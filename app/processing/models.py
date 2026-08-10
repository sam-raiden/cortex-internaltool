from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class ContentSource:
    type_name: str
    text: str

@dataclass
class ProcessedSignalResult:
    post_id: str
    success: bool
    language: Optional[str] = None
    raw_text_length: int = 0
    canonical_text_length: int = 0
    hashtag_count: int = 0
    processor_version: str = "v1"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0

@dataclass
class ProcessedBatchResult:
    posts_attempted: int = 0
    posts_processed: int = 0
    posts_failed: int = 0
    posts_skipped: int = 0
    languages_detected: Dict[str, int] = field(default_factory=lambda: {"ta": 0, "en": 0, "mixed": 0, "unknown": 0})
    duration_ms: int = 0
