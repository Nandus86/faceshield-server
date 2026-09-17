"""Unit tests for notification and webhook service."""

import asyncio
from unittest.mock import patch

import pytest
from core.database import session_scope
from core.models import AppSettings
from core.notification_service import notification_service


def run(coro):
    return asyncio.run(coro)


class TestNotificationService:
    def test_notify_noop_when_url_empty(self):
        async def scenario():
            with patch("core.notification_service._send_post_sync") as mock_send:
                await notification_service.notify("test_event", {"hello": "world"})
                mock_send.assert_not_called()

        run(scenario())

    def test_notify_dispatches_when_url_set(self):
        async def scenario():
            async with session_scope() as session:
                st = (await session.get(AppSettings, 1))
                st.webhook_url = "https://mock.webhook.test/api"

            with patch("core.notification_service._send_post_sync") as mock_send:
                await notification_service.notify("person_registered", {"person_id": 42, "name": "Maria"})
                # Give executor a fraction of a second to trigger
                await asyncio.sleep(0.1)
                assert mock_send.called

        run(scenario())
