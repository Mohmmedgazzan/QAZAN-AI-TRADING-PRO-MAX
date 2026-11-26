import React, { useCallback, useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { ProBacktestValidationView } from '@/components/engine/ProBacktestValidationView';
import { EquityChart } from '@/components/EquityChart';
import { useApp } from '@/contexts/AppContext';
import type { BacktestHistoryItem, BacktestRequest, BacktestResponse } from '@/types/platform';

export function BacktestingSection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [subtab, setSubtab] = useState<'pro' | 'classic'>('pro');
  const [strategy, setStrategy] = useState<BacktestRequest['strategy']>('EMA_CROSS');
  const [initialCapital, setInitialCapital] = useState(10000);
  const [feePct, setFeePct] = useState(0.1);
  const [slPct, setSlPct] = useState(2.0);
  const [tpPct, setTpPct] = useState(4.0);

  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await platformClient.getBacktestHistory());
    } catch {
      // ignore initial empty
    }
  }, []);

  const execute = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      setRunning(true);
      setError(null);
      try {
        const res = await platformClient.runBacktest({
          symbol: activeSymbol,
          interval: activeInterval,
          strategy,
          initial_capital: initialCapital,
          fee_pct: feePct,
          stop_loss_pct: slPct,
          take_profit_pct: tpPct,
        });
        setResult(res);
        void loadHistory();
      } catch (err) {
        setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
      } finally {
        setRunning(false);
      }
    },
    [activeSymbol, activeInterval, strategy, initialCapital, feePct, slPct, tpPct, loadHistory],
  );

  useEffect(() => {
    if (subtab === 'classic' && !result) {
      void execute();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subtab]);

  return (
    <section className="space-y-5 min-w-0">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1 min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections.backtesting} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            {subtab === 'pro' ? pt.btProSubtitle : pt.backtestSubtitle}
          </p>
        </div>

        <div className="inline-flex flex-wrap items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800 max-w-full">
          <button
            type="button"
            onClick={() => setSubtab('pro')}
            className={`min-h-[38px] px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors sm:whitespace-nowrap cursor-pointer ${
              subtab === 'pro'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {pt.btTabPro}
          </button>
          <button
            type="button"
            onClick={() => setSubtab('classic')}
            className={`min-h-[38px] px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors sm:whitespace-nowrap cursor-pointer ${
              subtab === 'classic'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {pt.btTabClassic}
          </button>
        </div>
      </div>

      {subtab === 'pro' ? (
        <ProBacktestValidationView />
      ) : (
        <div className="space-y-5">
      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      <form
        onSubmit={(e) => void execute(e)}
        className="qazan-card p-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end text-xs"
      >
        <label className="space-y-1">
          <span className="block text-slate-500 dark:text-slate-400">{pt.strategyLabel}</span>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as BacktestRequest['strategy'])}
            className="qazan-input font-mono"
          >
            <option value="EMA_CROSS">EMA Cross (9/21)</option>
            <option value="RSI_REVERSION">RSI Reversion</option>
            <option value="BOS_MOMENTUM">BOS Momentum (20)</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="block text-slate-500 dark:text-slate-400">{pt.initialCapital}</span>
          <input
            type="number"
            value={initialCapital}
            onChange={(e) => setInitialCapital(Number(e.target.value))}
            className="qazan-input font-mono tabular-nums"
          />
        </label>

        <label className="space-y-1">
          <span className="block text-slate-500 dark:text-slate-400">{pt.feePct}</span>
          <input
            type="number"
            step="0.05"
            value={feePct}
            onChange={(e) => setFeePct(Number(e.target.value))}
            className="qazan-input font-mono tabular-nums"
          />
        </label>

        <label className="space-y-1">
          <span className="block text-slate-500 dark:text-slate-400">{pt.slPct}</span>
          <input
            type="number"
            step="0.5"
            value={slPct}
            onChange={(e) => setSlPct(Number(e.target.value))}
            className="qazan-input font-mono tabular-nums"
          />
        </label>

        <label className="space-y-1">
          <span className="block text-slate-500 dark:text-slate-400">{pt.tpPct}</span>
          <input
            type="number"
            step="0.5"
            value={tpPct}
            onChange={(e) => setTpPct(Number(e.target.value))}
            className="qazan-input font-mono tabular-nums"
          />
        </label>

        <button type="submit" disabled={running} className="qazan-btn-gold w-full">
          <Play className="w-4 h-4" />
          <span>{pt.runBacktestBtn}</span>
        </button>
      </form>

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="qazan-card-gold p-3.5">
              <p className="text-[11px] text-slate-500">{pt.finalEquity}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                ${result.final_equity.toLocaleString('en-US')}
              </p>
            </div>
            <div className="qazan-card p-3.5">
              <p className="text-[11px] text-slate-500">{pt.totalReturn}</p>
              <p
                className={`mt-1 text-base font-mono font-bold tabular-nums ${
                  result.total_return_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                }`}
              >
                {result.total_return_pct >= 0 ? '+' : ''}
                {result.total_return_pct.toFixed(2)}%
              </p>
            </div>
            <div className="qazan-card p-3.5">
              <p className="text-[11px] text-slate-500">{pt.winRate}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums">{result.win_rate_pct.toFixed(1)}%</p>
            </div>
            <div className="qazan-card p-3.5">
              <p className="text-[11px] text-slate-500">{pt.profitFactor}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums">{result.profit_factor.toFixed(2)}</p>
            </div>
            <div className="qazan-card p-3.5">
              <p className="text-[11px] text-slate-500">{pt.maxDrawdown}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums text-red-600 dark:text-red-400">
                -{result.max_drawdown_pct.toFixed(2)}%
              </p>
            </div>
            <div className="qazan-card p-3.5">
              <p className="text-[11px] text-slate-500">{pt.sharpeRatio}</p>
              <p className="mt-1 text-base font-mono font-bold tabular-nums">
                {result.sharpe_ratio.toFixed(2)} ({result.total_trades})
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <h2 className="text-sm font-semibold">{pt.equityCurveTitle}</h2>
            <EquityChart points={result.equity_curve} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {result.trades.length > 0 && (
              <div className="qazan-card overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                  {pt.recentExecutions}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                        <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                        <th className="py-2.5 px-4 text-end">Entry / Exit</th>
                        <th className="py-2.5 px-4 text-end">PnL</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                      {[...result.trades].reverse().slice(0, 12).map((tr, i) => (
                        <tr key={i} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                          <td className="py-2.5 px-4 font-mono font-bold">
                            {tr.side} · {tr.exit_reason}
                          </td>
                          <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                            ${tr.entry_price.toFixed(2)} → ${tr.exit_price.toFixed(2)}
                          </td>
                          <td
                            className={`py-2.5 px-4 text-end font-mono tabular-nums font-bold ${
                              tr.pnl_usdt >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {tr.pnl_usdt >= 0 ? '+' : ''}${tr.pnl_usdt.toFixed(2)} ({tr.return_pct.toFixed(2)}%)
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {history.length > 0 && (
              <div className="qazan-card overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                  {pt.recentBacktests}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                        <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.strategyLabel}</th>
                        <th className="py-2.5 px-4 text-end">{pt.totalReturn}</th>
                        <th className="py-2.5 px-4 text-end">{pt.winRate}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                      {history.map((h) => (
                        <tr key={h.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                          <td className="py-2.5 px-4 font-mono font-semibold">{h.symbol} ({h.interval})</td>
                          <td className="py-2.5 px-4 font-mono">{h.strategy}</td>
                          <td
                            className={`py-2.5 px-4 text-end font-mono tabular-nums font-bold ${
                              h.total_return_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {h.total_return_pct >= 0 ? '+' : ''}{h.total_return_pct.toFixed(2)}%
                          </td>
                          <td className="py-2.5 px-4 text-end font-mono tabular-nums">{h.win_rate_pct.toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
        </div>
      )}
    </section>
  );
}
