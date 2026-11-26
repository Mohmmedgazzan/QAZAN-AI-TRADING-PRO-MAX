import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { TradeOpportunityDiscoveryView } from '@/components/engine/TradeOpportunityDiscoveryView';
import { useApp } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';
import type { TradeScannerResponse } from '@/types/platform';

export function TradeScannerSection({ onNavigate }: { onNavigate: (s: SectionId) => void }) {
  const { activeInterval, setActiveSymbol, pt, t } = useApp();
  const [subtab, setSubtab] = useState<'discovery' | 'classic'>('discovery');
  const [data, setData] = useState<TradeScannerResponse | null>(null);
  const [signalFilter, setSignalFilter] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await platformClient.getTradeScanner(activeInterval));
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeInterval]);

  useEffect(() => {
    if (subtab === 'classic' && !data) {
      void load();
    }
  }, [subtab, data, load]);

  const items = (data?.items ?? []).filter((item) =>
    signalFilter === 'ALL' ? true : item.signal === signalFilter,
  );

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {subtab === 'discovery'
              ? pt.discTitle
              : `${pt.sections['trade-scanner']} (${activeInterval})`}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            {subtab === 'discovery' ? pt.discSubtitle : pt.scannerSubtitle}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 max-w-full">
          <div className="flex flex-wrap items-center gap-1 p-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] text-xs max-w-full">
            <button
              type="button"
              onClick={() => setSubtab('discovery')}
              className={`min-h-[36px] px-3 py-1.5 rounded-md font-semibold cursor-pointer text-start sm:whitespace-nowrap ${
                subtab === 'discovery'
                  ? 'bg-[#D4AF37] text-[#06080D]'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              {pt.scannerTabDiscovery}
            </button>
            <button
              type="button"
              onClick={() => setSubtab('classic')}
              className={`min-h-[36px] px-3 py-1.5 rounded-md font-semibold cursor-pointer text-start sm:whitespace-nowrap ${
                subtab === 'classic'
                  ? 'bg-[#D4AF37] text-[#06080D]'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              {pt.scannerTabClassic}
            </button>
          </div>
        </div>
      </div>

      {subtab === 'discovery' ? (
        <TradeOpportunityDiscoveryView onNavigate={onNavigate} />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="flex items-center gap-1 p-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] text-xs">
              {(['ALL', 'LONG', 'SHORT'] as const).map((sig) => (
                <button
                  key={sig}
                  type="button"
                  onClick={() => setSignalFilter(sig)}
                  className={`min-h-[34px] px-2.5 rounded-md font-mono font-semibold cursor-pointer ${
                    signalFilter === sig
                      ? 'bg-[#D4AF37] text-[#06080D]'
                      : 'text-slate-600 dark:text-slate-400'
                  }`}
                >
                  {sig === 'ALL' ? t.filterAll : sig}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="qazan-btn-gold"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span>{pt.runScan}</span>
            </button>
          </div>

          {error && (
            <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
              {error}
            </div>
          )}

      {/* Mobile Cards (< md) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:hidden">
        {items.map((item) => (
          <div key={item.symbol} className="qazan-card p-4 space-y-3 text-xs">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono font-bold text-sm">{item.symbol}</p>
                <p className="font-mono text-slate-500 tabular-nums">
                  RSI {item.rsi_14.toFixed(1)} · {item.risk_reward.toFixed(2)}R
                </p>
              </div>
              <div className="text-end font-mono">
                <p
                  className={`font-bold ${
                    item.signal === 'LONG'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : item.signal === 'SHORT'
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-slate-500'
                  }`}
                >
                  {item.signal} · {item.score}/100
                </p>
                <p className="tabular-nums text-slate-500">
                  ${item.last_price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                </p>
              </div>
            </div>
            <p className="font-mono tabular-nums text-[11px] text-slate-600 dark:text-slate-300">
              {item.suggested_entry.toFixed(2)} / SL {item.stop_loss.toFixed(2)} / TP {item.take_profit.toFixed(2)}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setActiveSymbol(item.symbol);
                  onNavigate('live-charts');
                }}
                className="flex-1 min-h-[40px] rounded-lg bg-slate-100 dark:bg-[#111722] font-semibold"
              >
                {pt.openInCharts}
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveSymbol(item.symbol);
                  onNavigate('paper-trading');
                }}
                className="flex-1 min-h-[40px] rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/35 font-semibold text-[#9A7209] dark:text-[#E5C76B]"
              >
                {pt.tradeNow}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop Institutional Table */}
      <div className="hidden md:block qazan-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-start border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500 dark:text-slate-400">
                <th className="py-3 px-4 text-start">{pt.symbolCol}</th>
                <th className="py-3 px-4 text-end">{pt.priceCol}</th>
                <th className="py-3 px-4 text-end">RSI(14)</th>
                <th className="py-3 px-4 text-start">{pt.emaTrendCol}</th>
                <th className="py-3 px-4 text-start">{pt.signalCol}</th>
                <th className="py-3 px-4 text-end">{pt.entrySlTpCol}</th>
                <th className="py-3 px-4 text-end">{pt.rrCol}</th>
                <th className="py-3 px-4 text-end">{pt.scoreCol}</th>
                <th className="py-3 px-4 text-end">{pt.actionCol}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {loading && !data ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500">
                    {pt.loading}
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.symbol} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-3 px-4 font-mono font-bold">{item.symbol}</td>
                    <td className="py-3 px-4 text-end font-mono tabular-nums">
                      ${item.last_price.toLocaleString('en-US', { maximumFractionDigits: 4 })}
                    </td>
                    <td className="py-3 px-4 text-end font-mono tabular-nums">{item.rsi_14.toFixed(1)}</td>
                    <td
                      className={`py-3 px-4 font-mono font-semibold ${
                        item.ema_trend === 'BULLISH'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {item.ema_trend}
                    </td>
                    <td
                      className={`py-3 px-4 font-mono font-bold ${
                        item.signal === 'LONG'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : item.signal === 'SHORT'
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-slate-500'
                      }`}
                    >
                      {item.signal}
                    </td>
                    <td className="py-3 px-4 text-end font-mono tabular-nums text-slate-600 dark:text-slate-300">
                      {item.suggested_entry.toFixed(2)} / {item.stop_loss.toFixed(2)} / {item.take_profit.toFixed(2)}
                    </td>
                    <td className="py-3 px-4 text-end font-mono tabular-nums">{item.risk_reward.toFixed(2)}R</td>
                    <td className="py-3 px-4 text-end font-mono tabular-nums">
                      <div className="inline-flex items-center gap-2">
                        <div className="w-12 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden" dir="ltr">
                          <div className="h-full bg-[#D4AF37]" style={{ width: `${item.score}%` }} />
                        </div>
                        <span className="font-bold text-[#9A7209] dark:text-[#E5C76B]">{item.score}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-end">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setActiveSymbol(item.symbol);
                            onNavigate('live-charts');
                          }}
                          className="min-h-[36px] px-2.5 rounded-md bg-slate-100 dark:bg-[#111722] hover:bg-slate-200 dark:hover:bg-slate-800 text-xs font-medium cursor-pointer"
                        >
                          {pt.openInCharts}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setActiveSymbol(item.symbol);
                            onNavigate('paper-trading');
                          }}
                          className="min-h-[36px] px-2.5 rounded-md bg-[#D4AF37]/15 hover:bg-[#D4AF37]/25 border border-[#D4AF37]/30 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] cursor-pointer"
                        >
                          {pt.tradeNow}
                        </button>
                      </div>
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
    </section>
  );
}
