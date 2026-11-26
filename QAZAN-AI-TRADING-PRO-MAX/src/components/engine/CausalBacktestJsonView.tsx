import { useState } from 'react';
import { Check, Copy, Download, Play } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import type {
  CausalBacktestRequest,
  CausalBacktestResponse,
  MultiTimeframeAnalysisResponse,
  TechnicalRunHistoryItem,
} from '@/types/platform';

interface CausalBacktestJsonViewProps {
  symbol: string;
  multiTfData: MultiTimeframeAnalysisResponse | null;
  backtestData: CausalBacktestResponse | null;
  history: TechnicalRunHistoryItem[];
  running: boolean;
  onRunBacktest: (payload: CausalBacktestRequest) => void;
}

function fmtUtc(tsSec: number): string {
  return new Date(tsSec * 1000).toISOString().slice(0, 16).replace('T', ' ');
}

export function CausalBacktestJsonView({
  symbol,
  multiTfData,
  backtestData,
  history,
  running,
  onRunBacktest,
}: CausalBacktestJsonViewProps) {
  const { pt } = useApp();
  const [timeframe, setTimeframe] = useState<'4h' | '1d' | '1h'>('4h');
  const [lookbackBars, setLookbackBars] = useState(320);
  const [initialCapital, setInitialCapital] = useState(10000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [feePct, setFeePct] = useState(0.06);
  const [rrTarget, setRrTarget] = useState(2.0);
  const [jsonSource, setJsonSource] = useState<'analysis' | 'backtest'>('analysis');
  const [copied, setCopied] = useState(false);

  const activeJsonObject = jsonSource === 'analysis' ? multiTfData : backtestData;
  const formattedJson = activeJsonObject ? JSON.stringify(activeJsonObject, null, 2) : '{}';

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(formattedJson);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const handleDownloadJson = () => {
    const blob = new Blob([formattedJson], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `qazan_${symbol.toLowerCase()}_${jsonSource}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onRunBacktest({
      symbol,
      timeframe,
      lookback_bars: lookbackBars,
      initial_capital: initialCapital,
      risk_per_trade_pct: riskPct,
      fee_pct: feePct,
      rr_target: rrTarget,
    });
  };

  return (
    <div className="space-y-5">
      {/* Causal Backtest Runner Form */}
      <form onSubmit={handleSubmit} className="qazan-card p-4 sm:p-5 space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
          <div>
            <h2 className="text-sm sm:text-base font-semibold text-slate-900 dark:text-slate-100">
              {pt.engineBtTitle} · {symbol}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineLookaheadZero}</p>
          </div>
          <button type="submit" disabled={running} className="qazan-btn-gold">
            <Play className="w-4 h-4" />
            <span>{pt.engineBtRunBtn}</span>
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.timeframe}</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value as '4h' | '1d' | '1h')}
              className="qazan-input font-mono"
            >
              <option value="4h">4H</option>
              <option value="1d">1D</option>
              <option value="1h">1H</option>
            </select>
          </label>

          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.engineBtBars}</span>
            <input
              type="number"
              min={120}
              max={500}
              value={lookbackBars}
              onChange={(e) => setLookbackBars(Number(e.target.value) || 320)}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.initialCapital}</span>
            <input
              type="number"
              min={100}
              step={100}
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value) || 10000)}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.engineBtRiskPct}</span>
            <input
              type="number"
              min={0.2}
              max={10}
              step={0.1}
              value={riskPct}
              onChange={(e) => setRiskPct(Number(e.target.value) || 1.0)}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.feePct}</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={feePct}
              onChange={(e) => setFeePct(Number(e.target.value) || 0.06)}
              className="qazan-input font-mono tabular-nums"
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-slate-600 dark:text-slate-400 block">{pt.engineBtRrTarget}</span>
            <input
              type="number"
              min={1}
              max={6}
              step={0.25}
              value={rrTarget}
              onChange={(e) => setRrTarget(Number(e.target.value) || 2.0)}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
        </div>
      </form>

      {/* Backtest Results Strip */}
      {backtestData && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="qazan-card-gold p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.finalEquity}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums">
                ${backtestData.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
              <p
                className={`mt-1 text-xs font-mono tabular-nums font-semibold ${
                  backtestData.total_return_pct >= 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {backtestData.total_return_pct >= 0 ? '+' : ''}
                {backtestData.total_return_pct.toFixed(2)}%
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.winRate}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums">
                {backtestData.win_rate_pct.toFixed(2)}%
              </p>
              <p className="mt-1 text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.profitFactor}: {backtestData.profit_factor.toFixed(2)} · {backtestData.total_trades} trades
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.maxDrawdown}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums text-red-600 dark:text-red-400">
                -{backtestData.max_drawdown_pct.toFixed(2)}%
              </p>
              <p className="mt-1 text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.sharpeRatio}: {backtestData.sharpe_ratio.toFixed(2)}
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineBtBreakouts}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {backtestData.breakouts_confirmed}
              </p>
              <p className="mt-1 text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.engineBtFakeouts}: {backtestData.fakeouts_filtered} · {pt.engineBtStopHunts}:{' '}
                {backtestData.stop_hunts_detected}
              </p>
            </div>
          </div>

          {/* Backtest Trades Table */}
          <div className="qazan-card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                {pt.recentExecutions}
              </h3>
              <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {backtestData.bars_tested} bars
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-start">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                    <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                    <th className="py-2.5 px-4 text-start">{pt.engineBtSetupCol}</th>
                    <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                    <th className="py-2.5 px-4 text-end">{pt.entryPrice}</th>
                    <th className="py-2.5 px-4 text-end">{pt.engineBtExitReasonCol}</th>
                    <th className="py-2.5 px-4 text-end">PnL (USDT)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                  {backtestData.trades.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                        {pt.engineNoRecords}
                      </td>
                    </tr>
                  ) : (
                    [...backtestData.trades]
                      .reverse()
                      .slice(0, 15)
                      .map((tr, idx) => (
                        <tr key={`${tr.entry_time}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                          <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                            {fmtUtc(tr.entry_time)}
                          </td>
                          <td className="py-2.5 px-4 font-mono text-slate-700 dark:text-slate-300">
                            {tr.setup_type}
                          </td>
                          <td
                            className={`py-2.5 px-4 font-mono font-bold ${
                              tr.side === 'LONG'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {tr.side}
                          </td>
                          <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                            ${tr.entry_price.toFixed(2)} → ${tr.exit_price.toFixed(2)}
                          </td>
                          <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                            {tr.exit_reason}
                          </td>
                          <td
                            className={`py-2.5 px-4 text-end font-mono tabular-nums font-bold ${
                              tr.pnl_usdt >= 0
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {tr.pnl_usdt >= 0 ? '+' : ''}
                            {tr.pnl_usdt.toFixed(2)}
                          </td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* SQLite Run History */}
      <div className="qazan-card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
          {pt.engineRunHistoryTitle}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-start">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                <th className="py-2.5 px-4 text-start">ID</th>
                <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                <th className="py-2.5 px-4 text-start">{pt.engineBiasLabel}</th>
                <th className="py-2.5 px-4 text-start">{pt.enginePhaseLabel}</th>
                <th className="py-2.5 px-4 text-end">{pt.timeCol}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {history.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                    {pt.engineNoRecords}
                  </td>
                </tr>
              ) : (
                history.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500">#{item.id}</td>
                    <td className="py-2.5 px-4 font-mono font-semibold">{item.symbol}</td>
                    <td className="py-2.5 px-4 font-mono text-slate-700 dark:text-slate-300">
                      {item.run_type} ({item.ltf_interval})
                    </td>
                    <td
                      className={`py-2.5 px-4 font-mono font-bold ${
                        item.market_bias === 'BULLISH'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : item.market_bias === 'BEARISH'
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-[#9A7209] dark:text-[#E5C76B]'
                      }`}
                    >
                      {item.market_bias}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                      {item.market_phase} · {item.market_regime}
                    </td>
                    <td className="py-2.5 px-4 text-end font-mono tabular-nums text-slate-500" dir="ltr">
                      {item.created_at.slice(0, 19).replace('T', ' ')}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Structured JSON Viewer */}
      <div className="qazan-card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
              {pt.engineJsonTitle}
            </h3>
            <div className="inline-flex items-center p-1 rounded-lg bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setJsonSource('analysis')}
                className={`min-h-[34px] px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  jsonSource === 'analysis'
                    ? 'bg-[#D4AF37] text-[#06080D] font-semibold'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                {pt.engineJsonAnalysisOpt}
              </button>
              <button
                type="button"
                onClick={() => setJsonSource('backtest')}
                className={`min-h-[34px] px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  jsonSource === 'backtest'
                    ? 'bg-[#D4AF37] text-[#06080D] font-semibold'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                {pt.engineJsonBacktestOpt}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button type="button" onClick={() => void handleCopyJson()} className="qazan-btn-secondary">
              {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
              <span>{copied ? pt.engineCopiedJson : pt.engineCopyJson}</span>
            </button>
            <button type="button" onClick={handleDownloadJson} className="qazan-btn-secondary">
              <Download className="w-4 h-4" />
              <span>{pt.engineDownloadJson}</span>
            </button>
          </div>
        </div>

        <pre
          dir="ltr"
          className="p-4 max-h-[360px] overflow-auto text-xs font-mono leading-relaxed bg-slate-50 dark:bg-[#070A10] text-slate-800 dark:text-slate-200"
        >
          {formattedJson}
        </pre>
      </div>
    </div>
  );
}
