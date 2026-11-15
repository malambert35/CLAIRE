"""Offline catalogue recovery. Stop web/worker processes and use migration credentials."""

import argparse
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .archive import Archive
from .config import Settings
from .db import Audit, Memory, User, now


def reconcile(engine, archive: Archive, memory_id: UUID):
    candidates = list(archive.root.glob(f"families/*/users/*/private/memories/{memory_id}/HEAD.json"))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one committed archive for this UUID")
    relative = candidates[0].relative_to(archive.root).parts
    family_id, owner_id = UUID(relative[1]), UUID(relative[3])
    metadata, _ = archive.read(family_id, owner_id, memory_id)
    for revision in range(1, metadata.revision + 1):
        archive.read(family_id, owner_id, memory_id, revision)
    with Session(engine) as db:
        owner = db.get(User, str(owner_id))
        if not owner or owner.family_id != str(family_id):
            raise ValueError("Original owner and family must exist; recovery cannot transfer ownership")
        row = db.get(Memory, str(memory_id))
        if row and (
            row.owner_id != str(owner_id)
            or row.family_id != str(family_id)
            or row.revision > metadata.revision
        ):
            raise ValueError("Catalogue identity mismatch or attempted rollback")
        if metadata.visibility not in {"private", "family"}:
            raise ValueError("This catalogue does not yet support explicit reader grants")
        row = row or Memory(id=str(memory_id), owner_id=str(owner_id), family_id=str(family_id))
        row.title, row.visibility, row.revision = metadata.title, metadata.visibility, metadata.revision
        row.deleted, row.event_date, row.updated_at = metadata.deleted, metadata.event_date, now()
        db.add(row)
        db.add(Audit(action=f"memory.reconciled:{memory_id}"))
        db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memory_id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    engine = create_engine(settings.db_url())
    try:
        reconcile(engine, Archive(settings.data_dir), args.memory_id)
        print("Catalogue reconciled from committed archive; no testimony modified.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
