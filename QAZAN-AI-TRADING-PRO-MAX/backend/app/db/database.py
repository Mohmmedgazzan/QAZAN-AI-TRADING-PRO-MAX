from datetime import datetime, timezone
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import get_settings
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger

logger = get_logger("qazan.db")
_VERIFIED_DB_INODES: set[tuple[str, int]] = set()
_INITIALIZING_DB = False


def get_db_path() -> Path:
    return get_settings().resolved_db_path


@contextmanager
def get_db_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    global _INITIALIZING_DB
    target = db_path or get_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not _INITIALIZING_DB:
        cur_ino = target.stat().st_ino if target.exists() else -1
        key = (str(target), cur_ino)
        if key not in _VERIFIED_DB_INODES:
            _INITIALIZING_DB = True
            try:
                init_db(target)
                new_ino = target.stat().st_ino if target.exists() else -1
                _VERIFIED_DB_INODES.add((str(target), new_ino))
            finally:
                _INITIALIZING_DB = False

    conn = sqlite3.connect(str(target), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError("SQLite operation failed.", details=str(exc)) from exc
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                logger_name TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'backend',
                request_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_system_logs_created_at
                ON system_logs (created_at DESC);

            CREATE TABLE IF NOT EXISTS market_candles_cache (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (symbol, interval, open_time)
            );

            CREATE INDEX IF NOT EXISTS idx_candles_lookup
                ON market_candles_cache (symbol, interval, open_time DESC);

            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance_usdt REAL NOT NULL,
                initial_balance REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                leverage REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'OPEN',
                exit_price REAL,
                realized_pnl REAL,
                opened_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_paper_positions_status
                ON paper_positions (status, opened_at DESC);

            CREATE TABLE IF NOT EXISTS risk_profiles (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                account_balance REAL NOT NULL,
                risk_pct REAL NOT NULL,
                default_rr REAL NOT NULL,
                max_leverage REAL NOT NULL,
                max_daily_loss_pct REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                strategy TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                final_equity REAL NOT NULL,
                total_return_pct REAL NOT NULL,
                win_rate_pct REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                sharpe_ratio REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS economic_calendar_cache (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                country TEXT NOT NULL,
                event_date TEXT NOT NULL,
                impact TEXT NOT NULL,
                forecast TEXT,
                previous TEXT,
                actual TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS technical_analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                run_type TEXT NOT NULL,
                ltf_interval TEXT NOT NULL,
                market_bias TEXT NOT NULL,
                market_phase TEXT NOT NULL,
                market_regime TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tech_runs_created_at
                ON technical_analysis_runs (created_at DESC);

            CREATE TABLE IF NOT EXISTS probability_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                status TEXT NOT NULL,
                prob_up REAL,
                prob_down REAL,
                prob_sideways REAL,
                confidence_pct REAL,
                model_brier_score REAL,
                baseline_brier_score REAL,
                model_log_loss REAL,
                baseline_log_loss REAL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_prob_forecasts_created_at
                ON probability_forecasts (created_at DESC);

            CREATE TABLE IF NOT EXISTS tracked_symbols (
                symbol TEXT PRIMARY KEY,
                base_asset TEXT NOT NULL,
                quote_asset TEXT NOT NULL,
                source TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_metrics_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at_epoch REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_market_metrics_symbol
                ON market_metrics_cache (symbol, metric_type);

            CREATE TABLE IF NOT EXISTS trade_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                ltf_timeframe TEXT NOT NULL,
                decision TEXT NOT NULL,
                long_passed INTEGER NOT NULL,
                short_passed INTEGER NOT NULL,
                entry_zone_low REAL,
                entry_zone_high REAL,
                entry_price REAL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                gross_rr REAL,
                net_rr REAL,
                position_size_units REAL,
                position_notional_usdt REAL,
                risk_amount_usdt REAL,
                fee_cost_usdt REAL,
                slippage_cost_usdt REAL,
                daily_loss_used_pct REAL NOT NULL,
                daily_limit_breached INTEGER NOT NULL DEFAULT 0,
                is_duplicate INTEGER NOT NULL DEFAULT 0,
                invalidation_reason TEXT,
                payload_json TEXT NOT NULL,
                candle_time INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trade_opps_fp
                ON trade_opportunities (fingerprint, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_trade_opps_created
                ON trade_opportunities (created_at DESC);

            CREATE TABLE IF NOT EXISTS strategy_backtest_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                primary_interval TEXT NOT NULL,
                tested_timeframes_json TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                is_strategy_successful INTEGER NOT NULL DEFAULT 0,
                win_rate_pct REAL NOT NULL,
                profit_factor REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                expectancy_usdt REAL NOT NULL,
                expectancy_r REAL NOT NULL,
                realized_rr REAL NOT NULL,
                net_return_pct REAL NOT NULL,
                walk_forward_oos_return_pct REAL NOT NULL,
                total_fees_usdt REAL NOT NULL,
                total_slippage_usdt REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                saved_bookmark INTEGER NOT NULL DEFAULT 1,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_reports_created
                ON strategy_backtest_reports (created_at DESC);

            CREATE TABLE IF NOT EXISTS macro_news_events_cache (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                country TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_timestamp INTEGER NOT NULL,
                impact TEXT NOT NULL,
                previous TEXT,
                forecast TEXT,
                actual TEXT,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                is_official_source INTEGER NOT NULL DEFAULT 1,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_macro_news_ts
                ON macro_news_events_cache (event_timestamp ASC);
            """
        )

        # Safe incremental column upgrades on paper_positions for Phase 7 virtual execution accounting
        existing_paper_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(paper_positions)").fetchall()
        }
        if "entry_fee_usdt" not in existing_paper_cols:
            conn.execute("ALTER TABLE paper_positions ADD COLUMN entry_fee_usdt REAL NOT NULL DEFAULT 0.0")
        if "exit_fee_usdt" not in existing_paper_cols:
            conn.execute("ALTER TABLE paper_positions ADD COLUMN exit_fee_usdt REAL NOT NULL DEFAULT 0.0")
        if "slippage_cost_usdt" not in existing_paper_cols:
            conn.execute("ALTER TABLE paper_positions ADD COLUMN slippage_cost_usdt REAL NOT NULL DEFAULT 0.0")
        if "close_reason" not in existing_paper_cols:
            conn.execute("ALTER TABLE paper_positions ADD COLUMN close_reason TEXT")

        default_pairs = [
            ("BTCUSDT", "BTC", "USDT", "Default Institutional Pair", 1),
            ("ETHUSDT", "ETH", "USDT", "Default Institutional Pair", 1),
            ("SOLUSDT", "SOL", "USDT", "Default Institutional Pair", 1),
            ("BNBUSDT", "BNB", "USDT", "Default Institutional Pair", 1),
            ("XRPUSDT", "XRP", "USDT", "Default Institutional Pair", 1),
            ("ADAUSDT", "ADA", "USDT", "Default Institutional Pair", 1),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO tracked_symbols
                (symbol, base_asset, quote_asset, source, is_default, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(sym, base, quote, src, is_def, now_iso) for sym, base, quote, src, is_def in default_pairs],
        )

        # Ensure default paper trading account exists
        conn.execute(
            """
            INSERT OR IGNORE INTO paper_account (id, balance_usdt, initial_balance, updated_at)
            VALUES (1, 10000.0, 10000.0, ?)
            """,
            (now_iso,),
        )

        # Ensure default risk profile exists
        conn.execute(
            """
            INSERT OR IGNORE INTO risk_profiles
                (id, account_balance, risk_pct, default_rr, max_leverage, max_daily_loss_pct, updated_at)
            VALUES (1, 10000.0, 1.0, 2.0, 5.0, 3.0, ?)
            """,
            (now_iso,),
        )

    logger.info("SQLite database initialized at %s", str(db_path or get_db_path()))


def check_db_health(db_path: Path | None = None) -> dict:
    started = time.perf_counter()
    target = db_path or get_db_path()
    required_tables = {
        "system_logs",
        "market_candles_cache",
        "paper_account",
        "paper_positions",
        "risk_profiles",
        "backtest_runs",
        "app_settings",
        "economic_calendar_cache",
        "technical_analysis_runs",
        "probability_forecasts",
        "tracked_symbols",
        "market_metrics_cache",
        "trade_opportunities",
        "strategy_backtest_reports",
        "macro_news_events_cache",
    }
    with get_db_connection(target) as conn:
        existing_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        existing_names = {r["name"] for r in existing_rows}

    if not required_tables.issubset(existing_names):
        logger.warning("Detected missing SQLite tables (%s); running self-healing init_db().", sorted(required_tables - existing_names))
        init_db(target)

    with get_db_connection(target) as conn:
        row = conn.execute("SELECT sqlite_version() AS version, 1 AS ok").fetchone()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        logs_count = conn.execute("SELECT COUNT(*) AS cnt FROM system_logs").fetchone()["cnt"]
        cache_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM market_candles_cache"
        ).fetchone()["cnt"]
        paper_count = conn.execute("SELECT COUNT(*) AS cnt FROM paper_positions").fetchone()["cnt"]
        bt_count = conn.execute("SELECT COUNT(*) AS cnt FROM backtest_runs").fetchone()["cnt"]
        eng_count = conn.execute("SELECT COUNT(*) AS cnt FROM technical_analysis_runs").fetchone()["cnt"]
        prob_count = conn.execute("SELECT COUNT(*) AS cnt FROM probability_forecasts").fetchone()["cnt"]
        sym_count = conn.execute("SELECT COUNT(*) AS cnt FROM tracked_symbols").fetchone()["cnt"]
        metrics_cache_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM market_metrics_cache"
        ).fetchone()["cnt"]
        opps_count = conn.execute("SELECT COUNT(*) AS cnt FROM trade_opportunities").fetchone()["cnt"]
        strat_reports_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM strategy_backtest_reports"
        ).fetchone()["cnt"]
        macro_events_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM macro_news_events_cache"
        ).fetchone()["cnt"]

    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    return {
        "connected": bool(row and row["ok"] == 1),
        "sqlite_version": row["version"] if row else "unknown",
        "database_path": str(target),
        "latency_ms": latency_ms,
        "tables": [t["name"] for t in tables],
        "counts": {
            "system_logs": logs_count,
            "market_candles_cache": cache_count,
            "paper_positions": paper_count,
            "backtest_runs": bt_count,
            "technical_analysis_runs": eng_count,
            "probability_forecasts": prob_count,
            "tracked_symbols": sym_count,
            "market_metrics_cache": metrics_cache_count,
            "trade_opportunities": opps_count,
            "strategy_backtest_reports": strat_reports_count,
            "macro_news_events_cache": macro_events_count,
        },
    }
