from typing import Dict, List, Optional
import datetime
from pydantic import BaseModel, Field

class CollectionResult(BaseModel):
    """
    Common platform-neutral collection result encapsulating a single source execution
    """
    source_id: Optional[int] = None
    platform: str
    status: str = "FAILED"
    
    items_discovered: int = 0
    items_created: int = 0
    items_skipped: int = 0
    items_failed: int = 0
    
    duration_ms: int = 0
    started_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    finished_at: Optional[datetime.datetime] = None
    
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)
    
class CollectionBatchResult(BaseModel):
    """
    Common batch result tracking multiple sources in a run
    """
    run_id: Optional[str] = None
    platform: str
    vertical_scope: str = "ALL"
    status: str = "FAILED"
    
    pages_attempted: int = 0
    pages_successful: int = 0
    pages_failed: int = 0
    
    items_discovered: int = 0
    items_created: int = 0
    items_skipped: int = 0
    items_failed: int = 0
    
    duration_ms: int = 0
    started_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    finished_at: Optional[datetime.datetime] = None
    
    errors: List[Dict] = Field(default_factory=list)
    session_state_valid: bool = True
    session_metadata: Dict = Field(default_factory=dict)

class BaseCollector:
    """
    All platform collectors MUST implement this abstraction 
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        
    def collect(self, source, context: Dict = None) -> CollectionResult:
        """
        Process a single source objectively.
        """
        raise NotImplementedError("collect() must be implemented by the Subclass")
        
    def run_batch(self, sources_config: List[Dict], limit: int = None, vertical_scope: str = "ALL") -> CollectionBatchResult:
        """
        Process a batch sequentially mapping targets neutrally.
        """
        raise NotImplementedError("run_batch() must be implemented by the Subclass tracking metrics securely natively.")
