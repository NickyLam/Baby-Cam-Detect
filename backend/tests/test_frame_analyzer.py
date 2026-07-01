"""Tests for FrameAnalyzer - cooldown logic and confirmation flow."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import AnalysisResult


@pytest.fixture
def mock_settings():
    """Mock settings for frame analyzer."""
    mock_config = MagicMock()
    mock_config.llm_provider = "gemini"
    mock_config.single_frame_confidence = 0.70
    mock_config.confirmed_confidence = 0.80
    mock_config.cooldown_minutes = 5
    return mock_config


@pytest.fixture
def mock_vision_client():
    """Mock the VisionClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def analyzer(mock_settings, mock_vision_client):
    """Create a FrameAnalyzer with mocked dependencies."""
    with patch("app.services.frame_analyzer.settings", mock_settings):
        with patch("app.services.frame_analyzer.get_vision_client", return_value=mock_vision_client):
            from app.services.frame_analyzer import FrameAnalyzer
            fa = FrameAnalyzer()
            fa.client = mock_vision_client
            return fa


class TestCooldownLogic:
    """Test cooldown/debounce behavior."""

    def test_not_in_cooldown_initially(self, analyzer):
        assert analyzer._is_in_cooldown("cam-1", "face_down") is False

    def test_cooldown_set_and_active(self, analyzer):
        analyzer._set_cooldown("cam-1", "face_down")
        assert analyzer._is_in_cooldown("cam-1", "face_down") is True

    def test_cooldown_different_camera(self, analyzer):
        analyzer._set_cooldown("cam-1", "face_down")
        # Different camera should not be in cooldown
        assert analyzer._is_in_cooldown("cam-2", "face_down") is False

    def test_cooldown_different_event_type(self, analyzer):
        analyzer._set_cooldown("cam-1", "face_down")
        # Different event type should not be in cooldown
        assert analyzer._is_in_cooldown("cam-1", "blanket_over_face") is False

    def test_cooldown_expired(self, analyzer, mock_settings):
        mock_settings.cooldown_minutes = 5
        # Set cooldown 6 minutes ago
        analyzer.cooldown_tracker["cam-1"]["face_down"] = time.time() - 360
        assert analyzer._is_in_cooldown("cam-1", "face_down") is False


class TestConfirmationFlow:
    """Test multi-frame confirmation logic."""

    def test_has_pending_confirmation_false(self, analyzer):
        assert analyzer.has_pending_confirmation("cam-1") is False

    def test_clear_pending(self, analyzer):
        analyzer.pending_confirmations["cam-1"] = [b"frame1"]
        analyzer.clear_pending("cam-1")
        assert analyzer.has_pending_confirmation("cam-1") is False

    def test_clear_pending_nonexistent_camera(self, analyzer):
        # Should not raise
        analyzer.clear_pending("nonexistent")

    @pytest.mark.asyncio
    async def test_confirmation_accumulates_frames(self, analyzer):
        """First two frames should not trigger confirmation."""
        initial_result = AnalysisResult(
            status="alert",
            event_type="face_down",
            confidence=0.85,
            baby_visible=True,
            baby_position="prone",
            face_visible=False,
            obstruction_detected=False,
            reasoning="Baby appears face down",
        )

        # First frame - should return None (needs more)
        result = await analyzer._request_confirmation("cam-1", b"frame1", initial_result)
        assert result is None
        assert analyzer.has_pending_confirmation("cam-1") is True

    @pytest.mark.asyncio
    async def test_confirm_with_frames_returns_none_without_pending(self, analyzer):
        """confirm_with_frames should return None if no pending confirmation."""
        result = await analyzer.confirm_with_frames("cam-1", b"frame")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_safe_frame_returns_none(self, analyzer, mock_vision_client):
        """A safe frame should return None."""
        safe_result = AnalysisResult(
            status="safe",
            confidence=0.9,
            baby_visible=True,
            baby_position="supine",
            face_visible=True,
            obstruction_detected=False,
            reasoning="Baby sleeping safely on back",
        )
        mock_vision_client.analyze_frame = AsyncMock(
            return_value=(safe_result, {"latency_ms": 500})
        )

        result = await analyzer.analyze_single_frame("cam-1", b"frame_data")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_low_confidence_alert_returns_none(self, analyzer, mock_vision_client):
        """Alert below single_frame_confidence should return None."""
        low_conf_result = AnalysisResult(
            status="alert",
            event_type="face_down",
            confidence=0.50,  # Below 0.70 threshold
            baby_visible=True,
            baby_position="prone",
            face_visible=False,
            obstruction_detected=False,
            reasoning="Maybe face down",
        )
        mock_vision_client.analyze_frame = AsyncMock(
            return_value=(low_conf_result, {"latency_ms": 300})
        )

        result = await analyzer.analyze_single_frame("cam-1", b"frame_data")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_suppressed_by_cooldown(self, analyzer, mock_vision_client):
        """Alert during cooldown should be suppressed."""
        alert_result = AnalysisResult(
            status="alert",
            event_type="face_down",
            confidence=0.85,
            baby_visible=True,
            baby_position="prone",
            face_visible=False,
            obstruction_detected=False,
            reasoning="Baby face down",
        )
        mock_vision_client.analyze_frame = AsyncMock(
            return_value=(alert_result, {"latency_ms": 400})
        )

        # Set cooldown
        analyzer._set_cooldown("cam-1", "face_down")

        result = await analyzer.analyze_single_frame("cam-1", b"frame_data")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_error_returns_none(self, analyzer, mock_vision_client):
        """LLM errors should be handled gracefully."""
        mock_vision_client.analyze_frame = AsyncMock(
            side_effect=Exception("API timeout")
        )

        result = await analyzer.analyze_single_frame("cam-1", b"frame_data")
        assert result is None
