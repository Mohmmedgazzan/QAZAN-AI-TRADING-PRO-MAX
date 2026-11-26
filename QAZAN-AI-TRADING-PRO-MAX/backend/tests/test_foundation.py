import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure backend/ is importable
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app


setup_logging()
init_db()
client = TestClient(app)


def test_health_endpoint_reports_sqlite_and_ml_packages() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()

    assert payload["service"] == "QAZAN-AI-TRADING-PRO-MAX"
    assert payload["status"] == "healthy"
    assert payload["database"]["connected"] is True
    assert "system_logs" in payload["database"]["tables"]
    assert "market_candles_cache" in payload["database"]["tables"]

    ml_names = {pkg["name"]: pkg for pkg in payload["ml_runtime"]}
    for required in ("pandas", "numpy", "scikit-learn", "xgboost"):
        assert required in ml_names
        assert ml_names[required]["installed"] is True
        assert ml_names[required]["version"]


def test_error_pipeline_logs_to_sqlite_and_returns_structured_error() -> None:
    response = client.post("/api/v1/diagnostics/test-error")
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "DIAGNOSTIC_TEST_ERROR"
    assert payload["error"]["request_id"]

    logs_response = client.get("/api/v1/logs?limit=10&level=ERROR")
    assert logs_response.status_code == 200
    logs_payload = logs_response.json()
    assert logs_payload["total"] >= 1
    assert any("DIAGNOSTIC_TEST_ERROR" in entry["message"] for entry in logs_payload["logs"])


def test_client_error_recording_persists_to_sqlite() -> None:
    response = client.post(
        "/api/v1/logs/client",
        json={
            "level": "WARNING",
            "message": "Pytest frontend connectivity check warning",
            "context": "test_foundation",
        },
    )
    assert response.status_code == 201
    assert response.json()["recorded"] is True


def test_market_klines_rejects_unsupported_symbol_cleanly() -> None:
    response = client.get("/api/v1/market/klines?symbol=INVALIDPAIR&interval=1h")
    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["code"] == "EXTERNAL_MARKET_DATA_ERROR"
