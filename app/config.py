import os
from dataclasses import dataclass
from pathlib import Path

import yaml


CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.yaml"))


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG_PATH} must contain a YAML mapping")
    return data


_config = _load_config()


def _value(name: str, default):
    env_value = os.getenv(name.upper())
    if env_value is not None and env_value != "":
        return env_value
    return _config.get(name.lower(), default)


def _int_env(name: str, default: int) -> int:
    return int(_value(name, default))


def _float_env(name: str, default: float) -> float:
    return float(_value(name, default))


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(_value("DB_PATH", "data/market_rankings.sqlite3"))
    okx_base_url: str = str(_value("OKX_BASE_URL", "https://www.okx.com"))
    okx_ws_url: str = str(_value("OKX_WS_URL", "wss://ws.okx.com:8443/ws/v5/public"))
    quote_ccy: str = str(_value("QUOTE_CCY", "USDT"))
    collector_mode: str = str(_value("COLLECTOR_MODE", "rest")).lower()
    rest_requests_per_second: float = _float_env("REST_REQUESTS_PER_SECOND", 2.0)
    candles_limit: int = _int_env("CANDLES_LIMIT", 25)
    ranking_interval_seconds: int = _int_env("RANKING_INTERVAL_SECONDS", 600)
    instruments_refresh_seconds: int = _int_env("INSTRUMENTS_REFRESH_SECONDS", 3600)
    ws_subscribe_batch_size: int = _int_env("WS_SUBSCRIBE_BATCH_SIZE", 50)
    ws_reconnect_initial_seconds: int = _int_env("WS_RECONNECT_INITIAL_SECONDS", 5)
    ws_reconnect_max_seconds: int = _int_env("WS_RECONNECT_MAX_SECONDS", 60)


settings = Settings()
