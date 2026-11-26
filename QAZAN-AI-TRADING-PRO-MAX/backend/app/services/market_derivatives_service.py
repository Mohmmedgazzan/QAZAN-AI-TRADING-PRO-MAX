import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.engine.technical_engine import analyze_multi_timeframe
from app.ml.probability_engine import run_next_candle_probability_engine
from app.schemas.ingestion import (
    ConnectedEngineContext,
    MarketIntelligenceResponse,
    ProvenanceMetric,
)
from app.services.http_resilient import (
    UpstreamFetchError,
    fetch_json_resilient,
    rate_limit_monitor,
)
from app.services.market_data_validator import validate_ohlcv_and_market_data
from app.services.market_service import ALLOWED_INTERVALS, fetch_market_klines
from app.services.symbol_registry import is_symbol_tracked
from app.services.ws_market_hub import ws_market_hub

logger = get_logger("qazan.derivatives")


def _to_okx_swap_inst(symbol: str) -> str | None:
    for quote in ("USDT", "USDC"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}-{quote}-SWAP"
    return None


def _save_metric_cache(
    cache_key: str,
    symbol: str,
    metric_type: str,
    payload: dict[str, Any],
    source: str,
    ttl_seconds: float,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    expires = time.time() + ttl_seconds
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO market_metrics_cache
                (cache_key, symbol, metric_type, payload_json, source, updated_at, expires_at_epoch)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cache_key, symbol, metric_type, json.dumps(payload), source, now_iso, expires),
        )


def _load_metric_cache(cache_key: str, allow_expired: bool = True) -> tuple[dict[str, Any], str, float] | None:
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT payload_json, source, updated_at, expires_at_epoch
            FROM market_metrics_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    if not allow_expired and time.time() > float(row["expires_at_epoch"]):
        return None
    try:
        updated_dt = datetime.fromisoformat(row["updated_at"])
        age = max(0.0, round((datetime.now(timezone.utc) - updated_dt).total_seconds(), 1))
    except Exception:
        age = 0.0
    return json.loads(row["payload_json"]), str(row["updated_at"]), age


async def _fetch_open_interest(symbol: str) -> ProvenanceMetric:
    settings = get_settings()
    cache_key = f"oi:{symbol}"

    # Check fresh cache first (45s TTL)
    fresh = _load_metric_cache(cache_key, allow_expired=False)
    if fresh is not None:
        data, updated_at, age = fresh
        return ProvenanceMetric(
            metric="open_interest",
            status="CACHED",
            value=data.get("value"),
            secondary_value=data.get("notional_usd"),
            secondary_label="USD Notional",
            unit=data.get("unit", "Contracts"),
            source=data.get("source", "SQLite Cache"),
            updated_at=updated_at,
            cache_age_sec=age,
            note="Served from SQLite TTL cache",
        )

    # 1. Try Binance Futures Public REST API
    fapi_url = f"{settings.FUTURES_DATA_BASE_URL.rstrip('/')}/fapi/v1/openInterest"
    try:
        res = await fetch_json_resilient(
            fapi_url, params={"symbol": symbol}, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=2
        )
        oi_val = float(res.data["openInterest"])
        base_unit = symbol.replace("USDT", "").replace("USDC", "")
        mark_price = None
        try:
            prem_url = f"{settings.FUTURES_DATA_BASE_URL.rstrip('/')}/fapi/v1/premiumIndex"
            prem = await fetch_json_resilient(prem_url, params={"symbol": symbol}, timeout=4.0, max_retries=1)
            mark_price = float(prem.data.get("markPrice") or 0.0)
        except Exception:
            mark_price = None

        notional = round(oi_val * mark_price, 2) if mark_price and mark_price > 0 else None
        source = "Binance Futures Public API (/fapi/v1/openInterest)"
        payload = {"value": round(oi_val, 4), "notional_usd": notional, "unit": base_unit, "source": source}
        _save_metric_cache(cache_key, symbol, "open_interest", payload, source, ttl_seconds=45.0)
        return ProvenanceMetric(
            metric="open_interest",
            status="LIVE",
            value=payload["value"],
            secondary_value=notional,
            secondary_label="USD Notional",
            unit=base_unit,
            source=source,
            updated_at=res.fetched_at,
            cache_age_sec=0.0,
        )
    except Exception as bin_exc:
        logger.warning("Binance Futures OI failed for %s: %s", symbol, str(bin_exc))

    # 2. Try OKX Public SWAP fallback if Binance Futures fails
    okx_inst = _to_okx_swap_inst(symbol)
    if okx_inst:
        okx_url = f"{settings.OKX_PUBLIC_BASE_URL.rstrip('/')}/api/v5/public/open-interest"
        try:
            res = await fetch_json_resilient(
                okx_url,
                params={"instType": "SWAP", "instId": okx_inst},
                timeout=settings.MARKET_DATA_TIMEOUT_SEC,
                max_retries=1,
            )
            rows = res.data.get("data") if isinstance(res.data, dict) else None
            if rows and isinstance(rows, list):
                oi_ccy = float(rows[0].get("oiCcy") or 0.0)
                oi_usd = float(rows[0].get("oiUsd") or 0.0)
                base_unit = symbol.replace("USDT", "").replace("USDC", "")
                source = "OKX Public API (/api/v5/public/open-interest)"
                payload = {
                    "value": round(oi_ccy, 4),
                    "notional_usd": round(oi_usd, 2) if oi_usd > 0 else None,
                    "unit": base_unit,
                    "source": source,
                }
                _save_metric_cache(cache_key, symbol, "open_interest", payload, source, ttl_seconds=45.0)
                return ProvenanceMetric(
                    metric="open_interest",
                    status="LIVE",
                    value=payload["value"],
                    secondary_value=payload["notional_usd"],
                    secondary_label="USD Notional",
                    unit=base_unit,
                    source=source,
                    updated_at=res.fetched_at,
                    cache_age_sec=0.0,
                )
        except Exception as okx_exc:
            logger.warning("OKX OI fallback failed for %s: %s", symbol, str(okx_exc))

    # 3. Stale cache fallback before returning MISSING
    stale = _load_metric_cache(cache_key, allow_expired=True)
    if stale is not None:
        data, updated_at, age = stale
        return ProvenanceMetric(
            metric="open_interest",
            status="CACHED",
            value=data.get("value"),
            secondary_value=data.get("notional_usd"),
            secondary_label="USD Notional",
            unit=data.get("unit"),
            source=f"{data.get('source')} (Stale SQLite Cache Fallback)",
            updated_at=updated_at,
            cache_age_sec=age,
            note="Upstream unavailable; showing last verified cached observation.",
        )

    return ProvenanceMetric(
        metric="open_interest",
        status="MISSING",
        value=None,
        unit="Contracts",
        source="Unavailable (Binance Futures / OKX Public)",
        updated_at=None,
        note="Perpetual Open Interest unavailable for this symbol; no synthetic value fabricated.",
    )


async def _fetch_funding_rate(symbol: str) -> ProvenanceMetric:
    settings = get_settings()
    cache_key = f"funding:{symbol}"

    fresh = _load_metric_cache(cache_key, allow_expired=False)
    if fresh is not None:
        data, updated_at, age = fresh
        return ProvenanceMetric(
            metric="funding_rate",
            status="CACHED",
            value=data.get("value_pct"),
            secondary_value=data.get("mark_price"),
            secondary_label="Mark Price",
            unit="% (8h)",
            source=data.get("source", "SQLite Cache"),
            updated_at=updated_at,
            cache_age_sec=age,
            note=data.get("note"),
        )

    # 1. Binance Futures Premium Index (lastFundingRate)
    prem_url = f"{settings.FUTURES_DATA_BASE_URL.rstrip('/')}/fapi/v1/premiumIndex"
    try:
        res = await fetch_json_resilient(
            prem_url, params={"symbol": symbol}, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=2
        )
        raw_rate = float(res.data["lastFundingRate"])
        rate_pct = round(raw_rate * 100.0, 5)
        mark_price = round(float(res.data.get("markPrice") or 0.0), 4)
        source = "Binance Futures Public API (/fapi/v1/premiumIndex)"
        payload = {
            "value_pct": rate_pct,
            "mark_price": mark_price,
            "source": source,
            "note": f"Index price ${float(res.data.get('indexPrice') or 0.0):,.2f}",
        }
        _save_metric_cache(cache_key, symbol, "funding_rate", payload, source, ttl_seconds=60.0)
        return ProvenanceMetric(
            metric="funding_rate",
            status="LIVE",
            value=rate_pct,
            secondary_value=mark_price,
            secondary_label="Mark Price",
            unit="% (8h)",
            source=source,
            updated_at=res.fetched_at,
            cache_age_sec=0.0,
            note=payload["note"],
        )
    except Exception as bin_exc:
        logger.warning("Binance Futures funding failed for %s: %s", symbol, str(bin_exc))

    # 2. OKX fallback
    okx_inst = _to_okx_swap_inst(symbol)
    if okx_inst:
        okx_url = f"{settings.OKX_PUBLIC_BASE_URL.rstrip('/')}/api/v5/public/funding-rate"
        try:
            res = await fetch_json_resilient(
                okx_url, params={"instId": okx_inst}, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=1
            )
            rows = res.data.get("data") if isinstance(res.data, dict) else None
            if rows and isinstance(rows, list):
                rate_pct = round(float(rows[0]["fundingRate"]) * 100.0, 5)
                source = "OKX Public API (/api/v5/public/funding-rate)"
                payload = {"value_pct": rate_pct, "mark_price": None, "source": source, "note": None}
                _save_metric_cache(cache_key, symbol, "funding_rate", payload, source, ttl_seconds=60.0)
                return ProvenanceMetric(
                    metric="funding_rate",
                    status="LIVE",
                    value=rate_pct,
                    unit="% (8h)",
                    source=source,
                    updated_at=res.fetched_at,
                    cache_age_sec=0.0,
                )
        except Exception as okx_exc:
            logger.warning("OKX funding fallback failed for %s: %s", symbol, str(okx_exc))

    stale = _load_metric_cache(cache_key, allow_expired=True)
    if stale is not None:
        data, updated_at, age = stale
        return ProvenanceMetric(
            metric="funding_rate",
            status="CACHED",
            value=data.get("value_pct"),
            secondary_value=data.get("mark_price"),
            secondary_label="Mark Price",
            unit="% (8h)",
            source=f"{data.get('source')} (Stale SQLite Cache Fallback)",
            updated_at=updated_at,
            cache_age_sec=age,
            note="Upstream unavailable; serving cached observation.",
        )

    return ProvenanceMetric(
        metric="funding_rate",
        status="MISSING",
        value=None,
        unit="% (8h)",
        source="Unavailable (Binance Futures / OKX Public)",
        updated_at=None,
        note="Perpetual Funding Rate unavailable for this symbol; no synthetic rate generated.",
    )


async def _fetch_cvd(symbol: str) -> ProvenanceMetric:
    settings = get_settings()
    cache_key = f"cvd:{symbol}"

    # Combine live aggTrade WebSocket delta if present with Binance Spot aggTrades REST window
    ws_cvd = ws_market_hub.live_cvd_delta.get(symbol)
    agg_url = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/aggTrades"
    try:
        res = await fetch_json_resilient(
            agg_url,
            params={"symbol": symbol, "limit": 500},
            timeout=settings.MARKET_DATA_TIMEOUT_SEC,
            max_retries=2,
        )
        trades = res.data
        if not isinstance(trades, list) or len(trades) == 0:
            raise ValueError("Empty aggTrades payload")

        buy_vol = 0.0
        sell_vol = 0.0
        cvd_usd = 0.0
        for tr in trades:
            qty = float(tr["q"])
            price = float(tr["p"])
            is_buyer_maker = bool(tr["m"])
            if is_buyer_maker:
                sell_vol += qty
                cvd_usd -= qty * price
            else:
                buy_vol += qty
                cvd_usd += qty * price

        net_delta_base = buy_vol - sell_vol
        total_vol = buy_vol + sell_vol
        buy_ratio_pct = round((buy_vol / total_vol) * 100.0, 2) if total_vol > 0 else None

        source = "Binance Spot Public /api/v3/aggTrades (Last 500 Taker Trades)"
        if ws_cvd:
            source = "Binance Spot REST /api/v3/aggTrades + Live WS @aggTrade Stream"

        base_unit = symbol.replace("USDT", "").replace("USDC", "")
        payload = {
            "value": round(net_delta_base, 4),
            "cvd_usd": round(cvd_usd, 2),
            "buy_ratio_pct": buy_ratio_pct,
            "unit": base_unit,
            "source": source,
        }
        _save_metric_cache(cache_key, symbol, "cvd", payload, source, ttl_seconds=25.0)
        return ProvenanceMetric(
            metric="cvd",
            status="LIVE",
            value=payload["value"],
            secondary_value=payload["cvd_usd"],
            secondary_label="Net USD Delta",
            unit=base_unit,
            source=source,
            updated_at=res.fetched_at,
            cache_age_sec=0.0,
            note=f"Taker Buy Share: {buy_ratio_pct}% across {len(trades)} aggregated trades",
        )
    except Exception as exc:
        logger.warning("Failed fetching CVD aggTrades for %s: %s", symbol, str(exc))

    if ws_cvd:
        return ProvenanceMetric(
            metric="cvd",
            status="LIVE",
            value=round(float(ws_cvd["cumulative_delta_base"]), 4),
            secondary_value=round(float(ws_cvd["cumulative_delta_usd"]), 2),
            secondary_label="Session USD Delta",
            unit=symbol.replace("USDT", ""),
            source=ws_cvd["source"],
            updated_at=ws_cvd["updated_at"],
            cache_age_sec=0.0,
        )

    stale = _load_metric_cache(cache_key, allow_expired=True)
    if stale is not None:
        data, updated_at, age = stale
        return ProvenanceMetric(
            metric="cvd",
            status="CACHED",
            value=data.get("value"),
            secondary_value=data.get("cvd_usd"),
            secondary_label="Net USD Delta",
            unit=data.get("unit"),
            source=f"{data.get('source')} (SQLite Cache)",
            updated_at=updated_at,
            cache_age_sec=age,
        )

    return ProvenanceMetric(
        metric="cvd",
        status="MISSING",
        value=None,
        unit=symbol.replace("USDT", ""),
        source="Unavailable (Binance /api/v3/aggTrades)",
        updated_at=None,
        note="Aggregated trade delta unavailable; no synthetic CVD generated.",
    )


async def _fetch_btc_dominance() -> ProvenanceMetric:
    settings = get_settings()
    cache_key = "macro:btc_dominance"

    fresh = _load_metric_cache(cache_key, allow_expired=False)
    if fresh is not None:
        data, updated_at, age = fresh
        return ProvenanceMetric(
            metric="btc_dominance",
            status="CACHED",
            value=data.get("btc_dom"),
            secondary_value=data.get("eth_dom"),
            secondary_label="ETH Dominance %",
            unit="%",
            source=data.get("source", "SQLite Cache"),
            updated_at=updated_at,
            cache_age_sec=age,
            note="Served from SQLite 5m macro cache",
        )

    # 1. CoinGecko Public Global endpoint
    cg_url = f"{settings.COINGECKO_BASE_URL.rstrip('/')}/api/v3/global"
    try:
        res = await fetch_json_resilient(cg_url, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=2)
        gdata = res.data.get("data", {}) if isinstance(res.data, dict) else {}
        pcts = gdata.get("market_cap_percentage", {})
        if "btc" in pcts:
            btc_dom = round(float(pcts["btc"]), 3)
            eth_dom = round(float(pcts.get("eth", 0.0)), 3) if "eth" in pcts else None
            source = "CoinGecko Public Global API (/api/v3/global)"
            payload = {"btc_dom": btc_dom, "eth_dom": eth_dom, "source": source}
            _save_metric_cache(cache_key, "GLOBAL", "btc_dominance", payload, source, ttl_seconds=300.0)
            return ProvenanceMetric(
                metric="btc_dominance",
                status="LIVE",
                value=btc_dom,
                secondary_value=eth_dom,
                secondary_label="ETH Dominance %",
                unit="%",
                source=source,
                updated_at=res.fetched_at,
                cache_age_sec=0.0,
            )
    except Exception as cg_exc:
        logger.warning("CoinGecko global BTC dominance failed: %s", str(cg_exc))

    # 2. CoinPaprika Public Global fallback
    cp_url = f"{settings.COINPAPRIKA_BASE_URL.rstrip('/')}/v1/global"
    try:
        res = await fetch_json_resilient(cp_url, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=1)
        if isinstance(res.data, dict) and "bitcoin_dominance_percentage" in res.data:
            btc_dom = round(float(res.data["bitcoin_dominance_percentage"]), 3)
            source = "CoinPaprika Public Global API (/v1/global)"
            payload = {"btc_dom": btc_dom, "eth_dom": None, "source": source}
            _save_metric_cache(cache_key, "GLOBAL", "btc_dominance", payload, source, ttl_seconds=300.0)
            return ProvenanceMetric(
                metric="btc_dominance",
                status="LIVE",
                value=btc_dom,
                unit="%",
                source=source,
                updated_at=res.fetched_at,
                cache_age_sec=0.0,
            )
    except Exception as cp_exc:
        logger.warning("CoinPaprika global fallback failed: %s", str(cp_exc))

    stale = _load_metric_cache(cache_key, allow_expired=True)
    if stale is not None:
        data, updated_at, age = stale
        return ProvenanceMetric(
            metric="btc_dominance",
            status="CACHED",
            value=data.get("btc_dom"),
            secondary_value=data.get("eth_dom"),
            secondary_label="ETH Dominance %",
            unit="%",
            source=f"{data.get('source')} (Stale SQLite Cache Fallback)",
            updated_at=updated_at,
            cache_age_sec=age,
            note="Macro API unavailable; serving last cached reading.",
        )

    return ProvenanceMetric(
        metric="btc_dominance",
        status="MISSING",
        value=None,
        unit="%",
        source="Unavailable (CoinGecko / CoinPaprika Public Global)",
        updated_at=None,
        note="BTC Dominance unavailable; no synthetic dominance figure generated.",
    )


async def _fetch_volume_24h(symbol: str) -> ProvenanceMetric:
    settings = get_settings()
    ws_tk = ws_market_hub.latest_tickers.get(symbol)
    if ws_tk:
        return ProvenanceMetric(
            metric="volume_24h",
            status="LIVE",
            value=round(float(ws_tk["quote_volume_24h"]), 2),
            secondary_value=round(float(ws_tk["volume_24h"]), 4),
            secondary_label="Base Volume",
            unit="USDT",
            source=ws_tk["source"],
            updated_at=ws_tk["updated_at"],
            cache_age_sec=0.0,
        )

    url = f"{settings.MARKET_DATA_BASE_URL.rstrip('/')}/api/v3/ticker/24hr"
    try:
        res = await fetch_json_resilient(
            url, params={"symbol": symbol}, timeout=settings.MARKET_DATA_TIMEOUT_SEC, max_retries=2
        )
        q_vol = round(float(res.data["quoteVolume"]), 2)
        b_vol = round(float(res.data["volume"]), 4)
        source = "Binance Spot Public API (/api/v3/ticker/24hr)"
        _save_metric_cache(
            f"vol24h:{symbol}",
            symbol,
            "volume_24h",
            {"q_vol": q_vol, "b_vol": b_vol, "source": source},
            source,
            ttl_seconds=45.0,
        )
        return ProvenanceMetric(
            metric="volume_24h",
            status="LIVE",
            value=q_vol,
            secondary_value=b_vol,
            secondary_label="Base Volume",
            unit="USDT",
            source=source,
            updated_at=res.fetched_at,
            cache_age_sec=0.0,
        )
    except Exception as exc:
        logger.warning("Volume 24h fetch failed for %s: %s", symbol, str(exc))

    stale = _load_metric_cache(f"vol24h:{symbol}", allow_expired=True)
    if stale is not None:
        data, updated_at, age = stale
        return ProvenanceMetric(
            metric="volume_24h",
            status="CACHED",
            value=data.get("q_vol"),
            secondary_value=data.get("b_vol"),
            secondary_label="Base Volume",
            unit="USDT",
            source=f"{data.get('source')} (SQLite Cache)",
            updated_at=updated_at,
            cache_age_sec=age,
        )

    return ProvenanceMetric(
        metric="volume_24h",
        status="MISSING",
        value=None,
        unit="USDT",
        source="Unavailable (Binance /api/v3/ticker/24hr)",
        updated_at=None,
        note="24h Volume unavailable; no synthetic volume generated.",
    )


def _build_liquidations_metric(symbol: str) -> tuple[ProvenanceMetric, list]:
    symbol_events = ws_market_hub.get_recent_liquidations(symbol=symbol, limit=15)
    market_events = ws_market_hub.get_recent_liquidations(symbol=None, limit=15)
    events_to_show = symbol_events if symbol_events else market_events

    if symbol_events:
        total_usd = round(sum(ev.notional_usd for ev in symbol_events), 2)
        return (
            ProvenanceMetric(
                metric="liquidations",
                status="LIVE",
                value=total_usd,
                secondary_value=float(len(symbol_events)),
                secondary_label="Captured Events",
                unit="USD",
                source="Binance Futures WebSocket (!forceOrder@arr)",
                updated_at=symbol_events[0].received_at,
                cache_age_sec=0.0,
                note=f"Live captured force liquidations for {symbol}.",
            ),
            events_to_show,
        )

    if market_events:
        # Futures WS stream is receiving real market-wide liquidations, just none for this symbol yet
        market_usd = round(sum(ev.notional_usd for ev in market_events), 2)
        return (
            ProvenanceMetric(
                metric="liquidations",
                status="MISSING",
                value=None,
                secondary_value=market_usd,
                secondary_label="Market-Wide Captured USD",
                unit="USD",
                source="Binance Futures WebSocket (!forceOrder@arr)",
                updated_at=ws_market_hub.last_liquidation_at,
                note=(
                    f"No {symbol} force liquidations captured in current session yet "
                    f"({len(market_events)} market-wide events captured). Zero fake events shown."
                ),
            ),
            events_to_show,
        )

    return (
        ProvenanceMetric(
            metric="liquidations",
            status="MISSING",
            value=None,
            unit="USD",
            source="Binance Futures WebSocket (!forceOrder@arr)",
            updated_at=ws_market_hub.last_liquidation_at,
            note="No force liquidation events received yet on !forceOrder@arr stream; no synthetic numbers used.",
        ),
        [],
    )


async def build_market_intelligence(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
) -> MarketIntelligenceResponse:
    norm_symbol = symbol.strip().upper()
    norm_interval = interval.strip() if interval.strip() in ALLOWED_INTERVALS else "1h"

    # Fetch validated OHLCV + all real derivatives/macro metrics concurrently
    klines_task = fetch_market_klines(symbol=norm_symbol, interval=norm_interval, limit=180)
    vol_task = _fetch_volume_24h(norm_symbol)
    oi_task = _fetch_open_interest(norm_symbol)
    funding_task = _fetch_funding_rate(norm_symbol)
    cvd_task = _fetch_cvd(norm_symbol)
    dom_task = _fetch_btc_dominance()

    klines_res, vol_metric, oi_metric, funding_metric, cvd_metric, dom_metric = await asyncio.gather(
        klines_task,
        vol_task,
        oi_task,
        funding_task,
        cvd_task,
        dom_task,
    )

    liq_metric, recent_liqs = _build_liquidations_metric(norm_symbol)

    metrics_map = {
        "volume_24h": vol_metric,
        "open_interest": oi_metric,
        "funding_rate": funding_metric,
        "liquidations": liq_metric,
        "cvd": cvd_metric,
        "btc_dominance": dom_metric,
    }

    validation = validate_ohlcv_and_market_data(
        symbol=norm_symbol,
        interval=norm_interval,
        candles=klines_res.candles,
        metrics=metrics_map,
    )

    # Wire real validated OHLCV directly into Technical Engine & Probability Engine
    connected_engine = ConnectedEngineContext()
    try:
        tech_res, prob_res = await asyncio.gather(
            analyze_multi_timeframe(symbol=norm_symbol, ltf_interval=norm_interval, persist=False),
            run_next_candle_probability_engine(
                symbol=norm_symbol, interval=norm_interval, limit=260, persist=False
            ),
        )
        connected_engine = ConnectedEngineContext(
            technical_bias=tech_res.market_bias,
            technical_regime=tech_res.market_regime,
            technical_phase=tech_res.market_phase,
            htf_alignment_score=tech_res.htf_alignment_score,
            probability_status=prob_res.status,
            prob_up_pct=prob_res.probabilities.up_pct if prob_res.probabilities else None,
            prob_down_pct=prob_res.probabilities.down_pct if prob_res.probabilities else None,
            prob_sideways_pct=prob_res.probabilities.sideways_pct if prob_res.probabilities else None,
            prob_confidence_pct=prob_res.confidence_pct,
            engine_note=(
                f"Connected to validated {klines_res.candle_count}-bar {norm_symbol} feed "
                f"(integrity={validation.integrity_score_pct}%)."
            ),
        )
    except Exception as exc:
        logger.warning("Connected engine evaluation warning for %s: %s", norm_symbol, str(exc))
        connected_engine = ConnectedEngineContext(
            engine_note=f"Engine summary skipped: {str(exc)}"
        )

    return MarketIntelligenceResponse(
        symbol=norm_symbol,
        interval=norm_interval,
        generated_at=datetime.now(timezone.utc).isoformat(),
        ohlcv_source=klines_res.source,
        ohlcv_updated_at=klines_res.fetched_at,
        ohlcv_cached_fallback=klines_res.cached_fallback,
        ohlcv_summary=klines_res.summary,
        candles_preview=klines_res.candles[-40:],
        volume_24h=vol_metric,
        open_interest=oi_metric,
        funding_rate=funding_metric,
        liquidations=liq_metric,
        cvd=cvd_metric,
        btc_dominance=dom_metric,
        recent_liquidations=recent_liqs,
        validation=validation,
        rate_limit=rate_limit_monitor.snapshot(),
        ws_status=ws_market_hub.status(),
        connected_engine=connected_engine,
    )
