import { useCallback, useEffect, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Database, RefreshCw, Server } from 'lucide-react';
import { apiClient, ApiClientError } from '@/api/client';
import { useApp } from '@/contexts/AppContext';
import type { HealthResponse } from '@/types/api';

interface SystemHealthPanelProps {
  onErrorRecorded?: () => void;
}

export function SystemHealthPanel({ onErrorRecorded }: SystemHealthPanelProps) {
  const { t } = useApp();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [testingError, setTestingError] = useState<boolean>(false);
  const [diagnosticNotice, setDiagnosticNotice] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getHealth();
      setHealth(res);
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Unable to reach backend';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  const handleTestErrorPipeline = async () => {
    setTestingError(true);
    setDiagnosticNotice(null);
    try {
      await apiClient.triggerDiagnosticError();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setDiagnosticNotice(`${t.diagnosticResultTitle} (${err.code} · ID: ${err.requestId || '-'})`);
        onErrorRecorded?.();
        void checkHealth();
      }
    } finally {
      setTestingError(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 text-balance">
            {t.diagnosticsHeading}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {t.diagnosticsSubheading}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void handleTestErrorPipeline()}
            disabled={testingError || !health}
            className="qazan-btn-secondary disabled:opacity-50"
          >
            <AlertTriangle className="w-4 h-4 text-[#B88E14] dark:text-[#D4AF37]" />
            <span>{testingError ? t.testingErrorPipeline : t.testErrorPipeline}</span>
          </button>

          <button
            type="button"
            onClick={() => void checkHealth()}
            disabled={loading}
            className="qazan-btn-gold"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{t.runHealthCheck}</span>
          </button>
        </div>
      </div>

      {diagnosticNotice && (
        <div className="p-3.5 rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200 text-xs font-mono flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>{diagnosticNotice}</span>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 space-y-1 text-sm"
        >
          <p className="font-semibold">{t.statusOffline}</p>
          <p className="font-mono text-xs">{error}</p>
          <p className="text-xs opacity-80">{t.connectionTip}</p>
        </div>
      )}

      {loading && !health ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="h-48 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 animate-pulse" />
          <div className="h-48 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 animate-pulse" />
        </div>
      ) : health ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* FastAPI Backend Info */}
            <div className="qazan-card p-5 space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <Server className="w-5 h-5 text-[#B88E14] dark:text-[#D4AF37]" />
                  <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                    {t.backendService}
                  </h2>
                </div>
                <span
                  className={`text-xs font-semibold ${
                    health.status === 'healthy'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-amber-600 dark:text-amber-400'
                  }`}
                >
                  {health.status === 'healthy' ? t.statusHealthy : t.statusDegraded}
                </span>
              </div>

              <dl className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.pythonVersion}</dt>
                  <dd className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                    {health.python_version}
                  </dd>
                </div>
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.environmentLabel}</dt>
                  <dd className="font-mono text-slate-900 dark:text-slate-100">
                    {health.environment}
                  </dd>
                </div>
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.apiEndpointLabel}</dt>
                  <dd className="font-mono text-slate-900 dark:text-slate-100" dir="ltr">
                    {apiClient.getBaseUrl()}
                  </dd>
                </div>
              </dl>
            </div>

            {/* SQLite Health Info */}
            <div className="qazan-card p-5 space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <Database className="w-5 h-5 text-[#B88E14] dark:text-[#D4AF37]" />
                  <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                    {t.sqliteHeading}
                  </h2>
                </div>
                <span
                  className={`text-xs font-semibold ${
                    health.database.connected
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {health.database.connected ? t.sqliteConnected : t.sqliteDisconnected}
                </span>
              </div>

              <dl className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.sqliteVersion}</dt>
                  <dd className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                    {health.database.sqlite_version}
                  </dd>
                </div>
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.sqliteLatency}</dt>
                  <dd className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                    {health.database.latency_ms.toFixed(2)} ms
                  </dd>
                </div>
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{t.sqliteTables}</dt>
                  <dd className="font-mono text-xs tabular-nums text-slate-900 dark:text-slate-100 text-end">
                    system_logs ({health.database.counts.system_logs ?? 0}) · market_candles_cache (
                    {health.database.counts.market_candles_cache ?? 0})
                  </dd>
                </div>
                <div className="py-2.5 flex flex-col gap-1">
                  <dt className="text-slate-500 dark:text-slate-400 text-xs">{t.sqlitePath}</dt>
                  <dd className="font-mono text-xs text-slate-700 dark:text-slate-300 break-all" dir="ltr">
                    {health.database.database_path}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          {/* Open-Source Local ML Runtime */}
          <div className="qazan-card p-5 space-y-4">
            <div className="flex items-center gap-2.5">
              <Activity className="w-5 h-5 text-[#B88E14] dark:text-[#D4AF37]" />
              <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                {t.mlRuntimeHeading}
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {health.ml_runtime.map((pkg) => (
                <div
                  key={pkg.name}
                  className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 flex items-center justify-between gap-2"
                >
                  <div>
                    <p className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {pkg.name}
                    </p>
                    <p className="font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">
                      {pkg.version ? `v${pkg.version}` : '-'}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-semibold ${
                      pkg.installed
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {pkg.installed ? t.mlInstalled : t.mlMissing}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
