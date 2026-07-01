"""Tests for security module - JWT tokens and password hashing."""
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from passlib.context import CryptContext


# Use sha256_crypt for tests to avoid passlib + bcrypt>=4.1 incompatibility
# (bcrypt 4.x rejects >72 byte passwords during passlib's internal bug detection)
_test_pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


# We need to mock settings before importing security module
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests in this module."""
    mock_config = MagicMock()
    mock_config.secret_key = "test-secret-key-for-testing"
    mock_config.algorithm = "HS256"
    mock_config.access_token_expire_minutes = 60
    mock_config.refresh_token_expire_days = 7
    mock_config.api_prefix = "/api/v1"

    with patch("app.core.security.settings", mock_config):
        with patch("app.core.security.pwd_context", _test_pwd_context):
            with patch("app.config.get_settings", return_value=mock_config):
                yield mock_config


class TestPasswordHashing:
    """Test password hash and verify functions."""

    def test_hash_password_returns_hash(self, mock_settings):
        from app.core.security import hash_password
        hashed = hash_password("mysecretpassword")
        assert hashed != "mysecretpassword"
        assert len(hashed) > 20

    def test_verify_password_correct(self, mock_settings):
        from app.core.security import hash_password, verify_password
        password = "test-password-123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self, mock_settings):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correct-password")
        assert verify_password("wrong-password", hashed) is False

    def test_hash_is_unique_per_call(self, mock_settings):
        from app.core.security import hash_password
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        # bcrypt generates different salts each time
        assert h1 != h2


class TestJWTTokens:
    """Test JWT token creation and decoding."""

    def test_create_access_token(self, mock_settings):
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "user-123"})
        assert isinstance(token, str)
        assert len(token) > 10

        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_create_access_token_custom_expiry(self, mock_settings):
        from app.core.security import create_access_token, decode_token
        token = create_access_token(
            {"sub": "user-456"},
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_token(token)
        assert payload["sub"] == "user-456"

    def test_create_refresh_token(self, mock_settings):
        from app.core.security import create_refresh_token, decode_token
        token = create_refresh_token({"sub": "user-789"})
        payload = decode_token(token)
        assert payload["sub"] == "user-789"
        assert payload["type"] == "refresh"

    def test_decode_invalid_token_raises(self, mock_settings):
        from app.core.security import decode_token
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid-token-string")
        assert exc_info.value.status_code == 401

    def test_decode_expired_token_raises(self, mock_settings):
        from app.core.security import create_access_token, decode_token
        # Create a token that already expired
        token = create_access_token(
            {"sub": "user-expired"},
            expires_delta=timedelta(seconds=-10),
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    """Test the get_current_user_id dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, mock_settings):
        from app.core.security import create_access_token, get_current_user_id
        token = create_access_token({"sub": "user-abc"})
        user_id = await get_current_user_id(token)
        assert user_id == "user-abc"

    @pytest.mark.asyncio
    async def test_get_current_user_missing_sub(self, mock_settings):
        from app.core.security import create_access_token, get_current_user_id
        # Token without 'sub' claim
        token = create_access_token({"role": "admin"})
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_settings):
        from app.core.security import get_current_user_id
        with pytest.raises(HTTPException):
            await get_current_user_id("garbage-token")
