from datetime import datetime, timezone
import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.exceptions import ExternalMarketDataError
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.schemas.common import CandlePoint, MarketKlinesResponse, MarketSummary
from app.services.http_resilient import fetch_json_resilient
from app.services.market_data_validator import validate_ohlcv_and_market_data
from app.services.symbol_registry import is_symbol_tracked

logger = get_logger("qazan.market")

ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"}
ALLOWED_INTERVALS = {"15m", "1h", "4h", "1d", "1w"}


def _compute_summary(candles: list[CandlePoint]) -> MarketSummary:
    df = pd.DataFrame([c.model_dump() for c in candles])
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    volumes = df["volume"].to_numpy(dtype=np.float64)

    period_open = float(opens[0])
    last_close = float(closes[-1])
    period_change_pct = (
        round(((last_close - period_open) / period_open) * 100.0, 2)
        if period_open > 0
        else 0.0
    )
    total_volume = float(np.sum(volumes))
    typical_price = (highs + lows + closes) / 3.0
    vwap = (
        float(np.sum(typical_price * volumes) / total_volume)
        if total_volume > 0
        else last_close
    )

    return MarketSummary(
        last_close=round(last_close, 4),
        period_open=round(period_open, 4),
        period_change_pct=period_change_pct,
        period_high=round(float(np.max(highs)), 4),
        period_low=round(float(np.min(lows)), 4),
        total_volume=round(total_volume, 4),
        vwap=round(vwap, 4),
    )


def _save_candles_to_cache(symbol: str, interval: str, candles: list[CandlePoint], fetched_at: str) -> None:
    rows = [
        (symbol, interval, c.time, c.open, c.high, c.low, c.close, c.volume, fetched_at)
        for c in candles
    ]
    with get_db_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO market_candles_cache
                (symbol, interval, open_time, open, high, low, close, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _load_candles_from_cache(symbol: str, interval: str, limit: int) -> tuple[list[CandlePoint], str] | None:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT open_time, open, high, low, close, volume, fetched_at
            FROM market_candles_cache
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time DESC
            LIMIT ?
            """,
            (symbol, interval, limit),
        ).fetchall()

    if not rows:
        return None

    ordered = list(reversed(rows))
    fetched_at = ordered[-1]["fetched_at"]
    candles = [
        CandlePoint(
            time=int(r["open_time"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
        )
        for r in ordered
    ]
    return candles, fetched_at


async def fetch_market_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 120,
) -> MarketKlinesResponse:
    norm_symbol = symbol.strip().upper()
    norm_interval = interval.strip()

    if norm_symbol not in ALLOWED_SYMBOLS and not is_symbol_tracked(norm_symbol):
        raise ExternalMarketDataError(
            f"Unsupported trading pair '{norm_symbol}'.",
            details="Register the symbol first via /api/v1/data/symbols or select a tracked pair.",
        )
    if norm_interval not in ALLOWED_INTERVALS:
        raise ExternalMarketDataError(
            f"Unsupported timeframe '{norm_interval}'.",
            details=f"Allowed intervals: {', '.join(sorted(ALLOWED_INTERVALS))}",
        )

    settings = get_settings()
    endpoint = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/klines"
    params = {"symbol": norm_symbol, "interval": norm_interval, "limit": limit}

    try:
        res = await fetch_json_resilient(
            endpoint,
            params=params,
            timeout=settings.MARKET_DATA_TIMEOUT_SEC,
            max_retries=2,
        )
        raw_klines = res.data

        if not isinstance(raw_klines, list) or len(raw_klines) == 0:
            raise ExternalMarketDataError(
                "Market data provider returned an empty candle set.",
                details=f"Symbol={norm_symbol}, Interval={norm_interval}",
            )

        candles = [
            CandlePoint(
                time=int(item[0]) // 1000,
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
            )
            for item in raw_klines
        ]

        validation = validate_ohlcv_and_market_data(norm_symbol, norm_interval, candles)
        if validation.invalid_bars > 0:
            logger.warning(
                "Detected %d invalid OHLCV bars for %s (%s); filtering invalid rows.",
                validation.invalid_bars,
                norm_symbol,
                norm_interval,
            )
            candles = [
                c
                for c in candles
                if c.open > 0
                and c.high >= max(c.open, c.close)
                and c.low <= min(c.open, c.close)
                and c.volume >= 0
            ]
            if not candles:
                raise ExternalMarketDataError("All fetched OHLCV bars failed validation.")

        _save_candles_to_cache(norm_symbol, norm_interval, candles, res.fetched_at)
        summary = _compute_summary(candles)

        return MarketKlinesResponse(
            symbol=norm_symbol,
            interval=norm_interval,
            source="Binance Public REST API (Keyless)",
            cached_fallback=False,
            fetched_at=res.fetched_at,
            candle_count=len(candles),
            summary=summary,
            candles=candles,
        )

    except ExternalMarketDataError:
        raise
    except Exception as exc:
        logger.warning(
            "Upstream market API failed for %s (%s): %s. Checking SQLite cache.",
            norm_symbol,
            norm_interval,
            str(exc),
        )
        cached = _load_candles_from_cache(norm_symbol, norm_interval, limit)
        if cached is not None:
            candles, cached_at = cached
            summary = _compute_summary(candles)
            return MarketKlinesResponse(
                symbol=norm_symbol,
                interval=norm_interval,
                source="SQLite Local Cache (Upstream Unavailable)",
                cached_fallback=True,
                fetched_at=cached_at,
                candle_count=len(candles),
                summary=summary,
                candles=candles,
            )

        raise ExternalMarketDataError(
            f"Unable to fetch live market data for {norm_symbol} and no SQLite cache is available.",
            details=str(exc),
        ) from exc
