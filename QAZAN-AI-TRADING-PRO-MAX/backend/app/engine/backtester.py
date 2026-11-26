from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.engine.models import (
    CausalBacktestEquityPoint,
    CausalBacktestRequest,
    CausalBacktestResponse,
    CausalBacktestTrade,
)
from app.engine.technical_engine import (
    _persist_technical_run,
    analyze_dataframe_causal,
    filter_closed_candles,
)
from app.services.market_service import fetch_market_klines

logger = get_logger("qazan.engine.backtest")


def run_causal_backtest_on_df(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str = "4h",
    initial_capital: float = 10000.0,
    risk_per_trade_pct: float = 1.0,
    fee_pct: float = 0.06,
    rr_target: float = 2.0,
    persist: bool = True,
) -> CausalBacktestResponse:
    """
    Strictly causal walk-forward historical backtester.
    At every step t, the engine ONLY receives bars <= t (sliding window ending at t),
    completely eliminating any possibility of look-ahead bias.
    Entries execute at bar t+1 open after closed-candle confirmation at bar t.
    """
    ordered, _ = filter_closed_candles(df, timeframe.lower(), as_of_ts=None)
    n = len(ordered)
    warmup = min(65, max(30, n // 4))

    opens = ordered["open"].to_numpy(dtype=np.float64)
    highs = ordered["high"].to_numpy(dtype=np.float64)
    lows = ordered["low"].to_numpy(dtype=np.float64)
    closes = ordered["close"].to_numpy(dtype=np.float64)
    times = ordered["time"].to_numpy(dtype=np.int64)

    equity = float(initial_capital)
    peak_equity = equity
    max_dd_pct = 0.0

    trades: list[CausalBacktestTrade] = []
    equity_curve: list[CausalBacktestEquityPoint] = []
    trade_returns: list[float] = []

    seen_breach_keys: set[tuple[int, str, float]] = set()
    breakouts_confirmed = 0
    fakeouts_filtered = 0
    stop_hunts_detected = 0

    open_pos: dict | None = None
    pending_entry: dict | None = None

    for t in range(warmup, n):
        o = float(opens[t])
        h = float(highs[t])
        l = float(lows[t])
        c = float(closes[t])
        ts = int(times[t])

        # 1. Execute causal entry scheduled from prior closed bar (t - 1) at bar t open
        if pending_entry is not None and open_pos is None:
            entry_px = o
            sl_px = pending_entry["stop_loss"]
            side = pending_entry["side"]
            # Validate SL makes sense against actual bar open
            valid_sl = (side == "LONG" and sl_px < entry_px) or (side == "SHORT" and sl_px > entry_px)
            if valid_sl:
                risk_dist = abs(entry_px - sl_px)
                tp_px = (
                    entry_px + rr_target * risk_dist
                    if side == "LONG"
                    else entry_px - rr_target * risk_dist
                )
                risk_dollars = equity * (risk_per_trade_pct / 100.0)
                qty = risk_dollars / risk_dist
                # Cap notional at 2x equity to stay realistic
                max_qty = (equity * 2.0) / entry_px
                qty = min(qty, max_qty)
                open_pos = {
                    "entry_time": ts,
                    "setup_type": pending_entry["setup_type"],
                    "side": side,
                    "entry_price": entry_px,
                    "stop_loss": sl_px,
                    "take_profit": tp_px,
                    "qty": qty,
                }
            pending_entry = None

        # 2. Check exit of open position on bar t (conservative: SL evaluated before TP)
        if open_pos is not None:
            exit_px: float | None = None
            exit_reason: str | None = None
            if open_pos["side"] == "LONG":
                if l <= open_pos["stop_loss"]:
                    exit_px = open_pos["stop_loss"]
                    exit_reason = "SL"
                elif h >= open_pos["take_profit"]:
                    exit_px = open_pos["take_profit"]
                    exit_reason = "TP"
            else:
                if h >= open_pos["stop_loss"]:
                    exit_px = open_pos["stop_loss"]
                    exit_reason = "SL"
                elif l <= open_pos["take_profit"]:
                    exit_px = open_pos["take_profit"]
                    exit_reason = "TP"

            if exit_px is not None and exit_reason is not None:
                direction_mult = 1.0 if open_pos["side"] == "LONG" else -1.0
                gross_pnl = (exit_px - open_pos["entry_price"]) * direction_mult * open_pos["qty"]
                fees = (open_pos["entry_price"] + exit_px) * open_pos["qty"] * (fee_pct / 100.0)
                net_pnl = gross_pnl - fees
                ret_pct = (net_pnl / equity) * 100.0 if equity > 0 else 0.0
                equity += net_pnl
                trade_returns.append(ret_pct)
                trades.append(
                    CausalBacktestTrade(
                        entry_time=open_pos["entry_time"],
                        exit_time=ts,
                        setup_type=open_pos["setup_type"],
                        side=open_pos["side"],
                        entry_price=round(open_pos["entry_price"], 6),
                        stop_loss=round(open_pos["stop_loss"], 6),
                        take_profit=round(open_pos["take_profit"], 6),
                        exit_price=round(exit_px, 6),
                        pnl_usdt=round(net_pnl, 2),
                        return_pct=round(ret_pct, 2),
                        exit_reason=exit_reason,
                    )
                )
                open_pos = None

        # 3. Strictly causal analysis on bars <= t ONLY (slice ends at t + 1)
        win_start = max(0, (t + 1) - 160)
        window_df = ordered.iloc[win_start : t + 1]
        snap = analyze_dataframe_causal(window_df, timeframe=timeframe, as_of_ts=None)

        for br in snap.level_breaches:
            key = (br.confirmed_time, br.classification, br.level_price)
            if key in seen_breach_keys:
                continue
            seen_breach_keys.add(key)
            if br.classification == "BREAKOUT":
                breakouts_confirmed += 1
            elif br.classification == "FAKEOUT":
                fakeouts_filtered += 1
            elif br.classification == "STOP_HUNT":
                stop_hunts_detected += 1

        # 4. Schedule deterministic setup ONLY on closed bar t when no position is open
        if open_pos is None and pending_entry is None and t < n - 1:
            latest_breaches = [b for b in snap.level_breaches if b.confirmed_time == ts]
            if latest_breaches:
                ev = latest_breaches[-1]
                atr_pad = max(snap.atr_14 * 1.4, c * 0.004)
                if ev.classification == "BREAKOUT":
                    if ev.side == "BULLISH" and snap.market_bias == "BULLISH":
                        pending_entry = {
                            "setup_type": "BREAKOUT_CONTINUATION",
                            "side": "LONG",
                            "stop_loss": min(ev.level_price - 0.5 * snap.atr_14, c - atr_pad),
                        }
                    elif ev.side == "BEARISH" and snap.market_bias == "BEARISH":
                        pending_entry = {
                            "setup_type": "BREAKOUT_CONTINUATION",
                            "side": "SHORT",
                            "stop_loss": max(ev.level_price + 0.5 * snap.atr_14, c + atr_pad),
                        }
                elif ev.classification == "STOP_HUNT":
                    # Stop Hunt reversal into Discount / Premium
                    if (
                        ev.side == "BEARISH"
                        and snap.premium_discount.zone == "DISCOUNT"
                        and snap.market_bias != "BEARISH"
                    ):
                        pending_entry = {
                            "setup_type": "STOP_HUNT_POI",
                            "side": "LONG",
                            "stop_loss": l - 0.35 * snap.atr_14,
                        }
                    elif (
                        ev.side == "BULLISH"
                        and snap.premium_discount.zone == "PREMIUM"
                        and snap.market_bias != "BULLISH"
                    ):
                        pending_entry = {
                            "setup_type": "STOP_HUNT_POI",
                            "side": "SHORT",
                            "stop_loss": h + 0.35 * snap.atr_14,
                        }

        peak_equity = max(peak_equity, equity)
        dd = ((peak_equity - equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        max_dd_pct = max(max_dd_pct, dd)
        equity_curve.append(CausalBacktestEquityPoint(time=ts, value=round(equity, 2)))

    # Mark-to-market close any open position at final closed candle
    if open_pos is not None:
        final_px = float(closes[-1])
        final_ts = int(times[-1])
        direction_mult = 1.0 if open_pos["side"] == "LONG" else -1.0
        gross_pnl = (final_px - open_pos["entry_price"]) * direction_mult * open_pos["qty"]
        fees = (open_pos["entry_price"] + final_px) * open_pos["qty"] * (fee_pct / 100.0)
        net_pnl = gross_pnl - fees
        ret_pct = (net_pnl / equity) * 100.0 if equity > 0 else 0.0
        equity += net_pnl
        trade_returns.append(ret_pct)
        trades.append(
            CausalBacktestTrade(
                entry_time=open_pos["entry_time"],
                exit_time=final_ts,
                setup_type=open_pos["setup_type"],
                side=open_pos["side"],
                entry_price=round(open_pos["entry_price"], 6),
                stop_loss=round(open_pos["stop_loss"], 6),
                take_profit=round(open_pos["take_profit"], 6),
                exit_price=round(final_px, 6),
                pnl_usdt=round(net_pnl, 2),
                return_pct=round(ret_pct, 2),
                exit_reason="EOD",
            )
        )
        if equity_curve:
            equity_curve[-1] = CausalBacktestEquityPoint(time=final_ts, value=round(equity, 2))

    total_trades = len(trades)
    wins = [tr for tr in trades if tr.pnl_usdt > 0]
    losses = [tr for tr in trades if tr.pnl_usdt <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profit = sum(tr.pnl_usdt for tr in wins)
    gross_loss = abs(sum(tr.pnl_usdt for tr in losses))
    profit_factor = (
        round(gross_profit / gross_loss, 2)
        if gross_loss > 0
        else (round(gross_profit, 2) if gross_profit > 0 else 0.0)
    )
    total_return_pct = ((equity - initial_capital) / initial_capital) * 100.0

    if len(trade_returns) >= 2:
        mean_r = float(np.mean(trade_returns))
        std_r = float(np.std(trade_returns, ddof=1))
        sharpe = (mean_r / std_r) * math.sqrt(len(trade_returns)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    now_iso = datetime.now(timezone.utc).isoformat()
    result = CausalBacktestResponse(
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        bars_tested=n - warmup,
        look_ahead_bias_prevented=True,
        initial_capital=round(initial_capital, 2),
        final_equity=round(equity, 2),
        total_return_pct=round(total_return_pct, 2),
        win_rate_pct=round(win_rate, 2),
        profit_factor=profit_factor,
        max_drawdown_pct=round(max_dd_pct, 2),
        sharpe_ratio=round(sharpe, 2),
        total_trades=total_trades,
        breakouts_confirmed=breakouts_confirmed,
        fakeouts_filtered=fakeouts_filtered,
        stop_hunts_detected=stop_hunts_detected,
        trades=trades,
        equity_curve=equity_curve,
        executed_at=now_iso,
    )

    if persist:
        bias_tag = "BULLISH" if total_return_pct >= 0 else "BEARISH"
        run_id = _persist_technical_run(
            symbol=symbol.upper(),
            run_type="CAUSAL_BACKTEST",
            ltf_interval=timeframe.upper(),
            market_bias=bias_tag,
            market_phase=f"TRADES:{total_trades}",
            market_regime=f"WR:{round(win_rate, 1)}%",
            payload_json=result.model_dump_json(),
            created_at=now_iso,
        )
        result.run_id = run_id
        logger.info(
            "Recorded causal historical backtest #%d for %s (%s): trades=%d win_rate=%.1f%% return=%.2f%%",
            run_id,
            symbol.upper(),
            timeframe.upper(),
            total_trades,
            win_rate,
            total_return_pct,
        )

    return result


async def run_causal_historical_backtest(
    payload: CausalBacktestRequest,
    persist: bool = True,
) -> CausalBacktestResponse:
    klines = await fetch_market_klines(
        symbol=payload.symbol.strip().upper(),
        interval=payload.timeframe.strip().lower(),
        limit=payload.lookback_bars,
    )
    df = pd.DataFrame([c.model_dump() for c in klines.candles])
    return run_causal_backtest_on_df(
        df=df,
        symbol=klines.symbol,
        timeframe=klines.interval,
        initial_capital=payload.initial_capital,
        risk_per_trade_pct=payload.risk_per_trade_pct,
        fee_pct=payload.fee_pct,
        rr_target=payload.rr_target,
        persist=persist,
    )
