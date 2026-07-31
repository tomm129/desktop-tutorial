"""Fixtures compartilhadas — banco DuckDB isolado por teste e candles sintéticos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from crypto_bot.config import timeframe_to_seconds
from crypto_bot.storage.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(
        path=str(tmp_path / "test.duckdb"),
        backup_dir=str(tmp_path / "backups"),
    )
    yield database
    database.close()


def make_candles(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    n: int = 300,
    end: datetime | None = None,
    prices: np.ndarray | None = None,
    base_price: float = 100.0,
    volume: float = 10.0,
) -> pd.DataFrame:
    """Gera candles sintéticos consistentes terminando em `end` (inclusive)."""
    tf = timedelta(seconds=timeframe_to_seconds(timeframe))
    end = end or datetime.now(timezone.utc)
    timestamps = [end - tf * i for i in range(n - 1, -1, -1)]

    if prices is None:
        prices = np.full(n, base_price)
    close = np.asarray(prices, dtype=float)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * 1.001
    low = np.minimum(open_, close) * 0.999

    return pd.DataFrame(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def insert_candles(db: Database, df: pd.DataFrame) -> pd.DataFrame:
    """Insere candles e retorna a tabela com ids atribuídos."""
    db.insert_candles(df)
    return db.query("SELECT * FROM candles ORDER BY timestamp")
