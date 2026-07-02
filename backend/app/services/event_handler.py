"""Event handler - manages clip extraction, storage, and notification dispatch."""
import asyncio
import logging
import tempfile
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from app.config import get_settings
from app.core.ring_buffer import RingBuffer
from app.schemas import AnalysisResult

logger = logging.getLogger(__name__)
settings = get_settings()


class EventHandler:
    """Handles detected safety events: clip extraction, storage, notifications."""

    async def handle_event(
        self,
        camera_id: str,
        user_id: str,
        result: AnalysisResult,
        buffer: RingBuffer,
    ) -> None:
        """Process a confirmed safety event."""
        event_id = str(uuid.uuid4())
        detected_at = datetime.now(timezone.utc)

        logger.warning(
            f"SAFETY EVENT: camera={camera_id}, type={result.event_type}, "
            f"confidence={result.confidence:.2f}, reason={result.reasoning}"
        )

        # Extract clip from buffer
        clip_url = await self._extract_and_upload_clip(
            event_id, buffer, detected_at
        )

        # Generate thumbnail from the latest frame
        thumbnail_url = await self._generate_thumbnail(event_id, buffer)

        # Persist event to database
        await self._persist_event(
            event_id=event_id,
            camera_id=camera_id,
            result=result,
            detected_at=detected_at,
            clip_url=clip_url,
            thumbnail_url=thumbnail_url,
        )

        # Send push notification
        await self._send_notification(user_id, result, event_id)

    async def _extract_and_upload_clip(
        self, event_id: str, buffer: RingBuffer, detected_at: datetime
    ) -> Optional[str]:
        """Extract frames from buffer and encode as MP4 clip."""
        try:
            current_time = time.time()
            start_time = current_time - settings.clip_duration_before
            end_time = current_time + settings.clip_duration_after

            frames = buffer.get_frames_in_range(start_time, end_time)
            if not frames:
                logger.warning(f"No frames in buffer for event {event_id}")
                return None

            # Encode frames to MP4 using FFmpeg
            clip_path = await self._encode_clip(frames, event_id)
            if not clip_path:
                return None

            # Upload to S3
            clip_url = await self._upload_to_s3(clip_path, event_id, "clips")
            return clip_url

        except Exception as e:
            logger.error(f"Clip extraction error for event {event_id}: {e}")
            return None

    async def _encode_clip(self, frames, event_id: str) -> Optional[str]:
        """Encode JPEG frames to MP4 using FFmpeg."""
        try:
            output_path = f"/tmp/clip_{event_id}.mp4"
            fps = 5

            # Write frames to a temporary pipe for FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-f", "image2pipe",
                "-framerate", str(fps),
                "-vcodec", "mjpeg",
                "-i", "pipe:0",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Feed frames to FFmpeg
            frame_data = b"".join(f.data for f in frames)
            await process.communicate(input=frame_data)

            if process.returncode == 0:
                return output_path
            else:
                logger.error(f"FFmpeg encode failed for event {event_id}")
                return None

        except Exception as e:
            logger.error(f"Clip encoding error: {e}")
            return None

    async def _generate_thumbnail(
        self, event_id: str, buffer: RingBuffer
    ) -> Optional[str]:
        """Generate a thumbnail from the latest frame."""
        frame = buffer.get_latest_frame()
        if not frame:
            return None

        try:
            from PIL import Image

            img = Image.open(BytesIO(frame.data))
            img.thumbnail((320, 240))

            thumb_buffer = BytesIO()
            img.save(thumb_buffer, format="JPEG", quality=70)
            thumb_bytes = thumb_buffer.getvalue()

            # Upload thumbnail
            thumb_url = await self._upload_bytes_to_s3(
                thumb_bytes, f"thumbnails/{event_id}.jpg", "image/jpeg"
            )
            return thumb_url

        except Exception as e:
            logger.error(f"Thumbnail generation error: {e}")
            return None

    async def _upload_to_s3(
        self, file_path: str, event_id: str, prefix: str
    ) -> Optional[str]:
        """Upload a file to S3."""
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )

            key = f"{prefix}/{event_id}.mp4"
            s3.upload_file(
                file_path,
                settings.s3_bucket_name,
                key,
                ExtraArgs={"ContentType": "video/mp4"},
            )

            return self._generate_signed_url(s3, key)

        except Exception as e:
            logger.error(f"S3 upload error: {e}")
            return None

    async def _upload_bytes_to_s3(
        self, data: bytes, key: str, content_type: str
    ) -> Optional[str]:
        """Upload bytes directly to S3."""
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )

            s3.put_object(
                Bucket=settings.s3_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

            return self._generate_signed_url(s3, key)

        except Exception as e:
            logger.error(f"S3 bytes upload error: {e}")
            return None

    def _generate_signed_url(self, s3, key: str) -> str:
        """Create a short-lived URL for private event media."""
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": key},
            ExpiresIn=settings.s3_presigned_url_expire_seconds,
        )

    async def _persist_event(
        self,
        event_id: str,
        camera_id: str,
        result: AnalysisResult,
        detected_at: datetime,
        clip_url: Optional[str],
        thumbnail_url: Optional[str],
    ) -> None:
        """Save event to database."""
        try:
            from app.core.database import async_session_maker
            from app.models import Event

            async with async_session_maker() as session:
                event = Event(
                    id=uuid.UUID(event_id),
                    camera_id=uuid.UUID(camera_id),
                    event_type=result.event_type,
                    severity="critical",
                    confidence=result.confidence,
                    detected_at=detected_at,
                    clip_url=clip_url,
                    thumbnail_url=thumbnail_url,
                    llm_response=result.model_dump(),
                    frames_analyzed=3,  # multi-frame confirmation
                )
                session.add(event)
                await session.commit()

            logger.info(f"Event {event_id} persisted to database")

        except Exception as e:
            logger.error(f"Event persistence error: {e}")

    async def _send_notification(
        self, user_id: str, result: AnalysisResult, event_id: str
    ) -> None:
        """Send push notification to user."""
        try:
            from app.services.notification import NotificationService

            notification_service = NotificationService()
            await notification_service.send_safety_alert(
                user_id=user_id,
                event_type=result.event_type,
                confidence=result.confidence,
                event_id=event_id,
            )
        except Exception as e:
            logger.error(f"Notification error: {e}")
