from datetime import datetime, timezone
import numpy as np
import pandas as pd

from app.schemas.common import CandlePoint
from app.schemas.platform import (
    DealingRange,
    FairValueGap,
    IndicatorPoint,
    LiquidityAnalysisResponse,
    LiquidityLevel,
    LiquiditySweep,
    MarketStructureResponse,
    OrderBlock,
    SMCAnalysisResponse,
    StructureEvent,
    StructureSwingPoint,
    VolumeNode,
)
from app.services.market_service import fetch_market_klines


def candles_to_df(candles: list[CandlePoint]) -> pd.DataFrame:
    df = pd.DataFrame([c.model_dump() for c in candles])
    return df.sort_values("time").reset_index(drop=True)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean().bfill()


def detect_swings_and_structure(
    df: pd.DataFrame, window: int = 3
) -> tuple[list[StructureSwingPoint], list[StructureEvent], str]:
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    times = df["time"].to_numpy(dtype=np.int64)

    raw_swings: list[tuple[int, int, float, str]] = []
    n = len(df)
    for i in range(window, n - window):
        left_h = highs[i - window : i]
        right_h = highs[i + 1 : i + window + 1]
        if highs[i] > np.max(left_h) and highs[i] >= np.max(right_h):
            raw_swings.append((i, int(times[i]), float(highs[i]), "HIGH"))

        left_l = lows[i - window : i]
        right_l = lows[i + 1 : i + window + 1]
        if lows[i] < np.min(left_l) and lows[i] <= np.min(right_l):
            raw_swings.append((i, int(times[i]), float(lows[i]), "LOW"))

    raw_swings.sort(key=lambda x: x[0])

    swings: list[StructureSwingPoint] = []
    last_high: float | None = None
    last_low: float | None = None

    for _idx, ts, price, kind in raw_swings:
        if kind == "HIGH":
            label = "HH" if (last_high is None or price >= last_high) else "LH"
            last_high = price
        else:
            label = "HL" if (last_low is None or price >= last_low) else "LL"
            last_low = price
        swings.append(
            StructureSwingPoint(time=ts, price=round(price, 6), kind=kind, label=label)
        )

    # Detect BOS / CHoCH events where price closes beyond prior swing
    events: list[StructureEvent] = []
    trend_bias = "BULLISH"
    active_high: float | None = None
    active_low: float | None = None
    swing_by_idx = {item[0]: item for item in raw_swings}

    for i in range(n):
        if i in swing_by_idx:
            _, _t, price, kind = swing_by_idx[i]
            if kind == "HIGH":
                active_high = price
            else:
                active_low = price

        c = float(closes[i])
        t = int(times[i])

        if active_high is not None and c > active_high:
            ev_type = "BOS" if trend_bias == "BULLISH" else "CHoCH"
            events.append(
                StructureEvent(
                    time=t,
                    price=round(active_high, 6),
                    event_type=ev_type,
                    direction="BULLISH",
                )
            )
            trend_bias = "BULLISH"
            active_high = None

        elif active_low is not None and c < active_low:
            ev_type = "BOS" if trend_bias == "BEARISH" else "CHoCH"
            events.append(
                StructureEvent(
                    time=t,
                    price=round(active_low, 6),
                    event_type=ev_type,
                    direction="BEARISH",
                )
            )
            trend_bias = "BEARISH"
            active_low = None

    recent_labels = [s.label for s in swings[-4:]]
    if "HH" in recent_labels and "HL" in recent_labels and trend_bias == "BULLISH":
        regime = "UPTREND"
    elif "LH" in recent_labels and "LL" in recent_labels and trend_bias == "BEARISH":
        regime = "DOWNTREND"
    else:
        regime = "UPTREND" if trend_bias == "BULLISH" else "DOWNTREND" if len(events) > 0 else "RANGING"

    return swings[-16:], events[-12:], regime


async def analyze_market_structure(symbol: str, interval: str = "1h") -> MarketStructureResponse:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=180)
    df = candles_to_df(klines.candles)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["atr14"] = compute_atr(df, 14)

    swings, events, regime = detect_swings_and_structure(df, window=3)

    ema_20_series = [
        IndicatorPoint(time=int(row.time), value=round(float(row.ema20), 6))
        for row in df.itertuples()
    ]
    ema_50_series = [
        IndicatorPoint(time=int(row.time), value=round(float(row.ema50), 6))
        for row in df.itertuples()
    ]

    last = df.iloc[-1]
    return MarketStructureResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        regime=regime,
        last_close=round(float(last["close"]), 6),
        atr_14=round(float(last["atr14"]), 6),
        rsi_14=round(float(last["rsi14"]), 2),
        ema_20_last=round(float(last["ema20"]), 6),
        ema_50_last=round(float(last["ema50"]), 6),
        ema_20_series=ema_20_series,
        ema_50_series=ema_50_series,
        swings=swings,
        events=events,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


async def analyze_liquidity(symbol: str, interval: str = "1h") -> LiquidityAnalysisResponse:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=200)
    df = candles_to_df(klines.candles)
    atr_series = compute_atr(df, 14)
    tol = max(float(atr_series.iloc[-1]) * 0.35, float(df["close"].iloc[-1]) * 0.0015)
    last_close = float(df["close"].iloc[-1])

    swings, _events, _regime = detect_swings_and_structure(df, window=3)
    swing_highs = [s for s in swings if s.kind == "HIGH"]
    swing_lows = [s for s in swings if s.kind == "LOW"]

    def cluster_pools(points: list[StructureSwingPoint], side: str) -> list[LiquidityLevel]:
        pools: list[LiquidityLevel] = []
        used: set[int] = set()
        for idx, pt in enumerate(points):
            if idx in used:
                continue
            cluster = [pt]
            used.add(idx)
            for j in range(idx + 1, len(points)):
                if j not in used and abs(points[j].price - pt.price) <= tol:
                    cluster.append(points[j])
                    used.add(j)
            avg_price = float(np.mean([p.price for p in cluster]))
            dist_pct = round(((avg_price - last_close) / last_close) * 100.0, 2)
            pools.append(
                LiquidityLevel(
                    price=round(avg_price, 6),
                    side=side,
                    touches=len(cluster),
                    first_time=min(p.time for p in cluster),
                    last_time=max(p.time for p in cluster),
                    distance_pct=dist_pct,
                )
            )
        pools.sort(key=lambda x: (x.touches, -abs(x.distance_pct)), reverse=True)
        return pools[:6]

    bsl = cluster_pools(swing_highs, "BSL")
    ssl = cluster_pools(swing_lows, "SSL")

    # Detect recent wick liquidity sweeps
    sweeps: list[LiquiditySweep] = []
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    times = df["time"].to_numpy(dtype=np.int64)

    for i in range(20, len(df)):
        prior_high = float(np.max(highs[i - 20 : i]))
        prior_low = float(np.min(lows[i - 20 : i]))
        if highs[i] > prior_high and closes[i] < prior_high:
            sweeps.append(
                LiquiditySweep(
                    time=int(times[i]),
                    side="BSL_SWEEP",
                    swept_level=round(prior_high, 6),
                    wick_extreme=round(float(highs[i]), 6),
                    close_price=round(float(closes[i]), 6),
                )
            )
        elif lows[i] < prior_low and closes[i] > prior_low:
            sweeps.append(
                LiquiditySweep(
                    time=int(times[i]),
                    side="SSL_SWEEP",
                    swept_level=round(prior_low, 6),
                    wick_extreme=round(float(lows[i]), 6),
                    close_price=round(float(closes[i]), 6),
                )
            )

    # Volume profile across 12 bins
    p_min = float(df["low"].min())
    p_max = float(df["high"].max())
    bins = np.linspace(p_min, p_max, 13) if p_max > p_min else np.linspace(p_min * 0.99, p_min * 1.01, 13)
    typical = ((df["high"] + df["low"] + df["close"]) / 3.0).to_numpy(dtype=np.float64)
    vols = df["volume"].to_numpy(dtype=np.float64)
    total_vol = float(np.sum(vols)) or 1.0

    bin_vols = []
    for b in range(12):
        lo, hi = float(bins[b]), float(bins[b + 1])
        mask = (typical >= lo) & (typical <= hi if b == 11 else typical < hi)
        v = float(np.sum(vols[mask]))
        bin_vols.append((lo, hi, v))

    poc_idx = int(np.argmax([bv[2] for bv in bin_vols]))
    poc_price = round((bin_vols[poc_idx][0] + bin_vols[poc_idx][1]) / 2.0, 6)

    profile = [
        VolumeNode(
            price_low=round(lo, 6),
            price_high=round(hi, 6),
            price_mid=round((lo + hi) / 2.0, 6),
            volume=round(v, 4),
            share_pct=round((v / total_vol) * 100.0, 2),
            is_poc=(idx == poc_idx),
        )
        for idx, (lo, hi, v) in enumerate(bin_vols)
    ]

    return LiquidityAnalysisResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        last_close=round(last_close, 6),
        poc_price=poc_price,
        buy_side_pools=bsl,
        sell_side_pools=ssl,
        recent_sweeps=sweeps[-10:],
        volume_profile=profile,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


async def analyze_smc(symbol: str, interval: str = "1h") -> SMCAnalysisResponse:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=180)
    df = candles_to_df(klines.candles)
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    times = df["time"].to_numpy(dtype=np.int64)
    last_close = float(closes[-1])

    # Fair Value Gaps (3-candle imbalance)
    fvgs: list[FairValueGap] = []
    for i in range(2, len(df)):
        # Bullish FVG: candle[i].low > candle[i-2].high
        if lows[i] > highs[i - 2]:
            bottom = float(highs[i - 2])
            top = float(lows[i])
            mitigated = bool(np.min(lows[i + 1 :]) <= bottom) if i + 1 < len(df) else False
            fvgs.append(
                FairValueGap(
                    time=int(times[i - 1]),
                    direction="BULLISH",
                    top=round(top, 6),
                    bottom=round(bottom, 6),
                    mitigated=mitigated,
                )
            )
        # Bearish FVG: candle[i].high < candle[i-2].low
        elif highs[i] < lows[i - 2]:
            top = float(lows[i - 2])
            bottom = float(highs[i])
            mitigated = bool(np.max(highs[i + 1 :]) >= top) if i + 1 < len(df) else False
            fvgs.append(
                FairValueGap(
                    time=int(times[i - 1]),
                    direction="BEARISH",
                    top=round(top, 6),
                    bottom=round(bottom, 6),
                    mitigated=mitigated,
                )
            )

    # Order Blocks (last opposite candle before impulsive move > 1.3x ATR)
    atr = compute_atr(df, 14).to_numpy(dtype=np.float64)
    obs: list[OrderBlock] = []
    for i in range(1, len(df) - 1):
        body_next = abs(closes[i + 1] - opens[i + 1])
        if body_next >= atr[i] * 1.3:
            # Bullish OB: bearish candle followed by strong bullish displacement
            if closes[i] < opens[i] and closes[i + 1] > opens[i + 1]:
                mitigated = bool(np.min(lows[i + 2 :]) <= lows[i]) if i + 2 < len(df) else False
                obs.append(
                    OrderBlock(
                        time=int(times[i]),
                        direction="BULLISH",
                        high=round(float(highs[i]), 6),
                        low=round(float(lows[i]), 6),
                        mitigated=mitigated,
                    )
                )
            # Bearish OB: bullish candle followed by strong bearish displacement
            elif closes[i] > opens[i] and closes[i + 1] < opens[i + 1]:
                mitigated = bool(np.max(highs[i + 2 :]) >= highs[i]) if i + 2 < len(df) else False
                obs.append(
                    OrderBlock(
                        time=int(times[i]),
                        direction="BEARISH",
                        high=round(float(highs[i]), 6),
                        low=round(float(lows[i]), 6),
                        mitigated=mitigated,
                    )
                )

    # Dealing Range (last 60 candles)
    recent_slice = df.tail(60)
    r_high = float(recent_slice["high"].max())
    r_low = float(recent_slice["low"].min())
    eq = (r_high + r_low) / 2.0
    pos_pct = ((last_close - r_low) / (r_high - r_low) * 100.0) if r_high > r_low else 50.0
    zone = "PREMIUM" if pos_pct > 55.0 else "DISCOUNT" if pos_pct < 45.0 else "EQUILIBRIUM"

    return SMCAnalysisResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        last_close=round(last_close, 6),
        dealing_range=DealingRange(
            range_high=round(r_high, 6),
            range_low=round(r_low, 6),
            equilibrium=round(eq, 6),
            current_zone=zone,
            position_pct=round(pos_pct, 2),
        ),
        fair_value_gaps=fvgs[-10:],
        order_blocks=obs[-10:],
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )
