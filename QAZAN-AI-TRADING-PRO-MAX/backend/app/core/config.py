import re
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlparse
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

_DEFAULT_URLS: dict[str, tuple[str, tuple[str, ...]]] = {
    "MARKET_DATA_BASE_URL": ("https://api.binance.com", ("http", "https")),
    "FUTURES_DATA_BASE_URL": ("https://fapi.binance.com", ("http", "https")),
    "OKX_PUBLIC_BASE_URL": ("https://www.okx.com", ("http", "https")),
    "COINGECKO_BASE_URL": ("https://api.coingecko.com", ("http", "https")),
    "COINPAPRIKA_BASE_URL": ("https://api.coinpaprika.com", ("http", "https")),
    "BINANCE_SPOT_WS_URL": ("wss://stream.binance.com:9443/stream", ("ws", "wss")),
    "BINANCE_FUTURES_WS_URL": ("wss://fstream.binance.com/ws/!forceOrder@arr", ("ws", "wss")),
}

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_RAW_URL_RE = re.compile(r"(?:https?|wss?)://[^\s)\]>'\"]+")


def sanitize_service_url(value: object, default_url: str, allowed_schemes: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        return default_url
    raw = value.strip()
    if not raw:
        return default_url

    md_match = _MARKDOWN_LINK_RE.search(raw)
    if md_match:
        raw = md_match.group(1).strip()

    url_match = _RAW_URL_RE.search(raw)
    candidate = (url_match.group(0) if url_match else raw).strip().rstrip(").,;'\"")
    if candidate.endswith("/") and allowed_schemes == ("http", "https"):
        candidate = candidate.rstrip("/")

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in allowed_schemes or not parsed.netloc:
        return default_url
    return candidate


class Settings(BaseSettings):
    APP_NAME: str = "QAZAN-AI-TRADING-PRO-MAX"
    APP_VERSION: str = "1.0.0-open-source"
    APP_ENV: str = "development"
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8001
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    SQLITE_DB_PATH: str = str(BACKEND_ROOT / "data" / "qazan_trading.db")
    LOG_FILE_PATH: str = str(BACKEND_ROOT / "logs" / "qazan_backend.log")

    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,capacitor://localhost,http://localhost,https://localhost"
    )
    MARKET_DATA_BASE_URL: str = "https://api.binance.com"
    FUTURES_DATA_BASE_URL: str = "https://fapi.binance.com"
    OKX_PUBLIC_BASE_URL: str = "https://www.okx.com"
    COINGECKO_BASE_URL: str = "https://api.coingecko.com"
    COINPAPRIKA_BASE_URL: str = "https://api.coinpaprika.com"
    BINANCE_SPOT_WS_URL: str = "wss://stream.binance.com:9443/stream"
    BINANCE_FUTURES_WS_URL: str = "wss://fstream.binance.com/ws/!forceOrder@arr"
    MARKET_DATA_TIMEOUT_SEC: float = 8.0
    ENABLE_BACKGROUND_WS: bool = True

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "MARKET_DATA_BASE_URL",
        "FUTURES_DATA_BASE_URL",
        "OKX_PUBLIC_BASE_URL",
        "COINGECKO_BASE_URL",
        "COINPAPRIKA_BASE_URL",
        "BINANCE_SPOT_WS_URL",
        "BINANCE_FUTURES_WS_URL",
        mode="before",
    )
    @classmethod
    def _validate_external_url(cls, value: object, info: ValidationInfo) -> str:
        default_url, schemes = _DEFAULT_URLS[info.field_name or "MARKET_DATA_BASE_URL"]
        return sanitize_service_url(value, default_url, schemes)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def resolved_db_path(self) -> Path:
        raw = Path(self.SQLITE_DB_PATH)
        if raw.is_absolute():
            return raw
        return (BACKEND_ROOT / raw).resolve()

    @property
    def resolved_log_path(self) -> Path:
        raw = Path(self.LOG_FILE_PATH)
        if raw.is_absolute():
            return raw
        return (BACKEND_ROOT / raw).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
