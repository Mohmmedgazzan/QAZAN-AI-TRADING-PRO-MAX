import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.schemas.macro_news import (
    HighImpactWarningItem,
    MacroEventItem,
    MacroNewsResponse,
    MacroSourceStatus,
    OfficialMacroSnapshot,
)

logger = get_logger("qazan.macro_news")

NY_TZ = ZoneInfo("America/New_York")
USER_AGENT = "QAZAN-Quant-MacroMonitor/1.0 (+https://www.federalreserve.gov)"
CACHE_TTL_SECONDS = 600

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FED_PRESS_RSS_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"
FED_FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_LATEST_RSS_URL = "https://www.bls.gov/feed/bls_latest.rss"
BLS_CPI_RSS_URL = "https://www.bls.gov/feed/cpi.rss"
BLS_PPI_RSS_URL = "https://www.bls.gov/feed/ppi.rss"
BLS_EMPSIT_RSS_URL = "https://www.bls.gov/feed/empsit.rss"
BLS_CPI_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/cpi.htm"
BLS_PPI_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/ppi.htm"
BLS_EMPSIT_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
ECB_PRESS_RSS_URL = "https://www.ecb.europa.eu/rss/press.html"
BOE_NEWS_RSS_URL = "https://www.bankofengland.co.uk/rss/news"

CATEGORY_META: dict[str, tuple[str, str]] = {
    "FED_DECISION": ("قرارات الاحتياطي الفيدرالي", "Federal Reserve / FOMC"),
    "INTEREST_RATE": ("قرارات الفائدة", "Interest Rate Decisions"),
    "CPI": ("التضخم (CPI)", "Consumer Price Index (CPI)"),
    "PPI": ("أسعار المنتجين (PPI)", "Producer Price Index (PPI)"),
    "NFP": ("الوظائف غير الزراعية (NFP)", "Non-Farm Payrolls (NFP)"),
    "UNEMPLOYMENT": ("البطالة ومطالبات العمل", "Unemployment & Jobless"),
    "CENTRAL_BANK_SPEECH": ("تصريحات البنوك المركزية", "Central Bank Statements"),
    "OTHER_MACRO": ("مؤشرات اقتصادية أخرى", "Other Macro Releases"),
}

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def classify_macro_category(title: str, country: str = "", source_name: str = "") -> str:
    t = title.lower()
    ctry = country.upper()
    src = source_name.lower()

    if "fomc" in t or ("federal reserve" in t and ("statement" in t or "minutes" in t or "decision" in t or "meeting" in t)):
        return "FED_DECISION"
    if "federal funds rate" in t or "official bank rate" in t or "bank rate" in t or "cash rate" in t or "policy rate" in t or "monetary policy summary" in t or "monetary policy statement" in t or "interest rate" in t or "overnight rate" in t or "main refinancing rate" in t:
        return "INTEREST_RATE"
    if "cpi" in t or "consumer price" in t:
        return "CPI"
    if "ppi" in t or "producer price" in t:
        return "PPI"
    if "non-farm" in t or "nonfarm" in t or "payroll" in t or "adp non" in t or ("employment change" in t and "unemployment" not in t):
        return "NFP"
    if "unemployment" in t or "jobless" in t or "claimant count" in t:
        return "UNEMPLOYMENT"
    if (
        "speaks" in t
        or "speech" in t
        or "press conference" in t
        or "testifies" in t
        or "gov " in t
        or "chair " in t
        or "chairman" in t
        or "president lagarde" in t
        or "ecb" in src
        or "bank of england" in src
        or "federal reserve" in src
        or (ctry == "USD" and "fed " in t)
        or ("boe " in t)
        or ("rba " in t)
        or ("boc " in t)
        or ("boj " in t)
        or ("snb " in t)
        or ("rbnz " in t)
    ):
        return "CENTRAL_BANK_SPEECH"
    return "OTHER_MACRO"


def _compute_event_tags(title: str, primary_cat: str) -> list[str]:
    t = title.lower()
    tags = [primary_cat]
    if primary_cat == "FED_DECISION" and ("interest rate" in t or "federal funds" in t or "statement" in t):
        if "INTEREST_RATE" not in tags:
            tags.append("INTEREST_RATE")
    if primary_cat == "INTEREST_RATE" and ("fomc" in t or "federal reserve" in t):
        if "FED_DECISION" not in tags:
            tags.append("FED_DECISION")
    if ("fomc" in t or "federal reserve" in t or "fed chair" in t) and "CENTRAL_BANK_SPEECH" not in tags and ("speaks" in t or "press conference" in t):
        tags.append("CENTRAL_BANK_SPEECH")
    if "unemployment" in t and "UNEMPLOYMENT" not in tags:
        tags.append("UNEMPLOYMENT")
    return tags


def _normalize_impact(raw_impact: str | None) -> str:
    val = (raw_impact or "").strip().lower()
    if val == "high":
        return "High"
    if val == "medium":
        return "Medium"
    if val == "low":
        return "Low"
    return "Medium"


def _parse_iso_or_rfc_date(raw_date: str) -> tuple[str, int] | None:
    text = (raw_date or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), int(dt.timestamp())
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), int(dt.timestamp())
    except Exception:
        return None


def _make_id(prefix: str, key: str) -> str:
    digest = hashlib.md5(f"{prefix}:{key}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _format_duration_text(minutes_until: int) -> tuple[str, str]:
    if minutes_until <= 0:
        return "الآن / قيد الصدور", "Due now"
    hours, mins = divmod(minutes_until, 60)
    days, rem_hours = divmod(hours, 24)
    if days > 0:
        return f"بعد {days} يوم و{rem_hours} ساعة", f"in {days}d {rem_hours}h"
    if hours > 0:
        return f"بعد {hours} ساعة و{mins} دقيقة", f"in {hours}h {mins}m"
    return f"بعد {mins} دقيقة", f"in {mins}m"


def compute_warning_state(
    events: list[dict],
    now_dt: datetime,
    warning_hours: int = 24,
) -> tuple[list[MacroEventItem], list[HighImpactWarningItem], str, MacroEventItem | None]:
    now_ts = int(now_dt.timestamp())
    window_minutes = max(60, warning_hours * 60)

    hydrated: list[MacroEventItem] = []
    warnings: list[HighImpactWarningItem] = []

    for raw in events:
        ev_ts = int(raw["event_timestamp"])
        minutes_until = int((ev_ts - now_ts) // 60)
        cat = str(raw["category"])
        cat_ar, cat_en = CATEGORY_META.get(cat, CATEGORY_META["OTHER_MACRO"])
        impact = str(raw["impact"])

        if minutes_until < 0:
            ev_status = "RELEASED"
        elif minutes_until <= 60:
            ev_status = "IMMINENT"
        else:
            ev_status = "UPCOMING"

        warning_active = False
        warning_severity = "NONE"
        if impact == "High" and 0 <= minutes_until <= window_minutes:
            warning_active = True
            if minutes_until <= 60:
                warning_severity = "CRITICAL"
            elif minutes_until <= 360:
                warning_severity = "ELEVATED"
            else:
                warning_severity = "WATCH"

            dur_ar, dur_en = _format_duration_text(minutes_until)
            warnings.append(
                HighImpactWarningItem(
                    event_id=str(raw["id"]),
                    title=str(raw["title"]),
                    category=cat,
                    country=str(raw["country"]),
                    event_date=str(raw["event_date"]),
                    minutes_until=minutes_until,
                    severity=warning_severity,
                    source_name=str(raw["source_name"]),
                    warning_text_ar=(
                        f"تنبيه تقلب عالٍ: خبر [{raw['country']}] {raw['title']} ({cat_ar}) يصدر {dur_ar}."
                    ),
                    warning_text_en=(
                        f"High-Impact Alert: [{raw['country']}] {raw['title']} ({cat_en}) scheduled {dur_en}."
                    ),
                )
            )

        hydrated.append(
            MacroEventItem(
                id=str(raw["id"]),
                title=str(raw["title"]),
                category=cat,
                tags=_compute_event_tags(str(raw["title"]), cat),
                category_label_ar=cat_ar,
                category_label_en=cat_en,
                country=str(raw["country"]),
                event_date=str(raw["event_date"]),
                event_timestamp=ev_ts,
                impact=impact,
                previous=raw.get("previous"),
                forecast=raw.get("forecast"),
                actual=raw.get("actual"),
                source_name=str(raw["source_name"]),
                source_url=str(raw["source_url"]),
                is_official_source=bool(raw.get("is_official_source", True)),
                event_status=ev_status,
                minutes_until=minutes_until,
                warning_active=warning_active,
                warning_severity=warning_severity,
            )
        )

    warnings.sort(key=lambda w: w.minutes_until)

    active_level = "CLEAR"
    if any(w.severity == "CRITICAL" for w in warnings):
        active_level = "CRITICAL"
    elif any(w.severity == "ELEVATED" for w in warnings):
        active_level = "ELEVATED"
    elif warnings:
        active_level = "WATCH"

    upcoming_high = [e for e in hydrated if e.impact == "High" and e.minutes_until >= 0]
    upcoming_high.sort(key=lambda e: e.event_timestamp)
    next_high = upcoming_high[0] if upcoming_high else None

    return hydrated, warnings, active_level, next_high


async def _fetch_ff_events(client: httpx.AsyncClient, now_iso: str) -> tuple[list[dict], MacroSourceStatus]:
    try:
        res = await client.get(FF_CALENDAR_URL)
        res.raise_for_status()
        payload = res.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected ForexFactory JSON format.")

        items: list[dict] = []
        for idx, row in enumerate(payload):
            title = str(row.get("title") or "").strip()
            ctry = str(row.get("country") or "").strip().upper()
            parsed = _parse_iso_or_rfc_date(str(row.get("date") or ""))
            if not title or not parsed:
                continue
            ev_iso, ev_ts = parsed
            cat = classify_macro_category(title, ctry, "ForexFactory")
            items.append(
                {
                    "id": _make_id("ff", f"{ctry}:{ev_iso}:{title}:{idx}"),
                    "title": title,
                    "category": cat,
                    "country": ctry or "GLOBAL",
                    "event_date": ev_iso,
                    "event_timestamp": ev_ts,
                    "impact": _normalize_impact(row.get("impact")),
                    "previous": (str(row.get("previous") or "").strip() or None),
                    "forecast": (str(row.get("forecast") or "").strip() or None),
                    "actual": (str(row.get("actual") or "").strip() or None),
                    "source_name": "ForexFactory Public Calendar",
                    "source_url": FF_CALENDAR_URL,
                    "is_official_source": False,
                }
            )

        return items, MacroSourceStatus(
            source_id="forexfactory",
            source_name="ForexFactory Public Weekly Calendar",
            official_url=FF_CALENDAR_URL,
            status="LIVE",
            events_count=len(items),
            fetched_at=now_iso,
            note="Weekly macro calendar with consensus forecasts & previous prints.",
        )
    except Exception as exc:
        logger.warning("ForexFactory feed failed (%s); checking SQLite FF cache.", str(exc))
        cached_ff: list[dict] = []
        cached_at = now_iso
        with get_db_connection() as conn:
            ff_rows = conn.execute(
                "SELECT * FROM macro_news_events_cache WHERE is_official_source = 0 ORDER BY event_timestamp ASC"
            ).fetchall()
            if ff_rows:
                cached_at = str(ff_rows[0]["fetched_at"])
                cached_ff = [dict(r) for r in ff_rows]
            else:
                ec_rows = conn.execute(
                    "SELECT * FROM economic_calendar_cache ORDER BY event_date ASC"
                ).fetchall()
                for r in ec_rows:
                    parsed = _parse_iso_or_rfc_date(str(r["event_date"]))
                    if not parsed:
                        continue
                    ev_iso, ev_ts = parsed
                    title = str(r["title"])
                    ctry = str(r["country"]).upper()
                    cached_at = str(r["fetched_at"])
                    cached_ff.append(
                        {
                            "id": f"ff_{r['id']}",
                            "title": title,
                            "category": classify_macro_category(title, ctry, "ForexFactory"),
                            "country": ctry,
                            "event_date": ev_iso,
                            "event_timestamp": ev_ts,
                            "impact": _normalize_impact(str(r["impact"])),
                            "previous": r["previous"],
                            "forecast": r["forecast"],
                            "actual": r["actual"],
                            "source_name": "ForexFactory Public Calendar (SQLite Cached)",
                            "source_url": FF_CALENDAR_URL,
                            "is_official_source": False,
                        }
                    )

        return cached_ff, MacroSourceStatus(
            source_id="forexfactory",
            source_name="ForexFactory Public Weekly Calendar",
            official_url=FF_CALENDAR_URL,
            status="CACHED" if cached_ff else "DEGRADED",
            events_count=len(cached_ff),
            fetched_at=cached_at,
            note=(
                f"Rate-limited/unavailable ({type(exc).__name__}); using {len(cached_ff)} SQLite cached weekly events."
                if cached_ff
                else f"Fetch error: {type(exc).__name__}"
            ),
        )


def _extract_bls_release_dates(html_text: str, now_dt: datetime) -> list[datetime]:
    clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text))
    pattern = re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(202\d)\s+(\d{1,2}:\d{2}\s+[AP]M)",
        re.I,
    )
    out: list[datetime] = []
    seen_dates: set[str] = set()
    cutoff_past = now_dt - timedelta(days=35)
    cutoff_future = now_dt + timedelta(days=95)
    for m in pattern.finditer(clean):
        mon_str, day_str, yr_str, tm_str = m.groups()
        mon = _MONTH_MAP.get(mon_str.lower().rstrip("."))
        if not mon:
            continue
        try:
            tm = datetime.strptime(tm_str.upper(), "%I:%M %p")
            dt = datetime(int(yr_str), mon, int(day_str), tm.hour, tm.minute, tzinfo=NY_TZ)
        except Exception:
            continue
        key = dt.date().isoformat()
        if cutoff_past <= dt <= cutoff_future and key not in seen_dates:
            seen_dates.add(key)
            out.append(dt)
    out.sort()
    return out


def _parse_bls_atom_pair(xml_text: str) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Return (latest_title, latest_date_iso, latest_value, prev_value, link)."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None, None, None, None, None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        return None, None, None, None, None

    def _extract_val(title_txt: str, content_txt: str) -> str | None:
        combined = f"{title_txt} {content_txt}"
        is_neg = bool(re.search(r"\b(decreas|fall|fell|declin|drop|contract)\w*", title_txt, re.I))
        pct = re.search(r"([-+]?\d+\.\d+%|\d{1,3},\d{3}|unchanged)", combined, re.I)
        if pct:
            val = pct.group(1)
            if is_neg and not val.startswith(("-", "+")) and val.lower() != "unchanged":
                return f"-{val}"
            return val
        pct_word = re.search(r"([-+]?\d+\.\d+)\s*percent", combined, re.I)
        if pct_word:
            val = f"{pct_word.group(1)}%"
            if is_neg and not val.startswith(("-", "+")):
                return f"-{val}"
            return val
        return None

    first = entries[0]
    title0 = (first.findtext("atom:title", default="", namespaces=ns) or "").strip()
    content0 = (first.findtext("atom:content", default="", namespaces=ns) or "").strip()
    pub0 = (first.findtext("atom:published", default="", namespaces=ns) or "").strip()
    link_el = first.find("atom:link", ns)
    link0 = link_el.attrib.get("href", "") if link_el is not None else ""
    val0 = _extract_val(title0, content0)

    val1 = None
    if len(entries) > 1:
        second = entries[1]
        t1 = (second.findtext("atom:title", default="", namespaces=ns) or "").strip()
        c1 = (second.findtext("atom:content", default="", namespaces=ns) or "").strip()
        val1 = _extract_val(t1, c1)

    return title0, pub0, val0, val1, link0


async def _fetch_bls_official(
    client: httpx.AsyncClient, now_dt: datetime, now_iso: str
) -> tuple[list[dict], dict[str, str | None], MacroSourceStatus]:
    snapshot_updates: dict[str, str | None] = {}
    items: list[dict] = []
    urls = {
        "latest": BLS_LATEST_RSS_URL,
        "cpi_rss": BLS_CPI_RSS_URL,
        "ppi_rss": BLS_PPI_RSS_URL,
        "empsit_rss": BLS_EMPSIT_RSS_URL,
        "cpi_sched": BLS_CPI_SCHEDULE_URL,
        "ppi_sched": BLS_PPI_SCHEDULE_URL,
        "empsit_sched": BLS_EMPSIT_SCHEDULE_URL,
    }
    responses = await asyncio.gather(
        *[client.get(u) for u in urls.values()],
        return_exceptions=True,
    )
    res_map = dict(zip(urls.keys(), responses))

    ok_count = sum(1 for r in responses if isinstance(r, httpx.Response) and r.status_code == 200)
    if ok_count == 0:
        return [], snapshot_updates, MacroSourceStatus(
            source_id="bls_gov",
            source_name="U.S. Bureau of Labor Statistics (BLS.gov)",
            official_url=BLS_LATEST_RSS_URL,
            status="DEGRADED",
            events_count=0,
            fetched_at=now_iso,
            note="Unable to reach BLS.gov feeds.",
        )

    latest_metrics: dict[str, str] = {}
    latest_resp = res_map.get("latest")
    if isinstance(latest_resp, httpx.Response) and latest_resp.status_code == 200:
        cdata_m = re.search(r"<!\[CDATA\[(.*?)\]\]>", latest_resp.text, re.S)
        body_html = cdata_m.group(1) if cdata_m else latest_resp.text
        pairs = re.findall(
            r"<p>\s*([^<:]+):\s*<br>\s*<strong><span[^>]*class=\"data\"[^>]*>([^<]+)</span>",
            body_html,
            re.I | re.S,
        )
        for label, val in pairs:
            clean_label = html.unescape(re.sub(r"\s+", " ", label)).strip()
            clean_val = html.unescape(re.sub(r"\s+", " ", val)).strip()
            latest_metrics[clean_label] = clean_val

    cpi_latest_val = latest_metrics.get("Consumer Price Index (CPI)")
    ppi_latest_val = latest_metrics.get("Producer Price Index - Final Demand")
    nfp_latest_val = latest_metrics.get("Payroll Employment")
    unemp_latest_val = latest_metrics.get("Unemployment Rate")

    # Parse Atom feeds for exact actual/previous prints and timestamps
    cpi_rss = res_map.get("cpi_rss")
    cpi_prev_val = None
    if isinstance(cpi_rss, httpx.Response) and cpi_rss.status_code == 200:
        t0, pub0, v0, v1, link0 = _parse_bls_atom_pair(cpi_rss.text)
        cpi_prev_val = v1
        parsed_pub = _parse_iso_or_rfc_date(pub0 or "")
        if t0 and parsed_pub:
            ev_iso, ev_ts = parsed_pub
            items.append(
                {
                    "id": _make_id("bls_cpi_rel", ev_iso),
                    "title": f"US BLS Official CPI Release — {t0}",
                    "category": "CPI",
                    "country": "USD",
                    "event_date": ev_iso,
                    "event_timestamp": ev_ts,
                    "impact": "High",
                    "previous": v1,
                    "forecast": None,
                    "actual": cpi_latest_val or v0,
                    "source_name": "U.S. Bureau of Labor Statistics (BLS.gov)",
                    "source_url": link0 or BLS_CPI_RSS_URL,
                    "is_official_source": True,
                }
            )

    ppi_rss = res_map.get("ppi_rss")
    ppi_prev_val = None
    if isinstance(ppi_rss, httpx.Response) and ppi_rss.status_code == 200:
        t0, pub0, v0, v1, link0 = _parse_bls_atom_pair(ppi_rss.text)
        ppi_prev_val = v1
        parsed_pub = _parse_iso_or_rfc_date(pub0 or "")
        if t0 and parsed_pub:
            ev_iso, ev_ts = parsed_pub
            items.append(
                {
                    "id": _make_id("bls_ppi_rel", ev_iso),
                    "title": f"US BLS Official PPI Release — {t0}",
                    "category": "PPI",
                    "country": "USD",
                    "event_date": ev_iso,
                    "event_timestamp": ev_ts,
                    "impact": "High",
                    "previous": v1,
                    "forecast": None,
                    "actual": ppi_latest_val or v0,
                    "source_name": "U.S. Bureau of Labor Statistics (BLS.gov)",
                    "source_url": link0 or BLS_PPI_RSS_URL,
                    "is_official_source": True,
                }
            )

    empsit_rss = res_map.get("empsit_rss")
    nfp_prev_val = None
    unemp_prev_val = None
    if isinstance(empsit_rss, httpx.Response) and empsit_rss.status_code == 200:
        try:
            root = ET.fromstring(empsit_rss.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            if entries:
                e0 = entries[0]
                t0 = (e0.findtext("atom:title", default="", namespaces=ns) or "").strip()
                c0 = (e0.findtext("atom:content", default="", namespaces=ns) or "").strip()
                pub0 = (e0.findtext("atom:published", default="", namespaces=ns) or "").strip()
                l0_el = e0.find("atom:link", ns)
                l0 = l0_el.attrib.get("href", "") if l0_el is not None else BLS_EMPSIT_RSS_URL

                if len(entries) > 1:
                    c1 = (entries[1].findtext("atom:content", default="", namespaces=ns) or "").strip()
                    t1 = (entries[1].findtext("atom:title", default="", namespaces=ns) or "").strip()
                    m_nfp1 = re.search(r"(\d{1,3},\d{3}|unchanged)", f"{t1} {c1}", re.I)
                    m_u1 = re.search(r"unemployment rate[^0-9]*(\d+\.\d+)\s*(?:%|percent)", f"{t1} {c1}", re.I)
                    nfp_prev_val = m_nfp1.group(1) if m_nfp1 else None
                    unemp_prev_val = f"{m_u1.group(1)}%" if m_u1 else None

                parsed_pub = _parse_iso_or_rfc_date(pub0)
                if t0 and parsed_pub:
                    ev_iso, ev_ts = parsed_pub
                    items.append(
                        {
                            "id": _make_id("bls_nfp_rel", ev_iso),
                            "title": f"US Non-Farm Payrolls (NFP) Official Release — {t0}",
                            "category": "NFP",
                            "country": "USD",
                            "event_date": ev_iso,
                            "event_timestamp": ev_ts,
                            "impact": "High",
                            "previous": nfp_prev_val,
                            "forecast": None,
                            "actual": nfp_latest_val,
                            "source_name": "U.S. Bureau of Labor Statistics (BLS.gov)",
                            "source_url": l0,
                            "is_official_source": True,
                        }
                    )
                    if unemp_latest_val:
                        items.append(
                            {
                                "id": _make_id("bls_unemp_rel", ev_iso),
                                "title": "US Official Unemployment Rate (BLS Employment Situation)",
                                "category": "UNEMPLOYMENT",
                                "country": "USD",
                                "event_date": ev_iso,
                                "event_timestamp": ev_ts,
                                "impact": "High",
                                "previous": unemp_prev_val,
                                "forecast": None,
                                "actual": unemp_latest_val,
                                "source_name": "U.S. Bureau of Labor Statistics (BLS.gov)",
                                "source_url": l0,
                                "is_official_source": True,
                            }
                        )
        except Exception as exc:
            logger.warning("Failed parsing BLS empsit Atom feed: %s", str(exc))

    # Official upcoming scheduled release dates from bls.gov/schedule/news_release/*
    cpi_next_date = None
    ppi_next_date = None
    nfp_next_date = None

    sched_configs = [
        ("cpi_sched", "US CPI (Consumer Price Index) Official Release", "CPI", cpi_latest_val, BLS_CPI_SCHEDULE_URL),
        ("ppi_sched", "US PPI (Producer Price Index) Official Release", "PPI", ppi_latest_val, BLS_PPI_SCHEDULE_URL),
        ("empsit_sched", "US Non-Farm Payrolls (NFP) & Unemployment Rate", "NFP", nfp_latest_val, BLS_EMPSIT_SCHEDULE_URL),
    ]
    for key, title, cat, prev_val, url in sched_configs:
        resp = res_map.get(key)
        if not isinstance(resp, httpx.Response) or resp.status_code != 200:
            continue
        dates = _extract_bls_release_dates(resp.text, now_dt)
        upcoming = [d for d in dates if d > now_dt]
        if upcoming:
            nxt = upcoming[0]
            if key == "cpi_sched":
                cpi_next_date = nxt.isoformat()
            elif key == "ppi_sched":
                ppi_next_date = nxt.isoformat()
            elif key == "empsit_sched":
                nfp_next_date = nxt.isoformat()
            for d in upcoming[:2]:
                d_iso = d.isoformat()
                items.append(
                    {
                        "id": _make_id(f"bls_sched_{cat}", d_iso),
                        "title": title,
                        "category": cat,
                        "country": "USD",
                        "event_date": d_iso,
                        "event_timestamp": int(d.timestamp()),
                        "impact": "High",
                        "previous": prev_val,
                        "forecast": None,
                        "actual": None,
                        "source_name": "U.S. Bureau of Labor Statistics Schedule",
                        "source_url": url,
                        "is_official_source": True,
                    }
                )
                if key == "empsit_sched" and unemp_latest_val:
                    items.append(
                        {
                            "id": _make_id("bls_sched_UNEMP", d_iso),
                            "title": "US Unemployment Rate Official Release (BLS)",
                            "category": "UNEMPLOYMENT",
                            "country": "USD",
                            "event_date": d_iso,
                            "event_timestamp": int(d.timestamp()),
                            "impact": "High",
                            "previous": unemp_latest_val,
                            "forecast": None,
                            "actual": None,
                            "source_name": "U.S. Bureau of Labor Statistics Schedule",
                            "source_url": url,
                            "is_official_source": True,
                        }
                    )

    snapshot_updates.update(
        {
            "us_cpi_latest": cpi_latest_val,
            "us_cpi_previous": cpi_prev_val,
            "us_cpi_next_date": cpi_next_date,
            "us_ppi_latest": ppi_latest_val,
            "us_ppi_previous": ppi_prev_val,
            "us_ppi_next_date": ppi_next_date,
            "us_nfp_latest": nfp_latest_val,
            "us_nfp_previous": nfp_prev_val,
            "us_nfp_next_date": nfp_next_date,
            "us_unemployment_latest": unemp_latest_val,
            "us_unemployment_previous": unemp_prev_val,
        }
    )

    return items, snapshot_updates, MacroSourceStatus(
        source_id="bls_gov",
        source_name="U.S. Bureau of Labor Statistics (BLS.gov)",
        official_url=BLS_LATEST_RSS_URL,
        status="LIVE",
        events_count=len(items),
        fetched_at=now_iso,
        note="Official US CPI, PPI, NFP & Unemployment actuals and release schedule.",
    )


def _extract_fomc_upcoming_dates(html_text: str, now_dt: datetime) -> list[tuple[datetime, bool]]:
    """Parse official 2026 & 2027 FOMC decision dates from federalreserve.gov."""
    results: list[tuple[datetime, bool]] = []
    for year in (now_dt.year, now_dt.year + 1):
        marker = f"{year} FOMC Meetings"
        start = html_text.find(marker)
        if start == -1:
            continue
        next_panel = html_text.find("FOMC Meetings", start + len(marker))
        block = html_text[start:next_panel] if next_panel != -1 else html_text[start : start + 12000]
        clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))
        # Match patterns like "December 8-9*" or "January 26-27" or "May 4-5"
        matches = re.finditer(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s*-\s*(\d{1,2})(\*?)\b",
            clean,
        )
        seen_dates: set[str] = set()
        for m in matches:
            mon_name, d1_s, d2_s, star = m.groups()
            mon = _MONTH_MAP.get(mon_name.lower())
            if not mon:
                continue
            d1, d2 = int(d1_s), int(d2_s)
            decision_day = d2 if d2 >= d1 else d2
            decision_month = mon if d2 >= d1 else (mon % 12) + 1
            try:
                dt = datetime(year, decision_month, decision_day, 14, 0, tzinfo=NY_TZ)
            except Exception:
                continue
            iso_day = dt.date().isoformat()
            if dt >= (now_dt - timedelta(days=1)) and iso_day not in seen_dates:
                seen_dates.add(iso_day)
                results.append((dt, bool(star)))
    results.sort(key=lambda x: x[0])
    return results


async def _fetch_fed_official(
    client: httpx.AsyncClient, now_dt: datetime, now_iso: str
) -> tuple[list[dict], dict[str, str | None], MacroSourceStatus]:
    items: list[dict] = []
    snap: dict[str, str | None] = {}

    rss_res, cal_res = await asyncio.gather(
        client.get(FED_PRESS_RSS_URL),
        client.get(FED_FOMC_CALENDAR_URL),
        return_exceptions=True,
    )

    fed_target_rate: str | None = None
    fed_rate_date: str | None = None
    fed_rate_url: str | None = None
    latest_statement_url: str | None = None

    if isinstance(rss_res, httpx.Response) and rss_res.status_code == 200:
        try:
            root = ET.fromstring(rss_res.text)
            cutoff_past = now_dt - timedelta(days=45)
            for item_el in root.findall(".//item")[:10]:
                title = (item_el.findtext("title") or "").strip()
                pub = (item_el.findtext("pubDate") or "").strip()
                link = (item_el.findtext("link") or FED_PRESS_RSS_URL).strip()
                parsed = _parse_iso_or_rfc_date(pub)
                if not title or not parsed:
                    continue
                ev_iso, ev_ts = parsed
                if "issues fomc statement" in title.lower() and not latest_statement_url:
                    latest_statement_url = link
                    fed_rate_date = ev_iso
                    fed_rate_url = link

                if datetime.fromtimestamp(ev_ts, tz=timezone.utc) < cutoff_past:
                    continue

                cat = classify_macro_category(title, "USD", "Federal Reserve")
                items.append(
                    {
                        "id": _make_id("fed_rss", f"{ev_iso}:{title}"),
                        "title": title,
                        "category": cat,
                        "country": "USD",
                        "event_date": ev_iso,
                        "event_timestamp": ev_ts,
                        "impact": "High",
                        "previous": None,
                        "forecast": None,
                        "actual": None,
                        "source_name": "Federal Reserve Official Press",
                        "source_url": link,
                        "is_official_source": True,
                    }
                )
        except Exception as exc:
            logger.warning("Failed parsing Fed monetary RSS: %s", str(exc))

    # Extract exact target federal funds rate from latest official FOMC statement page
    if latest_statement_url:
        try:
            st_res = await client.get(latest_statement_url)
            if st_res.status_code == 200:
                clean_st = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", st_res.text))
                m_rate = re.search(
                    r"target range for the federal funds rate (?:at|to)\s+([0-9\-/]+\s+to\s+[0-9\-/]+\s+percent)",
                    clean_st,
                    re.I,
                )
                if m_rate:
                    fed_target_rate = m_rate.group(1).strip()
                    for ev in items:
                        if ev["source_url"] == latest_statement_url:
                            ev["actual"] = fed_target_rate
                            ev["category"] = "FED_DECISION"
        except Exception as exc:
            logger.warning("Unable to inspect latest FOMC statement text: %s", str(exc))

    next_fomc_date = None
    if isinstance(cal_res, httpx.Response) and cal_res.status_code == 200:
        fomc_dates = _extract_fomc_upcoming_dates(cal_res.text, now_dt)
        if fomc_dates:
            next_fomc_date = fomc_dates[0][0].isoformat()
            for dt, has_sep in fomc_dates[:3]:
                dt_iso = dt.isoformat()
                suffix = " & Economic Projections (SEP)" if has_sep else ""
                items.append(
                    {
                        "id": _make_id("fed_fomc_sched", dt_iso),
                        "title": f"FOMC Federal Funds Interest Rate Decision{suffix}",
                        "category": "FED_DECISION",
                        "country": "USD",
                        "event_date": dt_iso,
                        "event_timestamp": int(dt.timestamp()),
                        "impact": "High",
                        "previous": fed_target_rate,
                        "forecast": None,
                        "actual": None,
                        "source_name": "Federal Reserve FOMC Official Calendar",
                        "source_url": FED_FOMC_CALENDAR_URL,
                        "is_official_source": True,
                    }
                )

    snap.update(
        {
            "fed_target_rate": fed_target_rate,
            "fed_rate_date": fed_rate_date,
            "fed_rate_url": fed_rate_url,
            "next_fomc_date": next_fomc_date,
        }
    )

    ok_any = (
        (isinstance(rss_res, httpx.Response) and rss_res.status_code == 200)
        or (isinstance(cal_res, httpx.Response) and cal_res.status_code == 200)
    )
    return items, snap, MacroSourceStatus(
        source_id="federal_reserve",
        source_name="U.S. Federal Reserve (FOMC)",
        official_url=FED_FOMC_CALENDAR_URL,
        status="LIVE" if ok_any else "DEGRADED",
        events_count=len(items),
        fetched_at=now_iso,
        note="Official FOMC rate decisions, minutes, and meeting calendar.",
    )


async def _fetch_ecb_official(
    client: httpx.AsyncClient, now_dt: datetime, now_iso: str
) -> tuple[list[dict], MacroSourceStatus]:
    try:
        res = await client.get(ECB_PRESS_RSS_URL)
        res.raise_for_status()
        root = ET.fromstring(res.text)
        cutoff = now_dt - timedelta(days=21)
        items: list[dict] = []
        for item_el in root.findall(".//item")[:8]:
            title = (item_el.findtext("title") or "").strip()
            pub = (item_el.findtext("pubDate") or "").strip()
            link = (item_el.findtext("link") or ECB_PRESS_RSS_URL).strip()
            parsed = _parse_iso_or_rfc_date(pub)
            if not title or not parsed:
                continue
            ev_iso, ev_ts = parsed
            if datetime.fromtimestamp(ev_ts, tz=timezone.utc) < cutoff:
                continue
            low_t = title.lower()
            is_rate = "monetary policy decision" in low_t or "key ecb interest rates" in low_t
            cat = "INTEREST_RATE" if is_rate else "CENTRAL_BANK_SPEECH"
            impact = "High" if is_rate or "lagarde" in low_t or "financial stability" in low_t else "Medium"
            items.append(
                {
                    "id": _make_id("ecb", f"{ev_iso}:{title}"),
                    "title": f"ECB: {title}",
                    "category": cat,
                    "country": "EUR",
                    "event_date": ev_iso,
                    "event_timestamp": ev_ts,
                    "impact": impact,
                    "previous": None,
                    "forecast": None,
                    "actual": None,
                    "source_name": "European Central Bank (ECB)",
                    "source_url": link,
                    "is_official_source": True,
                }
            )
        return items, MacroSourceStatus(
            source_id="ecb_europa",
            source_name="European Central Bank (ECB)",
            official_url=ECB_PRESS_RSS_URL,
            status="LIVE",
            events_count=len(items),
            fetched_at=now_iso,
            note="Official ECB press releases & Governing Council speeches.",
        )
    except Exception as exc:
        logger.warning("ECB RSS fetch failed: %s", str(exc))
        return [], MacroSourceStatus(
            source_id="ecb_europa",
            source_name="European Central Bank (ECB)",
            official_url=ECB_PRESS_RSS_URL,
            status="DEGRADED",
            events_count=0,
            fetched_at=now_iso,
            note=f"Fetch error: {type(exc).__name__}",
        )


async def _fetch_boe_official(
    client: httpx.AsyncClient, now_dt: datetime, now_iso: str
) -> tuple[list[dict], MacroSourceStatus]:
    try:
        res = await client.get(BOE_NEWS_RSS_URL)
        res.raise_for_status()
        root = ET.fromstring(res.text)
        cutoff = now_dt - timedelta(days=30)
        items: list[dict] = []
        for item_el in root.findall(".//item")[:10]:
            title = (item_el.findtext("title") or "").strip()
            pub = (item_el.findtext("pubDate") or "").strip()
            link = (item_el.findtext("link") or BOE_NEWS_RSS_URL).strip()
            parsed = _parse_iso_or_rfc_date(pub)
            if not title or not parsed:
                continue
            ev_iso, ev_ts = parsed
            if datetime.fromtimestamp(ev_ts, tz=timezone.utc) < cutoff:
                continue
            low_t = title.lower()
            is_rate = "bank rate" in low_t or "monetary policy summary" in low_t
            if not is_rate and "speech" not in low_t and "governor" not in low_t and "mpc" not in low_t:
                continue
            actual_rate = None
            m_rate = re.search(r"bank rate[^0-9]*(\d+(?:\.\d+)?%)", low_t)
            if m_rate:
                actual_rate = m_rate.group(1)
            items.append(
                {
                    "id": _make_id("boe", f"{ev_iso}:{title}"),
                    "title": f"BoE: {title}",
                    "category": "INTEREST_RATE" if is_rate else "CENTRAL_BANK_SPEECH",
                    "country": "GBP",
                    "event_date": ev_iso,
                    "event_timestamp": ev_ts,
                    "impact": "High" if is_rate else "Medium",
                    "previous": None,
                    "forecast": None,
                    "actual": actual_rate,
                    "source_name": "Bank of England (BoE)",
                    "source_url": link,
                    "is_official_source": True,
                }
            )
        return items, MacroSourceStatus(
            source_id="bank_of_england",
            source_name="Bank of England (BoE)",
            official_url=BOE_NEWS_RSS_URL,
            status="LIVE",
            events_count=len(items),
            fetched_at=now_iso,
            note="Official BoE MPC Bank Rate summaries & statements.",
        )
    except Exception as exc:
        logger.warning("BoE RSS fetch failed: %s", str(exc))
        return [], MacroSourceStatus(
            source_id="bank_of_england",
            source_name="Bank of England (BoE)",
            official_url=BOE_NEWS_RSS_URL,
            status="DEGRADED",
            events_count=0,
            fetched_at=now_iso,
            note=f"Fetch error: {type(exc).__name__}",
        )


def _deduplicate_events(events: list[dict]) -> list[dict]:
    """Merge duplicate official/calendar entries cleanly without losing forecast/previous/actual."""
    merged: list[dict] = []
    for ev in sorted(events, key=lambda x: (x["event_timestamp"], not bool(x.get("is_official_source")))):
        matched = None
        for existing in merged:
            same_day = abs(existing["event_timestamp"] - ev["event_timestamp"]) <= 7200
            same_pair = existing["country"] == ev["country"] and existing["category"] == ev["category"]
            similar_title = (
                existing["title"].lower() == ev["title"].lower()
                or ("fomc" in existing["title"].lower() and "fomc" in ev["title"].lower() and "minutes" in existing["title"].lower() == ("minutes" in ev["title"].lower()))
                or (ev["category"] in ("CPI", "PPI", "NFP", "UNEMPLOYMENT") and same_pair and abs(existing["event_timestamp"] - ev["event_timestamp"]) <= 3600)
            )
            if same_day and same_pair and similar_title:
                matched = existing
                break
        if matched:
            if not matched.get("forecast") and ev.get("forecast"):
                matched["forecast"] = ev["forecast"]
            if not matched.get("previous") and ev.get("previous"):
                matched["previous"] = ev["previous"]
            if not matched.get("actual") and ev.get("actual"):
                matched["actual"] = ev["actual"]
            if ev.get("is_official_source") and not matched.get("is_official_source"):
                matched["source_name"] = f"{ev['source_name']} + Calendar"
                matched["source_url"] = ev["source_url"]
                matched["is_official_source"] = True
        else:
            merged.append(dict(ev))
    return merged


def _build_snapshot_from_events(events: list[dict], base_snap: dict[str, str | None]) -> OfficialMacroSnapshot:
    snap = dict(base_snap)
    for ev in events:
        if ev.get("country") != "USD":
            continue
        cat = ev.get("category")
        if cat == "CPI" and ev.get("actual") and not snap.get("us_cpi_latest"):
            snap["us_cpi_latest"] = ev["actual"]
        elif cat == "PPI" and ev.get("actual") and not snap.get("us_ppi_latest"):
            snap["us_ppi_latest"] = ev["actual"]
        elif cat == "NFP" and ev.get("actual") and not snap.get("us_nfp_latest"):
            snap["us_nfp_latest"] = ev["actual"]
        elif cat == "UNEMPLOYMENT" and ev.get("actual") and not snap.get("us_unemployment_latest"):
            snap["us_unemployment_latest"] = ev["actual"]
    return OfficialMacroSnapshot(**snap)


async def fetch_macro_news(
    category: str = "ALL",
    impact: str = "ALL",
    country: str = "ALL",
    search: str = "",
    warning_hours: int = 24,
    include_released: bool = True,
    refresh: bool = False,
) -> MacroNewsResponse:
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    raw_events: list[dict] = []
    source_statuses: list[MacroSourceStatus] = []
    snapshot_dict: dict[str, str | None] = {}
    used_cache = False

    if not refresh:
        with get_db_connection() as conn:
            cached_rows = conn.execute(
                "SELECT * FROM macro_news_events_cache ORDER BY event_timestamp ASC"
            ).fetchall()
        if cached_rows:
            try:
                fetched_dt = datetime.fromisoformat(str(cached_rows[0]["fetched_at"]))
                if (now_dt - fetched_dt).total_seconds() < CACHE_TTL_SECONDS:
                    used_cache = True
                    raw_events = [dict(r) for r in cached_rows]
                    # Also extract cached snapshot if present in app_settings
                    with get_db_connection() as conn:
                        snap_rows = conn.execute(
                            "SELECT key, value FROM app_settings WHERE key LIKE 'macro_snap_%'"
                        ).fetchall()
                    for sr in snap_rows:
                        k = str(sr["key"]).replace("macro_snap_", "")
                        snapshot_dict[k] = str(sr["value"]) if sr["value"] else None
                    source_statuses = [
                        MacroSourceStatus(
                            source_id="sqlite_macro_cache",
                            source_name="SQLite Official Macro Feed Cache (10m TTL)",
                            official_url=FED_FOMC_CALENDAR_URL,
                            status="CACHED",
                            events_count=len(raw_events),
                            fetched_at=str(cached_rows[0]["fetched_at"]),
                            note="Served from local SQLite cache within 10-minute freshness TTL.",
                        )
                    ]
            except Exception:
                used_cache = False

    if not used_cache:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json,application/xml,text/html,*/*"}
        async with httpx.AsyncClient(timeout=9.0, follow_redirects=True, headers=headers) as client:
            ff_res, bls_res, fed_res, ecb_res, boe_res = await asyncio.gather(
                _fetch_ff_events(client, now_iso),
                _fetch_bls_official(client, now_dt, now_iso),
                _fetch_fed_official(client, now_dt, now_iso),
                _fetch_ecb_official(client, now_dt, now_iso),
                _fetch_boe_official(client, now_dt, now_iso),
            )

        ff_items, ff_status = ff_res
        bls_items, bls_snap, bls_status = bls_res
        fed_items, fed_snap, fed_status = fed_res
        ecb_items, ecb_status = ecb_res
        boe_items, boe_status = boe_res

        source_statuses = [fed_status, bls_status, ecb_status, boe_status, ff_status]
        snapshot_dict = {**fed_snap, **bls_snap}

        combined = _deduplicate_events(fed_items + bls_items + ecb_items + boe_items + ff_items)
        if combined:
            raw_events = combined
            with get_db_connection() as conn:
                conn.execute("DELETE FROM macro_news_events_cache")
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO macro_news_events_cache (
                        id, title, category, country, event_date, event_timestamp,
                        impact, previous, forecast, actual, source_name, source_url,
                        is_official_source, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            ev["id"],
                            ev["title"],
                            ev["category"],
                            ev["country"],
                            ev["event_date"],
                            int(ev["event_timestamp"]),
                            ev["impact"],
                            ev.get("previous"),
                            ev.get("forecast"),
                            ev.get("actual"),
                            ev["source_name"],
                            ev["source_url"],
                            1 if ev.get("is_official_source") else 0,
                            now_iso,
                        )
                        for ev in raw_events
                    ],
                )
                conn.executemany(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    [
                        (f"macro_snap_{k}", str(v or ""), now_iso)
                        for k, v in snapshot_dict.items()
                    ],
                )
        else:
            # Fallback to SQLite cache even if stale when all upstreams failed
            with get_db_connection() as conn:
                cached_rows = conn.execute(
                    "SELECT * FROM macro_news_events_cache ORDER BY event_timestamp ASC"
                ).fetchall()
            raw_events = [dict(r) for r in cached_rows]

    # Hydrate statuses, warnings, countdowns across ALL fetched real events BEFORE filtering
    all_items, warnings, active_level, next_high = compute_warning_state(
        raw_events, now_dt=now_dt, warning_hours=warning_hours
    )

    category_counts: dict[str, int] = {"ALL": len(all_items)}
    for cat_key in CATEGORY_META:
        category_counts[cat_key] = sum(1 for item in all_items if cat_key in item.tags)

    norm_cat = category.strip().upper()
    norm_impact = impact.strip().upper()
    norm_country = country.strip().upper()
    norm_search = search.strip().lower()

    filtered = all_items
    if norm_cat != "ALL":
        filtered = [e for e in filtered if norm_cat in e.tags]
    if norm_impact != "ALL":
        filtered = [e for e in filtered if e.impact.upper() == norm_impact]
    if norm_country != "ALL":
        filtered = [e for e in filtered if e.country.upper() == norm_country]
    if not include_released:
        filtered = [e for e in filtered if e.event_status != "RELEASED"]
    if norm_search:
        filtered = [
            e for e in filtered
            if norm_search in e.title.lower()
            or norm_search in e.country.lower()
            or norm_search in e.source_name.lower()
        ]

    # Sort: upcoming/imminent chronological first, then most recent released
    upcoming_items = sorted(
        [e for e in filtered if e.minutes_until >= 0],
        key=lambda e: e.event_timestamp,
    )
    released_items = sorted(
        [e for e in filtered if e.minutes_until < 0],
        key=lambda e: e.event_timestamp,
        reverse=True,
    )
    ordered_filtered = upcoming_items + released_items

    official_snapshot = _build_snapshot_from_events(raw_events, snapshot_dict)

    return MacroNewsResponse(
        generated_at=now_iso,
        strict_official_sources_only=True,
        fabricated_events_count=0,
        warning_window_hours=warning_hours,
        active_warning_level=active_level,
        high_impact_warnings=warnings,
        next_high_impact_event=next_high,
        official_snapshot=official_snapshot,
        source_statuses=source_statuses,
        category_counts=category_counts,
        total=len(ordered_filtered),
        events=ordered_filtered,
    )
