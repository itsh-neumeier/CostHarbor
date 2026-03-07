"""Authentication dependencies for FastAPI routes."""

from fastapi import Request
from fastapi.responses import RedirectResponse


def get_current_user(request: Request):
    """Get current user from session. Redirect to login if not authenticated."""
    user = request.session.get("user")
    if not user:
        return None
    return user


def require_auth(request: Request):
    """Require authentication. Redirect to login if not authenticated."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return user
