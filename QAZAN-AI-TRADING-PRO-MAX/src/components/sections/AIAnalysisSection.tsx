import { useCallback, useEffect, useState } from 'react';
import { Cpu, RefreshCw, TrendingDown, TrendingUp } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { AIAnalysisResponse } from '@/types/platform';

function ProbabilityGauge({ probBullish, signalLabel }: { probBullish: number; signalLabel: string }) {
  const clamped = Math.min(100, Math.max(0, probBullish));
  // Semi-circle path length = pi * r (r = 76 -> ~238.76)
  const radius = 76;
  const arcLen = Math.PI * radius;
  const bullStroke = (clamped / 100) * arcLen;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 180 105" className="w-44 h-26 overflow-visible" aria-hidden="true">
        <path
          d="M 14 92 A 76 76 0 0 1 166 92"
          fill="none"
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          className="text-red-500/35"
        />
        <path
          d="M 14 92 A 76 76 0 0 1 166 92"
          fill="none"
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${bullStroke} ${arcLen}`}
          className="text-emerald-500 transition-all duration-500"
        />
        <text
          x="90"
          y="72"
          textAnchor="middle"
          className="fill-slate-900 dark:fill-slate-100 font-mono text-lg font-bold"
        >
          {clamped.toFixed(1)}%
        </text>
        <text
          x="90"
          y="91"
          textAnchor="middle"
          className="fill-[#9A7209] dark:fill-[#E5C76B] font-mono text-[11px] font-semibold"
        >
          {signalLabel}
        </text>
      </svg>
    </div>
  );
}

export function AIAnalysisSection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [data, setData] = useState<AIAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await platformClient.getAIAnalysis(activeSymbol, activeInterval);
      setData(res);
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
            {pt.sections['ai-analysis']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.aiSubtitle}</p>
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

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-44 qazan-card animate-pulse" />
          ))}
        </div>
      ) : data ? (
        <div className="space-y-4">
          {/* Primary Signal Gauge & Model Benchmarks */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="qazan-card-gold p-5 flex flex-col items-center justify-between gap-2">
              <div className="w-full flex items-center justify-between text-xs">
                <span className="text-slate-500 dark:text-slate-400">{pt.ensembleSignal}</span>
                <span
                  className={`inline-flex items-center gap-1 font-mono font-bold ${
                    data.signal === 'BULLISH'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {data.signal === 'BULLISH' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                  {data.signal === 'BULLISH' ? pt.bullish : pt.bearish}
                </span>
              </div>

              <ProbabilityGauge
                probBullish={data.prob_bullish}
                signalLabel={`${pt.confidence} ${data.confidence_pct.toFixed(1)}%`}
              />
            </div>

            <div className="qazan-card p-5 flex flex-col justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{pt.bullishProb}</span>
                  <span className="font-mono tabular-nums font-bold">{data.prob_bullish.toFixed(2)}%</span>
                </div>
                <div className="h-3 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex" dir="ltr">
                  <div className="bg-emerald-500 h-full" style={{ width: `${data.prob_bullish}%` }} />
                  <div className="bg-red-500 h-full" style={{ width: `${data.prob_bearish}%` }} />
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-red-600 dark:text-red-400 font-semibold">{pt.bearishProb}</span>
                  <span className="font-mono tabular-nums font-bold">{data.prob_bearish.toFixed(2)}%</span>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs font-mono">
                <span className="text-slate-500 dark:text-slate-400">{pt.sampleInfo}</span>
                <span className="tabular-nums font-semibold">
                  {data.train_size} train / {data.test_size} test
                </span>
              </div>
            </div>

            <div className="qazan-card p-5 space-y-3 text-xs">
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">{pt.rfAccuracy}</span>
                  <span className="font-mono tabular-nums font-semibold">{data.rf_test_accuracy_pct.toFixed(2)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                  <div className="h-full bg-sky-500 rounded-full" style={{ width: `${data.rf_test_accuracy_pct}%` }} />
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">{pt.xgbAccuracy}</span>
                  <span className="font-mono tabular-nums font-semibold">{data.xgb_test_accuracy_pct.toFixed(2)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                  <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${data.xgb_test_accuracy_pct}%` }} />
                </div>
              </div>

              <div className="space-y-1 pt-1">
                <div className="flex justify-between">
                  <span className="text-slate-700 dark:text-slate-200 font-semibold">{pt.ensembleAccuracy}</span>
                  <span className="font-mono tabular-nums font-bold text-[#9A7209] dark:text-[#E5C76B]">
                    {data.ensemble_test_accuracy_pct.toFixed(2)}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                  <div className="h-full bg-[#D4AF37] rounded-full" style={{ width: `${data.ensemble_test_accuracy_pct}%` }} />
                </div>
              </div>
            </div>
          </div>

          {/* Feature Importances & Technical Inputs */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="qazan-card p-5 space-y-3">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[#D4AF37]" />
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {pt.featureImportanceTitle}
                </h2>
              </div>
              <div className="space-y-2.5">
                {data.top_features.map((f) => (
                  <div key={f.feature} className="space-y-1">
                    <div className="flex justify-between text-xs font-mono">
                      <span className="text-slate-700 dark:text-slate-300">{f.feature}</span>
                      <span className="tabular-nums font-semibold text-[#9A7209] dark:text-[#E5C76B]">
                        {(f.importance * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                      <div
                        className="h-full bg-[#D4AF37] rounded-full"
                        style={{ width: `${Math.min(100, f.importance * 100 * 3.2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="qazan-card p-5 space-y-3 flex flex-col justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">
                  {pt.telemetryHeading}
                </h2>
                <dl className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                  <div className="py-2.5 flex justify-between">
                    <dt className="text-slate-500 dark:text-slate-400">RSI (14)</dt>
                    <dd className="font-mono tabular-nums font-semibold">{data.rsi_14.toFixed(2)}</dd>
                  </div>
                  <div className="py-2.5 flex justify-between">
                    <dt className="text-slate-500 dark:text-slate-400">MACD Histogram (%)</dt>
                    <dd
                      className={`font-mono tabular-nums font-semibold ${
                        data.macd_hist >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {data.macd_hist >= 0 ? '+' : ''}
                      {data.macd_hist.toFixed(4)}%
                    </dd>
                  </div>
                  <div className="py-2.5 flex justify-between">
                    <dt className="text-slate-500 dark:text-slate-400">ATR Volatility (%)</dt>
                    <dd className="font-mono tabular-nums font-semibold">{data.atr_pct.toFixed(3)}%</dd>
                  </div>
                </dl>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-slate-800">
                {pt.disclaimerMl}
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
