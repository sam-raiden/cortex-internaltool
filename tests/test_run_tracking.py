import pytest
from app.services.collection_run import CollectionRunService
from app.collectors.instagram.models import CollectionBatchResult, CollectionResult
from app.models.schema import CollectionRun, CollectionPageResult, InstagramPage
from app.storage.database import SessionLocal, Base, engine

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    
def test_successful_run_lifecycle(db_session):
    run_db = CollectionRunService.start_run(db_session, "test_run_001", "AUTHENTICATED")
    assert run_db.status == "RUNNING"
    assert run_db.session_state == "AUTHENTICATED"
    
    # Needs a dummy page in DB securely for constraints
    page = InstagramPage(username="tracktest", profile_url="http://test")
    db_session.add(page)
    db_session.commit()
    
    page_res = CollectionResult(page_username="tracktest", success=True)
    page_res.posts_discovered = 3
    page_res.new_posts = 1
    page_res.existing_posts = 2
    
    pr = CollectionRunService.log_page_result(db_session, run_db.id, "tracktest", page_res)
    assert pr.status == "SUCCESS"
    assert pr.posts_discovered == 3
    
    batch = CollectionBatchResult()
    batch.status = "SUCCESS"
    batch.pages_attempted = 1
    batch.pages_successful = 1
    
    CollectionRunService.complete_run(db_session, run_db.id, batch)
    
    assert run_db.status == "SUCCESS"
    assert run_db.pages_attempted == 1

def test_api_compatibility_format(db_session):
    run = CollectionRunService.get_run(db_session, "test_run_001")
    assert run is not None
    assert run.pages_successful == 1
    
    stats = CollectionRunService.get_run_statistics(db_session)
    assert stats["total_runs"] >= 1
