from datetime import datetime, timezone
import math
import time

from app.schemas.common import CandlePoint
from app.schemas.ingestion import DataValidationReport, ProvenanceMetric

INTERVAL_SECONDS_MAP: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def _is_valid_candle(c: CandlePoint) -> bool:
    vals = (c.open, c.high, c.low, c.close, c.volume)
    if not all(math.isfinite(v) for v in vals):
        return False
    if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
        return False
    if c.volume < 0:
        return False
    if c.high < max(c.open, c.close):
        return False
    if c.low > min(c.open, c.close):
        return False
    return True


def validate_ohlcv_and_market_data(
    symbol: str,
    interval: str,
    candles: list[CandlePoint],
    metrics: dict[str, ProvenanceMetric] | None = None,
    reference_epoch: float | None = None,
) -> DataValidationReport:
    now_epoch = reference_epoch if reference_epoch is not None else time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    step_sec = INTERVAL_SECONDS_MAP.get(interval, 3600)

    issues: list[str] = []
    invalid_bars = 0
    duplicate_timestamps = 0
    out_of_order_timestamps = 0
    missing_candle_gaps = 0
    missing_candles_estimated = 0
    gap_timestamps: list[int] = []

    if not candles:
        issues.append("OHLCV candle array is empty.")
        missing_fields = ["ohlcv"]
        if metrics:
            for name, m in metrics.items():
                if m.status == "MISSING":
                    missing_fields.append(name)
        return DataValidationReport(
            symbol=symbol,
            interval=interval,
            status="INVALID",
            candles_checked=0,
            invalid_bars=0,
            duplicate_timestamps=0,
            out_of_order_timestamps=0,
            missing_candle_gaps=0,
            missing_candles_estimated=0,
            gap_timestamps=[],
            stale_seconds=None,
            is_stale=True,
            missing_fields=missing_fields,
            integrity_score_pct=0.0,
            issues=issues,
            validated_at=now_iso,
        )

    seen_times: set[int] = set()
    prev_time: int | None = None
    for idx, bar in enumerate(candles):
        if not _is_valid_candle(bar):
            invalid_bars += 1
            if len(issues) < 12:
                issues.append(f"Invalid OHLCV invariants at bar index {idx} (time={bar.time}).")

        if bar.time in seen_times:
            duplicate_timestamps += 1
        seen_times.add(bar.time)

        if prev_time is not None:
            diff = bar.time - prev_time
            if diff <= 0:
                out_of_order_timestamps += 1
                if len(issues) < 12:
                    issues.append(f"Non-monotonic timestamp at index {idx}: {prev_time} -> {bar.time}.")
            elif diff > step_sec:
                missing_candle_gaps += 1
                missed = max(1, int(round(diff / step_sec)) - 1)
                missing_candles_estimated += missed
                # Record first missing candle timestamp(s)
                for g in range(1, min(missed, 5) + 1):
                    gap_timestamps.append(prev_time + g * step_sec)
                if len(issues) < 12:
                    issues.append(
                        f"Missing {missed} candle(s) after {prev_time} (gap={diff}s, expected={step_sec}s)."
                    )
        prev_time = bar.time

    last_bar_close_est = candles[-1].time + step_sec
    stale_seconds = max(0.0, round(now_epoch - last_bar_close_est, 1))
    is_stale = stale_seconds > (step_sec * 2.0)
    if is_stale:
        issues.append(f"Latest candle is stale by {stale_seconds}s (threshold={step_sec * 2}s).")

    missing_fields: list[str] = []
    if metrics:
        for name, m in metrics.items():
            if m.status == "MISSING" or m.value is None:
                missing_fields.append(name)
                issues.append(f"Metric '{name}' unavailable (MISSING — no synthetic fallback used).")

    # Compute deterministic integrity score
    total = max(1, len(candles))
    candle_penalty = ((invalid_bars + duplicate_timestamps + out_of_order_timestamps) / total) * 60.0
    gap_penalty = min(25.0, missing_candle_gaps * 5.0)
    stale_penalty = 15.0 if is_stale else 0.0
    field_penalty = min(20.0, len(missing_fields) * 4.0)
    score = max(0.0, round(100.0 - candle_penalty - gap_penalty - stale_penalty - field_penalty, 1))

    if invalid_bars > 0 or out_of_order_timestamps > 0:
        status = "INVALID"
    elif missing_candle_gaps > 0 or duplicate_timestamps > 0 or is_stale or len(missing_fields) > 0:
        status = "DEGRADED"
    else:
        status = "VALID"

    return DataValidationReport(
        symbol=symbol,
        interval=interval,
        status=status,
        candles_checked=len(candles),
        invalid_bars=invalid_bars,
        duplicate_timestamps=duplicate_timestamps,
        out_of_order_timestamps=out_of_order_timestamps,
        missing_candle_gaps=missing_candle_gaps,
        missing_candles_estimated=missing_candles_estimated,
        gap_timestamps=gap_timestamps[:20],
        stale_seconds=stale_seconds,
        is_stale=is_stale,
        missing_fields=missing_fields,
        integrity_score_pct=score,
        issues=issues,
        validated_at=now_iso,
    )
