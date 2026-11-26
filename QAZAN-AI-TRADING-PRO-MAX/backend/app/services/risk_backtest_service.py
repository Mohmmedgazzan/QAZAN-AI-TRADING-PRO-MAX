from datetime import datetime, timezone
import numpy as np

from app.core.exceptions import AppError
from app.db.database import get_db_connection
from app.schemas.platform import (
    BacktestHistoryItem,
    BacktestRequest,
    BacktestResponse,
    BacktestTrade,
    EquityPoint,
    RiskCalculateRequest,
    RiskCalculateResponse,
    RiskProfilePayload,
)
from app.services.market_service import fetch_market_klines
from app.services.quant_analysis_service import candles_to_df, compute_rsi


def calculate_risk_metrics(req: RiskCalculateRequest) -> RiskCalculateResponse:
    if req.entry_price == req.stop_loss:
        raise AppError(
            code="INVALID_RISK_PARAMETERS",
            message="Entry price and stop loss cannot be identical.",
            status_code=400,
        )

    direction = "LONG" if req.entry_price > req.stop_loss else "SHORT"
    stop_distance = abs(req.entry_price - req.stop_loss)
    reward_distance = (
        (req.take_profit - req.entry_price)
        if direction == "LONG"
        else (req.entry_price - req.take_profit)
    )
    if reward_distance <= 0:
        raise AppError(
            code="INVALID_RISK_PARAMETERS",
            message="Take profit must lie on the profitable side of entry price.",
            status_code=400,
        )

    risk_amount = req.account_balance * (req.risk_pct / 100.0)
    units = risk_amount / stop_distance
    notional = units * req.entry_price
    required_margin = notional / req.leverage
    rr = reward_distance / stop_distance
    reward_amount = risk_amount * rr
    stop_dist_pct = (stop_distance / req.entry_price) * 100.0

    # Approximate isolated liquidation price (0.5% maintenance margin)
    maint = 0.005
    if direction == "LONG":
        liq = req.entry_price * max(0.0, 1.0 - (1.0 / req.leverage) + maint)
    else:
        liq = req.entry_price * (1.0 + (1.0 / req.leverage) - maint)

    # Conservative half-Kelly assuming baseline 50% hit rate at computed R:R
    p = 0.50
    q = 1.0 - p
    kelly_full = max(0.0, (p * rr - q) / max(rr, 1e-9))
    kelly_half_pct = round(kelly_full * 0.5 * 100.0, 2)

    return RiskCalculateResponse(
        direction=direction,
        risk_amount_usdt=round(risk_amount, 2),
        reward_amount_usdt=round(reward_amount, 2),
        risk_reward_ratio=round(rr, 2),
        position_size_units=round(units, 6),
        position_notional_usdt=round(notional, 2),
        required_margin_usdt=round(required_margin, 2),
        stop_distance_pct=round(stop_dist_pct, 3),
        est_liquidation_price=round(liq, 6),
        kelly_fraction_pct=kelly_half_pct,
    )


def get_risk_profile() -> RiskProfilePayload:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM risk_profiles WHERE id = 1").fetchone()
    if not row:
        return RiskProfilePayload(
            account_balance=10000.0,
            risk_pct=1.0,
            default_rr=2.0,
            max_leverage=5.0,
            max_daily_loss_pct=3.0,
        )
    return RiskProfilePayload(
        account_balance=float(row["account_balance"]),
        risk_pct=float(row["risk_pct"]),
        default_rr=float(row["default_rr"]),
        max_leverage=float(row["max_leverage"]),
        max_daily_loss_pct=float(row["max_daily_loss_pct"]),
    )


def save_risk_profile(payload: RiskProfilePayload) -> RiskProfilePayload:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO risk_profiles
                (id, account_balance, risk_pct, default_rr, max_leverage, max_daily_loss_pct, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                account_balance = excluded.account_balance,
                risk_pct = excluded.risk_pct,
                default_rr = excluded.default_rr,
                max_leverage = excluded.max_leverage,
                max_daily_loss_pct = excluded.max_daily_loss_pct,
                updated_at = excluded.updated_at
            """,
            (
                payload.account_balance,
                payload.risk_pct,
                payload.default_rr,
                payload.max_leverage,
                payload.max_daily_loss_pct,
                now_iso,
            ),
        )
    return payload


async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    allowed_strategies = {"EMA_CROSS", "RSI_REVERSION", "BOS_MOMENTUM"}
    strategy = req.strategy.strip().upper()
    if strategy not in allowed_strategies:
        raise AppError(
            code="UNSUPPORTED_STRATEGY",
            message=f"Unsupported strategy '{strategy}'.",
            status_code=400,
            details=f"Allowed strategies: {', '.join(sorted(allowed_strategies))}",
        )

    klines = await fetch_market_klines(symbol=req.symbol, interval=req.interval, limit=400)
    df = candles_to_df(klines.candles)
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["roll_high20"] = df["high"].rolling(20).max().shift(1)
    df["roll_low20"] = df["low"].rolling(20).min().shift(1)

    capital = float(req.initial_capital)
    fee_rate = req.fee_pct / 100.0
    sl_frac = req.stop_loss_pct / 100.0
    tp_frac = req.take_profit_pct / 100.0

    position_side: str | None = None
    entry_price = 0.0
    entry_time = 0
    qty = 0.0

    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []
    returns_per_trade: list[float] = []

    for i in range(25, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = int(row["time"])
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

        # Check exit first if in position
        if position_side is not None:
            exit_price: float | None = None
            exit_reason = ""

            if position_side == "LONG":
                sl_price = entry_price * (1.0 - sl_frac)
                tp_price = entry_price * (1.0 + tp_frac)
                if l <= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                elif h >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"
                elif strategy == "EMA_CROSS" and float(row["ema9"]) < float(row["ema21"]):
                    exit_price = c
                    exit_reason = "SIGNAL_EXIT"
            else:
                sl_price = entry_price * (1.0 + sl_frac)
                tp_price = entry_price * (1.0 - tp_frac)
                if h >= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                elif l <= tp_price:
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"
                elif strategy == "EMA_CROSS" and float(row["ema9"]) > float(row["ema21"]):
                    exit_price = c
                    exit_reason = "SIGNAL_EXIT"

            if exit_price is not None:
                gross_pnl = (
                    (exit_price - entry_price) * qty
                    if position_side == "LONG"
                    else (entry_price - exit_price) * qty
                )
                exit_fee = abs(exit_price * qty) * fee_rate
                net_pnl = gross_pnl - exit_fee
                prev_cap = capital
                capital += net_pnl
                ret_pct = (net_pnl / max(prev_cap, 1e-9)) * 100.0
                returns_per_trade.append(ret_pct)
                trades.append(
                    BacktestTrade(
                        entry_time=entry_time,
                        exit_time=ts,
                        side=position_side,
                        entry_price=round(entry_price, 6),
                        exit_price=round(exit_price, 6),
                        pnl_usdt=round(net_pnl, 2),
                        return_pct=round(ret_pct, 2),
                        exit_reason=exit_reason,
                    )
                )
                position_side = None

        # Check entry if flat
        if position_side is None and capital > 10.0:
            enter_side: str | None = None
            if strategy == "EMA_CROSS":
                if float(prev["ema9"]) <= float(prev["ema21"]) and float(row["ema9"]) > float(row["ema21"]):
                    enter_side = "LONG"
                elif float(prev["ema9"]) >= float(prev["ema21"]) and float(row["ema9"]) < float(row["ema21"]):
                    enter_side = "SHORT"
            elif strategy == "RSI_REVERSION":
                if float(prev["rsi14"]) < 32.0 and float(row["rsi14"]) >= 32.0:
                    enter_side = "LONG"
                elif float(prev["rsi14"]) > 68.0 and float(row["rsi14"]) <= 68.0:
                    enter_side = "SHORT"
            elif strategy == "BOS_MOMENTUM":
                if c > float(row["roll_high20"]):
                    enter_side = "LONG"
                elif c < float(row["roll_low20"]):
                    enter_side = "SHORT"

            if enter_side is not None:
                entry_price = c
                entry_time = ts
                notional = capital * 0.95
                entry_fee = notional * fee_rate
                capital -= entry_fee
                qty = notional / entry_price
                position_side = enter_side

        # Mark-to-market equity
        mtm = capital
        if position_side == "LONG":
            mtm += (c - entry_price) * qty
        elif position_side == "SHORT":
            mtm += (entry_price - c) * qty
        equity_curve.append(EquityPoint(time=ts, value=round(mtm, 2)))

    # Close any open position at last bar
    if position_side is not None:
        last_row = df.iloc[-1]
        c = float(last_row["close"])
        ts = int(last_row["time"])
        gross_pnl = (c - entry_price) * qty if position_side == "LONG" else (entry_price - c) * qty
        net_pnl = gross_pnl - abs(c * qty) * fee_rate
        prev_cap = capital
        capital += net_pnl
        ret_pct = (net_pnl / max(prev_cap, 1e-9)) * 100.0
        returns_per_trade.append(ret_pct)
        trades.append(
            BacktestTrade(
                entry_time=entry_time,
                exit_time=ts,
                side=position_side,
                entry_price=round(entry_price, 6),
                exit_price=round(c, 6),
                pnl_usdt=round(net_pnl, 2),
                return_pct=round(ret_pct, 2),
                exit_reason="END_OF_DATA",
            )
        )
        if equity_curve:
            equity_curve[-1] = EquityPoint(time=ts, value=round(capital, 2))

    final_equity = round(capital, 2)
    total_return_pct = round(((final_equity - req.initial_capital) / req.initial_capital) * 100.0, 2)

    wins = [t.pnl_usdt for t in trades if t.pnl_usdt > 0]
    losses = [abs(t.pnl_usdt) for t in trades if t.pnl_usdt <= 0]
    win_rate = round((len(wins) / len(trades)) * 100.0, 2) if trades else 0.0
    profit_factor = round(sum(wins) / sum(losses), 2) if sum(losses) > 0 else (round(sum(wins), 2) if wins else 0.0)

    eq_vals = np.array([pt.value for pt in equity_curve] or [req.initial_capital], dtype=np.float64)
    peaks = np.maximum.accumulate(eq_vals)
    drawdowns = (peaks - eq_vals) / np.where(peaks > 0, peaks, 1.0)
    max_dd = round(float(np.max(drawdowns)) * 100.0, 2)

    if len(returns_per_trade) >= 2 and float(np.std(returns_per_trade)) > 0:
        sharpe = round(
            float(np.mean(returns_per_trade) / np.std(returns_per_trade) * np.sqrt(len(returns_per_trade))),
            2,
        )
    else:
        sharpe = 0.0

    executed_at = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs
                (symbol, interval, strategy, initial_capital, final_equity, total_return_pct,
                 win_rate_pct, max_drawdown_pct, total_trades, sharpe_ratio, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                klines.symbol,
                klines.interval,
                strategy,
                req.initial_capital,
                final_equity,
                total_return_pct,
                win_rate,
                max_dd,
                len(trades),
                sharpe,
                executed_at,
            ),
        )

    return BacktestResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        strategy=strategy,
        candle_count=len(df),
        initial_capital=req.initial_capital,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        total_trades=len(trades),
        equity_curve=equity_curve,
        trades=trades[-40:],
        executed_at=executed_at,
    )


def get_backtest_history(limit: int = 10) -> list[BacktestHistoryItem]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, interval, strategy, initial_capital, final_equity,
                   total_return_pct, win_rate_pct, max_drawdown_pct, total_trades,
                   sharpe_ratio, created_at
            FROM backtest_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [BacktestHistoryItem(**dict(r)) for r in rows]
