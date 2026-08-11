"""Minimal DB-backed async job queue.

Deliberately not Celery/RQ + a Redis broker -- this project already had
real friction just standing up Postgres (see the WSL2 workaround), and a
broker is a second service to operate for no benefit at this project's
scale. Jobs instead run via FastAPI's BackgroundTasks within the same
process: the HTTP caller gets an immediate response and a job id to poll,
while the actual work still happens asynchronously. This is genuinely
correct for this project's single-worker deployment; a horizontally-scaled
multi-worker deployment would need a real broker instead of BackgroundTasks
-- documented here, not solved, since nothing in this project runs that way
today.
"""
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.schema import Job
from app.storage.database import SessionLocal


def create_job(db: Session, job_type: str, params: Optional[dict] = None) -> Job:
    job = Job(job_type=job_type, status="PENDING", params=params or {})
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_job(job_id: int, work_fn: Callable[[Session], dict]) -> None:
    """Entry point for BackgroundTasks -- runs after the HTTP response has
    already been sent, so it cannot reuse the request's db session (that's
    already been closed by Depends(get_db)'s cleanup). Opens its own.

    work_fn(db) must return a JSON-serializable dict, stored as the job's
    result, or raise -- any exception is caught and recorded as a FAILED
    job rather than crashing the background task silently.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            return
        job.status = "RUNNING"
        job.started_at = datetime.utcnow()
        db.commit()

        try:
            result = work_fn(db)
            job.status = "SUCCESS"
            job.result = result
        except Exception as e:
            job.status = "FAILED"
            job.error_message = str(e)

        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def serialize_job(job: Job) -> dict:
    return {
        "jobId": job.id,
        "jobType": job.job_type,
        "status": job.status,
        "params": job.params,
        "result": job.result,
        "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat() + "Z" if job.created_at else None,
        "startedAt": job.started_at.isoformat() + "Z" if job.started_at else None,
        "finishedAt": job.finished_at.isoformat() + "Z" if job.finished_at else None,
    }
