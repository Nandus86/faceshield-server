"""Pydantic schemas for API requests/responses."""

import datetime
import os
from typing import List, Optional

from pydantic import BaseModel, Field


def image_url_for(path: Optional[str]) -> Optional[str]:
    """Map a stored file path to its static HTTP URL."""
    if not path:
        return None
    filename = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    if parent == "faces":
        return f"/faces/{filename}"
    if parent == "frames":
        return f"/frames/{filename}"
    return None


# ─── Person ──────────────────────────────────────────────────

class PersonBase(BaseModel):
    name: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(PersonBase):
    pass


class RegisterFaceRequest(BaseModel):
    """Manual registration with a known name from a base64 image."""
    name: str
    image_base64: str


class PersonOut(PersonBase):
    id: int
    name: Optional[str] = None
    display_name: str
    face_image_path: Optional[str] = None
    image_url: Optional[str] = None
    sighting_count: int = 0
    first_seen_at: datetime.datetime
    last_seen_at: datetime.datetime
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ─── Verification logs ───────────────────────────────────────

class VerificationLogOut(BaseModel):
    id: int
    person_id: int
    confidence: float
    detected_at: datetime.datetime
    source: Optional[str] = None
    is_new_registration: bool = False
    person_name: Optional[str] = None
    image_url: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Verify endpoint ─────────────────────────────────────────

class FaceResult(BaseModel):
    status: str = Field(..., description="known | known_cooldown | registered | pending | unknown")
    person_id: Optional[int] = None
    display_name: str = "Desconhecido"
    confidence: float = 0.0
    bbox: List[float] = Field(default_factory=list)
    face_image: Optional[str] = None


class VerifyResponse(BaseModel):
    faces_detected: int
    results: List[FaceResult]


# ─── RTSP streams ────────────────────────────────────────────

class RTSPStreamBase(BaseModel):
    name: str
    url: str


class RTSPStreamCreate(RTSPStreamBase):
    pass


class RTSPStreamUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None


class RTSPStreamOut(RTSPStreamBase):
    id: int
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class MergePersonsResponse(BaseModel):
    success: bool
    target_id: int
    target_name: str
    reassigned_logs_count: int
    reassigned_presence_sessions_count: int
    message: str


# ─── Runtime settings ────────────────────────────────────────

class AppSettingsOut(BaseModel):
    cooldown_minutes: int
    similarity_threshold: float
    image_retention_hours: int
    rtsp_frame_interval: float
    min_sightings: int
    presence_timeout_seconds: int
    auto_register_enabled: bool
    webhook_url: Optional[str] = None
    audio_alerts_enabled: bool = True

    model_config = {"from_attributes": True}


class AppSettingsUpdate(BaseModel):
    cooldown_minutes: Optional[int] = Field(None, ge=0, le=10080)
    similarity_threshold: Optional[float] = Field(None, ge=0.1, le=1.2)
    image_retention_hours: Optional[int] = Field(None, ge=1, le=8760)
    rtsp_frame_interval: Optional[float] = Field(None, ge=0.5, le=60)
    min_sightings: Optional[int] = Field(None, ge=1, le=10)
    presence_timeout_seconds: Optional[int] = Field(None, ge=5, le=3600)
    auto_register_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    audio_alerts_enabled: Optional[bool] = None


# ─── YouTube ─────────────────────────────────────────────────

class YouTubeRequest(BaseModel):
    url: str
    frame_interval: float = 1.0
    min_face_size: int = 40
    min_det_score: float = 0.40


# ─── Events ────────────────────────────────────────────────────

class EventBase(BaseModel):
    name: str


class EventCreate(EventBase):
    duration_minutes: Optional[int] = Field(None, ge=1, le=10080)


class EventUpdate(BaseModel):
    name: Optional[str] = None
    ended_at: Optional[datetime.datetime] = None


class EventOut(EventBase):
    id: int
    started_at: datetime.datetime
    ended_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    is_active: bool = False

    model_config = {"from_attributes": True}


class EventPresenceOut(BaseModel):
    id: int
    event_id: int
    person_id: int
    display_name: str
    face_image_url: Optional[str] = None
    first_seen_at: datetime.datetime

    model_config = {"from_attributes": True}
