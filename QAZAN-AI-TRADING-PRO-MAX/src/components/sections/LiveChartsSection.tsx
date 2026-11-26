import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { ApiClientError, apiClient } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { TradingChart } from '@/components/TradingChart';
import { useApp } from '@/contexts/AppContext';
import type { MarketKlinesResponse } from '@/types/api';
import type { MarketStructureResponse, Ticker24h } from '@/types/platform';

function formatPrice(val: number): string {
  if (val >= 100) return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export function LiveChartsSection() {
  const { activeSymbol, activeInterval, setActiveSymbol, t, pt } = useApp();
  const [klines, setKlines] = useState<MarketKlinesResponse | null>(null);
  const [structure, setStructure] = useState<MarketStructureResponse | null>(null);
  const [tickers, setTickers] = useState<Ticker24h[]>([]);
  const [showEma20, setShowEma20] = useState(true);
  const [showEma50, setShowEma50] = useState(true);
  const [showStructure, setShowStructure] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [kRes, sRes, tkRes] = await Promise.all([
        apiClient.getMarketKlines(activeSymbol, activeInterval, 180),
        platformClient.getMarketStructure(activeSymbol, activeInterval),
        platformClient.getMarketTickers(),
      ]);
      setKlines(kRes);
      setStructure(sRes);
      setTickers(tkRes.tickers);
    } catch (err) {
      const msg = err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err);
      setError(msg);
      await apiClient.reportClientError(msg, `LiveCharts(${activeSymbol}, ${activeInterval})`);
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
            {pt.sections['live-charts']} · {activeSymbol} ({activeInterval})
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{t.chartSubheading}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowEma20((v) => !v)}
            className={`min-h-[40px] px-3 rounded-lg border text-xs font-mono font-semibold transition-colors cursor-pointer ${
              showEma20
                ? 'border-[#D4AF37]/60 bg-[#D4AF37]/15 text-[#9A7209] dark:text-[#E5C76B]'
                : 'border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400'
            }`}
          >
            {pt.showEma20}
          </button>

          <button
            type="button"
            onClick={() => setShowEma50((v) => !v)}
            className={`min-h-[40px] px-3 rounded-lg border text-xs font-mono font-semibold transition-colors cursor-pointer ${
              showEma50
                ? 'border-sky-500/60 bg-sky-500/15 text-sky-700 dark:text-sky-300'
                : 'border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400'
            }`}
          >
            {pt.showEma50}
          </button>

          <button
            type="button"
            onClick={() => setShowStructure((v) => !v)}
            className={`min-h-[40px] px-3 rounded-lg border text-xs font-mono font-semibold transition-colors cursor-pointer ${
              showStructure
                ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                : 'border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400'
            }`}
          >
            {pt.showStructureMarkers}
          </button>

          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="qazan-btn-gold min-h-[40px]"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{pt.refresh}</span>
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-mono">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => void load()} className="min-h-[40px] px-3 rounded-lg bg-red-600 text-white text-xs font-semibold">
            {t.retry}
          </button>
        </div>
      )}

      {klines && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="qazan-card-gold p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t.lastClose}</p>
            <p className="mt-1 text-base font-mono font-bold tabular-nums">${formatPrice(klines.summary.last_close)}</p>
          </div>
          <div className="qazan-card p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t.periodChange}</p>
            <p
              className={`mt-1 text-base font-mono font-bold tabular-nums ${
                klines.summary.period_change_pct >= 0
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              {klines.summary.period_change_pct >= 0 ? '+' : ''}
              {klines.summary.period_change_pct.toFixed(2)}%
            </p>
          </div>
          <div className="qazan-card p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t.periodHigh}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums">${formatPrice(klines.summary.period_high)}</p>
          </div>
          <div className="qazan-card p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t.periodLow}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums">${formatPrice(klines.summary.period_low)}</p>
          </div>
          <div className="qazan-card p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t.vwap}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums">${formatPrice(klines.summary.vwap)}</p>
          </div>
          <div className="qazan-card p-3.5">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{pt.rsiLabel}</p>
            <p className="mt-1 text-base font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
              {structure ? structure.rsi_14.toFixed(2) : '-'}
            </p>
          </div>
        </div>
      )}

      {/* Terminal Chart + Side Watchlist Split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-9">
          {loading && !klines ? (
            <div className="w-full h-[380px] sm:h-[460px] qazan-card flex items-center justify-center text-sm text-slate-500">
              {t.loadingChart}
            </div>
          ) : (
            <TradingChart
              candles={klines?.candles ?? []}
              ema20={structure?.ema_20_series ?? []}
              ema50={structure?.ema_50_series ?? []}
              swings={structure?.swings ?? []}
              events={structure?.events ?? []}
              showEma20={showEma20}
              showEma50={showEma50}
              showStructure={showStructure}
              heightClass="h-[340px] sm:h-[440px] lg:h-[520px]"
            />
          )}
        </div>

        <aside className="lg:col-span-3 qazan-card p-3.5 space-y-2.5">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
            <h2 className="text-xs font-bold text-slate-900 dark:text-slate-100">{pt.watchlistTitle}</h2>
            <span className="text-[11px] font-mono text-slate-400">24h</span>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-1 gap-1.5">
            {tickers.map((tk) => {
              const selected = tk.symbol === activeSymbol;
              return (
                <button
                  key={tk.symbol}
                  type="button"
                  onClick={() => setActiveSymbol(tk.symbol)}
                  className={`w-full min-h-[48px] px-3 py-2 rounded-lg border text-start transition-colors flex items-center justify-between gap-2 cursor-pointer ${
                    selected
                      ? 'border-[#D4AF37]/50 bg-[#D4AF37]/10'
                      : 'border-slate-100 dark:border-slate-800/80 hover:bg-slate-50 dark:hover:bg-[#111722]'
                  }`}
                >
                  <div>
                    <p className={`font-mono text-xs font-bold ${selected ? 'text-[#9A7209] dark:text-[#E5C76B]' : ''}`}>
                      {tk.symbol}
                    </p>
                    <p className="text-[10px] font-mono text-slate-500 dark:text-slate-400">
                      ${(tk.quote_volume_24h / 1_000_000).toFixed(1)}M
                    </p>
                  </div>
                  <div className="text-end font-mono tabular-nums">
                    <p className="text-xs font-semibold">${formatPrice(tk.last_price)}</p>
                    <p
                      className={`text-[11px] font-semibold ${
                        tk.price_change_pct >= 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {tk.price_change_pct >= 0 ? '+' : ''}
                      {tk.price_change_pct.toFixed(2)}%
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>
      </div>

      {klines && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-mono text-slate-500 dark:text-slate-400">
          <span>
            {t.sourceLabel}: {klines.source}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {t.candlesCount}: {klines.candle_count}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {t.updatedAt}: {new Date(klines.fetched_at).toISOString()}
          </span>
        </div>
      )}
    </section>
  );
}
