import asyncio
from datetime import datetime, timezone
import json
import math
import numpy as np
import pandas as pd

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.engine.technical_engine import filter_closed_candles
from app.schemas.backtest_pro import (
    LookAheadAudit,
    ProBacktestRequest,
    ProBacktestResponse,
    ProBacktestTrade,
    SavedStrategyReportItem,
    TimeframeBacktestSummary,
    ValidationGateItem,
    WalkForwardFoldResult,
    WalkForwardSummary,
)
from app.schemas.platform import EquityPoint
from app.services.market_service import ALLOWED_INTERVALS, fetch_market_klines
from app.services.quant_analysis_service import candles_to_df, compute_atr, compute_rsi

logger = get_logger("qazan.backtest.pro")

ALLOWED_PRO_STRATEGIES = {
    "EMA_CROSS",
    "RSI_REVERSION",
    "BOS_MOMENTUM",
    "SMC_CONFLUENCE",
}


def _prepare_causal_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute strictly causal technical columns.
    Breakout / swing bounds use .shift(1) so bar i ONLY compares against bars <= i - 1.
    At execution step t, signals are read exclusively from bar t - 1 and filled at bar t OPEN.
    """
    work = df.copy()
    work["ema9"] = work["close"].ewm(span=9, adjust=False).mean()
    work["ema21"] = work["close"].ewm(span=21, adjust=False).mean()
    work["ema50"] = work["close"].ewm(span=50, adjust=False).mean()
    work["rsi14"] = compute_rsi(work["close"], 14)
    work["atr14"] = compute_atr(work, 14)
    work["prior_high20"] = work["high"].rolling(20, min_periods=10).max().shift(1)
    work["prior_low20"] = work["low"].rolling(20, min_periods=10).min().shift(1)
    work["range_high40"] = work["high"].rolling(40, min_periods=20).max().shift(1)
    work["range_low40"] = work["low"].rolling(40, min_periods=20).min().shift(1)
    return work


def _evaluate_causal_signal_on_bar(work: pd.DataFrame, idx: int, strategy: str) -> str | None:
    """
    Evaluate entry direction strictly on closed bar `idx` using data <= `idx`.
    The caller fills any returned signal at bar `idx + 1` OPEN.
    """
    if idx < 2:
        return None
    cur = work.iloc[idx]
    prev = work.iloc[idx - 1]
    c = float(cur["close"])

    if strategy == "EMA_CROSS":
        p9, p21 = float(prev["ema9"]), float(prev["ema21"])
        c9, c21 = float(cur["ema9"]), float(cur["ema21"])
        if p9 <= p21 and c9 > c21:
            return "LONG"
        if p9 >= p21 and c9 < c21:
            return "SHORT"
        return None

    if strategy == "RSI_REVERSION":
        prsi, crsi = float(prev["rsi14"]), float(cur["rsi14"])
        if prsi < 32.0 and crsi >= 32.0:
            return "LONG"
        if prsi > 68.0 and crsi <= 68.0:
            return "SHORT"
        return None

    if strategy == "BOS_MOMENTUM":
        rh = cur["prior_high20"]
        rl = cur["prior_low20"]
        e50 = float(cur["ema50"])
        if pd.notna(rh) and c > float(rh) and c >= e50:
            return "LONG"
        if pd.notna(rl) and c < float(rl) and c <= e50:
            return "SHORT"
        return None

    if strategy == "SMC_CONFLUENCE":
        rng_h = cur["range_high40"]
        rng_l = cur["range_low40"]
        prior_l20 = cur["prior_low20"]
        prior_h20 = cur["prior_high20"]
        if pd.isna(rng_h) or pd.isna(rng_l) or pd.isna(prior_l20) or pd.isna(prior_h20):
            return None
        span = max(float(rng_h) - float(rng_l), 1e-9)
        pos_in_range = (c - float(rng_l)) / span
        crsi = float(cur["rsi14"])
        prsi = float(prev["rsi14"])
        l_bar = float(cur["low"])
        h_bar = float(cur["high"])
        # Bullish liquidity sweep of 20-bar low inside Discount (<0.48) + reclaim close
        if l_bar < float(prior_l20) and c > float(prior_l20) and pos_in_range <= 0.48 and crsi >= prsi:
            return "LONG"
        # Bearish liquidity sweep of 20-bar high inside Premium (>0.52) + rejection close
        if h_bar > float(prior_h20) and c < float(prior_h20) and pos_in_range >= 0.52 and crsi <= prsi:
            return "SHORT"
        # Discount/Premium EMA pullback confluence
        if pos_in_range <= 0.38 and float(prev["ema9"]) <= float(prev["ema21"]) and float(cur["ema9"]) > float(cur["ema21"]):
            return "LONG"
        if pos_in_range >= 0.62 and float(prev["ema9"]) >= float(prev["ema21"]) and float(cur["ema9"]) < float(cur["ema21"]):
            return "SHORT"
        return None

    return None


def _simulate_causal_segment(
    work: pd.DataFrame,
    start_idx: int,
    end_idx: int,
    strategy: str,
    timeframe: str,
    initial_capital: float,
    risk_per_trade_pct: float,
    fee_pct: float,
    slippage_pct: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> dict:
    """
    Simulate strictly causal execution on work.iloc[start_idx:end_idx]:
    - Signals computed on closed bar (t - 1) ONLY.
    - Orders filled at bar t OPEN +/- adverse slippage.
    - Stop Loss evaluated BEFORE Take Profit on intra-bar range [low, high].
    """
    capital = float(initial_capital)
    fee_rate = fee_pct / 100.0
    slip_rate = slippage_pct / 100.0
    sl_frac = stop_loss_pct / 100.0
    tp_frac = take_profit_pct / 100.0

    opens = work["open"].to_numpy(dtype=np.float64)
    highs = work["high"].to_numpy(dtype=np.float64)
    lows = work["low"].to_numpy(dtype=np.float64)
    closes = work["close"].to_numpy(dtype=np.float64)
    times = work["time"].to_numpy(dtype=np.int64)

    open_pos: dict | None = None
    trades: list[ProBacktestTrade] = []
    equity_curve: list[EquityPoint] = []
    returns_per_trade: list[float] = []
    total_fees = 0.0
    total_slippage = 0.0
    gross_pnl_total = 0.0

    safe_start = max(start_idx, 25)
    safe_end = min(end_idx, len(work))

    for t in range(safe_start, safe_end):
        o = float(opens[t])
        h = float(highs[t])
        l = float(lows[t])
        c = float(closes[t])
        ts = int(times[t])

        # 1. Fill signal that was confirmed strictly on prior closed bar (t - 1) at current bar OPEN
        if open_pos is None and capital > 25.0:
            sig = _evaluate_causal_signal_on_bar(work, t - 1, strategy)
            if sig is not None:
                signal_close = float(closes[t - 1])
                raw_open = o
                if sig == "LONG":
                    fill_entry = raw_open * (1.0 + slip_rate)
                    sl_px = fill_entry * (1.0 - sl_frac)
                    tp_px = fill_entry * (1.0 + tp_frac)
                else:
                    fill_entry = raw_open * (1.0 - slip_rate)
                    sl_px = fill_entry * (1.0 + sl_frac)
                    tp_px = fill_entry * (1.0 - tp_frac)

                stop_dist = max(abs(fill_entry - sl_px), fill_entry * 1e-6)
                risk_dollars = capital * (risk_per_trade_pct / 100.0)
                qty = min(risk_dollars / stop_dist, (capital * 2.0) / max(fill_entry, 1e-9))
                entry_notional = qty * fill_entry
                entry_fee = entry_notional * fee_rate
                entry_slip = abs(fill_entry - raw_open) * qty

                if capital > entry_fee + 5.0 and qty > 0:
                    capital -= entry_fee
                    total_fees += entry_fee
                    total_slippage += entry_slip
                    open_pos = {
                        "side": sig,
                        "entry_time": ts,
                        "signal_price": signal_close,
                        "raw_entry": raw_open,
                        "entry_price": fill_entry,
                        "stop_loss": sl_px,
                        "take_profit": tp_px,
                        "qty": qty,
                        "risk_dollars": risk_dollars,
                        "entry_fee": entry_fee,
                        "entry_slip": entry_slip,
                        "pre_trade_capital": capital + entry_fee,
                    }

        # 2. Check intra-bar exit on bar t (SL strictly checked BEFORE TP)
        if open_pos is not None:
            raw_exit: float | None = None
            exit_reason = ""
            side = open_pos["side"]
            if side == "LONG":
                if l <= open_pos["stop_loss"]:
                    raw_exit = open_pos["stop_loss"]
                    exit_reason = "STOP_LOSS"
                elif h >= open_pos["take_profit"]:
                    raw_exit = open_pos["take_profit"]
                    exit_reason = "TAKE_PROFIT"
                elif strategy == "EMA_CROSS" and float(work.iloc[t]["ema9"]) < float(work.iloc[t]["ema21"]):
                    raw_exit = c
                    exit_reason = "SIGNAL_EXIT"
            else:
                if h >= open_pos["stop_loss"]:
                    raw_exit = open_pos["stop_loss"]
                    exit_reason = "STOP_LOSS"
                elif l <= open_pos["take_profit"]:
                    raw_exit = open_pos["take_profit"]
                    exit_reason = "TAKE_PROFIT"
                elif strategy == "EMA_CROSS" and float(work.iloc[t]["ema9"]) > float(work.iloc[t]["ema21"]):
                    raw_exit = c
                    exit_reason = "SIGNAL_EXIT"

            if raw_exit is not None:
                fill_exit = raw_exit * (1.0 - slip_rate) if side == "LONG" else raw_exit * (1.0 + slip_rate)
                qty = open_pos["qty"]
                exit_slip = abs(fill_exit - raw_exit) * qty
                exit_fee = abs(fill_exit * qty) * fee_rate
                gross_ideal = (
                    (raw_exit - open_pos["raw_entry"]) * qty
                    if side == "LONG"
                    else (open_pos["raw_entry"] - raw_exit) * qty
                )
                slippage_total_trade = open_pos["entry_slip"] + exit_slip
                fee_total_trade = open_pos["entry_fee"] + exit_fee
                # Raw cash delta already had entry_fee subtracted on open
                slipped_pnl = (
                    (fill_exit - open_pos["entry_price"]) * qty
                    if side == "LONG"
                    else (open_pos["entry_price"] - fill_exit) * qty
                )
                capital += slipped_pnl - exit_fee
                total_fees += exit_fee
                total_slippage += exit_slip
                gross_pnl_total += gross_ideal

                net_pnl = slipped_pnl - fee_total_trade
                ret_pct = (net_pnl / max(open_pos["pre_trade_capital"], 1e-9)) * 100.0
                r_mult = net_pnl / max(open_pos["risk_dollars"], 1e-9)
                returns_per_trade.append(ret_pct)

                trades.append(
                    ProBacktestTrade(
                        entry_time=open_pos["entry_time"],
                        exit_time=ts,
                        side=side,
                        timeframe=timeframe.upper(),
                        signal_price=round(open_pos["signal_price"], 6),
                        entry_price=round(open_pos["entry_price"], 6),
                        stop_loss=round(open_pos["stop_loss"], 6),
                        take_profit=round(open_pos["take_profit"], 6),
                        exit_price=round(fill_exit, 6),
                        qty=round(qty, 6),
                        gross_pnl_usdt=round(gross_ideal, 2),
                        fee_cost_usdt=round(fee_total_trade, 2),
                        slippage_cost_usdt=round(slippage_total_trade, 2),
                        net_pnl_usdt=round(net_pnl, 2),
                        return_pct=round(ret_pct, 2),
                        r_multiple=round(r_mult, 2),
                        exit_reason=exit_reason,
                    )
                )
                open_pos = None

        # 3. Mark-to-market equity
        mtm = capital
        if open_pos is not None:
            qty = open_pos["qty"]
            if open_pos["side"] == "LONG":
                mtm += (c - open_pos["entry_price"]) * qty
            else:
                mtm += (open_pos["entry_price"] - c) * qty
        equity_curve.append(EquityPoint(time=ts, value=round(max(mtm, 0.0), 2)))

    # Close any open position cleanly at end of segment close
    if open_pos is not None and safe_end > safe_start:
        last_idx = safe_end - 1
        raw_exit = float(closes[last_idx])
        ts = int(times[last_idx])
        side = open_pos["side"]
        fill_exit = raw_exit * (1.0 - slip_rate) if side == "LONG" else raw_exit * (1.0 + slip_rate)
        qty = open_pos["qty"]
        exit_slip = abs(fill_exit - raw_exit) * qty
        exit_fee = abs(fill_exit * qty) * fee_rate
        gross_ideal = (
            (raw_exit - open_pos["raw_entry"]) * qty
            if side == "LONG"
            else (open_pos["raw_entry"] - raw_exit) * qty
        )
        slippage_total_trade = open_pos["entry_slip"] + exit_slip
        fee_total_trade = open_pos["entry_fee"] + exit_fee
        slipped_pnl = (
            (fill_exit - open_pos["entry_price"]) * qty
            if side == "LONG"
            else (open_pos["entry_price"] - fill_exit) * qty
        )
        capital += slipped_pnl - exit_fee
        total_fees += exit_fee
        total_slippage += exit_slip
        gross_pnl_total += gross_ideal

        net_pnl = slipped_pnl - fee_total_trade
        ret_pct = (net_pnl / max(open_pos["pre_trade_capital"], 1e-9)) * 100.0
        r_mult = net_pnl / max(open_pos["risk_dollars"], 1e-9)
        returns_per_trade.append(ret_pct)
        trades.append(
            ProBacktestTrade(
                entry_time=open_pos["entry_time"],
                exit_time=ts,
                side=side,
                timeframe=timeframe.upper(),
                signal_price=round(open_pos["signal_price"], 6),
                entry_price=round(open_pos["entry_price"], 6),
                stop_loss=round(open_pos["stop_loss"], 6),
                take_profit=round(open_pos["take_profit"], 6),
                exit_price=round(fill_exit, 6),
                qty=round(qty, 6),
                gross_pnl_usdt=round(gross_ideal, 2),
                fee_cost_usdt=round(fee_total_trade, 2),
                slippage_cost_usdt=round(slippage_total_trade, 2),
                net_pnl_usdt=round(net_pnl, 2),
                return_pct=round(ret_pct, 2),
                r_multiple=round(r_mult, 2),
                exit_reason="END_OF_SEGMENT",
            )
        )
        if equity_curve:
            equity_curve[-1] = EquityPoint(time=ts, value=round(max(capital, 0.0), 2))

    # Aggregate statistics
    total_trades = len(trades)
    wins = [t for t in trades if t.net_pnl_usdt > 0]
    losses = [t for t in trades if t.net_pnl_usdt <= 0]
    win_rate_pct = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    loss_rate = 1.0 - win_rate if total_trades > 0 else 0.0

    gross_win = sum(t.net_pnl_usdt for t in wins)
    gross_loss = abs(sum(t.net_pnl_usdt for t in losses))
    profit_factor = (
        round(gross_win / gross_loss, 2)
        if gross_loss > 0
        else (round(min(gross_win, 99.99), 2) if gross_win > 0 else 0.0)
    )

    avg_win_usdt = (gross_win / len(wins)) if wins else 0.0
    avg_loss_usdt = (gross_loss / len(losses)) if losses else 0.0
    expectancy_usdt = (win_rate * avg_win_usdt) - (loss_rate * avg_loss_usdt) if total_trades > 0 else 0.0

    avg_win_r = float(np.mean([t.r_multiple for t in wins])) if wins else 0.0
    avg_loss_r = float(np.mean([abs(t.r_multiple) for t in losses])) if losses else 0.0
    expectancy_r = (win_rate * avg_win_r) - (loss_rate * avg_loss_r) if total_trades > 0 else 0.0

    configured_rr = take_profit_pct / max(stop_loss_pct, 1e-6)
    realized_rr = (avg_win_usdt / avg_loss_usdt) if (wins and losses and avg_loss_usdt > 0) else (avg_win_r if wins else 0.0)

    eq_vals = np.array([pt.value for pt in equity_curve] or [initial_capital], dtype=np.float64)
    peaks = np.maximum.accumulate(eq_vals)
    dd_usdt_arr = peaks - eq_vals
    dd_pct_arr = dd_usdt_arr / np.where(peaks > 0, peaks, 1.0)
    max_dd_pct = float(np.max(dd_pct_arr) * 100.0)
    max_dd_usdt = float(np.max(dd_usdt_arr))

    if len(returns_per_trade) >= 2:
        mean_r = float(np.mean(returns_per_trade))
        std_r = float(np.std(returns_per_trade, ddof=1))
        sharpe = (mean_r / std_r) * math.sqrt(len(returns_per_trade)) if std_r > 0 else 0.0
        downside = [r for r in returns_per_trade if r < 0]
        down_std = float(np.std(downside, ddof=1)) if len(downside) >= 2 else (abs(downside[0]) if len(downside) == 1 else 0.0)
        sortino = (mean_r / down_std) * math.sqrt(len(returns_per_trade)) if down_std > 0 else sharpe
    else:
        sharpe = 0.0
        sortino = 0.0

    net_return_pct = ((capital - initial_capital) / initial_capital) * 100.0
    gross_return_pct = (gross_pnl_total / initial_capital) * 100.0

    return {
        "final_equity": round(capital, 2),
        "gross_return_pct": round(gross_return_pct, 2),
        "net_return_pct": round(net_return_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usdt": round(max_dd_usdt, 2),
        "expectancy_usdt": round(expectancy_usdt, 2),
        "expectancy_r": round(expectancy_r, 3),
        "configured_rr": round(configured_rr, 2),
        "realized_rr": round(realized_rr, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "total_fees_usdt": round(total_fees, 2),
        "total_slippage_usdt": round(total_slippage, 2),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _run_walk_forward(
    work: pd.DataFrame,
    strategy: str,
    timeframe: str,
    initial_capital: float,
    risk_per_trade_pct: float,
    fee_pct: float,
    slippage_pct: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    folds: int,
) -> WalkForwardSummary:
    """
    Expanding Walk-Forward Testing:
    Split usable bars into `folds` chronological out-of-sample blocks.
    For fold k: optimize causal SL/TP multipliers strictly on In-Sample [0 : oos_start],
    freeze parameters, and evaluate strictly on unseen Out-of-Sample [oos_start : oos_end].
    """
    n = len(work)
    warmup = min(40, max(25, n // 6))
    usable = max(1, n - warmup)
    # Reserve first 45% of usable span as minimum In-Sample anchor, split remaining 55% into OOS folds
    anchor_len = max(45, int(usable * 0.45))
    oos_total = max(folds * 15, n - (warmup + anchor_len))
    if warmup + anchor_len >= n - 12:
        anchor_len = max(30, int(usable * 0.40))
        oos_total = max(12, n - (warmup + anchor_len))

    fold_len = max(10, oos_total // folds)
    param_candidates = [
        (stop_loss_pct, take_profit_pct),
        (max(0.5, round(stop_loss_pct * 0.8, 2)), round(take_profit_pct * 1.1, 2)),
        (round(stop_loss_pct * 1.25, 2), round(take_profit_pct * 1.25, 2)),
    ]

    fold_results: list[WalkForwardFoldResult] = []
    oos_trades_all: list[ProBacktestTrade] = []
    oos_equity_curve: list[EquityPoint] = []
    running_capital = float(initial_capital)
    is_returns: list[float] = []

    times = work["time"].to_numpy(dtype=np.int64)

    for k in range(folds):
        oos_start = warmup + anchor_len + k * fold_len
        if oos_start >= n - 4:
            break
        oos_end = n if k == folds - 1 else min(n, oos_start + fold_len)
        if oos_end - oos_start < 5:
            continue

        # In-Sample search strictly on [warmup : oos_start]
        best_cfg = param_candidates[0]
        best_is_sim: dict | None = None
        best_score = -1e9
        for cand_sl, cand_tp in param_candidates:
            sim_is = _simulate_causal_segment(
                work=work,
                start_idx=warmup,
                end_idx=oos_start,
                strategy=strategy,
                timeframe=timeframe,
                initial_capital=initial_capital,
                risk_per_trade_pct=risk_per_trade_pct,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
                stop_loss_pct=cand_sl,
                take_profit_pct=cand_tp,
            )
            score = sim_is["expectancy_r"] * 100.0 + sim_is["net_return_pct"]
            if sim_is["total_trades"] < 2:
                score -= 50.0
            if score > best_score:
                best_score = score
                best_cfg = (cand_sl, cand_tp)
                best_is_sim = sim_is

        assert best_is_sim is not None
        is_returns.append(best_is_sim["net_return_pct"])

        # Evaluate frozen IS configuration strictly on unseen OOS [oos_start : oos_end]
        sim_oos = _simulate_causal_segment(
            work=work,
            start_idx=oos_start,
            end_idx=oos_end,
            strategy=strategy,
            timeframe=timeframe,
            initial_capital=running_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct,
            stop_loss_pct=best_cfg[0],
            take_profit_pct=best_cfg[1],
        )
        running_capital = max(sim_oos["final_equity"], 50.0)
        oos_trades_all.extend(sim_oos["trades"])
        oos_equity_curve.extend(sim_oos["equity_curve"])

        fold_passed = (
            sim_oos["total_trades"] >= 1
            and sim_oos["net_return_pct"] > 0.0
            and sim_oos["profit_factor"] >= 1.0
        )

        fold_results.append(
            WalkForwardFoldResult(
                fold_index=len(fold_results) + 1,
                is_bars=oos_start - warmup,
                oos_bars=oos_end - oos_start,
                is_start_time=int(times[warmup]),
                is_end_time=int(times[oos_start - 1]),
                oos_start_time=int(times[oos_start]),
                oos_end_time=int(times[oos_end - 1]),
                selected_sl_pct=best_cfg[0],
                selected_tp_pct=best_cfg[1],
                is_return_pct=best_is_sim["net_return_pct"],
                is_profit_factor=best_is_sim["profit_factor"],
                is_trades=best_is_sim["total_trades"],
                oos_return_pct=sim_oos["net_return_pct"],
                oos_win_rate_pct=sim_oos["win_rate_pct"],
                oos_profit_factor=sim_oos["profit_factor"],
                oos_expectancy_usdt=sim_oos["expectancy_usdt"],
                oos_expectancy_r=sim_oos["expectancy_r"],
                oos_max_drawdown_pct=sim_oos["max_drawdown_pct"],
                oos_trades=sim_oos["total_trades"],
                fold_passed=fold_passed,
            )
        )

    total_oos_trades = len(oos_trades_all)
    oos_wins = [t for t in oos_trades_all if t.net_pnl_usdt > 0]
    oos_losses = [t for t in oos_trades_all if t.net_pnl_usdt <= 0]
    oos_wr = (len(oos_wins) / total_oos_trades * 100.0) if total_oos_trades > 0 else 0.0
    w_rate = (len(oos_wins) / total_oos_trades) if total_oos_trades > 0 else 0.0
    l_rate = (1.0 - w_rate) if total_oos_trades > 0 else 0.0
    oos_gw = sum(t.net_pnl_usdt for t in oos_wins)
    oos_gl = abs(sum(t.net_pnl_usdt for t in oos_losses))
    oos_pf = round(oos_gw / oos_gl, 2) if oos_gl > 0 else (round(min(oos_gw, 99.99), 2) if oos_gw > 0 else 0.0)
    avg_w_usdt = (oos_gw / len(oos_wins)) if oos_wins else 0.0
    avg_l_usdt = (oos_gl / len(oos_losses)) if oos_losses else 0.0
    oos_exp_usdt = (w_rate * avg_w_usdt) - (l_rate * avg_l_usdt) if total_oos_trades > 0 else 0.0
    avg_w_r = float(np.mean([t.r_multiple for t in oos_wins])) if oos_wins else 0.0
    avg_l_r = float(np.mean([abs(t.r_multiple) for t in oos_losses])) if oos_losses else 0.0
    oos_exp_r = (w_rate * avg_w_r) - (l_rate * avg_l_r) if total_oos_trades > 0 else 0.0

    eq_arr = np.array([pt.value for pt in oos_equity_curve] or [initial_capital], dtype=np.float64)
    pks = np.maximum.accumulate(eq_arr)
    oos_max_dd = float(np.max((pks - eq_arr) / np.where(pks > 0, pks, 1.0)) * 100.0)
    combined_oos_return_pct = ((running_capital - initial_capital) / initial_capital) * 100.0

    avg_is_ret = float(np.mean(is_returns)) if is_returns else 0.0
    if abs(avg_is_ret) > 0.25:
        wf_eff = max(-200.0, min(250.0, (combined_oos_return_pct / abs(avg_is_ret)) * 100.0))
    else:
        wf_eff = 100.0 if combined_oos_return_pct > 0 else 0.0

    return WalkForwardSummary(
        folds_count=len(fold_results),
        folds_passed=sum(1 for f in fold_results if f.fold_passed),
        combined_oos_return_pct=round(combined_oos_return_pct, 2),
        combined_oos_win_rate_pct=round(oos_wr, 2),
        combined_oos_profit_factor=oos_pf,
        combined_oos_expectancy_usdt=round(oos_exp_usdt, 2),
        combined_oos_expectancy_r=round(oos_exp_r, 3),
        combined_oos_max_drawdown_pct=round(oos_max_dd, 2),
        combined_oos_trades=total_oos_trades,
        walk_forward_efficiency_pct=round(wf_eff, 1),
        oos_equity_curve=oos_equity_curve,
        folds=fold_results,
    )


def _evaluate_validation_gates(
    sim: dict,
    wf: WalkForwardSummary,
    req: ProBacktestRequest,
) -> tuple[str, bool, list[ValidationGateItem], list[str]]:
    """
    CRITICAL GOVERNANCE RULE:
    A strategy MUST NOT be marked as PASSED / successful unless ALL validation gates pass:
    1. Sufficient sample size (in-sample + walk-forward OOS trades)
    2. Positive Net Expectancy (USDT + R-multiple + OOS Expectancy R)
    3. Profit Factor above minimum threshold (and OOS Profit Factor >= 1.0)
    4. Maximum Drawdown within institutional ceiling
    5. Walk-Forward OOS profitability & fold consistency
    6. Zero Look-Ahead Bias + Real Fee/Slippage Friction enforced
    """
    min_oos_trades = max(3, wf.folds_count)
    min_folds_req = max(1, math.ceil(wf.folds_count / 2)) if wf.folds_count > 0 else 1

    gates = [
        ValidationGateItem(
            gate_key="min_sample_size",
            label="Minimum Statistical Sample Size",
            passed=(sim["total_trades"] >= req.min_trades_required and wf.combined_oos_trades >= min_oos_trades),
            actual_value=f"{sim['total_trades']} trades (OOS: {wf.combined_oos_trades})",
            threshold=f">= {req.min_trades_required} total & >= {min_oos_trades} OOS",
            reason=f"Requires at least {req.min_trades_required} total trades and {min_oos_trades} walk-forward OOS trades.",
        ),
        ValidationGateItem(
            gate_key="positive_expectancy",
            label="Positive Net & OOS Expectancy",
            passed=(sim["expectancy_usdt"] > 0 and sim["expectancy_r"] > 0 and wf.combined_oos_expectancy_r > 0),
            actual_value=f"${sim['expectancy_usdt']:.2f} ({sim['expectancy_r']:+.3f}R | OOS: {wf.combined_oos_expectancy_r:+.3f}R)",
            threshold="> $0.00 & > 0.000R (IS & OOS)",
            reason="Strategy expectancy must remain positive net of fees/slippage in both historical and OOS periods.",
        ),
        ValidationGateItem(
            gate_key="profit_factor_floor",
            label="Profit Factor Threshold",
            passed=(sim["profit_factor"] >= req.min_profit_factor and wf.combined_oos_profit_factor >= 1.0),
            actual_value=f"{sim['profit_factor']:.2f} (OOS: {wf.combined_oos_profit_factor:.2f})",
            threshold=f">= {req.min_profit_factor:.2f} (OOS >= 1.00)",
            reason=f"Net Profit Factor must reach {req.min_profit_factor:.2f} and out-of-sample >= 1.00.",
        ),
        ValidationGateItem(
            gate_key="max_drawdown_cap",
            label="Maximum Drawdown Preservation",
            passed=(sim["max_drawdown_pct"] <= req.max_allowed_drawdown_pct and wf.combined_oos_max_drawdown_pct <= req.max_allowed_drawdown_pct),
            actual_value=f"{sim['max_drawdown_pct']:.2f}% (OOS: {wf.combined_oos_max_drawdown_pct:.2f}%)",
            threshold=f"<= {req.max_allowed_drawdown_pct:.1f}%",
            reason=f"Drawdown must not exceed {req.max_allowed_drawdown_pct:.1f}% across history or walk-forward folds.",
        ),
        ValidationGateItem(
            gate_key="walk_forward_oos",
            label="Walk-Forward Out-of-Sample Consistency",
            passed=(wf.folds_count >= 2 and wf.combined_oos_return_pct > 0.0 and wf.folds_passed >= min_folds_req),
            actual_value=f"{wf.combined_oos_return_pct:+.2f}% ({wf.folds_passed}/{wf.folds_count} folds)",
            threshold=f"> 0% OOS & >= {min_folds_req} folds passed",
            reason="Unseen Walk-Forward folds must generate positive cumulative return and pass majority of splits.",
        ),
        ValidationGateItem(
            gate_key="causal_friction_audit",
            label="Zero Look-Ahead & Fee/Slippage Integrity",
            passed=(req.fee_pct > 0.0 or req.slippage_pct > 0.0),
            actual_value=f"Fee {req.fee_pct:.2f}% + Slip {req.slippage_pct:.2f}% | Next-Bar Open",
            threshold="Look-ahead disabled & friction > 0%",
            reason="Simulation must exclude look-ahead bias and model realistic exchange fees or slippage.",
        ),
    ]

    failed = [f"{g.label}: {g.actual_value} (req {g.threshold})" for g in gates if not g.passed]
    all_passed = len(failed) == 0
    return ("PASSED" if all_passed else "FAILED"), all_passed, gates, failed


def run_pro_backtest_on_df(
    df: pd.DataFrame,
    req: ProBacktestRequest,
    timeframe: str | None = None,
    as_of_ts: int | None = None,
) -> tuple[dict, WalkForwardSummary, str, bool, list[ValidationGateItem], list[str], int, bool]:
    tf = (timeframe or req.primary_interval).strip().lower()
    now_ts = int(datetime.now(timezone.utc).timestamp()) if as_of_ts is None else as_of_ts
    ordered, unclosed_excluded = filter_closed_candles(df, tf, as_of_ts=now_ts)
    work = _prepare_causal_indicators(ordered)
    warmup = min(40, max(25, len(work) // 6))

    sim = _simulate_causal_segment(
        work=work,
        start_idx=warmup,
        end_idx=len(work),
        strategy=req.strategy.strip().upper(),
        timeframe=tf,
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
        fee_pct=req.fee_pct,
        slippage_pct=req.slippage_pct,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
    )
    wf = _run_walk_forward(
        work=work,
        strategy=req.strategy.strip().upper(),
        timeframe=tf,
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
        fee_pct=req.fee_pct,
        slippage_pct=req.slippage_pct,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        folds=req.walk_forward_folds,
    )
    status, is_ok, gates, reasons = _evaluate_validation_gates(sim, wf, req)
    return sim, wf, status, is_ok, gates, reasons, len(work), unclosed_excluded


async def run_pro_backtest(req: ProBacktestRequest) -> ProBacktestResponse:
    strategy = req.strategy.strip().upper()
    if strategy not in ALLOWED_PRO_STRATEGIES:
        raise AppError(
            code="UNSUPPORTED_STRATEGY",
            message=f"Unsupported strategy '{strategy}'.",
            status_code=400,
            details=f"Allowed strategies: {', '.join(sorted(ALLOWED_PRO_STRATEGIES))}",
        )

    primary_tf = req.primary_interval.strip().lower()
    if primary_tf not in ALLOWED_INTERVALS:
        raise AppError(
            code="UNSUPPORTED_INTERVAL",
            message=f"Unsupported interval '{primary_tf}'.",
            status_code=400,
        )

    tf_list: list[str] = []
    for item in [primary_tf, *req.timeframes]:
        clean_tf = item.strip().lower()
        if clean_tf in ALLOWED_INTERVALS and clean_tf not in tf_list:
            tf_list.append(clean_tf)

    klines_map = {}
    fetched = await asyncio.gather(
        *[fetch_market_klines(symbol=req.symbol, interval=tf, limit=req.lookback_bars) for tf in tf_list]
    )
    for tf, res in zip(tf_list, fetched):
        klines_map[tf] = res

    primary_klines = klines_map[primary_tf]
    primary_df = candles_to_df(primary_klines.candles)
    sim, wf, status, is_ok, gates, reasons, closed_n, primary_unclosed_excluded = run_pro_backtest_on_df(
        primary_df,
        req=req.model_copy(update={"strategy": strategy}),
        timeframe=primary_tf,
    )

    tf_matrix: list[TimeframeBacktestSummary] = []
    for tf in tf_list:
        tf_df = candles_to_df(klines_map[tf].candles)
        t_sim, t_wf, t_status, _, _, _, t_closed_n, _ = run_pro_backtest_on_df(
            tf_df,
            req=req.model_copy(update={"strategy": strategy}),
            timeframe=tf,
        )
        tf_matrix.append(
            TimeframeBacktestSummary(
                timeframe=tf.upper(),
                candle_count=t_closed_n,
                total_trades=t_sim["total_trades"],
                win_rate_pct=t_sim["win_rate_pct"],
                profit_factor=t_sim["profit_factor"],
                max_drawdown_pct=t_sim["max_drawdown_pct"],
                expectancy_usdt=t_sim["expectancy_usdt"],
                expectancy_r=t_sim["expectancy_r"],
                configured_rr=t_sim["configured_rr"],
                realized_rr=t_sim["realized_rr"],
                gross_return_pct=t_sim["gross_return_pct"],
                net_return_pct=t_sim["net_return_pct"],
                total_fees_usdt=t_sim["total_fees_usdt"],
                total_slippage_usdt=t_sim["total_slippage_usdt"],
                walk_forward_oos_return_pct=t_wf.combined_oos_return_pct,
                validation_status=t_status,
            )
        )

    executed_at = datetime.now(timezone.utc).isoformat()
    look_ahead_audit = LookAheadAudit(
        look_ahead_bias_prevented=True,
        unclosed_bar_excluded=primary_unclosed_excluded or (len(primary_klines.candles) > closed_n),
        execution_timing="SIGNAL_ON_CLOSED_BAR_FILL_NEXT_OPEN",
        indicators_shifted_causally=True,
        intraday_sl_evaluated_before_tp=True,
        notes=(
            "Live unclosed bar dropped before feature computation; signals read strictly on closed bar t-1 "
            "and filled at bar t OPEN with adverse slippage + side fees. SL is checked before TP intra-bar."
        ),
    )

    response = ProBacktestResponse(
        run_id=None,
        symbol=primary_klines.symbol,
        strategy=strategy,
        primary_interval=primary_tf.upper(),
        candle_count=len(primary_klines.candles),
        closed_bars_tested=closed_n,
        initial_capital=round(req.initial_capital, 2),
        final_equity=sim["final_equity"],
        gross_return_pct=sim["gross_return_pct"],
        net_return_pct=sim["net_return_pct"],
        win_rate_pct=sim["win_rate_pct"],
        profit_factor=sim["profit_factor"],
        max_drawdown_pct=sim["max_drawdown_pct"],
        max_drawdown_usdt=sim["max_drawdown_usdt"],
        expectancy_usdt=sim["expectancy_usdt"],
        expectancy_r=sim["expectancy_r"],
        configured_rr=sim["configured_rr"],
        realized_rr=sim["realized_rr"],
        sharpe_ratio=sim["sharpe_ratio"],
        sortino_ratio=sim["sortino_ratio"],
        total_trades=sim["total_trades"],
        winning_trades=sim["winning_trades"],
        losing_trades=sim["losing_trades"],
        fee_pct=req.fee_pct,
        slippage_pct=req.slippage_pct,
        total_fees_usdt=sim["total_fees_usdt"],
        total_slippage_usdt=sim["total_slippage_usdt"],
        validation_status=status,
        is_strategy_successful=is_ok,
        validation_gates=gates,
        rejection_reasons=reasons,
        look_ahead_audit=look_ahead_audit,
        walk_forward=wf,
        timeframe_matrix=tf_matrix,
        equity_curve=sim["equity_curve"],
        trades=sim["trades"][-60:],
        executed_at=executed_at,
    )

    if req.persist:
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO strategy_backtest_reports (
                    strategy_name, symbol, primary_interval, tested_timeframes_json,
                    validation_status, is_strategy_successful, win_rate_pct, profit_factor,
                    max_drawdown_pct, expectancy_usdt, expectancy_r, realized_rr,
                    net_return_pct, walk_forward_oos_return_pct, total_fees_usdt,
                    total_slippage_usdt, total_trades, saved_bookmark, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    strategy,
                    primary_klines.symbol,
                    primary_tf.upper(),
                    json.dumps([t.upper() for t in tf_list]),
                    status,
                    1 if is_ok else 0,
                    sim["win_rate_pct"],
                    sim["profit_factor"],
                    sim["max_drawdown_pct"],
                    sim["expectancy_usdt"],
                    sim["expectancy_r"],
                    sim["realized_rr"],
                    sim["net_return_pct"],
                    wf.combined_oos_return_pct,
                    sim["total_fees_usdt"],
                    sim["total_slippage_usdt"],
                    sim["total_trades"],
                    response.model_dump_json(),
                    executed_at,
                ),
            )
            response.run_id = int(cur.lastrowid)

    return response


def list_saved_strategy_reports(
    limit: int = 20,
    only_passed: bool = False,
) -> list[SavedStrategyReportItem]:
    with get_db_connection() as conn:
        if only_passed:
            rows = conn.execute(
                """
                SELECT id, strategy_name, symbol, primary_interval, tested_timeframes_json,
                       validation_status, is_strategy_successful, win_rate_pct, profit_factor,
                       max_drawdown_pct, expectancy_usdt, expectancy_r, realized_rr,
                       net_return_pct, walk_forward_oos_return_pct, total_fees_usdt,
                       total_slippage_usdt, total_trades, saved_bookmark, created_at
                FROM strategy_backtest_reports
                WHERE validation_status = 'PASSED' AND is_strategy_successful = 1
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, strategy_name, symbol, primary_interval, tested_timeframes_json,
                       validation_status, is_strategy_successful, win_rate_pct, profit_factor,
                       max_drawdown_pct, expectancy_usdt, expectancy_r, realized_rr,
                       net_return_pct, walk_forward_oos_return_pct, total_fees_usdt,
                       total_slippage_usdt, total_trades, saved_bookmark, created_at
                FROM strategy_backtest_reports
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    items: list[SavedStrategyReportItem] = []
    for r in rows:
        try:
            tfs = json.loads(r["tested_timeframes_json"])
        except Exception:
            tfs = [r["primary_interval"]]
        items.append(
            SavedStrategyReportItem(
                id=int(r["id"]),
                strategy_name=str(r["strategy_name"]),
                symbol=str(r["symbol"]),
                primary_interval=str(r["primary_interval"]),
                tested_timeframes=tfs,
                validation_status=str(r["validation_status"]),
                is_strategy_successful=bool(r["is_strategy_successful"]),
                win_rate_pct=float(r["win_rate_pct"]),
                profit_factor=float(r["profit_factor"]),
                max_drawdown_pct=float(r["max_drawdown_pct"]),
                expectancy_usdt=float(r["expectancy_usdt"]),
                expectancy_r=float(r["expectancy_r"]),
                realized_rr=float(r["realized_rr"]),
                net_return_pct=float(r["net_return_pct"]),
                walk_forward_oos_return_pct=float(r["walk_forward_oos_return_pct"]),
                total_fees_usdt=float(r["total_fees_usdt"]),
                total_slippage_usdt=float(r["total_slippage_usdt"]),
                total_trades=int(r["total_trades"]),
                saved_bookmark=bool(r["saved_bookmark"]),
                created_at=str(r["created_at"]),
            )
        )
    return items


def delete_saved_strategy_report(report_id: int) -> dict:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM strategy_backtest_reports WHERE id = ?", (report_id,))
        if cur.rowcount == 0:
            raise AppError(
                code="STRATEGY_REPORT_NOT_FOUND",
                message=f"Saved strategy report #{report_id} not found.",
                status_code=404,
            )
    return {"deleted": True, "id": report_id}
