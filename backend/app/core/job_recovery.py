from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.job import Job, JobStatus


RECOVERY_MESSAGE = "Recovered at startup after the previous application process stopped before this in-process job finished."


def recover_interrupted_jobs() -> int:
    db = SessionLocal()
    try:
        interrupted_jobs = db.execute(
            select(Job).where(Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)))
        ).scalars().all()
        if not interrupted_jobs:
            return 0

        now = datetime.utcnow()
        for job in interrupted_jobs:
            job.status = JobStatus.FAILED
            job.finished_at = now
            if not job.error_message:
                job.error_message = RECOVERY_MESSAGE

        db.commit()
        return len(interrupted_jobs)
    finally:
        db.close()
