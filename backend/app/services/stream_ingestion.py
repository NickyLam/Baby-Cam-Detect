"""Stream ingestion service - manages FFmpeg RTSP capture per camera."""
import asyncio
import logging
import subprocess
import time
from io import BytesIO
from typing import Optional

from PIL import Image

from app.config import get_settings
from app.core.ring_buffer import RingBuffer
from app.services.frame_analyzer import FrameAnalyzer
from app.services.event_handler import EventHandler

logger = logging.getLogger(__name__)
settings = get_settings()


class CameraStream:
    """Manages a single camera's RTSP stream capture and analysis pipeline."""

    def __init__(self, camera_id: str, rtsp_url: str, user_id: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.user_id = user_id
        self.buffer = RingBuffer(
            max_duration_seconds=settings.buffer_duration, fps=5
        )
        self.is_running = False
        self._process: Optional[subprocess.Popen] = None
        self._task: Optional[asyncio.Task] = None
        self._last_sample_time: float = 0
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10

    async def start(self):
        """Start the stream capture and analysis loop."""
        self.is_running = True
        self._reconnect_attempts = 0
        self._task = asyncio.create_task(self._run_capture_loop())
        logger.info(f"Started stream for camera {self.camera_id}")

    async def stop(self):
        """Stop the stream capture."""
        self.is_running = False
        if self._process:
            self._process.terminate()
            self._process = None
        if self._task:
            self._task.cancel()
            self._task = None
        self.buffer.clear()
        logger.info(f"Stopped stream for camera {self.camera_id}")

    async def _run_capture_loop(self):
        """Main capture loop with reconnection logic."""
        while self.is_running:
            try:
                await self._capture_stream()
            except Exception as e:
                logger.error(f"Stream error for camera {self.camera_id}: {e}")

            if not self.is_running:
                break

            # Reconnection with exponential backoff
            self._reconnect_attempts += 1
            if self._reconnect_attempts > self._max_reconnect_attempts:
                logger.error(
                    f"Camera {self.camera_id}: Max reconnect attempts reached"
                )
                self.is_running = False
                break

            backoff = min(2 ** self._reconnect_attempts, 60)
            logger.info(
                f"Camera {self.camera_id}: Reconnecting in {backoff}s "
                f"(attempt {self._reconnect_attempts})"
            )
            await asyncio.sleep(backoff)

    async def _capture_stream(self):
        """Capture frames from RTSP using FFmpeg."""
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-vf", "fps=5,scale=768:-1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "5",
            "-nostdin",
            "-loglevel", "error",
            "pipe:1",
        ]

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._reconnect_attempts = 0  # Reset on successful connection
        logger.info(f"Camera {self.camera_id}: FFmpeg started, reading frames...")

        # Read JPEG frames from pipe
        buffer = b""
        while self.is_running and self._process.returncode is None:
            chunk = await self._process.stdout.read(65536)
            if not chunk:
                break

            buffer += chunk

            # Find JPEG boundaries (SOI: FF D8, EOI: FF D9)
            while True:
                soi = buffer.find(b"\xff\xd8")
                if soi == -1:
                    buffer = b""
                    break

                eoi = buffer.find(b"\xff\xd9", soi + 2)
                if eoi == -1:
                    break

                # Extract complete JPEG frame
                frame_data = buffer[soi : eoi + 2]
                buffer = buffer[eoi + 2 :]

                # Store in ring buffer
                current_time = time.time()
                self.buffer.append(frame_data, current_time)

                # Sample for analysis at configured interval
                if current_time - self._last_sample_time >= settings.frame_sample_interval:
                    self._last_sample_time = current_time
                    # Don't await - fire and forget for analysis
                    asyncio.create_task(self._analyze_frame(frame_data))

    async def _analyze_frame(self, frame_jpeg: bytes):
        """Send frame for LLM analysis."""
        try:
            # Resize for cost efficiency
            resized = self._resize_frame(frame_jpeg, max_dim=768)

            analyzer = FrameAnalyzer()

            # Check if there's a pending confirmation first
            if analyzer.has_pending_confirmation(self.camera_id):
                result = await analyzer.confirm_with_frames(self.camera_id, resized)
            else:
                result = await analyzer.analyze_single_frame(self.camera_id, resized)

            if result and result.status == "alert":
                # Trigger event handling
                event_handler = EventHandler()
                await event_handler.handle_event(
                    camera_id=self.camera_id,
                    user_id=self.user_id,
                    result=result,
                    buffer=self.buffer,
                )

        except Exception as e:
            logger.error(f"Analysis task error for camera {self.camera_id}: {e}")

    def _resize_frame(self, frame_jpeg: bytes, max_dim: int = 768) -> bytes:
        """Resize frame for cost-efficient LLM analysis."""
        try:
            img = Image.open(BytesIO(frame_jpeg))
            w, h = img.size

            if max(w, h) <= max_dim:
                return frame_jpeg

            scale = max_dim / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

            output = BytesIO()
            img.save(output, format="JPEG", quality=80)
            return output.getvalue()
        except Exception:
            return frame_jpeg  # Return original on error


class StreamManager:
    """Singleton managing all active camera streams."""

    _instance: Optional["StreamManager"] = None
    _streams: dict[str, CameraStream] = {}

    @classmethod
    def get_instance(cls) -> "StreamManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_camera(self, camera) -> None:
        """Start monitoring a camera."""
        camera_id = str(camera.id)
        if camera_id in self._streams:
            await self._streams[camera_id].stop()

        stream = CameraStream(
            camera_id=camera_id,
            rtsp_url=camera.rtsp_url,
            user_id=str(camera.user_id),
        )
        self._streams[camera_id] = stream
        await stream.start()

    async def stop_camera(self, camera_id: str) -> None:
        """Stop monitoring a camera."""
        if camera_id in self._streams:
            await self._streams[camera_id].stop()
            del self._streams[camera_id]

    async def stop_all(self) -> None:
        """Stop all streams (for shutdown)."""
        for stream in self._streams.values():
            await stream.stop()
        self._streams.clear()

    def get_stream(self, camera_id: str) -> Optional[CameraStream]:
        """Get active stream for a camera."""
        return self._streams.get(camera_id)

    @property
    def active_count(self) -> int:
        return len(self._streams)
