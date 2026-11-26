import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { SMCAnalysisResponse } from '@/types/platform';

export function SmartMoneySection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [data, setData] = useState<SMCAnalysisResponse | null>(null);
  const [activeOnly, setActiveOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await platformClient.getSMCAnalysis(activeSymbol, activeInterval));
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  useEffect(() => {
    void load();
  }, [load]);

  const fvgs = (data ? [...data.fair_value_gaps].reverse() : []).filter((item) =>
    activeOnly ? !item.mitigated : true,
  );
  const obs = (data ? [...data.order_blocks].reverse() : []).filter((item) =>
    activeOnly ? !item.mitigated : true,
  );

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['smart-money']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.smcSubtitle}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveOnly((v) => !v)}
            className={`min-h-[44px] px-3.5 rounded-lg border text-xs font-semibold cursor-pointer transition-colors ${
              activeOnly
                ? 'border-[#D4AF37]/60 bg-[#D4AF37]/15 text-[#9A7209] dark:text-[#E5C76B]'
                : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] text-slate-600 dark:text-slate-300'
            }`}
          >
            {pt.activeOnlyToggle}
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

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {/* Premium / Discount Dealing Range */}
          <div className="qazan-card-gold p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {pt.dealingRangeTitle}
              </h2>
              <span className="font-mono text-xs font-bold text-[#9A7209] dark:text-[#E5C76B]">
                {pt.currentZone}: {data.dealing_range.current_zone} ({data.dealing_range.position_pct.toFixed(1)}%)
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs font-mono">
              <div>
                <p className="text-slate-500 dark:text-slate-400">{pt.rangeLow}</p>
                <p className="mt-1 font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                  ${data.dealing_range.range_low.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                </p>
              </div>
              <div className="text-center">
                <p className="text-slate-500 dark:text-slate-400">{pt.equilibrium}</p>
                <p className="mt-1 font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                  ${data.dealing_range.equilibrium.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                </p>
              </div>
              <div className="text-end">
                <p className="text-slate-500 dark:text-slate-400">{pt.rangeHigh}</p>
                <p className="mt-1 font-bold tabular-nums text-red-600 dark:text-red-400">
                  ${data.dealing_range.range_high.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                </p>
              </div>
            </div>

            <div className="relative pt-1" dir="ltr">
              <div className="h-3.5 rounded-full bg-gradient-to-r from-emerald-500/35 via-[#D4AF37]/35 to-red-500/35 relative overflow-hidden">
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[#D4AF37]" />
                <div
                  className="w-3 h-3.5 bg-[#D4AF37] rounded-full absolute top-0 shadow-sm"
                  style={{ left: `calc(${Math.min(97, Math.max(3, data.dealing_range.position_pct))}% - 6px)` }}
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Fair Value Gaps */}
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center justify-between">
                <span>{pt.fvgTitle}</span>
                <span className="font-mono text-xs text-slate-500 tabular-nums">{fvgs.length}</span>
              </div>
              <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                {fvgs.map((fvg, i) => (
                  <div key={i} className="p-3.5 flex items-center justify-between gap-2 font-mono hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <div>
                      <span
                        className={`font-bold ${
                          fvg.direction === 'BULLISH'
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {fvg.direction} FVG
                      </span>
                      <p className="text-slate-500 tabular-nums mt-0.5" dir="ltr">
                        {new Date(fvg.time * 1000).toISOString().slice(0, 16).replace('T', ' ')}
                      </p>
                    </div>
                    <div className="text-end tabular-nums">
                      <p className="font-semibold">
                        ${fvg.bottom.toLocaleString('en-US', { maximumFractionDigits: 4 })} – $
                        {fvg.top.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                      </p>
                      <p className={fvg.mitigated ? 'text-slate-500' : 'text-[#9A7209] dark:text-[#E5C76B] font-semibold'}>
                        {fvg.mitigated ? pt.mitigated : pt.unmitigated}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Order Blocks */}
            <div className="qazan-card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center justify-between">
                <span>{pt.obTitle}</span>
                <span className="font-mono text-xs text-slate-500 tabular-nums">{obs.length}</span>
              </div>
              <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                {obs.map((ob, i) => (
                  <div key={i} className="p-3.5 flex items-center justify-between gap-2 font-mono hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <div>
                      <span
                        className={`font-bold ${
                          ob.direction === 'BULLISH'
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {ob.direction} OB
                      </span>
                      <p className="text-slate-500 tabular-nums mt-0.5" dir="ltr">
                        {new Date(ob.time * 1000).toISOString().slice(0, 16).replace('T', ' ')}
                      </p>
                    </div>
                    <div className="text-end tabular-nums">
                      <p className="font-semibold">
                        ${ob.low.toLocaleString('en-US', { maximumFractionDigits: 4 })} – $
                        {ob.high.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                      </p>
                      <p className={ob.mitigated ? 'text-slate-500' : 'text-[#9A7209] dark:text-[#E5C76B] font-semibold'}>
                        {ob.mitigated ? pt.mitigated : pt.unmitigated}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
