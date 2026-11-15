"""Owner memory packages, readable without CLAIRE; no database or credentials."""

import argparse
import io
import json
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .archive import MemoryMetadata, checksum

MAX_BYTES = 32 * 1024 * 1024
MAX_REVISIONS = 500
GUIDE = """CLAIRE portable memory / Souvenir portable

Each revisions/<number>/ directory contains the original UTF-8 content.md and
metadata.json with ownership, visibility, dates, sources and verification status.
manifest.json records SHA-256 checksums. These detect corruption, not forgery.

Chaque dossier revisions/<numero>/ contient le texte original et ses metadonnees.
L'historique peut contenir des versions privees ou supprimees. Conservez ce ZIP
dans un emplacement protege. Le ZIP n'est pas chiffre.

Verify / Verifier: python -m claire.portable path/to/memory.zip
Read Markdown and JSON with any text editor. No model is needed.
This is one memory, not a complete database backup. It contains source references,
not copies of external source documents. Import and full restore are not included.
"""


def package_memory(archive, metadata):
    if metadata.revision > MAX_REVISIONS:
        raise ValueError("Too many revisions for a web export")
    files = {
        "README.txt": GUIDE.encode(),
        "schema.json": json.dumps(MemoryMetadata.model_json_schema(), ensure_ascii=False, indent=2).encode(),
    }
    for revision in range(1, metadata.revision + 1):
        item, content = archive.read(metadata.family_id, metadata.owner_id, metadata.id, revision)
        files[f"revisions/{revision}/metadata.json"] = item.model_dump_json(indent=2).encode()
        files[f"revisions/{revision}/content.md"] = content.encode()
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("Memory exceeds web export size limit")
    # Do not deliver a package built across a concurrent change or revocation.
    latest, _ = archive.read(metadata.family_id, metadata.owner_id, metadata.id)
    if latest != metadata:
        raise ValueError("Memory changed during export; retry")
    manifest = {
        "format": "claire-memory",
        "version": 1,
        "memory_id": str(metadata.id),
        "revision": metadata.revision,
        "files": {name: checksum(data) for name, data in files.items()},
    }
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    return output.getvalue()


def verify_package(path):
    """Validate without extracting any paths or writing into an archive."""
    with ZipFile(path) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or len(names) > MAX_REVISIONS * 2 + 3:
            raise ValueError("Duplicate entries or too many files")
        if sum(entry.file_size for entry in entries) > MAX_BYTES + 1_000_000:
            raise ValueError("Package exceeds verification size limit")
        manifest = json.loads(bundle.read("manifest.json"))
        if manifest.get("format") != "claire-memory" or manifest.get("version") != 1:
            raise ValueError("Unsupported package format")
        memory_id = UUID(manifest["memory_id"])
        count = manifest["revision"]
        if type(count) is not int or not 1 <= count <= MAX_REVISIONS:
            raise ValueError("Invalid revision count")
        expected = {"README.txt", "schema.json"} | {
            f"revisions/{revision}/{name}"
            for revision in range(1, count + 1)
            for name in ("metadata.json", "content.md")
        }
        if set(names) != expected | {"manifest.json"} or set(manifest["files"]) != expected:
            raise ValueError("Unexpected or missing package files")
        for name in expected:
            if checksum(bundle.read(name)) != manifest["files"][name]:
                raise ValueError("Package checksum mismatch")
        previous = None
        for revision in range(1, count + 1):
            item = MemoryMetadata.model_validate_json(bundle.read(f"revisions/{revision}/metadata.json"))
            content = bundle.read(f"revisions/{revision}/content.md")
            content.decode("utf-8")
            if (
                item.id != memory_id
                or item.revision != revision
                or item.parent_revision != (revision - 1 if revision > 1 else None)
                or item.content_sha256 != checksum(content)
            ):
                raise ValueError("Invalid revision chain")
            if previous and (item.family_id, item.owner_id, item.created_at) != (
                previous.family_id,
                previous.owner_id,
                previous.created_at,
            ):
                raise ValueError("Ownership or original recording changed")
            previous = item
        return manifest


def main():
    parser = argparse.ArgumentParser(description="Verify a portable CLAIRE memory ZIP without extracting it")
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    try:
        result = verify_package(args.package)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, RuntimeError) as error:
        parser.exit(1, f"Verification failed: {type(error).__name__}\n")
    print(f"Verified memory {result['memory_id']}: {result['revision']} revisions")


if __name__ == "__main__":
    main()
