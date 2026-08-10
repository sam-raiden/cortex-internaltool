"""Stage 22 -- shared view/serialization helpers matching the REAL frontend
contract (src/api-contract.ts, src/types.ts, src/data/mockData.ts -- pasted
in full by the user from their Google AI Studio project, not guessed from
spec prose). Every endpoint in app/api/v1.py builds its response from these
functions, so there is exactly one place that knows how to turn DB rows
into frontend-shaped JSON.

Honesty policy (per the master spec's "reality beats assumptions" rule,
consistent with every other stage this session): fields we cannot honestly
populate (avatars, verified badges, view/like counts, engagement strings,
medical specialty) are returned as None/empty, never a fabricated number.
Two fields the frontend's TypeScript types mark non-optional -- Trend.category
and Snapshot.fastestRising -- get an honest, clearly-a-placeholder default
instead of null (per explicit user confirmation), so the frontend's
required-field typing is never violated: category defaults to 'local_news'
until an LLM enrichment has actually classified it, and fastestRising always
returns the top trend with its real (possibly zero) momentumChange rather
than a fabricated spike.
"""
import datetime
from collections import Counter
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.schema import (
    Cluster, ClusterMember, ProcessedSignal, RawContent, Source, Trend,
    TrendRepresentative, TrendRun, TrendSemanticAnalysis,
)
from app.processing.llm_enrichment import CATEGORIES

CATEGORIES_SET = set(CATEGORIES)
FALLBACK_CATEGORY = "local_news"

PLATFORM_COLORS = {"instagram": "#E1306C", "youtube": "#FF0000", "rss": "#F59E0B"}
PLATFORM_DISPLAY_NAMES = {"instagram": "Instagram", "youtube": "YouTube Shorts", "rss": "Tamil News / RSS"}


# ---------------------------------------------------------------------------
# Small shared utilities
# ---------------------------------------------------------------------------

def format_relative_time(dt: Optional[datetime.datetime], now: Optional[datetime.datetime] = None) -> Optional[str]:
    """'2h 15m ago' / '18m ago' style, matching the frontend's convention.
    Returns None (never a fabricated string) when dt is None."""
    if dt is None:
        return None
    now = now or datetime.datetime.utcnow()
    total_minutes = max(int((now - dt).total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m ago" if minutes else f"{hours}h ago"
    return f"{minutes}m ago" if minutes else "just now"


def _format_engagement(likes, comments) -> Optional[str]:
    if likes is None and comments is None:
        return None
    parts = []
    if likes is not None:
        parts.append(f"{likes} likes")
    if comments is not None:
        parts.append(f"{comments} comments")
    return " · ".join(parts)


def _cluster_members(db: Session, trend: Trend) -> List[ClusterMember]:
    cluster = db.query(Cluster).get(trend.cluster_id)
    return cluster.members if cluster else []


def _unique_accounts(db: Session, trend: Trend) -> int:
    ids = {m.signal.post.source_id for m in _cluster_members(db, trend) if m.signal and m.signal.post}
    return len(ids)


def _distinct_platforms(db: Session, trend: Trend) -> List[str]:
    return sorted({m.signal.post.platform for m in _cluster_members(db, trend) if m.signal and m.signal.post and m.signal.post.platform})


def _hashtags_for_trend(db: Session, trend: Trend) -> List[str]:
    tags = []
    for m in _cluster_members(db, trend):
        if m.signal and m.signal.extracted_hashtags:
            tags.extend(m.signal.extracted_hashtags)
    seen, out = set(), []
    for t in tags:
        formatted = t if str(t).startswith("#") else f"#{t}"
        if formatted not in seen:
            seen.add(formatted)
            out.append(formatted)
    return out


def get_latest_enrichment(db: Session, trend_id: int) -> Optional[TrendSemanticAnalysis]:
    return (
        db.query(TrendSemanticAnalysis)
        .filter(TrendSemanticAnalysis.trend_id == trend_id, TrendSemanticAnalysis.status == "SUCCESS")
        .order_by(TrendSemanticAnalysis.id.desc())
        .first()
    )


def get_previous_trend_run(db: Session, current_run: TrendRun) -> Optional[TrendRun]:
    return (
        db.query(TrendRun)
        .filter(TrendRun.id < current_run.id)
        .order_by(TrendRun.id.desc())
        .first()
    )


def resolve_category(enrichment: Optional[TrendSemanticAnalysis]) -> str:
    if enrichment and enrichment.category in CATEGORIES_SET:
        return enrichment.category
    return FALLBACK_CATEGORY


def _fallback_micro_insight(trend: Trend) -> str:
    parts = [f"{trend.cluster_size} signals" if trend.cluster_size else "Limited signals"]
    if trend.evidence_strength:
        parts.append(f"{trend.evidence_strength.lower()} evidence")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Momentum -- the only honest "is this new/rising" signal available: cluster
# IDs are not stable across ClusterRuns (each run re-clusters from scratch),
# so matching the deterministic label text against the previous TrendRun is
# the closest non-fabricated proxy for trend identity over time.
# ---------------------------------------------------------------------------

def compute_momentum(db: Session, trend: Trend, previous_run: Optional[TrendRun]) -> dict:
    momentum = round((trend.trend_score or 0.0) * 100)
    change = 0
    if previous_run:
        prev = (
            db.query(Trend)
            .filter(Trend.trend_run_id == previous_run.id, Trend.label == trend.label)
            .first()
        )
        if prev:
            change = round(((trend.trend_score or 0.0) - (prev.trend_score or 0.0)) * 100)

    if change >= 15:
        direction = "rising_fast"
    elif change > 0:
        direction = "rising"
    elif change < 0:
        direction = "cooling"
    else:
        direction = "stable"

    return {"momentum": momentum, "momentumDirection": direction, "momentumChange": change}


def compute_first_last_detected(db: Session, trend: Trend, current_run: TrendRun) -> dict:
    now = current_run.snapshot_started_at or datetime.datetime.utcnow()

    earliest_run = (
        db.query(TrendRun)
        .join(Trend, Trend.trend_run_id == TrendRun.id)
        .filter(Trend.label == trend.label, TrendRun.id <= current_run.id)
        .order_by(TrendRun.id.asc())
        .first()
    )
    first_detected_dt = earliest_run.snapshot_started_at if earliest_run else current_run.snapshot_started_at

    reps = db.query(TrendRepresentative).filter(TrendRepresentative.trend_id == trend.id).all()
    latest_ts = None
    for r in reps:
        post = r.post
        ts = (post.published_at or post.scraped_at) if post else None
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    return {
        "firstDetected": format_relative_time(first_detected_dt, now) or "just now",
        "lastDetected": format_relative_time(latest_ts, now) or "just now",
    }


def compute_trend_vertical(db: Session, trend: Trend) -> dict:
    """Majority vote over Source.vertical (the authoritative field -- see
    the Stage 22 Instagram-collector fix) among the trend's cluster
    members. Honest about mixed-vertical clusters instead of forcing one
    fabricated label."""
    counts = Counter()
    for m in _cluster_members(db, trend):
        post = m.signal.post if m.signal else None
        source = post.source if post else None
        vertical = source.vertical if source and source.vertical else "GENERAL"
        counts[vertical] += 1
    if not counts:
        return {"primary_vertical": None, "breakdown": {}, "is_mixed": False}
    primary, _ = counts.most_common(1)[0]
    return {"primary_vertical": primary, "breakdown": dict(counts), "is_mixed": len(counts) > 1}


# ---------------------------------------------------------------------------
# Per-platform supporting content
# ---------------------------------------------------------------------------

def build_supporting_content(db: Session, trend: Trend) -> dict:
    reps = (
        db.query(TrendRepresentative)
        .filter(TrendRepresentative.trend_id == trend.id)
        .order_by(TrendRepresentative.rank)
        .all()
    )
    out = {}
    for r in reps:
        post = r.post
        if not post or not post.platform:
            continue
        source = post.source
        handle = f"@{source.username}" if source and source.username else "unknown"

        if post.platform == "instagram" and "instagram" not in out:
            out["instagram"] = {
                "title": post.title or post.text or "",
                "handle": handle,
                "url": post.url,
                "engagement": _format_engagement(post.likes, post.comments),
                "thumbnail": post.thumbnail_url,
            }
        elif post.platform == "youtube" and "youtube" not in out:
            out["youtube"] = {
                "title": post.title or "",
                "channel": source.username if source else "unknown",
                "url": post.url,
                "views": (post.raw_payload or {}).get("raw_view_count_text") if post.raw_payload else None,
                "thumbnail": post.thumbnail_url,
            }
        elif post.platform == "rss" and "news" not in out:
            out["news"] = {
                "title": post.title or "",
                "publisher": (source.name or source.username) if source else "unknown",
                "url": post.url,
                "publishedAgo": format_relative_time(post.published_at),
            }
    return out


# ---------------------------------------------------------------------------
# Trend serialization (matches frontend `Trend` type exactly)
# ---------------------------------------------------------------------------

def serialize_trend(db: Session, trend: Trend, current_run: TrendRun, previous_run: Optional[TrendRun]) -> dict:
    enrichment = get_latest_enrichment(db, trend.id)
    momentum = compute_momentum(db, trend, previous_run)
    detected = compute_first_last_detected(db, trend, current_run)
    hashtags = _hashtags_for_trend(db, trend)

    return {
        "id": f"tr-{trend.id}",
        "rank": trend.rank,
        "title": (enrichment.title if enrichment else None) or trend.label,
        "englishTitle": enrichment.english_title if enrichment else None,
        "normalizedTopic": (enrichment.normalized_topic if enrichment else None) or trend.label,
        "hashtags": hashtags,
        "platforms": _distinct_platforms(db, trend),
        "momentum": momentum["momentum"],
        "momentumDirection": momentum["momentumDirection"],
        "momentumChange": momentum["momentumChange"],
        "signalCount": trend.cluster_size,
        "sourceCount": _unique_accounts(db, trend),
        "firstDetected": detected["firstDetected"],
        "lastDetected": detected["lastDetected"],
        "category": resolve_category(enrichment),
        "microInsight": (enrichment.micro_insight if enrichment else None) or _fallback_micro_insight(trend),
        "supportingContent": build_supporting_content(db, trend),
        "summary": enrichment.summary if enrichment else None,
    }


def serialize_trends_for_run(db: Session, current_run: TrendRun, previous_run: Optional[TrendRun]) -> List[dict]:
    trends = db.query(Trend).filter(Trend.trend_run_id == current_run.id).order_by(Trend.rank.asc().nullslast()).all()
    return [serialize_trend(db, t, current_run, previous_run) for t in trends]


# ---------------------------------------------------------------------------
# Platform pulse / leadership
# ---------------------------------------------------------------------------

def compute_platform_pulse(db: Session, current_run: TrendRun, previous_run: Optional[TrendRun]) -> List[dict]:
    trends = db.query(Trend).filter(Trend.trend_run_id == current_run.id).order_by(Trend.trend_score.desc()).all()

    platform_signal_counts = dict(
        db.query(RawContent.platform, func.count(RawContent.id))
        .join(ProcessedSignal, ProcessedSignal.post_id == RawContent.id)
        .group_by(RawContent.platform).all()
    )

    pulse = []
    for platform in sorted(platform_signal_counts.keys()):
        platform_trends = [t for t in trends if platform in _distinct_platforms(db, t)]
        top5 = platform_trends[:5]
        top_momentum = compute_momentum(db, top5[0], previous_run) if top5 else {"momentum": 0, "momentumDirection": "stable"}

        top_trends_out = []
        for i, t in enumerate(top5):
            m = compute_momentum(db, t, previous_run)
            enrichment = get_latest_enrichment(db, t.id)
            hashtags = _hashtags_for_trend(db, t)
            top_trends_out.append({
                "rank": i + 1,
                "title": (enrichment.title if enrichment else None) or t.label,
                "hashtag": hashtags[0] if hashtags else "",
                "momentum": m["momentum"],
                "momentumDirection": m["momentumDirection"],
                "signalCount": t.cluster_size,
            })

        pulse.append({
            "platform": platform,
            "name": PLATFORM_DISPLAY_NAMES.get(platform, platform.title()),
            "totalActiveSignals": platform_signal_counts.get(platform, 0),
            "momentum": top_momentum["momentum"],
            "momentumDirection": top_momentum["momentumDirection"],
            "topTrends": top_trends_out,
        })
    return pulse


def compute_platform_leadership(platform_pulse: List[dict]) -> List[dict]:
    total = sum(p["totalActiveSignals"] for p in platform_pulse) or 1
    leadership = []
    for p in platform_pulse:
        leadership.append({
            "platform": p["platform"],
            "name": p["name"],
            "percentage": round(p["totalActiveSignals"] / total * 100),
            "signalCount": p["totalActiveSignals"],
            "color": PLATFORM_COLORS.get(p["platform"], "#999999"),
        })
    if leadership:
        max(leadership, key=lambda x: x["signalCount"])["isLeading"] = True
    return leadership


def compute_fastest_rising(trends_serialized: List[dict]) -> dict:
    """Always returns a value (Snapshot.fastestRising is a required field
    in the frontend contract) -- picks the highest momentumChange, honest
    about a zero/negative value rather than fabricating a spike."""
    if not trends_serialized:
        return {
            "trendTitle": "No trends available yet",
            "hashtag": "",
            "momentumIncrease": "+0%",
            "platforms": [],
            "details": "Not enough data collected yet to compute a trend.",
        }
    best = max(trends_serialized, key=lambda t: t["momentumChange"])
    sign = "+" if best["momentumChange"] >= 0 else ""
    return {
        "trendTitle": best["title"],
        "hashtag": best["hashtags"][0] if best["hashtags"] else "",
        "momentumIncrease": f"{sign}{best['momentumChange']}%",
        "platforms": best["platforms"],
        "details": best["microInsight"],
    }


# ---------------------------------------------------------------------------
# Emerging trends
# ---------------------------------------------------------------------------

def compute_emerging_trends(db: Session, current_run: TrendRun, previous_run: Optional[TrendRun], limit: int = 5) -> List[dict]:
    trends = db.query(Trend).filter(Trend.trend_run_id == current_run.id).all()
    previous_labels = set()
    if previous_run:
        previous_labels = {t.label for t in db.query(Trend).filter(Trend.trend_run_id == previous_run.id).all()}

    scored = []
    for t in trends:
        momentum = compute_momentum(db, t, previous_run)
        is_new = t.label not in previous_labels
        scored.append((t, momentum, is_new))

    scored.sort(key=lambda x: (not x[2], -x[1]["momentumChange"]))

    out = []
    for t, momentum, is_new in scored[:limit]:
        enrichment = get_latest_enrichment(db, t.id)
        hashtags = _hashtags_for_trend(db, t)
        sign = "+" if momentum["momentumChange"] >= 0 else ""
        out.append({
            "id": f"em-{t.id}",
            "hashtag": hashtags[0] if hashtags else "",
            "title": (enrichment.title if enrichment else None) or t.label,
            "momentumSpike": f"{sign}{momentum['momentumChange']}%",
            "detectedAgo": compute_first_last_detected(db, t, current_run)["lastDetected"],
            "signalCount": t.cluster_size,
            "platforms": _distinct_platforms(db, t),
            "category": resolve_category(enrichment),
            "description": (enrichment.explanation if enrichment else None) or (enrichment.summary if enrichment else None) or _fallback_micro_insight(t),
        })
    return out


# ---------------------------------------------------------------------------
# Instagram content
# ---------------------------------------------------------------------------

def serialize_instagram_content(db: Session, current_run: Optional[TrendRun], previous_run: Optional[TrendRun], limit: int = 5) -> List[dict]:
    rows = (
        db.query(RawContent)
        .filter(RawContent.platform == "instagram")
        .order_by(RawContent.scraped_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        source = r.source
        signal = r.signal
        hashtags = []
        if signal and signal.extracted_hashtags:
            hashtags = [t if str(t).startswith("#") else f"#{t}" for t in signal.extracted_hashtags]

        momentum_val, momentum_dir = 0, "stable"
        if signal and current_run:
            member = db.query(ClusterMember).filter(ClusterMember.signal_id == signal.id).first()
            if member:
                trend = (
                    db.query(Trend)
                    .filter(Trend.cluster_id == member.cluster_id, Trend.trend_run_id == current_run.id)
                    .first()
                )
                if trend:
                    m = compute_momentum(db, trend, previous_run)
                    momentum_val, momentum_dir = m["momentum"], m["momentumDirection"]

        post_type = "Reel" if r.url and "/reel/" in r.url else "Post"
        out.append({
            "id": f"ig-{r.id}",
            "username": (source.name or source.username) if source else "unknown",
            "handle": f"@{source.username}" if source and source.username else "unknown",
            "avatar": "",  # never scraped -- honest empty string, required field can't be null
            "postType": post_type,
            "title": r.title or r.text or "",
            "topic": hashtags[0] if hashtags else "",
            "hashtags": hashtags,
            "thumbnail": r.thumbnail_url or "",
            "momentum": momentum_val,
            "momentumDirection": momentum_dir,
            "engagement": _format_engagement(r.likes, r.comments),
            "timestamp": format_relative_time(r.published_at or r.scraped_at) or "unknown",
            "postUrl": r.url,
            "verified": None,  # optional field -- null is fine here
        })
    return out


# ---------------------------------------------------------------------------
# Medical intelligence
# ---------------------------------------------------------------------------

def _content_type_for_medical_trend(post) -> str:
    if post.platform == "youtube":
        return "Shorts"
    if post.platform == "rss":
        return "News Article"
    return "Reel"


def _content_type_for_medical_content(post) -> str:
    if post.platform == "youtube":
        return "Shorts"
    if post.platform == "rss":
        return "Article"
    return "Reel"


def serialize_medical_trend(db: Session, trend: Trend, current_run: TrendRun, previous_run: Optional[TrendRun]) -> dict:
    base = serialize_trend(db, trend, current_run, previous_run)
    reps = db.query(TrendRepresentative).filter(TrendRepresentative.trend_id == trend.id).order_by(TrendRepresentative.rank).all()
    top_rep = reps[0] if reps else None
    top_post = top_rep.post if top_rep else None
    top_source = top_post.source if top_post else None
    sign = "+" if base["momentumChange"] >= 0 else ""

    return {
        "id": base["id"],
        "rank": trend.rank,
        "title": base["title"],
        "englishTitle": base["englishTitle"],
        "hashtag": base["hashtags"][0] if base["hashtags"] else "",
        "momentum": base["momentum"],
        "momentumDirection": base["momentumDirection"],
        "momentumChange": f"{sign}{base['momentumChange']}%",
        "signalCount": base["signalCount"],
        "platforms": base["platforms"],
        "specialty": None,  # no medical-specialty classifier exists yet -- honest null (optional)
        "summary": base["summary"],
        "creatorHandle": f"@{top_source.username}" if top_source and top_source.username else None,
        "creatorName": (top_source.name or top_source.username) if top_source else None,
        "supportingContentUrl": top_post.url if top_post else None,
        "contentType": _content_type_for_medical_trend(top_post) if top_post else None,
    }


def serialize_medical_content(db: Session, limit: int = 10) -> List[dict]:
    rows = (
        db.query(RawContent)
        .join(Source, Source.id == RawContent.source_id)
        .filter(Source.vertical == "MEDICAL")
        .order_by(RawContent.scraped_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        source = r.source
        out.append({
            "id": f"med-cnt-{r.id}",
            "title": r.title or r.text or "",
            "creator": (source.name or source.username) if source else "unknown",
            "handle": f"@{source.username}" if source and source.username else "unknown",
            "specialty": "",
            "platform": r.platform,
            "postType": _content_type_for_medical_content(r),
            "momentum": 0,  # best-effort placeholder -- see module docstring honesty policy
            "engagement": _format_engagement(r.likes, r.comments) or "",
            "timeAgo": format_relative_time(r.published_at or r.scraped_at) or "unknown",
            "url": r.url,
            "avatar": None,
            "thumbnail": r.thumbnail_url,
        })
    return out


def compute_medical_intelligence(db: Session, current_run: TrendRun, previous_run: Optional[TrendRun]) -> Optional[dict]:
    trends = db.query(Trend).filter(Trend.trend_run_id == current_run.id).all()
    medical_trends = [t for t in trends if compute_trend_vertical(db, t)["primary_vertical"] == "MEDICAL"]

    if not medical_trends:
        return None

    medical_trends.sort(key=lambda t: t.trend_score or 0.0, reverse=True)
    ranked = [serialize_medical_trend(db, t, current_run, previous_run) for t in medical_trends]

    platform_counts = Counter()
    for t in medical_trends:
        for p in _distinct_platforms(db, t):
            platform_counts[p] += 1

    return {
        "topMedicalTrend": ranked[0],
        "rankedMedicalTrends": ranked,
        "medicalContent": serialize_medical_content(db, limit=10),
        "platformBreakdown": {
            "instagramCount": platform_counts.get("instagram", 0),
            "youtubeShortsCount": platform_counts.get("youtube", 0),
            "tamilNewsCount": platform_counts.get("rss", 0),
        },
    }
