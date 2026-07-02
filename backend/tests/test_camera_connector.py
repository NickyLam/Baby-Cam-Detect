"""Tests for camera connection validation and probing."""
import pytest


def test_rtsp_connector_rejects_non_rtsp_urls():
    from app.services.camera_connector import RTSPCameraConnector

    connector = RTSPCameraConnector()
    result = connector.validate_source("http://127.0.0.1:8080/admin")

    assert result.ok is False
    assert result.code == "unsupported_scheme"
    assert result.redacted_url == "http://127.0.0.1:8080/admin"


def test_rtsp_connector_rejects_loopback_and_link_local_targets():
    from app.services.camera_connector import RTSPCameraConnector

    connector = RTSPCameraConnector()

    loopback = connector.validate_source("rtsp://user:pass@127.0.0.1:554/live")
    link_local = connector.validate_source("rtsp://169.254.169.254/latest")

    assert loopback.ok is False
    assert loopback.code == "blocked_host"
    assert loopback.redacted_url == "rtsp://***:***@127.0.0.1:554/live"
    assert link_local.ok is False
    assert link_local.code == "blocked_host"


def test_rtsp_connector_accepts_private_lan_rtsp_sources():
    from app.services.camera_connector import RTSPCameraConnector

    connector = RTSPCameraConnector()
    result = connector.validate_source("rtsp://user:pass@192.168.31.9:554/stream1")

    assert result.ok is True
    assert result.code == "valid"
    assert result.redacted_url == "rtsp://***:***@192.168.31.9:554/stream1"


@pytest.mark.asyncio
async def test_camera_probe_api_uses_connector_without_persisting(monkeypatch):
    from app.api import cameras
    from app.schemas import CameraProbeRequest

    class DummyConnector:
        def validate_source(self, rtsp_url):
            from app.schemas import CameraProbeResponse

            assert rtsp_url == "rtsp://user:pass@192.168.31.9/live"
            return CameraProbeResponse(
                ok=True,
                code="valid",
                message="RTSP source accepted",
                redacted_url="rtsp://***:***@192.168.31.9/live",
            )

    monkeypatch.setattr(cameras, "RTSPCameraConnector", lambda: DummyConnector())

    result = await cameras.probe_camera(
        data=CameraProbeRequest(rtsp_url="rtsp://user:pass@192.168.31.9/live"),
        user_id="00000000-0000-0000-0000-000000000001",
    )

    assert result.ok is True
    assert result.redacted_url == "rtsp://***:***@192.168.31.9/live"
