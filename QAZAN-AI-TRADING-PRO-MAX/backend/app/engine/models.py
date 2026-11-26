from pydantic import BaseModel, Field


class EngineSwingPoint(BaseModel):
    pivot_index: int
    pivot_time: int
    confirmed_index: int
    confirmed_time: int
    price: float
    kind: str  # SWING_HIGH | SWING_LOW
    label: str  # HH | HL | LH | LL
    scope: str  # EXTERNAL | INTERNAL
    swept: bool
    broken: bool


class PremiumDiscountZone(BaseModel):
    range_high: float
    range_low: float
    equilibrium: float
    ote_low: float
    ote_high: float
    position_pct: float
    zone: str  # PREMIUM | DISCOUNT | EQUILIBRIUM


class LiquidityPoolNode(BaseModel):
    price: float
    side: str  # BSL | SSL
    scope: str  # EXTERNAL | INTERNAL
    touches: int
    pool_type: str  # SWING_LEVEL | EQH | EQL | FVG_CE
    first_time: int
    confirmed_time: int
    distance_pct: float
    swept: bool


class EqualLevelCluster(BaseModel):
    kind: str  # EQH | EQL
    avg_price: float
    touches: int
    first_time: int
    confirmed_time: int
    tolerance: float
    swept: bool


class CausalLiquiditySweep(BaseModel):
    time: int
    side: str  # BSL_SWEEP | SSL_SWEEP
    scope: str  # EXTERNAL | INTERNAL
    swept_level: float
    wick_extreme: float
    close_price: float
    wick_ratio: float


class LevelBreachEvent(BaseModel):
    breach_time: int
    confirmed_time: int
    level_price: float
    side: str  # BULLISH | BEARISH
    classification: str  # BREAKOUT | FAKEOUT | STOP_HUNT
    structure_tag: str | None = None  # BOS | CHoCH | None
    breach_close: float
    confirmation_close: float
    displacement_atr: float
    reason: str


class PendingBreakoutState(BaseModel):
    breach_time: int
    level_price: float
    side: str  # BULLISH | BEARISH
    breach_close: float
    bars_waited: int
    status: str = "PENDING_CONFIRMATION"


class CausalStructureEvent(BaseModel):
    breach_time: int
    confirmed_time: int
    level_price: float
    event_type: str  # BOS | CHoCH
    direction: str  # BULLISH | BEARISH
    confirmation_close: float


class SupplyDemandZone(BaseModel):
    zone_type: str  # SUPPLY | DEMAND
    pattern: str  # RBD | DBD | DBR | RBR
    top: float
    bottom: float
    formed_time: int
    confirmed_time: int
    displacement_atr: float
    status: str  # FRESH | TESTED | BROKEN
    touches: int


class CausalOrderBlock(BaseModel):
    direction: str  # BULLISH | BEARISH
    high: float
    low: float
    mean_threshold: float
    formed_time: int
    confirmed_time: int
    status: str  # ACTIVE | MITIGATED | INVALIDATED


class BreakerBlock(BaseModel):
    direction: str  # BULLISH_BREAKER | BEARISH_BREAKER
    high: float
    low: float
    origin_ob_time: int
    flipped_time: int
    status: str  # ACTIVE | MITIGATED | INVALIDATED


class CausalFairValueGap(BaseModel):
    direction: str  # BULLISH | BEARISH
    top: float
    bottom: float
    ce_midpoint: float
    formed_time: int
    confirmed_time: int
    status: str  # UNMITIGATED | PARTIALLY_FILLED | MITIGATED


class SingleTimeframeAnalysis(BaseModel):
    timeframe: str
    closed_bars_analyzed: int
    unclosed_bar_excluded: bool
    last_closed_time: int
    last_close: float
    atr_14: float
    adx_14: float
    rsi_14: float
    market_bias: str  # BULLISH | BEARISH | NEUTRAL
    market_regime: str  # TRENDING_EXPANSION | RANGING_COMPRESSION | VOLATILE_CHOP | TRANSITIONAL
    market_phase: str  # TREND | RANGE | CORRECTION
    premium_discount: PremiumDiscountZone
    swing_highs: list[EngineSwingPoint]
    swing_lows: list[EngineSwingPoint]
    hh_hl_lh_ll_sequence: list[EngineSwingPoint]
    external_liquidity: list[LiquidityPoolNode]
    internal_liquidity: list[LiquidityPoolNode]
    equal_highs_lows: list[EqualLevelCluster]
    liquidity_sweeps: list[CausalLiquiditySweep]
    structure_events: list[CausalStructureEvent]
    level_breaches: list[LevelBreachEvent]
    pending_breakout: PendingBreakoutState | None = None
    supply_demand_zones: list[SupplyDemandZone]
    order_blocks: list[CausalOrderBlock]
    breaker_blocks: list[BreakerBlock]
    fair_value_gaps: list[CausalFairValueGap]


class LTFConfirmationResult(BaseModel):
    timeframe: str
    htf_bias: str
    price_in_htf_poi: bool
    matched_poi_description: str | None = None
    ltf_structure_aligned: bool
    ltf_sweep_detected: bool
    setup_status: str  # CONFIRMED_LONG | CONFIRMED_SHORT | WAIT_CONFIRMATION | NO_SETUP
    rationale: str


class MultiTimeframeAnalysisResponse(BaseModel):
    run_id: int | None = None
    symbol: str
    primary_timeframes: list[str]
    ltf_timeframe: str
    look_ahead_bias_prevented: bool = True
    market_bias: str
    market_regime: str
    market_phase: str
    htf_alignment_score: float
    timeframes: dict[str, SingleTimeframeAnalysis]
    ltf_confirmation: LTFConfirmationResult
    analyzed_at: str


class CausalBacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    timeframe: str = Field(default="4h")
    lookback_bars: int = Field(default=320, ge=120, le=500)
    initial_capital: float = Field(default=10000.0, gt=0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0.1, le=10.0)
    fee_pct: float = Field(default=0.06, ge=0.0, le=1.0)
    rr_target: float = Field(default=2.0, ge=1.0, le=6.0)


class CausalBacktestTrade(BaseModel):
    entry_time: int
    exit_time: int
    setup_type: str  # BREAKOUT_CONTINUATION | STOP_HUNT_POI
    side: str  # LONG | SHORT
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    pnl_usdt: float
    return_pct: float
    exit_reason: str  # TP | SL | EOD


class CausalBacktestEquityPoint(BaseModel):
    time: int
    value: float


class CausalBacktestResponse(BaseModel):
    run_id: int | None = None
    symbol: str
    timeframe: str
    bars_tested: int
    look_ahead_bias_prevented: bool = True
    initial_capital: float
    final_equity: float
    total_return_pct: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    breakouts_confirmed: int
    fakeouts_filtered: int
    stop_hunts_detected: int
    trades: list[CausalBacktestTrade]
    equity_curve: list[CausalBacktestEquityPoint]
    executed_at: str


class TechnicalRunHistoryItem(BaseModel):
    id: int
    symbol: str
    run_type: str
    ltf_interval: str
    market_bias: str
    market_phase: str
    market_regime: str
    created_at: str
