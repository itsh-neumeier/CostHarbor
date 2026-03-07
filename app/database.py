"""SQLAlchemy database setup."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    """Dependency for FastAPI routes to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
