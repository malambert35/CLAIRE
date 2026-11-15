import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Settings
from .db import Audit, Family, User
from .identity import authenticate, login
from .memories import memory_router

logger = logging.getLogger("claire")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine = create_engine(settings.db_url(), pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="CLAIRE", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine

    @app.middleware("http")
    async def security(request: Request, call_next):
        started = time.monotonic()
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != settings.origin:
                return Response("Origin rejected", status_code=403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return Response("Invalid content length", status_code=400)
            if length > 16384:
                return Response("Request too large", status_code=413)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; style-src 'self'; img-src 'self' data:; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        logger.info(
            "request method=%s status=%s duration_ms=%.1f",
            request.method,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != "0002":
                    raise ValueError("Migration required")
            return {"status": "ready"}
        except (SQLAlchemyError, ValueError):
            raise HTTPException(503, "Database unavailable or migrations pending") from None

    @app.post("/api/v1/auth/login")
    def sign_in(body: Credentials, response: Response):
        with Session(engine) as db:
            token, csrf = login(db, body.email, body.password, settings.session_hours)
        response.set_cookie(
            "claire_session",
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        return {"csrf_token": csrf}

    @app.get("/api/v1/auth/me")
    def me(request: Request):
        with Session(engine) as db:
            user, session = authenticate(request, db)
            family = db.get(Family, user.family_id)
            return {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "family": {"id": family.id, "name": family.name},
                "csrf_token": session.csrf,
            }

    @app.post("/api/v1/auth/logout", status_code=204)
    def sign_out(request: Request, response: Response):
        with Session(engine) as db:
            user, session = authenticate(request, db)
            db.delete(session)
            db.add(Audit(actor_id=user.id, action="logout"))
            db.commit()
        response.delete_cookie("claire_session", path="/")

    @app.get("/api/v1/family/members")
    def members(request: Request):
        with Session(engine) as db:
            user, _ = authenticate(request, db)
            rows = db.scalars(select(User).where(User.family_id == user.family_id)).all()
            return [{"id": row.id, "email": row.email, "role": row.role} for row in rows]

    @app.get("/api/v1/capabilities")
    def capabilities(request: Request):
        with Session(engine) as db:
            authenticate(request, db)
        return {
            "version": "0.1.0",
            "identity": True,
            "family_members": True,
            "memories": True,
            "chat": False,
            "remote_ai": False,
            "integrations": False,
        }

    app.include_router(memory_router(engine, settings))
    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
