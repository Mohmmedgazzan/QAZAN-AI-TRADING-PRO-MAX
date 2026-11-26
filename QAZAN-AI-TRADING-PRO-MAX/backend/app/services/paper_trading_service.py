from datetime import datetime, timezone

from app.core.exceptions import AppError
from app.db.database import get_db_connection
from app.schemas.platform import PaperOrderRequest, PaperPositionView, PaperStateResponse
from app.services.market_service import ALLOWED_SYMBOLS
from app.services.market_tickers_service import fetch_spot_prices
from app.services.symbol_registry import is_symbol_tracked


def _calc_closed_stats(closed_rows: list) -> dict:
    total_closed = len(closed_rows)
    if total_closed == 0:
        return {
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_usdt": 0.0,
            "total_closed_trades": 0,
            "total_fees_paid_usdt": 0.0,
        }
    pnls = [float(r["realized_pnl"] or 0.0) for r in closed_rows]
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p <= 0]
    wr = (len(wins) / total_closed) * 100.0
    gw = sum(wins)
    gl = sum(losses)
    pf = round(gw / gl, 2) if gl > 0 else (round(min(gw, 99.99), 2) if gw > 0 else 0.0)
    w_rate = len(wins) / total_closed
    l_rate = 1.0 - w_rate
    avg_w = (gw / len(wins)) if wins else 0.0
    avg_l = (gl / len(losses)) if losses else 0.0
    exp = (w_rate * avg_w) - (l_rate * avg_l)
    fees = sum(float(r["entry_fee_usdt"] or 0.0) + float(r["exit_fee_usdt"] or 0.0) for r in closed_rows)
    return {
        "win_rate_pct": round(wr, 2),
        "profit_factor": pf,
        "expectancy_usdt": round(exp, 2),
        "total_closed_trades": total_closed,
        "total_fees_paid_usdt": round(fees, 2),
    }


async def get_paper_state() -> PaperStateResponse:
    with get_db_connection() as conn:
        acct = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
        open_rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC"
        ).fetchall()

    open_symbols = [str(r["symbol"]) for r in open_rows]
    live_prices = await fetch_spot_prices(open_symbols) if open_symbols else {}

    # Check if any open position has reached SL or TP on live mark price
    auto_triggered = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    if open_rows and live_prices:
        with get_db_connection() as conn:
            for r in open_rows:
                sym = str(r["symbol"])
                curr = live_prices.get(sym)
                if curr is None:
                    continue
                side = str(r["side"])
                sl = float(r["stop_loss"]) if r["stop_loss"] is not None else None
                tp = float(r["take_profit"]) if r["take_profit"] is not None else None

                trigger_reason: str | None = None
                fill_exit = curr
                if side == "LONG":
                    if sl is not None and curr <= sl:
                        trigger_reason = "AUTO_STOP_LOSS"
                        fill_exit = sl
                    elif tp is not None and curr >= tp:
                        trigger_reason = "AUTO_TAKE_PROFIT"
                        fill_exit = tp
                else:
                    if sl is not None and curr >= sl:
                        trigger_reason = "AUTO_STOP_LOSS"
                        fill_exit = sl
                    elif tp is not None and curr <= tp:
                        trigger_reason = "AUTO_TAKE_PROFIT"
                        fill_exit = tp

                if trigger_reason is not None:
                    qty = float(r["quantity"])
                    entry = float(r["entry_price"])
                    lev = float(r["leverage"])
                    margin = (entry * qty) / max(lev, 1.0)
                    exit_fee = abs(fill_exit * qty) * 0.0006
                    gross_pnl = (fill_exit - entry) * qty if side == "LONG" else (entry - fill_exit) * qty
                    entry_fee = float(r["entry_fee_usdt"] or 0.0)
                    net_realized = gross_pnl - entry_fee - exit_fee

                    acct_row = conn.execute("SELECT balance_usdt FROM paper_account WHERE id = 1").fetchone()
                    cur_bal = float(acct_row["balance_usdt"]) if acct_row else 0.0
                    updated_bal = max(0.0, cur_bal + margin + gross_pnl - exit_fee)
                    conn.execute(
                        "UPDATE paper_account SET balance_usdt = ?, updated_at = ? WHERE id = 1",
                        (updated_bal, now_iso),
                    )
                    conn.execute(
                        """
                        UPDATE paper_positions
                        SET status = 'CLOSED', exit_price = ?, realized_pnl = ?,
                            exit_fee_usdt = ?, close_reason = ?, closed_at = ?
                        WHERE id = ? AND status = 'OPEN'
                        """,
                        (round(fill_exit, 6), round(net_realized, 4), round(exit_fee, 4), trigger_reason, now_iso, int(r["id"])),
                    )
                    auto_triggered += 1

    # Reload updated snapshot after any SL/TP executions
    with get_db_connection() as conn:
        acct = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
        open_rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC"
        ).fetchall()
        closed_rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'CLOSED' ORDER BY id DESC LIMIT 40"
        ).fetchall()
        all_closed = conn.execute(
            "SELECT realized_pnl, entry_fee_usdt, exit_fee_usdt FROM paper_positions WHERE status = 'CLOSED'"
        ).fetchall()

    balance = float(acct["balance_usdt"]) if acct else 10000.0
    initial = float(acct["initial_balance"]) if acct else 10000.0
    updated_at = str(acct["updated_at"]) if acct else now_iso

    open_views: list[PaperPositionView] = []
    total_unrealized = 0.0
    locked_margin = 0.0
    open_fees = 0.0

    for r in open_rows:
        sym = str(r["symbol"])
        side = str(r["side"])
        qty = float(r["quantity"])
        entry = float(r["entry_price"])
        lev = float(r["leverage"])
        curr = live_prices.get(sym, entry)
        entry_fee = float(r["entry_fee_usdt"] or 0.0)
        slip_cost = float(r["slippage_cost_usdt"] or 0.0)
        open_fees += entry_fee

        pnl = (curr - entry) * qty if side == "LONG" else (entry - curr) * qty
        margin = (entry * qty) / max(lev, 1.0)
        roe = (pnl / max(margin, 1e-9)) * 100.0
        total_unrealized += pnl
        locked_margin += margin

        open_views.append(
            PaperPositionView(
                id=int(r["id"]),
                symbol=sym,
                side=side,
                quantity=round(qty, 6),
                entry_price=round(entry, 6),
                current_price=round(curr, 6),
                stop_loss=float(r["stop_loss"]) if r["stop_loss"] is not None else None,
                take_profit=float(r["take_profit"]) if r["take_profit"] is not None else None,
                leverage=lev,
                status="OPEN",
                unrealized_pnl=round(pnl, 2),
                unrealized_roe_pct=round(roe, 2),
                realized_pnl=None,
                exit_price=None,
                entry_fee_usdt=round(entry_fee, 2),
                exit_fee_usdt=0.0,
                slippage_cost_usdt=round(slip_cost, 2),
                close_reason=None,
                opened_at=str(r["opened_at"]),
                closed_at=None,
            )
        )

    closed_views: list[PaperPositionView] = []
    total_realized = 0.0
    for r in all_closed:
        total_realized += float(r["realized_pnl"] or 0.0)

    for r in closed_rows:
        rpnl = float(r["realized_pnl"] or 0.0)
        exit_p = float(r["exit_price"] or r["entry_price"])
        entry = float(r["entry_price"])
        qty = float(r["quantity"])
        lev = float(r["leverage"])
        margin = (entry * qty) / max(lev, 1.0)
        roe = (rpnl / max(margin, 1e-9)) * 100.0
        closed_views.append(
            PaperPositionView(
                id=int(r["id"]),
                symbol=str(r["symbol"]),
                side=str(r["side"]),
                quantity=round(qty, 6),
                entry_price=round(entry, 6),
                current_price=round(exit_p, 6),
                stop_loss=float(r["stop_loss"]) if r["stop_loss"] is not None else None,
                take_profit=float(r["take_profit"]) if r["take_profit"] is not None else None,
                leverage=lev,
                status="CLOSED",
                unrealized_pnl=0.0,
                unrealized_roe_pct=round(roe, 2),
                realized_pnl=round(rpnl, 2),
                exit_price=round(exit_p, 6),
                entry_fee_usdt=round(float(r["entry_fee_usdt"] or 0.0), 2),
                exit_fee_usdt=round(float(r["exit_fee_usdt"] or 0.0), 2),
                slippage_cost_usdt=round(float(r["slippage_cost_usdt"] or 0.0), 2),
                close_reason=str(r["close_reason"]) if r["close_reason"] else None,
                opened_at=str(r["opened_at"]),
                closed_at=str(r["closed_at"]) if r["closed_at"] else None,
            )
        )

    stats = _calc_closed_stats(all_closed)
    total_equity = balance + locked_margin + total_unrealized
    return PaperStateResponse(
        balance_usdt=round(balance, 2),
        initial_balance=round(initial, 2),
        total_equity_usdt=round(total_equity, 2),
        unrealized_pnl_usdt=round(total_unrealized, 2),
        realized_pnl_usdt=round(total_realized, 2),
        is_virtual=True,
        virtual_currency="VIRTUAL USDT",
        win_rate_pct=stats["win_rate_pct"],
        profit_factor=stats["profit_factor"],
        expectancy_usdt=stats["expectancy_usdt"],
        total_closed_trades=stats["total_closed_trades"],
        total_fees_paid_usdt=round(stats["total_fees_paid_usdt"] + open_fees, 2),
        auto_triggered_closes=auto_triggered,
        open_positions=open_views,
        closed_trades=closed_views,
        updated_at=updated_at,
    )


async def place_paper_order(req: PaperOrderRequest) -> PaperStateResponse:
    symbol = req.symbol.strip().upper()
    if symbol not in ALLOWED_SYMBOLS and not is_symbol_tracked(symbol):
        raise AppError(
            code="UNSUPPORTED_SYMBOL",
            message=f"Unsupported symbol '{symbol}' for paper trading.",
            status_code=400,
        )

    prices = await fetch_spot_prices([symbol])
    live_price = prices.get(symbol)
    if not live_price or live_price <= 0:
        raise AppError(
            code="PRICE_UNAVAILABLE",
            message=f"Live market price unavailable for {symbol}.",
            status_code=502,
        )

    slip_rate = req.slippage_pct / 100.0
    fee_rate = req.fee_pct / 100.0
    fill_price = live_price * (1.0 + slip_rate) if req.side == "LONG" else live_price * (1.0 - slip_rate)

    if req.stop_loss is not None:
        if req.side == "LONG" and req.stop_loss >= fill_price:
            raise AppError(
                code="INVALID_STOP_LOSS",
                message=f"LONG Stop Loss ({req.stop_loss}) must be below entry fill price ({fill_price:.4f}).",
                status_code=400,
            )
        if req.side == "SHORT" and req.stop_loss <= fill_price:
            raise AppError(
                code="INVALID_STOP_LOSS",
                message=f"SHORT Stop Loss ({req.stop_loss}) must be above entry fill price ({fill_price:.4f}).",
                status_code=400,
            )
    if req.take_profit is not None:
        if req.side == "LONG" and req.take_profit <= fill_price:
            raise AppError(
                code="INVALID_TAKE_PROFIT",
                message=f"LONG Take Profit ({req.take_profit}) must be above entry fill price ({fill_price:.4f}).",
                status_code=400,
            )
        if req.side == "SHORT" and req.take_profit >= fill_price:
            raise AppError(
                code="INVALID_TAKE_PROFIT",
                message=f"SHORT Take Profit ({req.take_profit}) must be below entry fill price ({fill_price:.4f}).",
                status_code=400,
            )

    required_margin = req.notional_usdt / req.leverage
    qty = req.notional_usdt / fill_price
    entry_fee = req.notional_usdt * fee_rate
    entry_slippage_cost = abs(fill_price - live_price) * qty
    total_debit = required_margin + entry_fee
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        acct = conn.execute("SELECT balance_usdt FROM paper_account WHERE id = 1").fetchone()
        balance = float(acct["balance_usdt"]) if acct else 0.0
        if total_debit > balance:
            raise AppError(
                code="INSUFFICIENT_PAPER_BALANCE",
                message=(
                    f"Required margin + fee (${total_debit:.2f}) exceeds available virtual balance (${balance:.2f})."
                ),
                status_code=400,
            )

        new_balance = balance - total_debit
        conn.execute(
            "UPDATE paper_account SET balance_usdt = ?, updated_at = ? WHERE id = 1",
            (new_balance, now_iso),
        )
        conn.execute(
            """
            INSERT INTO paper_positions
                (symbol, side, quantity, entry_price, stop_loss, take_profit, leverage, status,
                 entry_fee_usdt, slippage_cost_usdt, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
            """,
            (
                symbol,
                req.side,
                qty,
                round(fill_price, 6),
                req.stop_loss,
                req.take_profit,
                req.leverage,
                round(entry_fee, 4),
                round(entry_slippage_cost, 4),
                now_iso,
            ),
        )

    return await get_paper_state()


async def close_paper_position(position_id: int) -> PaperStateResponse:
    with get_db_connection() as conn:
        pos = conn.execute(
            "SELECT * FROM paper_positions WHERE id = ? AND status = 'OPEN'",
            (position_id,),
        ).fetchone()
        if not pos:
            raise AppError(
                code="POSITION_NOT_FOUND",
                message=f"Open paper position #{position_id} not found.",
                status_code=404,
            )

    symbol = str(pos["symbol"])
    prices = await fetch_spot_prices([symbol])
    raw_exit = prices.get(symbol, float(pos["entry_price"]))

    side = str(pos["side"])
    qty = float(pos["quantity"])
    entry = float(pos["entry_price"])
    lev = float(pos["leverage"])
    margin = (entry * qty) / max(lev, 1.0)
    entry_fee = float(pos["entry_fee_usdt"] or 0.0)
    prior_slip = float(pos["slippage_cost_usdt"] or 0.0)

    # Apply realistic exit slippage (0.03%) & exit fee (0.06%)
    exit_slip_rate = 0.0003
    exit_price = raw_exit * (1.0 - exit_slip_rate) if side == "LONG" else raw_exit * (1.0 + exit_slip_rate)
    exit_slip_cost = abs(exit_price - raw_exit) * qty
    exit_fee = abs(exit_price * qty) * 0.0006

    gross_pnl = (exit_price - entry) * qty if side == "LONG" else (entry - exit_price) * qty
    net_realized_pnl = gross_pnl - entry_fee - exit_fee
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        acct = conn.execute("SELECT balance_usdt FROM paper_account WHERE id = 1").fetchone()
        balance = float(acct["balance_usdt"]) if acct else 0.0
        updated_balance = max(0.0, balance + margin + gross_pnl - exit_fee)

        conn.execute(
            "UPDATE paper_account SET balance_usdt = ?, updated_at = ? WHERE id = 1",
            (updated_balance, now_iso),
        )
        conn.execute(
            """
            UPDATE paper_positions
            SET status = 'CLOSED', exit_price = ?, realized_pnl = ?,
                exit_fee_usdt = ?, slippage_cost_usdt = ?, close_reason = 'MANUAL_MARKET', closed_at = ?
            WHERE id = ?
            """,
            (
                round(exit_price, 6),
                round(net_realized_pnl, 4),
                round(exit_fee, 4),
                round(prior_slip + exit_slip_cost, 4),
                now_iso,
                position_id,
            ),
        )

    return await get_paper_state()


async def reset_paper_account(initial_balance: float = 10000.0) -> PaperStateResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM paper_positions")
        conn.execute(
            """
            INSERT INTO paper_account (id, balance_usdt, initial_balance, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                balance_usdt = excluded.balance_usdt,
                initial_balance = excluded.initial_balance,
                updated_at = excluded.updated_at
            """,
            (initial_balance, initial_balance, now_iso),
        )
    return await get_paper_state()
