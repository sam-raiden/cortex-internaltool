from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.storage.database import get_db
from app.models.schema import TrendRun, Trend

router = APIRouter(prefix="/api/trends", tags=["trends"])

@router.get("/latest")
def get_latest_trends(db: Session = Depends(get_db)):
    trend_run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    if not trend_run:
        raise HTTPException(status_code=404, detail="No trends available")
        
    out_trends = []
    total_signals = db.query(Trend).first() 
    # Usually easier to grab from corpus size or metadata
    
    for tr in trend_run.trends:
        reps = []
        for r in sorted(tr.representatives, key=lambda x: x.rank):
            reps.append({
                "post_id": r.post_id,
                "canonical_text": r.signal.canonical_text if r.signal else "UNKNOWN",
                "account": r.signal.post.page.username if r.signal and r.signal.post and r.signal.post.page else "UNKNOWN"
            })
            
        out_trends.append({
            "rank": tr.rank,
            "trend_id": f"TRND-{tr.id}",
            "label": tr.label,
            "label_quality": tr.label_quality,
            "trend_score": round(tr.trend_score, 4) if tr.trend_score else 0.0,
            "evidence_strength": tr.evidence_strength,
            "confidence": tr.trend_confidence,
            "trend_strength": tr.trend_strength,
            "trend_status": tr.trend_status,
            "cluster_size": tr.cluster_size,
            "corpus_support": round(tr.corpus_support, 4) if tr.corpus_support else 0.0,
            "embedding_cohesion": round(tr.embedding_cohesion, 4) if tr.embedding_cohesion else 0.0,
            "semantic_quality": tr.semantic_quality,
            "source_diversity": round(tr.source_diversity, 4) if tr.source_diversity else 0.0,
            "platform_diversity": tr.platform_diversity,
            "account_concentration": round(tr.account_concentration, 4) if tr.account_concentration else 0.0,
            "recency_score": tr.recency_score,
            "engagement_score": None,
            "velocity_score": None,
            "languages": {}, # Simplified out, provided extensively in batch JSON
            "representatives": reps
        })
        
    out_trends = sorted(out_trends, key=lambda x: x["rank"])
    
    return {
        "generated_at": trend_run.created_at.isoformat(),
        "scoring_version": trend_run.scoring_version,
        "corpus": {
            "signals": trend_run.analytics_metadata.get("platforms", {}).get("instagram", {}).get("posts", trend_run.corpus_size) if trend_run.analytics_metadata else trend_run.corpus_size,
            "eligible_signals": trend_run.corpus_size,
            "clusters": trend_run.trend_count,
            "noise": None 
        },
        "metric_availability": trend_run.metrics_availability or {},
        "analytics": trend_run.analytics_metadata or {},
        "trends": out_trends
    }
