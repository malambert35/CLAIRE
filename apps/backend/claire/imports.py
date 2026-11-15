"""Verified portable packages become new private copies, never in-place restores."""

import io
import json
import tempfile
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .archive import Archive, MemoryMetadata, Source, checksum, sync_directory
from .chat import context
from .db import Audit, Memory, now
from .identity import authenticate
from .portable import verify_package

UPLOAD_LIMIT = 34 * 1024 * 1024


def import_router(engine, settings):
    router = APIRouter(prefix="/api/v1/memory-import", tags=["memories"])

    def authorized(request):
        with Session(engine) as db:
            user, _ = authenticate(request, db)
            if user.role not in {"member", "family_admin"}:
                raise HTTPException(403, "This account cannot import memories")

    def process(request, payload, commit):
        try:
            manifest = verify_package(io.BytesIO(payload))
            with ZipFile(io.BytesIO(payload)) as bundle:
                revisions = [
                    (
                        MemoryMetadata.model_validate_json(bundle.read(f"revisions/{number}/metadata.json")),
                        bundle.read(f"revisions/{number}/content.md").decode("utf-8"),
                    )
                    for number in range(1, manifest["revision"] + 1)
                ]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, BadZipFile, RuntimeError):
            raise HTTPException(422, "Invalid or damaged CLAIRE memory package") from None
        digest = checksum(payload)
        latest, content = revisions[-1]
        if not commit:
            return {
                "sha256": digest,
                "title": latest.title,
                "revisions": len(revisions),
                "content": content[:6000],
                "deleted": latest.deleted,
                "original_id": str(latest.id),
                "visibility": "private",
            }
        if request.headers.get("x-import-confirm") != digest:
            raise HTTPException(422, "Preview this exact package and confirm its checksum before importing")
        with Session(engine) as db:
            user, _ = authenticate(request, db)
            if user.role not in {"member", "family_admin"}:
                raise HTTPException(403, "This account cannot import memories")
            context(db, user.id, user.family_id)
            new_id = uuid4()
            archive = Archive(settings.data_dir)
            archive.root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".import-", dir=archive.root) as folder:
                staging = Archive(Path(folder))
                for original, text in revisions:
                    if len(text.encode("utf-8")) > 1_000_000:
                        raise HTTPException(422, "A revision exceeds the archive content limit")
                    origin = {
                        key: str(getattr(original, key))
                        for key in (
                            "id",
                            "family_id",
                            "owner_id",
                            "contributor_id",
                            "revision",
                            "visibility",
                            "deleted",
                        )
                    }
                    provenance = Source(
                        id=uuid4(), reference="CLAIRE import: " + json.dumps(origin), relationship="context"
                    )
                    if len(original.sources) >= 1000:
                        raise HTTPException(422, "Too many source references to preserve import provenance")
                    imported = MemoryMetadata.model_validate(
                        {
                            **original.model_dump(),
                            "id": new_id,
                            "family_id": UUID(user.family_id),
                            "owner_id": UUID(user.id),
                            "contributor_id": UUID(user.id),
                            "visibility": "private",
                            "authorized_readers": [],
                            "sources": [*original.sources, provenance],
                        }
                    )
                    staging.write(imported, text, imported.revision - 1)
                if imported.deleted:
                    imported = imported.model_copy(
                        update={
                            "deleted": False,
                            "parent_revision": imported.revision,
                            "revision": imported.revision + 1,
                            "recorded_at": now(),
                        }
                    )
                    staging.write(imported, content, imported.revision - 1)
                target = archive.location(imported.family_id, imported.owner_id, imported.id)
                target.parent.mkdir(parents=True, exist_ok=True)
                staging.location(imported.family_id, imported.owner_id, imported.id).rename(target)
                sync_directory(target.parent)
            db.add(
                Memory(
                    id=str(new_id),
                    family_id=user.family_id,
                    owner_id=user.id,
                    title=imported.title,
                    visibility="private",
                    revision=imported.revision,
                    deleted=False,
                    event_date=imported.event_date,
                )
            )
            db.add(Audit(actor_id=user.id, action=f"memory.imported:{new_id}"))
            db.commit()
            return {"id": str(new_id), "revision": imported.revision, "visibility": "private"}

    async def receive(request, commit):
        await run_in_threadpool(authorized, request)
        if request.headers.get("content-type") != "application/zip":
            raise HTTPException(415, "Upload a CLAIRE ZIP package")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > UPLOAD_LIMIT:
                raise HTTPException(413, "Package exceeds upload limit")
            payload.extend(chunk)
        try:
            return await run_in_threadpool(process, request, bytes(payload), commit)
        except (OSError, ValueError, SQLAlchemyError):
            raise HTTPException(503, "Import could not be completed; check archive availability") from None

    @router.post("/preview")
    async def preview(request: Request):
        return await receive(request, False)

    @router.post("/confirm", status_code=201)
    async def confirm(request: Request):
        return await receive(request, True)

    return router
