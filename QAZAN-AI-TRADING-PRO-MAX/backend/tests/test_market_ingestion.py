import asyncio
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app
from app.schemas.common import CandlePoint
from app.schemas.ingestion import ProvenanceMetric
from app.services.http_resilient import fetch_json_resilient, rate_limit_monitor
from app.services.market_data_validator import validate_ohlcv_and_market_data
from app.services.market_derivatives_service import (
    _load_metric_cache,
    _save_metric_cache,
)

setup_logging()
init_db()
client = TestClient(app)


def test_resilient_http_retries_transient_503_and_tracks_rate_limits() -> None:
    rate_limit_monitor.reset_for_tests()
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"msg": "temp unavailable"})
        if calls["count"] == 2:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.05", "X-MBX-USED-WEIGHT-1M": "920"},
                json={"msg": "slow down"},
            )
        return httpx.Response(
            200,
            headers={"X-MBX-USED-WEIGHT-1M": "925"},
            json={"ok": True, "symbol": "BTCUSDT"},
        )

    async def _run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            return await fetch_json_resilient(
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                max_retries=3,
                base_backoff=0.02,
                client=mock_client,
            )

    res = asyncio.run(_run())
    assert res.status_code == 200
    assert res.data["ok"] is True
    assert res.retries_used == 2
    snap = rate_limit_monitor.snapshot()
    assert snap.retries_executed == 2
    assert snap.rate_limit_hits == 1
    assert snap.last_binance_used_weight_1m == 925


def test_validator_detects_missing_candle_gaps_invalid_ohlc_and_missing_fields() -> None:
    # Construct 3 hourly candles with 1 missing bar gap between 3600 and 10800 and 1 bad high < close
    candles = [
        CandlePoint(time=0, open=100.0, high=105.0, low=98.0, close=103.0, volume=120.0),
        CandlePoint(time=3600, open=103.0, high=108.0, low=101.0, close=107.0, volume=150.0),
        # Gap at 7200! Next bar at 10800 also has invalid high < close
        CandlePoint(time=10800, open=107.0, high=106.0, low=102.0, close=109.0, volume=180.0),
    ]
    metrics = {
        "liquidations": ProvenanceMetric(
            metric="liquidations",
            status="MISSING",
            value=None,
            source="Binance WS",
            updated_at=None,
        )
    }
    report = validate_ohlcv_and_market_data(
        symbol="BTCUSDT",
        interval="1h",
        candles=candles,
        metrics=metrics,
        reference_epoch=14500.0,
    )
    assert report.status == "INVALID"
    assert report.invalid_bars == 1
    assert report.missing_candle_gaps == 1
    assert report.missing_candles_estimated == 1
    assert 7200 in report.gap_timestamps
    assert "liquidations" in report.missing_fields


def test_metric_cache_stores_and_loads_provenance_without_fake_values() -> None:
    _save_metric_cache(
        "test:oi:BTCUSDT",
        "BTCUSDT",
        "open_interest",
        {"value": 81234.5, "notional_usd": 7500000000.0, "unit": "BTC", "source": "TestSource"},
        "TestSource",
        ttl_seconds=60.0,
    )
    loaded = _load_metric_cache("test:oi:BTCUSDT", allow_expired=False)
    assert loaded is not None
    data, updated_at, _age = loaded
    assert data["value"] == 81234.5
    assert updated_at


def test_dynamic_symbol_registry_add_remove_and_core_lock() -> None:
    list_res = client.get("/api/v1/data/symbols")
    assert list_res.status_code == 200
    syms = {item["symbol"] for item in list_res.json()["symbols"]}
    assert "BTCUSDT" in syms and "ETHUSDT" in syms

    # Core symbol cannot be deleted
    del_btc = client.delete("/api/v1/data/symbols/BTCUSDT")
    assert del_btc.status_code == 400
    assert del_btc.json()["error"]["code"] == "CORE_SYMBOL_LOCKED"

    # Invalid pair rejected cleanly
    bad_add = client.post("/api/v1/data/symbols", json={"symbol": "FAKESYM999"})
    assert bad_add.status_code == 400

    # Add real Binance pair DOGEUSDT, verify present, then clean up
    add_res = client.post("/api/v1/data/symbols", json={"symbol": "DOGEUSDT"})
    assert add_res.status_code == 201
    assert add_res.json()["symbol"] == "DOGEUSDT"

    del_res = client.delete("/api/v1/data/symbols/DOGEUSDT")
    assert del_res.status_code == 200
    remaining = {item["symbol"] for item in del_res.json()["symbols"]}
    assert "DOGEUSDT" not in remaining


def test_live_market_intelligence_btc_and_eth_with_provenance() -> None:
    for sym in ("BTCUSDT", "ETHUSDT"):
        res = client.get(f"/api/v1/data/market-intelligence?symbol={sym}&interval=1h")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == sym
        assert data["ohlcv_source"]
        assert data["ohlcv_updated_at"]
        assert data["ohlcv_summary"] is not None
        assert data["validation"]["candles_checked"] >= 100

        # Check provenance fields for every required metric
        for metric_key in ("volume_24h", "open_interest", "funding_rate", "cvd", "btc_dominance", "liquidations"):
            m = data[metric_key]
            assert m["source"]
            assert m["status"] in ("LIVE", "CACHED", "MISSING")
            if m["status"] in ("LIVE", "CACHED"):
                assert m["value"] is not None
                assert m["updated_at"] is not None
            else:
                # Anti-fake-data check: MISSING must NEVER fabricate a numeric value
                assert m["value"] is None

        # Connected technical & probability engines
        assert data["connected_engine"]["technical_bias"] in ("BULLISH", "BEARISH", "NEUTRAL")


def test_websocket_market_endpoint_snapshot_and_ping() -> None:
    with client.websocket_connect("/api/v1/ws/market?symbol=BTCUSDT") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert "ws_status" in snap
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["type"] == "pong"
