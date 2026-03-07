"""Test fixtures."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use SQLite for tests if no PostgreSQL available
TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///test.db")

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-pw")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("UPLOAD_DIR", "/tmp/costharbor_test_uploads")
os.environ.setdefault("DOCUMENT_DIR", "/tmp/costharbor_test_docs")

from app.database import Base


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
