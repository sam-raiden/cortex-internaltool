from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class CollectionResult:
    page_username: str
    success: bool
    posts_discovered: int = 0
    new_posts: int = 0
    existing_posts: int = 0
    extracted_post_ids: List[str] = field(default_factory=list)
    duration_ms: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CollectionBatchResult:
    pages_attempted: int = 0
    pages_successful: int = 0
    pages_failed: int = 0
    posts_discovered: int = 0
    new_posts: int = 0
    existing_posts: int = 0
    posts_with_stable_ids: int = 0
    extracted_post_ids: List[str] = field(default_factory=list)
    login_challenges: int = 0
    access_denied_events: int = 0
    timeouts: int = 0
    parser_failures: int = 0
    errors: List[dict] = field(default_factory=list)
    results: List['CollectionResult'] = field(default_factory=list)
    duration_ms: int = 0
    
    # Telemetry additions Stage 3.7
    run_id: str = ""
    status: str = "SUCCESS"
    session_state_valid: bool = True
