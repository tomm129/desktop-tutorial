"""Telegram alerting system for critical events."""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog

from crypto_bot.config import SETTINGS

logger = structlog.get_logger(__name__)

class AlertManager:
    """Sends alerts via Telegram Bot API."""

    def __init__(self) -> None:
        self.enabled = SETTINGS.telegram.enabled and bool(SETTINGS.telegram.bot_token)
        self.bot_token = SETTINGS.telegram.bot_token
        self.chat_id = SETTINGS.telegram.chat_id
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send(self, message: str, level: str = "INFO") -> bool:
        """Send a Telegram message."""
        if not self.enabled:
            logger.debug("alerts.skipped_disabled", message=message[:100])
            return False

        # Format message with level indicator
        icons = {
            "CRITICAL": "🔴",
            "ERROR": "🟠",
            "WARNING": "🟡",
            "INFO": "🟢",
        }
        icon = icons.get(level, "ℹ️")
        formatted = f"{icon} *CryptoBot {level}*\\n\\n{message}"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": formatted,
            "parse_mode": "MarkdownV2",
            "disable_notification": level not in ("CRITICAL", "ERROR"),
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            logger.info("alerts.sent", level=level, chat_id=self.chat_id)
            return True
        except Exception as e:
            logger.error("alerts.failed", error=str(e), level=level)
            return False

    async def send_critical(self, message: str) -> bool:
        return await self.send(message, "CRITICAL")

    async def send_error(self, message: str) -> bool:
        return await self.send(message, "ERROR")

    async def send_warning(self, message: str) -> bool:
        return await self.send(message, "WARNING")

    async def send_info(self, message: str) -> bool:
        return await self.send(message, "INFO")

    async def close(self) -> None:
        await self.client.aclose()

# Global instance
alert_manager = AlertManager()
