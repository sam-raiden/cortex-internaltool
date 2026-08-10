import os
import sys
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup environment for testing natively avoiding overlaps!
# No default fallback: a missing TEST_DATABASE_URL must be observable and
# must fail closed, not silently resolve to a hardcoded test URL.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

if TEST_DATABASE_URL is None or not TEST_DATABASE_URL:
    print("\n========================================")
    print("TEST DATABASE SAFETY FAILURE")
    print("========================================")
    print("TEST_DATABASE_URL is not set.")
    print("Tests require an explicit, isolated test database URL")
    print("(e.g. postgresql://.../tamilsh_poc_test). Refusing to run.")
    print("========================================")
    raise SystemExit("Aborted: TEST_DATABASE_URL missing")

if "tamilsh_poc" in TEST_DATABASE_URL and not "test" in TEST_DATABASE_URL:
    print("\n========================================")
    print("TEST DATABASE SAFETY FAILURE")
    print("========================================")
    print("Pytest attempted to use a protected development database.")
    print("Database: tamilsh_poc")
    print("Tests have been aborted.")
    print("Configure: TEST_DATABASE_URL=<isolated test database>")
    print("No destructive operation was executed.")
    print("========================================")
    raise SystemExit("Aborted due to protected database.")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Import AFTER the DATABASE_URL override above, not before. app.models.schema
# imports app.storage.database, whose module-level `engine`/`SessionLocal`
# bind to DATABASE_URL at import time. Importing Base earlier than this line
# would bind that engine to the (unset) dev DATABASE_URL before the override
# takes effect, silently defeating this file's test-DB isolation for any code
# that imports SessionLocal/engine directly from app.storage.database.
from app.models.schema import Base

print("\n========================================")
print("TEST DATABASE")
print("========================================")
print("Host: localhost")
print("Port: 5433")
print("Database: tamilsh_poc_test")
print("Environment: TEST")
print("\nProtected databases:")
print("tamilsh_poc")
print("\nSafety guard:")
print("ACTIVE")
print("========================================")

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def pytest_configure():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    Base.metadata.create_all(bind=engine)

@pytest.fixture(scope="module")
def db_session():
    # Strict validation mapping natively
    if "tamilsh_poc" in str(engine.url) and not "test" in str(engine.url):
        pytest.fail("Safety Guard triggered! Aborted.")
        
    session = TestingSessionLocal()
    yield session
    
    # Destructive operations protected cleanly
    session.rollback()
    for tbl in reversed(Base.metadata.sorted_tables):
        session.execute(tbl.delete())
    session.commit()
    session.close()
