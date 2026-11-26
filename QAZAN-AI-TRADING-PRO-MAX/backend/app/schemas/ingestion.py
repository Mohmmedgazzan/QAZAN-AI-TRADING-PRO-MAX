from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.common import CandlePoint, MarketSummary


MetricStatus = Literal["LIVE", "CACHED", "MISSING"]


class TrackedSymbolItem(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    source: str
    is_default: bool
    added_at: str


class TrackedSymbolsResponse(BaseModel):
    total: int
    symbols: list[TrackedSymbolItem]


class AddSymbolRequest(BaseModel):
    symbol: str = Field(..., min_length=4, max_length=20)


class ProvenanceMetric(BaseModel):
    metric: str
    status: MetricStatus
    value: float | None = None
    secondary_value: float | None = None
    secondary_label: str | None = None
    unit: str | None = None
    source: str
    updated_at: str | None = None
    cache_age_sec: float | None = None
    note: str | None = None


class LiquidationEventItem(BaseModel):
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    notional_usd: float
    event_time: int
    received_at: str
    source: str


class DataValidationReport(BaseModel):
    symbol: str
    interval: str
    status: Literal["VALID", "DEGRADED", "INVALID"]
    candles_checked: int
    invalid_bars: int
    duplicate_timestamps: int
    out_of_order_timestamps: int
    missing_candle_gaps: int
    missing_candles_estimated: int
    gap_timestamps: list[int]
    stale_seconds: float | None = None
    is_stale: bool
    missing_fields: list[str]
    integrity_score_pct: float
    issues: list[str]
    validated_at: str


class RateLimitTelemetry(BaseModel):
    total_requests: int
    retries_executed: int
    rate_limit_hits: int
    last_binance_used_weight_1m: int | None = None
    last_retry_after_sec: float | None = None
    cooldown_active: bool
    cooldown_remaining_sec: float
    last_error: str | None = None
    last_success_at: str | None = None


class ConnectedEngineContext(BaseModel):
    technical_bias: str | None = None
    technical_regime: str | None = None
    technical_phase: str | None = None
    htf_alignment_score: float | None = None
    probability_status: str | None = None
    prob_up_pct: float | None = None
    prob_down_pct: float | None = None
    prob_sideways_pct: float | None = None
    prob_confidence_pct: float | None = None
    engine_note: str | None = None


class WebSocketStreamStatus(BaseModel):
    spot_connected: bool
    futures_liquidations_connected: bool
    active_clients: int
    spot_messages_received: int
    liquidation_events_captured: int
    last_spot_tick_at: str | None = None
    last_liquidation_at: str | None = None


class MarketIntelligenceResponse(BaseModel):
    symbol: str
    interval: str
    generated_at: str
    ohlcv_source: str
    ohlcv_updated_at: str | None = None
    ohlcv_cached_fallback: bool
    ohlcv_summary: MarketSummary | None = None
    candles_preview: list[CandlePoint] = []
    volume_24h: ProvenanceMetric
    open_interest: ProvenanceMetric
    funding_rate: ProvenanceMetric
    liquidations: ProvenanceMetric
    cvd: ProvenanceMetric
    btc_dominance: ProvenanceMetric
    recent_liquidations: list[LiquidationEventItem] = []
    validation: DataValidationReport
    rate_limit: RateLimitTelemetry
    ws_status: WebSocketStreamStatus
    connected_engine: ConnectedEngineContext
