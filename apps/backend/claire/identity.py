import hashlib
import secrets
from datetime import UTC, timedelta

from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Audit, LoginAttempt, LoginSession, User, now

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def authenticate(request: Request, db: Session):
    token = request.cookies.get("claire_session", "")
    session = db.get(LoginSession, digest(token))
    if not session or aware(session.expires) <= now():
        raise HTTPException(401, "Sign in required")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(
        request.headers.get("x-csrf-token", ""), session.csrf
    ):
        raise HTTPException(403, "Invalid CSRF token")
    return user, session


def login(db: Session, email: str, password: str, hours: int):
    # Persistent per-account limiter; serializes existing rows across web workers.
    key = digest(email.lower())
    attempt = db.scalar(select(LoginAttempt).where(LoginAttempt.key == key).with_for_update())
    if attempt and aware(attempt.started) + timedelta(minutes=15) > now() and attempt.count >= 10:
        raise HTTPException(429, "Too many attempts; retry after 15 minutes")
    if not attempt:
        attempt = LoginAttempt(key=key, count=0, started=now())
        db.add(attempt)
    if aware(attempt.started) + timedelta(minutes=15) <= now():
        attempt.started, attempt.count = now(), 0
    attempt.count += 1
    user = db.scalar(select(User).where(User.email == email.lower()))
    valid = passwords.verify(password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        db.add(Audit(action="login.failed"))
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    session = LoginSession(
        token_hash=digest(token), user_id=user.id, csrf=csrf, expires=now() + timedelta(hours=hours)
    )
    db.add(session)
    db.add(Audit(actor_id=user.id, action="login.succeeded"))
    db.commit()
    return token, csrf
