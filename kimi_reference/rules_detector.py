"""Simple rule-based regime detection (Phase 2)."""

from __future__ import annotations

import pandas as pd
from typing import Optional

class RulesRegimeDetector:
    """Deterministic regime detection using ADX, ATR, volume, momentum."""

    @staticmethod
    def detect(df: pd.DataFrame) -> pd.DataFrame:
        """Detect regime for each candle using simple rules."""
        if len(df) < 50:
            return pd.DataFrame()

        df = df.copy().sort_values("timestamp")

        # Calculate ADX-like proxy (simplified)
        adx = _calculate_adx_proxy(df)

        # ATR percentile (rolling 50 periods)
        atr = df["atr_14"]
        atr_pct = atr.rolling(50).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100 if x.max() != x.min() else 50,
            raw=False,
        )

        # Volume percentile
        vol_sma = df["volume_sma_20"]
        vol_ratio = df["volume"] / vol_sma

        # Momentum
        mom = df["momentum_10"]

        regimes = pd.DataFrame({"candle_id": df["id"].values})
        regimes["timestamp"] = df["timestamp"].values
        regimes["symbol"] = df["symbol"].values

        # Trend: ADX > 25 = trend, < 20 = range
        regimes["trend"] = pd.cut(
            adx,
            bins=[-float("inf"), 20, 25, float("inf")],
            labels=["RANGE", "UNCERTAIN", "TREND"],
        ).astype(str)
        regimes["trend"] = regimes["trend"].replace("UNCERTAIN", "RANGE")

        # Refine trend direction using MA
        ma20 = df["ma_20"]
        close = df["close"]
        bull_mask = (regimes["trend"] == "TREND") & (close > ma20)
        bear_mask = (regimes["trend"] == "TREND") & (close < ma20)
        regimes.loc[bull_mask, "trend"] = "TREND_BULL"
        regimes.loc[bear_mask, "trend"] = "TREND_BEAR"

        # Volatility
        regimes["volatility"] = pd.cut(
            atr_pct,
            bins=[-float("inf"), 30, 70, float("inf")],
            labels=["LOW_VOL", "NORMAL", "HIGH_VOL"],
        ).astype(str)

        # Volume state
        regimes["volume_state"] = pd.cut(
            vol_ratio,
            bins=[-float("inf"), 0.8, 1.5, float("inf")],
            labels=["LOW_VOLUME", "NORMAL", "HIGH_VOLUME"],
        ).astype(str)

        # Momentum state
        regimes["momentum_state"] = pd.cut(
            mom,
            bins=[-float("inf"), -0.01, 0.01, float("inf")],
            labels=["NEGATIVE", "NEUTRAL", "POSITIVE"],
        ).astype(str)

        # Composite regime
        regimes["composite"] = (
            regimes["trend"] + "_"
            + regimes["volatility"] + "_"
            + regimes["volume_state"]
        )

        regimes["detected_at"] = pd.Timestamp.now(tz="UTC")

        return regimes.dropna()

def _calculate_adx_proxy(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simplified ADX calculation."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()

    return adx
