from pydantic import BaseModel, Field

from app.schemas.platform import EquityPoint


class ProBacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=4, max_length=20)
    strategy: str = Field(default="EMA_CROSS")  # EMA_CROSS | RSI_REVERSION | BOS_MOMENTUM | SMC_CONFLUENCE
    primary_interval: str = Field(default="1h")
    timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h", "4h", "1d"])
    lookback_bars: int = Field(default=420, ge=140, le=500)
    initial_capital: float = Field(default=10000.0, gt=50.0, le=10000000.0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0.05, le=10.0)
    fee_pct: float = Field(default=0.06, ge=0.0, le=1.0)
    slippage_pct: float = Field(default=0.04, ge=0.0, le=1.0)
    stop_loss_pct: float = Field(default=2.0, gt=0.1, le=25.0)
    take_profit_pct: float = Field(default=4.0, gt=0.1, le=50.0)
    walk_forward_folds: int = Field(default=4, ge=2, le=6)
    min_trades_required: int = Field(default=8, ge=1, le=100)
    min_profit_factor: float = Field(default=1.15, ge=0.5, le=5.0)
    max_allowed_drawdown_pct: float = Field(default=25.0, gt=1.0, le=80.0)
    persist: bool = Field(default=True)


class LookAheadAudit(BaseModel):
    look_ahead_bias_prevented: bool = True
    unclosed_bar_excluded: bool = True
    execution_timing: str = "SIGNAL_ON_CLOSED_BAR_FILL_NEXT_OPEN"
    indicators_shifted_causally: bool = True
    intraday_sl_evaluated_before_tp: bool = True
    notes: str


class ProBacktestTrade(BaseModel):
    entry_time: int
    exit_time: int
    side: str
    timeframe: str
    signal_price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    qty: float
    gross_pnl_usdt: float
    fee_cost_usdt: float
    slippage_cost_usdt: float
    net_pnl_usdt: float
    return_pct: float
    r_multiple: float
    exit_reason: str


class WalkForwardFoldResult(BaseModel):
    fold_index: int
    is_bars: int
    oos_bars: int
    is_start_time: int
    is_end_time: int
    oos_start_time: int
    oos_end_time: int
    selected_sl_pct: float
    selected_tp_pct: float
    is_return_pct: float
    is_profit_factor: float
    is_trades: int
    oos_return_pct: float
    oos_win_rate_pct: float
    oos_profit_factor: float
    oos_expectancy_usdt: float
    oos_expectancy_r: float
    oos_max_drawdown_pct: float
    oos_trades: int
    fold_passed: bool


class WalkForwardSummary(BaseModel):
    folds_count: int
    folds_passed: int
    combined_oos_return_pct: float
    combined_oos_win_rate_pct: float
    combined_oos_profit_factor: float
    combined_oos_expectancy_usdt: float
    combined_oos_expectancy_r: float
    combined_oos_max_drawdown_pct: float
    combined_oos_trades: int
    walk_forward_efficiency_pct: float
    oos_equity_curve: list[EquityPoint]
    folds: list[WalkForwardFoldResult]


class TimeframeBacktestSummary(BaseModel):
    timeframe: str
    candle_count: int
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy_usdt: float
    expectancy_r: float
    configured_rr: float
    realized_rr: float
    gross_return_pct: float
    net_return_pct: float
    total_fees_usdt: float
    total_slippage_usdt: float
    walk_forward_oos_return_pct: float
    validation_status: str  # PASSED | FAILED


class ValidationGateItem(BaseModel):
    gate_key: str
    label: str
    passed: bool
    actual_value: str
    threshold: str
    reason: str


class ProBacktestResponse(BaseModel):
    run_id: int | None = None
    symbol: str
    strategy: str
    primary_interval: str
    candle_count: int
    closed_bars_tested: int
    initial_capital: float
    final_equity: float
    gross_return_pct: float
    net_return_pct: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    max_drawdown_usdt: float
    expectancy_usdt: float
    expectancy_r: float
    configured_rr: float
    realized_rr: float
    sharpe_ratio: float
    sortino_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    fee_pct: float
    slippage_pct: float
    total_fees_usdt: float
    total_slippage_usdt: float
    validation_status: str  # PASSED | FAILED
    is_strategy_successful: bool
    validation_gates: list[ValidationGateItem]
    rejection_reasons: list[str]
    look_ahead_audit: LookAheadAudit
    walk_forward: WalkForwardSummary
    timeframe_matrix: list[TimeframeBacktestSummary]
    equity_curve: list[EquityPoint]
    trades: list[ProBacktestTrade]
    executed_at: str


class SavedStrategyReportItem(BaseModel):
    id: int
    strategy_name: str
    symbol: str
    primary_interval: str
    tested_timeframes: list[str]
    validation_status: str
    is_strategy_successful: bool
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy_usdt: float
    expectancy_r: float
    realized_rr: float
    net_return_pct: float
    walk_forward_oos_return_pct: float
    total_fees_usdt: float
    total_slippage_usdt: float
    total_trades: int
    saved_bookmark: bool
    created_at: str
