"""Memory API: authenticate, filter in SQL, check current archive ACL, then return content."""

from contextlib import contextmanager
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, object_session

from .archive import Archive, ArchiveConflict, Source, checksum
from .db import Audit, Memory, User, now
from .identity import authenticate
from .portable import package_memory


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=6000)
    visibility: Literal["private", "family"] = "private"
    event_date: str | None = Field(default=None, max_length=10)
    verification: Literal["recollection", "verified", "uncertain", "ai_interpretation"] = "recollection"
    sources: list[Source] = Field(default_factory=list, max_length=10)
    confirmed: bool = False

    @field_validator("event_date")
    @classmethod
    def valid_event_date(cls, value):
        if value is None:
            return value
        suffix = {4: "-01-01", 7: "-01", 10: ""}.get(len(value))
        if suffix is None:
            raise ValueError("Use YYYY, YYYY-MM or YYYY-MM-DD")
        date.fromisoformat(value + suffix)
        return value


class MemoryEdit(MemoryInput):
    expected_revision: int = Field(ge=1)


class RevisionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirmed: bool = False


def memory_router(engine, settings):
    router = APIRouter(prefix="/api/v1/memories", tags=["memories"])
    archive = Archive(settings.data_dir)

    @contextmanager
    def access(request):
        with Session(engine) as db:
            user, _ = authenticate(request, db)
            if engine.dialect.name == "postgresql":
                db.execute(
                    text(
                        "SELECT set_config('claire.user_id', :user, true), "
                        "set_config('claire.family_id', :family, true)"
                    ),
                    {"user": user.id, "family": user.family_id},
                )
            try:
                yield db, user
            except ArchiveConflict as error:
                raise HTTPException(409, str(error)) from None
            except (OSError, ValueError, SQLAlchemyError):
                # Do not expose paths, credentials, database errors or uncommitted content.
                raise HTTPException(503, "Archive unavailable or catalogue needs reconciliation") from None

    def visible(user):
        return (
            Memory.family_id == user.family_id,
            or_(Memory.owner_id == user.id, (Memory.visibility == "family") & ~Memory.deleted),
        )

    def find(db, user, memory_id, lock=False):
        statement = select(Memory).where(Memory.id == str(memory_id), *visible(user))
        if lock:
            statement = statement.with_for_update()
        row = db.scalar(statement)
        if not row:
            raise HTTPException(404, "Memory not found")
        return row

    def read(row, user):
        metadata, content = archive.read(UUID(row.family_id), UUID(row.owner_id), UUID(row.id))
        # File commit precedes catalogue commit. Mismatch fails closed, including revocation.
        if (metadata.revision, metadata.visibility, metadata.deleted) != (
            row.revision,
            row.visibility,
            row.deleted,
        ):
            raise HTTPException(503, "Archive catalogue needs reconciliation")
        if str(metadata.owner_id) != user.id and (metadata.visibility != "family" or metadata.deleted):
            raise HTTPException(404, "Memory not found")
        return metadata, content

    def result(metadata, content, user):
        db = object_session(user)
        labels = db.info.setdefault("contributor_labels", {})
        contributor = str(metadata.contributor_id)
        if contributor not in labels:
            labels[contributor] = db.scalar(
                select(User.email).where(User.id == contributor, User.family_id == user.family_id)
            )
        return {
            **metadata.model_dump(mode="json"),
            "content": content,
            "contributor_label": labels[contributor],
            "can_edit": str(metadata.owner_id) == user.id and user.role in {"member", "family_admin"},
        }

    def writable(user, confirmed, row=None):
        if user.role not in {"member", "family_admin"} or (row and row.owner_id != user.id):
            raise HTTPException(403, "Only the contributing owner may change this memory")
        if not confirmed:
            raise HTTPException(422, "Confirm the content and visibility before saving")

    def project(db, row, metadata, action, user):
        row.title, row.visibility, row.revision = metadata.title, metadata.visibility, metadata.revision
        row.deleted, row.event_date, row.updated_at = metadata.deleted, metadata.event_date, now()
        db.add(row)
        db.add(Audit(actor_id=user.id, action=f"memory.{action}:{row.id}"))
        db.commit()

    @router.get("")
    def listing(
        request: Request,
        deleted: bool = False,
        q: str = Query(default="", max_length=200),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
        sort: Literal["updated", "event"] = "updated",
    ):
        with access(request) as (db, user):
            query = select(Memory).where(*visible(user), Memory.deleted == deleted)
            if deleted:
                query = query.where(Memory.owner_id == user.id)
            if q:
                query = query.where(Memory.title.icontains(q, autoescape=True))
            order = Memory.event_date.asc().nullslast() if sort == "event" else Memory.updated_at.desc()
            rows = db.scalars(query.order_by(order, Memory.id).offset(offset).limit(limit)).all()
            return [result(*read(row, user), user) for row in rows]

    @router.post("", status_code=201)
    def create(body: MemoryInput, request: Request):
        with access(request) as (db, user):
            writable(user, body.confirmed)
            metadata = archive.create(
                UUID(user.family_id),
                UUID(user.id),
                body.title,
                body.content,
                visibility=body.visibility,
                event_date=body.event_date,
                verification=body.verification,
                sources=body.sources,
            )
            row = Memory(id=str(metadata.id), family_id=user.family_id, owner_id=user.id)
            project(db, row, metadata, "created", user)
            return result(metadata, body.content, user)

    @router.get("/{memory_id}")
    def detail(memory_id: UUID, request: Request):
        with access(request) as (db, user):
            return result(*read(find(db, user, memory_id), user), user)

    @router.put("/{memory_id}")
    def edit(memory_id: UUID, body: MemoryEdit, request: Request):
        with access(request) as (db, user):
            row = find(db, user, memory_id, lock=True)
            writable(user, body.confirmed, row)
            metadata, _ = read(row, user)
            if metadata.deleted or metadata.revision != body.expected_revision:
                raise HTTPException(409, "Memory changed or is deleted; reload before editing")
            changes = body.model_dump(exclude={"confirmed", "expected_revision", "content"})
            changes.update(
                revision=metadata.revision + 1,
                parent_revision=metadata.revision,
                recorded_at=now(),
                content_sha256=checksum(body.content.encode()),
            )
            updated = metadata.model_validate({**metadata.model_dump(), **changes})
            archive.write(updated, body.content, body.expected_revision)
            project(db, row, updated, "revised", user)
            return result(updated, body.content, user)

    def change_deleted(memory_id, body, request, deleted):
        with access(request) as (db, user):
            row = find(db, user, memory_id, lock=True)
            writable(user, body.confirmed, row)
            metadata, content = read(row, user)
            if metadata.revision != body.expected_revision or metadata.deleted == deleted:
                raise HTTPException(409, "Memory changed; reload before proceeding")
            updated = metadata.model_copy(
                update={
                    "revision": metadata.revision + 1,
                    "parent_revision": metadata.revision,
                    "recorded_at": now(),
                    "deleted": deleted,
                }
            )
            archive.write(updated, content, body.expected_revision)
            project(db, row, updated, "deleted" if deleted else "restored", user)
            return result(updated, content, user)

    @router.post("/{memory_id}/delete")
    def delete(memory_id: UUID, body: RevisionAction, request: Request):
        return change_deleted(memory_id, body, request, True)

    @router.post("/{memory_id}/restore")
    def restore(memory_id: UUID, body: RevisionAction, request: Request):
        return change_deleted(memory_id, body, request, False)

    @router.get("/{memory_id}/history")
    def history(memory_id: UUID, request: Request, offset: int = Query(default=0, ge=0)):
        with access(request) as (db, user):
            row = find(db, user, memory_id)
            # Sharing the current story never grants access to previously private revisions.
            if row.owner_id != user.id:
                raise HTTPException(403, "Revision history is private to its owner")
            metadata, _ = read(row, user)
            revisions = range(max(1, metadata.revision - offset - 49), metadata.revision - offset + 1)
            return [
                result(*archive.read(metadata.family_id, metadata.owner_id, metadata.id, revision), user)
                for revision in reversed(revisions)
            ]

    @router.get("/{memory_id}/export")
    def export(memory_id: UUID, request: Request):
        with access(request) as (db, user):
            row = find(db, user, memory_id)
            if row.owner_id != user.id:
                raise HTTPException(403, "Only the owner may export private revision history")
            metadata, _ = read(row, user)
            data = package_memory(archive, metadata)
            return Response(data, media_type="application/zip", headers={
                "Content-Disposition": f'attachment; filename="claire-memory-{memory_id}.zip"',
                "Cache-Control": "no-store",
            })

    return router
