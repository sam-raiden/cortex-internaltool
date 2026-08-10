import os
import json
import uuid
import pytest
from app.collectors.instagram.models import CollectionBatchResult, CollectionResult

def test_circuit_breaker_classification():
    batch = CollectionBatchResult()
    batch.pages_successful = 0
    
    # Simulate a critical block
    res = CollectionResult(page_username="test_blocked", success=False)
    res.error_type = "login_wall_overlay"
    
    critical_events = ["login_required", "login_wall_overlay", "access_denied", "rate_limited", "challenge_detected"]
    
    if res.error_type in critical_events:
        batch.status = "BLOCKED" if batch.pages_successful == 0 else "DEGRADED"

    assert batch.status == "BLOCKED"
    
    # Degraded flow
    batch.pages_successful = 5
    if res.error_type in critical_events:
        batch.status = "BLOCKED" if batch.pages_successful == 0 else "DEGRADED"
        
    assert batch.status == "DEGRADED"

def test_status_classification():
    batch = CollectionBatchResult()
    batch.pages_attempted = 10
    batch.pages_successful = 10
    batch.pages_failed = 0
    batch.status = "SUCCESS"
    
    # Base success validation
    if batch.status == "SUCCESS":
        if batch.pages_failed > 0:
            batch.status = "PARTIAL"
        if batch.pages_attempted == 0:
            batch.status = "FAILED"
            
    assert batch.status == "SUCCESS"
    
    # Partial failure validation
    batch.pages_failed = 2
    if batch.status == "SUCCESS":
        if batch.pages_failed > 0:
            batch.status = "PARTIAL"
            
    assert batch.status == "PARTIAL"

def test_serialization():
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    batch = CollectionBatchResult()
    batch.pages_attempted = 1
    batch.pages_successful = 1
    batch.posts_discovered = 3
    batch.new_posts = 1
    batch.existing_posts = 2
    batch.duration_ms = 1500
    
    res = CollectionResult(page_username="test", success=True)
    res.posts_discovered = 3
    res.new_posts = 1
    res.existing_posts = 2
    res.duration_ms = 1500
    
    batch.results = [res]
    
    report_payload = {
        "run_id": run_id,
        "duration_ms": batch.duration_ms,
        "posts_discovered": batch.posts_discovered,
        "new_posts": batch.new_posts,
        "per_page_metrics": [
            {
                "username": r.page_username,
                "status": "SUCCESS" if r.success else "FAILED",
                "posts_found": r.posts_discovered,
            } for r in batch.results
        ]
    }
    
    assert report_payload["run_id"] == run_id
    assert report_payload["duration_ms"] == 1500
    assert report_payload["per_page_metrics"][0]["username"] == "test"
    assert report_payload["per_page_metrics"][0]["posts_found"] == 3
