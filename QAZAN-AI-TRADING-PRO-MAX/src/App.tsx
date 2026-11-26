import React, { useState } from 'react';
import { apiClient } from '@/api/client';
import { AppShell } from '@/components/AppShell';
import { AIAnalysisSection } from '@/components/sections/AIAnalysisSection';
import { BacktestingSection } from '@/components/sections/BacktestingSection';
import { CandlePredictionSection } from '@/components/sections/CandlePredictionSection';
import { DashboardSection } from '@/components/sections/DashboardSection';
import { EconomicCalendarSection } from '@/components/sections/EconomicCalendarSection';
import { LiquidityAnalysisSection } from '@/components/sections/LiquidityAnalysisSection';
import { LiveChartsSection } from '@/components/sections/LiveChartsSection';
import { MarketOverviewSection } from '@/components/sections/MarketOverviewSection';
import { MarketStructureSection } from '@/components/sections/MarketStructureSection';
import { PaperTradingSection } from '@/components/sections/PaperTradingSection';
import { RiskManagementSection } from '@/components/sections/RiskManagementSection';
import { SettingsSection } from '@/components/sections/SettingsSection';
import { SmartMoneySection } from '@/components/sections/SmartMoneySection';
import { TradeScannerSection } from '@/components/sections/TradeScannerSection';
import { AppProvider } from '@/contexts/AppContext';
import type { SectionId } from '@/i18n/platformTranslations';

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; message: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    void apiClient.reportClientError(
      error.message,
      info.componentStack?.slice(0, 450) || 'ReactErrorBoundary',
      'CRITICAL',
    );
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50 dark:bg-[#070A10] text-slate-900 dark:text-slate-100">
          <div className="max-w-md w-full p-6 rounded-xl border border-red-500/30 bg-white dark:bg-[#0B111B] space-y-3">
            <h1 className="text-lg font-bold text-red-500">Application Render Error</h1>
            <p className="text-xs font-mono break-all text-slate-600 dark:text-slate-300">
              {this.state.message}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="min-h-[44px] px-4 py-2 rounded-lg bg-amber-500 text-slate-950 text-xs font-bold"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [activeSection, setActiveSection] = useState<SectionId>('dashboard');

  return (
    <AppProvider>
      <AppErrorBoundary>
        <AppShell activeSection={activeSection} onSectionChange={setActiveSection}>
          {activeSection === 'dashboard' && <DashboardSection onNavigate={setActiveSection} />}
          {activeSection === 'market-overview' && (
            <MarketOverviewSection onNavigate={setActiveSection} />
          )}
          {activeSection === 'live-charts' && <LiveChartsSection />}
          {activeSection === 'ai-analysis' && <AIAnalysisSection />}
          {activeSection === 'market-structure' && <MarketStructureSection />}
          {activeSection === 'liquidity-analysis' && <LiquidityAnalysisSection />}
          {activeSection === 'smart-money' && <SmartMoneySection />}
          {activeSection === 'candle-prediction' && <CandlePredictionSection />}
          {activeSection === 'trade-scanner' && (
            <TradeScannerSection onNavigate={setActiveSection} />
          )}
          {activeSection === 'risk-management' && <RiskManagementSection />}
          {activeSection === 'backtesting' && <BacktestingSection />}
          {activeSection === 'paper-trading' && <PaperTradingSection />}
          {activeSection === 'economic-calendar' && <EconomicCalendarSection />}
          {activeSection === 'settings' && <SettingsSection />}
        </AppShell>
      </AppErrorBoundary>
    </AppProvider>
  );
}
