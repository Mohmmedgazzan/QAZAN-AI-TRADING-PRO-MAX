import { AlertTriangle } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import type { CandleProbabilityResponse, ProbabilityForecastHistoryItem } from '@/types/platform';

interface CandleProbabilityViewProps {
  data: CandleProbabilityResponse | null;
  history: ProbabilityForecastHistoryItem[];
  loading: boolean;
}

function fmtPrice(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: value < 10 ? 4 : 2,
    maximumFractionDigits: value < 10 ? 4 : 2,
  });
}

function effectToneClass(effect: string): string {
  if (effect === 'UP' || effect === 'BULLISH') {
    return 'text-emerald-600 dark:text-emerald-400';
  }
  if (effect === 'DOWN' || effect === 'BEARISH') {
    return 'text-red-600 dark:text-red-400';
  }
  return 'text-[#9A7209] dark:text-[#E5C76B]';
}

export function CandleProbabilityView({ data, history, loading }: CandleProbabilityViewProps) {
  const { pt } = useApp();

  if (loading && !data) {
    return (
      <div className="qazan-card p-6 text-xs font-mono text-slate-500 dark:text-slate-400">
        {pt.loading}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  // Strict insufficient-data guard: never show fabricated probabilities
  if (data.status === 'INSUFFICIENT_DATA' || !data.probabilities || !data.estimated_range || !data.walk_forward_metrics) {
    return (
      <div className="qazan-card p-6 space-y-3">
        <div className="flex items-center gap-2.5 text-[#9A7209] dark:text-[#E5C76B]">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <h2 className="text-base font-semibold">{pt.probInsufficientTitle}</h2>
        </div>
        <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
          {data.insufficient_reason ?? pt.probInsufficientTitle}
        </p>
        <p className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
          {data.closed_bars_analyzed} / {data.minimum_required_bars} {pt.probSampleBarsLabel}
        </p>
      </div>
    );
  }

  const probs = data.probabilities;
  const rng = data.estimated_range;
  const wf = data.walk_forward_metrics;
  const snap = data.feature_snapshot;

  return (
    <div className="space-y-5">
      {/* Non-Guarantee Scientific Notice */}
      <div className="qazan-subpanel p-3.5 text-xs text-slate-700 dark:text-slate-300 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <span>{pt.probDisclaimerBanner}</span>
        <span className="font-mono tabular-nums text-slate-500 dark:text-slate-400 whitespace-nowrap shrink-0">
          {data.closed_bars_analyzed} {pt.probSampleBarsLabel} · {wf.folds} Folds
        </span>
      </div>

      {/* 3-State Probability Distribution Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="qazan-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>{pt.probUpLabel}</span>
            <span className="font-mono">UP</span>
          </div>
          <p className="text-2xl font-mono font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
            {probs.up_pct.toFixed(2)}%
          </p>
          <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div className="h-full bg-emerald-500" style={{ width: `${Math.min(100, probs.up_pct)}%` }} />
          </div>
        </div>

        <div className="qazan-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>{pt.probSidewaysLabel}</span>
            <span className="font-mono">SIDEWAYS</span>
          </div>
          <p className="text-2xl font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
            {probs.sideways_pct.toFixed(2)}%
          </p>
          <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div className="h-full bg-[#D4AF37]" style={{ width: `${Math.min(100, probs.sideways_pct)}%` }} />
          </div>
        </div>

        <div className="qazan-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>{pt.probDownLabel}</span>
            <span className="font-mono">DOWN</span>
          </div>
          <p className="text-2xl font-mono font-bold tabular-nums text-red-600 dark:text-red-400">
            {probs.down_pct.toFixed(2)}%
          </p>
          <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div className="h-full bg-red-500" style={{ width: `${Math.min(100, probs.down_pct)}%` }} />
          </div>
        </div>
      </div>

      {/* Estimated Price Range Envelope & Confidence Calibration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="qazan-card-gold p-4 sm:p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{pt.probRangeTitle}</h2>
            <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
              ±{rng.estimated_range_width_pct.toFixed(2)}% span
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs font-mono tabular-nums">
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400 font-sans">Lower Envelope (Q15)</p>
              <p className="mt-1 text-base font-bold text-red-600 dark:text-red-400">
                ${fmtPrice(rng.lower_bound)}
              </p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400 font-sans">Upper Envelope (Q85)</p>
              <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">
                ${fmtPrice(rng.upper_bound)}
              </p>
            </div>
          </div>

          <div className="space-y-1.5 text-xs font-mono tabular-nums pt-1">
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400 font-sans">{pt.currentClose}</span>
              <span className="font-semibold">${fmtPrice(rng.reference_close)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400 font-sans">
                Sideways Threshold (±{rng.sideways_threshold_pct.toFixed(3)}%)
              </span>
              <span className="text-[#9A7209] dark:text-[#E5C76B]">
                ${fmtPrice(rng.central_band_low)} – ${fmtPrice(rng.central_band_high)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400 font-sans">{pt.atrLabel}</span>
              <span>${fmtPrice(rng.atr_14)}</span>
            </div>
          </div>
        </div>

        {/* Walk-Forward Brier Score & Log Loss vs Baseline */}
        <div className="qazan-card p-4 sm:p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-2.5">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{pt.probCalibrationTitle}</h2>
            <span className="text-xs font-mono tabular-nums font-bold text-[#9A7209] dark:text-[#E5C76B]">
              {pt.confidence}: {data.confidence_pct?.toFixed(1)}% ({data.confidence_level})
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-start">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                  <th className="py-2 px-3 text-start">Metric</th>
                  <th className="py-2 px-3 text-end">Ensemble Model</th>
                  <th className="py-2 px-3 text-end">Causal Baseline</th>
                  <th className="py-2 px-3 text-end">{pt.probVsBaseline}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 font-mono tabular-nums">
                <tr>
                  <td className="py-2.5 px-3 font-sans font-medium">Brier Score</td>
                  <td className="py-2.5 px-3 text-end font-bold">{wf.model_brier_score.toFixed(4)}</td>
                  <td className="py-2.5 px-3 text-end text-slate-500">{wf.baseline_brier_score.toFixed(4)}</td>
                  <td
                    className={`py-2.5 px-3 text-end font-bold ${
                      wf.brier_skill_vs_baseline_pct >= 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {wf.brier_skill_vs_baseline_pct >= 0 ? '+' : ''}
                    {wf.brier_skill_vs_baseline_pct.toFixed(2)}%
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-sans font-medium">Log Loss</td>
                  <td className="py-2.5 px-3 text-end font-bold">{wf.model_log_loss.toFixed(4)}</td>
                  <td className="py-2.5 px-3 text-end text-slate-500">{wf.baseline_log_loss.toFixed(4)}</td>
                  <td
                    className={`py-2.5 px-3 text-end font-bold ${
                      wf.log_loss_skill_vs_baseline_pct >= 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {wf.log_loss_skill_vs_baseline_pct >= 0 ? '+' : ''}
                    {wf.log_loss_skill_vs_baseline_pct.toFixed(2)}%
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-sans font-medium">OOS Accuracy</td>
                  <td className="py-2.5 px-3 text-end font-bold">{wf.model_accuracy_pct.toFixed(2)}%</td>
                  <td className="py-2.5 px-3 text-end text-slate-500">{wf.baseline_accuracy_pct.toFixed(2)}%</td>
                  <td className="py-2.5 px-3 text-end text-slate-500">
                    {wf.evaluated_bars} bars ({wf.folds} folds)
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 9-Domain Closed-Bar Context Snapshot */}
      {snap && (
        <div className="qazan-card p-4 sm:p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{pt.probContextTitle}</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 text-xs font-mono tabular-nums">
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">OHLCV / Close</p>
              <p className="mt-1 font-bold">${fmtPrice(snap.close)}</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">RSI(14)</p>
              <p className="mt-1 font-bold">{snap.rsi_14.toFixed(2)}</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">ATR(14)</p>
              <p className="mt-1 font-bold">{snap.atr_pct.toFixed(3)}%</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">Volume Ratio</p>
              <p className="mt-1 font-bold">{snap.volume_ratio_20.toFixed(2)}x</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">VWAP Dist</p>
              <p className="mt-1 font-bold">
                ${fmtPrice(snap.vwap)} ({snap.vwap_distance_atr >= 0 ? '+' : ''}
                {snap.vwap_distance_atr.toFixed(2)} ATR)
              </p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">Market Structure</p>
              <p className={`mt-1 font-bold ${effectToneClass(snap.structure_bias)}`}>{snap.structure_bias}</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">Liquidity</p>
              <p className="mt-1 font-bold text-slate-800 dark:text-slate-200 truncate">{snap.liquidity_bias}</p>
            </div>
            <div className="qazan-subpanel p-3">
              <p className="text-slate-500 dark:text-slate-400">FVG</p>
              <p className="mt-1 font-bold text-slate-800 dark:text-slate-200 truncate">{snap.fvg_context}</p>
            </div>
            <div className="qazan-subpanel p-3 col-span-2 sm:col-span-1">
              <p className="text-slate-500 dark:text-slate-400">Trend</p>
              <p className="mt-1 font-bold text-[#9A7209] dark:text-[#E5C76B] truncate">{snap.trend_regime}</p>
            </div>
          </div>
        </div>
      )}

      {/* Driving Factors Attribution Table */}
      <div className="qazan-card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
          {pt.probFactorsTitle}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-start">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                <th className="py-2.5 px-4 text-start">{pt.probDomainCol}</th>
                <th className="py-2.5 px-4 text-start">{pt.probFeatureCol}</th>
                <th className="py-2.5 px-4 text-end">{pt.probValueCol}</th>
                <th className="py-2.5 px-4 text-start">{pt.probEffectCol}</th>
                <th className="py-2.5 px-4 text-end">{pt.probWeightCol}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {data.driving_factors.map((f) => (
                <tr key={f.feature} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                  <td className="py-2.5 px-4 font-mono font-semibold text-slate-700 dark:text-slate-300">
                    {f.domain}
                  </td>
                  <td className="py-2.5 px-4">
                    <p className="font-mono font-medium">{f.feature}</p>
                    <p className="text-slate-500 dark:text-slate-400">{f.explanation}</p>
                  </td>
                  <td className="py-2.5 px-4 text-end font-mono tabular-nums">{f.current_value.toFixed(4)}</td>
                  <td className={`py-2.5 px-4 font-mono font-bold ${effectToneClass(f.direction_effect)}`}>
                    {f.direction_effect}
                  </td>
                  <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                    {f.weight_pct.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Saved Forecast History in SQLite */}
      {history.length > 0 && (
        <div className="qazan-card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
            {pt.probHistoryTitle}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-start">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                  <th className="py-2.5 px-4 text-start">ID</th>
                  <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                  <th className="py-2.5 px-4 text-end">UP / SIDEWAYS / DOWN</th>
                  <th className="py-2.5 px-4 text-end">Brier (Model / Base)</th>
                  <th className="py-2.5 px-4 text-end">LogLoss (Model / Base)</th>
                  <th className="py-2.5 px-4 text-end">{pt.timeCol}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 font-mono tabular-nums">
                {history.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-2.5 px-4 text-slate-500">#{h.id}</td>
                    <td className="py-2.5 px-4 font-semibold">
                      {h.symbol} ({h.interval})
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      {h.prob_up != null ? `${h.prob_up.toFixed(1)}% / ${h.prob_sideways?.toFixed(1)}% / ${h.prob_down?.toFixed(1)}%` : h.status}
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      {h.model_brier_score != null ? `${h.model_brier_score.toFixed(4)} / ${h.baseline_brier_score?.toFixed(4)}` : '—'}
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      {h.model_log_loss != null ? `${h.model_log_loss.toFixed(4)} / ${h.baseline_log_loss?.toFixed(4)}` : '—'}
                    </td>
                    <td className="py-2.5 px-4 text-end text-slate-500" dir="ltr">
                      {h.created_at.slice(0, 19).replace('T', ' ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
