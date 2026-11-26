import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { platformClient } from '@/api/platformClient';
import {
  checkNetworkNow,
  getConfiguredBackendOrigin,
  getRuntimePlatform,
  hideNativeSplashScreen,
  hydrateNativePreferences,
  isNativePlatform,
  PREF_KEYS,
  resetConfiguredBackendOrigin,
  setConfiguredBackendOrigin,
  setPreference,
  subscribeNetworkChanges,
  syncSystemAppearance,
} from '@/services/nativePlatform';
import { translations, type Language, type TranslationDict } from '@/i18n/translations';
import {
  platformTranslations,
  type PlatformTranslationDict,
} from '@/i18n/platformTranslations';
import type { TrackedSymbolItem } from '@/types/platform';

export type ThemeMode = 'dark' | 'light';

const DEFAULT_SYMBOLS: TrackedSymbolItem[] = [
  'BTCUSDT',
  'ETHUSDT',
  'SOLUSDT',
  'BNBUSDT',
  'XRPUSDT',
  'ADAUSDT',
].map((sym) => ({
  symbol: sym,
  base_asset: sym.replace('USDT', ''),
  quote_asset: 'USDT',
  source: 'Default',
  is_default: true,
  added_at: '',
}));

interface AppContextValue {
  language: Language;
  dir: 'rtl' | 'ltr';
  theme: ThemeMode;
  t: TranslationDict;
  pt: PlatformTranslationDict;
  activeSymbol: string;
  activeInterval: string;
  trackedSymbols: TrackedSymbolItem[];
  isOnline: boolean;
  connectionType: string;
  isNative: boolean;
  runtimePlatform: string;
  backendOrigin: string;
  refreshTrackedSymbols: () => Promise<void>;
  recheckConnectivity: () => Promise<boolean>;
  updateBackendOrigin: (url: string) => Promise<string>;
  resetBackendOrigin: () => Promise<string>;
  setActiveSymbol: (symbol: string) => void;
  setActiveInterval: (interval: string) => void;
  setLanguage: (lang: Language) => void;
  setTheme: (theme: ThemeMode) => void;
  toggleLanguage: () => void;
  toggleTheme: () => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem(PREF_KEYS.language);
    return saved === 'en' ? 'en' : 'ar';
  });

  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(PREF_KEYS.theme);
    return saved === 'light' ? 'light' : 'dark';
  });

  const [activeSymbol, setActiveSymbolState] = useState<string>(() => {
    return localStorage.getItem(PREF_KEYS.symbol) || 'BTCUSDT';
  });

  const [activeInterval, setActiveIntervalState] = useState<string>(() => {
    return localStorage.getItem(PREF_KEYS.interval) || '1h';
  });

  const [backendOrigin, setBackendOriginState] = useState<string>(() => getConfiguredBackendOrigin());
  const [isOnline, setIsOnline] = useState<boolean>(() => (typeof navigator !== 'undefined' ? navigator.onLine : true));
  const [connectionType, setConnectionType] = useState<string>('wifi');
  const [trackedSymbols, setTrackedSymbols] = useState<TrackedSymbolItem[]>(DEFAULT_SYMBOLS);

  const dir: 'rtl' | 'ltr' = language === 'ar' ? 'rtl' : 'ltr';
  const nativeMode = isNativePlatform();
  const runtimePlatform = getRuntimePlatform();

  const refreshTrackedSymbols = useCallback(async () => {
    try {
      const res = await platformClient.getTrackedSymbols();
      if (res.symbols && res.symbols.length > 0) {
        setTrackedSymbols(res.symbols);
      }
    } catch {
      // Preserve existing/default list while offline
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      const hydrated = await hydrateNativePreferences();
      if (!mounted) return;
      if (hydrated.language) setLanguageState(hydrated.language);
      if (hydrated.theme) setThemeState(hydrated.theme);
      if (hydrated.symbol) setActiveSymbolState(hydrated.symbol);
      if (hydrated.interval) setActiveIntervalState(hydrated.interval);
      if (hydrated.backendOrigin) setBackendOriginState(hydrated.backendOrigin);
      await refreshTrackedSymbols();
      await hideNativeSplashScreen();
    })();
    return () => {
      mounted = false;
    };
  }, [refreshTrackedSymbols]);

  useEffect(() => {
    const unsub = subscribeNetworkChanges((state) => {
      setIsOnline(state.connected);
      setConnectionType(state.connectionType);
      if (state.connected) {
        void refreshTrackedSymbols();
      }
    });
    return unsub;
  }, [refreshTrackedSymbols]);

  useEffect(() => {
    const root = document.documentElement;
    root.lang = language;
    root.dir = dir;
    void setPreference(PREF_KEYS.language, language);
  }, [language, dir]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    void setPreference(PREF_KEYS.theme, theme);
    void syncSystemAppearance(theme);
  }, [theme]);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    void setPreference(PREF_KEYS.language, lang);
  };

  const setTheme = (mode: ThemeMode) => {
    setThemeState(mode);
    void setPreference(PREF_KEYS.theme, mode);
  };

  const setActiveSymbol = (sym: string) => {
    setActiveSymbolState(sym);
    void setPreference(PREF_KEYS.symbol, sym);
  };

  const setActiveInterval = (tf: string) => {
    setActiveIntervalState(tf);
    void setPreference(PREF_KEYS.interval, tf);
  };

  const recheckConnectivity = useCallback(async (): Promise<boolean> => {
    const net = await checkNetworkNow();
    setIsOnline(net.connected);
    setConnectionType(net.connectionType);
    if (net.connected) {
      await refreshTrackedSymbols();
    }
    return net.connected;
  }, [refreshTrackedSymbols]);

  const updateBackendOrigin = useCallback(async (url: string): Promise<string> => {
    const normalized = await setConfiguredBackendOrigin(url);
    setBackendOriginState(normalized);
    return normalized;
  }, []);

  const resetBackendOrigin = useCallback(async (): Promise<string> => {
    const normalized = await resetConfiguredBackendOrigin();
    setBackendOriginState(normalized);
    return normalized;
  }, []);

  const toggleLanguage = () => setLanguage(language === 'ar' ? 'en' : 'ar');
  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  return (
    <AppContext.Provider
      value={{
        language,
        dir,
        theme,
        t: translations[language],
        pt: platformTranslations[language],
        activeSymbol,
        activeInterval,
        trackedSymbols,
        isOnline,
        connectionType,
        isNative: nativeMode,
        runtimePlatform,
        backendOrigin,
        refreshTrackedSymbols,
        recheckConnectivity,
        updateBackendOrigin,
        resetBackendOrigin,
        setActiveSymbol,
        setActiveInterval,
        setLanguage,
        setTheme,
        toggleLanguage,
        toggleTheme,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useApp must be used inside AppProvider');
  }
  return ctx;
}
