"""Frame analyzer service - orchestrates LLM analysis with confirmation logic."""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

from app.config import get_settings
from app.schemas import AnalysisResult
from app.services.llm_client import VisionClient, get_vision_client
from app.prompts.safety_detection import (
    SAFETY_SYSTEM_PROMPT,
    SAFETY_USER_PROMPT,
    CONFIRMATION_SYSTEM_PROMPT,
    CONFIRMATION_USER_PROMPT,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class FrameAnalyzer:
    """Analyzes video frames for baby safety events using LLM vision.
    
    Implements:
    - Single-frame detection with confidence thresholding
    - 2-of-3 multi-frame confirmation to reduce false positives
    - Cooldown/debounce between same-type alerts
    """

    def __init__(self):
        self.client: VisionClient = get_vision_client(settings.llm_provider)
        self.cooldown_tracker: dict[str, dict[str, float]] = defaultdict(dict)
        # camera_id -> {event_type: last_alert_timestamp}
        self.pending_confirmations: dict[str, list[bytes]] = {}
        # camera_id -> list of suspicious frames awaiting confirmation

    async def analyze_single_frame(
        self, camera_id: str, frame_jpeg: bytes
    ) -> Optional[AnalysisResult]:
        """Analyze a single frame. Returns result only if alert threshold met.
        
        Returns None if frame is safe or unclear.
        Returns AnalysisResult with status='alert' if confirmed dangerous.
        """
        try:
            result, usage = await self.client.analyze_frame(
                frame_jpeg, SAFETY_SYSTEM_PROMPT, SAFETY_USER_PROMPT
            )

            logger.debug(
                f"Camera {camera_id}: status={result.status}, "
                f"confidence={result.confidence}, "
                f"position={result.baby_position}, "
                f"latency={usage.get('latency_ms')}ms"
            )

            if result.status == "alert" and result.confidence >= settings.single_frame_confidence:
                # Check cooldown
                if self._is_in_cooldown(camera_id, result.event_type):
                    logger.info(f"Camera {camera_id}: Alert suppressed (cooldown)")
                    return None

                # Add to pending confirmations
                return await self._request_confirmation(camera_id, frame_jpeg, result)

            return None

        except Exception as e:
            logger.error(f"Frame analysis error for camera {camera_id}: {e}")
            return None

    async def _request_confirmation(
        self, camera_id: str, trigger_frame: bytes, initial_result: AnalysisResult
    ) -> Optional[AnalysisResult]:
        """Collect additional frames and run multi-frame confirmation.
        
        For MVP, we do immediate re-analysis of the trigger frame (since we may not 
        have the next frame yet). In production, this would wait for 2 more frames.
        """
        # Store the trigger frame for this camera's pending confirmation
        if camera_id not in self.pending_confirmations:
            self.pending_confirmations[camera_id] = []

        self.pending_confirmations[camera_id].append(trigger_frame)

        # If we have 3 frames pending, run confirmation
        if len(self.pending_confirmations[camera_id]) >= 3:
            frames = self.pending_confirmations.pop(camera_id)
            return await self._run_confirmation(camera_id, frames, initial_result)

        # Not enough frames yet - return None (will confirm when more frames arrive)
        return None

    async def confirm_with_frames(
        self, camera_id: str, frame_jpeg: bytes
    ) -> Optional[AnalysisResult]:
        """Add a frame to pending confirmations and check if ready to confirm."""
        if camera_id not in self.pending_confirmations:
            return None

        self.pending_confirmations[camera_id].append(frame_jpeg)

        if len(self.pending_confirmations[camera_id]) >= 3:
            frames = self.pending_confirmations.pop(camera_id)
            # Run confirmation with the stored event type context
            return await self._run_confirmation(camera_id, frames, None)

        return None

    async def _run_confirmation(
        self,
        camera_id: str,
        frames: list[bytes],
        initial_result: Optional[AnalysisResult],
    ) -> Optional[AnalysisResult]:
        """Run multi-frame confirmation analysis."""
        event_type = initial_result.event_type if initial_result else "unknown"

        user_prompt = CONFIRMATION_USER_PROMPT.format(
            num_frames=len(frames), event_type=event_type
        )

        try:
            result, usage = await self.client.analyze_multi_frame(
                frames, CONFIRMATION_SYSTEM_PROMPT, user_prompt
            )

            logger.info(
                f"Camera {camera_id}: Confirmation result: status={result.status}, "
                f"confidence={result.confidence}, event={result.event_type}"
            )

            if (
                result.status == "alert"
                and result.confidence >= settings.confirmed_confidence
            ):
                # Update cooldown
                self._set_cooldown(camera_id, result.event_type)
                result.confidence = result.confidence  # Keep confirmed confidence
                return result

            return None

        except Exception as e:
            logger.error(f"Confirmation error for camera {camera_id}: {e}")
            return None

    def _is_in_cooldown(self, camera_id: str, event_type: str) -> bool:
        """Check if an event type is within the cooldown period."""
        last_alert = self.cooldown_tracker.get(camera_id, {}).get(event_type)
        if last_alert is None:
            return False
        elapsed = time.time() - last_alert
        return elapsed < (settings.cooldown_minutes * 60)

    def _set_cooldown(self, camera_id: str, event_type: str) -> None:
        """Record an alert time for cooldown tracking."""
        self.cooldown_tracker[camera_id][event_type] = time.time()

    def has_pending_confirmation(self, camera_id: str) -> bool:
        """Check if a camera has frames awaiting confirmation."""
        return camera_id in self.pending_confirmations

    def clear_pending(self, camera_id: str) -> None:
        """Clear pending confirmations for a camera (e.g., on stream stop)."""
        self.pending_confirmations.pop(camera_id, None)
