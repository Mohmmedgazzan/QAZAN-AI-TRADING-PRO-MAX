import { useCallback, useEffect, useState } from 'react';
import { ArrowDownUp, Database, RefreshCw, Search } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { MarketDataProvenanceView } from '@/components/engine/MarketDataProvenanceView';
import { useApp } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';
import type { MarketTickersResponse } from '@/types/platform';

interface MarketOverviewSectionProps {
  onNavigate: (section: SectionId) => void;
}

type SortField = 'volume' | 'change' | 'symbol';
type MarketTab = 'pulse' | 'ingestion';

function fmtPrice(v: number): string {
  if (v >= 100) return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export function MarketOverviewSection({ onNavigate }: MarketOverviewSectionProps) {
  const { setActiveSymbol, pt, t } = useApp();
  const [activeTab, setActiveTab] = useState<MarketTab>('pulse');
  const [data, setData] = useState<MarketTickersResponse | null>(null);
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortField>('volume');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await platformClient.getMarketTickers();
      setData(res);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = (data?.tickers || [])
    .filter((tk) => tk.symbol.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'change') return b.price_change_pct - a.price_change_pct;
      if (sortBy === 'symbol') return a.symbol.localeCompare(b.symbol);
      return b.quote_volume_24h - a.quote_volume_24h;
    });

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['market-overview']}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.overviewSubtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 p-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17]">
          <button
            type="button"
            onClick={() => setActiveTab('pulse')}
            className={`min-h-[38px] px-3 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer transition-colors ${
              activeTab === 'pulse'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {pt.marketTabPulse}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('ingestion')}
            className={`min-h-[38px] px-3 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer inline-flex items-center gap-1.5 transition-colors ${
              activeTab === 'ingestion'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>{pt.marketTabIntelligence}</span>
          </button>
        </div>
      </div>

      {activeTab === 'ingestion' ? (
        <MarketDataProvenanceView onSymbolsUpdated={() => void load()} />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="relative flex-1 min-w-[180px] sm:max-w-xs">
              <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={pt.searchPair}
                className="qazan-input ps-9 pe-3 text-xs"
              />
            </div>

            <div className="flex items-center gap-1 p-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] text-xs">
              <ArrowDownUp className="w-3.5 h-3.5 ms-1.5 text-[#D4AF37]" />
              {(['volume', 'change', 'symbol'] as const).map((field) => (
                <button
                  key={field}
                  type="button"
                  onClick={() => setSortBy(field)}
                  className={`min-h-[34px] px-2.5 rounded-md font-semibold cursor-pointer ${
                    sortBy === field
                      ? 'bg-[#D4AF37] text-[#06080D]'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                  }`}
                >
                  {field === 'volume' ? 'Vol' : field === 'change' ? '24h%' : 'A-Z'}
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
              <span>{pt.refresh}</span>
            </button>
          </div>

          {error && (
            <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
              {error}
            </div>
          )}

          {/* Mobile Cards (< md) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:hidden">
            {filtered.map((tk) => (
              <div key={tk.symbol} className="qazan-card p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-mono font-bold text-sm">{tk.symbol}</p>
                    <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
                      Vol ${(tk.quote_volume_24h / 1_000_000).toFixed(2)}M · {tk.spread_pct.toFixed(4)}%
                    </p>
                  </div>
                  <div className="text-end font-mono tabular-nums">
                    <p className="font-bold text-sm">${fmtPrice(tk.last_price)}</p>
                    <p className={`text-xs font-semibold ${tk.price_change_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                      {tk.price_change_pct >= 0 ? '+' : ''}{tk.price_change_pct.toFixed(2)}%
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSymbol(tk.symbol);
                      onNavigate('live-charts');
                    }}
                    className="flex-1 min-h-[40px] rounded-lg bg-slate-100 dark:bg-[#111722] text-xs font-semibold"
                  >
                    {pt.openInCharts}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSymbol(tk.symbol);
                      onNavigate('paper-trading');
                    }}
                    className="flex-1 min-h-[40px] rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/35 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B]"
                  >
                    {pt.tradeNow}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Institutional Desktop Table (md+) */}
          <div className="hidden md:block qazan-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-start border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500 dark:text-slate-400">
                    <th className="py-3 px-4 font-semibold text-start">{pt.symbolCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.priceCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.change24hCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.highLowCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.volume24hCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.spreadCol}</th>
                    <th className="py-3 px-4 font-semibold text-end">{pt.actionCol}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                  {loading && filtered.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        {pt.loading}
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        {t.logsEmpty}
                      </td>
                    </tr>
                  ) : (
                    filtered.map((tk) => {
                      const pct =
                        tk.high_24h > tk.low_24h
                          ? Math.min(100, Math.max(0, ((tk.last_price - tk.low_24h) / (tk.high_24h - tk.low_24h)) * 100))
                          : 50;
                      return (
                        <tr key={tk.symbol} className="hover:bg-slate-50 dark:hover:bg-[#111722]/70 transition-colors">
                          <td className="py-3 px-4 font-mono font-bold text-slate-900 dark:text-slate-100">
                            {tk.symbol}
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums font-semibold text-slate-900 dark:text-slate-100">
                            ${fmtPrice(tk.last_price)}
                          </td>
                          <td
                            className={`py-3 px-4 text-end font-mono tabular-nums font-semibold ${
                              tk.price_change_pct >= 0
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {tk.price_change_pct >= 0 ? '+' : ''}
                            {tk.price_change_pct.toFixed(2)}%
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums text-slate-600 dark:text-slate-400">
                            <div className="inline-flex flex-col items-end gap-1 min-w-[140px]">
                              <span>
                                ${fmtPrice(tk.high_24h)} / ${fmtPrice(tk.low_24h)}
                              </span>
                              <div className="w-28 h-1 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden" dir="ltr">
                                <div className="h-full bg-[#D4AF37]" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums text-slate-700 dark:text-slate-300">
                            ${(tk.quote_volume_24h / 1_000_000).toFixed(2)}M
                          </td>
                          <td className="py-3 px-4 text-end font-mono tabular-nums text-slate-500 dark:text-slate-400">
                            {tk.spread_pct.toFixed(4)}%
                          </td>
                          <td className="py-3 px-4 text-end">
                            <div className="inline-flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => {
                                  setActiveSymbol(tk.symbol);
                                  onNavigate('live-charts');
                                }}
                                className="min-h-[36px] px-2.5 rounded-md bg-slate-100 dark:bg-[#111722] hover:bg-slate-200 dark:hover:bg-slate-800 text-xs font-medium text-slate-800 dark:text-slate-200 cursor-pointer"
                              >
                                {pt.openInCharts}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setActiveSymbol(tk.symbol);
                                  onNavigate('paper-trading');
                                }}
                                className="min-h-[36px] px-2.5 rounded-md bg-[#D4AF37]/15 hover:bg-[#D4AF37]/25 border border-[#D4AF37]/30 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] cursor-pointer"
                              >
                                {pt.tradeNow}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {data && (
            <p className="text-xs font-mono text-slate-500 dark:text-slate-400">
              {t.sourceLabel}: {data.source} · {t.updatedAt}: {new Date(data.fetched_at).toISOString()}
            </p>
          )}
        </>
      )}
    </section>
  );
}
