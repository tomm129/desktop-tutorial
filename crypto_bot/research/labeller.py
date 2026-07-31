"""Rotulagem temporal estrita — future returns usando APENAS dados futuros.

Este módulo é o guardião contra look-ahead bias: todo future_return é calculado
a partir de candles com timestamp >= signal_timestamp + horizonte.

Correções sobre kimi_reference/labeller.py (STATUS.md):
- bug 5: upsert via anti-join (sem duplicatas em reprocessamento)
- bug 6: janela de rotulagem = maior horizonte + 1 candle do timeframe
         (não mais 2 dias fixos)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import structlog

from crypto_bot.config import SETTINGS, timeframe_to_seconds
from crypto_bot.storage.database import Database, db as default_db

logger = structlog.get_logger(__name__)


class TemporalLabeller:
    """Calculates future returns with STRICT temporal rules."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or default_db
        self.return_horizons = {
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }

    @property
    def max_horizon(self) -> timedelta:
        return max(self.return_horizons.values())

    def label_candle(self, candle: pd.Series) -> dict:
        """Label a single candle with future returns."""
        symbol = candle["symbol"]
        tf = candle["timeframe"]
        ts = pd.to_datetime(candle["timestamp"])

        signal_price = float(candle["close"])

        labels = {
            "candle_id": candle["id"],
            "symbol": symbol,
            "timeframe": tf,
            "timestamp": ts,
            "signal_price": signal_price,
        }

        for horizon_name, delta in self.return_horizons.items():
            future_ts = ts + delta
            future_price = self._get_future_price(symbol, tf, future_ts)

            if future_price is not None:
                ret = (future_price - signal_price) / signal_price
                labels[f"future_return_{horizon_name}"] = round(ret, 6)
            else:
                labels[f"future_return_{horizon_name}"] = None

        labels["label_populated_at"] = datetime.now(timezone.utc)
        labels["label_validated"] = True
        return labels

    def _get_future_price(
        self, symbol: str, timeframe: str, target_ts: datetime
    ) -> Optional[float]:
        """Fetch the close price of the first candle AFTER target_ts.

        STRICT: Only uses candles with timestamp >= target_ts.
        """
        result = self.db.query(
            """
            SELECT close
            FROM candles
            WHERE symbol = ?
              AND timeframe = ?
              AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            [symbol, timeframe, target_ts],
        )

        if result.empty:
            return None
        return float(result["close"].iloc[0])

    def run_batch(self, limit: int = 1000) -> int:
        """Label unlabelled candles in batches (por timeframe, janela = maior horizonte + 1 candle)."""
        now = datetime.now(timezone.utc)
        total = 0

        for timeframe in SETTINGS.timeframes:
            # bug 6 corrigido: rotula assim que existir dado futuro suficiente
            cutoff = now - (self.max_horizon + timedelta(seconds=timeframe_to_seconds(timeframe)))

            unlabelled = self.db.query(
                """
                SELECT c.id, c.symbol, c.timeframe, c.timestamp, c.close
                FROM candles c
                LEFT JOIN candle_labels cl ON c.id = cl.candle_id
                WHERE cl.candle_id IS NULL
                  AND c.timeframe = ?
                  AND c.timestamp < ?
                ORDER BY c.timestamp DESC
                LIMIT ?
                """,
                [timeframe, cutoff, limit],
            )

            if unlabelled.empty:
                continue

            logger.info(
                "labeller.batch.start", timeframe=timeframe, count=len(unlabelled)
            )

            labels_list = []
            for _, candle in unlabelled.iterrows():
                try:
                    labels_list.append(self.label_candle(candle))
                except Exception as e:
                    logger.error(
                        "labeller.candle_error",
                        candle_id=candle["id"],
                        error=str(e),
                    )

            if labels_list:
                df_labels = pd.DataFrame(labels_list)
                # bug 5 corrigido: anti-join em vez de append cego
                inserted = self.db.upsert_dataframe(df_labels, "candle_labels", ["candle_id"])
                total += inserted
                logger.info(
                    "labeller.batch.complete", timeframe=timeframe, labelled=inserted
                )

        if total == 0:
            logger.debug("labeller.no_unlabelled_candles")
        return total
