import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Plus,
  Radio,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type {
  LiquidationEventItem,
  MarketIntelligenceResponse,
  MetricStatus,
  ProvenanceMetric,
  WebSocketStreamStatus,
} from '@/types/platform';

function fmtNumber(val: number | null | undefined, digits = 2): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  return val.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtCompactUsd(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(2)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

function fmtUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return iso;
  }
}

export function MarketDataProvenanceView({ onSymbolsUpdated }: { onSymbolsUpdated?: () => void }) {
  const {
    activeSymbol,
    activeInterval,
    setActiveSymbol,
    trackedSymbols,
    refreshTrackedSymbols,
    pt,
  } = useApp();

  const [intel, setIntel] = useState<MarketIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newSymbol, setNewSymbol] = useState('');
  const [symbolActionBusy, setSymbolActionBusy] = useState(false);
  const [symbolFeedback, setSymbolFeedback] = useState<string | null>(null);

  // Real-time WebSocket state
  const [wsOpen, setWsOpen] = useState(false);
  const [wsTickPrice, setWsTickPrice] = useState<number | null>(null);
  const [wsTickChangePct, setWsTickChangePct] = useState<number | null>(null);
  const [wsTickTime, setWsTickTime] = useState<string | null>(null);
  const [wsLiveCvdBase, setWsLiveCvdBase] = useState<number | null>(null);
  const [wsStatus, setWsStatus] = useState<WebSocketStreamStatus | null>(null);
  const [wsLiquidations, setWsLiquidations] = useState<LiquidationEventItem[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const loadIntelligence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await platformClient.getMarketIntelligence(activeSymbol, activeInterval);
      setIntel(res);
      setWsStatus(res.ws_status);
      if (res.recent_liquidations.length > 0) {
        setWsLiquidations(res.recent_liquidations);
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, activeInterval]);

  useEffect(() => {
    void loadIntelligence();
  }, [loadIntelligence]);

  // Real WebSocket stream lifecycle with auto-reconnect
  useEffect(() => {
    let unmounted = false;
    setWsTickPrice(null);
    setWsTickChangePct(null);
    setWsLiveCvdBase(null);

    const connect = () => {
      if (unmounted) return;
      try {
        const ws = new WebSocket(platformClient.getWsMarketUrl(activeSymbol));
        wsRef.current = ws;

        ws.onopen = () => {
          if (!unmounted) setWsOpen(true);
        };

        ws.onmessage = (evt) => {
          if (unmounted) return;
          try {
            const msg = JSON.parse(evt.data);
            if (msg.ws_status) {
              setWsStatus(msg.ws_status);
            }
            if (msg.type === 'snapshot') {
              const tk = msg.tickers?.[activeSymbol];
              if (tk) {
                setWsTickPrice(tk.last_price);
                setWsTickChangePct(tk.price_change_pct);
                setWsTickTime(tk.updated_at);
              }
              const cvd = msg.live_cvd_delta?.[activeSymbol];
              if (cvd) {
                setWsLiveCvdBase(cvd.cumulative_delta_base);
              }
              if (Array.isArray(msg.recent_liquidations)) {
                setWsLiquidations(msg.recent_liquidations);
              }
            } else if (msg.type === 'tick' && msg.symbol === activeSymbol && msg.ticker) {
              setWsTickPrice(msg.ticker.last_price);
              setWsTickChangePct(msg.ticker.price_change_pct);
              setWsTickTime(msg.ticker.updated_at);
              if (msg.live_cvd) {
                setWsLiveCvdBase(msg.live_cvd.cumulative_delta_base);
              }
            } else if (msg.type === 'liquidation' && msg.event) {
              setWsLiquidations((prev) => [msg.event as LiquidationEventItem, ...prev].slice(0, 15));
            }
          } catch {
            // Ignore malformed frame
          }
        };

        ws.onclose = () => {
          if (unmounted) return;
          setWsOpen(false);
          reconnectTimerRef.current = window.setTimeout(connect, 3000);
        };

        ws.onerror = () => {
          if (!unmounted) setWsOpen(false);
        };
      } catch {
        if (!unmounted) setWsOpen(false);
      }
    };

    connect();
    return () => {
      unmounted = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [activeSymbol]);

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = newSymbol.trim().toUpperCase();
    if (!cleaned) return;
    setSymbolActionBusy(true);
    setSymbolFeedback(null);
    try {
      const added = await platformClient.addTrackedSymbol(cleaned);
      setNewSymbol('');
      await refreshTrackedSymbols();
      setActiveSymbol(added.symbol);
      onSymbolsUpdated?.();
      setSymbolFeedback(`+ ${added.symbol}`);
    } catch (err) {
      setSymbolFeedback(err instanceof ApiClientError ? err.message : String(err));
    } finally {
      setSymbolActionBusy(false);
    }
  };

  const handleRemoveSymbol = async (sym: string) => {
    setSymbolActionBusy(true);
    setSymbolFeedback(null);
    try {
      await platformClient.deleteTrackedSymbol(sym);
      await refreshTrackedSymbols();
      if (activeSymbol === sym) {
        setActiveSymbol('BTCUSDT');
      }
      onSymbolsUpdated?.();
    } catch (err) {
      setSymbolFeedback(err instanceof ApiClientError ? err.message : String(err));
    } finally {
      setSymbolActionBusy(false);
    }
  };

  const renderStatusLabel = (st: MetricStatus) => {
    if (st === 'LIVE') {
      return (
        <span className="px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/35 text-emerald-700 dark:text-emerald-300 font-mono text-[10px] font-bold">
          {pt.statusLive}
        </span>
      );
    }
    if (st === 'CACHED') {
      return (
        <span className="px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/35 text-amber-700 dark:text-amber-300 font-mono text-[10px] font-bold">
          {pt.statusCached}
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded bg-red-500/15 border border-red-500/35 text-red-700 dark:text-red-300 font-mono text-[10px] font-bold">
        {pt.statusMissing}
      </span>
    );
  };

  const renderMetricCard = (
    title: string,
    metric: ProvenanceMetric | undefined,
    formattedPrimary: string,
    formattedSecondary?: string | null,
  ) => {
    if (!metric) return null;
    const isMissing = metric.status === 'MISSING' || metric.value === null;
    return (
      <div className="qazan-card p-4 flex flex-col justify-between gap-3">
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">{title}</span>
          {renderStatusLabel(metric.status)}
        </div>

        <div>
          <p
            className={`text-lg sm:text-xl font-bold font-mono tabular-nums ${
              isMissing
                ? 'text-red-600 dark:text-red-400'
                : 'text-slate-900 dark:text-slate-100'
            }`}
          >
            {isMissing ? pt.statusMissing : formattedPrimary}
          </p>
          {formattedSecondary && !isMissing && (
            <p className="text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400 mt-0.5">
              {metric.secondary_label ? `${metric.secondary_label}: ` : ''}
              {formattedSecondary}
            </p>
          )}
          {metric.note && (
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
              {metric.note}
            </p>
          )}
        </div>

        <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 space-y-1 text-[11px] font-mono text-slate-500 dark:text-slate-400">
          <p className="truncate" title={metric.source}>
            <span className="text-slate-400 dark:text-slate-500">{pt.metricSourceLabel}: </span>
            {metric.source}
          </p>
          <p className="tabular-nums">
            <span className="text-slate-400 dark:text-slate-500">{pt.metricUpdatedLabel}: </span>
            {fmtUtc(metric.updated_at)}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      {/* Dynamic Symbol Registry & Real-Time WebSocket Header */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 qazan-card p-4 space-y-3">
          <form onSubmit={handleAddSymbol} className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              placeholder={pt.addSymbolPlaceholder}
              className="qazan-input flex-1 text-xs font-mono uppercase"
            />
            <button
              type="submit"
              disabled={symbolActionBusy || !newSymbol.trim()}
              className="qazan-btn-gold whitespace-nowrap"
            >
              <Plus className="w-4 h-4" />
              <span>{pt.addSymbolBtn}</span>
            </button>
          </form>

          {symbolFeedback && (
            <p className="text-xs font-mono text-[#B88E14] dark:text-[#E5C76B]">{symbolFeedback}</p>
          )}

          <div className="flex flex-wrap gap-1.5">
            {trackedSymbols.map((item) => {
              const isSelected = item.symbol === activeSymbol;
              const locked = item.symbol === 'BTCUSDT' || item.symbol === 'ETHUSDT';
              return (
                <div
                  key={item.symbol}
                  className={`inline-flex items-center rounded-md border text-xs font-mono ${
                    isSelected
                      ? 'border-[#D4AF37] bg-[#D4AF37]/15 text-[#9A7209] dark:text-[#E5C76B] font-bold'
                      : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#070A10] text-slate-700 dark:text-slate-300'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setActiveSymbol(item.symbol)}
                    className="min-h-[34px] px-2.5 cursor-pointer whitespace-nowrap"
                  >
                    {item.symbol}
                  </button>
                  {!locked && (
                    <button
                      type="button"
                      onClick={() => void handleRemoveSymbol(item.symbol)}
                      disabled={symbolActionBusy}
                      aria-label={`${pt.removeSymbol} ${item.symbol}`}
                      className="min-h-[34px] px-2 border-s border-slate-200 dark:border-slate-800 text-slate-400 hover:text-red-500 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-5 qazan-card p-4 flex flex-col justify-between gap-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Radio className={`w-4 h-4 ${wsOpen ? 'text-emerald-500' : 'text-amber-500'}`} />
              <span className="text-xs font-bold">{pt.wsStreamTitle}</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold border ${
                  wsOpen
                    ? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-700 dark:text-emerald-300'
                    : 'bg-amber-500/15 border-amber-500/35 text-amber-700 dark:text-amber-300'
                }`}
              >
                {wsOpen ? pt.wsConnected : pt.wsDisconnected}
              </span>
              <button
                type="button"
                onClick={() => void loadIntelligence()}
                disabled={loading}
                aria-label={pt.refresh}
                className="min-h-[34px] px-2.5 rounded-md border border-slate-200 dark:border-slate-800 hover:border-[#D4AF37]/40 text-xs inline-flex items-center gap-1 cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 font-mono tabular-nums">
            <div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">{activeSymbol} WS Price</p>
              <p className="text-base font-bold text-slate-900 dark:text-slate-100">
                {wsTickPrice !== null
                  ? `$${fmtNumber(wsTickPrice, wsTickPrice >= 100 ? 2 : 4)}`
                  : intel?.ohlcv_summary
                    ? `$${fmtNumber(intel.ohlcv_summary.last_close, intel.ohlcv_summary.last_close >= 100 ? 2 : 4)}`
                    : '—'}
              </p>
              {wsTickChangePct !== null && (
                <p
                  className={`text-xs font-semibold ${
                    wsTickChangePct >= 0
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {wsTickChangePct >= 0 ? '+' : ''}
                  {wsTickChangePct.toFixed(2)}%
                </p>
              )}
            </div>
            <div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">WS Taker Delta</p>
              <p className="text-base font-bold text-slate-900 dark:text-slate-100">
                {wsLiveCvdBase !== null ? `${wsLiveCvdBase >= 0 ? '+' : ''}${fmtNumber(wsLiveCvdBase, 3)}` : '—'}
              </p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                Spot msgs: {wsStatus?.spot_messages_received ?? 0}
              </p>
            </div>
          </div>

          <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400 truncate">
            {pt.metricUpdatedLabel}: {fmtUtc(wsTickTime || wsStatus?.last_spot_tick_at || intel?.generated_at)}
          </p>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono"
        >
          {error}
        </div>
      )}

      {loading && !intel ? (
        <div className="qazan-card p-8 text-center text-xs text-slate-500">{pt.loading}</div>
      ) : (
        intel && (
          <>
            {/* Validated OHLCV + Derivatives + Macro Provenance Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {/* OHLCV Summary Card */}
              <div className="qazan-card p-4 flex flex-col justify-between gap-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                    {pt.ohlcvSummaryTitle} ({intel.symbol} · {intel.interval})
                  </span>
                  {renderStatusLabel(intel.ohlcv_cached_fallback ? 'CACHED' : 'LIVE')}
                </div>
                <div className="font-mono tabular-nums">
                  <p className="text-lg sm:text-xl font-bold text-slate-900 dark:text-slate-100">
                    {intel.ohlcv_summary ? `$${fmtNumber(intel.ohlcv_summary.last_close, intel.ohlcv_summary.last_close >= 100 ? 2 : 4)}` : '—'}
                  </p>
                  {intel.ohlcv_summary && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      VWAP: ${fmtNumber(intel.ohlcv_summary.vwap, 2)} · Bars: {intel.validation.candles_checked}
                    </p>
                  )}
                </div>
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 space-y-1 text-[11px] font-mono text-slate-500 dark:text-slate-400">
                  <p className="truncate" title={intel.ohlcv_source}>
                    <span className="text-slate-400 dark:text-slate-500">{pt.metricSourceLabel}: </span>
                    {intel.ohlcv_source}
                  </p>
                  <p>
                    <span className="text-slate-400 dark:text-slate-500">{pt.metricUpdatedLabel}: </span>
                    {fmtUtc(intel.ohlcv_updated_at)}
                  </p>
                </div>
              </div>

              {renderMetricCard(
                pt.volume24hTitle,
                intel.volume_24h,
                fmtCompactUsd(intel.volume_24h.value),
                intel.volume_24h.secondary_value !== null
                  ? `${fmtNumber(intel.volume_24h.secondary_value, 2)} ${intel.symbol.replace('USDT', '')}`
                  : null,
              )}

              {renderMetricCard(
                pt.openInterestTitle,
                intel.open_interest,
                `${fmtNumber(intel.open_interest.value, 2)} ${intel.open_interest.unit ?? ''}`,
                intel.open_interest.secondary_value !== null
                  ? fmtCompactUsd(intel.open_interest.secondary_value)
                  : null,
              )}

              {renderMetricCard(
                pt.fundingRateTitle,
                intel.funding_rate,
                `${intel.funding_rate.value !== null && intel.funding_rate.value >= 0 ? '+' : ''}${fmtNumber(intel.funding_rate.value, 5)}%`,
                intel.funding_rate.secondary_value !== null
                  ? `$${fmtNumber(intel.funding_rate.secondary_value, 2)}`
                  : null,
              )}

              {renderMetricCard(
                pt.cvdTitle,
                intel.cvd,
                `${intel.cvd.value !== null && intel.cvd.value >= 0 ? '+' : ''}${fmtNumber(intel.cvd.value, 3)} ${intel.cvd.unit ?? ''}`,
                intel.cvd.secondary_value !== null ? fmtCompactUsd(intel.cvd.secondary_value) : null,
              )}

              {renderMetricCard(
                pt.btcDominanceTitle,
                intel.btc_dominance,
                `${fmtNumber(intel.btc_dominance.value, 2)}%`,
                intel.btc_dominance.secondary_value !== null
                  ? `${fmtNumber(intel.btc_dominance.secondary_value, 2)}%`
                  : null,
              )}
            </div>

            {/* Validation, Missing Data Detection & Rate-Limit Audit + Connected Engine */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-7 qazan-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {intel.validation.status === 'VALID' ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                    )}
                    <h2 className="text-sm font-bold">{pt.missingDataAuditTitle}</h2>
                  </div>
                  <span className="px-2 py-0.5 rounded font-mono text-[11px] font-bold border border-[#D4AF37]/35 bg-[#D4AF37]/10 text-[#9A7209] dark:text-[#E5C76B]">
                    {intel.validation.status} · {intel.validation.integrity_score_pct}%
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono tabular-nums text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.candleGapsLabel}</p>
                    <p className="text-sm font-bold mt-0.5">{intel.validation.missing_candle_gaps}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.invalidBarsLabel}</p>
                    <p className="text-sm font-bold mt-0.5">{intel.validation.invalid_bars}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.rateLimitWeightLabel}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.rate_limit.last_binance_used_weight_1m ?? '—'}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.retriesLabel}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.rate_limit.retries_executed} / {intel.rate_limit.rate_limit_hits}
                    </p>
                  </div>
                </div>

                {intel.validation.issues.length > 0 && (
                  <ul className="space-y-1 text-xs font-mono text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-500/25 rounded-lg p-3">
                    {intel.validation.issues.map((issue, idx) => (
                      <li key={idx}>• {issue}</li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Connected Analysis Engine Output */}
              <div className="lg:col-span-5 qazan-card p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-[#D4AF37]" />
                  <h2 className="text-sm font-bold">{pt.connectedEngineTitle}</h2>
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs font-mono tabular-nums">
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.engineBiasLabel}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.connected_engine.technical_bias ?? '—'}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.enginePhaseLabel}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.connected_engine.technical_phase ?? '—'}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.probUpLabel} / {pt.probDownLabel}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.connected_engine.prob_up_pct !== null
                        ? `${intel.connected_engine.prob_up_pct}% / ${intel.connected_engine.prob_down_pct}%`
                        : '—'}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#070A10] border border-slate-200/80 dark:border-slate-800">
                    <p className="text-[11px] text-slate-500">{pt.confidence}</p>
                    <p className="text-sm font-bold mt-0.5">
                      {intel.connected_engine.prob_confidence_pct !== null
                        ? `${intel.connected_engine.prob_confidence_pct}%`
                        : '—'}
                    </p>
                  </div>
                </div>
                {intel.connected_engine.engine_note && (
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    {intel.connected_engine.engine_note}
                  </p>
                )}
              </div>
            </div>

            {/* Live Force Liquidations Stream (!forceOrder@arr) */}
            <div className="qazan-card p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#D4AF37]" />
                  <h2 className="text-sm font-bold">{pt.liquidationsFeedTitle}</h2>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500 dark:text-slate-400">
                  <Database className="w-3.5 h-3.5" />
                  <span>{intel.liquidations.source}</span>
                  {renderStatusLabel(intel.liquidations.status)}
                </div>
              </div>

              {wsLiquidations.length === 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400 py-3">
                  {pt.noLiquidationsObserved}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-start border-collapse text-xs font-mono tabular-nums">
                    <thead>
                      <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                        <th className="py-2 px-3 text-start">{pt.symbolCol}</th>
                        <th className="py-2 px-3 text-start">{pt.directionCol}</th>
                        <th className="py-2 px-3 text-end">{pt.priceCol}</th>
                        <th className="py-2 px-3 text-end">Notional USD</th>
                        <th className="py-2 px-3 text-end">{pt.timeCol}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/70">
                      {wsLiquidations.slice(0, 10).map((ev, idx) => (
                        <tr key={`${ev.symbol}-${ev.event_time}-${idx}`}>
                          <td className="py-2 px-3 font-bold">{ev.symbol}</td>
                          <td
                            className={`py-2 px-3 font-semibold ${
                              ev.side === 'BUY'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {ev.side}
                          </td>
                          <td className="py-2 px-3 text-end">${fmtNumber(ev.price, 2)}</td>
                          <td className="py-2 px-3 text-end font-semibold">{fmtCompactUsd(ev.notional_usd)}</td>
                          <td className="py-2 px-3 text-end text-slate-500">{fmtUtc(ev.received_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )
      )}
    </div>
  );
}
