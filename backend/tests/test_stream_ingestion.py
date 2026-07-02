"""Tests for stream ingestion orchestration."""
from types import SimpleNamespace

import pytest

from app.schemas import AnalysisResult


@pytest.mark.asyncio
async def test_camera_stream_reuses_analyzer_for_multi_frame_confirmation(monkeypatch):
    """Consecutive sampled frames for one camera should share confirmation state."""
    from app.services import stream_ingestion

    handled_events = []

    class DummyAnalyzer:
        def __init__(self):
            self.frames = []

        def has_pending_confirmation(self, camera_id):
            return bool(self.frames)

        async def analyze_single_frame(self, camera_id, frame_jpeg):
            self.frames.append(frame_jpeg)
            return None

        async def confirm_with_frames(self, camera_id, frame_jpeg):
            self.frames.append(frame_jpeg)
            if len(self.frames) < 3:
                return None
            return AnalysisResult(
                status="alert",
                event_type="face_down",
                confidence=0.91,
                baby_visible=True,
                baby_position="on_stomach",
                face_visible=False,
                obstruction_detected=False,
                reasoning="Sustained face-down posture across frames",
            )

    class DummyEventHandler:
        async def handle_event(self, camera_id, user_id, result, buffer):
            handled_events.append((camera_id, user_id, result.event_type))

    monkeypatch.setattr(stream_ingestion, "FrameAnalyzer", DummyAnalyzer)
    monkeypatch.setattr(stream_ingestion, "EventHandler", DummyEventHandler)

    stream = stream_ingestion.CameraStream(
        camera_id="camera-1",
        rtsp_url="rtsp://user:secret@192.168.1.10/live",
        user_id="user-1",
    )

    await stream._analyze_frame(b"frame-1")
    await stream._analyze_frame(b"frame-2")
    await stream._analyze_frame(b"frame-3")

    assert handled_events == [("camera-1", "user-1", "face_down")]


def test_camera_response_redacts_rtsp_url():
    """Camera API responses must not expose stored RTSP credentials."""
    from app.schemas import CameraResponse

    camera = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        name="Nursery Cam",
        rtsp_url="rtsp://user:secret@192.168.1.10:554/stream1",
        rtsp_url_redacted="rtsp://***:***@192.168.1.10:554/stream1",
        status="setup",
        resolution=None,
        last_frame_at=None,
        error_message=None,
        created_at="2026-07-02T00:00:00Z",
    )

    payload = CameraResponse.model_validate(camera).model_dump()

    assert "rtsp_url" not in payload
    assert payload["rtsp_url_redacted"] == "rtsp://***:***@192.168.1.10:554/stream1"
