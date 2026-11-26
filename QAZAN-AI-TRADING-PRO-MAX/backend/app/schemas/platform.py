from pydantic import BaseModel, Field


class Ticker24h(BaseModel):
    symbol: str
    last_price: float
    price_change_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    quote_volume_24h: float
    bid_price: float
    ask_price: float
    spread_pct: float


class MarketTickersResponse(BaseModel):
    source: str
    fetched_at: str
    tickers: list[Ticker24h]


class IndicatorPoint(BaseModel):
    time: int
    value: float


class StructureSwingPoint(BaseModel):
    time: int
    price: float
    kind: str  # HIGH | LOW
    label: str  # HH | HL | LH | LL


class StructureEvent(BaseModel):
    time: int
    price: float
    event_type: str  # BOS | CHoCH
    direction: str  # BULLISH | BEARISH


class MarketStructureResponse(BaseModel):
    symbol: str
    interval: str
    regime: str  # UPTREND | DOWNTREND | RANGING
    last_close: float
    atr_14: float
    rsi_14: float
    ema_20_last: float
    ema_50_last: float
    ema_20_series: list[IndicatorPoint]
    ema_50_series: list[IndicatorPoint]
    swings: list[StructureSwingPoint]
    events: list[StructureEvent]
    analyzed_at: str


class LiquidityLevel(BaseModel):
    price: float
    side: str  # BSL | SSL
    touches: int
    first_time: int
    last_time: int
    distance_pct: float


class LiquiditySweep(BaseModel):
    time: int
    side: str  # BSL_SWEEP | SSL_SWEEP
    swept_level: float
    wick_extreme: float
    close_price: float


class VolumeNode(BaseModel):
    price_low: float
    price_high: float
    price_mid: float
    volume: float
    share_pct: float
    is_poc: bool


class LiquidityAnalysisResponse(BaseModel):
    symbol: str
    interval: str
    last_close: float
    poc_price: float
    buy_side_pools: list[LiquidityLevel]
    sell_side_pools: list[LiquidityLevel]
    recent_sweeps: list[LiquiditySweep]
    volume_profile: list[VolumeNode]
    analyzed_at: str


class FairValueGap(BaseModel):
    time: int
    direction: str  # BULLISH | BEARISH
    top: float
    bottom: float
    mitigated: bool


class OrderBlock(BaseModel):
    time: int
    direction: str  # BULLISH | BEARISH
    high: float
    low: float
    mitigated: bool


class DealingRange(BaseModel):
    range_high: float
    range_low: float
    equilibrium: float
    current_zone: str  # PREMIUM | DISCOUNT | EQUILIBRIUM
    position_pct: float


class SMCAnalysisResponse(BaseModel):
    symbol: str
    interval: str
    last_close: float
    dealing_range: DealingRange
    fair_value_gaps: list[FairValueGap]
    order_blocks: list[OrderBlock]
    analyzed_at: str


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class AIAnalysisResponse(BaseModel):
    symbol: str
    interval: str
    sample_size: int
    train_size: int
    test_size: int
    signal: str  # BULLISH | BEARISH
    confidence_pct: float
    prob_bullish: float
    prob_bearish: float
    rf_test_accuracy_pct: float
    xgb_test_accuracy_pct: float
    ensemble_test_accuracy_pct: float
    rsi_14: float
    macd_hist: float
    atr_pct: float
    top_features: list[FeatureImportance]
    analyzed_at: str


class CandlePredictionResponse(BaseModel):
    symbol: str
    interval: str
    current_close: float
    predicted_close: float
    predicted_high: float
    predicted_low: float
    expected_move_pct: float
    predicted_direction: str  # BULLISH | BEARISH
    xgb_val_mae_pct: float
    gbr_val_rmse_pct: float
    sample_size: int
    analyzed_at: str


class ScannerItem(BaseModel):
    symbol: str
    last_price: float
    rsi_14: float
    ema_trend: str  # BULLISH | BEARISH
    structure_regime: str
    volume_ratio: float
    signal: str  # LONG | SHORT | NEUTRAL
    suggested_entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    score: int


class TradeScannerResponse(BaseModel):
    interval: str
    scanned_at: str
    items: list[ScannerItem]


class RiskCalculateRequest(BaseModel):
    account_balance: float = Field(..., gt=0)
    risk_pct: float = Field(..., gt=0, le=50)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    take_profit: float = Field(..., gt=0)
    leverage: float = Field(default=1.0, ge=1.0, le=50.0)


class RiskCalculateResponse(BaseModel):
    direction: str  # LONG | SHORT
    risk_amount_usdt: float
    reward_amount_usdt: float
    risk_reward_ratio: float
    position_size_units: float
    position_notional_usdt: float
    required_margin_usdt: float
    stop_distance_pct: float
    est_liquidation_price: float
    kelly_fraction_pct: float


class RiskProfilePayload(BaseModel):
    account_balance: float = Field(..., gt=0)
    risk_pct: float = Field(..., gt=0, le=20)
    default_rr: float = Field(..., ge=0.5, le=20)
    max_leverage: float = Field(..., ge=1, le=50)
    max_daily_loss_pct: float = Field(..., gt=0, le=50)


class BacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    interval: str = Field(default="1h")
    strategy: str = Field(default="EMA_CROSS")  # EMA_CROSS | RSI_REVERSION | BOS_MOMENTUM
    initial_capital: float = Field(default=10000.0, gt=0)
    fee_pct: float = Field(default=0.1, ge=0, le=1.0)
    stop_loss_pct: float = Field(default=2.0, gt=0.1, le=25.0)
    take_profit_pct: float = Field(default=4.0, gt=0.1, le=50.0)


class BacktestTrade(BaseModel):
    entry_time: int
    exit_time: int
    side: str
    entry_price: float
    exit_price: float
    pnl_usdt: float
    return_pct: float
    exit_reason: str


class EquityPoint(BaseModel):
    time: int
    value: float


class BacktestResponse(BaseModel):
    symbol: str
    interval: str
    strategy: str
    candle_count: int
    initial_capital: float
    final_equity: float
    total_return_pct: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    equity_curve: list[EquityPoint]
    trades: list[BacktestTrade]
    executed_at: str


class BacktestHistoryItem(BaseModel):
    id: int
    symbol: str
    interval: str
    strategy: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    total_trades: int
    sharpe_ratio: float
    created_at: str


class PaperOrderRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    side: str = Field(..., pattern="^(LONG|SHORT)$")
    notional_usdt: float = Field(..., gt=10.0, le=1000000.0)
    leverage: float = Field(default=1.0, ge=1.0, le=20.0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    fee_pct: float = Field(default=0.06, ge=0.0, le=1.0)
    slippage_pct: float = Field(default=0.03, ge=0.0, le=1.0)


class PaperResetRequest(BaseModel):
    initial_balance: float = Field(default=10000.0, ge=100.0, le=10000000.0)


class PaperPositionView(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    leverage: float
    status: str
    unrealized_pnl: float
    unrealized_roe_pct: float
    realized_pnl: float | None = None
    exit_price: float | None = None
    entry_fee_usdt: float = 0.0
    exit_fee_usdt: float = 0.0
    slippage_cost_usdt: float = 0.0
    close_reason: str | None = None
    opened_at: str
    closed_at: str | None = None


class PaperStateResponse(BaseModel):
    balance_usdt: float
    initial_balance: float
    total_equity_usdt: float
    unrealized_pnl_usdt: float
    realized_pnl_usdt: float
    is_virtual: bool = True
    virtual_currency: str = "VIRTUAL USDT"
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_usdt: float = 0.0
    total_closed_trades: int = 0
    total_fees_paid_usdt: float = 0.0
    auto_triggered_closes: int = 0
    open_positions: list[PaperPositionView]
    closed_trades: list[PaperPositionView]
    updated_at: str


class EconomicEventItem(BaseModel):
    id: str
    title: str
    country: str
    event_date: str
    impact: str
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class EconomicCalendarResponse(BaseModel):
    source: str
    cached_fallback: bool
    fetched_at: str
    total: int
    events: list[EconomicEventItem]


class AppSettingsPayload(BaseModel):
    default_symbol: str = Field(default="BTCUSDT")
    default_interval: str = Field(default="1h")
    default_risk_pct: float = Field(default=1.0, gt=0, le=20)
    language: str = Field(default="ar", pattern="^(ar|en)$")
    theme: str = Field(default="dark", pattern="^(dark|light)$")


class DashboardSummaryResponse(BaseModel):
    active_symbol: str
    active_interval: str
    tickers: list[Ticker24h]
    paper_balance_usdt: float
    paper_equity_usdt: float
    open_positions_count: int
    realized_pnl_usdt: float
    quick_structure_regime: str
    quick_rsi_14: float
    quick_ai_signal: str
    quick_ai_confidence_pct: float
    system_status: str
    generated_at: str


class NextCandleProbabilities(BaseModel):
    up_pct: float
    down_pct: float
    sideways_pct: float
    dominant_outcome: str  # UP | DOWN | SIDEWAYS


class EstimatedPriceRange(BaseModel):
    reference_close: float
    lower_bound: float
    upper_bound: float
    central_band_low: float
    central_band_high: float
    atr_14: float
    sideways_threshold_pct: float
    estimated_range_width_pct: float
    note: str


class WalkForwardValidationMetrics(BaseModel):
    folds: int
    evaluated_bars: int
    model_brier_score: float
    baseline_brier_score: float
    brier_skill_vs_baseline_pct: float
    model_log_loss: float
    baseline_log_loss: float
    log_loss_skill_vs_baseline_pct: float
    model_accuracy_pct: float
    baseline_accuracy_pct: float
    outperforms_baseline: bool


class CandleProbabilityFactor(BaseModel):
    domain: str  # OHLCV | RSI | ATR | VOLUME | VWAP | MARKET_STRUCTURE | LIQUIDITY | FVG | TREND
    feature: str
    current_value: float
    direction_effect: str  # UP | DOWN | SIDEWAYS | NEUTRAL
    weight_pct: float
    explanation: str


class FeatureSnapshotSummary(BaseModel):
    close: float
    rsi_14: float
    atr_14: float
    atr_pct: float
    volume_ratio_20: float
    vwap: float
    vwap_distance_atr: float
    structure_bias: str
    liquidity_bias: str
    fvg_context: str
    trend_regime: str


class CandleProbabilityResponse(BaseModel):
    run_id: int | None = None
    symbol: str
    interval: str
    status: str  # OK | INSUFFICIENT_DATA
    insufficient_reason: str | None = None
    closed_bars_analyzed: int
    minimum_required_bars: int
    unclosed_bar_excluded: bool
    look_ahead_bias_prevented: bool = True
    is_guarantee: bool = False
    disclaimer: str
    probabilities: NextCandleProbabilities | None = None
    estimated_range: EstimatedPriceRange | None = None
    confidence_pct: float | None = None
    confidence_level: str | None = None  # LOW | MODERATE | HIGH
    walk_forward_metrics: WalkForwardValidationMetrics | None = None
    driving_factors: list[CandleProbabilityFactor] = []
    feature_snapshot: FeatureSnapshotSummary | None = None
    analyzed_at: str


class ProbabilityForecastHistoryItem(BaseModel):
    id: int
    symbol: str
    interval: str
    status: str
    prob_up: float | None = None
    prob_down: float | None = None
    prob_sideways: float | None = None
    confidence_pct: float | None = None
    model_brier_score: float | None = None
    baseline_brier_score: float | None = None
    model_log_loss: float | None = None
    baseline_log_loss: float | None = None
    created_at: str

