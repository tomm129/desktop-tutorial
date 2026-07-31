"""Pipeline candles → features → regimes.

Garante o contrato do rules_detector (bug 7 do STATUS.md): o detector recebe
sempre o DataFrame de candles JOINED com as features necessárias.
"""

from __future__ import annotations

import pandas as pd
import structlog

from crypto_bot.features.regime.rules_detector import RulesRegimeDetector
from crypto_bot.features.technical import TechnicalFeatures
from crypto_bot.storage.database import Database, db as default_db

logger = structlog.get_logger(__name__)

# Features que o rules_detector exige (além das colunas de candles)
_DETECTOR_FEATURES = ["candle_id", "atr_14", "volume_sma_20", "momentum_10", "ma_20"]


class FeaturePipeline:
    """Calcula e persiste features e regimes para os candles mais recentes."""

    def __init__(self, db: Database | None = None, lookback: int = 500) -> None:
        self.db = db or default_db
        self.lookback = lookback

    def run(self, symbol: str, timeframe: str) -> tuple[int, int]:
        """Roda features + regimes de um par/timeframe. Retorna (n_features, n_regimes)."""
        candles = self.db.query(
            """
            SELECT * FROM (
                SELECT id, symbol, timeframe, timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ) ORDER BY timestamp ASC
            """,
            [symbol, timeframe, self.lookback],
        )

        feats = TechnicalFeatures.calculate(candles)
        if feats.empty:
            logger.debug(
                "pipeline.insufficient_candles",
                symbol=symbol,
                timeframe=timeframe,
                count=len(candles),
            )
            return 0, 0

        n_features = self.db.upsert_dataframe(feats, "features", ["candle_id"])

        # Contrato do detector: candles JOIN features
        joined = candles.merge(
            feats[_DETECTOR_FEATURES], left_on="id", right_on="candle_id", how="inner"
        )
        regimes = RulesRegimeDetector.detect(joined)
        n_regimes = (
            self.db.upsert_dataframe(regimes, "regimes", ["candle_id"])
            if not regimes.empty
            else 0
        )

        logger.info(
            "pipeline.complete",
            symbol=symbol,
            timeframe=timeframe,
            features_inserted=n_features,
            regimes_inserted=n_regimes,
        )
        return n_features, n_regimes
