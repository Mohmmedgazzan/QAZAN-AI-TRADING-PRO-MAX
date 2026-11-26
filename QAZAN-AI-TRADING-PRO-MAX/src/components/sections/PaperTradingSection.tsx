import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { PaperStateResponse } from '@/types/platform';

const VIRTUAL_CAPITAL_PRESETS = [5000, 10000, 25000, 100000] as const;

export function PaperTradingSection() {
  const { activeSymbol, pt } = useApp();
  const [state, setState] = useState<PaperStateResponse | null>(null);
  const [notionalUsdt, setNotionalUsdt] = useState(500);
  const [leverage, setLeverage] = useState(2);
  const [stopLossInput, setStopLossInput] = useState('');
  const [takeProfitInput, setTakeProfitInput] = useState('');
  const [feePct, setFeePct] = useState(0.06);
  const [slippagePct, setSlippagePct] = useState(0.03);
  const [customVirtualCapital, setCustomVirtualCapital] = useState(10000);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'open' | 'closed'>('open');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await platformClient.getPaperState();
      setState(s);
      setCustomVirtualCapital(s.initial_balance);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submitOrder = async (side: 'LONG' | 'SHORT') => {
    setSubmitting(true);
    setError(null);
    try {
      const sl = stopLossInput.trim() ? Number(stopLossInput) : null;
      const tp = takeProfitInput.trim() ? Number(takeProfitInput) : null;
      const updated = await platformClient.placePaperOrder({
        symbol: activeSymbol,
        side,
        notional_usdt: notionalUsdt,
        leverage,
        stop_loss: sl && Number.isFinite(sl) ? sl : null,
        take_profit: tp && Number.isFinite(tp) ? tp : null,
        fee_pct: feePct,
        slippage_pct: slippagePct,
      });
      setState(updated);
      setStopLossInput('');
      setTakeProfitInput('');
      setTab('open');
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const closePos = async (id: number) => {
    setSubmitting(true);
    setError(null);
    try {
      setState(await platformClient.closePaperPosition(id));
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const resetAcct = async (amount?: number) => {
    setSubmitting(true);
    setError(null);
    try {
      const target = amount ?? customVirtualCapital;
      const updated = await platformClient.resetPaperAccount(target);
      setState(updated);
      setCustomVirtualCapital(updated.initial_balance);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-5 min-w-0">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1 min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['paper-trading']} · {activeSymbol}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.paperSubtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void resetAcct(10000)}
            disabled={submitting}
            className="qazan-btn-secondary"
          >
            <RotateCcw className="w-4 h-4" />
            <span>{pt.resetAccount}</span>
          </button>

          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="qazan-btn-gold"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{pt.refresh}</span>
          </button>
        </div>
      </div>

      {/* Virtual Money Governance Banner */}
      <div className="p-3.5 rounded-xl border border-[#D4AF37]/40 bg-[#D4AF37]/10 text-[#8A6506] dark:text-[#E5C76B] flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldCheck className="w-4 h-4 shrink-0" />
          <span className="font-semibold">{pt.paperVirtualBanner}</span>
        </div>
        {state && (
          <span className="font-mono font-bold tabular-nums">
            {state.virtual_currency ?? 'VIRTUAL USDT'} · Base: ${state.initial_balance.toLocaleString('en-US')}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {state && state.auto_triggered_closes ? (
        <div role="status" className="p-3 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200 text-xs font-mono">
          {pt.paperAutoTriggerNote} ({state.auto_triggered_closes})
        </div>
      ) : null}

      {state && (
        <>
          {/* Virtual Portfolio Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="qazan-card-gold p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.paperEquity}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                ${state.total_equity_usdt.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.availableBalance}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums">
                ${state.balance_usdt.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.unrealizedPnl}</p>
              <p className={`mt-1 text-base font-mono font-bold tabular-nums ${state.unrealized_pnl_usdt >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                {state.unrealized_pnl_usdt >= 0 ? '+' : ''}${state.unrealized_pnl_usdt.toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.realizedPnl}</p>
              <p className={`mt-1 text-base font-mono font-bold tabular-nums ${state.realized_pnl_usdt >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                {state.realized_pnl_usdt >= 0 ? '+' : ''}${state.realized_pnl_usdt.toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.paperWinRateLabel}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums">
                {(state.win_rate_pct ?? 0).toFixed(1)}% · PF {(state.profit_factor ?? 0).toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.paperFeesPaidLabel}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums text-amber-600 dark:text-amber-400">
                ${(state.total_fees_paid_usdt ?? 0).toFixed(2)}
              </p>
            </div>
          </div>

          {/* Virtual Capital Allocator */}
          <div className="qazan-card p-4 flex flex-col sm:flex-row sm:items-end justify-between gap-3 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-slate-500 font-medium">{pt.paperStartingCapital}:</span>
              {VIRTUAL_CAPITAL_PRESETS.map((amt) => (
                <button
                  key={amt}
                  type="button"
                  disabled={submitting}
                  onClick={() => void resetAcct(amt)}
                  className={`min-h-[34px] px-3 py-1 rounded-md font-mono font-semibold border cursor-pointer ${
                    state.initial_balance === amt
                      ? 'bg-[#D4AF37]/15 border-[#D4AF37] text-[#9A7209] dark:text-[#E5C76B]'
                      : 'border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  ${amt.toLocaleString('en-US')}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="number"
                min={100}
                step={500}
                value={customVirtualCapital}
                onChange={(e) => setCustomVirtualCapital(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums w-32"
              />
              <button
                type="button"
                disabled={submitting}
                onClick={() => void resetAcct(customVirtualCapital)}
                className="qazan-btn-secondary shrink-0"
              >
                {pt.paperApplyReset}
              </button>
            </div>
          </div>

          {/* Institutional Execution Ticket */}
          <div className="qazan-card p-5 space-y-4">
            <h2 className="text-sm font-semibold">{pt.placeOrderTitle} ({activeSymbol})</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-8 gap-3 items-end text-xs">
              <label className="space-y-1">
                <span className="block text-slate-500">{pt.notionalUsdt}</span>
                <input
                  type="number"
                  min={15}
                  step="50"
                  value={notionalUsdt}
                  onChange={(e) => setNotionalUsdt(Number(e.target.value))}
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1">
                <span className="block text-slate-500">{pt.leverage}</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={leverage}
                  onChange={(e) => setLeverage(Number(e.target.value))}
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1">
                <span className="block text-slate-500">{pt.optionalSl}</span>
                <input
                  type="number"
                  step="any"
                  value={stopLossInput}
                  onChange={(e) => setStopLossInput(e.target.value)}
                  placeholder="—"
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1">
                <span className="block text-slate-500">{pt.optionalTp}</span>
                <input
                  type="number"
                  step="any"
                  value={takeProfitInput}
                  onChange={(e) => setTakeProfitInput(e.target.value)}
                  placeholder="—"
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1">
                <span className="block text-slate-500">{pt.feePct}</span>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={feePct}
                  onChange={(e) => setFeePct(Number(e.target.value))}
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1">
                <span className="block text-slate-500">{pt.btSlippagePct}</span>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={slippagePct}
                  onChange={(e) => setSlippagePct(Number(e.target.value))}
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <button
                type="button"
                disabled={submitting}
                onClick={() => void submitOrder('LONG')}
                className="min-h-[44px] px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-bold cursor-pointer"
              >
                {pt.sideLong}
              </button>

              <button
                type="button"
                disabled={submitting}
                onClick={() => void submitOrder('SHORT')}
                className="min-h-[44px] px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white font-bold cursor-pointer"
              >
                {pt.sideShort}
              </button>
            </div>
          </div>

          {/* Positions & History */}
          <div className="qazan-card overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setTab('open')}
                className={`min-h-[38px] px-3 rounded-md text-xs font-semibold cursor-pointer ${
                  tab === 'open'
                    ? 'bg-[#D4AF37] text-[#06080D]'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                }`}
              >
                {pt.openPositionsTab} ({state.open_positions.length})
              </button>
              <button
                type="button"
                onClick={() => setTab('closed')}
                className={`min-h-[38px] px-3 rounded-md text-xs font-semibold cursor-pointer ${
                  tab === 'closed'
                    ? 'bg-[#D4AF37] text-[#06080D]'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                }`}
              >
                {pt.closedTradesTab} ({state.closed_trades.length})
              </button>
            </div>

            {tab === 'open' ? (
              state.open_positions.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">{pt.noOpenPositions}</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                        <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                        <th className="py-2.5 px-4 text-end">Entry / Mark</th>
                        <th className="py-2.5 px-4 text-end">SL / TP</th>
                        <th className="py-2.5 px-4 text-end">{pt.unrealizedPnl}</th>
                        <th className="py-2.5 px-4 text-end">{pt.actionCol}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                      {state.open_positions.map((pos) => (
                        <tr key={pos.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                          <td className="py-3 px-4 font-mono font-bold">
                            {pos.symbol} ({pos.leverage}x)
                          </td>
                          <td className={`py-3 px-4 font-mono font-bold ${pos.side === 'LONG' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {pos.side}
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums">
                            ${pos.entry_price.toFixed(2)} / ${pos.current_price.toFixed(2)}
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums text-slate-500">
                            {pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : '—'} / {pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : '—'}
                          </td>
                          <td className={`py-3 px-4 text-end font-mono tabular-nums font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)} ({pos.unrealized_roe_pct.toFixed(2)}%)
                          </td>
                          <td className="py-3 px-4 text-end">
                            <button
                              type="button"
                              disabled={submitting}
                              onClick={() => void closePos(pos.id)}
                              className="min-h-[36px] px-3 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold cursor-pointer"
                            >
                              {pt.closePosition}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : state.closed_trades.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">{pt.noClosedTrades}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                      <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                      <th className="py-2.5 px-4 text-end">Entry / Exit</th>
                      <th className="py-2.5 px-4 text-end">Fee + Slip</th>
                      <th className="py-2.5 px-4 text-end">{pt.realizedPnl}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {state.closed_trades.map((pos) => (
                      <tr key={pos.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-3 px-4 font-mono font-bold">
                          {pos.symbol} {pos.close_reason ? `· ${pos.close_reason}` : ''}
                        </td>
                        <td className={`py-3 px-4 font-mono font-bold ${pos.side === 'LONG' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                          {pos.side}
                        </td>
                        <td className="py-3 px-4 text-end font-mono tabular-nums">
                          ${pos.entry_price.toFixed(2)} / ${(pos.exit_price ?? pos.current_price).toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-end font-mono tabular-nums text-amber-600 dark:text-amber-400">
                          -${((pos.entry_fee_usdt ?? 0) + (pos.exit_fee_usdt ?? 0) + (pos.slippage_cost_usdt ?? 0)).toFixed(2)}
                        </td>
                        <td className={`py-3 px-4 text-end font-mono tabular-nums font-bold ${(pos.realized_pnl ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                          {(pos.realized_pnl ?? 0) >= 0 ? '+' : ''}${(pos.realized_pnl ?? 0).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
