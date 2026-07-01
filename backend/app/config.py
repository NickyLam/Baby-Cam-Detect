from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Baby-Cam-Detect"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/babycam"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # LLM Provider: "gemini", "openai", or "openai_compatible"
    llm_provider: str = "gemini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # OpenAI (fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # OpenAI-Compatible providers (Stepfun, Kimi, DeepSeek, etc.)
    compatible_api_key: str = ""
    compatible_api_base: str = ""  # e.g., https://api.stepfun.com/v1
    compatible_model: str = ""  # e.g., step-1v-8k, moonshot-v1-8k-vision

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "babycam-clips"

    # Stream Pipeline
    frame_sample_interval: float = 3.0  # seconds between LLM analysis frames
    buffer_duration: int = 45  # seconds of rolling buffer
    clip_duration_before: int = 15  # seconds before event
    clip_duration_after: int = 15  # seconds after event

    # Detection Thresholds
    single_frame_confidence: float = 0.70
    confirmed_confidence: float = 0.80
    cooldown_minutes: int = 5

    # Expo Push
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
