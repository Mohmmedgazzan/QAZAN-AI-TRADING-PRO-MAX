import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Play, ShieldAlert, Trash2 } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { EquityChart } from '@/components/EquityChart';
import { useApp } from '@/contexts/AppContext';
import type {
  ProBacktestRequest,
  ProBacktestResponse,
  ProStrategyType,
  SavedStrategyReportItem,
} from '@/types/platform';

const AVAILABLE_TFS = ['15m', '1h', '4h', '1d'] as const;

export function ProBacktestValidationView() {
  const { activeSymbol, activeInterval, pt } = useApp();

  const [strategy, setStrategy] = useState<ProStrategyType>('EMA_CROSS');
  const [selectedTfs, setSelectedTfs] = useState<string[]>(['15m', '1h', '4h', '1d']);
  const [lookbackBars, setLookbackBars] = useState(420);
  const [initialCapital, setInitialCapital] = useState(10000);
  const [riskPerTradePct, setRiskPerTradePct] = useState(1.0);
  const [feePct, setFeePct] = useState(0.06);
  const [slippagePct, setSlippagePct] = useState(0.04);
  const [slPct, setSlPct] = useState(2.0);
  const [tpPct, setTpPct] = useState(4.0);
  const [wfFolds, setWfFolds] = useState(4);
  const [minTrades, setMinTrades] = useState(8);
  const [minPf, setMinPf] = useState(1.15);
  const [maxDdLimit, setMaxDdLimit] = useState(25.0);

  const [curveMode, setCurveMode] = useState<'historical' | 'oos'>('historical');
  const [onlyPassedFilter, setOnlyPassedFilter] = useState(false);

  const [result, setResult] = useState<ProBacktestResponse | null>(null);
  const [savedReports, setSavedReports] = useState<SavedStrategyReportItem[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSaved = useCallback(async (onlyPassed = onlyPassedFilter) => {
    try {
      const items = await platformClient.getSavedStrategyReports(onlyPassed, 20);
      setSavedReports(items);
    } catch {
      // Ignore initial empty state
    }
  }, [onlyPassedFilter]);

  const toggleTf = (tf: string) => {
    setSelectedTfs((prev) => {
      if (prev.includes(tf)) {
        if (prev.length === 1 && tf === activeInterval) return prev;
        const filtered = prev.filter((item) => item !== tf);
        return filtered.length > 0 ? filtered : [activeInterval];
      }
      return [...prev, tf];
    });
  };

  const executePro = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      setRunning(true);
      setError(null);
      try {
        const tfPayload = Array.from(new Set([activeInterval, ...selectedTfs]));
        const payload: ProBacktestRequest = {
          symbol: activeSymbol,
          strategy,
          primary_interval: activeInterval,
          timeframes: tfPayload,
          lookback_bars: lookbackBars,
          initial_capital: initialCapital,
          risk_per_trade_pct: riskPerTradePct,
          fee_pct: feePct,
          slippage_pct: slippagePct,
          stop_loss_pct: slPct,
          take_profit_pct: tpPct,
          walk_forward_folds: wfFolds,
          min_trades_required: minTrades,
          min_profit_factor: minPf,
          max_allowed_drawdown_pct: maxDdLimit,
          persist: true,
        };
        const res = await platformClient.runProBacktest(payload);
        setResult(res);
        void loadSaved(onlyPassedFilter);
      } catch (err) {
        setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
      } finally {
        setRunning(false);
      }
    },
    [
      activeSymbol,
      activeInterval,
      strategy,
      selectedTfs,
      lookbackBars,
      initialCapital,
      riskPerTradePct,
      feePct,
      slippagePct,
      slPct,
      tpPct,
      wfFolds,
      minTrades,
      minPf,
      maxDdLimit,
      loadSaved,
      onlyPassedFilter,
    ],
  );

  useEffect(() => {
    void executePro();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadSaved(onlyPassedFilter);
  }, [onlyPassedFilter, loadSaved]);

  const handleDelete = async (id: number) => {
    try {
      await platformClient.deleteSavedStrategyReport(id);
      void loadSaved(onlyPassedFilter);
    } catch {
      // ignore if already removed
    }
  };

  const activeCurve =
    result && curveMode === 'oos' && result.walk_forward.oos_equity_curve.length > 0
      ? result.walk_forward.oos_equity_curve
      : result?.equity_curve ?? [];

  return (
    <div className="space-y-5 min-w-0">
      <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.btProSubtitle}</p>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono"
        >
          {error}
        </div>
      )}

      {/* Configuration Panel */}
      <form onSubmit={(e) => void executePro(e)} className="qazan-card p-4 space-y-4 text-xs">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.strategyLabel}</span>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as ProStrategyType)}
              className="qazan-input font-mono"
            >
              <option value="EMA_CROSS">EMA Cross (9/21)</option>
              <option value="RSI_REVERSION">RSI Reversion (14)</option>
              <option value="BOS_MOMENTUM">BOS Momentum (20)</option>
              <option value="SMC_CONFLUENCE">SMC Liquidity Confluence</option>
            </select>
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.initialCapital}</span>
            <input
              type="number"
              min={100}
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btRiskPerTrade}</span>
            <input
              type="number"
              step="0.25"
              min={0.1}
              max={10}
              value={riskPerTradePct}
              onChange={(e) => setRiskPerTradePct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.feePct}</span>
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

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btSlippagePct}</span>
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

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.engineBtBars}</span>
            <input
              type="number"
              min={150}
              max={500}
              step={20}
              value={lookbackBars}
              onChange={(e) => setLookbackBars(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.slPct}</span>
            <input
              type="number"
              step="0.25"
              min={0.2}
              value={slPct}
              onChange={(e) => setSlPct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.tpPct}</span>
            <input
              type="number"
              step="0.25"
              min={0.2}
              value={tpPct}
              onChange={(e) => setTpPct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btWalkForwardFolds}</span>
            <input
              type="number"
              min={2}
              max={6}
              value={wfFolds}
              onChange={(e) => setWfFolds(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btMinTrades}</span>
            <input
              type="number"
              min={3}
              max={50}
              value={minTrades}
              onChange={(e) => setMinTrades(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btMinPf}</span>
            <input
              type="number"
              step="0.05"
              min={0.8}
              max={4}
              value={minPf}
              onChange={(e) => setMinPf(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1 min-w-0">
            <span className="block text-slate-500 dark:text-slate-400 truncate">{pt.btMaxDdLimit}</span>
            <input
              type="number"
              step="1"
              min={5}
              max={60}
              value={maxDdLimit}
              onChange={(e) => setMaxDdLimit(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-slate-200 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500 dark:text-slate-400 font-medium">{pt.btTimeframesSelect}:</span>
            {AVAILABLE_TFS.map((tf) => {
              const checked = selectedTfs.includes(tf) || tf === activeInterval;
              return (
                <button
                  key={tf}
                  type="button"
                  onClick={() => toggleTf(tf)}
                  className={`min-h-[36px] px-3 py-1 rounded-md font-mono font-semibold text-xs border transition-colors cursor-pointer ${
                    checked
                      ? 'bg-[#D4AF37]/15 border-[#D4AF37] text-[#9A7209] dark:text-[#E5C76B]'
                      : 'border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400'
                  }`}
                >
                  {tf.toUpperCase()}
                </button>
              );
            })}
          </div>

          <button type="submit" disabled={running} className="qazan-btn-gold shrink-0">
            <Play className="w-4 h-4" />
            <span>{pt.runBacktestBtn}</span>
          </button>
        </div>
      </form>

      {result && (
        <div className="space-y-5">
          {/* Mandatory Strategy Validation Banner */}
          {result.is_strategy_successful ? (
            <div
              role="status"
              className="p-4 rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200 flex items-start gap-3"
            >
              <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-500 mt-0.5" />
              <div className="space-y-1 min-w-0">
                <p className="text-sm font-bold">{pt.btPassedBanner}</p>
                <p className="text-xs font-mono opacity-85">
                  {result.strategy} · {result.symbol} ({result.primary_interval}) · Run #{result.run_id ?? '—'}
                </p>
              </div>
            </div>
          ) : (
            <div
              role="alert"
              className="p-4 rounded-xl border border-red-500/40 bg-red-500/10 text-red-800 dark:text-red-200 flex items-start gap-3"
            >
              <ShieldAlert className="w-5 h-5 shrink-0 text-red-500 mt-0.5" />
              <div className="space-y-1.5 min-w-0">
                <p className="text-sm font-bold">{pt.btFailedBanner}</p>
                <ul className="text-xs font-mono space-y-0.5 list-disc list-inside opacity-90">
                  {result.rejection_reasons.map((r, idx) => (
                    <li key={idx} className="break-words">{r}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Zero Look-Ahead Audit Metadata (clean typographic row, no pill islands) */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-400 px-1 font-mono">
            <span className="font-semibold text-slate-900 dark:text-slate-200">{pt.btLookAheadAuditTitle}:</span>
            <span>{result.look_ahead_audit.execution_timing}</span>
            <span aria-hidden="true">·</span>
            <span>Unclosed Bar Excluded: {result.look_ahead_audit.unclosed_bar_excluded ? 'YES' : 'NO'}</span>
            <span aria-hidden="true">·</span>
            <span>SL Before TP: {result.look_ahead_audit.intraday_sl_evaluated_before_tp ? 'YES' : 'NO'}</span>
            <span aria-hidden="true">·</span>
            <span>Closed Bars: {result.closed_bars_tested}</span>
          </div>

          {/* Primary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            <div className="qazan-card-gold p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.finalEquity}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                ${result.final_equity.toLocaleString('en-US')}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.totalReturn}</p>
              <p
                className={`mt-1 text-sm sm:text-base font-mono font-bold tabular-nums ${
                  result.net_return_pct >= 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {result.net_return_pct >= 0 ? '+' : ''}
                {result.net_return_pct.toFixed(2)}%
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.winRate}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums">
                {result.win_rate_pct.toFixed(1)}% ({result.winning_trades}/{result.total_trades})
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.profitFactor}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums">
                {result.profit_factor.toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.maxDrawdown}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums text-red-600 dark:text-red-400">
                -{result.max_drawdown_pct.toFixed(2)}%
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.btExpectancyLabel}</p>
              <p
                className={`mt-1 text-sm sm:text-base font-mono font-bold tabular-nums ${
                  result.expectancy_r > 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                ${result.expectancy_usdt.toFixed(2)} ({result.expectancy_r >= 0 ? '+' : ''}{result.expectancy_r.toFixed(2)}R)
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.btRealizedRrLabel}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums">
                1 : {result.realized_rr.toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-3.5 min-w-0">
              <p className="text-[11px] text-slate-500 truncate">{pt.btFeesSlippageTotal}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold tabular-nums text-amber-600 dark:text-amber-400">
                -${(result.total_fees_usdt + result.total_slippage_usdt).toFixed(2)}
              </p>
            </div>
          </div>

          {/* Equity Curve Switcher (Historical vs Walk-Forward OOS) */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">{pt.equityCurveTitle}</h2>
              <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setCurveMode('historical')}
                  className={`min-h-[32px] px-3 py-1 rounded text-xs font-semibold cursor-pointer ${
                    curveMode === 'historical'
                      ? 'bg-[#D4AF37] text-[#06080D]'
                      : 'text-slate-600 dark:text-slate-400'
                  }`}
                >
                  Historical Equity
                </button>
                <button
                  type="button"
                  onClick={() => setCurveMode('oos')}
                  className={`min-h-[32px] px-3 py-1 rounded text-xs font-semibold cursor-pointer ${
                    curveMode === 'oos'
                      ? 'bg-[#D4AF37] text-[#06080D]'
                      : 'text-slate-600 dark:text-slate-400'
                  }`}
                >
                  Walk-Forward OOS
                </button>
              </div>
            </div>
            <EquityChart points={activeCurve} />
          </div>

          {/* 6 Validation Gates Checklist */}
          <div className="qazan-card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">{pt.btValidationGatesTitle}</h2>
              <span
                className={`text-xs font-mono font-bold ${
                  result.is_strategy_successful
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {result.is_strategy_successful ? pt.btStatusPassed : pt.btStatusFailed}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-start">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                    <th className="py-2.5 px-4 text-start">Gate</th>
                    <th className="py-2.5 px-4 text-start">Actual</th>
                    <th className="py-2.5 px-4 text-start">Required Threshold</th>
                    <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                  {result.validation_gates.map((g) => (
                    <tr key={g.gate_key} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                      <td className="py-2.5 px-4 font-medium">{g.label}</td>
                      <td className="py-2.5 px-4 font-mono tabular-nums">{g.actual_value}</td>
                      <td className="py-2.5 px-4 font-mono text-slate-500">{g.threshold}</td>
                      <td
                        className={`py-2.5 px-4 text-end font-mono font-bold ${
                          g.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {g.passed ? 'PASS' : 'FAIL'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Walk-Forward Testing Table & Multi-Timeframe Comparison */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 space-y-1">
                <h2 className="text-sm font-semibold">{pt.btWalkForwardTitle}</h2>
                <p className="text-xs font-mono text-slate-500">
                  {pt.btWfFoldsPassed}: {result.walk_forward.folds_passed}/{result.walk_forward.folds_count}
                  {' · '}
                  {pt.btWfOosReturn}: {result.walk_forward.combined_oos_return_pct >= 0 ? '+' : ''}
                  {result.walk_forward.combined_oos_return_pct.toFixed(2)}%
                  {' · '}
                  {pt.btWfEfficiency}: {result.walk_forward.walk_forward_efficiency_pct.toFixed(1)}%
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-3 text-start">Fold</th>
                      <th className="py-2.5 px-3 text-end">IS %</th>
                      <th className="py-2.5 px-3 text-end">OOS %</th>
                      <th className="py-2.5 px-3 text-end">OOS PF</th>
                      <th className="py-2.5 px-3 text-end">OOS Exp(R)</th>
                      <th className="py-2.5 px-3 text-end">{pt.engineStatusCol}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {result.walk_forward.folds.map((f) => (
                      <tr key={f.fold_index} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-2.5 px-3 font-mono font-semibold">
                          #{f.fold_index} ({f.is_bars}/{f.oos_bars})
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          {f.is_return_pct >= 0 ? '+' : ''}
                          {f.is_return_pct.toFixed(2)}%
                        </td>
                        <td
                          className={`py-2.5 px-3 text-end font-mono tabular-nums font-bold ${
                            f.oos_return_pct >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {f.oos_return_pct >= 0 ? '+' : ''}
                          {f.oos_return_pct.toFixed(2)}%
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          {f.oos_profit_factor.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          {f.oos_expectancy_r >= 0 ? '+' : ''}
                          {f.oos_expectancy_r.toFixed(2)}R
                        </td>
                        <td
                          className={`py-2.5 px-3 text-end font-mono font-bold ${
                            f.fold_passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {f.fold_passed ? 'PASS' : 'FAIL'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <h2 className="text-sm font-semibold">{pt.btMultiTfTitle}</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-3 text-start">TF</th>
                      <th className="py-2.5 px-3 text-end">{pt.winRate}</th>
                      <th className="py-2.5 px-3 text-end">PF</th>
                      <th className="py-2.5 px-3 text-end">DD</th>
                      <th className="py-2.5 px-3 text-end">Exp(R)</th>
                      <th className="py-2.5 px-3 text-end">Net %</th>
                      <th className="py-2.5 px-3 text-end">{pt.engineStatusCol}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {result.timeframe_matrix.map((row) => (
                      <tr key={row.timeframe} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-2.5 px-3 font-mono font-bold">{row.timeframe}</td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">{row.win_rate_pct.toFixed(1)}%</td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">{row.profit_factor.toFixed(2)}</td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums text-red-600 dark:text-red-400">
                          -{row.max_drawdown_pct.toFixed(1)}%
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          {row.expectancy_r >= 0 ? '+' : ''}
                          {row.expectancy_r.toFixed(2)}R
                        </td>
                        <td
                          className={`py-2.5 px-3 text-end font-mono tabular-nums font-bold ${
                            row.net_return_pct >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {row.net_return_pct >= 0 ? '+' : ''}
                          {row.net_return_pct.toFixed(2)}%
                        </td>
                        <td
                          className={`py-2.5 px-3 text-end font-mono font-bold ${
                            row.validation_status === 'PASSED'
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {row.validation_status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Trades Ledger with Fee + Slippage Breakdown */}
          {result.trades.length > 0 && (
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                {pt.recentExecutions}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-3 text-start">{pt.directionCol}</th>
                      <th className="py-2.5 px-3 text-end">Entry / Exit</th>
                      <th className="py-2.5 px-3 text-end">Fees + Slip</th>
                      <th className="py-2.5 px-3 text-end">R-Mult</th>
                      <th className="py-2.5 px-3 text-end">Net PnL</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {[...result.trades].reverse().slice(0, 12).map((tr, i) => (
                      <tr key={i} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-2.5 px-3 font-mono font-bold">
                          {tr.side} · {tr.exit_reason}
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          ${tr.entry_price.toFixed(2)} → ${tr.exit_price.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums text-amber-600 dark:text-amber-400">
                          -${(tr.fee_cost_usdt + tr.slippage_cost_usdt).toFixed(2)}
                        </td>
                        <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                          {tr.r_multiple >= 0 ? '+' : ''}
                          {tr.r_multiple.toFixed(2)}R
                        </td>
                        <td
                          className={`py-2.5 px-3 text-end font-mono tabular-nums font-bold ${
                            tr.net_pnl_usdt >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {tr.net_pnl_usdt >= 0 ? '+' : ''}${tr.net_pnl_usdt.toFixed(2)} ({tr.return_pct.toFixed(2)}%)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Saved Strategy Evaluation Registry (SQLite) */}
      <div className="qazan-card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{pt.btSavedStrategiesTitle}</h2>
          <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setOnlyPassedFilter(false)}
              className={`min-h-[32px] px-3 py-1 rounded text-xs font-semibold cursor-pointer ${
                !onlyPassedFilter
                  ? 'bg-[#D4AF37] text-[#06080D]'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              {pt.btAllRunsFilter}
            </button>
            <button
              type="button"
              onClick={() => setOnlyPassedFilter(true)}
              className={`min-h-[32px] px-3 py-1 rounded text-xs font-semibold cursor-pointer ${
                onlyPassedFilter
                  ? 'bg-[#D4AF37] text-[#06080D]'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              {pt.btOnlyPassedFilter}
            </button>
          </div>
        </div>

        {savedReports.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">{pt.engineNoRecords}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-start">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                  <th className="py-2.5 px-3 text-start">{pt.symbolCol}</th>
                  <th className="py-2.5 px-3 text-start">{pt.strategyLabel}</th>
                  <th className="py-2.5 px-3 text-end">{pt.winRate}</th>
                  <th className="py-2.5 px-3 text-end">PF</th>
                  <th className="py-2.5 px-3 text-end">OOS %</th>
                  <th className="py-2.5 px-3 text-end">{pt.engineStatusCol}</th>
                  <th className="py-2.5 px-3 text-end">{pt.actionCol}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {savedReports.map((rep) => (
                  <tr key={rep.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-2.5 px-3 font-mono font-semibold">
                      {rep.symbol} ({rep.primary_interval})
                    </td>
                    <td className="py-2.5 px-3 font-mono">{rep.strategy_name}</td>
                    <td className="py-2.5 px-3 text-end font-mono tabular-nums">{rep.win_rate_pct.toFixed(1)}%</td>
                    <td className="py-2.5 px-3 text-end font-mono tabular-nums">{rep.profit_factor.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-end font-mono tabular-nums">
                      {rep.walk_forward_oos_return_pct >= 0 ? '+' : ''}
                      {rep.walk_forward_oos_return_pct.toFixed(2)}%
                    </td>
                    <td
                      className={`py-2.5 px-3 text-end font-mono font-bold ${
                        rep.is_strategy_successful
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {rep.is_strategy_successful ? pt.btStatusPassed : pt.btStatusFailed}
                    </td>
                    <td className="py-2.5 px-3 text-end">
                      <button
                        type="button"
                        onClick={() => void handleDelete(rep.id)}
                        className="inline-flex items-center gap-1 min-h-[32px] px-2.5 rounded text-slate-500 hover:text-red-600 cursor-pointer"
                        title={pt.btDeleteReport}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
