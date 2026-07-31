"""Strict temporal labeller — future returns using ONLY future data.

This module is the guardian against look-ahead bias.
Every future_return is calculated from candles with timestamp > signal_timestamp.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd
import structlog

from crypto_bot.storage.database import db

logger = structlog.get_logger(__name__)

class TemporalLabeller:
    """Calculates future returns with STRICT temporal rules."""

    def __init__(self) -> None:
        self.return_horizons = {
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }

    def label_candle(self, candle: pd.Series) -> dict:
        """Label a single candle with future returns."""
        symbol = candle["symbol"]
        tf = candle["timeframe"]
        ts = pd.to_datetime(candle["timestamp"])

        # Get the candle's close price (signal price)
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
        result = db.query(
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
        """Label unlabelled candles in batches."""
        # Find candles without labels
        unlabelled = db.query(
            """
            SELECT c.id, c.symbol, c.timeframe, c.timestamp, c.close
            FROM candles c
            LEFT JOIN candle_labels cl ON c.id = cl.candle_id
            WHERE cl.candle_id IS NULL
              AND c.timestamp < ?  -- Only label candles old enough to have future data
            ORDER BY c.timestamp DESC
            LIMIT ?
            """,
            [
                datetime.now(timezone.utc) - timedelta(days=2),
                limit,
            ],
        )

        if unlabelled.empty:
            logger.debug("labeller.no_unlabelled_candles")
            return 0

        logger.info("labeller.batch.start", count=len(unlabelled))

        # Create labels table if not exists
        db.execute("""
            CREATE TABLE IF NOT EXISTS candle_labels (
                candle_id BIGINT PRIMARY KEY REFERENCES candles(id),
                symbol VARCHAR(20),
                timeframe VARCHAR(10),
                timestamp TIMESTAMP,
                signal_price DOUBLE,
                future_return_15m DOUBLE,
                future_return_30m DOUBLE,
                future_return_1h DOUBLE,
                future_return_4h DOUBLE,
                future_return_1d DOUBLE,
                label_populated_at TIMESTAMP,
                label_validated BOOLEAN
            )
        """)

        labels_list = []
        for _, candle in unlabelled.iterrows():
            try:
                label = self.label_candle(candle)
                labels_list.append(label)
            except Exception as e:
                logger.error(
                    "labeller.candle_error",
                    candle_id=candle["id"],
                    error=str(e),
                )

        if labels_list:
            df_labels = pd.DataFrame(labels_list)
            db.insert_dataframe(df_labels, "candle_labels", if_exists="append")

        logger.info("labeller.batch.complete", labelled=len(labels_list))
        return len(labels_list)
