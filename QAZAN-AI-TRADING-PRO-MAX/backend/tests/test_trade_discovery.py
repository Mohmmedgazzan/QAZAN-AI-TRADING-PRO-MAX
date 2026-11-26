import sys
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging
from app.db.database import get_db_connection, init_db
from app.engine.models import (
    CausalFairValueGap,
    CausalLiquiditySweep,
    CausalOrderBlock,
    CausalStructureEvent,
    EngineSwingPoint,
    LTFConfirmationResult,
    LevelBreachEvent,
    LiquidityPoolNode,
    MultiTimeframeAnalysisResponse,
    PremiumDiscountZone,
    SingleTimeframeAnalysis,
    SupplyDemandZone,
)
from app.main import app
from app.schemas.opportunity import TradeOpportunityRequest
from app.services.trade_discovery_service import (
    _persist_opportunity,
    evaluate_trade_opportunity_from_analysis,
)

setup_logging()
init_db()
client = TestClient(app)


def _build_synthetic_mtf(side: str = "LONG", confirm_entry: bool = True) -> MultiTimeframeAnalysisResponse:
    is_long = side == "LONG"
    bias = "BULLISH" if is_long else "BEARISH"
    price = 65000.0 if is_long else 64000.0
    atr = 500.0

    prem_disc = PremiumDiscountZone(
        range_high=68000.0 if is_long else 66500.0,
        range_low=62000.0 if is_long else 59000.0,
        equilibrium=65000.0 if is_long else 62750.0,
        ote_low=63200.0,
        ote_high=64400.0,
        position_pct=35.0 if is_long else 72.0,
        zone="DISCOUNT" if is_long else "PREMIUM",
    )

    swings_low = [
        EngineSwingPoint(
            pivot_index=10,
            pivot_time=1700000000,
            confirmed_index=13,
            confirmed_time=1700010800,
            price=64100.0 if is_long else 62000.0,
            kind="SWING_LOW",
            label="HL" if is_long else "LL",
            scope="EXTERNAL",
            swept=is_long,
            broken=False,
        )
    ]
    swings_high = [
        EngineSwingPoint(
            pivot_index=12,
            pivot_time=1700007200,
            confirmed_index=15,
            confirmed_time=1700018000,
            price=66500.0 if is_long else 64900.0,
            kind="SWING_HIGH",
            label="HH" if is_long else "LH",
            scope="EXTERNAL",
            swept=not is_long,
            broken=is_long,
        )
    ]

    struct_events = [
        CausalStructureEvent(
            breach_time=1700020000,
            confirmed_time=1700023600,
            level_price=64800.0 if is_long else 64200.0,
            event_type="BOS" if is_long else "CHoCH",
            direction=bias,
            confirmation_close=price,
        )
    ]

    breaches = [
        LevelBreachEvent(
            breach_time=1700020000,
            confirmed_time=1700023600,
            level_price=64800.0 if is_long else 64200.0,
            side=bias,
            classification="BREAKOUT",
            structure_tag="BOS" if is_long else "CHoCH",
            breach_close=price,
            confirmation_close=price,
            displacement_atr=1.4,
            reason="Confirmed candle close displacement",
        )
    ]

    zones = [
        SupplyDemandZone(
            zone_type="DEMAND" if is_long else "SUPPLY",
            pattern="DBR" if is_long else "RBD",
            top=64850.0 if is_long else 64550.0,
            bottom=64350.0 if is_long else 64050.0,
            formed_time=1700010000,
            confirmed_time=1700013600,
            displacement_atr=1.6,
            status="FRESH",
            touches=0,
        )
    ]

    obs = [
        CausalOrderBlock(
            direction=bias,
            high=64820.0 if is_long else 64520.0,
            low=64380.0 if is_long else 64080.0,
            mean_threshold=64600.0 if is_long else 64300.0,
            formed_time=1700010000,
            confirmed_time=1700013600,
            status="ACTIVE",
        )
    ]

    fvgs = [
        CausalFairValueGap(
            direction=bias,
            top=64900.0 if is_long else 64350.0,
            bottom=64650.0 if is_long else 64100.0,
            ce_midpoint=64775.0 if is_long else 64225.0,
            formed_time=1700014000,
            confirmed_time=1700017600,
            status="UNMITIGATED",
        )
    ]

    sweeps = [
        CausalLiquiditySweep(
            time=1700018000,
            side="SSL_SWEEP" if is_long else "BSL_SWEEP",
            scope="EXTERNAL",
            swept_level=64200.0 if is_long else 64750.0,
            wick_extreme=64050.0 if is_long else 64890.0,
            close_price=64500.0 if is_long else 64200.0,
            wick_ratio=0.72,
        )
    ]

    ext_liq = (
        [
            LiquidityPoolNode(
                price=66800.0,
                side="BSL",
                scope="EXTERNAL",
                touches=2,
                pool_type="EQH",
                first_time=1700000000,
                confirmed_time=1700007200,
                distance_pct=2.77,
                swept=False,
            ),
            LiquidityPoolNode(
                price=67900.0,
                side="BSL",
                scope="EXTERNAL",
                touches=2,
                pool_type="SWING_LEVEL",
                first_time=1700000000,
                confirmed_time=1700007200,
                distance_pct=4.46,
                swept=False,
            ),
        ]
        if is_long
        else [
            LiquidityPoolNode(
                price=61800.0,
                side="SSL",
                scope="EXTERNAL",
                touches=2,
                pool_type="EQL",
                first_time=1700000000,
                confirmed_time=1700007200,
                distance_pct=3.44,
                swept=False,
            ),
            LiquidityPoolNode(
                price=60200.0,
                side="SSL",
                scope="EXTERNAL",
                touches=2,
                pool_type="SWING_LEVEL",
                first_time=1700000000,
                confirmed_time=1700007200,
                distance_pct=5.94,
                swept=False,
            ),
        ]
    )

    def _make_tf(tf_name: str) -> SingleTimeframeAnalysis:
        return SingleTimeframeAnalysis(
            timeframe=tf_name,
            closed_bars_analyzed=120,
            unclosed_bar_excluded=True,
            last_closed_time=1700028000,
            last_close=price,
            atr_14=atr,
            adx_14=28.0,
            rsi_14=58.0 if is_long else 41.0,
            market_bias=bias,
            market_regime="TRENDING_EXPANSION",
            market_phase="TREND",
            premium_discount=prem_disc,
            swing_highs=swings_high,
            swing_lows=swings_low,
            hh_hl_lh_ll_sequence=swings_low + swings_high,
            external_liquidity=ext_liq,
            internal_liquidity=[],
            equal_highs_lows=[],
            liquidity_sweeps=sweeps,
            structure_events=struct_events,
            level_breaches=breaches,
            pending_breakout=None,
            supply_demand_zones=zones,
            order_blocks=obs,
            breaker_blocks=[],
            fair_value_gaps=fvgs,
        )

    ltf_status = (
        ("CONFIRMED_LONG" if is_long else "CONFIRMED_SHORT")
        if confirm_entry
        else "WAIT_CONFIRMATION"
    )
    ltf_conf = LTFConfirmationResult(
        timeframe="1h",
        htf_bias=bias,
        price_in_htf_poi=confirm_entry,
        matched_poi_description="HTF Zone + Sweep" if confirm_entry else None,
        ltf_structure_aligned=confirm_entry,
        ltf_sweep_detected=confirm_entry,
        setup_status=ltf_status,
        rationale="LTF structure aligned inside HTF POI" if confirm_entry else "Awaiting LTF confirmation",
    )

    return MultiTimeframeAnalysisResponse(
        run_id=None,
        symbol="TESTBTCUSDT",
        primary_timeframes=["1w", "1d", "4h"],
        ltf_timeframe="1h",
        look_ahead_bias_prevented=True,
        market_bias=bias,
        market_regime="TRENDING_EXPANSION",
        market_phase="TREND",
        htf_alignment_score=85.0,
        timeframes={"4h": _make_tf("4h"), "1h": _make_tf("1h")},
        ltf_confirmation=ltf_conf,
        analyzed_at="2026-11-16T00:00:00+00:00",
    )


def test_valid_long_hypothesis_and_fee_slippage_sizing() -> None:
    mtf = _build_synthetic_mtf(side="LONG", confirm_entry=True)
    req = TradeOpportunityRequest(
        symbol="TESTBTCUSDT",
        risk_pct=1.0,
        max_daily_loss_pct=3.0,
        fee_pct=0.06,
        slippage_pct=0.04,
        leverage=5.0,
        min_net_rr=1.5,
        allow_duplicate=True,
        persist=False,
    )
    res = evaluate_trade_opportunity_from_analysis(
        mtf=mtf,
        req=req,
        account_balance=10000.0,
        duplicate_checker=lambda _fp, _t: False,
    )
    assert res.decision == "LONG"
    assert res.live_execution_blocked is True
    assert res.execution_mode == "ANALYSIS_ONLY_NO_LIVE_ORDERS"
    assert res.long_hypothesis.eligible is True
    assert res.short_hypothesis.eligible is False
    assert res.entry_zone_low is not None and res.entry_zone_high is not None
    assert res.entry_zone_low <= res.entry_price <= res.entry_zone_high
    assert res.stop_loss < res.entry_price < res.tp1 < res.tp2 < res.tp3

    gov = res.risk_governance
    assert gov.risk_amount_usdt == 100.0
    assert gov.position_size_units > 0
    assert gov.total_friction_usdt > 0
    assert gov.net_rr_tp2 < gov.gross_rr_tp2
    # Max loss at SL including entry+exit fees & slippage must not exceed 1% ($100) + tiny rounding tolerance
    stop_loss_value = (res.entry_price - res.stop_loss) * gov.position_size_units
    worst_case_loss = stop_loss_value + gov.total_friction_usdt
    assert worst_case_loss <= 101.0


def test_valid_short_hypothesis_decision() -> None:
    mtf = _build_synthetic_mtf(side="SHORT", confirm_entry=True)
    req = TradeOpportunityRequest(
        symbol="TESTBTCUSDT",
        risk_pct=1.0,
        max_daily_loss_pct=3.0,
        fee_pct=0.06,
        slippage_pct=0.04,
        leverage=5.0,
        allow_duplicate=True,
        persist=False,
    )
    res = evaluate_trade_opportunity_from_analysis(
        mtf=mtf,
        req=req,
        account_balance=10000.0,
        duplicate_checker=lambda _fp, _t: False,
    )
    assert res.decision == "SHORT"
    assert res.short_hypothesis.eligible is True
    assert res.long_hypothesis.eligible is False
    assert res.stop_loss > res.entry_price > res.tp1 > res.tp2 > res.tp3
    assert res.risk_governance.confirmation_gate_passed is True


def test_missing_entry_confirmation_forces_no_trade() -> None:
    mtf = _build_synthetic_mtf(side="LONG", confirm_entry=False)
    req = TradeOpportunityRequest(symbol="TESTBTCUSDT", allow_duplicate=True, persist=False)
    res = evaluate_trade_opportunity_from_analysis(
        mtf=mtf,
        req=req,
        account_balance=10000.0,
        duplicate_checker=lambda _fp, _t: False,
    )
    assert res.decision == "NO_TRADE"
    assert res.risk_governance.confirmation_gate_passed is False
    assert res.risk_governance.position_size_units == 0.0
    assert any("entry_confirmation" in r for r in res.risk_governance.rejection_reasons)


def test_daily_loss_limit_3pct_blocks_trade() -> None:
    mtf = _build_synthetic_mtf(side="LONG", confirm_entry=True)
    req = TradeOpportunityRequest(
        symbol="TESTBTCUSDT",
        risk_pct=1.0,
        max_daily_loss_pct=3.0,
        simulate_daily_loss_pct=3.0,
        allow_duplicate=True,
        persist=False,
    )
    res = evaluate_trade_opportunity_from_analysis(
        mtf=mtf,
        req=req,
        account_balance=10000.0,
        duplicate_checker=lambda _fp, _t: False,
    )
    assert res.decision == "NO_TRADE"
    assert res.risk_governance.daily_limit_breached is True
    assert res.risk_governance.daily_remaining_risk_pct == 0.0
    assert res.risk_governance.position_size_units == 0.0
    assert any("Daily loss limit" in r for r in res.risk_governance.rejection_reasons)


def test_duplicate_signal_suppression_in_sqlite() -> None:
    with get_db_connection() as conn:
        conn.execute("DELETE FROM trade_opportunities WHERE symbol = 'DUPTESTUSDT'")

    mtf = _build_synthetic_mtf(side="LONG", confirm_entry=True)
    mtf.symbol = "DUPTESTUSDT"

    req_first = TradeOpportunityRequest(symbol="DUPTESTUSDT", allow_duplicate=False, persist=True)
    first_res = evaluate_trade_opportunity_from_analysis(mtf=mtf, req=req_first, account_balance=10000.0)
    assert first_res.decision == "LONG"
    assert first_res.risk_governance.duplicate_suppressed is False
    _persist_opportunity(first_res)

    second_res = evaluate_trade_opportunity_from_analysis(mtf=mtf, req=req_first, account_balance=10000.0)
    assert second_res.decision == "NO_TRADE"
    assert second_res.risk_governance.duplicate_suppressed is True
    assert second_res.risk_governance.duplicate_fingerprint == first_res.risk_governance.duplicate_fingerprint

    req_recheck = TradeOpportunityRequest(symbol="DUPTESTUSDT", allow_duplicate=True, persist=False)
    recheck_res = evaluate_trade_opportunity_from_analysis(mtf=mtf, req=req_recheck, account_balance=10000.0)
    assert recheck_res.decision == "LONG"

    with get_db_connection() as conn:
        conn.execute("DELETE FROM trade_opportunities WHERE symbol = 'DUPTESTUSDT'")


def test_live_api_opportunities_endpoints_and_version() -> None:
    from app.core.config import get_settings

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["version"] == get_settings().APP_VERSION

    eval_resp = client.get("/api/v1/opportunities/evaluate?symbol=BTCUSDT&ltf=1h&persist=true")
    assert eval_resp.status_code == 200
    payload = eval_resp.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["decision"] in {"LONG", "SHORT", "NO_TRADE"}
    assert payload["live_execution_blocked"] is True
    assert len(payload["long_hypothesis"]["checks"]) == 5
    assert len(payload["short_hypothesis"]["checks"]) == 5

    post_resp = client.post(
        "/api/v1/opportunities/evaluate",
        json={
            "symbol": "ETHUSDT",
            "htf_timeframe": "4h",
            "ltf_timeframe": "1h",
            "risk_pct": 1.0,
            "max_daily_loss_pct": 3.0,
            "fee_pct": 0.06,
            "slippage_pct": 0.04,
            "leverage": 3.0,
            "allow_duplicate": True,
            "persist": False,
        },
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["symbol"] == "ETHUSDT"

    scan_resp = client.get("/api/v1/opportunities/scan?ltf=1h")
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["live_execution_blocked"] is True
    assert len(scan_data["items"]) >= 2

    hist_resp = client.get("/api/v1/opportunities/history?limit=5")
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()) >= 1
