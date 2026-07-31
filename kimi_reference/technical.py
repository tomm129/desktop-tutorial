"""Technical feature engineering."""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional

import talib

class TechnicalFeatures:
    """Calculates technical indicators for a DataFrame of candles."""

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical features."""
        if len(df) < 200:
            return pd.DataFrame()

        df = df.copy().sort_values("timestamp")
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        features = pd.DataFrame({"candle_id": df["id"].values})
        features["timestamp"] = df["timestamp"].values
        features["symbol"] = df["symbol"].values
        features["timeframe"] = df["timeframe"].values

        # RSI
        features["rsi_14"] = talib.RSI(close, timeperiod=14)
        features["rsi_7"] = talib.RSI(close, timeperiod=7)

        # Moving Averages
        features["ma_20"] = talib.SMA(close, timeperiod=20)
        features["ma_50"] = talib.SMA(close, timeperiod=50)
        features["ma_200"] = talib.SMA(close, timeperiod=200)
        features["ema_12"] = talib.EMA(close, timeperiod=12)
        features["ema_26"] = talib.EMA(close, timeperiod=26)

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        features["bb_upper"] = bb_upper
        features["bb_middle"] = bb_middle
        features["bb_lower"] = bb_lower
        features["bb_width"] = (bb_upper - bb_lower) / bb_middle

        # ATR
        features["atr_14"] = talib.ATR(high, low, close, timeperiod=14)
        features["atr_percent"] = features["atr_14"] / close * 100

        # Momentum
        features["momentum_10"] = talib.MOM(close, timeperiod=10)
        features["momentum_20"] = talib.MOM(close, timeperiod=20)

        # Volatility
        features["volatility_20"] = pd.Series(close).rolling(20).std().values / close * 100
        features["volatility_50"] = pd.Series(close).rolling(50).std().values / close * 100

        # Volume
        features["volume_sma_20"] = talib.SMA(volume, timeperiod=20)
        features["volume_ratio"] = volume / features["volume_sma_20"]

        # OBV
        features["obv"] = talib.OBV(close, volume)

        # Price action
        features["body_size"] = abs(close - df["open"].values) / close * 100
        features["upper_shadow"] = (df["high"].values - np.maximum(close, df["open"].values)) / close * 100
        features["lower_shadow"] = (np.minimum(close, df["open"].values) - df["low"].values) / close * 100
        features["range_pct"] = (df["high"].values - df["low"].values) / close * 100

        features["calculated_at"] = pd.Timestamp.now(tz="UTC")

        return features.dropna()
