"""Stage 22 -- /api/v1 router matching the REAL frontend contract (pasted in
full by the user from their Google AI Studio project's src/api-contract.ts,
src/types.ts, src/data/mockData.ts). Every response is wrapped in the
frontend's ApiResponse<T> envelope: {success, data?, error?, meta?}.

`/api/trends/latest` (app/api/trends.py) is untouched -- this is a fully
separate, additive router.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.schema import Job, ProcessedSignal, Source, Trend, TrendRun
from app.processing.llm_enrichment import enrich_trend_run
from app.processing.trend_intelligence import run_trend_intelligence
from app.services.job_queue import create_job, run_job, serialize_job
from app.services.trend_view import (
    compute_emerging_trends, compute_fastest_rising, compute_medical_intelligence,
    compute_platform_leadership, compute_platform_pulse, get_previous_trend_run,
    serialize_instagram_content, serialize_trend, serialize_trends_for_run,
)
from app.storage.database import get_db

router = APIRouter(prefix="/api/v1", tags=["v1"])

API_VERSION = "1.0.0"


def _ok(data, snapshot_id: Optional[str] = None) -> dict:
    meta = {"timestamp": datetime.datetime.utcnow().isoformat() + "Z", "version": API_VERSION}
    if snapshot_id:
        meta["snapshotId"] = snapshot_id
    return {"success": True, "data": data, "meta": meta}


def _error(code: str, message: str, status_code: int = 404) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={
        "success": False,
        "error": {"code": code, "message": message},
        "meta": {"timestamp": datetime.datetime.utcnow().isoformat() + "Z", "version": API_VERSION},
    })


def _find_run_for_daypart(db: Session, daypart: Optional[str]) -> Optional[TrendRun]:
    """Real dayparts correspond to actual TrendRuns tagged by
    get_current_daypart() at scoring time, not a live recomputation. If no
    run exists yet for the requested daypart, falls back to the latest run
    overall rather than erroring -- the frontend always expects some
    snapshot back, and serving stale-but-real data is more honest than a
    hard failure when a same-day daypart simply hasn't run yet."""
    if daypart:
        run = (
            db.query(TrendRun)
            .filter(TrendRun.snapshot_period == daypart)
            .order_by(TrendRun.id.desc())
            .first()
        )
        if run:
            return run
    return db.query(TrendRun).order_by(TrendRun.id.desc()).first()


def _parse_trend_id(trend_id: str) -> Optional[int]:
    raw = trend_id[3:] if trend_id.lower().startswith("tr-") else trend_id
    return int(raw) if raw.isdigit() else None


def _build_snapshot(db: Session, run: TrendRun) -> dict:
    previous = get_previous_trend_run(db, run)
    top_trends = serialize_trends_for_run(db, run, previous)[:15]
    platform_pulse = compute_platform_pulse(db, run, previous)
    platform_leadership = compute_platform_leadership(platform_pulse)
    fastest_rising = compute_fastest_rising(top_trends)
    instagram_content = serialize_instagram_content(db, run, previous, limit=5)
    emerging = compute_emerging_trends(db, run, previous, limit=5)
    medical = compute_medical_intelligence(db, run, previous)

    started = run.snapshot_started_at or datetime.datetime.utcnow()
    daypart = run.snapshot_period or "evening"
    last_updated = started.strftime("%I:%M %p")
    if last_updated.startswith("0"):
        last_updated = last_updated[1:]

    return {
        "id": f"snap-{daypart}-{run.id}",
        "date": started.strftime("%b %d, %Y").upper(),
        "dayOfWeek": started.strftime("%A"),
        "daypart": daypart,
        "daypartLabel": f"{daypart.capitalize()} Intelligence",
        "lastUpdated": last_updated,
        "postsAnalyzed": db.query(ProcessedSignal).count(),
        "trendSignals": run.corpus_size or 0,
        "sourcesCount": db.query(Source).filter(Source.enabled == True).count(),
        "topTrends": top_trends,
        "platformPulse": platform_pulse,
        "platformLeadership": platform_leadership,
        "fastestRising": fastest_rising,
        "instagramContent": instagram_content,
        "emergingTrends": emerging,
        "medicalIntelligence": medical,
    }


@router.get("/snapshot")
def get_snapshot(daypart: Optional[str] = Query(None), db: Session = Depends(get_db)):
    run = _find_run_for_daypart(db, daypart)
    if not run:
        return _error("NO_SNAPSHOT", "No trend run available yet -- run clustering and trend scoring first", 404)
    snapshot = _build_snapshot(db, run)
    return _ok(snapshot, snapshot_id=snapshot["id"])


@router.get("/trends")
def list_trends(
    category: str = Query("all"),
    daypart: Optional[str] = Query(None),
    sort: str = Query("rank"),
    search: Optional[str] = Query(None),
    limit: int = Query(15, le=200),
    db: Session = Depends(get_db),
):
    run = _find_run_for_daypart(db, daypart)
    if not run:
        return _error("NO_SNAPSHOT", "No trend run available yet", 404)
    previous = get_previous_trend_run(db, run)
    trends = serialize_trends_for_run(db, run, previous)

    if category and category != "all":
        trends = [t for t in trends if t["category"] == category]
    if search:
        needle = search.lower()
        trends = [t for t in trends if needle in t["title"].lower() or needle in t["normalizedTopic"].lower()]

    if sort == "momentum":
        trends.sort(key=lambda t: t["momentum"], reverse=True)
    elif sort == "signals":
        trends.sort(key=lambda t: t["signalCount"] or 0, reverse=True)
    else:
        trends.sort(key=lambda t: t["rank"] if t["rank"] is not None else 999999)

    total = len(trends)
    trends = trends[:limit]

    return _ok(
        {"total": total, "category": category, "sort": sort, "trends": trends},
        snapshot_id=f"snap-{run.snapshot_period}-{run.id}",
    )


@router.get("/trends/{trend_id}")
def get_trend(trend_id: str, db: Session = Depends(get_db)):
    tid = _parse_trend_id(trend_id)
    if tid is None:
        return _error("INVALID_ID", f"invalid trend id: {trend_id}", 400)
    trend = db.query(Trend).get(tid)
    if not trend:
        return _error("NOT_FOUND", f"trend {trend_id} not found", 404)
    run = db.query(TrendRun).get(trend.trend_run_id)
    previous = get_previous_trend_run(db, run)
    return _ok(serialize_trend(db, trend, run, previous))


@router.get("/emerging-trends")
def emerging_trends(daypart: Optional[str] = Query(None), limit: int = Query(5, le=50), db: Session = Depends(get_db)):
    run = _find_run_for_daypart(db, daypart)
    if not run:
        return _error("NO_SNAPSHOT", "No trend run available yet", 404)
    previous = get_previous_trend_run(db, run)
    return _ok(compute_emerging_trends(db, run, previous, limit=limit))


@router.get("/platform-pulse")
def platform_pulse(daypart: Optional[str] = Query(None), db: Session = Depends(get_db)):
    run = _find_run_for_daypart(db, daypart)
    if not run:
        return _error("NO_SNAPSHOT", "No trend run available yet", 404)
    previous = get_previous_trend_run(db, run)
    return _ok(compute_platform_pulse(db, run, previous))


@router.get("/instagram-content")
def instagram_content(daypart: Optional[str] = Query(None), limit: int = Query(5, le=50), db: Session = Depends(get_db)):
    run = _find_run_for_daypart(db, daypart)
    previous = get_previous_trend_run(db, run) if run else None
    return _ok(serialize_instagram_content(db, run, previous, limit=limit))


@router.get("/medical-intelligence")
def medical_intelligence(daypart: Optional[str] = Query(None), db: Session = Depends(get_db)):
    run = _find_run_for_daypart(db, daypart)
    if not run:
        return _error("NO_SNAPSHOT", "No trend run available yet", 404)
    previous = get_previous_trend_run(db, run)
    data = compute_medical_intelligence(db, run, previous)
    if data is None:
        return _error("NO_MEDICAL_TRENDS", "No medical-vertical trends found in the current snapshot", 404)
    return _ok(data)


class RefreshSnapshotRequestBody(BaseModel):
    daypart: Optional[str] = None
    forceReanalysis: Optional[bool] = False
    enrich: Optional[bool] = False


def _do_snapshot_refresh(db: Session, enrich: bool) -> dict:
    """The actual refresh work, run inside a background task (see
    refresh_snapshot below) instead of blocking the HTTP request -- trend
    scoring plus optional LLM enrichment (each call ~5s+) made this a slow
    synchronous endpoint before. Raising here is caught by job_queue.run_job
    and recorded as a FAILED job rather than crashing the background task."""
    trend_run = run_trend_intelligence(db=db, write_json=False)
    if trend_run is None:
        raise ValueError("No cluster run available -- run clustering before refreshing trends")

    if enrich:
        enrich_trend_run(db, trend_run_id=trend_run.id)

    snapshot = _build_snapshot(db, trend_run)
    return {
        "snapshot": snapshot,
        "refreshedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "signalsIngested": trend_run.corpus_size or 0,
    }


@router.post("/snapshot/refresh", status_code=202)
def refresh_snapshot(
    background_tasks: BackgroundTasks,
    body: RefreshSnapshotRequestBody = RefreshSnapshotRequestBody(),
    db: Session = Depends(get_db),
):
    job = create_job(db, job_type="snapshot_refresh", params={"enrich": bool(body.enrich), "daypart": body.daypart})
    background_tasks.add_task(run_job, job.id, lambda job_db: _do_snapshot_refresh(job_db, body.enrich))
    return _ok({
        "jobId": job.id,
        "status": job.status,
        "message": f"Snapshot refresh started -- poll GET /api/v1/jobs/{job.id} for status",
    })


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        return _error("JOB_NOT_FOUND", f"No job with id {job_id}", 404)
    return _ok(serialize_job(job))
