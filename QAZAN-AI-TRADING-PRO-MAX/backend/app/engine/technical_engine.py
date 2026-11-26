from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

from app.core.exceptions import ExternalMarketDataError
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.engine.models import (
    BreakerBlock,
    CausalFairValueGap,
    CausalLiquiditySweep,
    CausalOrderBlock,
    CausalStructureEvent,
    EngineSwingPoint,
    EqualLevelCluster,
    LevelBreachEvent,
    LiquidityPoolNode,
    LTFConfirmationResult,
    MultiTimeframeAnalysisResponse,
    PendingBreakoutState,
    PremiumDiscountZone,
    SingleTimeframeAnalysis,
    SupplyDemandZone,
    TechnicalRunHistoryItem,
)
from app.services.market_service import fetch_market_klines

logger = get_logger("qazan.engine")

INTERVAL_SECONDS: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

PRIMARY_HTF_LIST = ["1w", "1d", "4h"]


def _compute_atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean().bfill()
    return atr.to_numpy(dtype=np.float64)


def _compute_rsi_series(closes: pd.Series, period: int = 14) -> np.ndarray:
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)
    return rsi.to_numpy(dtype=np.float64)


def _compute_adx_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean().replace(0.0, np.nan)
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * ((plus_di - minus_di).abs() / denom)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean().fillna(20.0)
    return adx.to_numpy(dtype=np.float64)


def filter_closed_candles(
    df: pd.DataFrame,
    timeframe: str,
    as_of_ts: int | None = None,
) -> tuple[pd.DataFrame, bool]:
    """
    Exclude an active unclosed candle when as_of_ts is supplied so structural
    breaks are never confirmed prior to bar close.
    """
    ordered = df.sort_values("time").reset_index(drop=True)
    if as_of_ts is None or len(ordered) < 2:
        return ordered, False

    interval_sec = INTERVAL_SECONDS.get(timeframe.lower(), 3600)
    last_open = int(ordered["time"].iloc[-1])
    if last_open + interval_sec > as_of_ts:
        return ordered.iloc[:-1].reset_index(drop=True), True
    return ordered, False


def analyze_dataframe_causal(
    df: pd.DataFrame,
    timeframe: str,
    swing_left: int = 3,
    swing_right: int = 3,
    as_of_ts: int | None = None,
) -> SingleTimeframeAnalysis:
    """
    Strictly causal bar-by-bar technical analysis engine.
    At every closed bar t, ONLY information from bars <= t is visible:
      - Swing pivots at p require confirmation at t = p + swing_right.
      - Breakouts require bar close beyond the level AND structural hold confirmation
        (distinguishing BREAKOUT vs FAKEOUT vs STOP_HUNT).
      - Order Blocks, Breaker Blocks, Supply/Demand, and FVGs evolve forward causally.
    """
    norm_tf = timeframe.lower()
    closed_df, unclosed_excluded = filter_closed_candles(df, norm_tf, as_of_ts=as_of_ts)
    n = len(closed_df)
    if n < 25:
        raise ExternalMarketDataError(
            f"Insufficient closed OHLCV bars ({n}) on {timeframe} for causal technical analysis.",
            details="At least 25 closed candles are required.",
        )

    opens = closed_df["open"].to_numpy(dtype=np.float64)
    highs = closed_df["high"].to_numpy(dtype=np.float64)
    lows = closed_df["low"].to_numpy(dtype=np.float64)
    closes = closed_df["close"].to_numpy(dtype=np.float64)
    times = closed_df["time"].to_numpy(dtype=np.int64)

    atr_arr = _compute_atr_series(closed_df, 14)
    rsi_arr = _compute_rsi_series(closed_df["close"], 14)
    adx_arr = _compute_adx_series(closed_df, 14)

    # Causal state containers
    confirmed_swings: list[dict] = []
    last_swing_high_price: float | None = None
    last_swing_low_price: float | None = None

    active_sh_idx: int | None = None
    active_sl_idx: int | None = None
    pending_breach: dict | None = None

    structure_bias = "NEUTRAL"
    structure_events: list[CausalStructureEvent] = []
    level_breaches: list[LevelBreachEvent] = []
    sweeps: list[CausalLiquiditySweep] = []

    fvgs: list[dict] = []
    order_blocks: list[dict] = []
    breaker_blocks: list[dict] = []
    supply_demand: list[dict] = []

    for t in range(n):
        o = float(opens[t])
        h = float(highs[t])
        l = float(lows[t])
        c = float(closes[t])
        ts = int(times[t])
        atr = max(float(atr_arr[t]), c * 1e-4)
        bar_range = max(h - l, 1e-9)

        # ------------------------------------------------------------------
        # 1. Causal Swing Pivot Confirmation (pivot p confirmed ONLY at t = p + swing_right)
        # ------------------------------------------------------------------
        p = t - swing_right
        if p >= swing_left:
            # Swing High check up to t (strictly causal: highs[p+1 : t+1])
            left_h = highs[p - swing_left : p]
            right_h = highs[p + 1 : t + 1]
            if highs[p] > np.max(left_h) and highs[p] >= np.max(right_h):
                p_price = float(highs[p])
                label = "HH" if (last_swing_high_price is None or p_price >= last_swing_high_price) else "LH"
                last_swing_high_price = p_price
                sw_entry = {
                    "pivot_index": p,
                    "pivot_time": int(times[p]),
                    "confirmed_index": t,
                    "confirmed_time": ts,
                    "price": p_price,
                    "kind": "SWING_HIGH",
                    "label": label,
                    "swept": False,
                    "broken": False,
                }
                confirmed_swings.append(sw_entry)
                active_sh_idx = len(confirmed_swings) - 1

            # Swing Low check up to t
            left_l = lows[p - swing_left : p]
            right_l = lows[p + 1 : t + 1]
            if lows[p] < np.min(left_l) and lows[p] <= np.min(right_l):
                p_price = float(lows[p])
                label = "HL" if (last_swing_low_price is None or p_price >= last_swing_low_price) else "LL"
                last_swing_low_price = p_price
                sw_entry = {
                    "pivot_index": p,
                    "pivot_time": int(times[p]),
                    "confirmed_index": t,
                    "confirmed_time": ts,
                    "price": p_price,
                    "kind": "SWING_LOW",
                    "label": label,
                    "swept": False,
                    "broken": False,
                }
                confirmed_swings.append(sw_entry)
                active_sl_idx = len(confirmed_swings) - 1

        # Determine causal dealing range bounds before evaluating scope
        recent_highs = [s["price"] for s in confirmed_swings if s["kind"] == "SWING_HIGH"]
        recent_lows = [s["price"] for s in confirmed_swings if s["kind"] == "SWING_LOW"]
        range_hi = max(recent_highs[-3:]) if recent_highs else float(np.max(highs[max(0, t - 30) : t + 1]))
        range_lo = min(recent_lows[-3:]) if recent_lows else float(np.min(lows[max(0, t - 30) : t + 1]))

        # ------------------------------------------------------------------
        # 2. Update Causal Mitigation & Polarity Flip (FVG, OB, Breaker, Supply/Demand)
        # ------------------------------------------------------------------
        for fvg in fvgs:
            if fvg["status"] == "MITIGATED":
                continue
            if fvg["direction"] == "BULLISH":
                if l <= fvg["bottom"]:
                    fvg["status"] = "MITIGATED"
                elif l < fvg["top"]:
                    fvg["status"] = "PARTIALLY_FILLED"
            else:
                if h >= fvg["top"]:
                    fvg["status"] = "MITIGATED"
                elif h > fvg["bottom"]:
                    fvg["status"] = "PARTIALLY_FILLED"

        for ob in order_blocks:
            if ob["status"] == "INVALIDATED":
                continue
            if ob["direction"] == "BULLISH":
                if c < ob["low"]:
                    ob["status"] = "INVALIDATED"
                    breaker_blocks.append(
                        {
                            "direction": "BEARISH_BREAKER",
                            "high": ob["high"],
                            "low": ob["low"],
                            "origin_ob_time": ob["formed_time"],
                            "flipped_time": ts,
                            "status": "ACTIVE",
                        }
                    )
                elif l <= ob["high"] and ob["status"] == "ACTIVE":
                    ob["status"] = "MITIGATED"
            else:
                if c > ob["high"]:
                    ob["status"] = "INVALIDATED"
                    breaker_blocks.append(
                        {
                            "direction": "BULLISH_BREAKER",
                            "high": ob["high"],
                            "low": ob["low"],
                            "origin_ob_time": ob["formed_time"],
                            "flipped_time": ts,
                            "status": "ACTIVE",
                        }
                    )
                elif h >= ob["low"] and ob["status"] == "ACTIVE":
                    ob["status"] = "MITIGATED"

        for br in breaker_blocks:
            if br["status"] == "INVALIDATED":
                continue
            if br["direction"] == "BULLISH_BREAKER":
                if c < br["low"]:
                    br["status"] = "INVALIDATED"
                elif l <= br["high"] and br["status"] == "ACTIVE":
                    br["status"] = "MITIGATED"
            else:
                if c > br["high"]:
                    br["status"] = "INVALIDATED"
                elif h >= br["low"] and br["status"] == "ACTIVE":
                    br["status"] = "MITIGATED"

        for zone in supply_demand:
            if zone["status"] == "BROKEN":
                continue
            if zone["zone_type"] == "DEMAND":
                if c < zone["bottom"]:
                    zone["status"] = "BROKEN"
                elif l <= zone["top"] and h >= zone["bottom"]:
                    zone["touches"] += 1
                    zone["status"] = "TESTED"
            else:
                if c > zone["top"]:
                    zone["status"] = "BROKEN"
                elif h >= zone["bottom"] and l <= zone["top"]:
                    zone["touches"] += 1
                    zone["status"] = "TESTED"

        # ------------------------------------------------------------------
        # 3. Resolve Pending Breakout vs Fakeout (requires bar close hold!)
        # ------------------------------------------------------------------
        if pending_breach is not None:
            lvl = pending_breach["level"]
            side = pending_breach["side"]
            sw_idx = pending_breach["swing_idx"]
            bars_waited = t - pending_breach["breach_idx"]

            if side == "BULLISH":
                if c < lvl:
                    # Failed structural hold -> FAKEOUT (Bull Trap)
                    level_breaches.append(
                        LevelBreachEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            side="BULLISH",
                            classification="FAKEOUT",
                            structure_tag=None,
                            breach_close=round(pending_breach["breach_close"], 6),
                            confirmation_close=round(c, 6),
                            displacement_atr=round((pending_breach["breach_close"] - lvl) / atr, 2),
                            reason="Closed above resistance then snapped back inside level within confirmation window.",
                        )
                    )
                    confirmed_swings[sw_idx]["swept"] = True
                    pending_breach = None
                elif (c > lvl and l >= lvl - 0.30 * atr) or (bars_waited >= 2 and c > lvl):
                    # Structural hold confirmed -> BREAKOUT (BOS or CHoCH)
                    ev_type = "BOS" if structure_bias in {"BULLISH", "NEUTRAL"} else "CHoCH"
                    structure_bias = "BULLISH"
                    confirmed_swings[sw_idx]["broken"] = True
                    structure_events.append(
                        CausalStructureEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            event_type=ev_type,
                            direction="BULLISH",
                            confirmation_close=round(c, 6),
                        )
                    )
                    level_breaches.append(
                        LevelBreachEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            side="BULLISH",
                            classification="BREAKOUT",
                            structure_tag=ev_type,
                            breach_close=round(pending_breach["breach_close"], 6),
                            confirmation_close=round(c, 6),
                            displacement_atr=round((c - lvl) / atr, 2),
                            reason=f"Confirmed {ev_type} with closed-candle structural hold above swing high.",
                        )
                    )
                    active_sh_idx = None
                    pending_breach = None

            elif side == "BEARISH":
                if c > lvl:
                    # Failed structural hold -> FAKEOUT (Bear Trap)
                    level_breaches.append(
                        LevelBreachEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            side="BEARISH",
                            classification="FAKEOUT",
                            structure_tag=None,
                            breach_close=round(pending_breach["breach_close"], 6),
                            confirmation_close=round(c, 6),
                            displacement_atr=round((lvl - pending_breach["breach_close"]) / atr, 2),
                            reason="Closed below support then reclaimed level inside confirmation window.",
                        )
                    )
                    confirmed_swings[sw_idx]["swept"] = True
                    pending_breach = None
                elif (c < lvl and h <= lvl + 0.30 * atr) or (bars_waited >= 2 and c < lvl):
                    ev_type = "BOS" if structure_bias in {"BEARISH", "NEUTRAL"} else "CHoCH"
                    structure_bias = "BEARISH"
                    confirmed_swings[sw_idx]["broken"] = True
                    structure_events.append(
                        CausalStructureEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            event_type=ev_type,
                            direction="BEARISH",
                            confirmation_close=round(c, 6),
                        )
                    )
                    level_breaches.append(
                        LevelBreachEvent(
                            breach_time=pending_breach["breach_time"],
                            confirmed_time=ts,
                            level_price=round(lvl, 6),
                            side="BEARISH",
                            classification="BREAKOUT",
                            structure_tag=ev_type,
                            breach_close=round(pending_breach["breach_close"], 6),
                            confirmation_close=round(c, 6),
                            displacement_atr=round((lvl - c) / atr, 2),
                            reason=f"Confirmed {ev_type} with closed-candle structural hold below swing low.",
                        )
                    )
                    active_sl_idx = None
                    pending_breach = None

        # ------------------------------------------------------------------
        # 4. Detect New Stop Hunts & Pending Breakouts at Active Swings
        # ------------------------------------------------------------------
        if pending_breach is None and active_sh_idx is not None:
            sh = confirmed_swings[active_sh_idx]
            lvl = sh["price"]
            if h > lvl and c <= lvl:
                # Wick pierced high, closed back below -> STOP HUNT / BSL SWEEP
                wick_ratio = round((h - max(o, c)) / bar_range, 2)
                scope = "EXTERNAL" if lvl >= range_hi * 0.998 else "INTERNAL"
                sh["swept"] = True
                sweeps.append(
                    CausalLiquiditySweep(
                        time=ts,
                        side="BSL_SWEEP",
                        scope=scope,
                        swept_level=round(lvl, 6),
                        wick_extreme=round(h, 6),
                        close_price=round(c, 6),
                        wick_ratio=wick_ratio,
                    )
                )
                level_breaches.append(
                    LevelBreachEvent(
                        breach_time=ts,
                        confirmed_time=ts,
                        level_price=round(lvl, 6),
                        side="BULLISH",
                        classification="STOP_HUNT",
                        structure_tag=None,
                        breach_close=round(c, 6),
                        confirmation_close=round(c, 6),
                        displacement_atr=round((h - lvl) / atr, 2),
                        reason="Wick swept buy-side liquidity above swing high and closed back inside range.",
                    )
                )
            elif c > lvl and not sh["broken"]:
                pending_breach = {
                    "swing_idx": active_sh_idx,
                    "level": lvl,
                    "side": "BULLISH",
                    "breach_idx": t,
                    "breach_time": ts,
                    "breach_close": c,
                }

        if pending_breach is None and active_sl_idx is not None:
            sl = confirmed_swings[active_sl_idx]
            lvl = sl["price"]
            if l < lvl and c >= lvl:
                wick_ratio = round((min(o, c) - l) / bar_range, 2)
                scope = "EXTERNAL" if lvl <= range_lo * 1.002 else "INTERNAL"
                sl["swept"] = True
                sweeps.append(
                    CausalLiquiditySweep(
                        time=ts,
                        side="SSL_SWEEP",
                        scope=scope,
                        swept_level=round(lvl, 6),
                        wick_extreme=round(l, 6),
                        close_price=round(c, 6),
                        wick_ratio=wick_ratio,
                    )
                )
                level_breaches.append(
                    LevelBreachEvent(
                        breach_time=ts,
                        confirmed_time=ts,
                        level_price=round(lvl, 6),
                        side="BEARISH",
                        classification="STOP_HUNT",
                        structure_tag=None,
                        breach_close=round(c, 6),
                        confirmation_close=round(c, 6),
                        displacement_atr=round((lvl - l) / atr, 2),
                        reason="Wick swept sell-side liquidity below swing low and closed back inside range.",
                    )
                )
            elif c < lvl and not sl["broken"]:
                pending_breach = {
                    "swing_idx": active_sl_idx,
                    "level": lvl,
                    "side": "BEARISH",
                    "breach_idx": t,
                    "breach_time": ts,
                    "breach_close": c,
                }

        # ------------------------------------------------------------------
        # 5. Detect Causal FVG, Order Blocks, and Supply/Demand at Bar t
        # ------------------------------------------------------------------
        if t >= 2:
            if lows[t] > highs[t - 2]:
                bottom = float(highs[t - 2])
                top = float(lows[t])
                fvgs.append(
                    {
                        "direction": "BULLISH",
                        "top": top,
                        "bottom": bottom,
                        "ce_midpoint": (top + bottom) / 2.0,
                        "formed_time": int(times[t - 1]),
                        "confirmed_time": ts,
                        "status": "UNMITIGATED",
                    }
                )
            elif highs[t] < lows[t - 2]:
                top = float(lows[t - 2])
                bottom = float(highs[t])
                fvgs.append(
                    {
                        "direction": "BEARISH",
                        "top": top,
                        "bottom": bottom,
                        "ce_midpoint": (top + bottom) / 2.0,
                        "formed_time": int(times[t - 1]),
                        "confirmed_time": ts,
                        "status": "UNMITIGATED",
                    }
                )

        if t >= 2:
            body_t = abs(c - o)
            body_prev = abs(float(closes[t - 1]) - float(opens[t - 1]))
            if body_t >= 1.25 * atr:
                # Bullish Impulse -> Bullish OB + Demand Zone
                if c > o and closes[t - 1] < opens[t - 1]:
                    ob_hi = float(highs[t - 1])
                    ob_lo = float(lows[t - 1])
                    order_blocks.append(
                        {
                            "direction": "BULLISH",
                            "high": ob_hi,
                            "low": ob_lo,
                            "mean_threshold": (ob_hi + ob_lo) / 2.0,
                            "formed_time": int(times[t - 1]),
                            "confirmed_time": ts,
                            "status": "ACTIVE",
                        }
                    )
                    if body_prev <= 0.85 * atr:
                        pattern = "RBR" if closes[t - 2] > opens[t - 2] else "DBR"
                        supply_demand.append(
                            {
                                "zone_type": "DEMAND",
                                "pattern": pattern,
                                "top": max(float(opens[t - 1]), float(closes[t - 1])),
                                "bottom": ob_lo,
                                "formed_time": int(times[t - 1]),
                                "confirmed_time": ts,
                                "displacement_atr": round(body_t / atr, 2),
                                "status": "FRESH",
                                "touches": 0,
                            }
                        )
                # Bearish Impulse -> Bearish OB + Supply Zone
                elif c < o and closes[t - 1] > opens[t - 1]:
                    ob_hi = float(highs[t - 1])
                    ob_lo = float(lows[t - 1])
                    order_blocks.append(
                        {
                            "direction": "BEARISH",
                            "high": ob_hi,
                            "low": ob_lo,
                            "mean_threshold": (ob_hi + ob_lo) / 2.0,
                            "formed_time": int(times[t - 1]),
                            "confirmed_time": ts,
                            "status": "ACTIVE",
                        }
                    )
                    if body_prev <= 0.85 * atr:
                        pattern = "DBD" if closes[t - 2] < opens[t - 2] else "RBD"
                        supply_demand.append(
                            {
                                "zone_type": "SUPPLY",
                                "pattern": pattern,
                                "top": ob_hi,
                                "bottom": min(float(opens[t - 1]), float(closes[t - 1])),
                                "formed_time": int(times[t - 1]),
                                "confirmed_time": ts,
                                "displacement_atr": round(body_t / atr, 2),
                                "status": "FRESH",
                                "touches": 0,
                            }
                        )

    # ------------------------------------------------------------------
    # Post-loop Snapshot at Last Closed Candle (t = n - 1)
    # ------------------------------------------------------------------
    last_close = float(closes[-1])
    last_ts = int(times[-1])
    last_atr = float(atr_arr[-1])
    last_adx = float(adx_arr[-1])
    last_rsi = float(rsi_arr[-1])

    # Active Dealing Range from recent confirmed swings (or trailing 50 closed bars)
    sh_list = [s for s in confirmed_swings if s["kind"] == "SWING_HIGH"]
    sl_list = [s for s in confirmed_swings if s["kind"] == "SWING_LOW"]
    if sh_list and sl_list:
        dr_high = max(s["price"] for s in sh_list[-3:])
        dr_low = min(s["price"] for s in sl_list[-3:])
    else:
        tail_slice = closed_df.tail(min(50, n))
        dr_high = float(tail_slice["high"].max())
        dr_low = float(tail_slice["low"].min())
    if dr_high <= dr_low:
        dr_high = float(closed_df["high"].max())
        dr_low = float(closed_df["low"].min())

    eq = (dr_high + dr_low) / 2.0
    pos_pct = ((last_close - dr_low) / (dr_high - dr_low) * 100.0) if dr_high > dr_low else 50.0
    pos_pct = max(0.0, min(100.0, pos_pct))
    zone_label = "PREMIUM" if pos_pct > 55.0 else "DISCOUNT" if pos_pct < 45.0 else "EQUILIBRIUM"

    if structure_bias == "BEARISH":
        ote_low = dr_low + 0.618 * (dr_high - dr_low)
        ote_high = dr_low + 0.786 * (dr_high - dr_low)
    else:
        ote_low = dr_high - 0.786 * (dr_high - dr_low)
        ote_high = dr_high - 0.618 * (dr_high - dr_low)

    premium_discount = PremiumDiscountZone(
        range_high=round(dr_high, 6),
        range_low=round(dr_low, 6),
        equilibrium=round(eq, 6),
        ote_low=round(ote_low, 6),
        ote_high=round(ote_high, 6),
        position_pct=round(pos_pct, 2),
        zone=zone_label,
    )

    # Tag swings as EXTERNAL vs INTERNAL relative to active Dealing Range
    swing_models: list[EngineSwingPoint] = []
    for s in confirmed_swings:
        is_ext = (
            (s["kind"] == "SWING_HIGH" and s["price"] >= dr_high * 0.995)
            or (s["kind"] == "SWING_LOW" and s["price"] <= dr_low * 1.005)
        )
        swing_models.append(
            EngineSwingPoint(
                pivot_index=s["pivot_index"],
                pivot_time=s["pivot_time"],
                confirmed_index=s["confirmed_index"],
                confirmed_time=s["confirmed_time"],
                price=round(s["price"], 6),
                kind=s["kind"],
                label=s["label"],
                scope="EXTERNAL" if is_ext else "INTERNAL",
                swept=s["swept"],
                broken=s["broken"],
            )
        )

    swing_highs_out = [s for s in swing_models if s.kind == "SWING_HIGH"][-10:]
    swing_lows_out = [s for s in swing_models if s.kind == "SWING_LOW"][-10:]

    # Equal Highs / Equal Lows (EQH / EQL) within adaptive ATR tolerance
    tol = max(last_atr * 0.35, last_close * 0.0015)
    eq_clusters: list[EqualLevelCluster] = []

    def _find_eq(points: list[EngineSwingPoint], cluster_kind: str) -> None:
        used: set[int] = set()
        for i, pt in enumerate(points):
            if i in used:
                continue
            grp = [pt]
            used.add(i)
            for j in range(i + 1, len(points)):
                if j not in used and abs(points[j].price - pt.price) <= tol:
                    grp.append(points[j])
                    used.add(j)
            if len(grp) >= 2:
                eq_clusters.append(
                    EqualLevelCluster(
                        kind=cluster_kind,
                        avg_price=round(float(np.mean([g.price for g in grp])), 6),
                        touches=len(grp),
                        first_time=min(g.pivot_time for g in grp),
                        confirmed_time=max(g.confirmed_time for g in grp),
                        tolerance=round(tol, 6),
                        swept=all(g.swept for g in grp),
                    )
                )

    _find_eq([s for s in swing_models if s.kind == "SWING_HIGH"][-16:], "EQH")
    _find_eq([s for s in swing_models if s.kind == "SWING_LOW"][-16:], "EQL")

    # External vs Internal Liquidity Pools
    ext_liq: list[LiquidityPoolNode] = []
    int_liq: list[LiquidityPoolNode] = []

    for s in swing_models[-20:]:
        if s.broken:
            continue
        side = "BSL" if s.kind == "SWING_HIGH" else "SSL"
        dist = round(((s.price - last_close) / last_close) * 100.0, 2)
        node = LiquidityPoolNode(
            price=s.price,
            side=side,
            scope=s.scope,
            touches=1,
            pool_type="SWING_LEVEL",
            first_time=s.pivot_time,
            confirmed_time=s.confirmed_time,
            distance_pct=dist,
            swept=s.swept,
        )
        if s.scope == "EXTERNAL":
            ext_liq.append(node)
        else:
            int_liq.append(node)

    for cl in eq_clusters:
        side = "BSL" if cl.kind == "EQH" else "SSL"
        dist = round(((cl.avg_price - last_close) / last_close) * 100.0, 2)
        is_ext = (
            (side == "BSL" and cl.avg_price >= dr_high * 0.995)
            or (side == "SSL" and cl.avg_price <= dr_low * 1.005)
        )
        node = LiquidityPoolNode(
            price=cl.avg_price,
            side=side,
            scope="EXTERNAL" if is_ext else "INTERNAL",
            touches=cl.touches,
            pool_type=cl.kind,
            first_time=cl.first_time,
            confirmed_time=cl.confirmed_time,
            distance_pct=dist,
            swept=cl.swept,
        )
        if is_ext:
            ext_liq.append(node)
        else:
            int_liq.append(node)

    for fvg in fvgs[-12:]:
        if fvg["status"] != "MITIGATED" and dr_low < fvg["ce_midpoint"] < dr_high:
            side = "SSL" if fvg["direction"] == "BULLISH" else "BSL"
            dist = round(((fvg["ce_midpoint"] - last_close) / last_close) * 100.0, 2)
            int_liq.append(
                LiquidityPoolNode(
                    price=round(fvg["ce_midpoint"], 6),
                    side=side,
                    scope="INTERNAL",
                    touches=1,
                    pool_type="FVG_CE",
                    first_time=fvg["formed_time"],
                    confirmed_time=fvg["confirmed_time"],
                    distance_pct=dist,
                    swept=False,
                )
            )

    ext_liq.sort(key=lambda x: abs(x.distance_pct))
    int_liq.sort(key=lambda x: abs(x.distance_pct))

    # Market Regime (ADX + ATR Volatility ratio)
    atr_med = float(np.median(atr_arr[-min(50, n) :])) or last_atr
    vol_ratio = last_atr / atr_med
    if last_adx >= 25.0 and vol_ratio >= 0.95:
        market_regime = "TRENDING_EXPANSION"
    elif last_adx < 18.0 and vol_ratio <= 0.9:
        market_regime = "RANGING_COMPRESSION"
    elif last_adx < 22.0 and vol_ratio > 1.25:
        market_regime = "VOLATILE_CHOP"
    else:
        market_regime = "TRANSITIONAL"

    # Market Phase: Trend / Range / Correction
    recent_labels = [s.label for s in swing_models[-4:]]
    ema20 = float(closed_df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(closed_df["close"].ewm(span=50, adjust=False).mean().iloc[-1])

    if structure_bias == "BULLISH":
        if last_close < ema20 or (structure_events and structure_events[-1].event_type == "CHoCH" and pos_pct < 50.0):
            market_phase = "CORRECTION"
        elif "HH" in recent_labels or last_close >= ema20 >= ema50:
            market_phase = "TREND"
        else:
            market_phase = "CORRECTION"
    elif structure_bias == "BEARISH":
        if last_close > ema20 or (structure_events and structure_events[-1].event_type == "CHoCH" and pos_pct > 50.0):
            market_phase = "CORRECTION"
        elif "LL" in recent_labels or last_close <= ema20 <= ema50:
            market_phase = "TREND"
        else:
            market_phase = "CORRECTION"
    else:
        market_phase = "RANGE"

    if last_adx < 17.5 and ("LH" in recent_labels and "HL" in recent_labels):
        market_phase = "RANGE"

    # Derived Market Bias (strictly causal)
    if structure_bias == "BULLISH" and ema20 >= ema50 * 0.997:
        market_bias = "BULLISH"
    elif structure_bias == "BEARISH" and ema20 <= ema50 * 1.003:
        market_bias = "BEARISH"
    elif structure_bias in {"BULLISH", "BEARISH"}:
        market_bias = structure_bias
    else:
        market_bias = "NEUTRAL"

    pending_out = (
        PendingBreakoutState(
            breach_time=pending_breach["breach_time"],
            level_price=round(pending_breach["level"], 6),
            side=pending_breach["side"],
            breach_close=round(pending_breach["breach_close"], 6),
            bars_waited=(n - 1) - pending_breach["breach_idx"],
        )
        if pending_breach is not None
        else None
    )

    return SingleTimeframeAnalysis(
        timeframe=timeframe.upper(),
        closed_bars_analyzed=n,
        unclosed_bar_excluded=unclosed_excluded,
        last_closed_time=last_ts,
        last_close=round(last_close, 6),
        atr_14=round(last_atr, 6),
        adx_14=round(last_adx, 2),
        rsi_14=round(last_rsi, 2),
        market_bias=market_bias,
        market_regime=market_regime,
        market_phase=market_phase,
        premium_discount=premium_discount,
        swing_highs=swing_highs_out,
        swing_lows=swing_lows_out,
        hh_hl_lh_ll_sequence=swing_models[-14:],
        external_liquidity=ext_liq[:8],
        internal_liquidity=int_liq[:8],
        equal_highs_lows=eq_clusters[-8:],
        liquidity_sweeps=sweeps[-10:],
        structure_events=structure_events[-10:],
        level_breaches=level_breaches[-12:],
        pending_breakout=pending_out,
        supply_demand_zones=[
            SupplyDemandZone(
                zone_type=z["zone_type"],
                pattern=z["pattern"],
                top=round(z["top"], 6),
                bottom=round(z["bottom"], 6),
                formed_time=z["formed_time"],
                confirmed_time=z["confirmed_time"],
                displacement_atr=z["displacement_atr"],
                status=z["status"],
                touches=z["touches"],
            )
            for z in supply_demand[-10:]
        ],
        order_blocks=[
            CausalOrderBlock(
                direction=ob["direction"],
                high=round(ob["high"], 6),
                low=round(ob["low"], 6),
                mean_threshold=round(ob["mean_threshold"], 6),
                formed_time=ob["formed_time"],
                confirmed_time=ob["confirmed_time"],
                status=ob["status"],
            )
            for ob in order_blocks[-10:]
        ],
        breaker_blocks=[
            BreakerBlock(
                direction=br["direction"],
                high=round(br["high"], 6),
                low=round(br["low"], 6),
                origin_ob_time=br["origin_ob_time"],
                flipped_time=br["flipped_time"],
                status=br["status"],
            )
            for br in breaker_blocks[-10:]
        ],
        fair_value_gaps=[
            CausalFairValueGap(
                direction=f["direction"],
                top=round(f["top"], 6),
                bottom=round(f["bottom"], 6),
                ce_midpoint=round(f["ce_midpoint"], 6),
                formed_time=f["formed_time"],
                confirmed_time=f["confirmed_time"],
                status=f["status"],
            )
            for f in fvgs[-10:]
        ],
    )


def evaluate_ltf_confirmation(
    htf_bias: str,
    htf_anchor: SingleTimeframeAnalysis,
    ltf: SingleTimeframeAnalysis,
) -> LTFConfirmationResult:
    """
    Deterministic LTF entry confirmation: NEVER emits random signals.
    Requires:
      1. Non-neutral HTF bias.
      2. Price positioned inside an unmitigated/active HTF POI (OB, Breaker, FVG, or Supply/Demand)
         or aligned Premium/Discount zone.
      3. Closed-candle LTF structural shift (BOS/CHoCH) OR Liquidity Sweep in HTF direction.
    """
    spot = ltf.last_close
    if htf_bias == "NEUTRAL":
        return LTFConfirmationResult(
            timeframe=ltf.timeframe,
            htf_bias=htf_bias,
            price_in_htf_poi=False,
            matched_poi_description=None,
            ltf_structure_aligned=False,
            ltf_sweep_detected=False,
            setup_status="NO_SETUP",
            rationale="HTF bias is NEUTRAL; capital preserved with zero random signals.",
        )

    matched_poi: str | None = None
    want_dir = "BULLISH" if htf_bias == "BULLISH" else "BEARISH"

    for ob in reversed(htf_anchor.order_blocks):
        if ob.direction == want_dir and ob.status in {"ACTIVE", "MITIGATED"} and ob.low <= spot <= ob.high:
            matched_poi = f"4H {ob.direction} OB (${ob.low:,.2f}-${ob.high:,.2f})"
            break

    if matched_poi is None:
        for fvg in reversed(htf_anchor.fair_value_gaps):
            if fvg.direction == want_dir and fvg.status != "MITIGATED" and fvg.bottom <= spot <= fvg.top:
                matched_poi = f"4H {fvg.direction} FVG (${fvg.bottom:,.2f}-${fvg.top:,.2f})"
                break

    if matched_poi is None:
        want_breaker = "BULLISH_BREAKER" if want_dir == "BULLISH" else "BEARISH_BREAKER"
        for br in reversed(htf_anchor.breaker_blocks):
            if br.direction == want_breaker and br.status != "INVALIDATED" and br.low <= spot <= br.high:
                matched_poi = f"4H {br.direction} (${br.low:,.2f}-${br.high:,.2f})"
                break

    if matched_poi is None:
        want_sd = "DEMAND" if want_dir == "BULLISH" else "SUPPLY"
        for sd in reversed(htf_anchor.supply_demand_zones):
            if sd.zone_type == want_sd and sd.status != "BROKEN" and sd.bottom <= spot <= sd.top:
                matched_poi = f"4H {sd.zone_type} ({sd.pattern}) (${sd.bottom:,.2f}-${sd.top:,.2f})"
                break

    price_in_poi = matched_poi is not None
    ltf_struct_aligned = bool(
        ltf.structure_events and ltf.structure_events[-1].direction == want_dir
    )
    want_sweep = "SSL_SWEEP" if want_dir == "BULLISH" else "BSL_SWEEP"
    ltf_sweep = any(sw.side == want_sweep for sw in ltf.liquidity_sweeps[-3:])

    if price_in_poi and (ltf_struct_aligned or ltf_sweep):
        status = "CONFIRMED_LONG" if want_dir == "BULLISH" else "CONFIRMED_SHORT"
        rationale = f"Price inside {matched_poi} with closed-candle LTF {ltf.timeframe} confirmation."
    elif price_in_poi or ltf_struct_aligned:
        status = "WAIT_CONFIRMATION"
        rationale = "Partial HTF/LTF alignment; awaiting full POI mitigation and closed-candle trigger."
    else:
        status = "NO_SETUP"
        rationale = "Price is not inside an active HTF POI with LTF trigger; no trade setup emitted."

    return LTFConfirmationResult(
        timeframe=ltf.timeframe,
        htf_bias=htf_bias,
        price_in_htf_poi=price_in_poi,
        matched_poi_description=matched_poi,
        ltf_structure_aligned=ltf_struct_aligned,
        ltf_sweep_detected=ltf_sweep,
        setup_status=status,
        rationale=rationale,
    )


def _persist_technical_run(
    symbol: str,
    run_type: str,
    ltf_interval: str,
    market_bias: str,
    market_phase: str,
    market_regime: str,
    payload_json: str,
    created_at: str,
) -> int:
    with get_db_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO technical_analysis_runs
                (symbol, run_type, ltf_interval, market_bias, market_phase, market_regime, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                run_type,
                ltf_interval,
                market_bias,
                market_phase,
                market_regime,
                payload_json,
                created_at,
            ),
        )
        return int(cur.lastrowid)


def get_technical_run_history(limit: int = 15) -> list[TechnicalRunHistoryItem]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, run_type, ltf_interval, market_bias, market_phase, market_regime, created_at
            FROM technical_analysis_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [TechnicalRunHistoryItem(**dict(r)) for r in rows]


async def analyze_multi_timeframe(
    symbol: str,
    ltf_interval: str = "1h",
    persist: bool = True,
) -> MultiTimeframeAnalysisResponse:
    norm_symbol = symbol.strip().upper()
    norm_ltf = ltf_interval.strip().lower()
    if norm_ltf not in {"15m", "1h"}:
        norm_ltf = "1h"

    now_ts = int(datetime.now(timezone.utc).timestamp())
    now_iso = datetime.now(timezone.utc).isoformat()

    # Fetch real OHLCV across 1W, 1D, 4H + LTF confirmation timeframe
    k_1w = await fetch_market_klines(norm_symbol, "1w", limit=180)
    k_1d = await fetch_market_klines(norm_symbol, "1d", limit=240)
    k_4h = await fetch_market_klines(norm_symbol, "4h", limit=300)
    k_ltf = await fetch_market_klines(norm_symbol, norm_ltf, limit=240)

    df_1w = pd.DataFrame([c.model_dump() for c in k_1w.candles])
    df_1d = pd.DataFrame([c.model_dump() for c in k_1d.candles])
    df_4h = pd.DataFrame([c.model_dump() for c in k_4h.candles])
    df_ltf = pd.DataFrame([c.model_dump() for c in k_ltf.candles])

    a_1w = analyze_dataframe_causal(df_1w, "1w", as_of_ts=now_ts)
    a_1d = analyze_dataframe_causal(df_1d, "1d", as_of_ts=now_ts)
    a_4h = analyze_dataframe_causal(df_4h, "4h", as_of_ts=now_ts)
    a_ltf = analyze_dataframe_causal(df_ltf, norm_ltf, as_of_ts=now_ts)

    # Weighted Multi-TF Market Bias Consensus (1W 40%, 1D 35%, 4H 25%)
    score_map = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}
    weighted_bias = (
        0.40 * score_map[a_1w.market_bias]
        + 0.35 * score_map[a_1d.market_bias]
        + 0.25 * score_map[a_4h.market_bias]
    )
    if weighted_bias >= 0.25:
        consensus_bias = "BULLISH"
    elif weighted_bias <= -0.25:
        consensus_bias = "BEARISH"
    else:
        consensus_bias = "NEUTRAL"

    alignment_pct = round(abs(weighted_bias) * 100.0, 1)

    # Derive overall market phase from 1D + 4H interaction (e.g. 4H pullback inside 1D trend -> CORRECTION)
    if a_1d.market_bias in {"BULLISH", "BEARISH"} and a_4h.market_bias != a_1d.market_bias and a_4h.market_bias != "NEUTRAL":
        overall_phase = "CORRECTION"
    else:
        overall_phase = a_1d.market_phase

    overall_regime = a_1d.market_regime
    ltf_conf = evaluate_ltf_confirmation(consensus_bias, a_4h, a_ltf)

    result = MultiTimeframeAnalysisResponse(
        symbol=norm_symbol,
        primary_timeframes=["1W", "1D", "4H"],
        ltf_timeframe=norm_ltf.upper(),
        look_ahead_bias_prevented=True,
        market_bias=consensus_bias,
        market_regime=overall_regime,
        market_phase=overall_phase,
        htf_alignment_score=alignment_pct,
        timeframes={
            "1W": a_1w,
            "1D": a_1d,
            "4H": a_4h,
            norm_ltf.upper(): a_ltf,
        },
        ltf_confirmation=ltf_conf,
        analyzed_at=now_iso,
    )

    if persist:
        run_id = _persist_technical_run(
            symbol=norm_symbol,
            run_type="MULTI_TF_ANALYSIS",
            ltf_interval=norm_ltf.upper(),
            market_bias=consensus_bias,
            market_phase=overall_phase,
            market_regime=overall_regime,
            payload_json=result.model_dump_json(),
            created_at=now_iso,
        )
        result.run_id = run_id
        logger.info(
            "Recorded Multi-TF analysis #%d for %s: bias=%s phase=%s regime=%s ltf=%s",
            run_id,
            norm_symbol,
            consensus_bias,
            overall_phase,
            overall_regime,
            ltf_conf.setup_status,
        )

    return result
