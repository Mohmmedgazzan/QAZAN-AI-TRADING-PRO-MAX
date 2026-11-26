from datetime import datetime, timezone
import re

from app.core.config import get_settings
from app.core.exceptions import AppError, ExternalMarketDataError
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.schemas.ingestion import TrackedSymbolItem, TrackedSymbolsResponse
from app.services.http_resilient import UpstreamFetchError, fetch_json_resilient

logger = get_logger("qazan.symbols")

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{4,20}$")
CORE_LOCKED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}


def _infer_assets(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, "QUOTE"


def get_tracked_symbols() -> TrackedSymbolsResponse:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT symbol, base_asset, quote_asset, source, is_default, added_at
            FROM tracked_symbols
            ORDER BY
                CASE symbol
                    WHEN 'BTCUSDT' THEN 0
                    WHEN 'ETHUSDT' THEN 1
                    ELSE 2
                END,
                is_default DESC,
                added_at ASC
            """
        ).fetchall()

    items = [
        TrackedSymbolItem(
            symbol=r["symbol"],
            base_asset=r["base_asset"],
            quote_asset=r["quote_asset"],
            source=r["source"],
            is_default=bool(r["is_default"]),
            added_at=r["added_at"],
        )
        for r in rows
    ]
    return TrackedSymbolsResponse(total=len(items), symbols=items)


def get_tracked_symbol_names() -> list[str]:
    return [s.symbol for s in get_tracked_symbols().symbols]


def is_symbol_tracked(symbol: str) -> bool:
    norm = symbol.strip().upper()
    if not SYMBOL_PATTERN.match(norm):
        return False
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM tracked_symbols WHERE symbol = ?",
            (norm,),
        ).fetchone()
    return row is not None


async def add_tracked_symbol(symbol: str) -> TrackedSymbolItem:
    norm = symbol.strip().upper()
    if not SYMBOL_PATTERN.match(norm):
        raise AppError(
            code="INVALID_SYMBOL_FORMAT",
            message=f"Symbol '{norm}' must contain 4-20 uppercase alphanumeric characters (e.g., DOGEUSDT).",
            status_code=400,
        )

    # Check if already tracked
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT symbol, base_asset, quote_asset, source, is_default, added_at FROM tracked_symbols WHERE symbol = ?",
            (norm,),
        ).fetchone()
    if existing:
        return TrackedSymbolItem(
            symbol=existing["symbol"],
            base_asset=existing["base_asset"],
            quote_asset=existing["quote_asset"],
            source=existing["source"],
            is_default=bool(existing["is_default"]),
            added_at=existing["added_at"],
        )

    # Verify live existence on Binance Public Spot API before registering
    settings = get_settings()
    verify_url = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/ticker/price"
    try:
        res = await fetch_json_resilient(
            verify_url,
            params={"symbol": norm},
            timeout=settings.MARKET_DATA_TIMEOUT_SEC,
            max_retries=2,
        )
        if not isinstance(res.data, dict) or "price" not in res.data:
            raise ExternalMarketDataError(f"Symbol '{norm}' was not confirmed by Binance Spot API.")
    except UpstreamFetchError as exc:
        if exc.status_code == 400:
            raise AppError(
                code="UNSUPPORTED_EXCHANGE_SYMBOL",
                message=f"Trading pair '{norm}' does not exist on Binance Spot market.",
                status_code=400,
                details=exc.message,
            ) from exc
        raise ExternalMarketDataError(
            f"Could not verify '{norm}' against Binance Public API.",
            details=exc.message,
        ) from exc

    base_asset, quote_asset = _infer_assets(norm)
    now_iso = datetime.now(timezone.utc).isoformat()
    source_desc = "Binance Spot Verified Pair"
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tracked_symbols (symbol, base_asset, quote_asset, source, is_default, added_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (norm, base_asset, quote_asset, source_desc, now_iso),
        )

    logger.info("Added tracked symbol %s (%s/%s)", norm, base_asset, quote_asset)
    return TrackedSymbolItem(
        symbol=norm,
        base_asset=base_asset,
        quote_asset=quote_asset,
        source=source_desc,
        is_default=False,
        added_at=now_iso,
    )


def remove_tracked_symbol(symbol: str) -> TrackedSymbolsResponse:
    norm = symbol.strip().upper()
    if norm in CORE_LOCKED_SYMBOLS:
        raise AppError(
            code="CORE_SYMBOL_LOCKED",
            message=f"Core institutional pair '{norm}' cannot be removed.",
            status_code=400,
        )
    with get_db_connection() as conn:
        deleted = conn.execute("DELETE FROM tracked_symbols WHERE symbol = ?", (norm,)).rowcount
    if deleted == 0:
        raise AppError(
            code="SYMBOL_NOT_FOUND",
            message=f"Symbol '{norm}' is not in tracked symbols.",
            status_code=404,
        )
    logger.info("Removed tracked symbol %s", norm)
    return get_tracked_symbols()
