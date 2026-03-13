from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobType(str, Enum):
    SCAN = "scan"
    METADATA_SYNC = "metadata_sync"
    FACE_DETECT = "face_detect"
    RECLUSTER = "recluster"
    SAM3D_BODY = "sam3d_body"
    SAM3D_OBJECT = "sam3d_object"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[JobType] = mapped_column(SqlEnum(JobType), index=True)
    status: Mapped[JobStatus] = mapped_column(SqlEnum(JobStatus), index=True, default=JobStatus.PENDING)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
