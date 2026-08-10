import ast
import os
import pathlib
import pytest
import sqlalchemy
from sqlalchemy import create_engine, text

def test_test_database_is_isolated():
    url = os.environ.get("TEST_DATABASE_URL", "")
    assert "tamilsh_poc_test" in url
    
def test_protected_database_rejected():
    from tests.conftest import TEST_DATABASE_URL
    os.environ["TEST_DATABASE_URL"] = "postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc"
    with pytest.raises(SystemExit):
        import importlib
        import tests.conftest
        importlib.reload(tests.conftest)
    # Restore explicitly
    os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
    importlib.reload(tests.conftest)

def test_missing_test_database_fails():
    from tests.conftest import TEST_DATABASE_URL
    os.environ["TEST_DATABASE_URL"] = ""
    with pytest.raises(SystemExit):
        import importlib
        import tests.conftest
        importlib.reload(tests.conftest)
    os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
    importlib.reload(tests.conftest)
    
def test_test_cleanup_only_affects_test_db(db_session):
    from app.models.schema import InstagramPage
    page = InstagramPage(username="cleanup_test_user", profile_url="http://x", tier=1)
    db_session.add(page)
    db_session.commit()
    # It inserted safely into test db
    assert db_session.query(InstagramPage).filter_by(username="cleanup_test_user").first() is not None

def test_development_database_unchanged():
    # Attempt connecting securely mapping native
    dev_url = "postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc"
    eng = create_engine(dev_url)
    with eng.connect() as conn:
        res = conn.execute(text("SELECT count(*) FROM instagram_pages WHERE username = 'cleanup_test_user'")).scalar()
        assert res == 0

def test_no_database_url_fallback():
    assert os.environ.get("DATABASE_URL") == os.environ.get("TEST_DATABASE_URL")
    
def test_schema_matches_development(db_session):
    res = db_session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()
    tables = [r[0] for r in res]
    assert "instagram_posts" in tables
    assert "content_sources" in tables

def test_pgvector_available(db_session):
    res = db_session.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).scalar()
    assert res == 'vector'

def test_session_engine_matches_test_database_url():
    # Regression coverage for the bug class that let test code bind
    # app.storage.database's SessionLocal/engine to the dev database: assert
    # the actual bound engine points at TEST_DATABASE_URL, not just that some
    # string env var looks right.
    from app.storage.database import engine
    test_url = sqlalchemy.engine.make_url(os.environ["TEST_DATABASE_URL"])
    assert engine.url.database == test_url.database
    assert engine.url.host == test_url.host
    assert engine.url.port == test_url.port

def test_no_test_file_imports_sessionlocal_or_engine_directly():
    # Enforces "tests must use conftest's db_session fixture, not construct
    # their own session from app.storage.database" as a collection-time
    # check, not just a convention. This is the exact shape of the bug that
    # let 6 test files bypass isolation and pollute the dev database (see
    # STAGE_12_REPORT.md). Known limitation: only catches
    # `from app.storage.database import SessionLocal/engine`, not
    # `import app.storage.database as db` + attribute access.
    tests_dir = pathlib.Path(__file__).parent
    offenders = []
    for path in sorted(tests_dir.glob("*.py")):
        if path.name in {"conftest.py", "test_database_isolation.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.storage.database":
                for alias in node.names:
                    if alias.name in ("SessionLocal", "engine"):
                        offenders.append(f"{path.name}:{node.lineno} imports {alias.name}")
    assert not offenders, (
        "Test files must use conftest's db_session fixture, not import "
        "SessionLocal/engine directly from app.storage.database:\n" + "\n".join(offenders)
    )
