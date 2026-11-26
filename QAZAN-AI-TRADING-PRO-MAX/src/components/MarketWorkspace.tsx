import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { apiClient, ApiClientError } from '@/api/client';
import { TradingChart } from '@/components/TradingChart';
import { useApp } from '@/contexts/AppContext';
import type { MarketKlinesResponse } from '@/types/api';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT'] as const;
const INTERVALS = ['15m', '1h', '4h', '1d'] as const;

function formatPrice(val: number): string {
  if (val >= 100) return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export function MarketWorkspace() {
  const { t } = useApp();
  const [symbol, setSymbol] = useState<string>('BTCUSDT');
  const [interval, setInterval] = useState<string>('1h');
  const [data, setData] = useState<MarketKlinesResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadMarketData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getMarketKlines(symbol, interval, 120);
      setData(response);
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? `${err.code}: ${err.message}${err.details ? ` (${err.details})` : ''}`
          : err instanceof Error
            ? err.message
            : 'Unknown error fetching market data';
      setError(msg);
      await apiClient.reportClientError(msg, `MarketWorkspace(${symbol}, ${interval})`);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  useEffect(() => {
    void loadMarketData();
  }, [loadMarketData]);

  return (
    <section className="space-y-5">
      {/* Header & Controls */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 text-balance">
            {t.chartHeading}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {t.chartSubheading}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Symbol Selector */}
          <div className="flex items-center gap-1 p-1 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg overflow-x-auto max-w-full">
            {SYMBOLS.map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => setSymbol(sym)}
                className={`min-h-[40px] px-3 text-xs font-mono font-medium rounded-md transition-colors whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-sky-500 ${
                  symbol === sym
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/70 dark:hover:bg-slate-800'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Timeframe Selector */}
          <div className="flex items-center gap-1 p-1 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg">
            {INTERVALS.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setInterval(tf)}
                className={`min-h-[40px] px-2.5 text-xs font-mono font-medium rounded-md transition-colors whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-sky-500 ${
                  interval === tf
                    ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/70 dark:hover:bg-slate-800'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => void loadMarketData()}
            disabled={loading}
            className="min-h-[44px] inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-60 text-white transition-colors whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-sky-500"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{t.refreshData}</span>
          </button>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5 text-red-600 dark:text-red-400" />
            <div className="space-y-1 text-sm">
              <p className="font-semibold">{t.errorTitle}</p>
              <p className="font-mono text-xs break-all opacity-90">{error}</p>
              <p className="text-xs opacity-80">{t.connectionTip}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadMarketData()}
            className="min-h-[44px] px-4 py-2 text-xs font-semibold rounded-lg bg-red-600 hover:bg-red-700 text-white whitespace-nowrap shrink-0"
          >
            {t.retry}
          </button>
        </div>
      )}

      {/* Cache Fallback Notice */}
      {data?.cached_fallback && (
        <div className="p-3 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200 text-xs">
          {t.cacheFallbackNotice}
        </div>
      )}

      {/* Summary Metrics Grid (Pandas / NumPy Output) */}
      {loading && !data ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-20 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 animate-pulse"
            />
          ))}
        </div>
      ) : data ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.lastClose}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              ${formatPrice(data.summary.last_close)}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.periodChange}</p>
            <p
              className={`mt-1 text-base font-mono font-semibold tabular-nums ${
                data.summary.period_change_pct >= 0
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              {data.summary.period_change_pct >= 0 ? '+' : ''}
              {data.summary.period_change_pct.toFixed(2)}%
            </p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.periodHigh}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              ${formatPrice(data.summary.period_high)}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.periodLow}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              ${formatPrice(data.summary.period_low)}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.vwap}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              ${formatPrice(data.summary.vwap)}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">{t.totalVolume}</p>
            <p className="mt-1 text-base font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {data.summary.total_volume.toLocaleString('en-US', { maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      ) : null}

      {/* Chart Canvas */}
      {loading && !data ? (
        <div className="w-full h-[340px] sm:h-[420px] lg:h-[480px] rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
          {t.loadingChart}
        </div>
      ) : (
        <TradingChart candles={data?.candles ?? []} />
      )}

      {/* Unboxed Provenance Line */}
      {data && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-slate-400 font-mono">
          <span>
            {t.sourceLabel}: {data.source}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {t.candlesCount}: {data.candle_count}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {t.updatedAt}: {new Date(data.fetched_at).toISOString()}
          </span>
        </div>
      )}
    </section>
  );
}
