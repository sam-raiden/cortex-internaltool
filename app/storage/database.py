import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc")

# Defense in depth for the Stage 9.2 guarantee (dev DB must never be touched by
# tests): if this module is imported while pytest is running but DATABASE_URL
# still points at the protected dev database, something imported this module
# before tests/conftest.py could redirect DATABASE_URL to the test database.
# Fail loudly here instead of silently binding to the dev DB.
if "pytest" in sys.modules and "tamilsh_poc" in DATABASE_URL and "test" not in DATABASE_URL:
    raise RuntimeError(
        "Refusing to bind SQLAlchemy engine to the protected dev database "
        f"({DATABASE_URL!r}) while running under pytest. app.storage.database "
        "was imported before tests/conftest.py set DATABASE_URL to the test "
        "database - check for a module-level import that runs ahead of "
        "conftest.py's override."
    )

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
