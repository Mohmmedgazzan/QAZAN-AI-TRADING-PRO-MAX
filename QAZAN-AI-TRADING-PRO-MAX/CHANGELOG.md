# Changelog

All notable changes to **QAZAN-AI-TRADING-PRO-MAX** are documented in this file.

## [1.0.0-open-source] - 2026-11-19
### Added
- **Open-Source Legal & Bilingual Documentation**:
  - Added MIT `LICENSE` and `SECURITY.md` (covering zero-secret design and Git history remediation steps via `git filter-repo` + key rotation).
  - Rewrote English `README.md` and created complete Arabic `README.ar.md` with mutual cross-links, architecture diagrams, step-by-step local run instructions, Docker usage, Android APK instructions, automated test commands, and GitHub publishing workflow.
- **Docker & Local Auto-Start Packaging**:
  - Added `Dockerfile.backend` (Python 3.11 + `libgomp1` for XGBoost + FastAPI healthcheck), `Dockerfile.frontend` (multi-stage Node 20 build + Nginx 1.27), `docker/nginx.conf` (HTTP + WebSocket `/api/v1/ws/market` upgrade proxy), `docker-compose.yml`, and `.dockerignore`.
  - Added one-command local startup scripts `scripts/start-local.sh` (Linux/macOS) and `scripts/start-local.bat` (Windows), plus root `requirements.txt` delegating to `backend/requirements.txt`.
- **GitHub Actions CI & Phase 10 Release Tests**:
  - Added `.github/workflows/ci.yml` automating TypeScript lint + Vite build, full Pytest suite (`backend/tests`), Docker Compose build validation, and Android Debug APK assembly.
  - Added `backend/tests/test_release_open_source.py` validating required open-source files, README cross-links, zero exposed secrets or cloud-builder preview URLs, Docker/CI config integrity, clean ZIP export rules, and `1.0.0-open-source` API health.

### Changed
- **Platform Independence & Dependency Cleanup**:
  - Cleaned `package.json` (`name: "qazan-ai-trading-pro-max"`, `version: "1.0.0"`, `license: "MIT"`, `private: false`, added `npm test` script, removed unused `@google/genai` cloud AI SDK dependency).
  - Updated `backend/requirements.txt` to explicitly declare `pydantic>=2.9.0` and `websockets>=13.0`.
  - Removed hardcoded cloud preview origin from `src/services/nativePlatform.ts` (`DEFAULT_NATIVE_BACKEND_ORIGIN` now defaults cleanly via `VITE_QAZAN_NATIVE_BACKEND_ORIGIN` or `https://localhost:8001`), cleaned `SettingsSection.tsx` placeholder, cleaned `vite.config.ts` comment, and re-synced clean assets into `android/app/src/main/assets/public/` via `npm run cap:sync`.
  - Hardened `.gitignore` and `.env.example` for safe GitHub hosting (ignoring `.env*`, `*.db*`, `backups/`, `*.keystore`, `*.jks`, `*.apk`, `*.aab`, `node_modules/`).
  - Updated `APP_VERSION` to `1.0.0-open-source` and release ZIP archive filename to `QAZAN-AI-TRADING-PRO-MAX-v1.0.0-open-source.zip` (excluding `.db*`, `.env*`, `.keystore`, and build caches).

## [0.9.0-android-capacitor] - 2026-11-19
### Added
- Native Android Conversion via **Capacitor v8** (`android/` native Gradle project targeting SDK 36, `minSdk: 24`, package `com.qazan.tradingpromax`):
  - **Installable Android APK Project**: Complete `AndroidManifest.xml`, `build.gradle`, Java 21 `MainActivity.java`, `strings.xml`, and `gradle` scripts (`android:apk:debug`, `android:apk:release`, `android:bundle:release` in `package.json`).
  - **Custom App Icon & Splash Brand Identity**: Institutional metallic gold falcon-quant icon across all `mipmap-*` adaptive (`v26`) and legacy densities (`mdpi`–`xxxhdpi`), plus full `drawable-*` splash screens and Android 12+ `Theme.SplashScreen` (`splash_icon.png`) carrying the `QAZAN` logo.
  - **Multi-Screen & Safe-Area Support**: `<supports-screens>` covering phones, large screens, foldables, and tablets paired with `viewport-fit=cover` and CSS `env(safe-area-inset-*)` padding (`.pt-safe`, `.pb-safe`, `.px-safe`).
  - **Native Dark & Light Theme Sync**: Android `values/styles.xml` + `values-night/styles.xml` (`DayNight`) synchronized live with React `AppContext` via `@capacitor/status-bar`.
  - **Secure HTTPS Backend & WebSocket Routing**: `res/xml/network_security_config.xml` + `android:usesCleartextTraffic="false"` + hardened `capacitor.config.ts` (`cleartext: false`, `allowMixedContent: false`), with `https://` origin validation and live latency testing inside `SettingsSection.tsx`.
  - **Offline / Disconnection Handling**: Real-time `@capacitor/network` + browser connectivity listener (`src/services/nativePlatform.ts`) surfacing an institutional offline alert banner with retry action in `AppShell.tsx` and instant `OFFLINE_NO_INTERNET` guarding in `src/api/client.ts`.
  - **Persistent Native Preferences**: `@capacitor/preferences` (`SharedPreferences`) paired with `localStorage` & SQLite `/api/v1/settings` for language, theme, symbol, timeframe, and HTTPS backend URL.
  - **Comprehensive APK Documentation**: Complete build, debug installation, Keystore signing, Release APK/AAB production, and verification steps documented in `ANDROID_APK_GUIDE.md`.

## [0.8.0-macro-economic-news] - 2026-11-18
### Added
- Institutional Official Macro Economic News & Pre-Event High-Impact Warning Engine (`backend/app/services/macro_news_service.py` & `backend/app/schemas/macro_news.py`):
  - Aggregates real market-moving macro events & official schedules from **U.S. Federal Reserve (FOMC Calendar & Monetary Press RSS + FOMC target rate)**, **U.S. Bureau of Labor Statistics (`BLS.gov` CPI, PPI, Employment Situation Atom feeds & official release schedules)**, **European Central Bank (`ECB` Press & Speeches RSS)**, **Bank of England (`BoE` MPC & News RSS)**, and **ForexFactory Public Weekly Calendar** with SQLite TTL caching (`macro_news_events_cache`) and `429` cache fallback.
  - Explicit multi-tag filtering across all 7 required domains: `FED_DECISION` (قرارات الاحتياطي الفيدرالي), `INTEREST_RATE` (قرارات الفائدة), `CPI`, `PPI`, `NFP`, `UNEMPLOYMENT` (البطالة), and `CENTRAL_BANK_SPEECH` (تصريحات البنوك المركزية), plus `OTHER_MACRO`.
  - Structured display of every required field: Event Name, Exact Timestamp & Countdown/Status (`IMMINENT` / `UPCOMING` / `RELEASED`), Impact Level (`High` / `Medium` / `Low`), `Previous`, `Forecast`, `Actual`, and clickable Official Source link (`fabricated_events_count = 0`).
  - Deterministic **Pre-Event High-Impact Volatility Warning Engine** (`CRITICAL` <= 60m, `ELEVATED` <= 6h, `WATCH` <= configurable window up to 7d, `CLEAR` otherwise) surfaced prominently in `EconomicCalendarSection.tsx` and unobtrusively on `DashboardSection.tsx`.
  - Exposed FastAPI endpoint `GET /api/v1/calendar/macro` while preserving `GET /api/v1/calendar/events` intact for full backward compatibility.
- Phase 8 pytest suite `backend/tests/test_macro_news.py` + pre-phase backup preserved in `.backups/phase7_v070/`.

## [0.7.0-pro-backtesting-paper] - 2026-11-18
### Added
- Institutional Professional Backtesting, Walk-Forward & Validation Gate Engine (`backend/app/services/pro_backtest_service.py` & `backend/app/schemas/backtest_pro.py`):
  - Multi-timeframe causal evaluation across `15m`, `1h`, `4h`, and `1d` real historical OHLCV bars.
  - Complete quantitative performance analytics: `Win Rate`, `Profit Factor`, `Maximum Drawdown (% & USDT)`, `Expectancy ($USDT & R-multiples)`, `Configured & Realized R:R`, `Sharpe`, and `Sortino`.
  - Realistic friction modeling: side-level exchange **fees & adverse slippage** (`fee_pct`, `slippage_pct`) deducted from fills and realized PnL.
  - Strict **Zero Look-Ahead Bias** guarantee: active unclosed bars dropped before computation, signals read strictly from closed bar `t-1` and filled at bar `t` OPEN (`SIGNAL_ON_CLOSED_BAR_FILL_NEXT_OPEN`), and intra-bar SL checked before TP.
  - Expanding **Walk-Forward Out-of-Sample (OOS)** testing selecting IS parameters without peeking and evaluating strictly on unseen chronological OOS folds.
  - **Mandatory Strategy Validation Gate**: strategies are explicitly labeled `FAILED` (`is_strategy_successful = False`) and blocked from "Passed / Successful" status unless ALL 6 gates pass (sample adequacy, positive IS & OOS expectancy, Profit Factor threshold, Drawdown cap, Walk-Forward OOS consistency, and causal/friction integrity).
  - SQLite persistence table `strategy_backtest_reports` + FastAPI routes `POST /api/v1/backtest/pro/run`, `GET /api/v1/backtest/pro/strategies`, and `DELETE /api/v1/backtest/pro/strategies/{report_id}`.
- Enhanced **Virtual Paper Trading** (`backend/app/services/paper_trading_service.py` & `PaperTradingSection.tsx`):
  - `100% VIRTUAL FUNDS` governance banner, preset & custom virtual capital reset (`$5,000` / `$10,000` / `$25,000` / `$100,000`), SL/TP directional validation, automatic SL/TP trigger fills on live mark price, per-trade virtual fee & slippage accounting, and closed portfolio Win Rate / Profit Factor / Expectancy telemetry.
- Frontend integration in `BacktestingSection.tsx` (`ProBacktestValidationView.tsx` + preserved Classic Quick Simulator) & `PaperTradingSection.tsx` with bilingual (`ar`/`en`) + Dark/Light responsive support.
- Phase 7 pytest suite `backend/tests/test_pro_backtest_paper.py` + pre-phase backup snapshot preserved in `.backups/phase6_v060/`.

## [0.6.0-trade-discovery-risk] - 2026-11-16
### Added
- Institutional Dual-Hypothesis Trade Opportunity Discovery & Risk Governance Engine (`backend/app/services/trade_discovery_service.py` & `backend/app/schemas/opportunity.py`):
  - Simultaneous causal evaluation of **LONG** (`Trend Confirmation`, `BOS/CHoCH`, `Demand/Bullish OB/SSL Sweep/Discount`, `LTF Entry Confirmation`, `Invalidation`) and **SHORT** (`Downtrend Confirmation`, `BOS/CHoCH`, `Supply/Bearish OB/BSL Sweep/Premium`, `LTF Entry Confirmation`, `Invalidation`) hypotheses.
  - Complete execution plan output: `Entry Zone`, `Stop Loss`, `TP1`, `TP2`, `TP3`, `Gross & Net R:R`, `Position Size (Units & Notional)`, and explicit `Invalidation` rules.
  - Strict Risk Governance rules: default `1%` risk per trade, `3%` daily loss circuit-breaker enforced against SQLite daily realized + unrealized PnL, explicit entry/exit **fees & slippage** friction deduction baked into unit sizing and net R:R, strict confirmation gate returning `NO_TRADE` whenever criteria fail, and SHA-256 signal deduplication (`trade_opportunities` table).
  - Hard execution lock (`live_execution_blocked = True`, `execution_mode = "ANALYSIS_ONLY_NO_LIVE_ORDERS"`).
- Exposed FastAPI endpoints `/api/v1/opportunities/evaluate` (`GET` & `POST`), `/api/v1/opportunities/scan`, and `/api/v1/opportunities/history`.
- Frontend integration inside `Trade Scanner` (`TradeOpportunityDiscoveryView.tsx`) with bilingual (`ar`/`en`) + Dark/Light responsive support while keeping the Classic Multi-Pair Scanner 100% functional.
- Phase 6 pytest suite `backend/tests/test_trade_discovery.py` + pre-phase backup snapshot preserved in `.backups/phase5_v050/`.

### Fixed
- Resolved `CONNECTION_REFUSED: Failed to fetch` and `502 Bad Gateway` issues across cloud preview containers:
  - Updated `src/api/client.ts` to ignore container-injected `:8000` `VITE_API_BASE_URL` values in favor of same-origin `/api/v1` gateway routing with transient `502`/`503`/startup retries.
  - Updated `server.ts` to use dedicated `QAZAN_BACKEND_HOST` / `QAZAN_BACKEND_PORT` (`127.0.0.1:8001`) avoiding control-plane port `8000` collision, bind port `3000` immediately before backend readiness, and auto-respawn FastAPI if exited.
  - Added inode-based SQLite schema auto-healing (`backend/app/db/database.py`) so missing tables recover automatically via `init_db()`.
  - Added `sanitize_service_url` validators in `backend/app/core/config.py` to strip Markdown-wrapped URL environment variables (`[https://...](https://...)`) preventing `UnsupportedProtocol` 502 errors on live Binance endpoints.

## [0.5.0-market-ingestion] - 2026-11-15
### Added
- Resilient keyless public market data ingestion layer (`backend/app/services/http_resilient.py`) featuring exponential backoff retries, HTTP `429`/`418` `Retry-After` handling, and Binance `X-MBX-USED-WEIGHT-1M` rate-limit monitoring.
- Dynamic SQLite-backed trading pair registry (`tracked_symbols` table + `backend/app/services/symbol_registry.py`) seeded with `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `ADAUSDT` and supporting verified addition/removal of custom Binance pairs across charts, scanner, paper trading, and WebSocket feeds.
- Real public derivatives, order-flow, and macro metrics (`backend/app/services/market_derivatives_service.py`) with strict per-metric provenance (`source`, `updated_at`, `status = LIVE | CACHED | MISSING`) and SQLite TTL caching (`market_metrics_cache`):
  - `OHLCV` & `24h Volume` (Binance Spot REST + WS)
  - `Open Interest` & `Funding Rate` (Binance Futures `/fapi/v1/openInterest`, `/fapi/v1/premiumIndex`, with OKX Public SWAP fallback)
  - `CVD` (Cumulative Volume Delta from Binance `/api/v3/aggTrades` + live `@aggTrade` WebSocket stream)
  - `Liquidations` (Live Binance Futures `!forceOrder@arr` WebSocket ring buffer — zero synthetic rows when none observed)
  - `BTC Dominance` (CoinGecko `/api/v3/global` with CoinPaprika `/v1/global` fallback)
- OHLCV data validator & missing-data detector (`backend/app/services/market_data_validator.py`) flagging invalid OHLC bounds, duplicate/out-of-order timestamps, missing candle gaps, staleness, and `MISSING` metrics without fabricating fallback values.
- Real-time server-authoritative WebSocket hub (`backend/app/services/ws_market_hub.py`) exposed at `/api/v1/ws/market` and proxied over port `3000` (`server.ts` HTTP upgrade handler).
- Frontend integration in `MarketOverviewSection` (`MarketDataProvenanceView.tsx`) and dynamic symbol list in `AppContext` / `AppShell`.
- Phase 5 ingestion test suite `backend/tests/test_market_ingestion.py` (6/6 passing) + pre-phase snapshot preserved in `.backups/phase4_v040/`.

## [0.4.0-probability-engine] - 2026-11-15
### Added
- Strictly causal Walk-Forward Statistical & ML Next-Candle Probability Engine (`backend/app/ml/probability_engine.py`) analyzing closed bars across 9 domains (`OHLCV`, `RSI`, `ATR`, `Volume`, `VWAP`, `Market Structure`, `Liquidity`, `FVG`, `Trend`) without paid APIs or future data leakage.
- Outputs calibrated 3-state next-candle probabilities (`UP`, `DOWN`, `SIDEWAYS` summing to 100%), ATR empirical quantile price range envelope (never claiming to know exact future close), entropy + calibration confidence score, and directional driving factors across all 9 domains.
- Expanding **Walk-Forward Validation** computing out-of-sample **Brier Score** and **Log Loss** vs a causal Markov + empirical-prior statistical baseline, with Bayesian shrinkage calibration.
- Strict `INSUFFICIENT_DATA` guard refusing to emit synthetic forecasts when fewer than 140 closed bars or insufficient labeled training windows exist.
- SQLite `probability_forecasts` table and endpoints `/api/v1/analysis/candle-probabilities` & `/api/v1/analysis/candle-probabilities/history`.
- Frontend integration inside `Candle Prediction` section (`CandleProbabilityView.tsx`) with segmented subtabs preserving the classic regression view, bilingual (`ar`/`en`) + Dark/Light support.
- Added 15-minute SQLite TTL cache guard in `calendar_settings_service.py` to prevent upstream ForexFactory `429` rate-limiting.
- Comprehensive Walk-Forward & zero-leakage test suite `backend/tests/test_probability_engine.py` (5/5 passing).
- Pre-probability snapshot preserved in `.backups/phase3_v030/`.

## [0.3.0-causal-engine] - 2026-11-15
### Added
- Strictly causal Multi-Timeframe Python Technical Analysis Engine (`backend/app/engine/`) operating on primary `1W`, `1D`, `4H` timeframes plus lower timeframe (`1H` / `15M`) entry confirmation:
  1. Market Bias (`BULLISH` / `BEARISH` / `NEUTRAL`)
  2. Market Regime (`TRENDING_EXPANSION` / `RANGING_COMPRESSION` / `VOLATILE_CHOP` / `TRANSITIONAL`)
  3. Market Phase (`TREND` / `RANGE` / `CORRECTION`)
  4. Structural Pivots (`HH` / `HL` / `LH` / `LL`) with causal confirmation at `t = p + swing_right`
  5. Premium / Discount + Equilibrium & OTE Zone (`61.8%–78.6%`)
  6. Swing Highs & Swing Lows (`EXTERNAL` / `INTERNAL` scope)
  7. External Liquidity (`BSL` / `SSL`)
  8. Internal Liquidity (`FVG_CE` & internal pivots)
  9. Equal Highs & Equal Lows clusters (`EQH` / `EQL`)
  10. Causal Liquidity Sweeps (`BSL_SWEEP` / `SSL_SWEEP` + wick ratio)
  11. `BOS` / `CHoCH` structural breaks requiring candle close + hold confirmation
  12. Supply & Demand zones (`RBD`, `DBD`, `DBR`, `RBR`) with freshness tracking
  13. Causal Order Blocks (`ACTIVE` / `MITIGATED` / `INVALIDATED`)
  14. Breaker Blocks (`BULLISH_BREAKER` / `BEARISH_BREAKER` flipped on OB invalidation)
  15. Fair Value Gaps (`UNMITIGATED` / `PARTIALLY_FILLED` / `MITIGATED`)
- Explicit state-machine distinction between `BREAKOUT`, `FAKEOUT`, `STOP_HUNT`, and `PENDING_CONFIRMATION`.
- Zero Look-ahead Bias guarantee: unclosed candles excluded when `as_of_ts` precedes close, pivots confirmed causally, and walk-forward causal backtester (`run_causal_backtest_on_df`) executing entries at `t+1` open.
- SQLite persistence table `technical_analysis_runs` and FastAPI endpoints `/api/v1/engine/analyze`, `/api/v1/engine/backtest`, `/api/v1/engine/history`, plus standalone JSON CLI (`python3 -m app.engine.cli`).
- Frontend integration inside `Market Structure` section via 3 segmented subtabs (`Single-TF Chart & Swings`, `Multi-TF Engine (1W · 1D · 4H)`, `Causal Backtest & JSON`) with bilingual (`ar`/`en`) + Dark/Light support.
- Regression & look-ahead invariance test suite `backend/tests/test_technical_engine.py` (5/5 passing; 16/16 total).
- Pre-engine backup preserved in `.backups/phase2_v021/`.

## [0.2.1-institutional-ui] - 2026-11-15
### Changed
- Redesigned Phase 2 UI into a luxury obsidian (`#06080D` / `#0B0F17`) & metallic gold (`#D4AF37` / `#E5C76B`) institutional trading terminal while preserving Phase 1 diagnostics, error logs, SQLite persistence, and dual Dark/Light + Arabic (RTL)/English (LTR) support.
- Upgraded `AppShell` with geometric candlestick monogram crest, gold active navigation rail, segmented timeframe bar on desktop, and responsive mobile thumb dock + 14-section drawer.
- Upgraded `TradingChart` (Lightweight Charts v5 `createSeriesMarkers`) to render live `HH/HL/LH/LL` swing labels and `BOS/CHoCH` breaks directly on candlesticks.
- Added institutional visualizations across sections: embedded live chart + 24h range telemetry on `Dashboard`, sorting + 24h range bars + mobile cards on `Market Overview`, side live watchlist on `Live Charts`, SVG semi-circular probability gauge on `AI Analysis`, embedded structural chart on `Market Structure`, Liquidity Depth Ladder on `Liquidity Analysis`, Active-only filter + Dealing Range marker on `Smart Money Concepts`, SVG Projected Candlestick Anatomy on `Candle Prediction`, signal filter + score bar on `Trade Scanner`, Risk/Reward proportion bar on `Risk Management`, execution trades table on `Backtesting`, and optional SL/TP fields on `Paper Trading`.
- Pre-redesign snapshot preserved in `.backups/phase2_v020/`.

## [0.2.0-institutional] - 2026-11-15
### Added
- Institutional luxury dark aesthetic with gold accents (`#D4AF37` / `#F59E0B`), emerald bullish (`#10B981`), and crimson bearish (`#EF4444`) signals, with preserved Dark/Light mode and Arabic (RTL) / English (LTR) support.
- Full 14-section architecture connected to real FastAPI + SQLite + Local ML + Public Live APIs:
  1. Dashboard
  2. Market Overview
  3. Live Charts (with EMA 20/50 & Market Structure overlays)
  4. AI Market Analysis (real Scikit-learn RandomForest & XGBoost on live OHLCV)
  5. Market Structure (HH/HL/LH/LL, BOS, CHoCH)
  6. Liquidity Analysis (EQH/EQL, Liquidity Sweeps, Volume Profile POC)
  7. Smart Money Concepts (FVG, Order Blocks, Premium/Discount Equilibrium)
  8. Candle Prediction (XGBoost & GradientBoosting next-candle OHLC forecast)
  9. Trade Scanner (multi-pair live quantitative scanner)
  10. Risk Management (position sizing, R:R, liquidation estimator, SQLite risk rules)
  11. Backtesting (historical strategy engine with equity curve & SQLite history)
  12. Paper Trading (live-priced virtual portfolio & orders persisted in SQLite)
  13. Economic Calendar (live public economic events feed + SQLite cache)
  14. Settings (persistent SQLite preferences + preserved System Health & Error Logs)
- Regression test suite `backend/tests/test_phase2_platform.py`.
- Phase 1 baseline backup stored in `.backups/phase1_baseline/`.

## [0.1.0-foundation] - 2026-11-15
### Added
- Separated Frontend (`src/` React + TypeScript + Vite + Tailwind v4 + TradingView Lightweight Charts) and Backend (`backend/` Python + FastAPI + SQLite + Pandas + NumPy + Scikit-learn + XGBoost).
- Capacitor Android configuration (`capacitor.config.ts`).
- Rotating file + SQLite error logging (`system_logs`), global exception handlers, and `/api/v1/health`, `/api/v1/market/klines`, `/api/v1/logs`, `/api/v1/logs/client`, `/api/v1/diagnostics/test-error`.
- Bilingual Arabic (RTL) / English (LTR) and Dark/Light theme switching.
- Foundational pytest suite `backend/tests/test_foundation.py` (4/4 passing).
