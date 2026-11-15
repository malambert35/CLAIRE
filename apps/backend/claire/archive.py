"""Portable immutable memory revisions. Not yet exposed through web APIs.

The HEAD file is the commit point. A failed write may leave an unreferenced revision,
but cannot replace the previous committed testimony. Locks fail closed after a crash.
"""

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .db import now


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    reference: str = Field(max_length=2000)
    relationship: Literal["supports", "contradicts", "context"] = "supports"


class MemoryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    family_id: UUID
    owner_id: UUID
    contributor_id: UUID
    revision: int = Field(ge=1)
    parent_revision: int | None = None
    title: str = Field(min_length=1, max_length=200)
    memory_type: str = Field(default="personal_memory", max_length=80)
    created_at: datetime
    recorded_at: datetime
    event_date: str | None = Field(default=None, max_length=80)
    visibility: Literal["private", "family", "readers"] = "private"
    authorized_readers: list[UUID] = Field(default_factory=list, max_length=1000)
    sources: list[Source] = Field(default_factory=list, max_length=1000)
    related_people: list[UUID] = Field(default_factory=list, max_length=1000)
    related_events: list[UUID] = Field(default_factory=list, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    verification: Literal["recollection", "verified", "uncertain", "ai_interpretation"] = "recollection"
    deleted: bool = False
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ArchiveConflict(ValueError):
    pass


def checksum(content: bytes):
    return hashlib.sha256(content).hexdigest()


def durable_write(path: Path, content: bytes):
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def sync_directory(path: Path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Archive:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def location(self, family: UUID, owner: UUID, memory: UUID):
        # Stable owner location even after sharing/revocation: ACL is metadata, not path.
        path = self.root / "families" / str(UUID(str(family))) / "users" / str(UUID(str(owner)))
        path = path / "private" / "memories" / str(UUID(str(memory)))
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Archive path escapes root")
        return path

    @contextmanager
    def locked(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        lock = path / ".write-lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise ArchiveConflict("Archive locked; investigate interrupted writer before recovery") from None
        try:
            yield
        finally:
            lock.rmdir()

    def read(self, family: UUID, owner: UUID, memory: UUID, revision: int | None = None):
        path = self.location(family, owner, memory)
        head = json.loads((path / "HEAD.json").read_text(encoding="utf-8"))
        committed = int(head["revision"])
        revision = committed if revision is None else revision
        if revision < 1 or revision > committed:
            raise ValueError("Revision is not committed")
        folder = path / "revisions" / str(revision)
        metadata_bytes = (folder / "metadata.json").read_bytes()
        if revision == committed and checksum(metadata_bytes) != head["metadata_sha256"]:
            raise ValueError("Metadata integrity check failed")
        metadata = MemoryMetadata.model_validate_json(metadata_bytes)
        content = (folder / "content.md").read_bytes()
        if metadata.content_sha256 != checksum(content):
            raise ValueError("Content integrity check failed")
        if (metadata.family_id, metadata.owner_id, metadata.id, metadata.revision) != (
            UUID(str(family)),
            UUID(str(owner)),
            UUID(str(memory)),
            revision,
        ):
            raise ValueError("Archive identity mismatch")
        return metadata, content.decode("utf-8")

    def write(self, metadata: MemoryMetadata, content: str, expected_revision: int):
        encoded = content.encode("utf-8")
        if len(encoded) > 1_000_000:
            raise ValueError("Memory exceeds one megabyte")
        if metadata.revision != expected_revision + 1 or metadata.content_sha256 != checksum(encoded):
            raise ValueError("Invalid revision or checksum")
        path = self.location(metadata.family_id, metadata.owner_id, metadata.id)
        with self.locked(path):
            head_path = path / "HEAD.json"
            current = json.loads(head_path.read_text()) if head_path.exists() else {"revision": 0}
            if current["revision"] != expected_revision:
                raise ArchiveConflict("Memory changed; reload before editing")
            if expected_revision:
                previous, _ = self.read(metadata.family_id, metadata.owner_id, metadata.id)
                if (
                    metadata.created_at != previous.created_at
                    or metadata.parent_revision != expected_revision
                ):
                    raise ValueError("Original recording history must be preserved")
            elif metadata.parent_revision is not None:
                raise ValueError("First revision cannot have a parent")
            revisions = path / "revisions"
            revisions.mkdir(exist_ok=True)
            staging = revisions / f".pending-{uuid4()}"
            staging.mkdir()
            metadata_bytes = metadata.model_dump_json(indent=2).encode("utf-8")
            durable_write(staging / "content.md", encoded)
            durable_write(staging / "metadata.json", metadata_bytes)
            sync_directory(staging)
            target = revisions / str(metadata.revision)
            if target.exists():
                # An interrupted prior write is never silently destroyed.
                raise ArchiveConflict("Uncommitted revision exists; operator recovery required")
            staging.rename(target)
            sync_directory(revisions)
            pointer = path / f".head-{uuid4()}.json"
            durable_write(
                pointer,
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "revision": metadata.revision,
                        "metadata_sha256": checksum(metadata_bytes),
                    }
                ).encode(),
            )
            os.replace(pointer, head_path)
            sync_directory(path)
        return metadata

    def create(self, family: UUID, owner: UUID, title: str, content: str, **attributes):
        recorded = now()
        metadata = MemoryMetadata(
            id=uuid4(),
            family_id=family,
            owner_id=owner,
            contributor_id=owner,
            revision=1,
            title=title,
            created_at=recorded,
            recorded_at=recorded,
            content_sha256=checksum(content.encode()),
            **attributes,
        )
        return self.write(metadata, content, 0)

    def export_memory(self, family: UUID, owner: UUID, memory: UUID, destination: Path):
        """Operator-only export; destination must be new. Never exports credentials."""
        latest, _ = self.read(family, owner, memory)
        source = self.location(family, owner, memory)
        destination.mkdir(parents=True, exist_ok=False)
        manifest = {"schema_version": "1.0.0", "memory_id": str(memory), "files": {}}
        for revision in range(1, latest.revision + 1):
            self.read(family, owner, memory, revision)
            for name in ("metadata.json", "content.md"):
                relative = Path("revisions") / str(revision) / name
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, target)
                manifest["files"][relative.as_posix()] = checksum(target.read_bytes())
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
