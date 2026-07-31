"""Quality gate: cenários fresh/stale/gap e tolerância por timeframe (bug 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from crypto_bot.monitoring.health import DataQualityGate
from tests.conftest import insert_candles, make_candles

SYMBOL = "BTC/USDT:USDT"


def _add_features_and_regimes(db, candles: pd.DataFrame) -> None:
    """Insere linhas mínimas em features/regimes para satisfazer os checks 4 e 5."""
    last = candles.iloc[-1]
    db.execute(
        "INSERT INTO features (candle_id, timestamp, symbol, timeframe, rsi_14) VALUES (?, ?, ?, ?, ?)",
        [int(last["id"]), last["timestamp"], last["symbol"], last["timeframe"], 50.0],
    )
    db.execute(
        "INSERT INTO regimes (candle_id, timestamp, symbol, timeframe, trend) VALUES (?, ?, ?, ?, ?)",
        [int(last["id"]), last["timestamp"], last["symbol"], last["timeframe"], "RANGE"],
    )


def test_fresh_data_passes(db):
    now = datetime.now(timezone.utc)
    candles = insert_candles(db, make_candles(timeframe="15m", n=20, end=now))
    _add_features_and_regimes(db, candles)

    ok, failures = DataQualityGate(db=db).check_all(SYMBOL, "15m")
    assert ok, failures


def test_stale_data_fails(db):
    stale_end = datetime.now(timezone.utc) - timedelta(hours=3)
    candles = insert_candles(db, make_candles(timeframe="15m", n=20, end=stale_end))
    _add_features_and_regimes(db, candles)

    ok, failures = DataQualityGate(db=db).check_all(SYMBOL, "15m")
    assert not ok
    assert any("Stale" in f for f in failures)


def test_timeframe_tolerance_bug1(db):
    """Candle de 1h com 50min de idade é OK (com 120s fixos, falharia)."""
    end = datetime.now(timezone.utc) - timedelta(minutes=50)
    candles = insert_candles(db, make_candles(timeframe="1h", n=20, end=end))
    _add_features_and_regimes(db, candles)

    gate = DataQualityGate(db=db)
    assert gate.max_age_seconds("1h") == 1.5 * 3600 + 60
    ok, failures = gate.check_all(SYMBOL, "1h")
    assert ok, failures


def test_gap_detected(db):
    now = datetime.now(timezone.utc)
    df = make_candles(timeframe="15m", n=10, end=now)
    df = df.drop(index=[6, 7])  # buraco de 2 candles
    candles = insert_candles(db, df)
    _add_features_and_regimes(db, candles)

    ok, failures = DataQualityGate(db=db).check_all(SYMBOL, "15m")
    assert not ok
    assert any("Gaps" in f for f in failures)


def test_empty_db_fails(db):
    ok, failures = DataQualityGate(db=db).check_all(SYMBOL, "15m")
    assert not ok
    assert any("No candles" in f for f in failures)
