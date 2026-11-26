import json

from app.core.config import get_settings
from app.core.exceptions import ExternalMarketDataError
from app.core.logging import get_logger
from app.schemas.platform import MarketTickersResponse, Ticker24h
from app.services.http_resilient import fetch_json_resilient
from app.services.symbol_registry import get_tracked_symbol_names

logger = get_logger("qazan.tickers")


async def fetch_market_tickers() -> MarketTickersResponse:
    settings = get_settings()
    endpoint = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/ticker/24hr"
    tracked = get_tracked_symbol_names()
    params = {"symbols": json.dumps(tracked, separators=(",", ":"))}

    try:
        res = await fetch_json_resilient(
            endpoint,
            params=params,
            timeout=settings.MARKET_DATA_TIMEOUT_SEC,
            max_retries=2,
        )
        raw = res.data

        if not isinstance(raw, list) or len(raw) == 0:
            raise ExternalMarketDataError("Market ticker feed returned empty payload.")

        tickers: list[Ticker24h] = []
        for item in raw:
            last_p = float(item["lastPrice"])
            bid_p = float(item.get("bidPrice") or last_p)
            ask_p = float(item.get("askPrice") or last_p)
            spread_pct = round(((ask_p - bid_p) / last_p) * 100.0, 4) if last_p > 0 and ask_p >= bid_p else 0.0
            tickers.append(
                Ticker24h(
                    symbol=str(item["symbol"]),
                    last_price=round(last_p, 6),
                    price_change_pct=round(float(item["priceChangePercent"]), 2),
                    high_24h=round(float(item["highPrice"]), 6),
                    low_24h=round(float(item["lowPrice"]), 6),
                    volume_24h=round(float(item["volume"]), 4),
                    quote_volume_24h=round(float(item["quoteVolume"]), 2),
                    bid_price=round(bid_p, 6),
                    ask_price=round(ask_p, 6),
                    spread_pct=spread_pct,
                )
            )

        tickers.sort(key=lambda t: t.quote_volume_24h, reverse=True)
        return MarketTickersResponse(
            source="Binance Public 24hr Ticker REST API (Keyless)",
            fetched_at=res.fetched_at,
            tickers=tickers,
        )
    except ExternalMarketDataError:
        raise
    except Exception as exc:
        logger.error("Failed fetching 24h market tickers: %s", str(exc))
        raise ExternalMarketDataError(
            "Unable to fetch live 24h market tickers.",
            details=str(exc),
        ) from exc


async def fetch_spot_prices(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    settings = get_settings()
    endpoint = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/ticker/price"
    unique_syms = sorted({s.strip().upper() for s in symbols})
    params = {"symbols": json.dumps(unique_syms, separators=(",", ":"))}
    try:
        res = await fetch_json_resilient(
            endpoint,
            params=params,
            timeout=settings.MARKET_DATA_TIMEOUT_SEC,
            max_retries=2,
        )
        return {str(item["symbol"]): float(item["price"]) for item in res.data}
    except Exception as exc:
        raise ExternalMarketDataError(
            "Unable to fetch live spot prices for mark-to-market valuation.",
            details=str(exc),
        ) from exc
