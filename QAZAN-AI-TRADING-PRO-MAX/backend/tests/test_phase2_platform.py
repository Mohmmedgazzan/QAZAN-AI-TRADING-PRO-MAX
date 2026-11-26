import sys
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app


setup_logging()
init_db()
client = TestClient(app)


def test_market_tickers_live() -> None:
    res = client.get("/api/v1/market/tickers")
    assert res.status_code == 200
    data = res.json()
    assert len(data["tickers"]) >= 4
    symbols = {t["symbol"] for t in data["tickers"]}
    assert "BTCUSDT" in symbols


def test_ai_analysis_and_candle_prediction_real_ml() -> None:
    ai_res = client.get("/api/v1/analysis/ai?symbol=BTCUSDT&interval=1h")
    assert ai_res.status_code == 200
    ai = ai_res.json()
    assert ai["signal"] in ("BULLISH", "BEARISH")
    assert ai["sample_size"] >= 100
    assert len(ai["top_features"]) > 0

    pred_res = client.get("/api/v1/analysis/candle-prediction?symbol=BTCUSDT&interval=1h")
    assert pred_res.status_code == 200
    pred = pred_res.json()
    assert pred["predicted_high"] >= pred["predicted_low"]
    assert pred["predicted_close"] > 0


def test_structure_liquidity_smc_quant_endpoints() -> None:
    for path in (
        "/api/v1/analysis/structure?symbol=BTCUSDT&interval=1h",
        "/api/v1/analysis/liquidity?symbol=BTCUSDT&interval=1h",
        "/api/v1/analysis/smc?symbol=BTCUSDT&interval=1h",
    ):
        res = client.get(path)
        assert res.status_code == 200, path


def test_risk_calculator_and_profile_persistence() -> None:
    calc = client.post(
        "/api/v1/risk/calculate",
        json={
            "account_balance": 10000,
            "risk_pct": 1.0,
            "entry_price": 60000,
            "stop_loss": 59000,
            "take_profit": 62000,
            "leverage": 5,
        },
    )
    assert calc.status_code == 200
    body = calc.json()
    assert body["direction"] == "LONG"
    assert body["risk_amount_usdt"] == 100.0
    assert body["risk_reward_ratio"] == 2.0

    put_res = client.put(
        "/api/v1/risk/profile",
        json={
            "account_balance": 15000,
            "risk_pct": 1.5,
            "default_rr": 2.5,
            "max_leverage": 10,
            "max_daily_loss_pct": 4.0,
        },
    )
    assert put_res.status_code == 200
    assert client.get("/api/v1/risk/profile").json()["account_balance"] == 15000.0


def test_backtest_engine_and_history() -> None:
    res = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "BTCUSDT",
            "interval": "1h",
            "strategy": "EMA_CROSS",
            "initial_capital": 10000,
            "fee_pct": 0.1,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 4.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["candle_count"] >= 200
    assert len(data["equity_curve"]) > 50

    hist = client.get("/api/v1/backtest/history")
    assert hist.status_code == 200
    assert len(hist.json()) >= 1


def test_paper_trading_lifecycle() -> None:
    reset = client.post("/api/v1/paper/reset")
    assert reset.status_code == 200
    assert reset.json()["balance_usdt"] == 10000.0

    order = client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "BTCUSDT",
            "side": "LONG",
            "notional_usdt": 1000.0,
            "leverage": 2.0,
        },
    )
    assert order.status_code == 201
    state = order.json()
    assert len(state["open_positions"]) == 1
    pos_id = state["open_positions"][0]["id"]

    closed = client.post(f"/api/v1/paper/close/{pos_id}")
    assert closed.status_code == 200
    assert len(closed.json()["open_positions"]) == 0
    assert len(closed.json()["closed_trades"]) >= 1

    # Restore clean 10,000 balance after test
    client.post("/api/v1/paper/reset")


def test_settings_and_scanner_and_calendar() -> None:
    put_s = client.put(
        "/api/v1/settings",
        json={
            "default_symbol": "ETHUSDT",
            "default_interval": "4h",
            "default_risk_pct": 1.5,
            "language": "ar",
            "theme": "dark",
        },
    )
    assert put_s.status_code == 200
    assert client.get("/api/v1/settings").json()["default_symbol"] == "ETHUSDT"

    scanner = client.get("/api/v1/scanner/scan?interval=1h")
    assert scanner.status_code == 200
    assert len(scanner.json()["items"]) >= 4

    cal = client.get("/api/v1/calendar/events")
    assert cal.status_code == 200
    assert cal.json()["total"] >= 1
