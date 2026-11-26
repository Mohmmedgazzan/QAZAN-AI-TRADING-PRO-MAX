import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { LiquidityAnalysisResponse } from '@/types/platform';

export function LiquidityAnalysisSection() {
  const { activeSymbol, activeInterval, pt } = useApp();
  const [data, setData] = useState<LiquidityAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await platformClient.getLiquidityAnalysis(activeSymbol, activeInterval));
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  useEffect(() => {
    void load();
  }, [load]);

  const maxTouches = data
    ? Math.max(
        1,
        ...data.buy_side_pools.map((p) => p.touches),
        ...data.sell_side_pools.map((p) => p.touches),
      )
    : 1;

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['liquidity-analysis']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.liquiditySubtitle}</p>
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

      {data && (
        <div className="space-y-4">
          <div className="qazan-card-gold p-4 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.pocLevel}</p>
              <p className="text-xl font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                ${data.poc_price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
            <div className="text-end">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.priceCol}</p>
              <p className="text-lg font-mono font-semibold tabular-nums">
                ${data.last_close.toLocaleString('en-US', { maximumFractionDigits: 4 })}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Liquidity Depth Ladder */}
            <div className="qazan-card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {pt.liquidityMapTitle}
              </h2>

              <div className="space-y-2">
                <p className="text-xs font-semibold text-red-600 dark:text-red-400">{pt.buySidePools}</p>
                {data.buy_side_pools.map((pool, i) => (
                  <div key={`bsl-${i}`} className="space-y-1 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="font-bold tabular-nums">${pool.price.toLocaleString('en-US', { maximumFractionDigits: 4 })}</span>
                      <span className="text-slate-500 dark:text-slate-400 tabular-nums">
                        {pool.touches} {pt.touchesLabel} · {pool.distance_pct >= 0 ? '+' : ''}{pool.distance_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                      <div
                        className="h-full bg-red-500/80 rounded-full"
                        style={{ width: `${(pool.touches / maxTouches) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="py-2 px-3 rounded-lg border border-[#D4AF37]/35 bg-[#D4AF37]/10 flex items-center justify-between text-xs font-mono">
                <span className="font-semibold text-[#9A7209] dark:text-[#E5C76B]">SPOT / POC</span>
                <span className="font-bold tabular-nums">
                  ${data.last_close.toLocaleString('en-US', { maximumFractionDigits: 4 })} · POC ${data.poc_price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                </span>
              </div>

              <div className="space-y-2">
                <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">{pt.sellSidePools}</p>
                {data.sell_side_pools.map((pool, i) => (
                  <div key={`ssl-${i}`} className="space-y-1 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="font-bold tabular-nums">${pool.price.toLocaleString('en-US', { maximumFractionDigits: 4 })}</span>
                      <span className="text-slate-500 dark:text-slate-400 tabular-nums">
                        {pool.touches} {pt.touchesLabel} · {pool.distance_pct >= 0 ? '+' : ''}{pool.distance_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                      <div
                        className="h-full bg-emerald-500/80 rounded-full"
                        style={{ width: `${(pool.touches / maxTouches) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Volume Profile */}
            <div className="qazan-card p-5 space-y-3">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{pt.volumeProfile}</h2>
              <div className="space-y-2">
                {[...data.volume_profile].reverse().map((node, idx) => (
                  <div key={idx} className="space-y-1 text-xs font-mono">
                    <div className="flex justify-between tabular-nums">
                      <span className={node.is_poc ? 'text-[#9A7209] dark:text-[#E5C76B] font-bold' : 'text-slate-600 dark:text-slate-400'}>
                        ${node.price_mid.toLocaleString('en-US', { maximumFractionDigits: 2 })} {node.is_poc ? '· POC' : ''}
                      </span>
                      <span className="tabular-nums">{node.share_pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                      <div
                        className={`h-full rounded-full ${node.is_poc ? 'bg-[#D4AF37]' : 'bg-sky-500/70'}`}
                        style={{ width: `${Math.min(100, node.share_pct * 3.2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Recent Sweeps */}
          <div className="qazan-card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
              {pt.recentSweeps}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-start">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                    <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                    <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                    <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                    <th className="py-2.5 px-4 text-end">Wick Extreme</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                  {[...data.recent_sweeps].reverse().map((sw, i) => (
                    <tr key={`${sw.time}-${i}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                      <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                        {new Date(sw.time * 1000).toISOString().slice(0, 16).replace('T', ' ')}
                      </td>
                      <td
                        className={`py-2.5 px-4 font-mono font-semibold ${
                          sw.side === 'SSL_SWEEP'
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {sw.side}
                      </td>
                      <td className="py-2.5 px-4 text-end font-mono tabular-nums">${sw.swept_level.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                      <td className="py-2.5 px-4 text-end font-mono tabular-nums">${sw.wick_extreme.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
