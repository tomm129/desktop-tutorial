"""Data Quality Gate — valida os dados antes de QUALQUER decisão.

Correção sobre kimi_reference/health.py (bug 1 do STATUS.md):
tolerância de idade por timeframe (1.5 × tf_seconds + 60s), não 120s fixo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

import structlog

from crypto_bot.config import timeframe_to_seconds
from crypto_bot.storage.database import Database, db as default_db

logger = structlog.get_logger(__name__)


class DataQualityGate:
    """Validates data freshness and integrity. Returns NO_TRADE if invalid."""

    # Margem fixa somada à tolerância proporcional ao timeframe
    AGE_MARGIN_SECONDS = 60
    AGE_FACTOR = 1.5

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or default_db

    def max_age_seconds(self, timeframe: str) -> float:
        """bug 1 corrigido: um candle de 15m pode ter até ~22.5min; um de 1h, ~1.5h."""
        return self.AGE_FACTOR * timeframe_to_seconds(timeframe) + self.AGE_MARGIN_SECONDS

    def check_all(self, symbol: str, timeframe: str) -> Tuple[bool, List[str]]:
        """Run all data quality checks. Returns (pass, list_of_failures)."""
        failures = []

        # Check 1: Candles exist
        count = self.db.get_candle_count(symbol, timeframe)
        if count == 0:
            failures.append(f"No candles for {symbol}/{timeframe}")

        # Check 2: Freshness (tolerância por timeframe)
        # timestamp do candle é a ABERTURA; idade conta a partir do fechamento,
        # senão o último candle fechado de 1h pareceria "stale" logo após fechar
        last_ts = self.db.get_last_candle_timestamp(symbol, timeframe)
        if last_ts is None:
            failures.append(f"No timestamp for {symbol}/{timeframe}")
        else:
            close_ts = last_ts.timestamp() + timeframe_to_seconds(timeframe)
            age = datetime.now(timezone.utc).timestamp() - close_ts
            if age > self.max_age_seconds(timeframe):
                failures.append(
                    f"Stale data: {symbol}/{timeframe} last candle is {age:.0f}s old "
                    f"(max {self.max_age_seconds(timeframe):.0f}s)"
                )

        # Check 3: Gap detection (last 10 candles)
        gaps = self._check_recent_gaps(symbol, timeframe)
        if gaps:
            failures.append(f"Gaps detected: {gaps}")

        # Check 4: Feature availability
        if not self._check_features(symbol, timeframe):
            failures.append(f"Missing features for {symbol}/{timeframe}")

        # Check 5: Regime availability
        if not self._check_regime(symbol, timeframe):
            failures.append(f"Missing regime for {symbol}/{timeframe}")

        passed = len(failures) == 0
        if not passed:
            logger.warning(
                "health.quality_gate.failed",
                symbol=symbol,
                timeframe=timeframe,
                failures=failures,
            )

        return passed, failures

    def _check_recent_gaps(self, symbol: str, timeframe: str, n: int = 10) -> List[dict]:
        """Check for gaps in the last N candles."""
        result = self.db.query(
            """
            SELECT timestamp
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [symbol, timeframe, n],
        )

        if len(result) < 2:
            return []

        tf_seconds = timeframe_to_seconds(timeframe)
        gaps = []

        for i in range(len(result) - 1):
            diff = (result.iloc[i]["timestamp"] - result.iloc[i + 1]["timestamp"]).total_seconds()
            if diff > tf_seconds * 1.5:
                gaps.append({
                    "between": str(result.iloc[i + 1]["timestamp"]),
                    "and": str(result.iloc[i]["timestamp"]),
                    "gap_seconds": diff - tf_seconds,
                })

        return gaps

    def _check_features(self, symbol: str, timeframe: str) -> bool:
        """Check if features exist for this symbol/timeframe."""
        result = self.db.query(
            """
            SELECT 1
            FROM features f
            JOIN candles c ON f.candle_id = c.id
            WHERE c.symbol = ? AND c.timeframe = ?
            ORDER BY c.timestamp DESC
            LIMIT 1
            """,
            [symbol, timeframe],
        )
        return not result.empty

    def _check_regime(self, symbol: str, timeframe: str) -> bool:
        """Check if regime exists for this symbol/timeframe."""
        result = self.db.query(
            """
            SELECT 1
            FROM regimes r
            JOIN candles c ON r.candle_id = c.id
            WHERE c.symbol = ? AND c.timeframe = ?
            ORDER BY c.timestamp DESC
            LIMIT 1
            """,
            [symbol, timeframe],
        )
        return not result.empty


# Global gate instance
quality_gate = DataQualityGate()
