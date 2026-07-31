"""Main orchestrator — 24/7 Crypto Market Research Engine."""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone

import structlog

from crypto_bot.collectors.candles import CandleCollector
from crypto_bot.config import SETTINGS
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
        self.labeller = TemporalLabeller()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, self._signal_handler)

    def _signal_handler(self) -> None:
        logger.warning("main.shutdown_signal_received")
        self.running = False

    async def run_collection_cycle(self) -> None:
        """One collection + labelling cycle."""
        cycle_start = datetime.now(timezone.utc)

        try:
            # 1. Collect candles
            results = await self.collector.collect_all()
            total_inserted = sum(v for v in results.values() if v > 0)

            # 2. Label new candles
            labelled = self.labeller.run_batch(limit=5000)

            # 3. Health check
            for symbol in SETTINGS.symbols:
                for tf in SETTINGS.timeframes:
                    ok, failures = quality_gate.check_all(symbol, tf)
                    if not ok:
                        await alert_manager.send_warning(
                            f"Data quality gate failed for {symbol}/{tf}: {failures}"
                        )

            # 4. Alert on anomalies
            errors = [k for k, v in results.items() if v == -1]
            if errors:
                await alert_manager.send_error(
                    f"Collection errors: {errors}"
                )

            logger.info(
                "main.cycle.complete",
                duration_seconds=(datetime.now(timezone.utc) - cycle_start).total_seconds(),
                candles_inserted=total_inserted,
                candles_labelled=labelled,
            )

        except Exception as e:
            logger.error("main.cycle.error", error=str(e), exc_info=True)
            await alert_manager.send_critical(f"Cycle error: {str(e)[:500]}")

    async def run(self) -> None:
        """Main loop."""
        self.running = True

        await alert_manager.send_info(
            "🚀 CryptoBot Research Engine started\\n"
            f"Symbols: {SETTINGS.symbols}\\n"
            f"Timeframes: {SETTINGS.timeframes}\\n"
            f"Mode: {'PAPER' if SETTINGS.paper_trading.enabled else 'LIVE'}"
        )

        logger.info(
            "main.start",
            version="2.2.0",
            symbols=SETTINGS.symbols,
            timeframes=SETTINGS.timeframes,
        )

        while self.running:
            await self.run_collection_cycle()

            # Sleep until next interval
            sleep_time = SETTINGS.collection.interval_seconds
            logger.debug("main.sleep", seconds=sleep_time)
            await asyncio.sleep(sleep_time)

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
