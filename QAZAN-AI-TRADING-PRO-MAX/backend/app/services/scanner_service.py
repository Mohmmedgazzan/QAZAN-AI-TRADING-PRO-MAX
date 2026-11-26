import asyncio
from datetime import datetime, timezone
import numpy as np

from app.schemas.platform import ScannerItem, TradeScannerResponse
from app.services.market_service import ALLOWED_SYMBOLS, fetch_market_klines
from app.services.quant_analysis_service import (
    candles_to_df,
    compute_atr,
    compute_rsi,
    detect_swings_and_structure,
)


async def _scan_single(symbol: str, interval: str) -> ScannerItem:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=150)
    df = candles_to_df(klines.candles)
    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    ema50 = df["close"].ewm(span=50, adjust=False).mean()
    rsi14 = compute_rsi(df["close"], 14)
    atr14 = compute_atr(df, 14)
    vol_avg = float(df["volume"].tail(20).mean()) or 1.0
    vol_ratio = float(df["volume"].iloc[-1]) / vol_avg

    _swings, _events, regime = detect_swings_and_structure(df, window=3)

    last_close = float(df["close"].iloc[-1])
    last_rsi = float(rsi14.iloc[-1])
    last_atr = float(atr14.iloc[-1])
    ema_trend = "BULLISH" if float(ema20.iloc[-1]) >= float(ema50.iloc[-1]) else "BEARISH"

    score = 50
    if ema_trend == "BULLISH":
        score += 15
    else:
        score -= 15
    if regime == "UPTREND":
        score += 15
    elif regime == "DOWNTREND":
        score -= 15
    if last_rsi < 35:
        score += 10
    elif last_rsi > 65:
        score -= 10
    if vol_ratio > 1.2:
        score += 5 if ema_trend == "BULLISH" else -5

    if score >= 65:
        signal = "LONG"
        sl = last_close - (last_atr * 1.5)
        tp = last_close + (last_atr * 3.0)
    elif score <= 35:
        signal = "SHORT"
        sl = last_close + (last_atr * 1.5)
        tp = last_close - (last_atr * 3.0)
    else:
        signal = "NEUTRAL"
        sl = last_close - (last_atr * 1.5)
        tp = last_close + (last_atr * 3.0)

    rr = abs(tp - last_close) / max(abs(last_close - sl), 1e-9)

    return ScannerItem(
        symbol=klines.symbol,
        last_price=round(last_close, 6),
        rsi_14=round(last_rsi, 2),
        ema_trend=ema_trend,
        structure_regime=regime,
        volume_ratio=round(vol_ratio, 2),
        signal=signal,
        suggested_entry=round(last_close, 6),
        stop_loss=round(max(sl, 0.0001), 6),
        take_profit=round(max(tp, 0.0001), 6),
        risk_reward=round(rr, 2),
        score=int(np.clip(score, 0, 100)),
    )


from app.services.symbol_registry import get_tracked_symbol_names


async def run_trade_scanner(interval: str = "1h") -> TradeScannerResponse:
    symbols = get_tracked_symbol_names() or sorted(ALLOWED_SYMBOLS)
    tasks = [_scan_single(sym, interval) for sym in symbols]
    items = await asyncio.gather(*tasks)
    items_sorted = sorted(items, key=lambda x: abs(x.score - 50), reverse=True)
    return TradeScannerResponse(
        interval=interval,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        items=items_sorted,
    )
