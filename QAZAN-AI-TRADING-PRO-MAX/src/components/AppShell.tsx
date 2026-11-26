import React, { useState } from 'react';
import {
  Activity,
  BarChart3,
  BrainCircuit,
  CalendarDays,
  CandlestickChart,
  Compass,
  Droplets,
  Flame,
  Globe,
  History,
  LayoutDashboard,
  Menu,
  Moon,
  Radar,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sun,
  Wallet,
  WifiOff,
  X,
} from 'lucide-react';
import { useApp } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';

interface AppShellProps {
  activeSection: SectionId;
  onSectionChange: (section: SectionId) => void;
  children: React.ReactNode;
}

const INTERVALS = ['15m', '1h', '4h', '1d'] as const;

function QazanEmblem({ className = 'w-7 h-7' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 36 36"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <rect
        x="1.5"
        y="1.5"
        width="33"
        height="33"
        rx="8"
        className="fill-[#0B0F17] stroke-[#D4AF37]"
        strokeWidth="1.4"
      />
      <path d="M12 10V26M12 13H15V21H12" className="stroke-[#10B981]" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 8V28" className="stroke-[#D4AF37]" strokeWidth="1.8" strokeLinecap="round" />
      <rect x="16.2" y="13.5" width="3.6" height="9" rx="1" className="fill-[#D4AF37]" />
      <path d="M24 11V25M21 15H24V22H21" className="stroke-[#EF4444]" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function AppShell({ activeSection, onSectionChange, children }: AppShellProps) {
  const {
    t,
    pt,
    theme,
    toggleTheme,
    toggleLanguage,
    activeSymbol,
    activeInterval,
    trackedSymbols,
    isOnline,
    recheckConnectivity,
    setActiveSymbol,
    setActiveInterval,
  } = useApp();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [retryingNet, setRetryingNet] = useState(false);

  const handleRetryConnectivity = async () => {
    setRetryingNet(true);
    try {
      await recheckConnectivity();
    } finally {
      setRetryingNet(false);
    }
  };

  const groups: Array<{
    title: string;
    items: Array<{ id: SectionId; label: string; icon: React.ComponentType<{ className?: string }> }>;
  }> = [
    {
      title: pt.navGroups.core,
      items: [
        { id: 'dashboard', label: pt.sections.dashboard, icon: LayoutDashboard },
        { id: 'market-overview', label: pt.sections['market-overview'], icon: BarChart3 },
        { id: 'live-charts', label: pt.sections['live-charts'], icon: CandlestickChart },
      ],
    },
    {
      title: pt.navGroups.quantAi,
      items: [
        { id: 'ai-analysis', label: pt.sections['ai-analysis'], icon: BrainCircuit },
        { id: 'market-structure', label: pt.sections['market-structure'], icon: Compass },
        { id: 'liquidity-analysis', label: pt.sections['liquidity-analysis'], icon: Droplets },
        { id: 'smart-money', label: pt.sections['smart-money'], icon: Activity },
        { id: 'candle-prediction', label: pt.sections['candle-prediction'], icon: Flame },
        { id: 'trade-scanner', label: pt.sections['trade-scanner'], icon: Radar },
      ],
    },
    {
      title: pt.navGroups.execution,
      items: [
        { id: 'risk-management', label: pt.sections['risk-management'], icon: ShieldCheck },
        { id: 'backtesting', label: pt.sections.backtesting, icon: History },
        { id: 'paper-trading', label: pt.sections['paper-trading'], icon: Wallet },
      ],
    },
    {
      title: pt.navGroups.system,
      items: [
        { id: 'economic-calendar', label: pt.sections['economic-calendar'], icon: CalendarDays },
        { id: 'settings', label: pt.sections.settings, icon: Settings },
      ],
    },
  ];

  const mobilePrimaryTabs: Array<{
    id: SectionId;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    { id: 'dashboard', label: pt.sections.dashboard, icon: LayoutDashboard },
    { id: 'live-charts', label: pt.sections['live-charts'], icon: CandlestickChart },
    { id: 'ai-analysis', label: pt.sections['ai-analysis'], icon: BrainCircuit },
    { id: 'paper-trading', label: pt.sections['paper-trading'], icon: Wallet },
  ];

  const handleSelectSection = (id: SectionId) => {
    onSectionChange(id);
    setMobileMenuOpen(false);
  };

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#F4F5F7] dark:bg-[#06080D] text-slate-900 dark:text-slate-100">
      {/* Institutional Desktop Sidebar */}
      <aside className="hidden lg:flex lg:w-[264px] lg:flex-col lg:shrink-0 border-e border-slate-200 dark:border-[#D4AF37]/15 bg-white dark:bg-[#0B0F17]">
        <div className="h-14 px-4 flex items-center gap-2.5 border-b border-slate-200 dark:border-[#D4AF37]/15">
          <QazanEmblem className="w-7 h-7 shrink-0" />
          <div className="min-w-0">
            <span className="block font-bold text-xs tracking-wider text-slate-900 dark:text-[#E5C76B] truncate">
              {t.brandName}
            </span>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-5 overflow-y-auto" aria-label="Main navigation">
          {groups.map((grp) => (
            <div key={grp.title} className="space-y-1">
              <p className="px-3 pb-0.5 text-[11px] font-semibold tracking-wide text-slate-400 dark:text-slate-500">
                {grp.title}
              </p>
              {grp.items.map((item) => {
                const Icon = item.icon;
                const active = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelectSection(item.id)}
                    className={`relative w-full min-h-[42px] px-3 py-2 rounded-lg flex items-center gap-2.5 text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                      active
                        ? 'bg-[#D4AF37]/12 text-[#9A7209] dark:bg-[#D4AF37]/14 dark:text-[#E5C76B] font-semibold'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-[#121824] hover:text-slate-900 dark:hover:text-slate-100'
                    }`}
                  >
                    {active && (
                      <span
                        aria-hidden="true"
                        className="absolute inset-y-2 start-0 w-[3px] rounded-full bg-[#D4AF37]"
                      />
                    )}
                    <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-[#B88E14] dark:text-[#D4AF37]' : ''}`} />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Institutional Command Top Bar */}
        <header className="sticky top-0 z-30 pt-safe border-b border-slate-200 dark:border-[#D4AF37]/15 bg-white/95 dark:bg-[#0B0F17]/95 backdrop-blur-md">
          <div className="h-14 px-3 sm:px-6 flex items-center justify-between gap-2 sm:gap-4">
          <div className="min-w-0 flex items-center gap-2 sm:gap-3">
            <div className="lg:hidden flex items-center gap-2 min-w-0">
              <QazanEmblem className="w-6 h-6 shrink-0" />
              <span className="font-bold text-xs tracking-tight text-slate-900 dark:text-[#E5C76B] truncate max-w-[110px] sm:max-w-none">
                {t.brandName}
              </span>
            </div>

            {/* Active Symbol & Timeframe Bar */}
            <div className="flex items-center gap-1.5">
              <select
                aria-label={pt.activePair}
                value={activeSymbol}
                onChange={(e) => setActiveSymbol(e.target.value)}
                className="min-h-[38px] px-2.5 rounded-lg border border-slate-200 dark:border-[#D4AF37]/30 bg-slate-50 dark:bg-[#070A10] font-mono text-xs font-bold text-slate-900 dark:text-[#E5C76B] focus:outline-none focus:border-[#D4AF37]"
              >
                {trackedSymbols.map((item) => (
                  <option key={item.symbol} value={item.symbol}>
                    {item.symbol}
                  </option>
                ))}
              </select>

              <select
                aria-label={pt.timeframe}
                value={activeInterval}
                onChange={(e) => setActiveInterval(e.target.value)}
                className="md:hidden min-h-[38px] px-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#070A10] font-mono text-xs font-semibold text-slate-800 dark:text-slate-200"
              >
                {INTERVALS.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>

              <div className="hidden md:flex items-center p-0.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#070A10]">
                {INTERVALS.map((tf) => (
                  <button
                    key={tf}
                    type="button"
                    onClick={() => setActiveInterval(tf)}
                    className={`min-h-[32px] px-2.5 rounded-md font-mono text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                      activeInterval === tf
                        ? 'bg-[#D4AF37] text-[#06080D] font-bold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={toggleLanguage}
              aria-label={t.toggleLangLabel}
              className="min-h-[40px] min-w-[44px] px-2.5 inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold whitespace-nowrap shrink-0 cursor-pointer"
            >
              <Globe className="w-4 h-4 text-[#B88E14] dark:text-[#D4AF37]" />
              <span>{t.toggleLangLabel}</span>
            </button>

            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t.toggleThemeLight : t.toggleThemeDark}
              className="min-h-[40px] min-w-[44px] px-2.5 inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#111722] hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold whitespace-nowrap shrink-0 cursor-pointer"
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 text-[#D4AF37]" />
              ) : (
                <Moon className="w-4 h-4 text-slate-700" />
              )}
              <span className="hidden md:inline">
                {theme === 'dark' ? t.toggleThemeLight : t.toggleThemeDark}
              </span>
            </button>
          </div>
          </div>
        </header>

        {/* Offline Connectivity Alert Banner (Android / Web Network Drop) */}
        {!isOnline && (
          <div
            role="status"
            aria-live="polite"
            className="mx-3.5 sm:mx-6 mt-3 p-3 rounded-xl border border-amber-500/40 bg-amber-50 dark:bg-amber-950/35 text-amber-900 dark:text-amber-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
          >
            <div className="flex items-start gap-2.5 min-w-0">
              <WifiOff className="w-4 h-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              <div className="space-y-0.5 min-w-0 text-xs">
                <p className="font-bold">{pt.offlineBannerTitle}</p>
                <p className="text-amber-800/85 dark:text-amber-200/80">{pt.offlineBannerDetail}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void handleRetryConnectivity()}
              disabled={retryingNet}
              className="min-h-[44px] px-3.5 rounded-lg border border-amber-500/45 bg-white dark:bg-[#0B0F17] text-amber-800 dark:text-amber-300 text-xs font-bold inline-flex items-center justify-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${retryingNet ? 'animate-spin' : ''}`} />
              <span>{retryingNet ? pt.reconnecting : pt.retryConnection}</span>
            </button>
          </div>
        )}

        {/* Scrollable Workspace Viewport */}
        <main className="flex-1 w-full max-w-[1440px] mx-auto px-3.5 sm:px-6 px-safe py-5 pb-24 lg:pb-8">
          {children}
        </main>
      </div>

      {/* Mobile 14-Section Command Drawer */}
      {mobileMenuOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="lg:hidden fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="w-full max-h-[84vh] rounded-t-2xl border-t border-[#D4AF37]/30 bg-white dark:bg-[#0B0F17] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <QazanEmblem className="w-6 h-6" />
                <span className="font-bold text-xs tracking-wide text-slate-900 dark:text-[#E5C76B]">
                  {t.brandName}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                aria-label={pt.closeMenu}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4">
              {groups.map((grp) => (
                <div key={grp.title} className="space-y-1.5">
                  <p className="px-2 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                    {grp.title}
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                    {grp.items.map((item) => {
                      const Icon = item.icon;
                      const active = activeSection === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => handleSelectSection(item.id)}
                          className={`min-h-[48px] px-3.5 rounded-xl flex items-center gap-3 text-sm font-medium transition-colors ${
                            active
                              ? 'bg-[#D4AF37] text-[#06080D] font-bold'
                              : 'bg-slate-50 dark:bg-[#111722] text-slate-800 dark:text-slate-200'
                          }`}
                        >
                          <Icon className="w-4 h-4 shrink-0" />
                          <span className="truncate">{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Fixed Bottom Thumb Dock */}
      <nav
        aria-label="Mobile bottom navigation"
        className="lg:hidden fixed bottom-0 left-0 right-0 z-40 h-16 pb-safe border-t border-slate-200 dark:border-[#D4AF37]/15 bg-white/95 dark:bg-[#0B0F17]/95 backdrop-blur-md grid grid-cols-5 items-center"
      >
        {mobilePrimaryTabs.map((item) => {
          const Icon = item.icon;
          const active = activeSection === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => handleSelectSection(item.id)}
              className={`min-h-[48px] flex flex-col items-center justify-center gap-1 px-1 transition-colors ${
                active
                  ? 'text-[#B88E14] dark:text-[#E5C76B] font-semibold'
                  : 'text-slate-500 dark:text-slate-400'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="text-[10px] leading-none truncate max-w-full">{item.label}</span>
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => setMobileMenuOpen(true)}
          className={`min-h-[48px] flex flex-col items-center justify-center gap-1 px-1 transition-colors ${
            mobileMenuOpen ? 'text-[#D4AF37] font-semibold' : 'text-slate-500 dark:text-slate-400'
          }`}
        >
          <Menu className="w-5 h-5" />
          <span className="text-[10px] leading-none whitespace-nowrap">{pt.mobileMore}</span>
        </button>
      </nav>
    </div>
  );
}
