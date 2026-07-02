from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ===== Auth Schemas =====
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: Optional[str]
    timezone: str
    created_at: datetime


# ===== Camera Schemas =====
class CameraCreate(BaseModel):
    name: str = "Nursery Cam"
    rtsp_url: str = Field(..., min_length=7)


class CameraProbeRequest(BaseModel):
    rtsp_url: str = Field(..., min_length=7)


class CameraProbeResponse(BaseModel):
    ok: bool
    code: str
    message: str
    redacted_url: str


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    rtsp_url_redacted: str
    status: str
    resolution: Optional[str]
    last_frame_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


# ===== Event Schemas =====
class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    camera_id: UUID
    event_type: str
    severity: str
    confidence: float
    detected_at: datetime
    clip_url: Optional[str]
    thumbnail_url: Optional[str]
    frames_analyzed: int
    dismissed: bool
    created_at: datetime


class EventSummary(BaseModel):
    total_events: int
    face_down_count: int
    blanket_over_face_count: int
    dismissed_count: int
    period_start: datetime
    period_end: datetime


# ===== Notification Schemas =====
class DeviceTokenCreate(BaseModel):
    push_token: str
    platform: str = Field(..., pattern="^(ios|android)$")


class NotificationPreferenceUpdate(BaseModel):
    safety_alerts: Optional[bool] = None
    milestone_alerts: Optional[bool] = None
    quiet_start: Optional[str] = None  # "HH:MM" format
    quiet_end: Optional[str] = None
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=60)
    sensitivity: Optional[str] = Field(None, pattern="^(low|medium|high)$")


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    safety_alerts: bool
    milestone_alerts: bool
    quiet_start: Optional[str]
    quiet_end: Optional[str]
    cooldown_minutes: int
    sensitivity: str


# ===== Analysis Schemas =====
class AnalysisResult(BaseModel):
    status: str  # safe, alert, unclear
    event_type: Optional[str] = None
    confidence: float = 0.0
    baby_visible: bool = True
    baby_position: Optional[str] = None
    face_visible: bool = True
    obstruction_detected: bool = False
    reasoning: Optional[str] = None
