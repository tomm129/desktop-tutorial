"""Coleta OHLCV 24/7 — Binance Futures USDT-M via CCXT (endpoints públicos).

Validação (OHLC inconsistente, preços não positivos), detecção de gaps,
retry com backoff exponencial e backfill de N dias no primeiro boot.
Apenas candles FECHADOS são persistidos (o candle em formação é descartado).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import ccxt
import pandas as pd
import structlog

from crypto_bot.config import SETTINGS, timeframe_to_seconds
from crypto_bot.storage.database import Database, db as default_db

logger = structlog.get_logger(__name__)

BACKOFF_SECONDS = [2, 4, 8, 16]


class CandleCollector:
    """Coleta e persiste candles fechados de todos os pares/timeframes configurados."""

    def __init__(self, db: Database | None = None, exchange: Any | None = None) -> None:
        self.db = db or default_db
        self._exchange = exchange

    @property
    def exchange(self) -> Any:
        if self._exchange is None:
            self._exchange = ccxt.binanceusdm({"enableRateLimit": True})
        return self._exchange

    # ------------------------------------------------------------------ #
    # Fetch com retry
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv_with_retry(
        self, symbol: str, timeframe: str, since: int, limit: int
    ) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt, backoff in enumerate([0] + BACKOFF_SECONDS):
            if backoff:
                logger.warning(
                    "collector.retry",
                    symbol=symbol,
                    timeframe=timeframe,
                    attempt=attempt,
                    backoff_seconds=backoff,
                    error=str(last_error),
                )
                time.sleep(backoff)
            try:
                return self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            except Exception as e:  # rate limit, rede, etc.
                last_error = e
        raise RuntimeError(
            f"fetch_ohlcv falhou após {len(BACKOFF_SECONDS) + 1} tentativas: {last_error}"
        )

    # ------------------------------------------------------------------ #
    # Validação
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate(df: pd.DataFrame) -> pd.DataFrame:
        """Remove candles com OHLC inconsistente ou preços não positivos."""
        if df.empty:
            return df
        valid = (
            (df["open"] > 0)
            & (df["high"] > 0)
            & (df["low"] > 0)
            & (df["close"] > 0)
            & (df["volume"] >= 0)
            & (df["high"] >= df["low"])
            & (df["high"] >= df[["open", "close"]].max(axis=1))
            & (df["low"] <= df[["open", "close"]].min(axis=1))
        )
        dropped = int((~valid).sum())
        if dropped:
            logger.warning("collector.validation.dropped", count=dropped)
        zero_vol = int((df.loc[valid, "volume"] == 0).sum())
        if zero_vol:
            logger.warning("collector.validation.zero_volume", count=zero_vol)
        return df[valid]

    def _detect_gaps(self, symbol: str, timeframe: str, df: pd.DataFrame) -> list[dict]:
        """Detecta gaps entre candles consecutivos do batch inserido."""
        if len(df) < 2:
            return []
        tf_seconds = timeframe_to_seconds(timeframe)
        ts = df["timestamp"].sort_values().reset_index(drop=True)
        diffs = ts.diff().dt.total_seconds().iloc[1:]
        gaps = [
            {"after": str(ts.iloc[i - 1]), "gap_seconds": float(d - tf_seconds)}
            for i, d in diffs.items()
            if d > tf_seconds * 1.5
        ]
        if gaps:
            logger.warning("collector.gaps_detected", symbol=symbol, timeframe=timeframe, gaps=gaps)
        return gaps

    # ------------------------------------------------------------------ #
    # Coleta
    # ------------------------------------------------------------------ #

    def collect_symbol_timeframe(self, symbol: str, timeframe: str) -> int:
        """Coleta candles novos de um par/timeframe. Retorna nº inserido."""
        tf_seconds = timeframe_to_seconds(timeframe)
        now = datetime.now(timezone.utc)

        last_ts = self.db.get_last_candle_timestamp(symbol, timeframe)
        if last_ts is None:
            since_dt = now - timedelta(days=SETTINGS.collection.backfill_days)
            logger.info(
                "collector.backfill.start",
                symbol=symbol,
                timeframe=timeframe,
                since=str(since_dt),
            )
        else:
            since_dt = last_ts + timedelta(seconds=tf_seconds)

        since_ms = int(since_dt.timestamp() * 1000)
        limit = SETTINGS.collection.fetch_limit
        rows: list[list[float]] = []

        while True:
            batch = self._fetch_ohlcv_with_retry(symbol, timeframe, since_ms, limit)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            since_ms = int(batch[-1][0]) + tf_seconds * 1000

        if not rows:
            return 0

        df = pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        df["symbol"] = symbol
        df["timeframe"] = timeframe

        # Apenas candles FECHADOS: abertura + timeframe <= agora
        cutoff = now - timedelta(seconds=tf_seconds)
        df = df[df["timestamp"] <= cutoff]

        df = self.validate(df)
        if df.empty:
            return 0

        inserted = self.db.insert_candles(df)
        self._detect_gaps(symbol, timeframe, df)

        logger.info(
            "collector.collected",
            symbol=symbol,
            timeframe=timeframe,
            fetched=len(rows),
            inserted=inserted,
        )
        return inserted

    async def collect_all(self) -> dict[str, int]:
        """Coleta todos os pares/timeframes. Retorna {'SYMBOL tf': inseridos | -1 em erro}."""
        results: dict[str, int] = {}
        for symbol in SETTINGS.symbols:
            for timeframe in SETTINGS.timeframes:
                key = f"{symbol} {timeframe}"
                try:
                    results[key] = await asyncio.to_thread(
                        self.collect_symbol_timeframe, symbol, timeframe
                    )
                except Exception as e:
                    logger.error(
                        "collector.error", symbol=symbol, timeframe=timeframe, error=str(e)
                    )
                    results[key] = -1
        return results

    def close(self) -> None:
        # ccxt síncrono não mantém conexões persistentes que exijam close explícito
        self._exchange = None
