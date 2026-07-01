"""Shared test configuration and fixtures."""
import sys
from unittest.mock import MagicMock

# Pre-mock heavy modules that aren't needed for unit tests
# This prevents import errors when database/async drivers aren't installed
_modules_to_mock = [
    "asyncpg",
    "redis",
    "google.generativeai",
    "openai",
    "boto3",
    "ffmpeg",
    "httpx",
]

for mod in _modules_to_mock:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
