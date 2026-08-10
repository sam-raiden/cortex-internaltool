import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.models.schema import (
    Base, InstagramPage, InstagramPost, CollectionRun, 
    CollectionError, ProcessedSignal, Cluster, ClusterMember
)

# Testing session setup has been centrally isolated to conftest.py
# The local destructive actions have been removed to avoid dual overlaps!


def test_database_connection(db_session):
    try:
        db_session.execute(text("SELECT 1"))
    except Exception as e:
        pytest.fail(f"Database connection failed: {e}")


def test_basic_insert_read(db_session):
    page = InstagramPage(username="test_page_1", profile_url="htty://test.com", tier=1)
    db_session.add(page)
    db_session.commit()
    
    fetched = db_session.query(InstagramPage).filter_by(username="test_page_1").first()
    assert fetched is not None
    assert fetched.tier == 1


def test_foreign_key_and_relationships(db_session):
    # Ensure page exists
    page = db_session.query(InstagramPage).filter_by(username="test_page_1").first()
    
    post = InstagramPost(
        page_id=page.id,
        instagram_post_id="post_ABC123",
        post_url="http://test.com/p/ABC123",
        caption="#Tamil trend testing"
    )
    db_session.add(post)
    db_session.commit()
    
    # Check relationship
    fetched_page = db_session.query(InstagramPage).filter_by(username="test_page_1").first()
    assert len(fetched_page.posts) >= 1
    assert fetched_page.posts[0].instagram_post_id == "post_ABC123"


def test_instagram_post_id_uniqueness(db_session):
    page = db_session.query(InstagramPage).filter_by(username="test_page_1").first()
    
    duplicate_post = InstagramPost(
        page_id=page.id,
        instagram_post_id="post_ABC123", # Already exists from previous test
        post_url="http://test.com/p/DUP",
    )
    db_session.add(duplicate_post)
    
    with pytest.raises(IntegrityError):
        db_session.commit()
    
    db_session.rollback()


def test_collection_run_and_errors(db_session):
    run = CollectionRun(run_id="old_test_run1", status="FAILED", pages_attempted=1, parser_errors=1)
    db_session.add(run)
    db_session.commit()
    
    fetched_run = db_session.query(CollectionRun).filter_by(run_id="old_test_run1").first()
    assert fetched_run is not None
    assert fetched_run.status == "FAILED"
    
    page = db_session.query(InstagramPage).filter_by(username="test_page_1").first()
    
    err = CollectionError(run_id=fetched_run.id, page_id=page.id, error_type="HTTP_429", error_message="Rate limited")
    db_session.add(err)
    db_session.commit()
    
    fetched_err = db_session.query(CollectionError).filter_by(run_id=fetched_run.id).first()
    assert fetched_err.error_type == "HTTP_429"
    assert fetched_err.run.status == "FAILED"


def test_processed_signal_creation(db_session):
    post = db_session.query(InstagramPost).filter_by(instagram_post_id="post_ABC123").first()
    
    # We will test generic insertion of processed_signal including an embedding
    # pgvector supports writing lists directly, e.g. [0.1, 0.2, 0.3]
    signal = ProcessedSignal(
        post_id=post.id,
        canonical_text="tamil trend testing",
        language="ta",
        processing_status="EMBEDDED",
        embedding=[0.1, 0.2, 0.3] # Using smaller array for mock
    )
    db_session.add(signal)
    db_session.commit()
    
    fetched_signal = db_session.query(ProcessedSignal).filter_by(post_id=post.id).first()
    assert fetched_signal is not None
    assert fetched_signal.canonical_text == "tamil trend testing"
    # Testing existence of vector data
    assert fetched_signal.embedding is not None 

