import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import type { MultiTimeframeAnalysisResponse, SingleTimeframeAnalysis } from '@/types/platform';

interface MultiTfEngineViewProps {
  data: MultiTimeframeAnalysisResponse | null;
  loading: boolean;
  ltf: '1h' | '15m';
  onChangeLtf: (nextLtf: '1h' | '15m') => void;
  onRefresh: () => void;
}

function fmtPrice(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: value < 10 ? 4 : 2,
    maximumFractionDigits: value < 10 ? 4 : 2,
  });
}

function fmtUtc(tsSec: number): string {
  return new Date(tsSec * 1000).toISOString().slice(0, 16).replace('T', ' ');
}

function biasToneClass(bias: string): string {
  if (bias === 'BULLISH' || bias === 'CONFIRMED_LONG' || bias === 'DISCOUNT') {
    return 'text-emerald-600 dark:text-emerald-400';
  }
  if (bias === 'BEARISH' || bias === 'CONFIRMED_SHORT' || bias === 'PREMIUM') {
    return 'text-red-600 dark:text-red-400';
  }
  return 'text-[#9A7209] dark:text-[#E5C76B]';
}

export function MultiTfEngineView({
  data,
  loading,
  ltf,
  onChangeLtf,
  onRefresh,
}: MultiTfEngineViewProps) {
  const { pt } = useApp();
  const [selectedTf, setSelectedTf] = useState<string>('4H');

  const availableTfs = data ? ['1W', '1D', '4H', data.ltf_timeframe] : ['1W', '1D', '4H', ltf.toUpperCase()];
  const activeTfKey = availableTfs.includes(selectedTf) ? selectedTf : '4H';
  const tfData: SingleTimeframeAnalysis | undefined = data?.timeframes?.[activeTfKey];

  return (
    <div className="space-y-5">
      {/* Toolbar: LTF Selector + Zero Look-ahead Guarantee + Refresh */}
      <div className="qazan-card p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-400">
          <span className="font-semibold text-slate-900 dark:text-slate-100">
            {pt.engineLookaheadZero}
          </span>
          {data?.run_id != null && (
            <>
              <span aria-hidden="true">·</span>
              <span className="font-mono tabular-nums">Run #{data.run_id}</span>
            </>
          )}
          {tfData && (
            <>
              <span aria-hidden="true">·</span>
              <span className="font-mono tabular-nums">
                {tfData.unclosed_bar_excluded ? pt.engineUnclosedExcluded : `${tfData.closed_bars_analyzed} bars`}
              </span>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">{pt.engineLtfLabel}:</span>
          <div className="inline-flex items-center p-1 rounded-lg bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
            {(['1h', '15m'] as const).map((tfOpt) => (
              <button
                key={tfOpt}
                type="button"
                onClick={() => onChangeLtf(tfOpt)}
                className={`min-h-[36px] px-3 py-1.5 text-xs font-mono font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  ltf === tfOpt
                    ? 'bg-[#D4AF37] text-[#06080D]'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                }`}
              >
                {tfOpt.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="qazan-btn-gold"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{pt.engineRunBtn}</span>
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="qazan-card p-6 text-xs font-mono text-slate-500 dark:text-slate-400">
          {pt.loading}
        </div>
      )}

      {data && (
        <>
          {/* Global HTF Summary Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="qazan-card-gold p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineBiasLabel}</p>
              <p className={`mt-1 text-lg font-mono font-bold ${biasToneClass(data.market_bias)}`}>
                {data.market_bias}
              </p>
              <p className="mt-1 text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.engineAlignmentLabel}: {data.htf_alignment_score.toFixed(1)}%
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineRegimeLabel}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold text-slate-900 dark:text-slate-100 truncate">
                {data.market_regime}
              </p>
              <p className="mt-1 text-xs font-mono text-slate-500 dark:text-slate-400">
                {pt.enginePhaseLabel}: {data.market_phase}
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineLtfSetupTitle}</p>
              <p
                className={`mt-1 text-sm sm:text-base font-mono font-bold ${biasToneClass(
                  data.ltf_confirmation.setup_status,
                )}`}
              >
                {data.ltf_confirmation.setup_status}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 font-mono">
                {data.ltf_confirmation.timeframe}
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.engineInHtfPoi}</p>
              <p className="mt-1 text-sm sm:text-base font-mono font-bold text-slate-900 dark:text-slate-100">
                {data.ltf_confirmation.price_in_htf_poi ? pt.engineYes : pt.engineNo}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 truncate font-mono">
                {data.ltf_confirmation.matched_poi_description ?? '—'}
              </p>
            </div>
          </div>

          {/* Deterministic LTF Confirmation Checklist */}
          <div className="qazan-card p-4 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-2.5">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {pt.engineLtfSetupTitle}
              </h2>
              <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                <span>
                  {pt.engineLtfAligned}: {data.ltf_confirmation.ltf_structure_aligned ? pt.engineYes : pt.engineNo}
                </span>
                <span aria-hidden="true">·</span>
                <span>
                  {pt.engineLtfSweep}: {data.ltf_confirmation.ltf_sweep_detected ? pt.engineYes : pt.engineNo}
                </span>
              </div>
            </div>
            <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
              {data.ltf_confirmation.rationale}
            </p>
          </div>

          {/* Timeframe Selector Tabs (1W, 1D, 4H, LTF) */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              {pt.engineTfSelector}
            </span>
            <div className="flex flex-wrap items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
              {availableTfs.map((tfKey) => {
                const tfSnap = data.timeframes[tfKey];
                return (
                  <button
                    key={tfKey}
                    type="button"
                    onClick={() => setSelectedTf(tfKey)}
                    className={`min-h-[40px] px-3.5 py-1.5 text-xs font-mono font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                      activeTfKey === tfKey
                        ? 'bg-[#D4AF37] text-[#06080D]'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                    }`}
                  >
                    {tfKey}
                    {tfSnap ? ` · ${tfSnap.market_bias}` : ''}
                  </button>
                );
              })}
            </div>
          </div>

          {tfData && (
            <div className="space-y-5">
              {/* Timeframe Telemetry + Premium / Discount + Pending Breakout */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="qazan-card p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {tfData.timeframe} · {tfData.market_bias} / {tfData.market_phase}
                    </h3>
                    <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400" dir="ltr">
                      {fmtUtc(tfData.last_closed_time)}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                    <div className="qazan-subpanel p-3">
                      <p className="text-slate-500 dark:text-slate-400">{pt.currentClose}</p>
                      <p className="mt-1 font-mono font-bold tabular-nums">${fmtPrice(tfData.last_close)}</p>
                    </div>
                    <div className="qazan-subpanel p-3">
                      <p className="text-slate-500 dark:text-slate-400">{pt.atrLabel}</p>
                      <p className="mt-1 font-mono font-bold tabular-nums">${fmtPrice(tfData.atr_14)}</p>
                    </div>
                    <div className="qazan-subpanel p-3">
                      <p className="text-slate-500 dark:text-slate-400">ADX(14) / RSI(14)</p>
                      <p className="mt-1 font-mono font-bold tabular-nums">
                        {tfData.adx_14.toFixed(1)} / {tfData.rsi_14.toFixed(1)}
                      </p>
                    </div>
                  </div>

                  {tfData.pending_breakout && (
                    <div className="qazan-subpanel p-3 border-amber-500/40 dark:border-[#D4AF37]/40 text-xs space-y-1">
                      <p className="font-semibold text-[#9A7209] dark:text-[#E5C76B]">
                        {pt.enginePendingBreakout}
                      </p>
                      <p className="font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {tfData.pending_breakout.side} @ ${fmtPrice(tfData.pending_breakout.level_price)} · Close $
                        {fmtPrice(tfData.pending_breakout.breach_close)} ({tfData.pending_breakout.bars_waited} bars)
                      </p>
                    </div>
                  )}
                </div>

                {/* Premium / Discount & OTE Range */}
                <div className="qazan-card p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {pt.enginePremDiscTitle}
                    </h3>
                    <span className={`text-xs font-mono font-bold ${biasToneClass(tfData.premium_discount.zone)}`}>
                      {tfData.premium_discount.zone} ({tfData.premium_discount.position_pct.toFixed(1)}%)
                    </span>
                  </div>

                  <div className="space-y-2 text-xs font-mono tabular-nums">
                    <div className="flex justify-between">
                      <span className="text-slate-500 dark:text-slate-400">{pt.rangeHigh}</span>
                      <span className="text-red-600 dark:text-red-400 font-semibold">
                        ${fmtPrice(tfData.premium_discount.range_high)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500 dark:text-slate-400">{pt.equilibrium}</span>
                      <span className="text-[#9A7209] dark:text-[#E5C76B] font-semibold">
                        ${fmtPrice(tfData.premium_discount.equilibrium)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500 dark:text-slate-400">{pt.engineOteZone}</span>
                      <span className="text-slate-800 dark:text-slate-200">
                        ${fmtPrice(tfData.premium_discount.ote_low)} – ${fmtPrice(tfData.premium_discount.ote_high)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500 dark:text-slate-400">{pt.rangeLow}</span>
                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                        ${fmtPrice(tfData.premium_discount.range_low)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Breakout vs Fakeout vs Stop Hunt + Causal BOS/CHoCH */}
              <div className="qazan-card overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                    {pt.engineBreachClassTitle}
                  </h3>
                  <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                    {tfData.level_breaches.length}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                        <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.engineClassCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                        <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                        <th className="py-2.5 px-4 text-end">{pt.engineConfirmCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                      {tfData.level_breaches.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                            {pt.engineNoRecords}
                          </td>
                        </tr>
                      ) : (
                        [...tfData.level_breaches]
                          .reverse()
                          .slice(0, 12)
                          .map((b, idx) => (
                            <tr key={`${b.confirmed_time}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                              <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500 whitespace-nowrap" dir="ltr">
                                {fmtUtc(b.confirmed_time)}
                              </td>
                              <td
                                className={`py-2.5 px-4 font-mono font-bold whitespace-nowrap ${
                                  b.classification === 'BREAKOUT'
                                    ? 'text-emerald-600 dark:text-emerald-400'
                                    : b.classification === 'FAKEOUT'
                                      ? 'text-red-600 dark:text-red-400'
                                      : 'text-[#9A7209] dark:text-[#E5C76B]'
                                }`}
                              >
                                {b.classification}
                                {b.structure_tag ? ` · ${b.structure_tag}` : ''}
                              </td>
                              <td className={`py-2.5 px-4 font-mono font-semibold ${biasToneClass(b.side)}`}>
                                {b.side}
                              </td>
                              <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                                ${fmtPrice(b.level_price)}
                              </td>
                              <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                                ${fmtPrice(b.confirmation_close)}
                              </td>
                              <td className="py-2.5 px-4 text-slate-600 dark:text-slate-400 max-w-xs truncate">
                                {b.reason}
                              </td>
                            </tr>
                          ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Liquidity: External, Internal, EQH/EQL, Sweeps */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="qazan-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                    {pt.engineExternalLiq} & {pt.engineInternalLiq}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-start">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                          <th className="py-2.5 px-4 text-start">{pt.engineScopeCol}</th>
                          <th className="py-2.5 px-4 text-start">{pt.directionCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.distanceLabel}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {[...tfData.external_liquidity.slice(0, 6), ...tfData.internal_liquidity.slice(0, 6)].length === 0 ? (
                          <tr>
                            <td colSpan={5} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                              {pt.engineNoRecords}
                            </td>
                          </tr>
                        ) : (
                          [...tfData.external_liquidity.slice(0, 6), ...tfData.internal_liquidity.slice(0, 6)].map(
                            (liq, idx) => (
                              <tr key={`${liq.scope}-${liq.price}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                                <td className="py-2.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                                  {liq.scope} · {liq.pool_type}
                                </td>
                                <td
                                  className={`py-2.5 px-4 font-mono font-bold ${
                                    liq.side === 'BSL'
                                      ? 'text-red-600 dark:text-red-400'
                                      : 'text-emerald-600 dark:text-emerald-400'
                                  }`}
                                >
                                  {liq.side} ({liq.touches})
                                </td>
                                <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                                  ${fmtPrice(liq.price)}
                                </td>
                                <td className="py-2.5 px-4 text-end font-mono tabular-nums text-slate-500">
                                  {liq.distance_pct.toFixed(2)}%
                                </td>
                                <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                  {liq.swept ? 'SWEPT' : 'UNTAPPED'}
                                </td>
                              </tr>
                            ),
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* EQH/EQL + Sweeps */}
                <div className="qazan-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                    {pt.engineEqhlTitle} · {pt.engineSweepsTitle}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-start">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                          <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                          <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {tfData.equal_highs_lows.length === 0 && tfData.liquidity_sweeps.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                              {pt.engineNoRecords}
                            </td>
                          </tr>
                        ) : (
                          <>
                            {tfData.equal_highs_lows.slice(-5).map((eq, idx) => (
                              <tr key={`eq-${eq.confirmed_time}-${idx}`}>
                                <td className="py-2.5 px-4 font-mono font-bold text-[#9A7209] dark:text-[#E5C76B]">
                                  {eq.kind} ({eq.touches}x)
                                </td>
                                <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                  {fmtUtc(eq.confirmed_time)}
                                </td>
                                <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                                  ${fmtPrice(eq.avg_price)}
                                </td>
                                <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                  {eq.swept ? 'SWEPT' : 'INTACT'}
                                </td>
                              </tr>
                            ))}
                            {[...tfData.liquidity_sweeps]
                              .reverse()
                              .slice(0, 6)
                              .map((sw, idx) => (
                                <tr key={`sw-${sw.time}-${idx}`}>
                                  <td
                                    className={`py-2.5 px-4 font-mono font-bold ${
                                      sw.side === 'SSL_SWEEP'
                                        ? 'text-emerald-600 dark:text-emerald-400'
                                        : 'text-red-600 dark:text-red-400'
                                    }`}
                                  >
                                    {sw.side} ({sw.scope})
                                  </td>
                                  <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                    {fmtUtc(sw.time)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                                    ${fmtPrice(sw.swept_level)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums text-slate-500">
                                    Wick {(sw.wick_ratio * 100).toFixed(0)}%
                                  </td>
                                </tr>
                              ))}
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Institutional Zones: Supply/Demand, Order Blocks, Breaker Blocks, FVG */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Supply/Demand + Order Blocks */}
                <div className="qazan-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                    {pt.engineSupplyDemandTitle} · {pt.engineOrderBlocksTitle}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-start">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                          <th className="py-2.5 px-4 text-start">{pt.enginePatternCol}</th>
                          <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineZoneBoundsCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {tfData.supply_demand_zones.length === 0 && tfData.order_blocks.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                              {pt.engineNoRecords}
                            </td>
                          </tr>
                        ) : (
                          <>
                            {[...tfData.supply_demand_zones]
                              .reverse()
                              .slice(0, 6)
                              .map((sd, idx) => (
                                <tr key={`sd-${sd.formed_time}-${idx}`}>
                                  <td
                                    className={`py-2.5 px-4 font-mono font-bold ${
                                      sd.zone_type === 'DEMAND'
                                        ? 'text-emerald-600 dark:text-emerald-400'
                                        : 'text-red-600 dark:text-red-400'
                                    }`}
                                  >
                                    {sd.zone_type} ({sd.pattern})
                                  </td>
                                  <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                    {fmtUtc(sd.formed_time)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                                    ${fmtPrice(sd.bottom)} – ${fmtPrice(sd.top)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                    {sd.status}
                                  </td>
                                </tr>
                              ))}
                            {[...tfData.order_blocks]
                              .reverse()
                              .slice(0, 6)
                              .map((ob, idx) => (
                                <tr key={`ob-${ob.formed_time}-${idx}`}>
                                  <td className={`py-2.5 px-4 font-mono font-bold ${biasToneClass(ob.direction)}`}>
                                    OB {ob.direction}
                                  </td>
                                  <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                    {fmtUtc(ob.formed_time)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                                    ${fmtPrice(ob.low)} – ${fmtPrice(ob.high)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                    {ob.status}
                                  </td>
                                </tr>
                              ))}
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Breaker Blocks + Fair Value Gaps */}
                <div className="qazan-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm">
                    {pt.engineBreakerBlocksTitle} · {pt.engineFvgTitle}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-start">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                          <th className="py-2.5 px-4 text-start">{pt.enginePatternCol}</th>
                          <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineZoneBoundsCol}</th>
                          <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {tfData.breaker_blocks.length === 0 && tfData.fair_value_gaps.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-4 px-4 text-slate-500 dark:text-slate-400 text-center">
                              {pt.engineNoRecords}
                            </td>
                          </tr>
                        ) : (
                          <>
                            {[...tfData.breaker_blocks]
                              .reverse()
                              .slice(0, 6)
                              .map((br, idx) => (
                                <tr key={`br-${br.flipped_time}-${idx}`}>
                                  <td
                                    className={`py-2.5 px-4 font-mono font-bold ${
                                      br.direction === 'BULLISH_BREAKER'
                                        ? 'text-emerald-600 dark:text-emerald-400'
                                        : 'text-red-600 dark:text-red-400'
                                    }`}
                                  >
                                    {br.direction}
                                  </td>
                                  <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                    {fmtUtc(br.flipped_time)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                                    ${fmtPrice(br.low)} – ${fmtPrice(br.high)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                    {br.status}
                                  </td>
                                </tr>
                              ))}
                            {[...tfData.fair_value_gaps]
                              .reverse()
                              .slice(0, 6)
                              .map((fvg, idx) => (
                                <tr key={`fvg-${fvg.formed_time}-${idx}`}>
                                  <td className={`py-2.5 px-4 font-mono font-bold ${biasToneClass(fvg.direction)}`}>
                                    FVG {fvg.direction}
                                  </td>
                                  <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                                    {fmtUtc(fvg.formed_time)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono tabular-nums">
                                    ${fmtPrice(fvg.bottom)} – ${fmtPrice(fvg.top)}
                                  </td>
                                  <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                                    {fvg.status}
                                  </td>
                                </tr>
                              ))}
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* HH / HL / LH / LL Causal Sequence */}
              <div className="qazan-card overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                    HH / HL / LH / LL ({tfData.timeframe})
                  </h3>
                  <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                    {tfData.hh_hl_lh_ll_sequence.length}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-start">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                        <th className="py-2.5 px-4 text-start">{pt.timeCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.eventCol}</th>
                        <th className="py-2.5 px-4 text-start">{pt.engineScopeCol}</th>
                        <th className="py-2.5 px-4 text-end">{pt.levelCol}</th>
                        <th className="py-2.5 px-4 text-end">{pt.engineStatusCol}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                      {[...tfData.hh_hl_lh_ll_sequence]
                        .reverse()
                        .slice(0, 12)
                        .map((sw, idx) => (
                          <tr key={`${sw.pivot_time}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                            <td className="py-2.5 px-4 font-mono tabular-nums text-slate-500" dir="ltr">
                              {fmtUtc(sw.pivot_time)}
                            </td>
                            <td
                              className={`py-2.5 px-4 font-mono font-bold ${
                                sw.label === 'HH' || sw.label === 'HL'
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-red-600 dark:text-red-400'
                              }`}
                            >
                              {sw.label} ({sw.kind})
                            </td>
                            <td className="py-2.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                              {sw.scope}
                            </td>
                            <td className="py-2.5 px-4 text-end font-mono tabular-nums font-semibold">
                              ${fmtPrice(sw.price)}
                            </td>
                            <td className="py-2.5 px-4 text-end font-mono text-slate-500">
                              {sw.broken ? 'BROKEN' : sw.swept ? 'SWEPT' : 'INTACT'}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
