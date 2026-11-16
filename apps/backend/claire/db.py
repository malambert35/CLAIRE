from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Family(Base):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30), default="member")


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    started: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Memory(Base):
    """Reconstructable catalogue; content and provenance live in the archive."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(12), default="private")
    revision: Mapped[int] = mapped_column()
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    event_date: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    mime: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(12))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column()
    visibility: Mapped[str] = mapped_column(String(12), default="private")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    active_run: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"))
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="complete")
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
