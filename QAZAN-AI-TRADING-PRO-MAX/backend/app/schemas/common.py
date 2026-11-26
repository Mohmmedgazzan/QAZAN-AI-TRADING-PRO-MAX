from pydantic import BaseModel, Field


class MLPackageStatus(BaseModel):
    name: str
    installed: bool
    version: str | None = None


class DatabaseHealth(BaseModel):
    connected: bool
    sqlite_version: str
    database_path: str
    latency_ms: float
    tables: list[str]
    counts: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    python_version: str
    timestamp: str
    database: DatabaseHealth
    ml_runtime: list[MLPackageStatus]


class CandlePoint(BaseModel):
    time: int = Field(..., description="Unix timestamp in seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSummary(BaseModel):
    last_close: float
    period_open: float
    period_change_pct: float
    period_high: float
    period_low: float
    total_volume: float
    vwap: float


class MarketKlinesResponse(BaseModel):
    symbol: str
    interval: str
    source: str
    cached_fallback: bool
    fetched_at: str
    candle_count: int
    summary: MarketSummary
    candles: list[CandlePoint]


class SystemLogEntry(BaseModel):
    id: int
    created_at: str
    level: str
    logger_name: str
    message: str
    source: str
    request_id: str | None = None


class SystemLogsResponse(BaseModel):
    total: int
    logs: list[SystemLogEntry]


class ClientLogRequest(BaseModel):
    level: str = Field(default="ERROR", pattern="^(WARNING|ERROR|CRITICAL)$")
    message: str = Field(..., min_length=1, max_length=2000)
    context: str | None = Field(default=None, max_length=500)
