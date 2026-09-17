"""Database models — single source of truth for all people, logs and presence."""

import datetime
from typing import List, Optional

from sqlalchemy import Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
    VectorType = Vector(512)
except Exception:  # pragma: no cover - pgvector optional (SQLite fallback)
    from sqlalchemy import JSON
    VectorType = JSON


class Base(DeclarativeBase):
    pass


class Person(Base):
    """A person known to the system, registered exactly once.

    Auto-registered people start with a NULL name and are displayed as
    "Pessoa #N" until renamed through the dashboard or API.
    """

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding = mapped_column(VectorType, nullable=False)
    face_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    sighting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    logs: Mapped[List["VerificationLog"]] = relationship(
        back_populates="person", cascade="all, delete-orphan", lazy="selectin"
    )
    presence_sessions: Mapped[List["PresenceSession"]] = relationship(
        back_populates="person", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def display_name(self) -> str:
        return self.name if self.name else f"Pessoa #{self.id}"

    def __repr__(self) -> str:
        return f"<Person id={self.id} name={self.name!r}>"


class VerificationLog(Base):
    """A recognition event for a registered person."""

    __tablename__ = "verification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    frame_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_new_registration: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    person: Mapped["Person"] = relationship(back_populates="logs", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<VerificationLog id={self.id} person_id={self.person_id} "
            f"confidence={self.confidence:.2f}>"
        )


class PresenceSession(Base):
    """A continuous presence interval of a person in front of a source.

    A session opens on the first detection and stays open while detections
    keep arriving within PRESENCE_TIMEOUT_SECONDS; it is closed by the
    presence timeout task.
    """

    __tablename__ = "presence_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    person: Mapped["Person"] = relationship(back_populates="presence_sessions")

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def __repr__(self) -> str:
        return f"<PresenceSession id={self.id} person_id={self.person_id} active={self.is_active}>"


class RTSPStream(Base):
    """A configured RTSP camera stream."""

    __tablename__ = "rtsp_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<RTSPStream id={self.id} name={self.name!r} active={self.is_active}>"


class AppSettings(Base):
    """Runtime-configurable application settings (single row, id=1)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)
    similarity_threshold: Mapped[float] = mapped_column(Float, default=0.45)
    image_retention_hours: Mapped[int] = mapped_column(Integer, default=48)
    rtsp_frame_interval: Mapped[float] = mapped_column(Float, default=2.0)
    min_sightings: Mapped[int] = mapped_column(Integer, default=2)
    presence_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    auto_register_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    audio_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Event(Base):
    """A monitoring event / session."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    presences: Mapped[List["EventPresence"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def __repr__(self) -> str:
        return f"<Event id={self.id} name={self.name!r} active={self.is_active}>"


class EventPresence(Base):
    """First-seen record of a person inside a specific event."""

    __tablename__ = "event_presences"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_event_person"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    face_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="presences")
    person: Mapped["Person"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<EventPresence event={self.event_id} person={self.person_id}>"

