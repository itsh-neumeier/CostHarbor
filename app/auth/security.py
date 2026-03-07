"""Password hashing and initial admin creation."""

import logging

from passlib.context import CryptContext

from app.config import settings
from app.database import SessionLocal

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


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
