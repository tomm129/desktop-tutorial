"""Features técnicas: colunas, sanidade e ausência de TA-Lib (bug 4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_bot.features.technical import TechnicalFeatures

EXPECTED_COLUMNS = {
    "candle_id", "timestamp", "symbol", "timeframe",
    "rsi_14", "rsi_7", "ma_20", "ma_50", "ma_200", "ema_12", "ema_26",
    "bb_upper", "bb_middle", "bb_lower", "bb_width",
    "atr_14", "atr_percent", "momentum_10", "momentum_20",
    "volatility_20", "volatility_50", "volume_sma_20", "volume_ratio",
    "obv", "body_size", "upper_shadow", "lower_shadow", "range_pct",
    "calculated_at",
}


def _df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + rng.uniform(0, 0.3, n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.3, n)
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
            "volume": rng.uniform(1, 100, n),
        }
    )


def test_no_talib_dependency():
    import crypto_bot.features.technical as mod

    assert "talib" not in mod.__dict__


def test_columns_match_reference():
    feats = TechnicalFeatures.calculate(_df())
    assert set(feats.columns) == EXPECTED_COLUMNS
    assert not feats.empty


def test_min_candles_guard():
    assert TechnicalFeatures.calculate(_df(n=150)).empty


def test_rsi_bounds():
    feats = TechnicalFeatures.calculate(_df())
    assert feats["rsi_14"].between(0, 100).all()
    assert feats["rsi_7"].between(0, 100).all()


def test_sma_correctness():
    df = _df()
    feats = TechnicalFeatures.calculate(df)
    expected = df["close"].rolling(20).mean()
    merged = feats.merge(
        pd.DataFrame({"id": df["id"], "expected": expected}),
        left_on="candle_id", right_on="id",
    )
    assert merged["ma_20"].values == pytest.approx(merged["expected"].values, rel=1e-9)


def test_bollinger_ordering():
    feats = TechnicalFeatures.calculate(_df())
    assert (feats["bb_upper"] >= feats["bb_middle"]).all()
    assert (feats["bb_middle"] >= feats["bb_lower"]).all()


def test_atr_positive():
    feats = TechnicalFeatures.calculate(_df())
    assert (feats["atr_14"] > 0).all()


def test_no_lookahead_in_features():
    """Alterar o último candle não pode mudar features de candles anteriores."""
    df = _df()
    feats_before = TechnicalFeatures.calculate(df)

    df2 = df.copy()
    df2.loc[df2.index[-1], ["open", "high", "low", "close"]] = [500, 600, 400, 550]
    feats_after = TechnicalFeatures.calculate(df2)

    check_cols = [c for c in EXPECTED_COLUMNS - {"calculated_at", "symbol", "timeframe", "timestamp", "candle_id"}]
    before = feats_before[feats_before["candle_id"] < df["id"].iloc[-1]]
    after = feats_after[feats_after["candle_id"] < df["id"].iloc[-1]]
    pd.testing.assert_frame_equal(
        before[check_cols].reset_index(drop=True),
        after[check_cols].reset_index(drop=True),
    )
