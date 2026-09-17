"""Notification & Webhook dispatch service for real-time alerts.

Sends background HTTP POST requests to configured Webhook URLs when events
(like new person registration, recognition, presence ended) occur.
"""

import asyncio
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from core.database import session_scope
from core.models import AppSettings

logger = logging.getLogger(__name__)


async def _get_webhook_url() -> Optional[str]:
    try:
        async with session_scope() as session:
            result = await session.execute(select(AppSettings.webhook_url).where(AppSettings.id == 1))
            url = result.scalar_one_or_none()
            if url and url.strip():
                return url.strip()
    except Exception as err:
        logger.debug("Falha ao ler webhook_url das configurações: %s", err)
    return None


def _send_post_sync(url: str, payload: dict, timeout: float = 4.0) -> None:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "VisionAI-FaceShield/3.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status >= 400:
                logger.warning("Webhook retornou status HTTP %d (%s)", response.status, url)
    except urllib.error.URLError as err:
        logger.warning("Erro de conexão no Webhook (%s): %s", url, err.reason)
    except Exception as err:
        logger.warning("Falha ao despachar Webhook (%s): %s", url, err)


class NotificationService:
    """Dispatches webhook notifications asynchronously without blocking inference."""

    @staticmethod
    async def notify(event_type: str, data: dict) -> None:
        webhook_url = await _get_webhook_url()
        if not webhook_url:
            return

        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _send_post_sync, webhook_url, payload)


notification_service = NotificationService()
