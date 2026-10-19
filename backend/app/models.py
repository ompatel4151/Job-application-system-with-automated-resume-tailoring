import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatus(str, enum.Enum):
    saved = "saved"
    applied = "applied"
    screening = "screening"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class Resume(Base):
    __tablename__ = "resumes"
    # Lists are "my resumes, newest first".
    __table_args__ = (Index("ix_resumes_user_created", "user_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The Supabase user who owns the row (the token's sub). No foreign key to
    # auth.users, so the schema doesn't depend on Supabase's own tables.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False)
    # Structured resume content: summary, skills, experience, projects, education
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    tailored_resumes: Mapped[list["TailoredResume"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"
    # The board is "my applications, most recently updated first".
    __table_args__ = (Index("ix_applications_user_updated", "user_id", "updated_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The Supabase user who owns the row (the token's sub). No foreign key to
    # auth.users, so the schema doesn't depend on Supabase's own tables.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.saved
    )
    job_description: Mapped[str | None] = mapped_column(Text)
    job_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    tailored_resumes: Mapped[list["TailoredResume"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Same owner as its application; stored so RLS can check it directly.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Indexed: Postgres doesn't index foreign keys on its own, and the detail
    # page and tailored list look rows up by application. Without it, each
    # lookup scanned the whole table (measured in RESULTS.md, milestone 6).
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    match_analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped["Application"] = relationship(back_populates="tailored_resumes")
    resume: Mapped["Resume"] = relationship(back_populates="tailored_resumes")


class IdempotencyKey(Base):
    """The stored response of a create request sent with an Idempotency-Key."""

    __tablename__ = "idempotency_keys"

    # (user, key) is the primary key: two requests can never both claim the same
    # key, and one user's key can never replay another user's response.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Hash of method + path + body, to catch a key reused for a different request.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(JSON)
    # ponytail: keys are kept forever; delete rows older than ~24h if the table grows.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
