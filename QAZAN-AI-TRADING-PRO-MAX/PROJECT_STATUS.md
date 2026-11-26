# Project Status — QAZAN-AI-TRADING-PRO-MAX

## Current Milestone
- **Active Phase:** Phase 10 (`1.0.0-open-source`) — Full Open-Source Independence, MIT Licensing, Secret Hygiene, Bilingual Documentation (`README.md` + `README.ar.md`), Docker/Compose Packaging, Local Auto-Start Scripts, GitHub Actions CI, and Clean ZIP Release Verification.
- **Previous Phase Preserved:** Phase 9 (`0.9.0-android-capacitor`) and all Phases 1–8 modules, endpoints, SQLite tables, quantitative engines, and UI sections remain 100% intact.

## Module Status

| # | Section / Component | Backend / Packaging Target | Status |
|---|---|---|---|
| 0 | Core Health, Logs & Error Pipeline | `/api/v1/health`, `/api/v1/logs` | Verified (`1.0.0-open-source`) |
| 1 | Dashboard (Split Terminal + Embedded Chart + Macro Alert Strip) | `/api/v1/dashboard/summary`, `/api/v1/market/klines`, `/api/v1/calendar/macro` | Verified |
| 2 | Market Overview + Ingestion, WS & Provenance | `/api/v1/market/tickers`, `/api/v1/data/market-intelligence`, `/api/v1/data/symbols`, `/api/v1/data/validation`, `WS /api/v1/ws/market` | Verified |
| 3 | Live Charts (EMA 20/50 + BOS/Swings + Watchlist) | `/api/v1/market/klines`, `/api/v1/analysis/structure` | Verified |
| 4 | AI Market Analysis (SVG Gauge + Benchmarks) | `/api/v1/analysis/ai` | Verified |
| 5 | Market Structure & Causal Multi-TF Engine (`1W/1D/4H` + `LTF`) | `/api/v1/analysis/structure`, `/api/v1/engine/analyze`, `/api/v1/engine/backtest`, `/api/v1/engine/history` | Verified |
| 6 | Liquidity Analysis (Depth Ladder + Volume Profile) | `/api/v1/analysis/liquidity` | Verified |
| 7 | Smart Money Concepts (Equilibrium + Active Filter) | `/api/v1/analysis/smc` | Verified |
| 8 | Candle Prediction & Walk-Forward Probabilities (Brier/LogLoss vs Baseline) | `/api/v1/analysis/candle-probabilities`, `/api/v1/analysis/candle-probabilities/history`, `/api/v1/analysis/candle-prediction` | Verified |
| 9 | Trade Scanner + Dual-Hypothesis Discovery & Risk Governance (`LONG`/`SHORT`/`NO_TRADE`) | `/api/v1/opportunities/evaluate`, `/api/v1/opportunities/scan`, `/api/v1/opportunities/history`, `/api/v1/scanner/scan` | Verified |
| 10 | Risk Management (R:R Scale + SQLite Profile) | `/api/v1/risk/calculate`, `/api/v1/risk/profile` | Verified |
| 11 | Pro Backtesting, Walk-Forward, Multi-TF Matrix & Validation Gate | `/api/v1/backtest/pro/run`, `/api/v1/backtest/pro/strategies`, `/api/v1/backtest/run`, `/api/v1/backtest/history` | Verified |
| 12 | Virtual Paper Trading (`VIRTUAL USDT`, Auto SL/TP, Fee/Slippage) | `/api/v1/paper/*` | Verified |
| 13 | Official Macro Economic News & High-Impact Warnings (Fed, BLS CPI/PPI/NFP/Unemp, ECB, BoE, FF) | `/api/v1/calendar/macro`, `/api/v1/calendar/events` | Verified |
| 14 | Settings (+ Preserved System Health, Logs, Android HTTPS Origin & ZIP Backup) | `/api/v1/settings`, `/download/qazan-project-backup.zip` | Verified |
| 15 | Open-Source Release, Docker, CI & Secret Hygiene | `LICENSE`, `README.md`, `README.ar.md`, `SECURITY.md`, `docker-compose.yml`, `.github/workflows/ci.yml` | Verified (Runtime Docker/Gradle/EXE require host toolchains; see notes) |

## Verification Matrix (Phase 10)
- **Full Pytest Suite (`pytest backend/tests -v`):** Covers Phases 1–10 (`test_foundation.py`, `test_phase2_platform.py`, `test_technical_engine.py`, `test_probability_engine.py`, `test_market_ingestion.py`, `test_trade_discovery.py`, `test_pro_backtest_paper.py`, `test_macro_news.py`, and `test_release_open_source.py`).
- **Frontend Build & TypeCheck:** `npm run lint` (`tsc --noEmit`) and `npm run build` (`vite build`) pass with **0 errors**.
- **Capacitor Sync:** `npm run cap:sync` syncs clean `dist/` assets into `android/app/src/main/assets/public/` with zero cloud-builder preview URLs.
- **Clean Distribution ZIP:** `python3 scripts/create_project_backup.py` generates `backups/QAZAN-AI-TRADING-PRO-MAX-v1.0.0-open-source.zip` passing `zipfile -t` with zero secrets, `.env`, `.keystore`, `.db`, or `node_modules`.
- **Environment Constraints (Honest Reporting):**
  - `docker` CLI/daemon, `java` (JDK 21) / Android SDK (`gradlew`), and Windows `.exe` packaging toolchains are **not installed** in the current Linux container runtime, so `docker compose build`, `gradlew assembleDebug`, and Windows `.exe` packaging were **not executed inside this container** and are configured in `.github/workflows/ci.yml` + `ANDROID_APK_GUIDE.md` for local or GitHub Actions execution.

## Regression Policy
- All Phase 1–9 suites plus `test_release_open_source.py` must remain 100% passing.
- Zero hardcoded cloud preview URLs, paid AI SDK dependencies, or exposed secrets may appear in source files or release ZIP exports.
- Existing SQLite databases (`backend/database.db` / `backend/data/qazan_trading.db`) and user trading/risk/paper settings must remain untouched across maintenance updates.
