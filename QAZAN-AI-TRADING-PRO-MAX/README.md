# QAZAN-AI-TRADING-PRO-MAX

> **Language / اللغة:** **English** · [العربية (`README.ar.md`)](./README.ar.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-D4AF37.svg)](./LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.0.0--open--source-10B981.svg)](./CHANGELOG.md)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLite%20%2B%20Local%20ML-0B0F17.svg)](#architecture)
[![Android](https://img.shields.io/badge/Android-Capacitor%20v8-3DDC84.svg)](./ANDROID_APK_GUIDE.md)

**QAZAN-AI-TRADING-PRO-MAX** is a fully open-source, self-hosted quantitative trading analysis, backtesting, macro-economic intelligence, and virtual paper-trading platform. It runs **100% independently** of cloud app builders or paid AI/market API keys — powered by local machine learning (**Scikit-learn** & **XGBoost**), a strictly causal multi-timeframe technical engine, keyless public exchange & central-bank feeds, **SQLite (WAL)** persistence, and a native **Capacitor Android** build.

---

## Key Features (Phases 1–10)

1. **Institutional Split-Terminal Dashboard**: Live portfolio telemetry, embedded TradingView Lightweight Charts v5, local ML directional bias, and an unobtrusive pre-event macro volatility strip.
2. **Real Keyless Market Data Ingestion & WebSocket Stream**: Live Binance Spot/Futures REST & WebSocket streams (`@aggTrade`, `!forceOrder@arr`), OKX/CoinGecko/CoinPaprika public fallbacks, OHLCV gap validation, and dynamic pair registry (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `ADAUSDT`, plus user-added symbols).
3. **Causal Multi-Timeframe Technical Engine (`1W / 1D / 4H` + LTF)**: Zero look-ahead bias analysis detecting `HH/HL/LH/LL`, `BOS`/`CHoCH`, Supply & Demand, Order Blocks, Breaker Blocks, FVG, EQH/EQL, Liquidity Sweeps, and `BREAKOUT` vs `FAKEOUT` vs `STOP_HUNT`.
4. **Walk-Forward Next-Candle Probability Engine**: 9-domain causal feature extraction calibrated against Markov/empirical baselines with out-of-sample **Brier Score**, **Log Loss**, ATR quantile range envelopes, and strict `INSUFFICIENT_DATA` protection.
5. **Dual-Hypothesis Trade Discovery & Risk Governance**: Evaluates `LONG` / `SHORT` / `NO_TRADE` with `1%` default risk, `3%` daily loss circuit-breaker, fee & slippage deduction, SHA-256 deduplication, and strict `NO LIVE ORDERS` execution safety lock.
6. **Pro Backtesting & Mandatory Validation Gate**: Multi-timeframe (`15m`, `1h`, `4h`, `1d`) simulation with expanding Walk-Forward OOS testing, Win Rate, Profit Factor, Max Drawdown, Expectancy, Sharpe/Sortino, fee/slippage friction, and strict 6-gate validation blocking unproven strategies from being labeled successful.
7. **Virtual Paper Trading (`VIRTUAL USDT`)**: Real-time mark-to-market virtual portfolio with custom capital resets, directional SL/TP validation, automatic SL/TP triggers, and fee/slippage accounting.
8. **Official Macro Economic Calendar**: Aggregates real schedules and releases from the **Federal Reserve (FOMC)**, **US BLS (CPI, PPI, NFP, Unemployment)**, **ECB**, **Bank of England**, and public weekly consensus feeds with `CRITICAL` / `ELEVATED` / `WATCH` pre-event warnings (`fabricated_events_count = 0`).
9. **Native Android App (Capacitor v8)**: Installable Android project (`com.qazan.tradingpromax`) with custom metallic-gold launcher icons, QAZAN splash screen, DayNight status-bar sync, strict HTTPS `network_security_config.xml`, offline handling, and `SharedPreferences` persistence.
10. **Open-Source Self-Hosted Packaging**: Docker & Docker Compose support, cross-platform local startup scripts, MIT license, GitHub Actions CI, secret-hygiene verification, and one-click full ZIP export.

---

## Architecture

```text
QAZAN-AI-TRADING-PRO-MAX/
├── backend/                     # FastAPI + SQLite (WAL) + Local ML + Causal Quant Engine
│   ├── app/
│   │   ├── api/v1/router.py     # REST & WebSocket endpoints (/api/v1/*)
│   │   ├── core/                # Pydantic Settings, logging, structured exceptions
│   │   ├── db/database.py       # 15-table SQLite schema with self-healing init
│   │   ├── engine/              # Causal multi-timeframe SMC/ICT engine & CLI
│   │   ├── ml/                  # RandomForest, XGBoost, Walk-Forward probability engine
│   │   ├── schemas/             # Strict Pydantic v2 contracts
│   │   └── services/            # Ingestion, discovery, pro backtest, paper trading, macro news
│   ├── tests/                   # 8+ Pytest suites covering Phases 1–10
│   └── requirements.txt
├── src/                         # React 19 + TypeScript + Tailwind CSS v4 + Lightweight Charts v5
│   ├── api/                     # Typed HTTP & platform API clients
│   ├── components/              # AppShell, Charts, 14 Terminal Sections & Quant Views
│   ├── contexts/AppContext.tsx  # Arabic (RTL)/English (LTR), Dark/Light, Native state
│   ├── i18n/                    # Complete bilingual dictionaries (ar & en)
│   └── services/nativePlatform.ts
├── android/                     # Native Capacitor v8 Android Gradle project (SDK 36 / minSdk 24)
├── docker/nginx.conf            # Nginx reverse proxy (HTTP + WebSocket upgrade)
├── scripts/
│   ├── create_project_backup.py # Clean ZIP packager (excludes secrets, DBs, build caches)
│   ├── start-local.sh           # Linux/macOS quick-start launcher
│   └── start-local.bat          # Windows quick-start launcher
├── .github/workflows/ci.yml     # GitHub Actions CI (Lint, Build, Pytest, Docker, Android APK)
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── server.ts                    # Unified Node/Express gateway (port 3000 -> FastAPI 8001)
├── capacitor.config.ts
├── ANDROID_APK_GUIDE.md
├── LICENSE                      # MIT License
├── README.md                    # English documentation
├── README.ar.md                 # Arabic documentation
└── SECURITY.md                  # Security & secret-rotation policy
```

---

## Prerequisites

- **Node.js** `>= 20.x` and **npm**
- **Python** `>= 3.10` (`3.11` recommended) and **pip**
- **Docker** & **Docker Compose** (optional, for containerized deployment)
- **JDK 21** + **Android SDK 36** (optional, only for building Android APK/AAB)

---

## Local Setup & Running

### Option A: One-Command Local Quick Start

- **Linux / macOS:**
  ```bash
  chmod +x scripts/start-local.sh
  ./scripts/start-local.sh
  ```
- **Windows (Command Prompt / PowerShell):**
  ```cmd
  scripts\start-local.bat
  ```

### Option B: Manual Step-by-Step Setup

1. **Create your local environment file (never commit `.env`):**
   ```bash
   cp .env.example .env
   ```
   > **Note:** If `api.binance.com` is geo-restricted in your region, set `MARKET_DATA_BASE_URL="https://data-api.binance.vision"` inside `.env`.

2. **Install Frontend & Gateway dependencies:**
   ```bash
   npm install
   ```

3. **Install Backend Python dependencies:**
   ```bash
   python3 -m pip install -r backend/requirements.txt
   ```
   *(You can also run `pip install -r requirements.txt` from the repository root.)*

4. **Start the Unified App (Web + API Gateway on `http://localhost:3000`):**
   ```bash
   npm run dev
   ```
   For production mode after building:
   ```bash
   npm run build
   npm start
   ```

### Option C: Decoupled Services (Two Terminals)

- **Terminal 1 (FastAPI Backend on port `8001`):**
  ```bash
  cd backend
  uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
  ```
- **Terminal 2 (Vite Frontend on port `3000`):**
  ```bash
  npx vite --host 0.0.0.0 --port 3000
  ```

### Option D: Docker & Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
```
- Web Terminal: `http://localhost:3000`
- FastAPI Docs (Swagger): `http://localhost:8001/docs`
- SQLite data persists inside the Docker volume `qazan_sqlite_data`.

---

## Automated Tests & Verification

Run all checks locally:
```bash
# TypeScript type-check
npm run lint

# Production frontend bundle
npm run build

# Full backend Pytest suite (Phases 1–10)
npm run backend:test

# Or run everything together
npm test
```

---

## Building the Android APK

Full instructions (Debug APK, Keystore generation, Release APK/AAB signing, and `apksigner` verification) are documented in [`ANDROID_APK_GUIDE.md`](./ANDROID_APK_GUIDE.md).

Quick Debug APK build (requires JDK 21 & Android SDK 36):
```bash
npm run cap:sync
npm run android:apk:debug
```

---

## Publishing Your Own Copy to GitHub

1. **Initialize Git & verify ignored files:**
   ```bash
   git init
   git status
   ```
   Confirm `.env`, `node_modules/`, `backups/`, `*.db`, and `*.keystore` are **not** listed as untracked files (protected by `.gitignore`).

2. **Create the initial commit & push:**
   ```bash
   git add .
   git commit -m "chore: release QAZAN-AI-TRADING-PRO-MAX v1.0.0-open-source"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/QAZAN-AI-TRADING-PRO-MAX.git
   git push -u origin main
   ```

3. **CI Pipeline:** GitHub Actions (`.github/workflows/ci.yml`) will automatically run Frontend Lint/Build, Backend Pytest, Docker Compose verification, and Android Debug APK assembly on every push or pull request.

---

## Security & Secret Hygiene

- No paid API keys, cloud builder tokens, or hardcoded personal credentials are required or included.
- See [`SECURITY.md`](./SECURITY.md) for secret-handling guidelines and remediation steps if a local secret or Android `.keystore` is ever committed accidentally.

## License

Released under the [MIT License](./LICENSE).
