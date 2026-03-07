"""Authentication routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import verify_password
from app.database import get_db

router = APIRouter(tags=["auth"])


@router.get("/login")
async def login_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
        },
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Ungueltige Anmeldedaten.",
            },
            status_code=401,
        )

    request.session["user"] = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
