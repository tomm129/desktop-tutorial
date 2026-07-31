"""Configuração centralizada via pydantic-settings (.env + defaults)."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class CollectionSettings(BaseModel):
    interval_seconds: int = 900
    # 50 dias => 300 candles de 4h no primeiro boot: 200 de warm-up das
    # features (ma_200) + 50 do rolling do regime detector, com folga
    backfill_days: int = 50
    # Margem após o fechamento do candle antes de coletar (evita candle ainda aberto)
    sync_margin_seconds: int = 5
    max_retries: int = 4
    fetch_limit: int = 1000


class PaperTradingSettings(BaseModel):
    enabled: bool = True


class DatabaseSettings(BaseModel):
    path: str = "data/crypto_bot.duckdb"
    backup_dir: str = "data/backups"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CRYPTOBOT_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Binance Futures perpétuos USDT-M (símbolos unificados CCXT)
    symbols: list[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes: list[str] = ["15m", "1h", "4h"]

    telegram: TelegramSettings = TelegramSettings()
    collection: CollectionSettings = CollectionSettings()
    paper_trading: PaperTradingSettings = PaperTradingSettings()
    database: DatabaseSettings = DatabaseSettings()


SETTINGS = Settings()


def timeframe_to_seconds(timeframe: str) -> int:
    """Converte '15m'/'1h'/'4h'/'1d' em segundos."""
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    factor = {"m": 60, "h": 3600, "d": 86400}
    if unit not in factor:
        raise ValueError(f"Timeframe inválido: {timeframe}")
    return value * factor[unit]
