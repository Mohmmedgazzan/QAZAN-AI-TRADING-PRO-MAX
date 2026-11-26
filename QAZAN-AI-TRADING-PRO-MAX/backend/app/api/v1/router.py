import sys
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Query, Request, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.database import check_db_health, get_db_connection
from app.ml.engine_probe import probe_ml_runtime
from app.schemas.common import (
    ClientLogRequest,
    DatabaseHealth,
    HealthResponse,
    MarketKlinesResponse,
    SystemLogEntry,
    SystemLogsResponse,
)
from app.schemas.platform import (
    AIAnalysisResponse,
    AppSettingsPayload,
    BacktestHistoryItem,
    BacktestRequest,
    BacktestResponse,
    CandlePredictionResponse,
    CandleProbabilityResponse,
    DashboardSummaryResponse,
    EconomicCalendarResponse,
    LiquidityAnalysisResponse,
    MarketStructureResponse,
    MarketTickersResponse,
    PaperOrderRequest,
    PaperResetRequest,
    PaperStateResponse,
    ProbabilityForecastHistoryItem,
    RiskCalculateRequest,
    RiskCalculateResponse,
    RiskProfilePayload,
    SMCAnalysisResponse,
    TradeScannerResponse,
)
from app.ml.predictor import run_ai_market_analysis, run_candle_prediction
from app.ml.probability_engine import (
    get_probability_forecast_history,
    run_next_candle_probability_engine,
)
from app.services.calendar_settings_service import (
    build_dashboard_summary,
    fetch_economic_calendar,
    get_app_settings,
    save_app_settings,
)
from app.services.market_service import fetch_market_klines
from app.services.market_tickers_service import fetch_market_tickers
from app.services.paper_trading_service import (
    close_paper_position,
    get_paper_state,
    place_paper_order,
    reset_paper_account,
)
from app.services.quant_analysis_service import (
    analyze_liquidity,
    analyze_market_structure,
    analyze_smc,
)
from app.services.risk_backtest_service import (
    calculate_risk_metrics,
    get_backtest_history,
    get_risk_profile,
    run_backtest,
    save_risk_profile,
)
from app.services.scanner_service import run_trade_scanner
from app.engine.models import (
    CausalBacktestRequest,
    CausalBacktestResponse,
    MultiTimeframeAnalysisResponse,
    TechnicalRunHistoryItem,
)
from app.engine.technical_engine import (
    analyze_multi_timeframe,
    get_technical_run_history,
)
from app.engine.backtester import run_causal_historical_backtest
from app.schemas.ingestion import (
    AddSymbolRequest,
    DataValidationReport,
    MarketIntelligenceResponse,
    TrackedSymbolItem,
    TrackedSymbolsResponse,
    WebSocketStreamStatus,
)
from app.services.market_data_validator import validate_ohlcv_and_market_data
from app.services.market_derivatives_service import build_market_intelligence
from app.services.symbol_registry import (
    add_tracked_symbol,
    get_tracked_symbols,
    remove_tracked_symbol,
)
from app.services.ws_market_hub import ws_market_hub
from app.schemas.opportunity import (
    TradeOpportunityHistoryItem,
    TradeOpportunityRequest,
    TradeOpportunityResponse,
    TradeOpportunityScanResponse,
)
from app.services.trade_discovery_service import (
    discover_trade_opportunity,
    get_opportunity_history,
    scan_all_opportunities,
)
from app.schemas.backtest_pro import (
    ProBacktestRequest,
    ProBacktestResponse,
    SavedStrategyReportItem,
)
from app.services.pro_backtest_service import (
    delete_saved_strategy_report,
    list_saved_strategy_reports,
    run_pro_backtest,
)
from app.schemas.macro_news import MacroNewsResponse
from app.services.macro_news_service import fetch_macro_news

router = APIRouter()
logger = get_logger("qazan.api")


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def get_health() -> HealthResponse:
    settings = get_settings()
    db_info = check_db_health()
    ml_packages = probe_ml_runtime()
    all_ml_ready = all(pkg.installed for pkg in ml_packages)
    overall_status = "healthy" if (db_info["connected"] and all_ml_ready) else "degraded"

    return HealthResponse(
        status=overall_status,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        python_version=sys.version.split()[0],
        timestamp=datetime.now(timezone.utc).isoformat(),
        database=DatabaseHealth(**db_info),
        ml_runtime=ml_packages,
    )


@router.get("/market/klines", response_model=MarketKlinesResponse, tags=["Market Data"])
async def get_market_klines(
    symbol: str = Query(default="BTCUSDT", min_length=5, max_length=12),
    interval: str = Query(default="1h", min_length=2, max_length=4),
    limit: int = Query(default=120, ge=20, le=500),
) -> MarketKlinesResponse:
    return await fetch_market_klines(symbol=symbol, interval=interval, limit=limit)


@router.get("/logs", response_model=SystemLogsResponse, tags=["Diagnostics"])
async def get_system_logs(
    limit: int = Query(default=50, ge=1, le=200),
    level: str = Query(default="ALL"),
) -> SystemLogsResponse:
    norm_level = level.strip().upper()
    with get_db_connection() as conn:
        if norm_level in {"WARNING", "ERROR", "CRITICAL"}:
            rows = conn.execute(
                """
                SELECT id, created_at, level, logger_name, message, source, request_id
                FROM system_logs
                WHERE level = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (norm_level, limit),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM system_logs WHERE level = ?",
                (norm_level,),
            ).fetchone()["cnt"]
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, level, logger_name, message, source, request_id
                FROM system_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS cnt FROM system_logs").fetchone()["cnt"]

    entries = [SystemLogEntry(**dict(r)) for r in rows]
    return SystemLogsResponse(total=total, logs=entries)


@router.post("/logs/client", status_code=201, tags=["Diagnostics"])
async def record_client_log(payload: ClientLogRequest, request: Request) -> dict:
    request_id = getattr(request.state, "request_id", None)
    created_at = datetime.now(timezone.utc).isoformat()
    full_message = (
        f"{payload.message} | context={payload.context}"
        if payload.context
        else payload.message
    )
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_logs (created_at, level, logger_name, message, source, request_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (created_at, payload.level, "qazan.frontend", full_message, "frontend", request_id),
        )
    logger.warning("Client error logged [%s]: %s", payload.level, payload.message)
    return {"recorded": True, "timestamp": created_at}


@router.post("/diagnostics/test-error", tags=["Diagnostics"])
async def trigger_diagnostic_error() -> None:
    raise AppError(
        code="DIAGNOSTIC_TEST_ERROR",
        message="Controlled diagnostic error triggered to verify logging and exception pipeline.",
        status_code=400,
        details="End-to-end error capture verified in SQLite system_logs.",
    )


# ==============================================================================
# Phase 2: Institutional Trading Platform Endpoints
# ==============================================================================


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse, tags=["Dashboard"])
async def get_dashboard_summary(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> DashboardSummaryResponse:
    return await build_dashboard_summary(symbol=symbol, interval=interval)


@router.get("/market/tickers", response_model=MarketTickersResponse, tags=["Market Data"])
async def get_market_tickers() -> MarketTickersResponse:
    return await fetch_market_tickers()


@router.get("/analysis/ai", response_model=AIAnalysisResponse, tags=["AI & ML"])
async def get_ai_analysis(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> AIAnalysisResponse:
    return await run_ai_market_analysis(symbol=symbol, interval=interval)


@router.get("/analysis/candle-prediction", response_model=CandlePredictionResponse, tags=["AI & ML"])
async def get_candle_prediction(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> CandlePredictionResponse:
    return await run_candle_prediction(symbol=symbol, interval=interval)


@router.get("/analysis/candle-probabilities", response_model=CandleProbabilityResponse, tags=["AI & ML"])
async def get_candle_probabilities(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=360, ge=30, le=500),
    persist: bool = Query(default=True),
) -> CandleProbabilityResponse:
    return await run_next_candle_probability_engine(
        symbol=symbol,
        interval=interval,
        limit=limit,
        persist=persist,
    )


@router.get(
    "/analysis/candle-probabilities/history",
    response_model=list[ProbabilityForecastHistoryItem],
    tags=["AI & ML"],
)
def get_candle_probability_history(
    limit: int = Query(default=10, ge=1, le=50),
) -> list[ProbabilityForecastHistoryItem]:
    return get_probability_forecast_history(limit=limit)


@router.get("/analysis/structure", response_model=MarketStructureResponse, tags=["Quant Analysis"])
async def get_market_structure(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> MarketStructureResponse:
    return await analyze_market_structure(symbol=symbol, interval=interval)


@router.get("/analysis/liquidity", response_model=LiquidityAnalysisResponse, tags=["Quant Analysis"])
async def get_liquidity_analysis(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> LiquidityAnalysisResponse:
    return await analyze_liquidity(symbol=symbol, interval=interval)


@router.get("/analysis/smc", response_model=SMCAnalysisResponse, tags=["Quant Analysis"])
async def get_smc_analysis(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> SMCAnalysisResponse:
    return await analyze_smc(symbol=symbol, interval=interval)


@router.get("/scanner/scan", response_model=TradeScannerResponse, tags=["Scanner"])
async def get_trade_scanner(interval: str = Query(default="1h")) -> TradeScannerResponse:
    return await run_trade_scanner(interval=interval)


@router.post("/risk/calculate", response_model=RiskCalculateResponse, tags=["Risk"])
def post_risk_calculate(payload: RiskCalculateRequest) -> RiskCalculateResponse:
    return calculate_risk_metrics(payload)


@router.get("/risk/profile", response_model=RiskProfilePayload, tags=["Risk"])
def get_saved_risk_profile() -> RiskProfilePayload:
    return get_risk_profile()


@router.put("/risk/profile", response_model=RiskProfilePayload, tags=["Risk"])
def put_saved_risk_profile(payload: RiskProfilePayload) -> RiskProfilePayload:
    return save_risk_profile(payload)


@router.post("/backtest/run", response_model=BacktestResponse, tags=["Backtesting"])
async def post_run_backtest(payload: BacktestRequest) -> BacktestResponse:
    return await run_backtest(payload)


@router.get("/backtest/history", response_model=list[BacktestHistoryItem], tags=["Backtesting"])
def get_saved_backtests(limit: int = Query(default=10, ge=1, le=50)) -> list[BacktestHistoryItem]:
    return get_backtest_history(limit=limit)


@router.get("/paper/state", response_model=PaperStateResponse, tags=["Paper Trading"])
async def get_paper_trading_state() -> PaperStateResponse:
    return await get_paper_state()


@router.post("/paper/order", response_model=PaperStateResponse, status_code=201, tags=["Paper Trading"])
async def post_paper_order(payload: PaperOrderRequest) -> PaperStateResponse:
    return await place_paper_order(payload)


@router.post("/paper/close/{position_id}", response_model=PaperStateResponse, tags=["Paper Trading"])
async def post_close_paper_position(position_id: int) -> PaperStateResponse:
    return await close_paper_position(position_id)


@router.post("/paper/reset", response_model=PaperStateResponse, tags=["Paper Trading"])
async def post_reset_paper_account(
    payload: PaperResetRequest | None = Body(default=None),
) -> PaperStateResponse:
    target_balance = payload.initial_balance if payload is not None else 10000.0
    return await reset_paper_account(target_balance)


@router.get("/calendar/events", response_model=EconomicCalendarResponse, tags=["Calendar"])
async def get_calendar_events(
    impact: str = Query(default="ALL"),
    country: str = Query(default="ALL"),
) -> EconomicCalendarResponse:
    return await fetch_economic_calendar(impact=impact, country=country)


@router.get("/settings", response_model=AppSettingsPayload, tags=["Settings"])
def get_platform_settings() -> AppSettingsPayload:
    return get_app_settings()


@router.put("/settings", response_model=AppSettingsPayload, tags=["Settings"])
def put_platform_settings(payload: AppSettingsPayload) -> AppSettingsPayload:
    return save_app_settings(payload)


# ==============================================================================
# Phase 3: Institutional Multi-Timeframe Causal Technical Engine (1W / 1D / 4H)
# ==============================================================================


@router.get("/engine/analyze", response_model=MultiTimeframeAnalysisResponse, tags=["Technical Engine"])
async def get_multi_tf_engine_analysis(
    symbol: str = Query(default="BTCUSDT"),
    ltf: str = Query(default="1h"),
    persist: bool = Query(default=True),
) -> MultiTimeframeAnalysisResponse:
    return await analyze_multi_timeframe(symbol=symbol, ltf_interval=ltf, persist=persist)


@router.post("/engine/backtest", response_model=CausalBacktestResponse, tags=["Technical Engine"])
async def post_causal_engine_backtest(
    payload: CausalBacktestRequest,
) -> CausalBacktestResponse:
    return await run_causal_historical_backtest(payload=payload, persist=True)


@router.get("/engine/history", response_model=list[TechnicalRunHistoryItem], tags=["Technical Engine"])
def get_engine_run_history(limit: int = Query(default=15, ge=1, le=50)) -> list[TechnicalRunHistoryItem]:
    return get_technical_run_history(limit=limit)


# ==============================================================================
# Phase 5: Real Market Data Ingestion, Validation, Symbols & WebSocket Feed
# ==============================================================================


@router.get("/data/symbols", response_model=TrackedSymbolsResponse, tags=["Market Ingestion"])
def list_tracked_symbols() -> TrackedSymbolsResponse:
    return get_tracked_symbols()


@router.post("/data/symbols", response_model=TrackedSymbolItem, status_code=201, tags=["Market Ingestion"])
async def register_tracked_symbol(payload: AddSymbolRequest) -> TrackedSymbolItem:
    item = await add_tracked_symbol(payload.symbol)
    ws_market_hub.trigger_resubscribe()
    return item


@router.delete("/data/symbols/{symbol}", response_model=TrackedSymbolsResponse, tags=["Market Ingestion"])
def delete_tracked_symbol(symbol: str) -> TrackedSymbolsResponse:
    res = remove_tracked_symbol(symbol)
    ws_market_hub.trigger_resubscribe()
    return res


@router.get("/data/market-intelligence", response_model=MarketIntelligenceResponse, tags=["Market Ingestion"])
async def get_market_intelligence(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> MarketIntelligenceResponse:
    return await build_market_intelligence(symbol=symbol, interval=interval)


@router.get("/data/validation", response_model=DataValidationReport, tags=["Market Ingestion"])
async def get_data_validation_report(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=120, ge=20, le=500),
) -> DataValidationReport:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=limit)
    return validate_ohlcv_and_market_data(symbol=klines.symbol, interval=klines.interval, candles=klines.candles)


@router.get("/data/ws-status", response_model=WebSocketStreamStatus, tags=["Market Ingestion"])
def get_websocket_stream_status() -> WebSocketStreamStatus:
    return ws_market_hub.status()


@router.websocket("/ws/market")
async def websocket_market_stream(websocket: WebSocket, symbol: str | None = None) -> None:
    await ws_market_hub.connect_client(websocket, symbol=symbol)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() == "snapshot":
                await websocket.send_json(ws_market_hub.build_snapshot(symbol=symbol))
            elif msg.strip().lower() == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        await ws_market_hub.disconnect_client(websocket)
    except Exception:
        await ws_market_hub.disconnect_client(websocket)


# ==============================================================================
# Phase 6: Trade Opportunity Discovery & Risk Governance
# ==============================================================================


@router.post("/opportunities/evaluate", response_model=TradeOpportunityResponse, tags=["Trade Discovery & Risk"])
async def post_evaluate_trade_opportunity(payload: TradeOpportunityRequest) -> TradeOpportunityResponse:
    return await discover_trade_opportunity(payload)


@router.get("/opportunities/evaluate", response_model=TradeOpportunityResponse, tags=["Trade Discovery & Risk"])
async def get_evaluate_trade_opportunity(
    symbol: str = Query(default="BTCUSDT", min_length=4, max_length=20),
    htf: str = Query(default="4h"),
    ltf: str = Query(default="1h"),
    risk_pct: float = Query(default=1.0, gt=0.05, le=10.0),
    max_daily_loss_pct: float = Query(default=3.0, gt=0.1, le=20.0),
    fee_pct: float = Query(default=0.06, ge=0.0, le=1.0),
    slippage_pct: float = Query(default=0.04, ge=0.0, le=1.0),
    leverage: float = Query(default=1.0, ge=1.0, le=50.0),
    min_net_rr: float = Query(default=1.5, ge=0.5, le=10.0),
    allow_duplicate: bool = Query(default=False),
    persist: bool = Query(default=True),
) -> TradeOpportunityResponse:
    return await discover_trade_opportunity(
        TradeOpportunityRequest(
            symbol=symbol,
            htf_timeframe=htf,
            ltf_timeframe=ltf,
            risk_pct=risk_pct,
            max_daily_loss_pct=max_daily_loss_pct,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct,
            leverage=leverage,
            min_net_rr=min_net_rr,
            allow_duplicate=allow_duplicate,
            persist=persist,
        )
    )


@router.get("/opportunities/scan", response_model=TradeOpportunityScanResponse, tags=["Trade Discovery & Risk"])
async def get_scan_trade_opportunities(
    ltf: str = Query(default="1h"),
    risk_pct: float = Query(default=1.0, gt=0.05, le=10.0),
    max_daily_loss_pct: float = Query(default=3.0, gt=0.1, le=20.0),
    fee_pct: float = Query(default=0.06, ge=0.0, le=1.0),
    slippage_pct: float = Query(default=0.04, ge=0.0, le=1.0),
) -> TradeOpportunityScanResponse:
    return await scan_all_opportunities(
        ltf_timeframe=ltf,
        risk_pct=risk_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        fee_pct=fee_pct,
        slippage_pct=slippage_pct,
    )


@router.get("/opportunities/history", response_model=list[TradeOpportunityHistoryItem], tags=["Trade Discovery & Risk"])
def get_trade_opportunity_history(limit: int = Query(default=15, ge=1, le=50)) -> list[TradeOpportunityHistoryItem]:
    return get_opportunity_history(limit=limit)


# ==============================================================================
# Phase 7: Institutional Pro Backtesting, Walk-Forward & Validation Gate
# ==============================================================================


@router.post("/backtest/pro/run", response_model=ProBacktestResponse, tags=["Backtesting Pro"])
async def post_run_pro_backtest(payload: ProBacktestRequest) -> ProBacktestResponse:
    return await run_pro_backtest(payload)


@router.get("/backtest/pro/strategies", response_model=list[SavedStrategyReportItem], tags=["Backtesting Pro"])
def get_saved_strategy_reports(
    limit: int = Query(default=20, ge=1, le=100),
    only_passed: bool = Query(default=False),
) -> list[SavedStrategyReportItem]:
    return list_saved_strategy_reports(limit=limit, only_passed=only_passed)


@router.delete("/backtest/pro/strategies/{report_id}", tags=["Backtesting Pro"])
def remove_saved_strategy_report(report_id: int) -> dict:
    return delete_saved_strategy_report(report_id)


# ==============================================================================
# Phase 8: Official Macro Economic News & High-Impact Warning Engine
# ==============================================================================


@router.get("/calendar/macro", response_model=MacroNewsResponse, tags=["Macro Economic News"])
async def get_macro_economic_news(
    category: str = Query(default="ALL"),
    impact: str = Query(default="ALL"),
    country: str = Query(default="ALL"),
    search: str = Query(default=""),
    warning_hours: int = Query(default=24, ge=1, le=168),
    include_released: bool = Query(default=True),
    refresh: bool = Query(default=False),
) -> MacroNewsResponse:
    return await fetch_macro_news(
        category=category,
        impact=impact,
        country=country,
        search=search,
        warning_hours=warning_hours,
        include_released=include_released,
        refresh=refresh,
    )




