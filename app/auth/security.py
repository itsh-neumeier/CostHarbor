"""Password hashing and initial admin creation."""

import logging

import bcrypt

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_initial_admin() -> None:
    """Create the initial admin user if no users exist."""
    from app.auth.models import User

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                username=settings.admin_username,
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info("Initial admin user '%s' created", settings.admin_username)
    finally:
        db.close()
