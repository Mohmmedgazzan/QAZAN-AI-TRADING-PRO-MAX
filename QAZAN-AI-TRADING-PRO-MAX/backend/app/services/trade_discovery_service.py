import asyncio
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.engine.models import MultiTimeframeAnalysisResponse, SingleTimeframeAnalysis
from app.engine.technical_engine import analyze_multi_timeframe
from app.schemas.opportunity import (
    DecisionType,
    HypothesisCheckItem,
    HypothesisEvaluation,
    RiskGovernanceReport,
    TradeOpportunityHistoryItem,
    TradeOpportunityRequest,
    TradeOpportunityResponse,
    TradeOpportunityScanResponse,
)
from app.services.paper_trading_service import get_paper_state
from app.services.risk_backtest_service import get_risk_profile
from app.services.symbol_registry import get_tracked_symbol_names

logger = get_logger("qazan.discovery")


def _round_px(price: float) -> float:
    if price >= 1000:
        return round(price, 2)
    if price >= 10:
        return round(price, 4)
    return round(price, 6)


def _compute_fingerprint(
    symbol: str,
    htf: str,
    ltf: str,
    side: str,
    entry_low: float | None,
    entry_high: float | None,
    stop_loss: float | None,
) -> str:
    raw = (
        f"{symbol}|{htf}|{ltf}|{side}|"
        f"{round(entry_low or 0.0, 2)}|{round(entry_high or 0.0, 2)}|{round(stop_loss or 0.0, 2)}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _check_duplicate_fingerprint(fingerprint: str, candle_time: int) -> bool:
    """
    Returns True if an identical actionable signal with the same fingerprint
    was already recorded for the current closed candle (or within the last 4 hours).
    """
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, candle_time, created_at
            FROM trade_opportunities
            WHERE fingerprint = ?
              AND decision IN ('LONG', 'SHORT')
              AND is_duplicate = 0
            ORDER BY id DESC
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()
    if not row:
        return False
    if int(row["candle_time"]) == int(candle_time):
        return True
    try:
        prev_dt = datetime.fromisoformat(str(row["created_at"]))
        age_sec = (datetime.now(timezone.utc) - prev_dt).total_seconds()
        if age_sec < 4 * 3600:
            return True
    except Exception:
        pass
    return False


def _evaluate_long_hypothesis(
    mtf: MultiTimeframeAnalysisResponse,
    htf: SingleTimeframeAnalysis,
    ltf: SingleTimeframeAnalysis,
) -> HypothesisEvaluation:
    price = float(ltf.last_close or htf.last_close)
    atr = max(float(ltf.atr_14 or htf.atr_14), price * 0.0025)

    # 1. Trend Confirmation (HTF + 4H bullish alignment)
    trend_ok = (
        mtf.market_bias == "BULLISH"
        or (htf.market_bias == "BULLISH" and mtf.htf_alignment_score >= 50.0)
    )
    trend_detail = (
        f"HTF bias={mtf.market_bias}, 4H bias={htf.market_bias}, alignment={mtf.htf_alignment_score}%"
    )

    # 2. BOS / CHoCH Bullish Confirmation
    bull_struct_events = [
        ev for ev in (list(htf.structure_events) + list(ltf.structure_events)) if ev.direction == "BULLISH"
    ]
    bear_struct_events = [
        ev for ev in (list(htf.structure_events) + list(ltf.structure_events)) if ev.direction == "BEARISH"
    ]
    latest_bull_t = max((ev.confirmed_time for ev in bull_struct_events), default=0)
    latest_bear_t = max((ev.confirmed_time for ev in bear_struct_events), default=0)
    bull_breakouts = [
        b
        for b in (list(htf.level_breaches) + list(ltf.level_breaches))
        if b.side == "BULLISH" and b.classification == "BREAKOUT"
    ]
    bos_choch_ok = len(bull_struct_events) > 0 and (
        latest_bull_t >= latest_bear_t or len(bull_breakouts) > 0
    )
    bos_detail = (
        f"Confirmed bullish {bull_struct_events[-1].event_type} @ {_round_px(bull_struct_events[-1].level_price)}"
        if bull_struct_events
        else "No confirmed bullish BOS/CHoCH closed above swing resistance"
    )

    # 3. Demand Zones & Liquidity (Demand / Bullish OB / FVG / SSL Sweep / Discount)
    active_demand = [z for z in (list(htf.supply_demand_zones) + list(ltf.supply_demand_zones)) if z.zone_type == "DEMAND" and z.status != "BROKEN"]
    active_bull_ob = [ob for ob in (list(htf.order_blocks) + list(ltf.order_blocks)) if ob.direction == "BULLISH" and ob.status == "ACTIVE"]
    active_bull_fvg = [g for g in (list(htf.fair_value_gaps) + list(ltf.fair_value_gaps)) if g.direction == "BULLISH" and g.status != "MITIGATED"]
    ssl_sweeps = [sw for sw in (list(htf.liquidity_sweeps) + list(ltf.liquidity_sweeps)) if sw.side == "SSL_SWEEP"]
    in_discount_or_eq = htf.premium_discount.zone in ("DISCOUNT", "EQUILIBRIUM")

    poi_candidates_low: list[float] = []
    poi_candidates_high: list[float] = []
    for z in active_demand:
        if z.bottom <= price * 1.015:
            poi_candidates_low.append(z.bottom)
            poi_candidates_high.append(z.top)
    for ob in active_bull_ob:
        if ob.low <= price * 1.015:
            poi_candidates_low.append(ob.low)
            poi_candidates_high.append(ob.high)
    for g in active_bull_fvg:
        if g.bottom <= price * 1.015:
            poi_candidates_low.append(g.bottom)
            poi_candidates_high.append(g.top)

    demand_liq_ok = (len(active_demand) + len(active_bull_ob) + len(ssl_sweeps) > 0) and (
        in_discount_or_eq or len(ssl_sweeps) > 0 or len(poi_candidates_low) > 0
    )
    demand_detail = (
        f"Demand={len(active_demand)}, BullOB={len(active_bull_ob)}, SSL sweeps={len(ssl_sweeps)}, Zone={htf.premium_discount.zone}"
    )

    # 4. LTF Entry Confirmation (never enter blind)
    entry_confirm_ok = (
        mtf.ltf_confirmation.setup_status == "CONFIRMED_LONG"
        or (
            mtf.ltf_confirmation.ltf_structure_aligned
            and ltf.market_bias == "BULLISH"
            and (mtf.ltf_confirmation.price_in_htf_poi or mtf.ltf_confirmation.ltf_sweep_detected)
        )
    )
    entry_confirm_detail = mtf.ltf_confirmation.rationale

    # 5. Invalidation & Levels (Entry Zone, SL, TP1, TP2, TP3)
    if poi_candidates_low and poi_candidates_high:
        zone_low = _round_px(max(poi_candidates_low[-1], price - atr * 1.6))
        zone_high = _round_px(min(max(poi_candidates_high[-1], zone_low), price))
        entry_px = _round_px(min(price, (zone_low + zone_high) / 2.0 + 0.15 * (price - zone_low)))
    else:
        zone_low = _round_px(price - atr * 0.45)
        zone_high = _round_px(price)
        entry_px = _round_px(price)

    recent_lows = [sw.price for sw in ltf.swing_lows if sw.price < entry_px]
    structural_floor = max(recent_lows) if recent_lows else zone_low
    sl_anchor = min(zone_low, structural_floor)
    stop_loss = _round_px(max(entry_px * 0.5, sl_anchor - atr * 0.35))
    if stop_loss >= entry_px:
        stop_loss = _round_px(entry_px - atr * 1.2)

    risk_dist = max(entry_px - stop_loss, entry_px * 0.002)
    invalidation_ok = 0 < stop_loss < entry_px

    # Structural BSL targets blended with R multiples
    bsl_above = sorted(
        [
            p.price
            for p in (list(htf.external_liquidity) + list(htf.internal_liquidity) + list(ltf.external_liquidity))
            if p.side == "BSL" and p.price > entry_px + risk_dist * 1.1
        ]
    )
    tp1_base = entry_px + risk_dist * 1.5
    tp2_base = entry_px + risk_dist * 2.5
    tp3_base = entry_px + risk_dist * 3.5

    tp1 = _round_px(max(tp1_base, bsl_above[0]) if bsl_above else tp1_base)
    tp2 = _round_px(max(tp2_base, bsl_above[1] if len(bsl_above) > 1 else tp2_base, tp1 + risk_dist * 0.6))
    tp3 = _round_px(max(tp3_base, htf.premium_discount.range_high, tp2 + risk_dist * 0.8))

    invalidation_reason = f"Close below structural demand/HL invalidation at {_round_px(stop_loss)}"

    checks = [
        HypothesisCheckItem(
            criterion="trend_confirmation",
            passed=trend_ok,
            detail=trend_detail,
            evidence_value=mtf.market_bias,
        ),
        HypothesisCheckItem(
            criterion="bos_choch",
            passed=bos_choch_ok,
            detail=bos_detail,
            evidence_value=str(len(bull_struct_events)),
        ),
        HypothesisCheckItem(
            criterion="demand_liquidity",
            passed=demand_liq_ok,
            detail=demand_detail,
            evidence_value=htf.premium_discount.zone,
        ),
        HypothesisCheckItem(
            criterion="entry_confirmation",
            passed=entry_confirm_ok,
            detail=entry_confirm_detail,
            evidence_value=mtf.ltf_confirmation.setup_status,
        ),
        HypothesisCheckItem(
            criterion="invalidation",
            passed=invalidation_ok,
            detail=invalidation_reason,
            evidence_value=str(stop_loss),
        ),
    ]

    passed_count = sum(1 for c in checks if c.passed)
    eligible = all(c.passed for c in checks)
    return HypothesisEvaluation(
        side="LONG",
        eligible=eligible,
        passed_count=passed_count,
        total_count=len(checks),
        score_pct=round((passed_count / len(checks)) * 100.0, 1),
        checks=checks,
        invalidation_price=stop_loss,
        invalidation_reason=invalidation_reason,
        proposed_entry_zone_low=zone_low,
        proposed_entry_zone_high=zone_high,
        proposed_entry=entry_px,
        proposed_stop_loss=stop_loss,
        proposed_tp1=tp1,
        proposed_tp2=tp2,
        proposed_tp3=tp3,
    )


def _evaluate_short_hypothesis(
    mtf: MultiTimeframeAnalysisResponse,
    htf: SingleTimeframeAnalysis,
    ltf: SingleTimeframeAnalysis,
) -> HypothesisEvaluation:
    price = float(ltf.last_close or htf.last_close)
    atr = max(float(ltf.atr_14 or htf.atr_14), price * 0.0025)

    # 1. Downtrend Confirmation
    trend_ok = (
        mtf.market_bias == "BEARISH"
        or (htf.market_bias == "BEARISH" and mtf.htf_alignment_score >= 50.0)
    )
    trend_detail = (
        f"HTF bias={mtf.market_bias}, 4H bias={htf.market_bias}, alignment={mtf.htf_alignment_score}%"
    )

    # 2. BOS / CHoCH Bearish Confirmation
    bear_struct_events = [
        ev for ev in (list(htf.structure_events) + list(ltf.structure_events)) if ev.direction == "BEARISH"
    ]
    bull_struct_events = [
        ev for ev in (list(htf.structure_events) + list(ltf.structure_events)) if ev.direction == "BULLISH"
    ]
    latest_bear_t = max((ev.confirmed_time for ev in bear_struct_events), default=0)
    latest_bull_t = max((ev.confirmed_time for ev in bull_struct_events), default=0)
    bear_breakouts = [
        b
        for b in (list(htf.level_breaches) + list(ltf.level_breaches))
        if b.side == "BEARISH" and b.classification == "BREAKOUT"
    ]
    bos_choch_ok = len(bear_struct_events) > 0 and (
        latest_bear_t >= latest_bull_t or len(bear_breakouts) > 0
    )
    bos_detail = (
        f"Confirmed bearish {bear_struct_events[-1].event_type} @ {_round_px(bear_struct_events[-1].level_price)}"
        if bear_struct_events
        else "No confirmed bearish BOS/CHoCH closed below swing support"
    )

    # 3. Supply Zones & Liquidity (Supply / Bearish OB / FVG / BSL Sweep / Premium)
    active_supply = [z for z in (list(htf.supply_demand_zones) + list(ltf.supply_demand_zones)) if z.zone_type == "SUPPLY" and z.status != "BROKEN"]
    active_bear_ob = [ob for ob in (list(htf.order_blocks) + list(ltf.order_blocks)) if ob.direction == "BEARISH" and ob.status == "ACTIVE"]
    active_bear_fvg = [g for g in (list(htf.fair_value_gaps) + list(ltf.fair_value_gaps)) if g.direction == "BEARISH" and g.status != "MITIGATED"]
    bsl_sweeps = [sw for sw in (list(htf.liquidity_sweeps) + list(ltf.liquidity_sweeps)) if sw.side == "BSL_SWEEP"]
    in_premium_or_eq = htf.premium_discount.zone in ("PREMIUM", "EQUILIBRIUM")

    poi_lows: list[float] = []
    poi_highs: list[float] = []
    for z in active_supply:
        if z.top >= price * 0.985:
            poi_lows.append(z.bottom)
            poi_highs.append(z.top)
    for ob in active_bear_ob:
        if ob.high >= price * 0.985:
            poi_lows.append(ob.low)
            poi_highs.append(ob.high)
    for g in active_bear_fvg:
        if g.top >= price * 0.985:
            poi_lows.append(g.bottom)
            poi_highs.append(g.top)

    supply_liq_ok = (len(active_supply) + len(active_bear_ob) + len(bsl_sweeps) > 0) and (
        in_premium_or_eq or len(bsl_sweeps) > 0 or len(poi_highs) > 0
    )
    supply_detail = (
        f"Supply={len(active_supply)}, BearOB={len(active_bear_ob)}, BSL sweeps={len(bsl_sweeps)}, Zone={htf.premium_discount.zone}"
    )

    # 4. LTF Entry Confirmation
    entry_confirm_ok = (
        mtf.ltf_confirmation.setup_status == "CONFIRMED_SHORT"
        or (
            mtf.ltf_confirmation.ltf_structure_aligned
            and ltf.market_bias == "BEARISH"
            and (mtf.ltf_confirmation.price_in_htf_poi or mtf.ltf_confirmation.ltf_sweep_detected)
        )
    )
    entry_confirm_detail = mtf.ltf_confirmation.rationale

    # 5. Invalidation & Levels
    if poi_lows and poi_highs:
        zone_high = _round_px(min(poi_highs[-1], price + atr * 1.6))
        zone_low = _round_px(max(price, min(poi_lows[-1], zone_high)))
        entry_px = _round_px(max(price, (zone_low + zone_high) / 2.0 - 0.15 * (zone_high - price)))
    else:
        zone_low = _round_px(price)
        zone_high = _round_px(price + atr * 0.45)
        entry_px = _round_px(price)

    recent_highs = [sw.price for sw in ltf.swing_highs if sw.price > entry_px]
    structural_ceil = min(recent_highs) if recent_highs else zone_high
    sl_anchor = max(zone_high, structural_ceil)
    stop_loss = _round_px(sl_anchor + atr * 0.35)
    if stop_loss <= entry_px:
        stop_loss = _round_px(entry_px + atr * 1.2)

    risk_dist = max(stop_loss - entry_px, entry_px * 0.002)
    invalidation_ok = stop_loss > entry_px

    ssl_below = sorted(
        [
            p.price
            for p in (list(htf.external_liquidity) + list(htf.internal_liquidity) + list(ltf.external_liquidity))
            if p.side == "SSL" and p.price < entry_px - risk_dist * 1.1
        ],
        reverse=True,
    )
    tp1_base = entry_px - risk_dist * 1.5
    tp2_base = entry_px - risk_dist * 2.5
    tp3_base = entry_px - risk_dist * 3.5

    tp1 = _round_px(max(0.0001, min(tp1_base, ssl_below[0]) if ssl_below else tp1_base))
    tp2 = _round_px(max(0.0001, min(tp2_base, ssl_below[1] if len(ssl_below) > 1 else tp2_base, tp1 - risk_dist * 0.6)))
    tp3 = _round_px(max(0.0001, min(tp3_base, htf.premium_discount.range_low, tp2 - risk_dist * 0.8)))

    invalidation_reason = f"Close above structural supply/LH invalidation at {_round_px(stop_loss)}"

    checks = [
        HypothesisCheckItem(
            criterion="trend_confirmation",
            passed=trend_ok,
            detail=trend_detail,
            evidence_value=mtf.market_bias,
        ),
        HypothesisCheckItem(
            criterion="bos_choch",
            passed=bos_choch_ok,
            detail=bos_detail,
            evidence_value=str(len(bear_struct_events)),
        ),
        HypothesisCheckItem(
            criterion="supply_liquidity",
            passed=supply_liq_ok,
            detail=supply_detail,
            evidence_value=htf.premium_discount.zone,
        ),
        HypothesisCheckItem(
            criterion="entry_confirmation",
            passed=entry_confirm_ok,
            detail=entry_confirm_detail,
            evidence_value=mtf.ltf_confirmation.setup_status,
        ),
        HypothesisCheckItem(
            criterion="invalidation",
            passed=invalidation_ok,
            detail=invalidation_reason,
            evidence_value=str(stop_loss),
        ),
    ]

    passed_count = sum(1 for c in checks if c.passed)
    eligible = all(c.passed for c in checks)
    return HypothesisEvaluation(
        side="SHORT",
        eligible=eligible,
        passed_count=passed_count,
        total_count=len(checks),
        score_pct=round((passed_count / len(checks)) * 100.0, 1),
        checks=checks,
        invalidation_price=stop_loss,
        invalidation_reason=invalidation_reason,
        proposed_entry_zone_low=zone_low,
        proposed_entry_zone_high=zone_high,
        proposed_entry=entry_px,
        proposed_stop_loss=stop_loss,
        proposed_tp1=tp1,
        proposed_tp2=tp2,
        proposed_tp3=tp3,
    )


def _compute_today_paper_loss_pct(account_balance: float, unrealized_pnl: float) -> tuple[float, float]:
    today_prefix = datetime.now(timezone.utc).date().isoformat()
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT realized_pnl
            FROM paper_positions
            WHERE status = 'CLOSED' AND closed_at LIKE ?
            """,
            (f"{today_prefix}%",),
        ).fetchall()
    realized_sum = sum(float(r["realized_pnl"] or 0.0) for r in rows)
    realized_loss_pct = max(0.0, (-realized_sum / max(account_balance, 1.0)) * 100.0)
    unrealized_loss_pct = max(0.0, (-unrealized_pnl / max(account_balance, 1.0)) * 100.0)
    return round(realized_loss_pct, 3), round(unrealized_loss_pct, 3)


def evaluate_trade_opportunity_from_analysis(
    mtf: MultiTimeframeAnalysisResponse,
    req: TradeOpportunityRequest,
    account_balance: float,
    daily_realized_loss_pct: float = 0.0,
    daily_unrealized_loss_pct: float = 0.0,
    duplicate_checker=None,
) -> TradeOpportunityResponse:
    htf = mtf.timeframes.get(req.htf_timeframe) or mtf.timeframes.get("4h") or next(iter(mtf.timeframes.values()))
    ltf = mtf.timeframes.get(req.ltf_timeframe) or mtf.timeframes.get("1h") or htf
    last_price = float(ltf.last_close or htf.last_close)
    candle_time = int(ltf.last_closed_time or htf.last_closed_time)

    long_hyp = _evaluate_long_hypothesis(mtf, htf, ltf)
    short_hyp = _evaluate_short_hypothesis(mtf, htf, ltf)

    if req.simulate_daily_loss_pct is not None:
        daily_realized_loss_pct = round(float(req.simulate_daily_loss_pct), 3)
        daily_unrealized_loss_pct = 0.0

    daily_total_loss_pct = round(daily_realized_loss_pct + daily_unrealized_loss_pct, 3)
    daily_remaining_pct = max(0.0, round(req.max_daily_loss_pct - daily_total_loss_pct, 3))
    daily_limit_breached = daily_total_loss_pct >= req.max_daily_loss_pct

    rejection_reasons: list[str] = []
    if daily_limit_breached:
        rejection_reasons.append(
            f"Daily loss limit reached ({daily_total_loss_pct:.2f}% >= {req.max_daily_loss_pct:.2f}% max)."
        )

    selected_hyp: HypothesisEvaluation | None = None
    candidate_side: DecisionType = "NO_TRADE"

    if long_hyp.eligible and short_hyp.eligible:
        rejection_reasons.append("Conflicting LONG and SHORT confirmations; standing aside (NO TRADE).")
    elif long_hyp.eligible:
        selected_hyp = long_hyp
        candidate_side = "LONG"
    elif short_hyp.eligible:
        selected_hyp = short_hyp
        candidate_side = "SHORT"
    else:
        best = long_hyp if long_hyp.passed_count >= short_hyp.passed_count else short_hyp
        failed = [c.criterion for c in best.checks if not c.passed]
        rejection_reasons.append(
            f"Missing mandatory confirmation(s) on {best.side}: {', '.join(failed)}."
        )

    # Compute Risk, Position Size, Fees, Slippage & Net R:R on selected hypothesis (or preview on highest-scoring)
    preview_hyp = selected_hyp or (long_hyp if long_hyp.passed_count >= short_hyp.passed_count else short_hyp)
    entry_px = preview_hyp.proposed_entry or last_price
    stop_loss = preview_hyp.proposed_stop_loss or last_price
    tp1 = preview_hyp.proposed_tp1 or last_price
    tp2 = preview_hyp.proposed_tp2 or last_price
    tp3 = preview_hyp.proposed_tp3 or last_price
    stop_dist = max(abs(entry_px - stop_loss), entry_px * 0.001)

    effective_risk_pct = min(req.risk_pct, daily_remaining_pct) if not daily_limit_breached else 0.0
    risk_budget_usdt = round(account_balance * (effective_risk_pct / 100.0), 2)

    fee_rate = req.fee_pct / 100.0
    slip_rate = req.slippage_pct / 100.0
    friction_per_side = fee_rate + slip_rate
    # Effective loss per 1 unit including entry + SL exit fees & slippage
    effective_loss_per_unit = stop_dist + (entry_px * friction_per_side) + (stop_loss * friction_per_side)
    raw_units = risk_budget_usdt / max(effective_loss_per_unit, 1e-9) if risk_budget_usdt > 0 else 0.0
    # Cap notional by account_balance * leverage
    max_notional = account_balance * req.leverage
    notional_usdt = min(raw_units * entry_px, max_notional) if raw_units > 0 else 0.0
    units = notional_usdt / max(entry_px, 1e-9)
    margin_usdt = notional_usdt / max(req.leverage, 1.0)

    est_fee_usdt = round(notional_usdt * fee_rate * 2.0, 2)
    est_slippage_usdt = round(notional_usdt * slip_rate * 2.0, 2)
    total_friction = round(est_fee_usdt + est_slippage_usdt, 2)

    gross_rr_1 = round(abs(tp1 - entry_px) / stop_dist, 2)
    gross_rr_2 = round(abs(tp2 - entry_px) / stop_dist, 2)
    gross_rr_3 = round(abs(tp3 - entry_px) / stop_dist, 2)

    if risk_budget_usdt > 0 and units > 0:
        net_rr_1 = round(((abs(tp1 - entry_px) * units) - total_friction) / risk_budget_usdt, 2)
        net_rr_2 = round(((abs(tp2 - entry_px) * units) - total_friction) / risk_budget_usdt, 2)
        net_rr_3 = round(((abs(tp3 - entry_px) * units) - total_friction) / risk_budget_usdt, 2)
    else:
        net_rr_1, net_rr_2, net_rr_3 = gross_rr_1, gross_rr_2, gross_rr_3

    if selected_hyp is not None and net_rr_2 < req.min_net_rr:
        rejection_reasons.append(
            f"Net R:R after fees & slippage ({net_rr_2:.2f}R) is below minimum {req.min_net_rr:.2f}R."
        )
        selected_hyp = None
        candidate_side = "NO_TRADE"

    # Deduplication gate
    fingerprint: str | None = None
    duplicate_suppressed = False
    if candidate_side in ("LONG", "SHORT") and selected_hyp is not None:
        fingerprint = _compute_fingerprint(
            mtf.symbol,
            req.htf_timeframe,
            req.ltf_timeframe,
            candidate_side,
            selected_hyp.proposed_entry_zone_low,
            selected_hyp.proposed_entry_zone_high,
            selected_hyp.proposed_stop_loss,
        )
        checker = duplicate_checker or _check_duplicate_fingerprint
        if not req.allow_duplicate and checker(fingerprint, candle_time):
            duplicate_suppressed = True
            rejection_reasons.append(
                f"Duplicate {candidate_side} signal suppressed for fingerprint {fingerprint} (already issued)."
            )
            candidate_side = "NO_TRADE"

    if daily_limit_breached:
        candidate_side = "NO_TRADE"

    confirmation_gate_passed = (
        candidate_side in ("LONG", "SHORT") and not daily_limit_breached and not duplicate_suppressed
    )

    final_decision: DecisionType = candidate_side if confirmation_gate_passed else "NO_TRADE"

    risk_gov = RiskGovernanceReport(
        account_balance_usdt=round(account_balance, 2),
        risk_per_trade_pct=round(effective_risk_pct, 2),
        max_daily_loss_pct=round(req.max_daily_loss_pct, 2),
        daily_realized_loss_pct=daily_realized_loss_pct,
        daily_unrealized_loss_pct=daily_unrealized_loss_pct,
        daily_total_loss_pct=daily_total_loss_pct,
        daily_remaining_risk_pct=daily_remaining_pct,
        daily_limit_breached=daily_limit_breached,
        fee_pct_per_side=round(req.fee_pct, 4),
        slippage_pct_per_side=round(req.slippage_pct, 4),
        estimated_fee_usdt=est_fee_usdt if confirmation_gate_passed else 0.0,
        estimated_slippage_usdt=est_slippage_usdt if confirmation_gate_passed else 0.0,
        total_friction_usdt=total_friction if confirmation_gate_passed else 0.0,
        gross_rr_tp1=gross_rr_1,
        gross_rr_tp2=gross_rr_2,
        gross_rr_tp3=gross_rr_3,
        net_rr_tp1=net_rr_1,
        net_rr_tp2=net_rr_2,
        net_rr_tp3=net_rr_3,
        risk_amount_usdt=risk_budget_usdt if confirmation_gate_passed else 0.0,
        position_size_units=round(units, 6) if confirmation_gate_passed else 0.0,
        position_notional_usdt=round(notional_usdt, 2) if confirmation_gate_passed else 0.0,
        required_margin_usdt=round(margin_usdt, 2) if confirmation_gate_passed else 0.0,
        leverage_used=round(req.leverage, 2),
        confirmation_gate_passed=confirmation_gate_passed,
        duplicate_suppressed=duplicate_suppressed,
        duplicate_fingerprint=fingerprint,
        rejection_reasons=rejection_reasons,
    )

    if final_decision in ("LONG", "SHORT") and selected_hyp is not None:
        inval_level = selected_hyp.invalidation_price
        inval_rule = selected_hyp.invalidation_reason
        rr_summary = f"Net {net_rr_1:.2f}R / {net_rr_2:.2f}R / {net_rr_3:.2f}R (after {req.fee_pct + req.slippage_pct:.2f}%/side cost)"
        out_ez_low = selected_hyp.proposed_entry_zone_low
        out_ez_high = selected_hyp.proposed_entry_zone_high
        out_entry = selected_hyp.proposed_entry
        out_sl = selected_hyp.proposed_stop_loss
        out_tp1 = selected_hyp.proposed_tp1
        out_tp2 = selected_hyp.proposed_tp2
        out_tp3 = selected_hyp.proposed_tp3
    else:
        inval_level = preview_hyp.invalidation_price
        inval_rule = " ; ".join(rejection_reasons) if rejection_reasons else "Confirmation conditions not met."
        rr_summary = f"NO TRADE (Theoretical preview: {net_rr_2:.2f}R net)"
        out_ez_low = preview_hyp.proposed_entry_zone_low
        out_ez_high = preview_hyp.proposed_entry_zone_high
        out_entry = preview_hyp.proposed_entry
        out_sl = preview_hyp.proposed_stop_loss
        out_tp1 = preview_hyp.proposed_tp1
        out_tp2 = preview_hyp.proposed_tp2
        out_tp3 = preview_hyp.proposed_tp3

    now_iso = datetime.now(timezone.utc).isoformat()
    return TradeOpportunityResponse(
        opportunity_id=None,
        symbol=mtf.symbol,
        htf_timeframe=req.htf_timeframe,
        ltf_timeframe=req.ltf_timeframe,
        decision=final_decision,
        live_execution_blocked=True,
        execution_mode="ANALYSIS_ONLY_NO_LIVE_ORDERS",
        last_price=round(last_price, 6),
        entry_zone_low=out_ez_low,
        entry_zone_high=out_ez_high,
        entry_price=out_entry,
        stop_loss=out_sl,
        tp1=out_tp1,
        tp2=out_tp2,
        tp3=out_tp3,
        invalidation_level=inval_level,
        invalidation_rule=inval_rule,
        risk_reward_summary=rr_summary,
        long_hypothesis=long_hyp,
        short_hypothesis=short_hyp,
        risk_governance=risk_gov,
        market_context={
            "htf_bias": mtf.market_bias,
            "market_regime": mtf.market_regime,
            "market_phase": mtf.market_phase,
            "htf_alignment_score": mtf.htf_alignment_score,
            "ltf_setup_status": mtf.ltf_confirmation.setup_status,
            "premium_discount_zone": htf.premium_discount.zone,
        },
        candle_time=candle_time,
        analyzed_at=now_iso,
    )


def _persist_opportunity(res: TradeOpportunityResponse) -> int:
    fp = res.risk_governance.duplicate_fingerprint or _compute_fingerprint(
        res.symbol,
        res.htf_timeframe,
        res.ltf_timeframe,
        res.decision,
        res.entry_zone_low,
        res.entry_zone_high,
        res.stop_loss,
    )
    with get_db_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_opportunities (
                fingerprint, symbol, timeframe, ltf_timeframe, decision,
                long_passed, short_passed, entry_zone_low, entry_zone_high,
                entry_price, stop_loss, tp1, tp2, tp3, gross_rr, net_rr,
                position_size_units, position_notional_usdt, risk_amount_usdt,
                fee_cost_usdt, slippage_cost_usdt, daily_loss_used_pct,
                daily_limit_breached, is_duplicate, invalidation_reason,
                payload_json, candle_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fp,
                res.symbol,
                res.htf_timeframe,
                res.ltf_timeframe,
                res.decision,
                res.long_hypothesis.passed_count,
                res.short_hypothesis.passed_count,
                res.entry_zone_low,
                res.entry_zone_high,
                res.entry_price,
                res.stop_loss,
                res.tp1,
                res.tp2,
                res.tp3,
                res.risk_governance.gross_rr_tp2,
                res.risk_governance.net_rr_tp2,
                res.risk_governance.position_size_units,
                res.risk_governance.position_notional_usdt,
                res.risk_governance.risk_amount_usdt,
                res.risk_governance.estimated_fee_usdt,
                res.risk_governance.estimated_slippage_usdt,
                res.risk_governance.daily_total_loss_pct,
                1 if res.risk_governance.daily_limit_breached else 0,
                1 if res.risk_governance.duplicate_suppressed else 0,
                res.invalidation_rule,
                json.dumps(res.model_dump()),
                res.candle_time,
                res.analyzed_at,
            ),
        )
        return int(cur.lastrowid)


async def discover_trade_opportunity(req: TradeOpportunityRequest) -> TradeOpportunityResponse:
    prof = get_risk_profile()
    paper = await get_paper_state()

    account_balance = float(req.account_balance or prof.account_balance or paper.total_equity_usdt or 10000.0)
    daily_realized_loss_pct, daily_unrealized_loss_pct = _compute_today_paper_loss_pct(
        account_balance, paper.unrealized_pnl_usdt
    )

    mtf = await analyze_multi_timeframe(
        symbol=req.symbol.strip().upper(),
        ltf_interval=req.ltf_timeframe,
        persist=False,
    )

    result = evaluate_trade_opportunity_from_analysis(
        mtf=mtf,
        req=req,
        account_balance=account_balance,
        daily_realized_loss_pct=daily_realized_loss_pct,
        daily_unrealized_loss_pct=daily_unrealized_loss_pct,
    )

    if req.persist:
        result.opportunity_id = _persist_opportunity(result)
        logger.info(
            "Trade discovery evaluated %s (%s/%s): decision=%s, L=%d/5, S=%d/5",
            result.symbol,
            result.htf_timeframe,
            result.ltf_timeframe,
            result.decision,
            result.long_hypothesis.passed_count,
            result.short_hypothesis.passed_count,
        )

    return result


async def scan_all_opportunities(
    ltf_timeframe: str = "1h",
    risk_pct: float = 1.0,
    max_daily_loss_pct: float = 3.0,
    fee_pct: float = 0.06,
    slippage_pct: float = 0.04,
) -> TradeOpportunityScanResponse:
    symbols = get_tracked_symbol_names()[:8]
    tasks = [
        discover_trade_opportunity(
            TradeOpportunityRequest(
                symbol=sym,
                htf_timeframe="4h",
                ltf_timeframe=ltf_timeframe,
                risk_pct=risk_pct,
                max_daily_loss_pct=max_daily_loss_pct,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
                persist=False,
            )
        )
        for sym in symbols
    ]
    items = await asyncio.gather(*tasks)
    # Sort actionable decisions (LONG/SHORT) first, then highest max hypothesis score
    items_sorted = sorted(
        items,
        key=lambda x: (
            1 if x.decision in ("LONG", "SHORT") else 0,
            max(x.long_hypothesis.score_pct, x.short_hypothesis.score_pct),
        ),
        reverse=True,
    )
    any_breach = any(it.risk_governance.daily_limit_breached for it in items_sorted)
    return TradeOpportunityScanResponse(
        htf_timeframe="4h",
        ltf_timeframe=ltf_timeframe,
        risk_pct=risk_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        daily_limit_breached=any_breach,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        live_execution_blocked=True,
        items=items_sorted,
    )


def get_opportunity_history(limit: int = 15) -> list[TradeOpportunityHistoryItem]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, fingerprint, symbol, timeframe, ltf_timeframe, decision,
                   long_passed, short_passed, entry_price, stop_loss, tp1, tp2, tp3,
                   net_rr, position_size_units, daily_loss_used_pct,
                   daily_limit_breached, is_duplicate, invalidation_reason, created_at
            FROM trade_opportunities
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        TradeOpportunityHistoryItem(
            id=int(r["id"]),
            fingerprint=str(r["fingerprint"]),
            symbol=str(r["symbol"]),
            timeframe=str(r["timeframe"]),
            ltf_timeframe=str(r["ltf_timeframe"]),
            decision=r["decision"],
            long_passed=int(r["long_passed"]),
            short_passed=int(r["short_passed"]),
            entry_price=r["entry_price"],
            stop_loss=r["stop_loss"],
            tp1=r["tp1"],
            tp2=r["tp2"],
            tp3=r["tp3"],
            net_rr=r["net_rr"],
            position_size_units=r["position_size_units"],
            daily_loss_used_pct=float(r["daily_loss_used_pct"]),
            daily_limit_breached=bool(r["daily_limit_breached"]),
            is_duplicate=bool(r["is_duplicate"]),
            invalidation_reason=r["invalidation_reason"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]
