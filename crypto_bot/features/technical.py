"""Feature engineering técnico — implementação própria em pandas/numpy (sem TA-Lib).

Mantém os mesmos nomes de colunas do módulo de referência (kimi_reference/technical.py).
RSI e ATR usam suavização de Wilder (compatível com TA-Lib).

Anti look-ahead: todas as janelas são retrospectivas (rolling/ewm), nunca usam
dados posteriores ao timestamp do candle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI com suavização de Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # avg_loss == 0 → RSI 100 (sem perdas no período)
    out = out.where(avg_loss != 0, 100.0)
    out[avg_gain.isna() | avg_loss.isna()] = np.nan
    return out


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def bollinger(close: pd.Series, period: int = 20, ndev: float = 2.0):
    middle = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    return middle + ndev * std, middle, middle - ndev * std


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR com suavização de Wilder."""
    prev_close = close.shift()
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def momentum(close: pd.Series, period: int) -> pd.Series:
    return close.diff(period)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


class TechnicalFeatures:
    """Calcula indicadores técnicos para um DataFrame de candles.

    Contrato de entrada: colunas id, symbol, timeframe, timestamp, open, high,
    low, close, volume. Mínimo de 200 candles (ma_200).
    """

    MIN_CANDLES = 200

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical features."""
        if len(df) < TechnicalFeatures.MIN_CANDLES:
            return pd.DataFrame()

        df = df.copy().sort_values("timestamp").reset_index(drop=True)
        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]
        volume = df["volume"]

        features = pd.DataFrame({"candle_id": df["id"].values})
        features["timestamp"] = df["timestamp"].values
        features["symbol"] = df["symbol"].values
        features["timeframe"] = df["timeframe"].values

        # RSI
        features["rsi_14"] = rsi(close, 14).values
        features["rsi_7"] = rsi(close, 7).values

        # Moving Averages
        features["ma_20"] = sma(close, 20).values
        features["ma_50"] = sma(close, 50).values
        features["ma_200"] = sma(close, 200).values
        features["ema_12"] = ema(close, 12).values
        features["ema_26"] = ema(close, 26).values

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = bollinger(close, 20, 2.0)
        features["bb_upper"] = bb_upper.values
        features["bb_middle"] = bb_middle.values
        features["bb_lower"] = bb_lower.values
        features["bb_width"] = ((bb_upper - bb_lower) / bb_middle).values

        # ATR
        atr_14 = atr(high, low, close, 14)
        features["atr_14"] = atr_14.values
        features["atr_percent"] = (atr_14 / close * 100).values

        # Momentum
        features["momentum_10"] = momentum(close, 10).values
        features["momentum_20"] = momentum(close, 20).values

        # Volatility
        features["volatility_20"] = (close.rolling(20).std() / close * 100).values
        features["volatility_50"] = (close.rolling(50).std() / close * 100).values

        # Volume
        vol_sma = sma(volume, 20)
        features["volume_sma_20"] = vol_sma.values
        features["volume_ratio"] = (volume / vol_sma).values

        # OBV
        features["obv"] = obv(close, volume).values

        # Price action
        features["body_size"] = ((close - open_).abs() / close * 100).values
        features["upper_shadow"] = ((high - pd.concat([close, open_], axis=1).max(axis=1)) / close * 100).values
        features["lower_shadow"] = ((pd.concat([close, open_], axis=1).min(axis=1) - low) / close * 100).values
        features["range_pct"] = ((high - low) / close * 100).values

        features["calculated_at"] = pd.Timestamp.now(tz="UTC")

        return features.dropna()
