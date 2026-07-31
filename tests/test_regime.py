"""Regime detector: séries sintéticas de tendência clara e lateralização."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_bot.features.pipeline import _DETECTOR_FEATURES
from crypto_bot.features.regime.rules_detector import RulesRegimeDetector
from crypto_bot.features.technical import TechnicalFeatures


def _candles_from_prices(prices: np.ndarray, spread: float = 0.001) -> pd.DataFrame:
    n = len(prices)
    close = np.asarray(prices, dtype=float)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    return pd.DataFrame(
        {
            "id": np.arange(1, n + 1),
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(n, 10.0),
        }
    )


def _detect(prices: np.ndarray) -> pd.DataFrame:
    candles = _candles_from_prices(prices)
    feats = TechnicalFeatures.calculate(candles)
    joined = candles.merge(feats[_DETECTOR_FEATURES], left_on="id", right_on="candle_id")
    return RulesRegimeDetector.detect(joined)


def test_uptrend_detected_as_bull():
    rng = np.random.default_rng(7)
    prices = np.linspace(100, 200, 400) + rng.normal(0, 0.2, 400)
    regimes = _detect(prices)
    assert not regimes.empty
    tail = regimes.tail(50)
    assert (tail["trend"] == "TREND_BULL").mean() > 0.8


def test_downtrend_detected_as_bear():
    rng = np.random.default_rng(7)
    prices = np.linspace(200, 100, 400) + rng.normal(0, 0.2, 400)
    regimes = _detect(prices)
    tail = regimes.tail(50)
    assert (tail["trend"] == "TREND_BEAR").mean() > 0.8


def test_sideways_detected_as_range():
    rng = np.random.default_rng(7)
    prices = 100 + rng.normal(0, 0.3, 400)
    regimes = _detect(prices)
    tail = regimes.tail(50)
    assert (tail["trend"] == "RANGE").mean() > 0.6


def test_contract_enforced():
    """bug 7: entrada sem as features do contrato deve falhar com erro claro."""
    candles = _candles_from_prices(np.full(100, 100.0))
    with pytest.raises(ValueError, match="candles JOIN features"):
        RulesRegimeDetector.detect(candles)


def test_no_nan_categories_in_output():
    rng = np.random.default_rng(7)
    prices = 100 + rng.normal(0, 0.3, 400)
    regimes = _detect(prices)
    for col in ["trend", "volatility", "volume_state", "momentum_state", "composite"]:
        assert not regimes[col].str.contains("nan").any()
