"""Authenticated, bounded storage of immutable originals; SQL owns current ACLs."""

import io
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import quote, unquote
from uuid import UUID, uuid4
from zipfile import ZIP_STORED, ZipFile

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .archive import checksum, durable_write, sync_directory
from .chat import context
from .db import Asset, Audit, now
from .identity import authenticate

ASSET_LIMIT = 25 * 1024 * 1024


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: Literal["private", "family"] = "private"
    confirmed: bool = False

    @field_validator("filename")
    @classmethod
    def safe_name(cls, value):
        if any(ord(c) < 32 or c in "/\\" for c in value) or value in {".", ".."}:
            raise ValueError("Invalid filename")
        return value

    @field_validator("title")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Enter a title")
        return value


class AssetChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirmed: bool = False
    visibility: Literal["private", "family"] | None = None
    deleted: bool | None = None


def identify(filename, data):
    extension = Path(filename).suffix.lower()
    if extension == ".pdf" and data.startswith(b"%PDF-"):
        return "application/pdf", "document"
    if extension in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "image"
    if extension == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "image"
    if extension == ".webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "image"
    if extension == ".wav" and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav", "audio"
    if extension == ".mp3" and (
        data.startswith(b"ID3") or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)
    ):
        return "audio/mpeg", "audio"
    if (
        extension == ".mp4"
        and data[4:8] == b"ftyp"
        and data[8:12] in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V "}
    ):
        return "video/mp4", "video"
    raise HTTPException(
        422,
        "Supported originals: PDF, JPEG, PNG, WebP, MP3, WAV and MP4. File signature must match its extension.",
    )


def asset_router(engine, settings):
    router = APIRouter(prefix="/api/v1/assets", tags=["files"])

    def actor(request, db, write=False):
        user, _ = authenticate(request, db)
        if write and user.role not in {"member", "family_admin"}:
            raise HTTPException(403, "This account cannot change files")
        context(db, user.id, user.family_id)
        return user

    def visible(user):
        return (
            Asset.family_id == user.family_id,
            or_(Asset.owner_id == user.id, (Asset.visibility == "family") & ~Asset.deleted),
        )

    def find(db, user, asset_id, lock=False):
        stmt = select(Asset).where(Asset.id == str(asset_id), *visible(user))
        row = db.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise HTTPException(404, "File not found")
        return row

    def metadata(row):
        return {
            "schema_version": "1.0.0",
            **{column.name: getattr(row, column.name) for column in Asset.__table__.columns},
            "created_at": row.created_at.isoformat(),
        }

    def location(row):
        root = settings.data_dir.resolve()
        path = root / "files" / str(UUID(row.family_id)) / str(UUID(row.owner_id)) / str(UUID(row.id))
        if not path.resolve().is_relative_to(root):
            raise HTTPException(503, "File storage unavailable")
        return path

    def original(row):
        try:
            path = location(row) / "original"
            if path.stat().st_size != row.size:
                raise ValueError("size")
            data = path.read_bytes()
            if checksum(data) != row.sha256:
                raise ValueError("checksum")
            return data
        except (OSError, ValueError):
            raise HTTPException(503, "Original file unavailable or damaged") from None

    def save(request, body, data):
        mime, category = identify(body.filename, data)
        with Session(engine) as db:
            user = actor(request, db, True)
            row = Asset(
                id=str(uuid4()),
                family_id=user.family_id,
                owner_id=user.id,
                title=body.title,
                filename=body.filename,
                description=body.description,
                mime=mime,
                category=category,
                sha256=checksum(data),
                size=len(data),
                visibility=body.visibility,
                deleted=False,
                revision=1,
                created_at=now(),
            )
            try:
                folder = location(row)
                folder.mkdir(parents=True, exist_ok=False)
                durable_write(folder / "original", data)
                durable_write(
                    folder / "import.json", json.dumps(metadata(row), ensure_ascii=False).encode("utf-8")
                )
                sync_directory(folder)
                db.add(row)
                db.add(Audit(actor_id=user.id, action=f"asset.imported:{row.id}"))
                db.commit()
                context(db, user.id, user.family_id)
                return metadata(row)
            except (OSError, SQLAlchemyError):
                # An interrupted write is unlisted and never served without a committed catalogue row.
                raise HTTPException(503, "File could not be saved; please retry") from None

    @router.post("", status_code=201)
    async def upload(request: Request):
        with Session(engine) as db:
            actor(request, db, True)
        try:
            header = request.headers.get("x-file-metadata", "")
            if len(header) > 20000:
                raise ValueError("metadata")
            body = UploadMetadata.model_validate_json(unquote(header))
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid file information") from None
        if not body.confirmed:
            raise HTTPException(422, "Confirm the file and visibility before importing")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > ASSET_LIMIT:
                raise HTTPException(413, "File exceeds 25 MiB")
            data.extend(chunk)
        if not data:
            raise HTTPException(422, "Empty file")
        return await run_in_threadpool(save, request, body, bytes(data))

    @router.get("")
    def listing(
        request: Request,
        kind: Literal["document", "media"] = "media",
        deleted: bool = False,
        q: str = Query(default="", max_length=200),
        offset: int = Query(default=0, ge=0),
    ):
        with Session(engine) as db:
            user = actor(request, db)
            stmt = select(Asset).where(*visible(user), Asset.deleted == deleted)
            stmt = stmt.where(
                Asset.category == "document" if kind == "document" else Asset.category != "document"
            )
            if deleted:
                stmt = stmt.where(Asset.owner_id == user.id)
            if q:
                stmt = stmt.where(
                    or_(
                        Asset.title.icontains(q, autoescape=True),
                        Asset.description.icontains(q, autoescape=True),
                        Asset.filename.icontains(q, autoescape=True),
                    )
                )
            return [
                metadata(row)
                for row in db.scalars(
                    stmt.order_by(Asset.created_at.desc(), Asset.id).offset(offset).limit(50)
                )
            ]

    @router.patch("/{asset_id}")
    def change(asset_id: UUID, body: AssetChange, request: Request):
        with Session(engine) as db:
            user = actor(request, db, True)
            row = find(db, user, asset_id, True)
            if row.owner_id != user.id:
                raise HTTPException(403, "Only the owner may change this file")
            if not body.confirmed:
                raise HTTPException(422, "Confirmation required")
            if body.expected_revision != row.revision:
                raise HTTPException(409, "File changed; reload before retrying")
            if body.visibility is not None:
                row.visibility = body.visibility
            if body.deleted is not None:
                row.deleted = body.deleted
            row.revision += 1
            db.add(Audit(actor_id=user.id, action=f"asset.changed:{row.id}"))
            db.commit()
            context(db, user.id, user.family_id)
            return metadata(row)

    @router.get("/{asset_id}/content")
    def content(asset_id: UUID, request: Request, download: bool = False):
        with Session(engine) as db:
            user = actor(request, db)
            row = find(db, user, asset_id)
            data = original(row)
            disposition = "attachment" if download or row.category == "document" else "inline"
            headers = {
                "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(row.filename, safe='')}",
                "Cache-Control": "no-store",
                "Accept-Ranges": "bytes",
            }
            requested = request.headers.get("range")
            if requested and not download:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if not match or not any(match.groups()) or any(len(v) > 12 for v in match.groups()):
                    return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
                first, last = match.groups()
                start = int(first) if first else max(0, len(data) - int(last))
                end = min(int(last), len(data) - 1) if first and last else len(data) - 1
                if start > end or start >= len(data):
                    return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
                headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                return Response(data[start : end + 1], status_code=206, media_type=row.mime, headers=headers)
            return Response(
                data,
                media_type=row.mime,
                headers=headers,
            )

    @router.get("/{asset_id}/export")
    def export(asset_id: UUID, request: Request):
        with Session(engine) as db:
            user = actor(request, db)
            row = find(db, user, asset_id)
            payload = io.BytesIO()
            with ZipFile(payload, "w", compression=ZIP_STORED) as bundle:
                bundle.writestr("metadata.json", json.dumps(metadata(row), ensure_ascii=False, indent=2))
                bundle.writestr("original/" + row.filename, original(row))
            return Response(
                payload.getvalue(),
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="claire-file-{row.id}.zip"'},
            )

    return router
