"""Tests for the RingBuffer - core data structure for frame storage."""
import time
import threading

import pytest

from app.core.ring_buffer import RingBuffer, BufferedFrame


class TestRingBufferBasics:
    """Test basic buffer operations."""

    def test_append_and_get_frame_count(self):
        buf = RingBuffer(max_duration_seconds=10, fps=5)
        assert buf.get_frame_count() == 0

        buf.append(b"frame1")
        assert buf.get_frame_count() == 1

        buf.append(b"frame2")
        buf.append(b"frame3")
        assert buf.get_frame_count() == 3

    def test_max_capacity_evicts_oldest(self):
        # 2 seconds * 5 fps = 10 max frames
        buf = RingBuffer(max_duration_seconds=2, fps=5)

        for i in range(15):
            buf.append(f"frame{i}".encode(), timestamp=float(i))

        assert buf.get_frame_count() == 10

        # Oldest frames should be evicted, latest should be frame14
        latest = buf.get_latest_frame()
        assert latest is not None
        assert latest.data == b"frame14"

    def test_get_latest_frame_empty(self):
        buf = RingBuffer()
        assert buf.get_latest_frame() is None

    def test_get_latest_frame(self):
        buf = RingBuffer()
        buf.append(b"first", timestamp=1.0)
        buf.append(b"second", timestamp=2.0)
        buf.append(b"third", timestamp=3.0)

        latest = buf.get_latest_frame()
        assert latest is not None
        assert latest.data == b"third"
        assert latest.timestamp == 3.0

    def test_clear(self):
        buf = RingBuffer()
        buf.append(b"frame1")
        buf.append(b"frame2")
        assert buf.get_frame_count() == 2

        buf.clear()
        assert buf.get_frame_count() == 0
        assert buf.get_latest_frame() is None


class TestRingBufferTimeRange:
    """Test time-range frame extraction."""

    def test_get_frames_in_range_basic(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=10.0)
        buf.append(b"f2", timestamp=11.0)
        buf.append(b"f3", timestamp=12.0)
        buf.append(b"f4", timestamp=13.0)
        buf.append(b"f5", timestamp=14.0)

        frames = buf.get_frames_in_range(11.0, 13.0)
        assert len(frames) == 3
        assert frames[0].data == b"f2"
        assert frames[-1].data == b"f4"

    def test_get_frames_in_range_empty(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=10.0)
        buf.append(b"f2", timestamp=20.0)

        # Range with no frames
        frames = buf.get_frames_in_range(11.0, 19.0)
        assert frames == []

    def test_get_frames_in_range_all(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=1.0)
        buf.append(b"f2", timestamp=2.0)
        buf.append(b"f3", timestamp=3.0)

        frames = buf.get_frames_in_range(0.0, 100.0)
        assert len(frames) == 3

    def test_get_frames_in_range_boundary_inclusive(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=5.0)
        buf.append(b"f2", timestamp=10.0)
        buf.append(b"f3", timestamp=15.0)

        # Exact boundary match should be inclusive
        frames = buf.get_frames_in_range(5.0, 10.0)
        assert len(frames) == 2


class TestRingBufferDuration:
    """Test duration property."""

    def test_duration_empty(self):
        buf = RingBuffer()
        assert buf.duration_seconds == 0.0

    def test_duration_single_frame(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=5.0)
        assert buf.duration_seconds == 0.0

    def test_duration_multiple_frames(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=10.0)
        buf.append(b"f2", timestamp=15.0)
        buf.append(b"f3", timestamp=25.0)
        assert buf.duration_seconds == 15.0


class TestRingBufferThreadSafety:
    """Test concurrent access."""

    def test_concurrent_append_and_read(self):
        buf = RingBuffer(max_duration_seconds=10, fps=10)
        errors = []

        def writer():
            for i in range(100):
                buf.append(f"frame{i}".encode(), timestamp=float(i))

        def reader():
            for _ in range(100):
                try:
                    buf.get_latest_frame()
                    buf.get_frame_count()
                    buf.get_frames_in_range(0, 50)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Thread safety errors: {errors}"


class TestBufferedFrame:
    """Test the BufferedFrame dataclass."""

    def test_frame_creation(self):
        frame = BufferedFrame(data=b"test", timestamp=123.0, index=0)
        assert frame.data == b"test"
        assert frame.timestamp == 123.0
        assert frame.index == 0

    def test_frame_index_increments(self):
        buf = RingBuffer()
        buf.append(b"f1", timestamp=1.0)
        buf.append(b"f2", timestamp=2.0)
        buf.append(b"f3", timestamp=3.0)

        latest = buf.get_latest_frame()
        assert latest.index == 2  # 0-based counter
