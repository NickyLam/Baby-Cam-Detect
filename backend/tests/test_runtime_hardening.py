"""Tests for runtime reliability and security hardening."""
import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_camera_stream_limits_concurrent_analysis(monkeypatch):
    from app.services import stream_ingestion

    current = 0
    max_seen = 0

    class SlowAnalyzer:
        def has_pending_confirmation(self, camera_id):
            return False

        async def analyze_single_frame(self, camera_id, frame_jpeg):
            nonlocal current, max_seen
            current += 1
            max_seen = max(max_seen, current)
            await asyncio.sleep(0.01)
            current -= 1
            return None

        def clear_pending(self, camera_id):
            pass

    class DummyEventHandler:
        async def handle_event(self, camera_id, user_id, result, buffer):
            raise AssertionError("No event expected")

    monkeypatch.setattr(stream_ingestion, "FrameAnalyzer", SlowAnalyzer)
    monkeypatch.setattr(stream_ingestion, "EventHandler", DummyEventHandler)

    stream = stream_ingestion.CameraStream(
        camera_id="camera-1",
        rtsp_url="rtsp://192.168.31.9/live",
        user_id="user-1",
    )

    await asyncio.gather(
        stream._analyze_frame(b"frame-1"),
        stream._analyze_frame(b"frame-2"),
        stream._analyze_frame(b"frame-3"),
    )

    assert max_seen == 1


def test_settings_reject_default_secret_in_production():
    from app.config import Settings

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(debug=False, secret_key="change-me-in-production")


def test_settings_allows_default_secret_in_debug():
    from app.config import Settings

    settings = Settings(debug=True, secret_key="change-me-in-production")

    assert settings.debug is True


@pytest.mark.asyncio
async def test_event_handler_returns_signed_s3_urls(monkeypatch, tmp_path):
    from app.services.event_handler import EventHandler

    uploaded = []

    class DummyS3:
        def upload_file(self, file_path, bucket, key, ExtraArgs):
            uploaded.append((file_path, bucket, key, ExtraArgs))

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            return f"https://signed.local/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: DummyS3())

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"mp4")

    handler = EventHandler()
    url = await handler._upload_to_s3(str(clip), "event-1", "clips")

    assert uploaded[0][2] == "clips/event-1.mp4"
    assert url == "https://signed.local/babycam-clips/clips/event-1.mp4?expires=3600"
