from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, 
    ForeignKey, Float, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, synonym
from pgvector.sqlalchemy import Vector
from app.storage.database import Base

class Source(Base):
    __tablename__ = 'sources'

    def __init__(self, **kwargs):
        if 'username' in kwargs: kwargs['external_id'] = kwargs.pop('username')
        if 'profile_url' in kwargs: kwargs['url'] = kwargs.pop('profile_url')
        super().__init__(**kwargs)

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), unique=True, nullable=False, index=True)
    username = synonym('external_id')
    platform = Column(String(50), default='instagram', index=True)
    source_type = Column(String(50))
    status = Column(String(50), default='ACTIVE')
    url = Column(String(512), nullable=False)
    profile_url = synonym('url')
    vertical = Column(String(50), default="GENERAL", index=True, nullable=False)
    name = Column(String(255))
    priority = Column(Integer, default=1)
    tier = Column(Integer, default=1)
    enabled = Column(Boolean, default=True, index=True)
    active = synonym('enabled')
    health = Column(String(50), default='UNKNOWN', nullable=False)
    configuration = Column(JSON)
    last_collected_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_post_id = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    raw_contents = relationship("RawContent", back_populates="source")
    posts = synonym("raw_contents")
    errors = relationship("CollectionError", back_populates="page")


class RawContent(Base):
    __tablename__ = 'raw_contents'

    def __init__(self, **kwargs):
        if 'instagram_post_id' in kwargs: kwargs['external_content_id'] = kwargs.pop('instagram_post_id')
        if 'page_id' in kwargs: kwargs['source_id'] = kwargs.pop('page_id')
        if 'caption' in kwargs: kwargs['text'] = kwargs.pop('caption')
        if 'post_url' in kwargs: kwargs['url'] = kwargs.pop('post_url')
        super().__init__(**kwargs)

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    external_content_id = Column(String(2048), unique=True, nullable=False, index=True)
    instagram_post_id = synonym('external_content_id')
    platform = Column(String(50), default='instagram')
    vertical = Column(String(50), default='GENERAL')
    content_type = Column(String(50))
    title = Column(String(512))
    raw_payload = Column(JSON)
    url = Column(String(2048), nullable=False)
    post_url = synonym('url')
    text = Column(Text)
    caption = synonym('text')
    hashtags = Column(JSON)
    published_at = Column(DateTime, index=True)
    likes = Column(Integer)
    comments = Column(Integer)
    media_url = Column(Text)
    thumbnail_url = Column(Text)
    media_type = Column(String(50))
    scraped_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("Source", back_populates="raw_contents")
    page = synonym("source")
    signal = relationship("ProcessedSignal", back_populates="post", uselist=False)
    sources = relationship("ContentSource", back_populates="post")


class ContentSource(Base):
    __tablename__ = 'content_sources'

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey('raw_contents.id'), nullable=False, index=True)
    source_type = Column(String(50), nullable=False) # CAPTION, OCR, ASR
    raw_text = Column(Text)
    language = Column(String(50))
    confidence = Column(Float)
    duration_ms = Column(Integer)
    processing_status = Column(String(50), default="COMPLETED")
    processor_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("RawContent", back_populates="sources")


class CollectionRun(Base):
    __tablename__ = 'collection_runs'

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), unique=True, index=True, nullable=False)
    vertical_scope = Column(String(50), default="ALL", index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime)
    status = Column(String(50), nullable=False, index=True)
    session_state = Column(String(50))
    
    pages_attempted = Column(Integer, default=0)
    pages_successful = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)
    
    posts_discovered = Column(Integer, default=0)
    unique_posts = Column(Integer, default=0)
    new_posts = Column(Integer, default=0)
    existing_posts = Column(Integer, default=0)
    
    parser_errors = Column(Integer, default=0)
    navigation_errors = Column(Integer, default=0)
    timeout_errors = Column(Integer, default=0)
    
    login_wall_events = Column(Integer, default=0)
    challenge_events = Column(Integer, default=0)
    access_denied_events = Column(Integer, default=0)
    rate_limit_indicators = Column(Integer, default=0)
    
    duration_ms = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    errors = relationship("CollectionError", back_populates="run")
    page_results = relationship("CollectionPageResult", back_populates="run")

class CollectionPageResult(Base):
    __tablename__ = 'collection_page_results'

    def __init__(self, **kwargs):
        if 'page_id' in kwargs: kwargs['source_id'] = kwargs.pop('page_id')
        super().__init__(**kwargs)

    id = Column(Integer, primary_key=True, index=True)
    run_internal_id = Column(Integer, ForeignKey('collection_runs.id'), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    
    status = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    duration_ms = Column(Integer, default=0)
    
    posts_discovered = Column(Integer, default=0)
    new_posts = Column(Integer, default=0)
    existing_posts = Column(Integer, default=0)
    
    error_type = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("CollectionRun", back_populates="page_results")
    page = relationship("Source")


class CollectionError(Base):
    __tablename__ = 'collection_errors'

    def __init__(self, **kwargs):
        if 'page_id' in kwargs: kwargs['source_id'] = kwargs.pop('page_id')
        super().__init__(**kwargs)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey('collection_runs.id'), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False)
    error_type = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("CollectionRun", back_populates="errors")
    page = relationship("Source", back_populates="errors")


class ProcessedSignal(Base):
    __tablename__ = 'processed_signals'

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey('raw_contents.id'), nullable=False, index=True)
    raw_text = Column(Text)
    ocr_text = Column(Text)
    transcript = Column(Text)
    canonical_text = Column(Text, nullable=False)
    language = Column(String(50))
    extracted_hashtags = Column(JSON)
    # Using generic Vector type without hardcoded dimensions for POC future-proofing
    embedding = Column(Vector)
    signal_quality = Column(String(50))
    source_metadata = Column(JSON)
    embedding_metadata = Column(JSON)
    
    processing_status = Column(String(50), index=True)
    processor_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    post = relationship("RawContent", back_populates="signal")
    clusters = relationship("ClusterMember", back_populates="signal")


class ClusterRun(Base):
    __tablename__ = 'cluster_runs'

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), unique=True, index=True)
    run_name = Column(String(255))
    algorithm = Column(String(50))
    embedding_model = Column(String(255))
    embedding_dimension = Column(Integer)
    metric = Column(String(50))
    hdbscan_version = Column(String(50))
    min_cluster_size = Column(Integer)
    min_samples = Column(Integer)
    corpus_size = Column(Integer)
    cluster_count = Column(Integer)
    noise_count = Column(Integer)
    configuration_hash = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    clusters = relationship("Cluster", back_populates="run")


class Cluster(Base):
    __tablename__ = 'clusters'

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(String(100), index=True)
    run_id = Column(Integer, ForeignKey('cluster_runs.id'), nullable=False, index=True)
    cluster_label = Column(String(255))
    status = Column(String(50))
    representative_signal_id = Column(Integer)
    signal_count = Column(Integer, default=0)
    coherence_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    run = relationship("ClusterRun", back_populates="clusters")
    members = relationship("ClusterMember", back_populates="cluster")


class ClusterMember(Base):
    __tablename__ = 'cluster_members'

    cluster_id = Column(Integer, ForeignKey('clusters.id', ondelete='CASCADE'), primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey('processed_signals.id'), primary_key=True, index=True)
    similarity_score = Column(Float)
    membership_probability = Column(Float)
    outlier_score = Column(Float)
    is_representative = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    cluster = relationship("Cluster", back_populates="members")
    signal = relationship("ProcessedSignal", back_populates="clusters")


class TrendRun(Base):
    __tablename__ = 'trend_runs'

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), unique=True, index=True)
    cluster_run_id = Column(Integer, ForeignKey('cluster_runs.id'), nullable=False)
    algorithm_version = Column(String(50))
    scoring_version = Column(String(50))
    corpus_size = Column(Integer)
    trend_count = Column(Integer)
    configuration_hash = Column(String(255))
    metrics_availability = Column(JSON)
    analytics_metadata = Column(JSON)
    snapshot_started_at = Column(DateTime)
    snapshot_finished_at = Column(DateTime)
    snapshot_date = Column(String(50))
    snapshot_period = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    trends = relationship("Trend", back_populates="run")


class Trend(Base):
    __tablename__ = 'trends'

    id = Column(Integer, primary_key=True, index=True)
    trend_run_id = Column(Integer, ForeignKey('trend_runs.id'), nullable=False, index=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'), nullable=False)
    rank = Column(Integer)
    label = Column(String(255))
    label_confidence = Column(String(50))
    label_quality = Column(String(50))
    label_quality_reason = Column(String(255))
    trend_status = Column(String(50))
    trend_score = Column(Float)
    trend_strength = Column(String(50))
    evidence_strength = Column(String(50))
    trend_confidence = Column(String(50))
    cluster_size = Column(Integer)
    embedding_cohesion = Column(Float)
    semantic_quality = Column(String(50))
    corpus_support = Column(Float)
    source_diversity = Column(Float, nullable=True)
    platform_diversity = Column(Float, nullable=True)
    account_concentration = Column(Float, nullable=True)
    independent_source_strength = Column(Float, nullable=True)
    recency_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("TrendRun", back_populates="trends")
    representatives = relationship("TrendRepresentative", back_populates="trend")


class TrendRepresentative(Base):
    __tablename__ = 'trend_representatives'

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(Integer, ForeignKey('trends.id', ondelete='CASCADE'), nullable=False, index=True)
    post_id = Column(Integer, ForeignKey('raw_contents.id'), nullable=False)
    signal_id = Column(Integer, ForeignKey('processed_signals.id'), nullable=False)
    rank = Column(Integer)

    trend = relationship("Trend", back_populates="representatives")
    post = relationship("RawContent")
    signal = relationship("ProcessedSignal")


class TrendSemanticAnalysis(Base):
    """Stage 21 -- LLM semantic interpretation of a Trend. Deliberately a
    separate table from Trend (not new columns on it): lets caching by
    evidence_hash work independent of which TrendRun/rank a cluster's
    descendant lands in, and lets multiple enrichment attempts (different
    prompt/model versions) coexist without mutating the immutable Trend
    snapshot. A Trend row is always fully valid with zero rows here --
    status='FAILED' or absence both mean "enrichment unavailable", never
    "trend invalid"."""
    __tablename__ = 'trend_semantic_analyses'

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(Integer, ForeignKey('trends.id', ondelete='CASCADE'), nullable=False, index=True)
    evidence_hash = Column(String(64), nullable=False, index=True)
    llm_model = Column(String(100), nullable=False)
    llm_prompt_version = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # SUCCESS, FAILED

    normalized_topic = Column(String(255))
    title = Column(String(255))
    english_title = Column(String(255))
    tamil_title = Column(String(255))
    category = Column(String(50))
    hashtags = Column(JSON)
    micro_insight = Column(Text)
    summary = Column(Text)
    explanation = Column(Text)
    confidence_reason = Column(Text)

    error_message = Column(Text)
    raw_response = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    trend = relationship("Trend", backref="semantic_analyses")


# Backwards compatibility aliases for Stage 1-10.5 logic
InstagramPage = Source
InstagramPost = RawContent
