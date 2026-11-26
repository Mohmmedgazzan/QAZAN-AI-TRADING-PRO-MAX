import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import random
import time
from typing import Any
import httpx

from app.core.logging import get_logger
from app.schemas.ingestion import RateLimitTelemetry

logger = get_logger("qazan.http")

RETRYABLE_STATUS_CODES = {418, 429, 500, 502, 503, 504}


class UpstreamFetchError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        source_url: str = "",
        retries_used: int = 0,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.source_url = source_url
        self.retries_used = retries_used


@dataclass
class ResilientFetchResult:
    data: Any
    status_code: int
    source_url: str
    used_weight_1m: int | None
    retries_used: int
    fetched_at: str


class RateLimitMonitor:
    def __init__(self) -> None:
        self.total_requests: int = 0
        self.retries_executed: int = 0
        self.rate_limit_hits: int = 0
        self.last_binance_used_weight_1m: int | None = None
        self.last_retry_after_sec: float | None = None
        self.cooldown_until_epoch: float = 0.0
        self.last_error: str | None = None
        self.last_success_at: str | None = None

    def snapshot(self) -> RateLimitTelemetry:
        now = time.time()
        remaining = max(0.0, round(self.cooldown_until_epoch - now, 2))
        return RateLimitTelemetry(
            total_requests=self.total_requests,
            retries_executed=self.retries_executed,
            rate_limit_hits=self.rate_limit_hits,
            last_binance_used_weight_1m=self.last_binance_used_weight_1m,
            last_retry_after_sec=self.last_retry_after_sec,
            cooldown_active=remaining > 0.0,
            cooldown_remaining_sec=remaining,
            last_error=self.last_error,
            last_success_at=self.last_success_at,
        )

    def reset_for_tests(self) -> None:
        self.total_requests = 0
        self.retries_executed = 0
        self.rate_limit_hits = 0
        self.last_binance_used_weight_1m = None
        self.last_retry_after_sec = None
        self.cooldown_until_epoch = 0.0
        self.last_error = None
        self.last_success_at = None


rate_limit_monitor = RateLimitMonitor()


def _parse_retry_after(header_val: str | None) -> float | None:
    if not header_val:
        return None
    try:
        parsed = float(header_val.strip())
        return max(0.0, parsed)
    except ValueError:
        return None


def _parse_binance_weight(headers: httpx.Headers) -> int | None:
    for key in ("x-mbx-used-weight-1m", "X-MBX-USED-WEIGHT-1M", "x-mbx-used-weight"):
        val = headers.get(key)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
    return None


async def fetch_json_resilient(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float = 8.0,
    max_retries: int = 3,
    base_backoff: float = 0.35,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> ResilientFetchResult:
    """
    Resilient async HTTP JSON fetcher with:
    - Exponential backoff + jitter retries on transient network/5xx errors
    - HTTP 429 / 418 rate-limit detection & Retry-After header handling
    - Binance X-MBX-USED-WEIGHT-1M header monitoring
    """
    now_epoch = time.time()
    if rate_limit_monitor.cooldown_until_epoch > now_epoch and "binance" in url:
        wait_rem = round(rate_limit_monitor.cooldown_until_epoch - now_epoch, 2)
        if wait_rem > 2.5:
            raise UpstreamFetchError(
                f"Rate-limit cooldown active ({wait_rem}s remaining).",
                status_code=429,
                source_url=url,
                retries_used=0,
            )
        await asyncio.sleep(wait_rem)

    req_headers = {"User-Agent": "QAZAN-AI-TRADING-PRO-MAX/0.5.0", **(headers or {})}
    retries_used = 0
    last_exc_msg = "Unknown upstream error"
    last_status: int | None = None

    async def _do_request(http_client: httpx.AsyncClient) -> httpx.Response:
        return await http_client.get(url, params=params, headers=req_headers)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        for attempt in range(max_retries + 1):
            rate_limit_monitor.total_requests += 1
            try:
                response = await _do_request(active_client)
                used_weight = _parse_binance_weight(response.headers)
                if used_weight is not None:
                    rate_limit_monitor.last_binance_used_weight_1m = used_weight

                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_status = response.status_code
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    if response.status_code in (418, 429):
                        rate_limit_monitor.rate_limit_hits += 1
                        rate_limit_monitor.last_retry_after_sec = retry_after
                        cooldown_sec = retry_after if retry_after is not None else (base_backoff * (2**attempt))
                        # Cap inline sleep to 3s while registering true cooldown if longer
                        if cooldown_sec > 3.0:
                            rate_limit_monitor.cooldown_until_epoch = time.time() + min(cooldown_sec, 60.0)
                            last_exc_msg = f"HTTP {response.status_code} Retry-After={cooldown_sec}s"
                            rate_limit_monitor.last_error = last_exc_msg
                            raise UpstreamFetchError(
                                last_exc_msg,
                                status_code=response.status_code,
                                source_url=url,
                                retries_used=retries_used,
                            )
                        sleep_sec = cooldown_sec
                    else:
                        sleep_sec = base_backoff * (2**attempt) + random.uniform(0.02, 0.12)

                    last_exc_msg = f"HTTP {response.status_code} from {url}"
                    if attempt < max_retries:
                        retries_used += 1
                        rate_limit_monitor.retries_executed += 1
                        logger.warning(
                            "Retry %s/%s for %s after %s (sleep %.2fs)",
                            retries_used,
                            max_retries,
                            url,
                            last_exc_msg,
                            sleep_sec,
                        )
                        await asyncio.sleep(sleep_sec)
                        continue

                    rate_limit_monitor.last_error = last_exc_msg
                    raise UpstreamFetchError(
                        last_exc_msg,
                        status_code=response.status_code,
                        source_url=url,
                        retries_used=retries_used,
                    )

                if response.status_code >= 400:
                    last_status = response.status_code
                    last_exc_msg = f"HTTP {response.status_code}: {response.text[:160]}"
                    rate_limit_monitor.last_error = last_exc_msg
                    raise UpstreamFetchError(
                        last_exc_msg,
                        status_code=response.status_code,
                        source_url=url,
                        retries_used=retries_used,
                    )

                payload = response.json()
                fetched_at = datetime.now(timezone.utc).isoformat()
                rate_limit_monitor.last_success_at = fetched_at
                return ResilientFetchResult(
                    data=payload,
                    status_code=response.status_code,
                    source_url=str(response.url),
                    used_weight_1m=used_weight,
                    retries_used=retries_used,
                    fetched_at=fetched_at,
                )

            except UpstreamFetchError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, ValueError) as exc:
                last_exc_msg = f"{type(exc).__name__}: {str(exc)}"
                if attempt < max_retries:
                    retries_used += 1
                    rate_limit_monitor.retries_executed += 1
                    sleep_sec = base_backoff * (2**attempt) + random.uniform(0.02, 0.12)
                    logger.warning(
                        "Network retry %s/%s for %s (%s, sleep %.2fs)",
                        retries_used,
                        max_retries,
                        url,
                        last_exc_msg,
                        sleep_sec,
                    )
                    await asyncio.sleep(sleep_sec)
                    continue
                rate_limit_monitor.last_error = last_exc_msg
                raise UpstreamFetchError(
                    last_exc_msg,
                    status_code=last_status,
                    source_url=url,
                    retries_used=retries_used,
                ) from exc
    finally:
        if owns_client:
            await active_client.aclose()

    rate_limit_monitor.last_error = last_exc_msg
    raise UpstreamFetchError(last_exc_msg, status_code=last_status, source_url=url, retries_used=retries_used)
