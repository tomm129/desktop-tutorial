"""Teste crítico: anti look-ahead do labeller com dados sintéticos.

Injeta um candle futuro com preço absurdo e prova que ele NÃO vaza para
labels de candles cujos horizontes terminam antes dele.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from crypto_bot.research.labeller import TemporalLabeller
from tests.conftest import insert_candles, make_candles

SPIKE_PRICE = 100_000.0
BASE_PRICE = 100.0


@pytest.fixture
def labelled_db(db, monkeypatch):
    """3 dias de candles 15m a preço constante, com um spike absurdo 26h atrás."""
    monkeypatch.setattr(
        "crypto_bot.research.labeller.SETTINGS.timeframes", ["15m"], raising=False
    )
    now = datetime.now(timezone.utc)
    n = 3 * 96  # 3 dias de candles 15m
    df = make_candles(timeframe="15m", n=n, end=now, base_price=BASE_PRICE)

    spike_ts = now - timedelta(hours=26)
    idx = (df["timestamp"] - spike_ts).abs().idxmin()
    spike_ts = df.loc[idx, "timestamp"].to_pydatetime()
    df.loc[idx, ["open", "high", "low", "close"]] = SPIKE_PRICE

    candles = insert_candles(db, df)
    labeller = TemporalLabeller(db=db)
    labelled = labeller.run_batch(limit=10_000)
    assert labelled > 0

    labels = db.query("SELECT * FROM candle_labels ORDER BY timestamp")
    return db, labeller, labels, spike_ts


def test_no_lookahead_before_horizon(labelled_db):
    """Candles cujo horizonte de 1d termina ANTES do spike não podem vê-lo."""
    _, _, labels, spike_ts = labelled_db
    unaffected = labels[
        (labels["timestamp"] + timedelta(days=1) < spike_ts)
        & (labels["signal_price"] == BASE_PRICE)
    ]
    assert len(unaffected) > 0
    for col in ["future_return_15m", "future_return_30m", "future_return_1h",
                "future_return_4h", "future_return_1d"]:
        vals = unaffected[col].dropna()
        assert (vals.abs() < 1e-9).all(), f"{col} vazou o spike para o passado!"


def test_spike_visible_only_at_exact_horizon(labelled_db):
    """O candle exatamente 1d antes do spike DEVE vê-lo no horizonte 1d — e só nele."""
    _, _, labels, spike_ts = labelled_db
    target = labels[labels["timestamp"] == spike_ts - timedelta(days=1)]
    assert len(target) == 1
    row = target.iloc[0]
    expected = (SPIKE_PRICE - BASE_PRICE) / BASE_PRICE
    assert row["future_return_1d"] == pytest.approx(expected, rel=1e-4)
    # Horizontes mais curtos terminam antes do spike → retorno 0
    for col in ["future_return_15m", "future_return_30m", "future_return_1h", "future_return_4h"]:
        assert abs(row[col]) < 1e-9


def test_short_horizon_boundary(labelled_db):
    """future_return_15m: só o candle 15min antes do spike o enxerga."""
    _, _, labels, spike_ts = labelled_db
    sees_it = labels[labels["timestamp"] == spike_ts - timedelta(minutes=15)]
    just_before = labels[labels["timestamp"] == spike_ts - timedelta(minutes=30)]
    assert len(sees_it) == 1 and len(just_before) == 1
    assert sees_it.iloc[0]["future_return_15m"] > 100
    assert abs(just_before.iloc[0]["future_return_15m"]) < 1e-9


def test_rerun_does_not_duplicate(labelled_db):
    """bug 5: reprocessar o batch não pode duplicar labels."""
    db, labeller, labels, _ = labelled_db
    count_before = len(labels)
    inserted_again = labeller.run_batch(limit=10_000)
    assert inserted_again == 0
    count_after = db.query("SELECT COUNT(*) AS n FROM candle_labels")["n"].iloc[0]
    assert count_after == count_before


def test_labelling_window_uses_max_horizon(db, monkeypatch):
    """bug 6: candles com mais de (1d + 1 candle) de idade são rotulados — não 2 dias."""
    monkeypatch.setattr(
        "crypto_bot.research.labeller.SETTINGS.timeframes", ["15m"], raising=False
    )
    now = datetime.now(timezone.utc)
    df = make_candles(timeframe="15m", n=2 * 96, end=now, base_price=BASE_PRICE)
    insert_candles(db, df)

    labeller = TemporalLabeller(db=db)
    labeller.run_batch(limit=10_000)
    labels = db.query("SELECT * FROM candle_labels")

    # Com o filtro antigo (2 dias) nada seria rotulado; agora candles entre
    # ~24h15m e 48h de idade devem ter label
    assert len(labels) > 0
    cutoff = now - (timedelta(days=1) + timedelta(minutes=15))
    assert (labels["timestamp"] <= cutoff).all()
