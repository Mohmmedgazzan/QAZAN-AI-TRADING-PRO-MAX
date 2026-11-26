import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  ExternalLink,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { MacroCategory, MacroEventItem, MacroNewsResponse } from '@/types/platform';

const MACRO_CATEGORIES: MacroCategory[] = [
  'ALL',
  'FED_DECISION',
  'INTEREST_RATE',
  'CPI',
  'PPI',
  'NFP',
  'UNEMPLOYMENT',
  'CENTRAL_BANK_SPEECH',
  'OTHER_MACRO',
];

function fmtUtcDisplay(isoStr: string | null | undefined): string {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return isoStr.slice(0, 16).replace('T', ' ');
  return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
}

function fmtCountdown(minutesUntil: number, isAr: boolean): string {
  if (minutesUntil < 0) {
    const absMins = Math.abs(minutesUntil);
    if (absMins < 60) return isAr ? `منذ ${absMins} د` : `${absMins}m ago`;
    const hrs = Math.floor(absMins / 60);
    if (hrs < 48) return isAr ? `منذ ${hrs} س` : `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return isAr ? `منذ ${days} ي` : `${days}d ago`;
  }
  if (minutesUntil === 0) return isAr ? 'الآن' : 'Now';
  const days = Math.floor(minutesUntil / 1440);
  const hours = Math.floor((minutesUntil % 1440) / 60);
  const mins = minutesUntil % 60;
  if (days > 0) return isAr ? `بعد ${days} ي ${hours} س` : `in ${days}d ${hours}h`;
  if (hours > 0) return isAr ? `بعد ${hours} س ${mins} د` : `in ${hours}h ${mins}m`;
  return isAr ? `بعد ${mins} د` : `in ${mins}m`;
}

export function EconomicCalendarSection() {
  const { pt, t, language } = useApp();
  const isAr = language === 'ar';

  const [category, setCategory] = useState<MacroCategory>('ALL');
  const [impact, setImpact] = useState('ALL');
  const [country, setCountry] = useState('ALL');
  const [search, setSearch] = useState('');
  const [warningHours, setWarningHours] = useState(24);
  const [includeReleased, setIncludeReleased] = useState(true);
  const [data, setData] = useState<MacroNewsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (forceRefresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await platformClient.getMacroNews({
          category,
          impact,
          country,
          search,
          warning_hours: warningHours,
          include_released: includeReleased,
          refresh: forceRefresh,
        });
        setData(res);
      } catch (err) {
        setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
      } finally {
        setLoading(false);
      }
    },
    [category, impact, country, search, warningHours, includeReleased],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const warningBannerStyle =
    data?.active_warning_level === 'CRITICAL'
      ? 'border-red-500/45 bg-red-50 dark:bg-red-950/35 text-red-900 dark:text-red-100'
      : data?.active_warning_level === 'ELEVATED'
        ? 'border-amber-500/45 bg-amber-50 dark:bg-amber-950/30 text-amber-950 dark:text-amber-100'
        : data?.active_warning_level === 'WATCH'
          ? 'border-[#D4AF37]/45 bg-amber-50/70 dark:bg-[#17140A] text-slate-900 dark:text-amber-100'
          : 'border-emerald-500/30 bg-emerald-50/60 dark:bg-emerald-950/20 text-emerald-900 dark:text-emerald-100';

  const warningHeadline =
    data?.active_warning_level === 'CRITICAL'
      ? pt.macroWarningCritical
      : data?.active_warning_level === 'ELEVATED'
        ? pt.macroWarningElevated
        : data?.active_warning_level === 'WATCH'
          ? pt.macroWarningWatch
          : pt.macroWarningClear;

  const renderImpactText = (ev: MacroEventItem) => {
    const low = ev.impact.toLowerCase();
    if (low === 'high') {
      return (
        <span className="inline-flex items-center gap-1 font-mono font-bold text-red-600 dark:text-red-400">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>{isAr ? 'عالٍ · High' : 'High'}</span>
        </span>
      );
    }
    if (low === 'medium') {
      return (
        <span className="font-mono font-semibold text-amber-600 dark:text-amber-400">
          {isAr ? 'متوسط · Medium' : 'Medium'}
        </span>
      );
    }
    return (
      <span className="font-mono text-slate-500 dark:text-slate-400">
        {isAr ? 'منخفض · Low' : 'Low'}
      </span>
    );
  };

  return (
    <section className="space-y-5">
      {/* Page Header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1 max-w-3xl">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections['economic-calendar']}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            {pt.calendarSubtitle}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            aria-label={pt.macroWarningWindowLabel}
            value={warningHours}
            onChange={(e) => setWarningHours(Number(e.target.value))}
            className="min-h-[42px] px-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17]"
          >
            <option value={6}>{pt.macroWarningWindowLabel}: 6h</option>
            <option value={24}>{pt.macroWarningWindowLabel}: 24h</option>
            <option value={72}>{pt.macroWarningWindowLabel}: 72h</option>
            <option value={168}>{pt.macroWarningWindowLabel}: 7d</option>
          </select>

          <button
            type="button"
            onClick={() => void load(true)}
            disabled={loading}
            className="qazan-btn-gold whitespace-nowrap shrink-0"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{pt.refresh}</span>
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-500/35 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono"
        >
          {error}
        </div>
      )}

      {/* Pre-Event High-Impact Volatility Warning Banner */}
      {data && (
        <div
          role="status"
          className={`p-4 rounded-xl border space-y-2.5 ${warningBannerStyle}`}
        >
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 font-semibold text-sm">
              {data.active_warning_level === 'CLEAR' ? (
                <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
              )}
              <span>{warningHeadline}</span>
            </div>

            {data.next_high_impact_event && (
              <span className="text-xs font-mono tabular-nums text-slate-700 dark:text-slate-300">
                {data.next_high_impact_event.country} · {data.next_high_impact_event.title} ·{' '}
                {fmtCountdown(data.next_high_impact_event.minutes_until, isAr)}
              </span>
            )}
          </div>

          {data.high_impact_warnings.length > 0 && (
            <div className="divide-y divide-black/10 dark:divide-white/10 border-t border-black/10 dark:border-white/10 pt-2">
              {data.high_impact_warnings.slice(0, 5).map((w) => (
                <div
                  key={w.event_id}
                  className="py-1.5 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between text-xs"
                >
                  <span className="font-medium">
                    {isAr ? w.warning_text_ar : w.warning_text_en}
                  </span>
                  <span className="font-mono tabular-nums text-[11px] opacity-80 whitespace-nowrap" dir="ltr">
                    {w.severity} · {fmtUtcDisplay(w.event_date)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Official Central Bank & US BLS Macro Snapshot Strip (4 KPI Cards) */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="qazan-card-gold p-4 space-y-1">
            <p className="text-xs text-slate-500 dark:text-slate-400">{pt.macroFedRateLabel}</p>
            <p className="text-base sm:text-lg font-mono font-bold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
              {data.official_snapshot.fed_target_rate || '—'}
            </p>
            <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
              {pt.macroNextFomcLabel}: {fmtUtcDisplay(data.official_snapshot.next_fomc_date)}
            </p>
          </div>

          <div className="qazan-card p-4 space-y-1">
            <p className="text-xs text-slate-500 dark:text-slate-400">{pt.macroCpiOfficialLabel}</p>
            <p className="text-base sm:text-lg font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">
              {data.official_snapshot.us_cpi_latest || '—'}
            </p>
            <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
              {pt.previousCol}: {data.official_snapshot.us_cpi_previous || '—'} · {pt.macroNextReleaseLabel}:{' '}
              {data.official_snapshot.us_cpi_next_date?.slice(0, 10) || '—'}
            </p>
          </div>

          <div className="qazan-card p-4 space-y-1">
            <p className="text-xs text-slate-500 dark:text-slate-400">{pt.macroPpiOfficialLabel}</p>
            <p className="text-base sm:text-lg font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">
              {data.official_snapshot.us_ppi_latest || '—'}
            </p>
            <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
              {pt.previousCol}: {data.official_snapshot.us_ppi_previous || '—'} · {pt.macroNextReleaseLabel}:{' '}
              {data.official_snapshot.us_ppi_next_date?.slice(0, 10) || '—'}
            </p>
          </div>

          <div className="qazan-card p-4 space-y-1">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {pt.macroNfpOfficialLabel} / {pt.macroUnempOfficialLabel}
            </p>
            <p className="text-base sm:text-lg font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">
              {data.official_snapshot.us_nfp_latest || '—'} ·{' '}
              {data.official_snapshot.us_unemployment_latest || '—'}
            </p>
            <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
              {pt.macroNextReleaseLabel}: {data.official_snapshot.us_nfp_next_date?.slice(0, 10) || '—'}
            </p>
          </div>
        </div>
      )}

      {/* Interactive Category Segmented Filter Tabs */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-1.5 p-1.5 rounded-xl bg-slate-100 dark:bg-[#111722] border border-slate-200 dark:border-slate-800">
          {MACRO_CATEGORIES.map((cat) => {
            const active = category === cat;
            const count = data?.category_counts?.[cat];
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`min-h-[38px] px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap shrink-0 transition-colors cursor-pointer ${
                  active
                    ? 'bg-white dark:bg-[#0B0F17] text-[#9A7209] dark:text-[#E5C76B] border border-[#D4AF37]/40 shadow-sm font-semibold'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                }`}
              >
                <span>{pt.macroCategories[cat]}</span>
                {typeof count === 'number' && (
                  <span className="ms-1.5 font-mono tabular-nums opacity-70">({count})</span>
                )}
              </button>
            );
          })}
        </div>

        {/* Secondary Filter Toolbar */}
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[200px] sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute top-1/2 -translate-y-1/2 start-3 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={pt.macroSearchPlaceholder}
                aria-label={pt.macroSearchPlaceholder}
                className="w-full min-h-[42px] ps-9 pe-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] text-slate-900 dark:text-slate-100"
              />
            </div>

            <select
              aria-label={pt.impactFilter}
              value={impact}
              onChange={(e) => setImpact(e.target.value)}
              className="min-h-[42px] px-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17]"
            >
              <option value="ALL">
                {pt.impactFilter}: {t.filterAll}
              </option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            <select
              aria-label={pt.currencyFilter}
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="min-h-[42px] px-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17]"
            >
              <option value="ALL">
                {pt.currencyFilter}: {t.filterAll}
              </option>
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
              <option value="JPY">JPY</option>
              <option value="CAD">CAD</option>
              <option value="AUD">AUD</option>
              <option value="CHF">CHF</option>
              <option value="NZD">NZD</option>
            </select>
          </div>

          <label className="inline-flex items-center gap-2 min-h-[40px] px-2 text-slate-700 dark:text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeReleased}
              onChange={(e) => setIncludeReleased(e.target.checked)}
              className="w-4 h-4 accent-[#D4AF37]"
            />
            <span className="whitespace-nowrap">{pt.macroIncludeReleasedLabel}</span>
          </label>
        </div>
      </div>

      {/* Mobile Cards (< md) */}
      <div className="grid grid-cols-1 gap-2.5 md:hidden">
        {loading && !data ? (
          <div className="qazan-card p-6 text-center text-xs text-slate-500">{pt.loading}</div>
        ) : data && data.events.length === 0 ? (
          <div className="qazan-card p-6 text-center text-xs text-slate-500">{pt.macroNoEventsFiltered}</div>
        ) : (
          data?.events.map((ev) => (
            <div
              key={ev.id}
              className={`qazan-card p-3.5 space-y-2 text-xs ${
                ev.warning_active ? 'border-amber-500/45 dark:border-[#D4AF37]/45' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-2 text-[11px] font-mono">
                <span className="font-bold text-[#9A7209] dark:text-[#E5C76B]">
                  {ev.country} · {isAr ? ev.category_label_ar : ev.category_label_en}
                </span>
                {renderImpactText(ev)}
              </div>

              <p className="font-semibold text-slate-900 dark:text-slate-100 leading-snug">{ev.title}</p>

              <div className="flex flex-wrap items-center justify-between gap-2 font-mono tabular-nums text-[11px] text-slate-500 dark:text-slate-400">
                <span dir="ltr">{fmtUtcDisplay(ev.event_date)}</span>
                <span className="inline-flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>{fmtCountdown(ev.minutes_until, isAr)}</span>
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100 dark:border-slate-800/80 font-mono tabular-nums text-[11px]">
                <div>
                  <span className="block text-slate-400">{pt.previousCol}</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">{ev.previous || '—'}</span>
                </div>
                <div>
                  <span className="block text-slate-400">{pt.forecastCol}</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">{ev.forecast || '—'}</span>
                </div>
                <div>
                  <span className="block text-slate-400">{pt.actualCol}</span>
                  <span className="font-bold text-emerald-700 dark:text-emerald-400">{ev.actual || '—'}</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400 pt-1">
                <span className="truncate">{ev.source_name}</span>
                <a
                  href={ev.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[#9A7209] dark:text-[#E5C76B] hover:underline shrink-0"
                >
                  <span>{isAr ? 'المصدر' : 'Source'}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Desktop High-Density Data Table (>= md) */}
      <div className="hidden md:block qazan-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-start border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500 dark:text-slate-400">
                <th className="py-3 px-4 text-start whitespace-nowrap">{pt.timeCol}</th>
                <th className="py-3 px-3 text-start whitespace-nowrap">{pt.currencyCol}</th>
                <th className="py-3 px-3 text-start whitespace-nowrap">{pt.impactCol}</th>
                <th className="py-3 px-4 text-start">{pt.eventTitleCol}</th>
                <th className="py-3 px-3 text-end whitespace-nowrap">{pt.previousCol}</th>
                <th className="py-3 px-3 text-end whitespace-nowrap">{pt.forecastCol}</th>
                <th className="py-3 px-3 text-end whitespace-nowrap">{pt.actualCol}</th>
                <th className="py-3 px-4 text-start whitespace-nowrap">{pt.macroSourceCol}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {loading && !data ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {pt.loading}
                  </td>
                </tr>
              ) : data && data.events.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {pt.macroNoEventsFiltered}
                  </td>
                </tr>
              ) : (
                data?.events.map((ev) => (
                  <tr
                    key={ev.id}
                    className={`hover:bg-slate-50 dark:hover:bg-[#111722]/60 ${
                      ev.warning_active ? 'bg-amber-50/40 dark:bg-amber-950/15' : ''
                    }`}
                  >
                    <td className="py-3 px-4 font-mono tabular-nums whitespace-nowrap">
                      <div className="text-slate-700 dark:text-slate-200" dir="ltr">
                        {fmtUtcDisplay(ev.event_date)}
                      </div>
                      <div
                        className={`text-[11px] ${
                          ev.event_status === 'IMMINENT'
                            ? 'text-red-600 dark:text-red-400 font-semibold'
                            : ev.event_status === 'UPCOMING'
                              ? 'text-[#9A7209] dark:text-[#E5C76B]'
                              : 'text-slate-400'
                        }`}
                      >
                        {fmtCountdown(ev.minutes_until, isAr)} ·{' '}
                        {ev.event_status === 'IMMINENT'
                          ? pt.macroStatusImminent
                          : ev.event_status === 'UPCOMING'
                            ? pt.macroStatusUpcoming
                            : pt.macroStatusReleased}
                      </div>
                    </td>
                    <td className="py-3 px-3 font-mono font-bold text-[#9A7209] dark:text-[#E5C76B] whitespace-nowrap">
                      {ev.country}
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">{renderImpactText(ev)}</td>
                    <td className="py-3 px-4 max-w-md">
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{ev.title}</div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                        {isAr ? ev.category_label_ar : ev.category_label_en}
                      </div>
                    </td>
                    <td className="py-3 px-3 text-end font-mono tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                      {ev.previous || '—'}
                    </td>
                    <td className="py-3 px-3 text-end font-mono tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                      {ev.forecast || '—'}
                    </td>
                    <td className="py-3 px-3 text-end font-mono tabular-nums font-bold text-emerald-700 dark:text-emerald-400 whitespace-nowrap">
                      {ev.actual || '—'}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <a
                        href={ev.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-600 dark:text-slate-400 hover:text-[#9A7209] dark:hover:text-[#E5C76B]"
                      >
                        <span className="truncate max-w-[160px]">{ev.source_name}</span>
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Official Sources & Integrity Verification Panel */}
      {data && (
        <div className="qazan-card p-4 space-y-3 text-xs">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">{pt.macroSourcesTitle}</h2>
            <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
              {data.total} {isAr ? 'حدثاً' : 'events'} · {isAr ? 'أحداث مختلقة: 0' : 'Fabricated: 0'}
            </span>
          </div>

          <p className="text-[11px] text-slate-600 dark:text-slate-400">{pt.macroZeroFabricationNote}</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5 pt-1">
            {data.source_statuses.map((src) => (
              <div
                key={src.source_id}
                className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 space-y-1"
              >
                <div className="flex items-center justify-between gap-2 font-mono text-[11px]">
                  <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                    {src.source_name}
                  </span>
                  <span
                    className={`font-bold shrink-0 ${
                      src.status === 'LIVE'
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : src.status === 'CACHED'
                          ? 'text-amber-600 dark:text-amber-400'
                          : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {src.status}
                  </span>
                </div>
                <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                  {src.events_count} {isAr ? 'سجل' : 'items'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
