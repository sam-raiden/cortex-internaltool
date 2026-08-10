"""Stage 21 -- LLM semantic interpretation layer.

Runs strictly AFTER deterministic trend scoring (app.processing.trend_intelligence),
as a separate, decoupled step -- an LLM failure must never block or corrupt a
deterministic TrendRun/Trend row. The LLM only interprets evidence already
computed by the deterministic layer (cluster representative signals,
hashtags, source accounts, language distribution, scores); it never invents
metrics, counts, or timestamps, and this module never asks it to.

Caching: identical evidence (same representative texts/accounts/hashtags,
same model, same prompt version) reuses a prior SUCCESS result instead of
calling the model again -- see evidence_hash()/get_cached_analysis().
"""
import argparse
import hashlib
import json
import logging
from collections import Counter
from typing import List, Optional

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.models.schema import Trend, TrendRepresentative, TrendRun, TrendSemanticAnalysis
from app.services.llm_client import LLMError, OllamaClient
from app.storage.database import SessionLocal

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3:8b"
PROMPT_VERSION = "v2"  # v2: category taxonomy corrected to match the real frontend contract's
                        # TrendCategory enum (src/types.ts) -- v1 used an invented taxonomy that
                        # doesn't match. Bumping the version deliberately invalidates old cache
                        # entries so no cached v1-taxonomy result is ever served under v2's schema.

CATEGORIES = [
    "politics", "cinema", "memes", "sports", "local_news", "culture", "viral", "medical",
]

SYSTEM_PROMPT = (
    "You are a trend analyst for a Tamil/English digital media trend-intelligence "
    "platform. You will be given evidence about a cluster of related social/news "
    "posts: representative excerpts, hashtags, source accounts, platforms, and "
    "language distribution, plus deterministic scores that have already been "
    "computed by other code. Your job is ONLY to interpret this evidence into a "
    "human-readable title, summary, and category.\n\n"
    "STRICT RULES:\n"
    "- Never invent or state any number, count, statistic, view/like/share count, "
    "or date/timestamp that was not explicitly given to you in the evidence.\n"
    "- Never claim cross-platform presence, source counts, or momentum beyond what "
    "the evidence states.\n"
    "- Never provide medical advice or diagnosis -- if the evidence is medical in "
    "nature, describe it as a trend topic only.\n"
    "- If you are uncertain about something, say so plainly in confidence_reason "
    "instead of guessing.\n"
    "- Base every field only on the provided evidence text."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "normalized_topic": {"type": "string"},
        "title": {"type": "string"},
        "english_title": {"type": "string"},
        "tamil_title": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "micro_insight": {"type": "string"},
        "summary": {"type": "string"},
        "explanation": {"type": "string"},
        "confidence_reason": {"type": "string"},
    },
    "required": [
        "normalized_topic", "title", "english_title", "tamil_title", "category",
        "hashtags", "micro_insight", "summary", "explanation", "confidence_reason",
    ],
}


class TrendSemanticOutput(BaseModel):
    normalized_topic: str
    title: str
    english_title: str
    tamil_title: str
    category: str
    hashtags: List[str]
    micro_insight: str
    summary: str
    explanation: str
    confidence_reason: str

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"invalid category: {v!r}, must be one of {CATEGORIES}")
        return v


def build_evidence(db: Session, trend: Trend) -> dict:
    """Re-derives evidence from already-persisted rows -- works standalone,
    independent of trend_intelligence.py's in-memory state at scoring time."""
    reps = (
        db.query(TrendRepresentative)
        .filter(TrendRepresentative.trend_id == trend.id)
        .order_by(TrendRepresentative.rank)
        .all()
    )

    texts, hashtags, accounts, platforms = [], [], [], []
    languages = Counter()

    for rep in reps:
        signal = rep.signal
        if signal and signal.canonical_text:
            texts.append(signal.canonical_text)
        if signal and signal.extracted_hashtags:
            hashtags.extend(signal.extracted_hashtags)
        if signal and signal.language:
            languages[signal.language] += 1

        post = rep.post
        if post:
            if post.platform:
                platforms.append(post.platform)
            if post.source and post.source.username:
                accounts.append(post.source.username)

    return {
        "representative_texts": texts,
        "hashtags": sorted(set(hashtags)),
        "accounts": sorted(set(accounts)),
        "platforms": sorted(set(platforms)),
        "language_distribution": dict(languages),
        "deterministic_context": {
            "deterministic_label": trend.label,
            "trend_score": trend.trend_score,
            "corpus_support": trend.corpus_support,
            "source_diversity": trend.source_diversity,
            "platform_diversity": trend.platform_diversity,
            "cluster_size": trend.cluster_size,
            "embedding_cohesion": trend.embedding_cohesion,
        },
    }


def evidence_hash(evidence: dict, model: str, prompt_version: str) -> str:
    """Hashes only the CONTENT the LLM actually interprets (representative
    texts/hashtags/accounts/platforms/languages) -- deliberately excludes
    `deterministic_context`, which carries per-trend bookkeeping (label,
    scores) that's unique to whichever cluster/run it came from almost by
    construction. Two different trends with byte-identical representative
    content must hash the same so the cache actually caches; including the
    trend-specific label would defeat that entirely."""
    hashable = {k: v for k, v in evidence.items() if k != "deterministic_context"}
    canonical = json.dumps(hashable, sort_keys=True, default=str)
    payload = f"{model}::{prompt_version}::{canonical}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_analysis(db: Session, hash_value: str) -> Optional[TrendSemanticAnalysis]:
    return (
        db.query(TrendSemanticAnalysis)
        .filter(TrendSemanticAnalysis.evidence_hash == hash_value, TrendSemanticAnalysis.status == "SUCCESS")
        .order_by(TrendSemanticAnalysis.id.desc())
        .first()
    )


def _build_user_prompt(evidence: dict) -> str:
    return (
        "EVIDENCE (all of it -- do not use any information outside this):\n"
        f"Representative excerpts: {json.dumps(evidence['representative_texts'], ensure_ascii=False)}\n"
        f"Hashtags: {json.dumps(evidence['hashtags'], ensure_ascii=False)}\n"
        f"Source accounts: {json.dumps(evidence['accounts'], ensure_ascii=False)}\n"
        f"Platforms: {json.dumps(evidence['platforms'], ensure_ascii=False)}\n"
        f"Language distribution: {json.dumps(evidence['language_distribution'], ensure_ascii=False)}\n"
        f"Deterministic label already computed by other code (for context only, "
        f"do not restate as your own finding): {evidence['deterministic_context']['deterministic_label']!r}\n\n"
        "Produce normalized_topic, title, english_title, tamil_title, category, "
        "hashtags, micro_insight, summary, explanation, and confidence_reason."
    )


def enrich_trend(db: Session, trend: Trend, model: str = DEFAULT_MODEL, client: Optional[OllamaClient] = None) -> TrendSemanticAnalysis:
    """Never raises -- always returns a persisted TrendSemanticAnalysis row,
    SUCCESS or FAILED. The underlying Trend row is never modified."""
    client = client or OllamaClient(model=model)
    evidence = build_evidence(db, trend)

    if not evidence["representative_texts"]:
        row = TrendSemanticAnalysis(
            trend_id=trend.id, evidence_hash="", llm_model=model, llm_prompt_version=PROMPT_VERSION,
            status="FAILED", error_message="no representative text available to interpret",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    h = evidence_hash(evidence, model, PROMPT_VERSION)

    cached = get_cached_analysis(db, h)
    if cached:
        row = TrendSemanticAnalysis(
            trend_id=trend.id, evidence_hash=h, llm_model=model, llm_prompt_version=PROMPT_VERSION,
            status="SUCCESS", normalized_topic=cached.normalized_topic, title=cached.title,
            english_title=cached.english_title, tamil_title=cached.tamil_title, category=cached.category,
            hashtags=cached.hashtags, micro_insight=cached.micro_insight, summary=cached.summary,
            explanation=cached.explanation, confidence_reason=cached.confidence_reason,
            raw_response=cached.raw_response,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    try:
        raw = client.generate_json(SYSTEM_PROMPT, _build_user_prompt(evidence), RESPONSE_SCHEMA, max_retries=1)
        validated = TrendSemanticOutput.model_validate(raw)
    except (LLMError, ValidationError, ValueError) as e:
        logger.warning(f"LLM enrichment failed for trend {trend.id}: {e}")
        row = TrendSemanticAnalysis(
            trend_id=trend.id, evidence_hash=h, llm_model=model, llm_prompt_version=PROMPT_VERSION,
            status="FAILED", error_message=str(e),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    row = TrendSemanticAnalysis(
        trend_id=trend.id, evidence_hash=h, llm_model=model, llm_prompt_version=PROMPT_VERSION,
        status="SUCCESS", normalized_topic=validated.normalized_topic, title=validated.title,
        english_title=validated.english_title, tamil_title=validated.tamil_title, category=validated.category,
        hashtags=validated.hashtags, micro_insight=validated.micro_insight, summary=validated.summary,
        explanation=validated.explanation, confidence_reason=validated.confidence_reason,
        raw_response=raw,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enrich_trend_run(db: Session, trend_run_id: Optional[int] = None, model: str = DEFAULT_MODEL) -> dict:
    if trend_run_id is None:
        trend_run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    else:
        trend_run = db.query(TrendRun).filter(TrendRun.id == trend_run_id).first()

    if not trend_run:
        return {"trend_run_id": None, "total": 0, "enriched": 0, "cached": 0, "failed": 0}

    trends = db.query(Trend).filter(Trend.trend_run_id == trend_run.id).all()
    client = OllamaClient(model=model)

    enriched = cached = failed = 0
    for trend in trends:
        evidence = build_evidence(db, trend)
        h = evidence_hash(evidence, model, PROMPT_VERSION) if evidence["representative_texts"] else None
        was_cached = bool(h and get_cached_analysis(db, h))

        row = enrich_trend(db, trend, model=model, client=client)

        if row.status != "SUCCESS":
            failed += 1
        elif was_cached:
            cached += 1
        else:
            enriched += 1

    return {"trend_run_id": trend_run.id, "total": len(trends), "enriched": enriched, "cached": cached, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="Cortex Trends LLM semantic enrichment")
    parser.add_argument("action", choices=["enrich"])
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = enrich_trend_run(db, trend_run_id=args.run_id, model=args.model)
        print("========================================")
        print("LLM SEMANTIC ENRICHMENT")
        print("========================================")
        print(f"TrendRun: {report['trend_run_id']}")
        print(f"Total trends: {report['total']}")
        print(f"Newly enriched: {report['enriched']}")
        print(f"Reused from cache: {report['cached']}")
        print(f"Failed: {report['failed']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
