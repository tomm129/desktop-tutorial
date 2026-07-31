"""Orquestrador principal — 24/7 Crypto Market Research Engine.

Ciclo: coleta → features → regimes → rotulagem → health check → alertas.
NENHUMA ORDEM É EXECUTADA nesta fase.

Correção sobre kimi_reference/main.py (bug 3 do STATUS.md):
signal handlers registrados dentro de run() via asyncio.get_running_loop().
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone

import structlog

from crypto_bot import __version__
from crypto_bot.collectors.candles import CandleCollector
from crypto_bot.config import SETTINGS, timeframe_to_seconds
from crypto_bot.features.pipeline import FeaturePipeline
from crypto_bot.monitoring.alerts import alert_manager
from crypto_bot.monitoring.health import quality_gate
from crypto_bot.research.labeller import TemporalLabeller
from crypto_bot.storage.database import db

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("main")


class CryptoBot:
    """Main application orchestrator."""

    def __init__(self) -> None:
        self.running = False
        self.collector = CandleCollector()
        self.pipeline = FeaturePipeline()
        self.labeller = TemporalLabeller()

    def _signal_handler(self) -> None:
        logger.warning("main.shutdown_signal_received")
        self.running = False

    async def run_collection_cycle(self) -> None:
        """One collection + features + labelling cycle."""
        cycle_start = datetime.now(timezone.utc)

        try:
            # 1. Coleta de candles
            results = await self.collector.collect_all()
            total_inserted = sum(v for v in results.values() if v > 0)

            # 2. Features + regimes (contrato do rules_detector garantido no pipeline)
            total_features = 0
            total_regimes = 0
            for symbol in SETTINGS.symbols:
                for tf in SETTINGS.timeframes:
                    n_f, n_r = await asyncio.to_thread(self.pipeline.run, symbol, tf)
                    total_features += n_f
                    total_regimes += n_r

            # 3. Rotulagem temporal
            labelled = await asyncio.to_thread(self.labeller.run_batch, 5000)

            # 4. Health check
            for symbol in SETTINGS.symbols:
                for tf in SETTINGS.timeframes:
                    ok, failures = quality_gate.check_all(symbol, tf)
                    if not ok:
                        await alert_manager.send_warning(
                            f"Data quality gate failed for {symbol}/{tf}: {failures}"
                        )

            # 5. Alertas de erro de coleta
            errors = [k for k, v in results.items() if v == -1]
            if errors:
                await alert_manager.send_error(f"Collection errors: {errors}")

            # 6. Backup diário (idempotente)
            db.backup()

            logger.info(
                "main.cycle.complete",
                duration_seconds=(datetime.now(timezone.utc) - cycle_start).total_seconds(),
                candles_inserted=total_inserted,
                features_inserted=total_features,
                regimes_inserted=total_regimes,
                candles_labelled=labelled,
            )

        except Exception as e:
            logger.error("main.cycle.error", error=str(e), exc_info=True)
            await alert_manager.send_critical(f"Cycle error: {str(e)[:500]}")

    def _seconds_until_next_cycle(self) -> float:
        """Sincroniza com o fechamento do candle mais curto + margem (CLAUDE.md)."""
        shortest = min(timeframe_to_seconds(tf) for tf in SETTINGS.timeframes)
        interval = min(shortest, SETTINGS.collection.interval_seconds)
        now = datetime.now(timezone.utc).timestamp()
        next_close = (int(now // interval) + 1) * interval
        return max(next_close - now + SETTINGS.collection.sync_margin_seconds, 1.0)

    async def run(self) -> None:
        """Main loop."""
        self.running = True

        # bug 3 corrigido: handlers registrados com o loop já rodando
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        await alert_manager.send_info(
            "🚀 CryptoBot Research Engine started\n"
            f"Symbols: {SETTINGS.symbols}\n"
            f"Timeframes: {SETTINGS.timeframes}\n"
            f"Mode: {'PAPER' if SETTINGS.paper_trading.enabled else 'LIVE'}"
        )

        logger.info(
            "main.start",
            version=__version__,
            symbols=SETTINGS.symbols,
            timeframes=SETTINGS.timeframes,
        )

        while self.running:
            await self.run_collection_cycle()

            sleep_time = self._seconds_until_next_cycle()
            logger.debug("main.sleep", seconds=round(sleep_time, 1))
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

        # Graceful shutdown
        logger.info("main.shutdown")
        self.collector.close()
        db.close()
        await alert_manager.send_info("🛑 CryptoBot Research Engine stopped")
        await alert_manager.close()


def main() -> None:
    """Entry point."""
    bot = CryptoBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("main.keyboard_interrupt")
    finally:
        db.close()


if __name__ == "__main__":
    main()
