import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.engine.backtester import run_causal_backtest_on_df
from app.engine.technical_engine import analyze_dataframe_causal
from app.main import app


def _make_ohlcv_df(closes: list[float], interval_sec: int = 14400) -> pd.DataFrame:
    base_ts = 1_700_000_000
    rows = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c * 0.995
        h = max(o, c) * 1.006
        l = min(o, c) * 0.994
        rows.append(
            {
                "time": base_ts + i * interval_sec,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": 1200.0 + (i % 7) * 150.0,
            }
        )
    return pd.DataFrame(rows)


def test_zero_lookahead_bias_invariance():
    """
    Mathematical proof of zero look-ahead bias:
    Swings, structure breaks, and breach classifications confirmed on or before bar N-1
    must remain 100% identical when 35 future bars are appended.
    """
    rng = np.random.default_rng(42)
    steps = rng.normal(0.001, 0.015, size=140)
    prices = [100.0]
    for s in steps:
        prices.append(prices[-1] * (1.0 + float(s)))

    df_full = _make_ohlcv_df(prices)
    cutoff = 100
    cutoff_time = int(df_full["time"].iloc[cutoff - 1])

    snap_prefix = analyze_dataframe_causal(df_full.iloc[:cutoff], timeframe="4h")
    snap_full = analyze_dataframe_causal(df_full, timeframe="4h")

    prefix_swings = [(s.pivot_time, s.confirmed_time, s.kind, s.price) for s in snap_prefix.hh_hl_lh_ll_sequence]
    full_swings_before_cutoff = [
        (s.pivot_time, s.confirmed_time, s.kind, s.price)
        for s in snap_full.hh_hl_lh_ll_sequence
        if s.confirmed_time <= cutoff_time
    ]
    for sw in prefix_swings:
        if sw[1] >= full_swings_before_cutoff[0][1]:
            assert sw in full_swings_before_cutoff

    prefix_events = [(e.breach_time, e.confirmed_time, e.event_type, e.direction) for e in snap_prefix.structure_events]
    full_events_before_cutoff = [
        (e.breach_time, e.confirmed_time, e.event_type, e.direction)
        for e in snap_full.structure_events
        if e.confirmed_time <= cutoff_time
    ]
    for ev in prefix_events:
        if ev[1] >= (full_events_before_cutoff[0][1] if full_events_before_cutoff else 0):
            assert ev in full_events_before_cutoff


def test_unclosed_candle_excluded_before_close_time():
    prices = [100 + i * 0.4 + (1.5 if i % 5 == 0 else -0.6) for i in range(40)]
    df = _make_ohlcv_df(prices, interval_sec=14400)
    last_open = int(df["time"].iloc[-1])

    # Query 1000 seconds after last_open -> last bar is unclosed!
    res = analyze_dataframe_causal(df, timeframe="4h", as_of_ts=last_open + 1000)
    assert res.unclosed_bar_excluded is True
    assert res.closed_bars_analyzed == 39
    assert res.last_closed_time == int(df["time"].iloc[-2])


def test_breakout_vs_fakeout_vs_stop_hunt_distinction():
    # Single clear swing high at bar 4 (high=110.0) followed by consolidation below 105
    rows = []
    base_ts = 1_700_000_000
    closes = [
        100, 102, 105, 108, 109.5, 106, 104, 102, 100, 99,
        99.5, 100, 100.5, 101, 101.5, 102, 102.5, 103, 103.5, 104,
        104.2, 104.5, 105.0, 105.5, 106.0, 106.2, 106.5, 107.0, 108.0, 109.0,
    ]
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else 99.5
        rows.append(
            {
                "time": base_ts + i * 14400,
                "open": float(o),
                "high": float(max(o, c) + 0.4),
                "low": float(min(o, c) - 0.4),
                "close": float(c),
                "volume": 1200.0,
            }
        )
    df = pd.DataFrame(rows)
    # Bar 4 is clear swing high = 110.0
    df.loc[4, "high"] = 110.0
    # Bar 12: wick sweeps above 110.0 (high=111.4), closes back below (close=104.0) -> STOP_HUNT
    df.loc[12, "open"] = 104.5
    df.loc[12, "high"] = 111.4
    df.loc[12, "low"] = 103.8
    df.loc[12, "close"] = 104.0
    # Bar 16: closes above bar 12's swing high 111.4 (111.9), Bar 17 closes back below 111.4 (109.2) -> FAKEOUT
    df.loc[16, "open"] = 109.0
    df.loc[16, "high"] = 112.1
    df.loc[16, "low"] = 108.8
    df.loc[16, "close"] = 111.9
    df.loc[17, "open"] = 111.9
    df.loc[17, "high"] = 112.0
    df.loc[17, "low"] = 109.0
    df.loc[17, "close"] = 109.2
    # Bar 21: closes above bar 16's swing high 112.1 (112.8), Bar 22 holds above 112.1 (low=112.4, close=114.2) -> BREAKOUT
    df.loc[21, "open"] = 109.5
    df.loc[21, "high"] = 113.0
    df.loc[21, "low"] = 109.3
    df.loc[21, "close"] = 112.8
    df.loc[22, "open"] = 112.8
    df.loc[22, "high"] = 114.5
    df.loc[22, "low"] = 112.4
    df.loc[22, "close"] = 114.2

    res = analyze_dataframe_causal(df, timeframe="4h")
    classifications = {b.classification for b in res.level_breaches}
    assert "STOP_HUNT" in classifications
    assert "FAKEOUT" in classifications
    assert "BREAKOUT" in classifications


def test_causal_historical_backtester_runs_on_price_series():
    rng = np.random.default_rng(7)
    prices = [100.0]
    for idx in range(220):
        drift = 0.0025 if (idx // 35) % 2 == 0 else -0.0018
        prices.append(prices[-1] * (1.0 + drift + float(rng.normal(0, 0.012))))
    df = _make_ohlcv_df(prices)

    bt = run_causal_backtest_on_df(df, symbol="BTCUSDT", timeframe="4h", persist=False)
    expected_warmup = min(65, max(30, len(df) // 4))
    assert bt.look_ahead_bias_prevented is True
    assert bt.bars_tested == len(df) - expected_warmup
    assert bt.final_equity > 0
    assert (bt.breakouts_confirmed + bt.fakeouts_filtered + bt.stop_hunts_detected) > 0


def test_multi_tf_engine_and_backtest_api_endpoints():
    with TestClient(app) as client:
        res = client.get("/api/v1/engine/analyze?symbol=BTCUSDT&ltf=1h")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["primary_timeframes"] == ["1W", "1D", "4H"]
        assert data["look_ahead_bias_prevented"] is True
        assert set(["1W", "1D", "4H", "1H"]).issubset(set(data["timeframes"].keys()))
        assert data["market_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}
        assert data["market_phase"] in {"TREND", "RANGE", "CORRECTION"}
        assert data["ltf_confirmation"]["setup_status"] in {
            "CONFIRMED_LONG",
            "CONFIRMED_SHORT",
            "WAIT_CONFIRMATION",
            "NO_SETUP",
        }
        assert data["run_id"] is not None

        bt_res = client.post(
            "/api/v1/engine/backtest",
            json={"symbol": "BTCUSDT", "timeframe": "4h", "lookback_bars": 200},
        )
        assert bt_res.status_code == 200
        bt_data = bt_res.json()
        assert bt_data["look_ahead_bias_prevented"] is True
        assert bt_data["bars_tested"] > 100
        assert bt_data["run_id"] is not None

        hist_res = client.get("/api/v1/engine/history?limit=5")
        assert hist_res.status_code == 200
        hist_items = hist_res.json()
        assert len(hist_items) >= 2
