import { useCallback, useEffect, useState } from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  Lock,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';
import type {
  HypothesisEvaluation,
  TradeOpportunityHistoryItem,
  TradeOpportunityResponse,
  TradeOpportunityScanResponse,
} from '@/types/platform';

function fmtPx(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toLocaleString('en-US', {
    minimumFractionDigits: value < 10 ? 4 : 2,
    maximumFractionDigits: value < 10 ? 4 : 2,
  });
}

function decisionTextTone(decision: 'LONG' | 'SHORT' | 'NO_TRADE'): string {
  if (decision === 'LONG') return 'text-emerald-600 dark:text-emerald-400';
  if (decision === 'SHORT') return 'text-red-600 dark:text-red-400';
  return 'text-[#9A7209] dark:text-[#E5C76B]';
}

function checkLabel(criterion: string, lang: 'ar' | 'en'): string {
  const labels: Record<string, { ar: string; en: string }> = {
    trend_confirmation: { ar: 'تأكيد الاتجاه (HTF + 4H)', en: 'Trend Confirmation (HTF + 4H)' },
    bos_choch: { ar: 'كسر الهيكل (BOS / CHoCH)', en: 'Structure Break (BOS / CHoCH)' },
    demand_liquidity: { ar: 'مناطق الطلب وسحب السيولة', en: 'Demand Zones & SSL Liquidity' },
    supply_liquidity: { ar: 'مناطق العرض وسحب السيولة', en: 'Supply Zones & BSL Liquidity' },
    entry_confirmation: { ar: 'تأكيد الدخول على الفريم الأصغر', en: 'LTF Entry Confirmation' },
    invalidation: { ar: 'تحديد الإلغاء ووقف الخسارة', en: 'Invalidation & Stop Loss' },
  };
  return labels[criterion]?.[lang] ?? criterion;
}

function HypothesisCard({
  hyp,
  title,
  lang,
}: {
  hyp: HypothesisEvaluation;
  title: string;
  lang: 'ar' | 'en';
}) {
  const isLong = hyp.side === 'LONG';
  return (
    <div className="qazan-card p-4 sm:p-5 space-y-3.5">
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
        <div className="space-y-0.5">
          <h3
            className={`text-sm font-bold ${
              isLong ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
            }`}
          >
            {title}
          </h3>
          <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
            {hyp.passed_count}/{hyp.total_count} ({hyp.score_pct.toFixed(0)}%)
          </p>
        </div>
        <span
          className={`text-xs font-mono font-bold ${
            hyp.eligible
              ? isLong
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-red-600 dark:text-red-400'
              : 'text-slate-500 dark:text-slate-400'
          }`}
        >
          {hyp.eligible ? 'ELIGIBLE' : 'NOT CONFIRMED'}
        </span>
      </div>

      <ul className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
        {hyp.checks.map((chk) => (
          <li key={chk.criterion} className="py-2.5 flex items-start gap-2.5">
            {chk.passed ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
            ) : (
              <XCircle className="w-4 h-4 shrink-0 text-red-500 dark:text-red-400 mt-0.5" />
            )}
            <div className="min-w-0 flex-1 space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {checkLabel(chk.criterion, lang)}
                </span>
                {chk.evidence_value && (
                  <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400 shrink-0">
                    {chk.evidence_value}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed break-words">
                {chk.detail}
              </p>
            </div>
          </li>
        ))}
      </ul>

      <div className="qazan-subpanel p-3 text-[11px] font-mono tabular-nums space-y-1">
        <div className="flex justify-between gap-2">
          <span className="text-slate-500 font-sans">Entry Zone</span>
          <span className="font-semibold">
            ${fmtPx(hyp.proposed_entry_zone_low)} – ${fmtPx(hyp.proposed_entry_zone_high)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500 font-sans">Stop / TP2</span>
          <span>
            <span className="text-red-600 dark:text-red-400">${fmtPx(hyp.proposed_stop_loss)}</span>
            {' / '}
            <span className="text-emerald-600 dark:text-emerald-400">${fmtPx(hyp.proposed_tp2)}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

export function TradeOpportunityDiscoveryView({
  onNavigate,
}: {
  onNavigate: (s: SectionId) => void;
}) {
  const { activeSymbol, setActiveSymbol, language, pt } = useApp();

  const [ltf, setLtf] = useState<'15m' | '1h' | '4h'>('1h');
  const [riskPct, setRiskPct] = useState(1.0);
  const [maxDailyLossPct, setMaxDailyLossPct] = useState(3.0);
  const [feePct, setFeePct] = useState(0.06);
  const [slippagePct, setSlippagePct] = useState(0.04);
  const [leverage, setLeverage] = useState(5.0);
  const [minNetRr, setMinNetRr] = useState(1.5);
  const [allowDuplicate, setAllowDuplicate] = useState(true);

  const [evaluation, setEvaluation] = useState<TradeOpportunityResponse | null>(null);
  const [scanResult, setScanResult] = useState<TradeOpportunityScanResponse | null>(null);
  const [history, setHistory] = useState<TradeOpportunityHistoryItem[]>([]);

  const [loadingEval, setLoadingEval] = useState(false);
  const [loadingScan, setLoadingScan] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await platformClient.getTradeOpportunityHistory(12));
    } catch {
      // ignore initial empty history error
    }
  }, []);

  const runEvaluation = useCallback(
    async (targetSymbol?: string, persist = true) => {
      setLoadingEval(true);
      setError(null);
      try {
        const res = await platformClient.evaluateTradeOpportunity({
          symbol: targetSymbol ?? activeSymbol,
          htf_timeframe: '4h',
          ltf_timeframe: ltf,
          risk_pct: riskPct,
          max_daily_loss_pct: maxDailyLossPct,
          fee_pct: feePct,
          slippage_pct: slippagePct,
          leverage,
          min_net_rr: minNetRr,
          allow_duplicate: allowDuplicate,
          persist,
        });
        setEvaluation(res);
        await loadHistory();
      } catch (err) {
        setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
      } finally {
        setLoadingEval(false);
      }
    },
    [
      activeSymbol,
      allowDuplicate,
      feePct,
      leverage,
      loadHistory,
      ltf,
      maxDailyLossPct,
      minNetRr,
      riskPct,
      slippagePct,
    ],
  );

  const runScanAll = useCallback(async () => {
    setLoadingScan(true);
    setError(null);
    try {
      const scan = await platformClient.scanTradeOpportunities({
        ltf,
        risk_pct: riskPct,
        max_daily_loss_pct: maxDailyLossPct,
        fee_pct: feePct,
        slippage_pct: slippagePct,
      });
      setScanResult(scan);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setLoadingScan(false);
    }
  }, [feePct, ltf, maxDailyLossPct, riskPct, slippagePct]);

  useEffect(() => {
    void runEvaluation(activeSymbol, false);
    void loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSymbol]);

  const gov = evaluation?.risk_governance;
  const dailyBarPct = gov
    ? Math.min(100, (gov.daily_total_loss_pct / Math.max(0.1, gov.max_daily_loss_pct)) * 100)
    : 0;

  return (
    <div className="space-y-5 min-w-0">
      {/* Execution Lock Banner */}
      <div className="qazan-subpanel px-4 py-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between text-xs">
        <div className="flex items-center gap-2 font-semibold text-[#9A7209] dark:text-[#E5C76B]">
          <Lock className="w-4 h-4 shrink-0" />
          <span>{pt.discAnalysisOnlyBanner}</span>
        </div>
        <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
          HTF 1W / 1D / 4H → LTF {ltf.toUpperCase()}
        </span>
      </div>

      {/* Governance & Risk Parameter Controls */}
      <div className="qazan-card p-4 sm:p-5 space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 text-xs">
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.engineLtfLabel}</span>
            <select
              value={ltf}
              onChange={(e) => setLtf(e.target.value as '15m' | '1h' | '4h')}
              className="qazan-input font-mono"
            >
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.riskPercent}</span>
            <input
              type="number"
              step="0.1"
              min="0.1"
              max="5"
              value={riskPct}
              onChange={(e) => setRiskPct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.discMaxDailyLossLabel}</span>
            <input
              type="number"
              step="0.5"
              min="0.5"
              max="15"
              value={maxDailyLossPct}
              onChange={(e) => setMaxDailyLossPct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.discFeeSideLabel}</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="0.5"
              value={feePct}
              onChange={(e) => setFeePct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.discSlippageLabel}</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="0.5"
              value={slippagePct}
              onChange={(e) => setSlippagePct(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.leverage}</span>
            <input
              type="number"
              step="1"
              min="1"
              max="50"
              value={leverage}
              onChange={(e) => setLeverage(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-500 dark:text-slate-400">{pt.discMinNetRrLabel}</span>
            <input
              type="number"
              step="0.1"
              min="0.5"
              max="5"
              value={minNetRr}
              onChange={(e) => setMinNetRr(Number(e.target.value))}
              className="qazan-input font-mono tabular-nums"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <label className="inline-flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={allowDuplicate}
              onChange={(e) => setAllowDuplicate(e.target.checked)}
              className="w-4 h-4 accent-[#D4AF37]"
            />
            <span>{pt.discAllowDuplicateLabel}</span>
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void runEvaluation(activeSymbol, true)}
              disabled={loadingEval}
              className="qazan-btn-gold"
            >
              <RefreshCw className={`w-4 h-4 ${loadingEval ? 'animate-spin' : ''}`} />
              <span>{pt.discEvaluateBtn} ({activeSymbol})</span>
            </button>
            <button
              type="button"
              onClick={() => void runScanAll()}
              disabled={loadingScan}
              className="qazan-btn-secondary border-[#D4AF37]/40 text-[#9A7209] dark:text-[#E5C76B]"
            >
              <Search className={`w-4 h-4 ${loadingScan ? 'animate-spin' : ''}`} />
              <span>{pt.discScanAllBtn}</span>
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {evaluation && gov && (
        <>
          {/* Final Decision & Structured Execution Plan */}
          <div className="qazan-card-gold p-5 space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-800 pb-3.5">
              <div className="space-y-1">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {pt.discDecisionLabel} · {evaluation.symbol} (${fmtPx(evaluation.last_price)})
                </p>
                <div className="flex items-center gap-2.5">
                  {evaluation.decision === 'NO_TRADE' ? (
                    <ShieldAlert className="w-6 h-6 text-[#9A7209] dark:text-[#E5C76B]" />
                  ) : (
                    <ShieldCheck
                      className={`w-6 h-6 ${decisionTextTone(evaluation.decision)}`}
                    />
                  )}
                  <h2 className={`text-xl sm:text-2xl font-mono font-bold ${decisionTextTone(evaluation.decision)}`}>
                    {evaluation.decision === 'NO_TRADE' ? pt.discNoTrade : evaluation.decision}
                  </h2>
                </div>
              </div>

              <div className="text-xs font-mono tabular-nums space-y-1 sm:text-end">
                <p className="text-slate-500 dark:text-slate-400">
                  {String(evaluation.market_context.htf_bias ?? '—')} · {String(evaluation.market_context.market_regime ?? '—')}
                </p>
                <p className="font-semibold text-[#9A7209] dark:text-[#E5C76B]">
                  {evaluation.risk_reward_summary}
                </p>
              </div>
            </div>

            {evaluation.decision === 'NO_TRADE' && gov.rejection_reasons.length > 0 && (
              <div className="p-3.5 rounded-lg border border-amber-500/30 bg-amber-50/70 dark:bg-amber-950/20 text-xs space-y-1">
                <p className="font-semibold text-[#9A7209] dark:text-[#E5C76B]">{pt.discRejectionTitle}:</p>
                <ul className="list-disc list-inside space-y-0.5 text-slate-700 dark:text-slate-300 font-mono text-[11px]">
                  {gov.rejection_reasons.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 pt-1">
                  {pt.discTheoreticalPreview}
                </p>
              </div>
            )}

            {/* Entry Zone / SL / TP1 / TP2 / TP3 / Position Size / Friction */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-xs font-mono tabular-nums">
              <div className="qazan-subpanel p-3 col-span-2 sm:col-span-2">
                <p className="text-slate-500 font-sans">{pt.discEntryZone}</p>
                <p className="mt-1 font-bold">
                  ${fmtPx(evaluation.entry_zone_low)} – ${fmtPx(evaluation.entry_zone_high)}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">Mid: ${fmtPx(evaluation.entry_price)}</p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discStopLoss}</p>
                <p className="mt-1 font-bold text-red-600 dark:text-red-400">${fmtPx(evaluation.stop_loss)}</p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discTp1}</p>
                <p className="mt-1 font-bold text-emerald-600 dark:text-emerald-400">${fmtPx(evaluation.tp1)}</p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discTp2}</p>
                <p className="mt-1 font-bold text-emerald-600 dark:text-emerald-400">${fmtPx(evaluation.tp2)}</p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discTp3}</p>
                <p className="mt-1 font-bold text-emerald-600 dark:text-emerald-400">${fmtPx(evaluation.tp3)}</p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discNetRr}</p>
                <p className="mt-1 font-bold text-[#9A7209] dark:text-[#E5C76B]">
                  {gov.net_rr_tp2 != null ? `${gov.net_rr_tp2.toFixed(2)}R` : '—'}
                </p>
                <p className="text-[10px] text-slate-500">
                  Gross: {gov.gross_rr_tp2 != null ? `${gov.gross_rr_tp2.toFixed(2)}R` : '—'}
                </p>
              </div>
              <div className="qazan-subpanel p-3">
                <p className="text-slate-500 font-sans">{pt.discPosSize}</p>
                <p className="mt-1 font-bold">
                  {gov.position_size_units != null ? gov.position_size_units.toFixed(4) : '0.0000'}
                </p>
                <p className="text-[10px] text-slate-500">
                  ${gov.position_notional_usdt?.toLocaleString('en-US') ?? '0'}
                </p>
              </div>
            </div>

            {/* Friction & Invalidation Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="qazan-subpanel p-3.5 space-y-1">
                <p className="text-slate-500 dark:text-slate-400 font-medium">{pt.discInvalidationTitle}</p>
                <p className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                  ${fmtPx(evaluation.invalidation_level)} — {evaluation.invalidation_rule}
                </p>
              </div>
              <div className="qazan-subpanel p-3.5 flex flex-wrap items-center justify-between gap-2 font-mono tabular-nums">
                <div>
                  <p className="text-slate-500 dark:text-slate-400 font-sans">{pt.discFrictionCost}</p>
                  <p className="mt-0.5 font-bold">
                    ${gov.total_friction_usdt.toFixed(2)} (Fee ${gov.estimated_fee_usdt.toFixed(2)} + Slip $
                    {gov.estimated_slippage_usdt.toFixed(2)})
                  </p>
                </div>
                <div className="text-end">
                  <p className="text-slate-500 dark:text-slate-400 font-sans">{pt.discMarginReq}</p>
                  <p className="mt-0.5 font-bold">${gov.required_margin_usdt?.toFixed(2) ?? '0.00'}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Dual Hypothesis Comparison: LONG vs SHORT */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <HypothesisCard
              hyp={evaluation.long_hypothesis}
              title={pt.discLongHypothesis}
              lang={language}
            />
            <HypothesisCard
              hyp={evaluation.short_hypothesis}
              title={pt.discShortHypothesis}
              lang={language}
            />
          </div>

          {/* Daily Loss Governance Circuit Breaker */}
          <div className="qazan-card p-4 sm:p-5 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <AlertOctagon
                  className={`w-4 h-4 ${
                    gov.daily_limit_breached
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-[#9A7209] dark:text-[#E5C76B]'
                  }`}
                />
                <h3 className="text-sm font-semibold">{pt.discDailyLossMeter}</h3>
              </div>
              <span className="font-mono text-xs tabular-nums font-bold">
                {gov.daily_total_loss_pct.toFixed(2)}% / {gov.max_daily_loss_pct.toFixed(2)}%
              </span>
            </div>

            <div className="h-2.5 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden" dir="ltr">
              <div
                className={`h-full transition-all ${
                  gov.daily_limit_breached ? 'bg-red-500' : 'bg-[#D4AF37]'
                }`}
                style={{ width: `${dailyBarPct}%` }}
              />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono tabular-nums pt-1">
              <div>
                <p className="text-slate-500 font-sans">{pt.discDailyUsedLabel}</p>
                <p className="font-semibold">{gov.daily_total_loss_pct.toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-slate-500 font-sans">{pt.discDailyRemainingLabel}</p>
                <p className="font-semibold text-emerald-600 dark:text-emerald-400">
                  {gov.daily_remaining_risk_pct.toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-slate-500 font-sans">{pt.discConfirmationGate}</p>
                <p
                  className={`font-bold ${
                    gov.confirmation_gate_passed
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-[#9A7209] dark:text-[#E5C76B]'
                  }`}
                >
                  {gov.confirmation_gate_passed ? 'OPEN' : 'LOCKED'}
                </p>
              </div>
              <div>
                <p className="text-slate-500 font-sans">{pt.discDeduplicationLabel}</p>
                <p className="font-semibold truncate">{gov.duplicate_fingerprint ?? '—'}</p>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Multi-Pair Dual-Hypothesis Scan Summary */}
      {scanResult && (
        <div className="qazan-card overflow-hidden min-w-0">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between text-sm font-semibold">
            <span>{pt.discScanSummaryTitle}</span>
            <span className="font-mono text-xs text-slate-500 tabular-nums">
              {scanResult.items.length} pairs · LTF {scanResult.ltf_timeframe}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-start">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                  <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                  <th className="py-2.5 px-4 text-end">{pt.priceCol}</th>
                  <th className="py-2.5 px-4 text-center">LONG</th>
                  <th className="py-2.5 px-4 text-center">SHORT</th>
                  <th className="py-2.5 px-4 text-start">{pt.discDecisionLabel}</th>
                  <th className="py-2.5 px-4 text-end">{pt.discNetRr}</th>
                  <th className="py-2.5 px-4 text-end">{pt.actionCol}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 font-mono tabular-nums">
                {scanResult.items.map((item) => (
                  <tr key={item.symbol} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-2.5 px-4 font-bold">{item.symbol}</td>
                    <td className="py-2.5 px-4 text-end">${fmtPx(item.last_price)}</td>
                    <td className="py-2.5 px-4 text-center text-emerald-600 dark:text-emerald-400">
                      {item.long_hypothesis.passed_count}/5
                    </td>
                    <td className="py-2.5 px-4 text-center text-red-600 dark:text-red-400">
                      {item.short_hypothesis.passed_count}/5
                    </td>
                    <td className={`py-2.5 px-4 font-bold ${decisionTextTone(item.decision)}`}>
                      {item.decision}
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      {item.risk_governance.net_rr_tp2 != null
                        ? `${item.risk_governance.net_rr_tp2.toFixed(2)}R`
                        : '—'}
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setActiveSymbol(item.symbol);
                            void runEvaluation(item.symbol, false);
                          }}
                          className="min-h-[32px] px-2.5 rounded-md bg-slate-100 dark:bg-[#111722] hover:bg-slate-200 dark:hover:bg-slate-800 font-sans text-xs font-medium cursor-pointer"
                        >
                          Inspect
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setActiveSymbol(item.symbol);
                            onNavigate('live-charts');
                          }}
                          className="min-h-[32px] px-2.5 rounded-md bg-[#D4AF37]/15 border border-[#D4AF37]/30 font-sans text-xs font-semibold text-[#9A7209] dark:text-[#E5C76B] cursor-pointer"
                        >
                          {pt.openInCharts}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SQLite Saved Opportunity History */}
      {history.length > 0 && (
        <div className="qazan-card overflow-hidden min-w-0">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 text-sm font-semibold">
            {pt.discHistoryTitle}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-start">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500">
                  <th className="py-2.5 px-4 text-start">ID</th>
                  <th className="py-2.5 px-4 text-start">{pt.symbolCol}</th>
                  <th className="py-2.5 px-4 text-start">{pt.discDecisionLabel}</th>
                  <th className="py-2.5 px-4 text-center">L / S</th>
                  <th className="py-2.5 px-4 text-end">Entry / SL / TP2</th>
                  <th className="py-2.5 px-4 text-end">{pt.discNetRr}</th>
                  <th className="py-2.5 px-4 text-end">{pt.timeCol}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 font-mono tabular-nums">
                {history.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-50 dark:hover:bg-[#111722]/60">
                    <td className="py-2.5 px-4 text-slate-500">#{h.id}</td>
                    <td className="py-2.5 px-4 font-bold">
                      {h.symbol} ({h.timeframe}/{h.ltf_timeframe})
                    </td>
                    <td className={`py-2.5 px-4 font-bold ${decisionTextTone(h.decision)}`}>
                      {h.decision}
                      {h.is_duplicate ? ' (DUP)' : ''}
                    </td>
                    <td className="py-2.5 px-4 text-center">
                      {h.long_passed}/5 · {h.short_passed}/5
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      ${fmtPx(h.entry_price)} / ${fmtPx(h.stop_loss)} / ${fmtPx(h.tp2)}
                    </td>
                    <td className="py-2.5 px-4 text-end">
                      {h.net_rr != null ? `${h.net_rr.toFixed(2)}R` : '—'}
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
