"""Alertas Telegram para eventos críticos.

Correção sobre kimi_reference/alerts.py (bug 2 do STATUS.md):
parse_mode HTML com escape adequado, em vez de MarkdownV2 sem escape.
"""

from __future__ import annotations

import html

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
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def send(self, message: str, level: str = "INFO") -> bool:
        """Send a Telegram message."""
        if not self.enabled:
            logger.debug("alerts.skipped_disabled", message=message[:100])
            return False

        icons = {
            "CRITICAL": "🔴",
            "ERROR": "🟠",
            "WARNING": "🟡",
            "INFO": "🟢",
        }
        icon = icons.get(level, "ℹ️")
        # bug 2 corrigido: HTML com escape — nenhum caractere do conteúdo quebra o parse
        formatted = f"{icon} <b>CryptoBot {html.escape(level)}</b>\n\n{html.escape(message)}"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": formatted,
            "parse_mode": "HTML",
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
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Global instance
alert_manager = AlertManager()
