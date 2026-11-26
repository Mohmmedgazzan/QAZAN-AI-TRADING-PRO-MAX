import React, { useEffect, useState } from 'react';
import { Archive, CheckCircle2, Download, Lock, RotateCcw, ShieldCheck, Smartphone, Wifi, WifiOff } from 'lucide-react';
import { ApiClientError, apiClient } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { LogsPanel } from '@/components/LogsPanel';
import { SystemHealthPanel } from '@/components/SystemHealthPanel';
import { useApp } from '@/contexts/AppContext';
import { validateSecureBackendOrigin } from '@/services/nativePlatform';

export function SettingsSection() {
  const {
    pt,
    language,
    theme,
    activeSymbol,
    activeInterval,
    isOnline,
    isNative,
    runtimePlatform,
    backendOrigin,
    setLanguage,
    setTheme,
    setActiveSymbol,
    setActiveInterval,
    updateBackendOrigin,
    resetBackendOrigin,
    recheckConnectivity,
  } = useApp();

  const [subtab, setSubtab] = useState<'prefs' | 'health' | 'logs'>('prefs');
  const [defaultRiskPct, setDefaultRiskPct] = useState(1.0);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logsToken, setLogsToken] = useState(0);

  const [originDraft, setOriginDraft] = useState(backendOrigin);
  const [connFeedback, setConnFeedback] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [testingConn, setTestingConn] = useState(false);
  const [backupMeta, setBackupMeta] = useState<{
    filename: string;
    size_bytes: number;
    updated_at: string;
  } | null>(null);
  const [refreshingZip, setRefreshingZip] = useState(false);

  const loadBackupInfo = async (refresh = false) => {
    setRefreshingZip(true);
    try {
      const resp = await fetch(`/download/backup-info${refresh ? '?refresh=1' : ''}`);
      if (resp.ok) {
        const info = (await resp.json()) as {
          filename: string;
          size_bytes: number;
          updated_at: string;
        };
        setBackupMeta(info);
      }
    } catch {
      // Ignore if offline or native WebView without local gateway
    } finally {
      setRefreshingZip(false);
    }
  };

  useEffect(() => {
    void loadBackupInfo(false);
  }, []);

  useEffect(() => {
    setOriginDraft(backendOrigin);
  }, [backendOrigin]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await platformClient.getSettings();
        setDefaultRiskPct(res.default_risk_pct);
      } catch {
        // use local defaults when offline
      }
    })();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(false);
    setError(null);
    try {
      await platformClient.saveSettings({
        default_symbol: activeSymbol,
        default_interval: activeInterval,
        default_risk_pct: defaultRiskPct,
        language,
        theme,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  const handleApplyAndTestBackend = async () => {
    setConnFeedback(null);
    const check = validateSecureBackendOrigin(originDraft);
    if (!check.valid) {
      setConnFeedback({ ok: false, message: check.error || 'Invalid HTTPS URL' });
      return;
    }

    setTestingConn(true);
    try {
      const normalized = await updateBackendOrigin(check.normalized);
      await recheckConnectivity();

      const targetHealthUrl = isNative
        ? `${normalized}/api/v1/health`
        : `${apiClient.getBaseUrl()}/health`;
      const started = performance.now();
      const resp = await fetch(targetHealthUrl);
      const latencyMs = Math.round(performance.now() - started);

      if (!resp.ok) {
        setConnFeedback({
          ok: false,
          message: `HTTP ${resp.status} (${normalized})`,
        });
        return;
      }
      const data = (await resp.json()) as { version?: string; status?: string };
      setConnFeedback({
        ok: true,
        message: `${pt.connectionSuccessLabel} · ${data.version ?? 'OK'} (${latencyMs}ms)`,
      });
    } catch (err) {
      setConnFeedback({
        ok: false,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setTestingConn(false);
    }
  };

  const handleResetBackend = async () => {
    const def = await resetBackendOrigin();
    setOriginDraft(def);
    setConnFeedback({ ok: true, message: def });
  };

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {pt.sections.settings}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.settingsSubtitle}</p>
        </div>

        <div className="flex items-center gap-1 p-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B0F17] overflow-x-auto">
          <button
            type="button"
            onClick={() => setSubtab('prefs')}
            className={`min-h-[40px] px-3 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer ${
              subtab === 'prefs'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {pt.preferencesSubtab}
          </button>
          <button
            type="button"
            onClick={() => setSubtab('health')}
            className={`min-h-[40px] px-3 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer ${
              subtab === 'health'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {pt.systemHealthSubtab}
          </button>
          <button
            type="button"
            onClick={() => setSubtab('logs')}
            className={`min-h-[40px] px-3 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer ${
              subtab === 'logs'
                ? 'bg-[#D4AF37] text-[#06080D]'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            {pt.errorLogsSubtab}
          </button>
        </div>
      </div>

      {subtab === 'prefs' && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          <form onSubmit={(e) => void handleSave(e)} className="xl:col-span-7 qazan-card p-5 space-y-4 text-xs">
            {error && (
              <div role="alert" className="p-3 rounded-lg border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 font-mono">
                {error}
              </div>
            )}
            {saved && (
              <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{pt.settingsSaved}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="space-y-1.5">
                <span className="block text-slate-500 dark:text-slate-400">{pt.defaultSymbol}</span>
                <select
                  value={activeSymbol}
                  onChange={(e) => setActiveSymbol(e.target.value)}
                  className="qazan-input font-mono"
                >
                  {['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT'].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="block text-slate-500 dark:text-slate-400">{pt.defaultTimeframe}</span>
                <select
                  value={activeInterval}
                  onChange={(e) => setActiveInterval(e.target.value)}
                  className="qazan-input font-mono"
                >
                  {['15m', '1h', '4h', '1d'].map((tf) => (
                    <option key={tf} value={tf}>{tf}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="block text-slate-500 dark:text-slate-400">{pt.defaultRiskPct}</span>
                <input
                  type="number"
                  step="0.1"
                  value={defaultRiskPct}
                  onChange={(e) => setDefaultRiskPct(Number(e.target.value))}
                  className="qazan-input font-mono tabular-nums"
                />
              </label>

              <label className="space-y-1.5">
                <span className="block text-slate-500 dark:text-slate-400">{pt.languageLabel}</span>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as 'ar' | 'en')}
                  className="qazan-input"
                >
                  <option value="ar">العربية (RTL)</option>
                  <option value="en">English (LTR)</option>
                </select>
              </label>

              <label className="space-y-1.5 sm:col-span-2">
                <span className="block text-slate-500 dark:text-slate-400">{pt.themeLabel}</span>
                <select
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as 'dark' | 'light')}
                  className="qazan-input"
                >
                  <option value="dark">Dark Institutional Gold</option>
                  <option value="light">Light Mode</option>
                </select>
              </label>
            </div>

            <button type="submit" className="qazan-btn-gold">
              {pt.saveSettings}
            </button>
          </form>

          {/* Phase 9: Secure Android Backend & Native Persistence Panel */}
          <div className="xl:col-span-5 qazan-card-gold p-5 space-y-4 text-xs">
            <div className="flex items-start gap-2.5">
              <div className="w-9 h-9 rounded-lg border border-[#D4AF37]/30 bg-[#D4AF37]/10 flex items-center justify-center shrink-0">
                <Smartphone className="w-4 h-4 text-[#B88E14] dark:text-[#D4AF37]" />
              </div>
              <div className="space-y-0.5 min-w-0">
                <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  {pt.mobileBackendTitle}
                </h2>
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  {pt.mobileBackendSubtitle}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <div className="qazan-subpanel p-3 space-y-1">
                <span className="block text-[11px] text-slate-500 dark:text-slate-400">{pt.platformModeLabel}</span>
                <span className="block font-mono font-bold text-slate-900 dark:text-slate-100 uppercase">
                  {isNative ? `CAPACITOR (${runtimePlatform})` : 'WEB TERMINAL'}
                </span>
              </div>
              <div className="qazan-subpanel p-3 space-y-1">
                <span className="block text-[11px] text-slate-500 dark:text-slate-400">{pt.networkStatusLabel}</span>
                <span
                  className={`inline-flex items-center gap-1.5 font-semibold ${
                    isOnline ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'
                  }`}
                >
                  {isOnline ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
                  {isOnline ? pt.onlineStatus : pt.offlineStatus}
                </span>
              </div>
              <div className="qazan-subpanel p-3 space-y-1">
                <span className="block text-[11px] text-slate-500 dark:text-slate-400">{pt.storageEngineLabel}</span>
                <span className="block font-mono font-semibold text-slate-900 dark:text-slate-100">
                  {isNative ? 'Preferences + SQLite' : 'localStorage + SQLite'}
                </span>
              </div>
            </div>

            <label className="block space-y-1.5">
              <span className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300 font-semibold">
                <Lock className="w-3.5 h-3.5 text-[#D4AF37]" />
                {pt.backendUrlLabel}
              </span>
              <input
                type="url"
                dir="ltr"
                value={originDraft}
                onChange={(e) => setOriginDraft(e.target.value)}
                placeholder="https://api.your-domain.com"
                className="qazan-input font-mono text-xs"
              />
              <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                {pt.backendUrlHint}
              </span>
            </label>

            {connFeedback && (
              <div
                className={`p-3 rounded-lg border font-mono text-xs flex items-center gap-2 ${
                  connFeedback.ok
                    ? 'border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300'
                    : 'border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300'
                }`}
              >
                <ShieldCheck className="w-4 h-4 shrink-0" />
                <span className="break-all">{connFeedback.message}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleApplyAndTestBackend()}
                disabled={testingConn}
                className="qazan-btn-gold"
              >
                <ShieldCheck className="w-4 h-4" />
                <span>{pt.testSecureConnection}</span>
              </button>
              <button
                type="button"
                onClick={() => void handleResetBackend()}
                className="qazan-btn-secondary"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>{pt.resetDefaultBackend}</span>
              </button>
            </div>
          </div>

          {/* Full Project ZIP Backup Download Card */}
          <div className="xl:col-span-12 qazan-card p-5 space-y-3 text-xs">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div className="flex items-start gap-3 min-w-0">
                <div className="w-9 h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] flex items-center justify-center shrink-0">
                  <Archive className="w-4 h-4 text-[#B88E14] dark:text-[#D4AF37]" />
                </div>
                <div className="space-y-1 min-w-0">
                  <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    {pt.backupCardTitle}
                  </h2>
                  <p className="text-xs text-slate-600 dark:text-slate-400">
                    {pt.backupCardSubtitle}
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    {pt.backupIncludesNote}
                    {backupMeta && (
                      <span className="ms-2 font-mono font-semibold text-slate-700 dark:text-slate-200">
                        ({pt.backupSizeLabel}: {(backupMeta.size_bytes / (1024 * 1024)).toFixed(2)} MB)
                      </span>
                    )}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 shrink-0">
                <a
                  href="/download/qazan-project-backup.zip?refresh=1"
                  download="QAZAN-AI-TRADING-PRO-MAX-v1.0.0-open-source.zip"
                  className="qazan-btn-gold"
                >
                  <Download className="w-4 h-4" />
                  <span>{pt.downloadZipBtn}</span>
                </a>
                <button
                  type="button"
                  onClick={() => void loadBackupInfo(true)}
                  disabled={refreshingZip}
                  className="qazan-btn-secondary"
                >
                  <RotateCcw className={`w-3.5 h-3.5 ${refreshingZip ? 'animate-spin' : ''}`} />
                  <span>{pt.refreshZipBtn}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {subtab === 'health' && (
        <SystemHealthPanel onErrorRecorded={() => setLogsToken((n) => n + 1)} />
      )}

      {subtab === 'logs' && <LogsPanel key={logsToken} />}
    </section>
  );
}
