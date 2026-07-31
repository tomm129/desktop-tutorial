"""Data quality gate — validates data before ANY decision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from crypto_bot.config import SETTINGS
from crypto_bot.storage.database import db

logger = structlog.get_logger(__name__)

class DataQualityGate:
    """Validates data freshness and integrity. Returns NO_TRADE if invalid."""

    def __init__(self) -> None:
        self.max_age_seconds = 120  # Data must be fresher than 2 minutes
        self.required_tables = ["candles", "features", "regimes"]

    def check_all(self, symbol: str, timeframe: str) -> Tuple[bool, List[str]]:
        """Run all data quality checks. Returns (pass, list_of_failures)."""
        failures = []

        # Check 1: Candles exist
        count = db.get_candle_count(symbol, timeframe)
        if count == 0:
            failures.append(f"No candles for {symbol}/{timeframe}")

        # Check 2: Freshness
        last_ts = db.get_last_candle_timestamp(symbol, timeframe)
        if last_ts is None:
            failures.append(f"No timestamp for {symbol}/{timeframe}")
        else:
            age = (datetime.now(timezone.utc) - last_ts).total_seconds()
            if age > self.max_age_seconds:
                failures.append(
                    f"Stale data: {symbol}/{timeframe} last candle is {age:.0f}s old"
                )

        # Check 3: Gap detection (last 10 candles)
        gaps = self._check_recent_gaps(symbol, timeframe)
        if gaps:
            failures.append(f"Gaps detected: {gaps}")

        # Check 4: Feature availability
        features_ok = self._check_features(symbol, timeframe)
        if not features_ok:
            failures.append(f"Missing features for {symbol}/{timeframe}")

        # Check 5: Regime availability
        regime_ok = self._check_regime(symbol, timeframe)
        if not regime_ok:
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
        result = db.query(
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

        # Expected interval
        tf_seconds = self._timeframe_to_seconds(timeframe)
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
        """Check if features exist for the latest candle."""
        result = db.query(
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
        """Check if regime exists for the latest candle."""
        result = db.query(
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

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        return value * {"m": 60, "h": 3600, "d": 86400}.get(unit, 60)

# Global gate instance
quality_gate = DataQualityGate()
