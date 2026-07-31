"""Coletor: validação, dedup, descarte do candle aberto e retry — com mock da API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from crypto_bot.collectors.candles import CandleCollector


class FakeExchange:
    """Mock de ccxt: devolve OHLCV pré-definido e conta chamadas."""

    def __init__(self, rows: list[list[float]], fail_times: int = 0) -> None:
        self.rows = rows
        self.fail_times = fail_times
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("simulated network failure")
        return [r for r in self.rows if r[0] >= (since or 0)][: limit or len(self.rows)]


def _rows(n: int, end: datetime, tf_minutes: int = 15, price: float = 100.0):
    """n candles fechados de 15m terminando em `end` (abertura do último)."""
    out = []
    for i in range(n - 1, -1, -1):
        ts = end - timedelta(minutes=tf_minutes * i)
        ms = int(ts.timestamp() * 1000)
        out.append([ms, price, price * 1.001, price * 0.999, price, 10.0])
    return out


def test_collect_inserts_closed_candles_only(db):
    now = datetime.now(timezone.utc)
    open_candle_ts = now.replace(second=0, microsecond=0)
    rows = _rows(10, end=open_candle_ts)  # o último ainda não fechou

    collector = CandleCollector(db=db, exchange=FakeExchange(rows))
    inserted = collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")

    assert inserted == 9  # candle aberto descartado
    stored = db.query("SELECT * FROM candles ORDER BY timestamp")
    assert stored["timestamp"].max().to_pydatetime() < now - timedelta(seconds=900)


def test_recollect_dedups(db):
    end = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = _rows(10, end=end)
    collector = CandleCollector(db=db, exchange=FakeExchange(rows))

    first = collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")
    second = collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")

    assert first == 10
    assert second == 0
    assert db.get_candle_count("BTC/USDT:USDT", "15m") == 10


def test_invalid_ohlc_dropped(db):
    end = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = _rows(5, end=end)
    rows[2][2] = 50.0  # high < low → inconsistente
    collector = CandleCollector(db=db, exchange=FakeExchange(rows))

    inserted = collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")
    assert inserted == 4


def test_retry_with_backoff(db, monkeypatch):
    monkeypatch.setattr("crypto_bot.collectors.candles.time.sleep", lambda s: None)
    end = datetime.now(timezone.utc) - timedelta(hours=1)
    exchange = FakeExchange(_rows(5, end=end), fail_times=2)
    collector = CandleCollector(db=db, exchange=exchange)

    inserted = collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")
    assert inserted == 5
    assert exchange.calls == 3  # 2 falhas + 1 sucesso


def test_retry_exhaustion_raises(db, monkeypatch):
    monkeypatch.setattr("crypto_bot.collectors.candles.time.sleep", lambda s: None)
    exchange = FakeExchange([], fail_times=99)
    collector = CandleCollector(db=db, exchange=exchange)

    with pytest.raises(RuntimeError, match="falhou após"):
        collector.collect_symbol_timeframe("BTC/USDT:USDT", "15m")


def test_collect_all_returns_minus_one_on_error(db, monkeypatch):
    monkeypatch.setattr("crypto_bot.collectors.candles.time.sleep", lambda s: None)
    monkeypatch.setattr("crypto_bot.collectors.candles.SETTINGS.symbols", ["BTC/USDT:USDT"])
    monkeypatch.setattr("crypto_bot.collectors.candles.SETTINGS.timeframes", ["15m"])
    exchange = FakeExchange([], fail_times=99)
    collector = CandleCollector(db=db, exchange=exchange)

    results = asyncio.run(collector.collect_all())
    assert results == {"BTC/USDT:USDT 15m": -1}
