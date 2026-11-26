from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app
from app.services.macro_news_service import (
    classify_macro_category,
    compute_warning_state,
)

setup_logging()
init_db()
client = TestClient(app)


def test_macro_category_classification_covers_all_seven_domains() -> None:
    assert classify_macro_category("FOMC Meeting Minutes", "USD") == "FED_DECISION"
    assert classify_macro_category("Federal Reserve issues FOMC statement", "USD") == "FED_DECISION"
    assert classify_macro_category("Official Bank Rate Decision", "GBP") == "INTEREST_RATE"
    assert classify_macro_category("CPI m/m", "USD") == "CPI"
    assert classify_macro_category("Core PPI m/m", "USD") == "PPI"
    assert classify_macro_category("Non-Farm Employment Change", "USD") == "NFP"
    assert classify_macro_category("Unemployment Rate", "USD") == "UNEMPLOYMENT"
    assert classify_macro_category("BOE Gov Bailey Speaks", "GBP") == "CENTRAL_BANK_SPEECH"
    assert classify_macro_category("ECB Press Speech", "EUR", "European Central Bank (ECB)") == "CENTRAL_BANK_SPEECH"


def test_pre_event_high_impact_warning_severity_tiers() -> None:
    now_dt = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

    def _ev(eid: str, title: str, cat: str, impact: str, offset_min: int) -> dict:
        dt = now_dt + timedelta(minutes=offset_min)
        return {
            "id": eid,
            "title": title,
            "category": cat,
            "country": "USD",
            "event_date": dt.isoformat(),
            "event_timestamp": int(dt.timestamp()),
            "impact": impact,
            "previous": "0.3%",
            "forecast": "0.4%",
            "actual": None,
            "source_name": "U.S. Bureau of Labor Statistics",
            "source_url": "https://www.bls.gov",
            "is_official_source": True,
        }

    # 1) Critical <= 60 min
    _, w_crit, lvl_crit, next_ev = compute_warning_state(
        [_ev("e1", "US CPI m/m", "CPI", "High", 45)],
        now_dt=now_dt,
        warning_hours=24,
    )
    assert lvl_crit == "CRITICAL"
    assert len(w_crit) == 1
    assert w_crit[0].severity == "CRITICAL"
    assert next_ev is not None and next_ev.id == "e1"

    # 2) Elevated (60 < m <= 360)
    _, w_elev, lvl_elev, _ = compute_warning_state(
        [_ev("e2", "FOMC Federal Funds Rate Decision", "FED_DECISION", "High", 180)],
        now_dt=now_dt,
        warning_hours=24,
    )
    assert lvl_elev == "ELEVATED"
    assert w_elev[0].severity == "ELEVATED"

    # 3) Watch (360 < m <= 1440)
    _, w_watch, lvl_watch, _ = compute_warning_state(
        [_ev("e3", "Non-Farm Payrolls", "NFP", "High", 720)],
        now_dt=now_dt,
        warning_hours=24,
    )
    assert lvl_watch == "WATCH"
    assert w_watch[0].severity == "WATCH"

    # 4) Clear when only Medium/Low, past events, or beyond window
    _, w_clear, lvl_clear, _ = compute_warning_state(
        [
            _ev("e4", "Minor Speech", "CENTRAL_BANK_SPEECH", "Medium", 30),
            _ev("e5", "Past CPI", "CPI", "High", -30),
            _ev("e6", "Far Future PPI", "PPI", "High", 48 * 60),
        ],
        now_dt=now_dt,
        warning_hours=24,
    )
    assert lvl_clear == "CLEAR"
    assert len(w_clear) == 0


def test_live_macro_news_endpoint_and_official_sources() -> None:
    res = client.get("/api/v1/calendar/macro?warning_hours=24")
    assert res.status_code == 200
    body = res.json()

    assert body["strict_official_sources_only"] is True
    assert body["fabricated_events_count"] == 0
    assert body["total"] >= 10

    # Verify official Federal Reserve & BLS snapshot fields are populated from real feeds
    snap = body["official_snapshot"]
    assert snap["fed_target_rate"] is not None
    assert snap["us_cpi_latest"] is not None
    assert snap["us_ppi_latest"] is not None
    assert snap["us_nfp_latest"] is not None
    assert snap["us_unemployment_latest"] is not None

    # Verify all 7 requested categories are tracked in category_counts
    counts = body["category_counts"]
    for req_cat in (
        "FED_DECISION",
        "INTEREST_RATE",
        "CPI",
        "PPI",
        "NFP",
        "UNEMPLOYMENT",
        "CENTRAL_BANK_SPEECH",
    ):
        assert req_cat in counts
        assert counts[req_cat] >= 1, f"Expected real events for category {req_cat}"

    # Verify filtering works cleanly without breaking response schema
    f_cpi = client.get("/api/v1/calendar/macro?category=CPI&impact=HIGH")
    assert f_cpi.status_code == 200
    cpi_events = f_cpi.json()["events"]
    assert len(cpi_events) >= 1
    assert all("CPI" in ev["tags"] and ev["impact"] == "High" for ev in cpi_events)

    # Verify original calendar endpoint remains 100% intact
    legacy = client.get("/api/v1/calendar/events")
    assert legacy.status_code == 200
    assert legacy.json()["total"] >= 1
