import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  BrainCircuit,
  CandlestickChart,
  Radar,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { ApiClientError, apiClient } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { TradingChart } from '@/components/TradingChart';
import { useApp } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';
import type { MarketKlinesResponse } from '@/types/api';
import type {
  DashboardSummaryResponse,
  MacroNewsResponse,
  MarketStructureResponse,
} from '@/types/platform';

interface DashboardSectionProps {
  onNavigate: (section: SectionId) => void;
}

function fmtPrice(v: number): string {
  if (v >= 100) return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export function DashboardSection({ onNavigate }: DashboardSectionProps) {
  const { activeSymbol, activeInterval, setActiveSymbol, pt, t, language } = useApp();
  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [klines, setKlines] = useState<MarketKlinesResponse | null>(null);
  const [structure, setStructure] = useState<MarketStructureResponse | null>(null);
  const [macroAlert, setMacroAlert] = useState<MacroNewsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, klineRes, structRes, macroRes] = await Promise.all([
        platformClient.getDashboardSummary(activeSymbol, activeInterval),
        apiClient.getMarketKlines(activeSymbol, activeInterval, 120),
        platformClient.getMarketStructure(activeSymbol, activeInterval),
        platformClient.getMacroNews({ warning_hours: 24 }).catch(() => null),
      ]);
      setData(summaryRes);
      setKlines(klineRes);
      setStructure(structRes);
      setMacroAlert(macroRes);
    } catch (err) {
      const msg = err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err);
      setError(msg);
      await apiClient.reportClientError(msg, 'DashboardSection');
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  useEffect(() => {
    void load();
  }, [load]);

  const activeTicker = data?.tickers.find((tk) => tk.symbol === activeSymbol) ?? data?.tickers[0];
  const rangePct =
    activeTicker && activeTicker.high_24h > activeTicker.low_24h
      ? Math.min(
          100,
          Math.max(
            0,
            ((activeTicker.last_price - activeTicker.low_24h) /
              (activeTicker.high_24h - activeTicker.low_24h)) *
              100,
          ),
        )
      : 50;

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {pt.sections.dashboard} · {activeSymbol}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.dashSubtitle}</p>
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
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono flex items-center justify-between gap-3"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="min-h-[40px] px-3 rounded-lg bg-red-600 text-white font-semibold shrink-0"
          >
            {t.retry}
          </button>
        </div>
      )}

      {macroAlert && macroAlert.active_warning_level !== 'CLEAR' && macroAlert.high_impact_warnings.length > 0 && (
        <div
          role="status"
          className={`p-3.5 rounded-xl border flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between text-xs ${
            macroAlert.active_warning_level === 'CRITICAL'
              ? 'border-red-500/45 bg-red-50 dark:bg-red-950/35 text-red-900 dark:text-red-100'
              : 'border-amber-500/45 bg-amber-50 dark:bg-amber-950/25 text-amber-950 dark:text-amber-100'
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
            <span>
              {language === 'ar'
                ? macroAlert.high_impact_warnings[0].warning_text_ar
                : macroAlert.high_impact_warnings[0].warning_text_en}
            </span>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('economic-calendar')}
            className="min-h-[36px] inline-flex items-center gap-1 font-semibold text-[#9A7209] dark:text-[#E5C76B] hover:underline whitespace-nowrap shrink-0 cursor-pointer"
          >
            <span>{pt.sections['economic-calendar']}</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {loading && !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 qazan-card animate-pulse" />
            ))}
          </div>
          <div className="h-[380px] qazan-card animate-pulse" />
        </div>
      ) : data ? (
        <>
          {/* Institutional 4-KPI Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="qazan-card-gold p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.paperEquity}</p>
              <p className="mt-1.5 text-lg sm:text-xl font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                ${data.paper_equity_usdt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="mt-1 text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400 truncate">
                {pt.availableBalance}: ${data.paper_balance_usdt.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.realizedPnl}</p>
              <p
                className={`mt-1.5 text-lg sm:text-xl font-mono font-bold tabular-nums flex items-center gap-1.5 ${
                  data.realized_pnl_usdt >= 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {data.realized_pnl_usdt >= 0 ? '+' : ''}${data.realized_pnl_usdt.toFixed(2)}
              </p>
              <p className="mt-1 text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.openPositions}: {data.open_positions_count}
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                {pt.quickAiBias} · {data.active_symbol}
              </p>
              <p
                className={`mt-1.5 text-lg sm:text-xl font-mono font-bold flex items-center gap-1.5 ${
                  data.quick_ai_signal === 'BULLISH'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {data.quick_ai_signal === 'BULLISH' ? (
                  <TrendingUp className="w-4 h-4 shrink-0" />
                ) : (
                  <TrendingDown className="w-4 h-4 shrink-0" />
                )}
                <span>{data.quick_ai_signal === 'BULLISH' ? pt.bullish : pt.bearish}</span>
              </p>
              <p className="mt-1 text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                {pt.confidence}: {data.quick_ai_confidence_pct.toFixed(1)}%
              </p>
            </div>

            <div className="qazan-card p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">{pt.structureRegime}</p>
              <p
                className={`mt-1.5 text-lg sm:text-xl font-mono font-bold ${
                  data.quick_structure_regime === 'UPTREND'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : data.quick_structure_regime === 'DOWNTREND'
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-[#9A7209] dark:text-[#E5C76B]'
                }`}
              >
                {data.quick_structure_regime}
              </p>
              <p className="mt-1 text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                RSI(14): {data.quick_rsi_14.toFixed(2)}
              </p>
            </div>
          </div>

          {/* 12-Col Institutional Terminal Split: Embedded Chart + Active Pair Telemetry */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div className="lg:col-span-8 qazan-card p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <CandlestickChart className="w-4 h-4 text-[#D4AF37]" />
                  <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">
                    {activeSymbol} · {activeInterval}
                  </h2>
                  {klines && (
                    <span className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
                      VWAP ${fmtPrice(klines.summary.vwap)}
                    </span>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => onNavigate('live-charts')}
                  className="min-h-[36px] inline-flex items-center gap-1 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] hover:underline cursor-pointer"
                >
                  <span>{pt.expandChart}</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
              </div>

              {klines ? (
                <TradingChart
                  candles={klines.candles}
                  ema20={structure?.ema_20_series ?? []}
                  ema50={structure?.ema_50_series ?? []}
                  swings={structure?.swings ?? []}
                  events={structure?.events ?? []}
                  showEma20
                  showEma50
                  showStructure
                  heightClass="h-[300px] sm:h-[360px]"
                />
              ) : (
                <div className="h-[320px] flex items-center justify-center text-xs text-slate-500">
                  {pt.loading}
                </div>
              )}
            </div>

            <div className="lg:col-span-4 qazan-card p-4 flex flex-col justify-between gap-4">
              {activeTicker && (
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
                    <div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{pt.activePair}</p>
                      <p className="text-lg font-mono font-bold text-slate-900 dark:text-slate-100">
                        {activeTicker.symbol}
                      </p>
                    </div>
                    <div className="text-end">
                      <p className="text-lg font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">
                        ${fmtPrice(activeTicker.last_price)}
                      </p>
                      <p
                        className={`text-xs font-mono font-semibold tabular-nums ${
                          activeTicker.price_change_pct >= 0
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {activeTicker.price_change_pct >= 0 ? '+' : ''}
                        {activeTicker.price_change_pct.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  {/* 24h Range Track */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                      <span>L: ${fmtPrice(activeTicker.low_24h)}</span>
                      <span>H: ${fmtPrice(activeTicker.high_24h)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800 relative" dir="ltr">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-red-500/70 via-[#D4AF37] to-emerald-500/80"
                        style={{ width: `${rangePct}%` }}
                      />
                    </div>
                  </div>

                  <dl className="divide-y divide-slate-100 dark:divide-slate-800 text-xs font-mono">
                    <div className="py-2 flex justify-between">
                      <dt className="text-slate-500 dark:text-slate-400">Bid / Ask</dt>
                      <dd className="tabular-nums font-semibold">
                        ${fmtPrice(activeTicker.bid_price)} / ${fmtPrice(activeTicker.ask_price)}
                      </dd>
                    </div>
                    <div className="py-2 flex justify-between">
                      <dt className="text-slate-500 dark:text-slate-400">{pt.spreadCol}</dt>
                      <dd className="tabular-nums">{activeTicker.spread_pct.toFixed(4)}%</dd>
                    </div>
                    <div className="py-2 flex justify-between">
                      <dt className="text-slate-500 dark:text-slate-400">{pt.volume24hCol}</dt>
                      <dd className="tabular-nums">
                        ${(activeTicker.quote_volume_24h / 1_000_000).toFixed(2)}M
                      </dd>
                    </div>
                    {structure && (
                      <div className="py-2 flex justify-between">
                        <dt className="text-slate-500 dark:text-slate-400">{pt.atrLabel}</dt>
                        <dd className="tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                          ${structure.atr_14.toFixed(4)}
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
              )}

              {/* Quick Desk Shortcuts */}
              <div className="grid grid-cols-1 gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => onNavigate('paper-trading')}
                  className="qazan-btn-gold w-full"
                >
                  <Wallet className="w-4 h-4" />
                  <span>{pt.sections['paper-trading']}</span>
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => onNavigate('ai-analysis')}
                    className="qazan-btn-secondary w-full"
                  >
                    <BrainCircuit className="w-4 h-4 text-[#D4AF37]" />
                    <span className="truncate">{pt.sections['ai-analysis']}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onNavigate('trade-scanner')}
                    className="qazan-btn-secondary w-full"
                  >
                    <Radar className="w-4 h-4 text-[#D4AF37]" />
                    <span className="truncate">{pt.sections['trade-scanner']}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Live 24h Market Pulse Matrix */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                {pt.marketPulse}
              </h2>
              <button
                type="button"
                onClick={() => onNavigate('market-overview')}
                className="min-h-[40px] inline-flex items-center gap-1 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] hover:underline cursor-pointer"
              >
                <span>{pt.sections['market-overview']}</span>
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {data.tickers.map((tk) => {
                const pct =
                  tk.high_24h > tk.low_24h
                    ? Math.min(100, Math.max(0, ((tk.last_price - tk.low_24h) / (tk.high_24h - tk.low_24h)) * 100))
                    : 50;
                const isSelected = tk.symbol === activeSymbol;
                return (
                  <div
                    key={tk.symbol}
                    className={`p-4 rounded-xl border transition-colors flex flex-col justify-between gap-3 ${
                      isSelected
                        ? 'border-[#D4AF37]/50 bg-white dark:bg-[#0D131F]'
                        : 'border-slate-200/90 dark:border-slate-800/90 hover:border-[#D4AF37]/35 bg-white dark:bg-[#0B0F17]'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-mono font-bold text-sm text-slate-900 dark:text-slate-100">
                          {tk.symbol}
                        </p>
                        <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                          Vol: ${(tk.quote_volume_24h / 1_000_000).toFixed(2)}M
                        </p>
                      </div>
                      <div className="text-end">
                        <p className="font-mono font-bold text-base tabular-nums text-slate-900 dark:text-slate-100">
                          ${fmtPrice(tk.last_price)}
                        </p>
                        <p
                          className={`font-mono text-xs font-semibold tabular-nums ${
                            tk.price_change_pct >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {tk.price_change_pct >= 0 ? '+' : ''}
                          {tk.price_change_pct.toFixed(2)}%
                        </p>
                      </div>
                    </div>

                    <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden" dir="ltr">
                      <div
                        className={`h-full rounded-full ${
                          tk.price_change_pct >= 0 ? 'bg-emerald-500/80' : 'bg-red-500/80'
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => {
                          setActiveSymbol(tk.symbol);
                          onNavigate('live-charts');
                        }}
                        className="flex-1 min-h-[40px] px-3 rounded-lg bg-slate-100 dark:bg-[#111722] hover:bg-slate-200 dark:hover:bg-slate-800 text-xs font-semibold text-slate-800 dark:text-slate-200 transition-colors cursor-pointer"
                      >
                        {pt.openInCharts}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setActiveSymbol(tk.symbol);
                          onNavigate('paper-trading');
                        }}
                        className="flex-1 min-h-[40px] px-3 rounded-lg bg-[#D4AF37]/15 hover:bg-[#D4AF37]/25 border border-[#D4AF37]/35 text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] transition-colors cursor-pointer"
                      >
                        {pt.tradeNow}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
