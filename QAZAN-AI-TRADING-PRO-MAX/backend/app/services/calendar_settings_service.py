from datetime import datetime, timezone
import hashlib
import httpx

from app.core.exceptions import ExternalMarketDataError
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.ml.predictor import run_ai_market_analysis
from app.schemas.platform import (
    AppSettingsPayload,
    DashboardSummaryResponse,
    EconomicCalendarResponse,
    EconomicEventItem,
)
from app.services.market_tickers_service import fetch_market_tickers
from app.services.paper_trading_service import get_paper_state
from app.services.quant_analysis_service import analyze_market_structure

logger = get_logger("qazan.calendar_settings")

PUBLIC_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


async def fetch_economic_calendar(
    impact: str = "ALL", country: str = "ALL"
) -> EconomicCalendarResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    norm_impact = impact.strip().upper()
    norm_country = country.strip().upper()

    events: list[EconomicEventItem] = []
    cached_fallback = False
    source = "ForexFactory Public Weekly Calendar JSON (Keyless)"

    # Serve from SQLite cache if fetched within the last 15 minutes to avoid upstream 429 limits
    with get_db_connection() as conn:
        recent_rows = conn.execute(
            "SELECT * FROM economic_calendar_cache ORDER BY event_date ASC"
        ).fetchall()
    if recent_rows:
        try:
            fetched_dt = datetime.fromisoformat(str(recent_rows[0]["fetched_at"]))
            if (datetime.now(timezone.utc) - fetched_dt).total_seconds() < 900:
                events = [
                    EconomicEventItem(
                        id=str(r["id"]),
                        title=str(r["title"]),
                        country=str(r["country"]),
                        event_date=str(r["event_date"]),
                        impact=str(r["impact"]),
                        forecast=r["forecast"],
                        previous=r["previous"],
                        actual=r["actual"],
                    )
                    for r in recent_rows
                ]
                if norm_impact != "ALL":
                    events = [e for e in events if e.impact.upper() == norm_impact]
                if norm_country != "ALL":
                    events = [e for e in events if e.country.upper() == norm_country]
                return EconomicCalendarResponse(
                    source="ForexFactory Public Weekly Calendar (SQLite Cached)",
                    cached_fallback=False,
                    fetched_at=str(recent_rows[0]["fetched_at"]),
                    total=len(events),
                    events=events,
                )
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(PUBLIC_CALENDAR_URL)
            res.raise_for_status()
            raw = res.json()

        if not isinstance(raw, list):
            raise ValueError("Unexpected economic calendar JSON format.")

        rows_to_cache = []
        for idx, item in enumerate(raw):
            title = str(item.get("title") or "").strip()
            ctry = str(item.get("country") or "").strip().upper()
            ev_date = str(item.get("date") or "").strip()
            imp = str(item.get("impact") or "Low").strip()
            forecast = str(item.get("forecast") or "").strip() or None
            previous = str(item.get("previous") or "").strip() or None
            actual = str(item.get("actual") or "").strip() or None
            ev_id = hashlib.md5(f"{ctry}:{ev_date}:{title}:{idx}".encode()).hexdigest()[:16]

            rows_to_cache.append(
                (ev_id, title, ctry, ev_date, imp, forecast, previous, actual, now_iso)
            )

        with get_db_connection() as conn:
            conn.execute("DELETE FROM economic_calendar_cache")
            conn.executemany(
                """
                INSERT OR REPLACE INTO economic_calendar_cache
                    (id, title, country, event_date, impact, forecast, previous, actual, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_cache,
            )

        for r in rows_to_cache:
            events.append(
                EconomicEventItem(
                    id=r[0],
                    title=r[1],
                    country=r[2],
                    event_date=r[3],
                    impact=r[4],
                    forecast=r[5],
                    previous=r[6],
                    actual=r[7],
                )
            )
    except Exception as exc:
        logger.warning("Economic calendar upstream failed: %s. Checking SQLite cache.", str(exc))
        with get_db_connection() as conn:
            cached = conn.execute(
                "SELECT * FROM economic_calendar_cache ORDER BY event_date ASC"
            ).fetchall()
        if cached:
            cached_fallback = True
            source = "SQLite Local Cache (Upstream Unavailable)"
            now_iso = str(cached[0]["fetched_at"])
            events = [
                EconomicEventItem(
                    id=str(r["id"]),
                    title=str(r["title"]),
                    country=str(r["country"]),
                    event_date=str(r["event_date"]),
                    impact=str(r["impact"]),
                    forecast=r["forecast"],
                    previous=r["previous"],
                    actual=r["actual"],
                )
                for r in cached
            ]
        else:
            from app.services.macro_news_service import fetch_macro_news

            macro_res = await fetch_macro_news(warning_hours=72)
            if not macro_res.events:
                raise ExternalMarketDataError(
                    "Unable to fetch economic calendar feed and no official macro fallback succeeded.",
                    details=str(exc),
                ) from exc
            cached_fallback = False
            source = "Official Central Banks & BLS Macro Fallback (ForexFactory Rate-Limited)"
            now_iso = macro_res.generated_at
            events = [
                EconomicEventItem(
                    id=m.id,
                    title=m.title,
                    country=m.country,
                    event_date=m.event_date,
                    impact=m.impact,
                    forecast=m.forecast,
                    previous=m.previous,
                    actual=m.actual,
                )
                for m in macro_res.events
            ]

    if norm_impact != "ALL":
        events = [e for e in events if e.impact.upper() == norm_impact]
    if norm_country != "ALL":
        events = [e for e in events if e.country.upper() == norm_country]

    return EconomicCalendarResponse(
        source=source,
        cached_fallback=cached_fallback,
        fetched_at=now_iso,
        total=len(events),
        events=events,
    )


def get_app_settings() -> AppSettingsPayload:
    defaults = AppSettingsPayload()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    mapping = {str(r["key"]): str(r["value"]) for r in rows}
    return AppSettingsPayload(
        default_symbol=mapping.get("default_symbol", defaults.default_symbol),
        default_interval=mapping.get("default_interval", defaults.default_interval),
        default_risk_pct=float(mapping.get("default_risk_pct", defaults.default_risk_pct)),
        language=mapping.get("language", defaults.language),
        theme=mapping.get("theme", defaults.theme),
    )


def save_app_settings(payload: AppSettingsPayload) -> AppSettingsPayload:
    now_iso = datetime.now(timezone.utc).isoformat()
    pairs = [
        ("default_symbol", payload.default_symbol.upper(), now_iso),
        ("default_interval", payload.default_interval, now_iso),
        ("default_risk_pct", str(payload.default_risk_pct), now_iso),
        ("language", payload.language, now_iso),
        ("theme", payload.theme, now_iso),
    ]
    with get_db_connection() as conn:
        conn.executemany(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            pairs,
        )
    return payload


async def build_dashboard_summary(symbol: str = "BTCUSDT", interval: str = "1h") -> DashboardSummaryResponse:
    tickers_resp = await fetch_market_tickers()
    paper_state = await get_paper_state()
    structure = await analyze_market_structure(symbol=symbol, interval=interval)
    ai_res = await run_ai_market_analysis(symbol=symbol, interval=interval)

    return DashboardSummaryResponse(
        active_symbol=structure.symbol,
        active_interval=structure.interval,
        tickers=tickers_resp.tickers,
        paper_balance_usdt=paper_state.balance_usdt,
        paper_equity_usdt=paper_state.total_equity_usdt,
        open_positions_count=len(paper_state.open_positions),
        realized_pnl_usdt=paper_state.realized_pnl_usdt,
        quick_structure_regime=structure.regime,
        quick_rsi_14=structure.rsi_14,
        quick_ai_signal=ai_res.signal,
        quick_ai_confidence_pct=ai_res.confidence_pct,
        system_status="healthy",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
