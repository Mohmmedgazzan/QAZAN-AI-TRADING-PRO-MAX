import sys
from pathlib import Path
import time
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app
from app.schemas.backtest_pro import ProBacktestRequest
from app.services.pro_backtest_service import run_pro_backtest_on_df

setup_logging()
init_db()
client = TestClient(app)


def _make_ohlcv_df(prices: list[float], interval_sec: int = 3600) -> pd.DataFrame:
    # Use timestamps safely in the past so all candles are closed
    base_ts = int(time.time()) - (len(prices) + 5) * interval_sec
    rows = []
    for i, close in enumerate(prices):
        prev = prices[i - 1] if i > 0 else close
        o = prev
        h = max(o, close) * 1.004
        l = min(o, close) * 0.996
        rows.append(
            {
                "time": base_ts + i * interval_sec,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(close, 4),
                "volume": 1000.0 + (i % 7) * 120.0,
            }
        )
    return pd.DataFrame(rows)


def test_pro_backtest_zero_lookahead_invariance_and_unclosed_exclusion() -> None:
    rng = np.random.default_rng(42)
    rets = rng.normal(0.0008, 0.011, size=260)
    prices = [50000.0]
    for r in rets:
        prices.append(prices[-1] * (1.0 + float(r)))
    full_df = _make_ohlcv_df(prices, interval_sec=3600)

    # Corrupt final future portion heavily to verify truncation before cutoff cannot affect prior trades
    cutoff = 190
    truncated_df = full_df.iloc[:cutoff].copy()
    mutated_df = full_df.copy()
    mutated_df.loc[mutated_df.index >= cutoff, "close"] *= 2.5
    mutated_df.loc[mutated_df.index >= cutoff, "high"] *= 2.6

    req = ProBacktestRequest(
        symbol="BTCUSDT",
        strategy="EMA_CROSS",
        primary_interval="1h",
        timeframes=["1h"],
        fee_pct=0.06,
        slippage_pct=0.04,
        persist=False,
    )
    sim_trunc, *_ = run_pro_backtest_on_df(truncated_df, req, timeframe="1h")
    sim_mut, *_ = run_pro_backtest_on_df(mutated_df, req, timeframe="1h")

    cutoff_ts = int(truncated_df.iloc[-1]["time"])
    trades_trunc = [t for t in sim_trunc["trades"] if t.exit_time < cutoff_ts]
    trades_mut_before = [t for t in sim_mut["trades"] if t.exit_time < cutoff_ts]

    assert len(trades_trunc) == len(trades_mut_before)
    for t1, t2 in zip(trades_trunc, trades_mut_before):
        assert t1.entry_time == t2.entry_time
        assert t1.entry_price == t2.entry_price
        assert t1.exit_price == t2.exit_price
        assert t1.net_pnl_usdt == t2.net_pnl_usdt

    # Also verify live unclosed candle at current timestamp is excluded automatically
    now_sec = int(time.time())
    with_unclosed = pd.concat(
        [
            truncated_df,
            pd.DataFrame(
                [
                    {
                        "time": now_sec - 120,  # within active 1h bar -> unclosed!
                        "open": 99999.0,
                        "high": 99999.0,
                        "low": 99999.0,
                        "close": 99999.0,
                        "volume": 5000.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    *_, closed_n_with_live, unclosed_excluded = run_pro_backtest_on_df(with_unclosed, req, timeframe="1h")
    assert unclosed_excluded is True
    assert closed_n_with_live == len(truncated_df)


def test_pro_backtest_fees_and_slippage_deduction() -> None:
    prices = []
    px = 100.0
    for i in range(240):
        # Smooth alternating wave creating multiple EMA crossovers
        px = 100.0 + 14.0 * np.sin(i / 6.5) + i * 0.08
        prices.append(float(px))
    df = _make_ohlcv_df(prices, interval_sec=3600)

    req_zero = ProBacktestRequest(
        symbol="ETHUSDT",
        strategy="EMA_CROSS",
        primary_interval="1h",
        timeframes=["1h"],
        fee_pct=0.0,
        slippage_pct=0.0,
        persist=False,
    )
    req_frict = req_zero.model_copy(update={"fee_pct": 0.10, "slippage_pct": 0.08})

    sim_zero, *_ = run_pro_backtest_on_df(df, req_zero, timeframe="1h")
    sim_frict, *_ = run_pro_backtest_on_df(df, req_frict, timeframe="1h")

    assert sim_zero["total_trades"] >= 3
    assert sim_frict["total_fees_usdt"] > 0.0
    assert sim_frict["total_slippage_usdt"] > 0.0
    assert sim_frict["final_equity"] < sim_zero["final_equity"]


def test_validation_gate_blocks_unproven_or_losing_strategy() -> None:
    # Downward choppy whipsaw designed to trigger losing crossovers -> MUST NOT pass validation
    prices = [100.0 - (i * 0.04) + (4.5 * np.sin(i * 0.95)) for i in range(220)]
    df = _make_ohlcv_df(prices, interval_sec=3600)

    req = ProBacktestRequest(
        symbol="BTCUSDT",
        strategy="EMA_CROSS",
        primary_interval="1h",
        timeframes=["1h"],
        fee_pct=0.10,
        slippage_pct=0.06,
        min_trades_required=8,
        min_profit_factor=1.15,
        max_allowed_drawdown_pct=20.0,
        persist=False,
    )
    sim, wf, status, is_success, gates, reasons, _, _ = run_pro_backtest_on_df(df, req, timeframe="1h")

    assert status == "FAILED"
    assert is_success is False
    assert len(reasons) >= 1
    assert any(not g.passed for g in gates)
    assert wf.folds_count >= 2
    for fold in wf.folds:
        assert fold.is_end_time < fold.oos_start_time


def test_live_pro_backtest_multi_timeframe_and_persistence() -> None:
    res = client.post(
        "/api/v1/backtest/pro/run",
        json={
            "symbol": "BTCUSDT",
            "strategy": "EMA_CROSS",
            "primary_interval": "1h",
            "timeframes": ["15m", "1h", "4h"],
            "lookback_bars": 260,
            "initial_capital": 10000.0,
            "risk_per_trade_pct": 1.0,
            "fee_pct": 0.06,
            "slippage_pct": 0.04,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 4.0,
            "walk_forward_folds": 4,
            "persist": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] is not None
    assert body["look_ahead_audit"]["look_ahead_bias_prevented"] is True
    assert body["look_ahead_audit"]["unclosed_bar_excluded"] is True
    assert body["look_ahead_audit"]["execution_timing"] == "SIGNAL_ON_CLOSED_BAR_FILL_NEXT_OPEN"
    assert len(body["timeframe_matrix"]) == 3
    assert {row["timeframe"] for row in body["timeframe_matrix"]} == {"15M", "1H", "4H"}
    assert body["walk_forward"]["folds_count"] >= 2

    # Never report strategy as successful if any validation gate failed
    all_passed = all(g["passed"] for g in body["validation_gates"])
    assert body["is_strategy_successful"] is all_passed
    assert body["validation_status"] == ("PASSED" if all_passed else "FAILED")

    # Saved reports endpoint + only_passed strict filter
    saved_all = client.get("/api/v1/backtest/pro/strategies?limit=20&only_passed=false")
    assert saved_all.status_code == 200
    assert any(item["id"] == body["run_id"] for item in saved_all.json())

    saved_passed = client.get("/api/v1/backtest/pro/strategies?limit=20&only_passed=true")
    assert saved_passed.status_code == 200
    for item in saved_passed.json():
        assert item["validation_status"] == "PASSED"
        assert item["is_strategy_successful"] is True

    del_res = client.delete(f"/api/v1/backtest/pro/strategies/{body['run_id']}")
    assert del_res.status_code == 200


def test_virtual_paper_trading_enhanced_accounting_and_sl_tp_validation() -> None:
    reset_res = client.post("/api/v1/paper/reset", json={"initial_balance": 25000.0})
    assert reset_res.status_code == 200
    state = reset_res.json()
    assert state["balance_usdt"] == 25000.0
    assert state["is_virtual"] is True
    assert state["virtual_currency"] == "VIRTUAL USDT"

    # Invalid SL for LONG (>= live market price) should fail cleanly
    bad_sl = client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "BTCUSDT",
            "side": "LONG",
            "notional_usdt": 1000.0,
            "leverage": 2.0,
            "stop_loss": 9999999.0,
        },
    )
    assert bad_sl.status_code == 400
    assert bad_sl.json()["error"]["code"] == "INVALID_STOP_LOSS"

    good_order = client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "BTCUSDT",
            "side": "LONG",
            "notional_usdt": 1000.0,
            "leverage": 2.0,
            "fee_pct": 0.06,
            "slippage_pct": 0.03,
        },
    )
    assert good_order.status_code == 201
    opened = good_order.json()["open_positions"][0]
    assert opened["entry_fee_usdt"] > 0.0
    assert opened["slippage_cost_usdt"] >= 0.0

    closed = client.post(f"/api/v1/paper/close/{opened['id']}")
    assert closed.status_code == 200
    closed_state = closed.json()
    assert closed_state["total_closed_trades"] >= 1
    assert closed_state["total_fees_paid_usdt"] > 0.0
    assert closed_state["closed_trades"][0]["close_reason"] == "MANUAL_MARKET"

    # Restore clean default $10,000 virtual account
    client.post("/api/v1/paper/reset")
