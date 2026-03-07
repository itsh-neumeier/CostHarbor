"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import get_db
from app.version import VERSION

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Ensure storage directories exist
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.document_dir).mkdir(parents=True, exist_ok=True)

    # Create initial admin user if no users exist
    from app.auth.security import create_initial_admin
    create_initial_admin()

    logger.info("CostHarbor v%s started", VERSION)
    yield
    logger.info("CostHarbor shutting down")


def create_app() -> FastAPI:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    application = FastAPI(
        title="CostHarbor",
        version=VERSION,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    application.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["VERSION"] = VERSION
    application.state.templates = templates

    # Register routes
    from app.auth.routes import router as auth_router
    from app.core.routes import router as core_router
    from app.sources.routes import router as sources_router
    from app.billing.routes import router as billing_router
    from app.audit.routes import router as audit_router
    from app.documents.routes import router as documents_router
    from app.sources.adapters.vrm_imap_routes import router as vrm_imap_router

    application.include_router(auth_router)
    application.include_router(core_router)
    application.include_router(sources_router)
    application.include_router(billing_router)
    application.include_router(audit_router)
    application.include_router(documents_router)
    application.include_router(vrm_imap_router)

    @application.get("/")
    async def root(request: Request, db: Session = Depends(get_db)):
        user = request.session.get("user")
        if not user:
            return templates.TemplateResponse("dashboard.html", {"request": request, "user": None})

        from app.core.models import Site, Unit, Tenant
        from app.sources.models import SourceConnection, ImportJob
        from app.billing.models import CalculationRun

        stats = {
            "sites": db.query(Site).count(),
            "units": db.query(Unit).count(),
            "tenants": db.query(Tenant).count(),
            "sources": db.query(SourceConnection).count(),
        }

        recent_imports = []
        for job in db.query(ImportJob).order_by(ImportJob.created_at.desc()).limit(5).all():
            src = db.get(SourceConnection, job.source_connection_id)
            recent_imports.append({
                "source_name": src.name if src else "?",
                "status": job.status,
                "created_at": job.created_at,
                "records_imported": job.records_imported,
            })

        recent_calcs = []
        for run in db.query(CalculationRun).order_by(CalculationRun.created_at.desc()).limit(5).all():
            u = db.get(Unit, run.unit_id)
            recent_calcs.append({
                "billing_month": run.billing_month,
                "unit_name": u.name if u else "?",
                "status": run.status,
                "total_amount_cents": run.total_amount_cents,
            })

        return templates.TemplateResponse("dashboard.html", {
            "request": request, "user": user,
            "stats": stats, "recent_imports": recent_imports,
            "recent_calculations": recent_calcs,
        })

    return application


app = create_app()
