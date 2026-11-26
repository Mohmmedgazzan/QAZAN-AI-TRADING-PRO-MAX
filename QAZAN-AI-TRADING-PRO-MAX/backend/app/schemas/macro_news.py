from pydantic import BaseModel


class MacroEventItem(BaseModel):
    id: str
    title: str
    category: str  # INTEREST_RATE | FED_DECISION | CPI | PPI | NFP | UNEMPLOYMENT | CENTRAL_BANK_SPEECH | OTHER_MACRO
    tags: list[str] = []
    category_label_ar: str
    category_label_en: str
    country: str
    event_date: str
    event_timestamp: int
    impact: str  # High | Medium | Low
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None
    source_name: str
    source_url: str
    is_official_source: bool
    event_status: str  # IMMINENT | UPCOMING | RELEASED
    minutes_until: int
    warning_active: bool
    warning_severity: str  # CRITICAL | ELEVATED | WATCH | NONE


class HighImpactWarningItem(BaseModel):
    event_id: str
    title: str
    category: str
    country: str
    event_date: str
    minutes_until: int
    severity: str  # CRITICAL | ELEVATED | WATCH
    source_name: str
    warning_text_ar: str
    warning_text_en: str


class MacroSourceStatus(BaseModel):
    source_id: str
    source_name: str
    official_url: str
    status: str  # LIVE | CACHED | DEGRADED
    events_count: int
    fetched_at: str
    note: str | None = None


class OfficialMacroSnapshot(BaseModel):
    fed_target_rate: str | None = None
    fed_rate_date: str | None = None
    fed_rate_url: str | None = None
    next_fomc_date: str | None = None
    us_cpi_latest: str | None = None
    us_cpi_previous: str | None = None
    us_cpi_next_date: str | None = None
    us_ppi_latest: str | None = None
    us_ppi_previous: str | None = None
    us_ppi_next_date: str | None = None
    us_nfp_latest: str | None = None
    us_nfp_previous: str | None = None
    us_nfp_next_date: str | None = None
    us_unemployment_latest: str | None = None
    us_unemployment_previous: str | None = None


class MacroNewsResponse(BaseModel):
    generated_at: str
    strict_official_sources_only: bool = True
    fabricated_events_count: int = 0
    warning_window_hours: int
    active_warning_level: str  # CRITICAL | ELEVATED | WATCH | CLEAR
    high_impact_warnings: list[HighImpactWarningItem]
    next_high_impact_event: MacroEventItem | None = None
    official_snapshot: OfficialMacroSnapshot
    source_statuses: list[MacroSourceStatus]
    category_counts: dict[str, int]
    total: int
    events: list[MacroEventItem]
