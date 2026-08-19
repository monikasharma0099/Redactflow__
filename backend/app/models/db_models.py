"""SQLAlchemy 2.0 ORM models (SPEC 1.4)."""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Float, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # image|pdf|batch_item
    filename: Mapped[str] = mapped_column(String(128), default="")
    mask_type: Mapped[str] = mapped_column(String(32), default="blur")
    status: Mapped[str] = mapped_column(String(32), default="completed")
    pii_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    original_path: Mapped[str] = mapped_column(String(512), default="")
    masked_path: Mapped[str] = mapped_column(String(512), default="")
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    detections: Mapped[list["Detection"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    pii_type: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(String(1024))
    x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="regex")

    job: Mapped[Job] = relationship(back_populates="detections")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    mask_type: Mapped[str] = mapped_column(String(32), default="blur")
    zip_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
