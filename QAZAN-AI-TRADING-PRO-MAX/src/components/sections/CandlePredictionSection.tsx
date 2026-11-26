import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { CandleProbabilityView } from '@/components/engine/CandleProbabilityView';
import { useApp } from '@/contexts/AppContext';
import type {
  CandlePredictionResponse,
  CandleProbabilityResponse,
  ProbabilityForecastHistoryItem,
} from '@/types/platform';

type PredictionSubtab = 'probability' | 'regression';

function CandleAnatomySvg({ data }: { data: CandlePredictionResponse }) {
  const high = Math.max(data.predicted_high, data.current_close, data.predicted_close);
  const low = Math.min(data.predicted_low, data.current_close, data.predicted_close);
  const span = Math.max(1e-8, high - low);

  const toY = (price: number) => 22 + ((high - price) / span) * 146;
  const yHigh = toY(data.predicted_high);
  const yLow = toY(data.predicted_low);
  const yOpen = toY(data.current_close);
  const yClose = toY(data.predicted_close);

  const bodyTop = Math.min(yOpen, yClose);
  const bodyHeight = Math.max(8, Math.abs(yClose - yOpen));
  const isBull = data.predicted_direction === 'BULLISH';

  return (
    <svg viewBox="0 0 320 190" className="w-full max-w-[340px] h-48 mx-auto" aria-hidden="true">
      {/* Horizontal Price Guides */}
      <line x1="24" y1={yHigh} x2="296" y2={yHigh} stroke="currentColor" strokeDasharray="3 3" className="text-emerald-500/40" />
      <line x1="24" y1={yLow} x2="296" y2={yLow} stroke="currentColor" strokeDasharray="3 3" className="text-red-500/40" />
      <line x1="24" y1={yOpen} x2="120" y2={yOpen} stroke="currentColor" strokeWidth="1" className="text-[#D4AF37]/70" />

      {/* Wick */}
      <line
        x1="150"
        y1={yHigh}
        x2="150"
        y2={yLow}
        strokeWidth="3"
        strokeLinecap="round"
        className={isBull ? 'stroke-emerald-500' : 'stroke-red-500'}
      />

      {/* Projected Body */}
      <rect
        x="128"
        y={bodyTop}
        width="44"
        height={bodyHeight}
        rx="4"
        className={isBull ? 'fill-emerald-500/85 stroke-emerald-400' : 'fill-red-500/85 stroke-red-400'}
        strokeWidth="1.5"
      />

      {/* Labels */}
      <text x="190" y={Math.max(16, yHigh + 4)} className="fill-emerald-500 font-mono text-[11px] font-semibold">
        H ${data.predicted_high.toLocaleString('en-US', { maximumFractionDigits: 2 })}
      </text>
      <text x="190" y={Math.min(182, yLow + 4)} className="fill-red-500 font-mono text-[11px] font-semibold">
        L ${data.predicted_low.toLocaleString('en-US', { maximumFractionDigits: 2 })}
      </text>
      <text x="190" y={yClose + 4} className="fill-[#9A7209] dark:fill-[#E5C76B] font-mono text-[11px] font-bold">
        C ${data.predicted_close.toLocaleString('en-US', { maximumFractionDigits: 2 })}
      </text>
    </svg>
  );
}

export function CandlePredictionSection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [subtab, setSubtab] = useState<PredictionSubtab>('probability');
  const [data, setData] = useState<CandlePredictionResponse | null>(null);
  const [probData, setProbData] = useState<CandleProbabilityResponse | null>(null);
  const [probHistory, setProbHistory] = useState<ProbabilityForecastHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [probRes, histRes, regRes] = await Promise.all([
        platformClient.getCandleProbabilities(activeSymbol, activeInterval, 360, true),
        platformClient.getCandleProbabilityHistory(8),
        platformClient.getCandlePrediction(activeSymbol, activeInterval),
      ]);
      setProbData(probRes);
      setProbHistory(histRes);
      setData(regRes);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['candle-prediction']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.candlePredSubtitle}</p>
        </div>

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

      {/* Segmented Subtabs: Walk-Forward Probability Engine vs Classic Regression Range */}
      <div className="flex flex-wrap items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800 w-full sm:w-fit">
        {(
          [
            { id: 'probability', label: pt.probTabProbabilistic },
            { id: 'regression', label: pt.probTabRegression },
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

      {subtab === 'probability' && (
        <CandleProbabilityView data={probData} history={probHistory} loading={loading} />
      )}

      {subtab === 'regression' && data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.currentClose}</p>
              <p className="mt-1.5 text-xl font-mono font-bold tabular-nums">
                ${data.current_close.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
            <div className="qazan-card-gold p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.predictedClose}</p>
              <p
                className={`mt-1.5 text-xl font-mono font-bold tabular-nums ${
                  data.predicted_direction === 'BULLISH'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                ${data.predicted_close.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.predictedHigh}</p>
              <p className="mt-1.5 text-xl font-mono font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                ${data.predicted_high.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.predictedLow}</p>
              <p className="mt-1.5 text-xl font-mono font-bold tabular-nums text-red-600 dark:text-red-400">
                ${data.predicted_low.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div className="lg:col-span-5 qazan-card p-5 space-y-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {pt.candleAnatomyTitle}
              </h2>
              <CandleAnatomySvg data={data} />
            </div>

            <div className="lg:col-span-7 qazan-card p-5 flex flex-col justify-between gap-4 text-xs font-mono">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="qazan-subpanel p-4">
                  <p className="text-slate-500 dark:text-slate-400">{pt.expectedMove}</p>
                  <p
                    className={`mt-1.5 text-xl font-bold tabular-nums ${
                      data.expected_move_pct >= 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {data.expected_move_pct >= 0 ? '+' : ''}
                    {data.expected_move_pct.toFixed(3)}%
                  </p>
                </div>
                <div className="qazan-subpanel p-4">
                  <p className="text-slate-500 dark:text-slate-400">{pt.valMae} (XGB)</p>
                  <p className="mt-1.5 text-xl font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                    {data.xgb_val_mae_pct.toFixed(3)}%
                  </p>
                </div>
                <div className="qazan-subpanel p-4">
                  <p className="text-slate-500 dark:text-slate-400">{pt.valRmse} (GBR)</p>
                  <p className="mt-1.5 text-xl font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                    {data.gbr_val_rmse_pct.toFixed(3)}%
                  </p>
                </div>
              </div>

              <p className="text-xs font-sans text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-slate-800">
                {pt.disclaimerMl} ({data.sample_size} bars)
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
