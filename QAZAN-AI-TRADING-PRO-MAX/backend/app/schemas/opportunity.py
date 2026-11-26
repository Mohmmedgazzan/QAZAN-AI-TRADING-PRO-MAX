from typing import Any, Literal
from pydantic import BaseModel, Field


DecisionType = Literal["LONG", "SHORT", "NO_TRADE"]


class HypothesisCheckItem(BaseModel):
    criterion: str
    passed: bool
    detail: str
    evidence_value: str | None = None


class HypothesisEvaluation(BaseModel):
    side: Literal["LONG", "SHORT"]
    eligible: bool
    passed_count: int
    total_count: int
    score_pct: float
    checks: list[HypothesisCheckItem]
    invalidation_price: float | None = None
    invalidation_reason: str
    proposed_entry_zone_low: float | None = None
    proposed_entry_zone_high: float | None = None
    proposed_entry: float | None = None
    proposed_stop_loss: float | None = None
    proposed_tp1: float | None = None
    proposed_tp2: float | None = None
    proposed_tp3: float | None = None


class RiskGovernanceReport(BaseModel):
    account_balance_usdt: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    daily_realized_loss_pct: float
    daily_unrealized_loss_pct: float
    daily_total_loss_pct: float
    daily_remaining_risk_pct: float
    daily_limit_breached: bool
    fee_pct_per_side: float
    slippage_pct_per_side: float
    estimated_fee_usdt: float
    estimated_slippage_usdt: float
    total_friction_usdt: float
    gross_rr_tp1: float | None = None
    gross_rr_tp2: float | None = None
    gross_rr_tp3: float | None = None
    net_rr_tp1: float | None = None
    net_rr_tp2: float | None = None
    net_rr_tp3: float | None = None
    risk_amount_usdt: float | None = None
    position_size_units: float | None = None
    position_notional_usdt: float | None = None
    required_margin_usdt: float | None = None
    leverage_used: float
    confirmation_gate_passed: bool
    duplicate_suppressed: bool
    duplicate_fingerprint: str | None = None
    rejection_reasons: list[str]


class TradeOpportunityRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=4, max_length=20)
    htf_timeframe: str = Field(default="4h")
    ltf_timeframe: str = Field(default="1h")
    account_balance: float | None = Field(default=None, gt=0)
    risk_pct: float = Field(default=1.0, gt=0.05, le=10.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0.1, le=20.0)
    fee_pct: float = Field(default=0.06, ge=0.0, le=1.0)
    slippage_pct: float = Field(default=0.04, ge=0.0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=50.0)
    min_net_rr: float = Field(default=1.5, ge=0.5, le=10.0)
    simulate_daily_loss_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    allow_duplicate: bool = Field(default=False)
    persist: bool = Field(default=True)


class TradeOpportunityResponse(BaseModel):
    opportunity_id: int | None = None
    symbol: str
    htf_timeframe: str
    ltf_timeframe: str
    decision: DecisionType
    live_execution_blocked: bool = True
    execution_mode: str = "ANALYSIS_ONLY_NO_LIVE_ORDERS"
    last_price: float
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    invalidation_level: float | None = None
    invalidation_rule: str
    risk_reward_summary: str
    long_hypothesis: HypothesisEvaluation
    short_hypothesis: HypothesisEvaluation
    risk_governance: RiskGovernanceReport
    market_context: dict[str, Any]
    candle_time: int
    analyzed_at: str


class TradeOpportunityScanResponse(BaseModel):
    htf_timeframe: str
    ltf_timeframe: str
    risk_pct: float
    max_daily_loss_pct: float
    daily_limit_breached: bool
    scanned_at: str
    live_execution_blocked: bool = True
    items: list[TradeOpportunityResponse]


class TradeOpportunityHistoryItem(BaseModel):
    id: int
    fingerprint: str
    symbol: str
    timeframe: str
    ltf_timeframe: str
    decision: DecisionType
    long_passed: int
    short_passed: int
    entry_price: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    net_rr: float | None = None
    position_size_units: float | None = None
    daily_loss_used_pct: float
    daily_limit_breached: bool
    is_duplicate: bool
    invalidation_reason: str | None = None
    created_at: str
