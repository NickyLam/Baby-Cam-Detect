import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Float, Integer, Text, DateTime,
    ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.url_security import redact_url_credentials


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100))
    timezone = Column(String(50), default="UTC")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    cameras = relationship("Camera", back_populates="user", cascade="all, delete-orphan")
    device_tokens = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), default="Nursery Cam")
    rtsp_url = Column(String(500), nullable=False)
    status = Column(String(20), default="setup")  # active, paused, error, setup
    resolution = Column(String(20))
    last_frame_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="cameras")
    events = relationship("Event", back_populates="camera", cascade="all, delete-orphan")

    @property
    def rtsp_url_redacted(self) -> str:
        """Return the RTSP URL without exposing embedded credentials."""
        return redact_url_credentials(self.rtsp_url)


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # face_down, blanket_over_face
    severity = Column(String(20), default="critical")  # critical, warning, info
    confidence = Column(Float, nullable=False)
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    clip_url = Column(String(500))
    thumbnail_url = Column(String(500))
    llm_response = Column(JSON)
    frames_analyzed = Column(Integer, default=1)
    dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    camera = relationship("Camera", back_populates="events")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    push_token = Column(String(500), nullable=False)
    platform = Column(String(20))  # ios, android
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="device_tokens")


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    safety_alerts = Column(Boolean, default=True)
    milestone_alerts = Column(Boolean, default=True)
    quiet_start = Column(String(5))  # "22:00"
    quiet_end = Column(String(5))  # "06:00"
    cooldown_minutes = Column(Integer, default=5)
    sensitivity = Column(String(10), default="medium")  # low, medium, high

    # Relationships
    user = relationship("User", back_populates="notification_preferences")


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    model_used = Column(String(50))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Integer)
    result = Column(String(20))  # safe, alert, error
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
