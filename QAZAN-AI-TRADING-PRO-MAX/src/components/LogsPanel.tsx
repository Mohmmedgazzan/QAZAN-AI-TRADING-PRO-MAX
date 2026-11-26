import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient, ApiClientError } from '@/api/client';
import { useApp } from '@/contexts/AppContext';
import type { SystemLogEntry } from '@/types/api';

const LEVELS = ['ALL', 'WARNING', 'ERROR', 'CRITICAL'] as const;

export function LogsPanel() {
  const { t } = useApp();
  const [levelFilter, setLevelFilter] = useState<string>('ALL');
  const [logs, setLogs] = useState<SystemLogEntry[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getSystemLogs(50, levelFilter);
      setLogs(res.logs);
      setTotal(res.total);
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Unable to load system logs';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [levelFilter]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const levelLabel = (lvl: string) => {
    if (lvl === 'ALL') return t.filterAll;
    if (lvl === 'WARNING') return t.filterWarning;
    if (lvl === 'ERROR') return t.filterError;
    if (lvl === 'CRITICAL') return t.filterCritical;
    return lvl;
  };

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 text-balance">
            {t.logsHeading}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {t.logsSubheading} ({total})
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 p-1 bg-slate-100 dark:bg-[#0B0F17] border border-slate-200 dark:border-slate-800 rounded-lg">
            {LEVELS.map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setLevelFilter(lvl)}
                className={`min-h-[40px] px-3 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  levelFilter === lvl
                    ? 'bg-[#D4AF37] text-[#06080D]'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/70 dark:hover:bg-[#111722]'
                }`}
              >
                {levelLabel(lvl)}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => void loadLogs()}
            disabled={loading}
            className="qazan-btn-gold"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{t.refreshData}</span>
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 text-xs font-mono"
        >
          {error}
        </div>
      )}

      <div className="qazan-card overflow-hidden">
        {loading && logs.length === 0 ? (
          <div className="p-6 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 rounded bg-slate-100 dark:bg-slate-800 animate-pulse" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            {t.logsEmpty}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-start border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] text-slate-500 dark:text-slate-400">
                  <th className="py-3 px-4 font-semibold text-start whitespace-nowrap">{t.logsTime}</th>
                  <th className="py-3 px-4 font-semibold text-start whitespace-nowrap">{t.logsLevel}</th>
                  <th className="py-3 px-4 font-semibold text-start whitespace-nowrap">{t.logsSource}</th>
                  <th className="py-3 px-4 font-semibold text-start whitespace-nowrap">{t.logsRequestId}</th>
                  <th className="py-3 px-4 font-semibold text-start">{t.logsMessage}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {logs.map((entry) => (
                  <tr
                    key={entry.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3 px-4 font-mono tabular-nums whitespace-nowrap text-slate-600 dark:text-slate-400" dir="ltr">
                      {entry.created_at.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td
                      className={`py-3 px-4 font-mono font-semibold whitespace-nowrap ${
                        entry.level === 'ERROR' || entry.level === 'CRITICAL'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-amber-600 dark:text-amber-400'
                      }`}
                    >
                      {entry.level}
                    </td>
                    <td className="py-3 px-4 font-mono whitespace-nowrap text-slate-700 dark:text-slate-300">
                      {entry.source}
                    </td>
                    <td className="py-3 px-4 font-mono tabular-nums whitespace-nowrap text-slate-500 dark:text-slate-400">
                      {entry.request_id || '-'}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-900 dark:text-slate-100 break-words min-w-[260px]">
                      {entry.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
