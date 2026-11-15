from uuid import uuid4

import pytest
from claire.archive import Archive, ArchiveConflict, Source, checksum
from claire.db import now


def test_provenance_revisions_and_contradictory_accounts(tmp_path):
    archive = Archive(tmp_path)
    family, owner, source_id = uuid4(), uuid4(), uuid4()
    original = archive.create(
        family,
        owner,
        "The journey",
        "It happened in 1962.",
        sources=[Source(id=source_id, reference="Interview with witness A")],
    )
    other = archive.create(
        family,
        owner,
        "Another account",
        "I recall 1963.",
        sources=[Source(id=original.id, reference="Conflicting testimony", relationship="contradicts")],
    )
    changed = original.model_copy(
        update={"revision": 2, "parent_revision": 1, "recorded_at": now(), "deleted": True}
    )
    archive.write(changed, "It happened in 1962.", 1)
    metadata, text = archive.read(family, owner, original.id, 1)
    assert text == "It happened in 1962."
    assert metadata.contributor_id == owner and metadata.sources[0].id == source_id
    assert archive.read(family, owner, original.id)[0].deleted
    assert archive.read(family, owner, other.id)[1] == "I recall 1963."
    restored = changed.model_copy(update={"revision": 3, "parent_revision": 2, "deleted": False})
    archive.write(restored, text, 2)
    assert not archive.read(family, owner, original.id)[0].deleted


def test_stale_writes_and_tampering_fail_closed(tmp_path):
    archive = Archive(tmp_path)
    memory = archive.create(uuid4(), uuid4(), "Story", "Original")
    second = memory.model_copy(update={"revision": 2, "parent_revision": 1})
    archive.write(second, "Original", 1)
    with pytest.raises(ArchiveConflict):
        archive.write(second, "Original", 1)
    path = archive.location(memory.family_id, memory.owner_id, memory.id)
    (path / "revisions" / "2" / "content.md").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        archive.read(memory.family_id, memory.owner_id, memory.id)


def test_portable_export_contains_original_text_and_checksums(tmp_path):
    archive = Archive(tmp_path / "archive")
    memory = archive.create(uuid4(), uuid4(), "Recipe", "# Crêpes\nA personal recollection.")
    export = tmp_path / "export"
    manifest = archive.export_memory(memory.family_id, memory.owner_id, memory.id, export)
    for relative, digest in manifest["files"].items():
        assert checksum((export / relative).read_bytes()) == digest
    assert "Crêpes" in (export / "revisions/1/content.md").read_text(encoding="utf-8")


def test_reject_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        Archive(tmp_path).location("../../outside", uuid4(), uuid4())
