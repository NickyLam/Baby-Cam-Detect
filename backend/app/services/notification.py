"""Push notification service using Expo Push API."""
import logging
from datetime import datetime, time as dt_time
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session_maker
from app.models import DeviceToken, NotificationPreference

logger = logging.getLogger(__name__)
settings = get_settings()

# Human-readable event descriptions
EVENT_DESCRIPTIONS = {
    "face_down": "Baby may be sleeping face-down",
    "blanket_over_face": "Blanket may be covering baby's face",
}


class NotificationService:
    """Handles push notification dispatch via Expo Push API."""

    async def send_safety_alert(
        self,
        user_id: str,
        event_type: str,
        confidence: float,
        event_id: str,
    ) -> None:
        """Send a safety alert push notification."""
        # Check preferences
        if not await self._should_notify(user_id):
            logger.info(f"Notification suppressed for user {user_id} (preferences)")
            return

        # Get user's device tokens
        tokens = await self._get_active_tokens(user_id)
        if not tokens:
            logger.warning(f"No active device tokens for user {user_id}")
            return

        # Build notification
        title = "⚠️ Safety Alert"
        body = EVENT_DESCRIPTIONS.get(event_type, f"Safety concern detected")
        data = {
            "event_id": event_id,
            "event_type": event_type,
            "confidence": str(confidence),
            "type": "safety_alert",
        }

        # Send to all devices
        await self._send_expo_push(tokens, title, body, data)

    async def _should_notify(self, user_id: str) -> bool:
        """Check if notifications should be sent based on user preferences."""
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == UUID(user_id)
                    )
                )
                prefs = result.scalar_one_or_none()

                if not prefs:
                    return True  # Default to send

                if not prefs.safety_alerts:
                    return False

                # Check quiet hours
                if prefs.quiet_start and prefs.quiet_end:
                    now = datetime.now().time()
                    quiet_start = dt_time.fromisoformat(prefs.quiet_start)
                    quiet_end = dt_time.fromisoformat(prefs.quiet_end)

                    if quiet_start <= quiet_end:
                        if quiet_start <= now <= quiet_end:
                            return False
                    else:
                        # Overnight range (e.g., 22:00 - 06:00)
                        if now >= quiet_start or now <= quiet_end:
                            return False

                return True

        except Exception as e:
            logger.error(f"Error checking notification preferences: {e}")
            return True  # Default to send on error

    async def _get_active_tokens(self, user_id: str) -> list[str]:
        """Get all active push tokens for a user."""
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(DeviceToken.push_token).where(
                        DeviceToken.user_id == UUID(user_id),
                        DeviceToken.is_active == True,
                    )
                )
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching device tokens: {e}")
            return []

    async def _send_expo_push(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict,
    ) -> None:
        """Send push notifications via Expo Push API."""
        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data,
                "sound": "default",
                "priority": "high",
                "categoryId": "safety_alert",
            }
            for token in tokens
        ]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.expo_push_url,
                    json=messages,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(
                        f"Push notifications sent to {len(tokens)} devices"
                    )
                else:
                    logger.error(
                        f"Expo push error: {response.status_code} - {response.text}"
                    )

        except Exception as e:
            logger.error(f"Push notification send error: {e}")
