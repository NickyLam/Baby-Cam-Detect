import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BufferedFrame:
    """A single frame stored in the ring buffer."""
    data: bytes  # JPEG encoded frame
    timestamp: float  # Unix timestamp
    index: int  # Sequential frame index


class RingBuffer:
    """Thread-safe ring buffer for storing video frames.
    
    Maintains a rolling window of frames for clip extraction
    when events are detected.
    """

    def __init__(self, max_duration_seconds: int = 45, fps: int = 5):
        self.max_duration = max_duration_seconds
        self.fps = fps
        self.max_frames = max_duration_seconds * fps
        self._buffer: deque[BufferedFrame] = deque(maxlen=self.max_frames)
        self._lock = threading.Lock()
        self._frame_counter = 0

    def append(self, frame_data: bytes, timestamp: Optional[float] = None) -> None:
        """Add a frame to the buffer."""
        if timestamp is None:
            timestamp = time.time()
        
        with self._lock:
            frame = BufferedFrame(
                data=frame_data,
                timestamp=timestamp,
                index=self._frame_counter,
            )
            self._buffer.append(frame)
            self._frame_counter += 1

    def get_frames_in_range(
        self, start_time: float, end_time: float
    ) -> list[BufferedFrame]:
        """Extract frames within a time range."""
        with self._lock:
            return [
                f for f in self._buffer
                if start_time <= f.timestamp <= end_time
            ]

    def get_latest_frame(self) -> Optional[BufferedFrame]:
        """Get the most recent frame."""
        with self._lock:
            if self._buffer:
                return self._buffer[-1]
            return None

    def get_frame_count(self) -> int:
        """Get current number of frames in buffer."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all frames from the buffer."""
        with self._lock:
            self._buffer.clear()

    @property
    def duration_seconds(self) -> float:
        """Current duration of buffered content in seconds."""
        with self._lock:
            if len(self._buffer) < 2:
                return 0.0
            return self._buffer[-1].timestamp - self._buffer[0].timestamp
