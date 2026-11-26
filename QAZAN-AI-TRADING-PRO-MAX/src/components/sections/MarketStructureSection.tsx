import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiClientError, apiClient } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { CausalBacktestJsonView } from '@/components/engine/CausalBacktestJsonView';
import { MultiTfEngineView } from '@/components/engine/MultiTfEngineView';
import { TradingChart } from '@/components/TradingChart';
import { useApp } from '@/contexts/AppContext';
import type { MarketKlinesResponse } from '@/types/api';
import type {
  CausalBacktestRequest,
  CausalBacktestResponse,
  MarketStructureResponse,
  MultiTimeframeAnalysisResponse,
  TechnicalRunHistoryItem,
} from '@/types/platform';

type StructureSubtab = 'single-tf' | 'multi-tf' | 'backtest-json';

export function MarketStructureSection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [subtab, setSubtab] = useState<StructureSubtab>('single-tf');
  const [data, setData] = useState<MarketStructureResponse | null>(null);
  const [klines, setKlines] = useState<MarketKlinesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Multi-TF Engine & Causal Backtest state
  const [engineLtf, setEngineLtf] = useState<'1h' | '15m'>('1h');
  const [multiTfData, setMultiTfData] = useState<MultiTimeframeAnalysisResponse | null>(null);
  const [engineLoading, setEngineLoading] = useState(false);
  const [backtestData, setBacktestData] = useState<CausalBacktestResponse | null>(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [runHistory, setRunHistory] = useState<TechnicalRunHistoryItem[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sRes, kRes] = await Promise.all([
        platformClient.getMarketStructure(activeSymbol, activeInterval),
        apiClient.getMarketKlines(activeSymbol, activeInterval, 120),
      ]);
      setData(sRes);
      setKlines(kRes);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  const loadEngine = useCallback(
    async (ltfOverride?: '1h' | '15m') => {
      const targetLtf = ltfOverride ?? engineLtf;
      setEngineLoading(true);
      setError(null);
      try {
        const [mtfRes, histRes] = await Promise.all([
          platformClient.getMultiTfEngineAnalysis(activeSymbol, targetLtf, true),
          platformClient.getEngineRunHistory(10),
        ]);
        setMultiTfData(mtfRes);
        setRunHistory(histRes);
      } catch (err) {
        setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
      } finally {
        setEngineLoading(false);
      }
    },
    [activeSymbol, engineLtf],
  );

  const handleRunBacktest = useCallback(async (payload: CausalBacktestRequest) => {
    setBacktestRunning(true);
    setError(null);
    try {
      const btRes = await platformClient.runCausalEngineBacktest(payload);
      setBacktestData(btRes);
      const histRes = await platformClient.getEngineRunHistory(10);
      setRunHistory(histRes);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBacktestRunning(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (subtab !== 'single-tf' && (!multiTfData || multiTfData.symbol !== activeSymbol)) {
      void loadEngine();
    }
  }, [subtab, activeSymbol, multiTfData, loadEngine]);

  const handleChangeLtf = (nextLtf: '1h' | '15m') => {
    setEngineLtf(nextLtf);
    void loadEngine(nextLtf);
  };

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['market-structure']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.structureSubtitle}</p>
        </div>

        <button
          type="button"
          onClick={() => (subtab === 'single-tf' ? void load() : void loadEngine())}
          disabled={loading || engineLoading}
          className="qazan-btn-gold"
        >
          <RefreshCw className={`w-4 h-4 ${loading || engineLoading ? 'animate-spin' : ''}`} />
          <span>{pt.refresh}</span>
        </button>
      </div>

      {/* Segmented Workbench Subtabs */}
      <div className="flex flex-wrap items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800 w-full sm:w-fit">
        {(
          [
            { id: 'single-tf', label: pt.engineTabSingle },
            { id: 'multi-tf', label: pt.engineTabMultiTf },
            { id: 'backtest-json', label: pt.engineTabBacktestJson },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSubtab(tab.id)}
            className={`min-h-[40px] px-3.5 py-2 text-xs font-semibold rounded-lg transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              subtab === tab.id
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {subtab === 'single-tf' && data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="qazan-card-gold p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.structureRegime}</p>
              <p
                className={`mt-1 text-lg font-mono font-bold ${
                  data.regime === 'UPTREND'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : data.regime === 'DOWNTREND'
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-[#9A7209] dark:text-[#E5C76B]'
                }`}
              >
                {data.regime}
              </p>
            </div>
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.atrLabel}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums">${data.atr_14.toFixed(4)}</p>
            </div>
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.rsiLabel}</p>
              <p className="mt-1 text-lg font-mono font-bold tabular-nums">{data.rsi_14.toFixed(2)}</p>
            </div>
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">EMA 20 / EMA 50</p>
              <p className="mt-1 text-sm font-mono font-semibold tabular-nums">
                {data.ema_20_last.toFixed(2)} / {data.ema_50_last.toFixed(2)}
              </p>
            </div>
          </div>

          {klines && (
            <TradingChart
              candles={klines.candles}
              ema20={data.ema_20_series}
              ema50={data.ema_50_series}
              swings={data.swings}
              events={data.events}
              showEma20
              showEma50
              showStructure
              heightClass="h-[290px] sm:h-[360px]"
            />
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Swings */}
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                {pt.recentSwings}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                      <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                      <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {[...data.swings].reverse().map((s, idx) => (
                      <tr key={`${s.time}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                          {new Date(s.time * 1000).toISOString().slice(0, 16).replace('T', ' ')}
                        </td>
                        <td
                          className={`py-2.5 px-4 font-mono font-bold ${
                            s.label === 'HH' || s.label === 'HL'
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {s.label} ({s.kind})
                        </td>
                        <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                          ${s.price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* BOS / CHoCH */}
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                {pt.bosChochEvents}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-start">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                      <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                      <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                      <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                      <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {[...data.events].reverse().map((ev, idx) => (
                      <tr key={`${ev.time}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                        <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                          {new Date(ev.time * 1000).toISOString().slice(0, 16).replace('T', ' ')}
                        </td>
                        <td className="py-2.5 px-4 font-mono font-bold text-[#9A7209] dark:text-[#E5C76B]">
                          {ev.event_type}
                        </td>
                        <td
                          className={`py-2.5 px-4 font-mono font-semibold ${
                            ev.direction === 'BULLISH'
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {ev.direction === 'BULLISH' ? pt.bullish : pt.bearish}
                        </td>
                        <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                          ${ev.price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {subtab === 'multi-tf' && (
        <MultiTfEngineView
          data={multiTfData}
          loading={engineLoading}
          ltf={engineLtf}
          onChangeLtf={handleChangeLtf}
          onRefresh={() => void loadEngine()}
        />
      )}

      {subtab === 'backtest-json' && (
        <CausalBacktestJsonView
          symbol={activeSymbol}
          multiTfData={multiTfData}
          backtestData={backtestData}
          history={runHistory}
          running={backtestRunning}
          onRunBacktest={(payload) => void handleRunBacktest(payload)}
        />
      )}
    </section>
  );
}
