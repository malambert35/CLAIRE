import io
import json
import os
from uuid import UUID
from zipfile import ZipFile

import pytest
from claire.archive import Archive
from claire.archive_admin import reconcile
from claire.config import Settings
from claire.db import Base, Family, User
from claire.identity import passwords
from claire.main import create_app
from claire.portable import verify_package
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture
def household(tmp_path):
    settings = Settings(
        database_url=os.environ.get("CLAIRE_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'memory.db'}"),
        data_dir=tmp_path / "archive",
        origin="https://testserver",
        static_dir=tmp_path / "missing",
    )
    app = create_app(settings)
    Base.metadata.drop_all(app.state.engine)
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        first, second = Family(name="First"), Family(name="Second")
        db.add_all([first, second])
        db.flush()
        for name, family, role in [
            ("alice", first, "member"),
            ("bob", first, "family_admin"),
            ("reader", first, "reader"),
            ("outsider", second, "family_admin"),
        ]:
            db.add(
                User(
                    email=f"{name}@example.test",
                    family_id=family.id,
                    role=role,
                    password_hash=passwords.hash("fictional-long-password"),
                )
            )
        db.commit()
    clients = {}
    for name in ("alice", "bob", "reader", "outsider"):
        client = TestClient(app, base_url="https://testserver")
        client.headers["origin"] = "https://testserver"
        response = client.post(
            "/api/v1/auth/login",
            json={"email": f"{name}@example.test", "password": "fictional-long-password"},
        )
        client.headers["x-csrf-token"] = response.json()["csrf_token"]
        clients[name] = client
    yield clients, settings
    for client in clients.values():
        client.close()
    Base.metadata.drop_all(app.state.engine)
    app.state.engine.dispose()


def draft(**changes):
    return {
        "title": "The summer journey",
        "content": "My original recollection.",
        "confirmed": True,
        **changes,
    }


def test_text_document_import_search_and_visibility(household):
    clients, _ = household
    alice, bob = clients["alice"], clients["bob"]
    body = {
        "filename": "lettre.md",
        "title": "Une lettre",
        "content": "Texte original : **Boréal**.",
        "confirmed": True,
    }
    response = alice.post("/api/v1/memories/documents", json=body)
    assert response.status_code == 201
    document = response.json()
    assert document["memory_type"] == "document" and document["visibility"] == "private"
    assert document["verification"] == "uncertain"
    assert "lettre.md" in document["sources"][-1]["reference"]
    query = "/api/v1/memories?kind=document&q=BORÉAL"
    assert [item["id"] for item in alice.get(query).json()] == [document["id"]]
    assert bob.get(query).json() == []
    assert clients["outsider"].get(query).json() == []
    path = f"/api/v1/memories/{document['id']}"
    edited = alice.put(
        path,
        json=draft(title="Une lettre", content=body["content"], visibility="family", expected_revision=1),
    )
    assert edited.status_code == 200 and edited.json()["memory_type"] == "document"
    assert bob.get(query).json()[0]["id"] == document["id"]
    assert bob.get(path + "/history").status_code == 403
    alice.post(path + "/delete", json={"confirmed": True, "expected_revision": 2})
    assert bob.get(query).json() == [] and alice.get(query).json() == []
    assert alice.get(query + "&deleted=true").json()[0]["id"] == document["id"]


def test_document_input_limits_confirmation_and_reader_role(household):
    clients, _ = household
    body = {"filename": "letter.txt", "title": "Letter", "content": "Original testimony."}
    path = "/api/v1/memories/documents"
    assert clients["alice"].post(path, json=body).status_code == 422
    body["confirmed"] = True
    assert clients["reader"].post(path, json=body).status_code == 403
    for changes in (
        {"filename": "file.pdf"},
        {"filename": "../file.md"},
        {"content": "binary\x00data"},
        {"content": "x" * 6001},
        {"content": "é" * 5000},
    ):
        assert clients["alice"].post(path, json={**body, **changes}).status_code == 422
    assert clients["alice"].get("/api/v1/memories?kind=document").json() == []


def test_import_preview_confirmation_private_copy_and_history(household, tmp_path):
    clients, _ = household
    alice, bob = clients["alice"], clients["bob"]
    original = alice.post("/api/v1/memories", json=draft()).json()
    path = f"/api/v1/memories/{original['id']}"
    alice.put(path, json=draft(content="Nouveau récit.", visibility="family", expected_revision=1))
    alice.post(path + "/delete", json={"expected_revision": 2, "confirmed": True})
    package = alice.get(path + "/export").content
    headers = {"content-type": "application/zip"}
    preview = alice.post("/api/v1/memory-import/preview", content=package, headers=headers)
    assert preview.status_code == 200 and preview.json()["revisions"] == 3
    assert alice.get("/api/v1/memories").json() == []
    assert alice.post("/api/v1/memory-import/confirm", content=package, headers=headers).status_code == 422
    headers["x-import-confirm"] = preview.json()["sha256"]
    response = alice.post("/api/v1/memory-import/confirm", content=package, headers=headers)
    assert response.status_code == 201
    imported_path = f"/api/v1/memories/{response.json()['id']}"
    assert response.json()["id"] != original["id"]
    imported = alice.get(imported_path).json()
    assert imported["visibility"] == "private" and not imported["deleted"]
    assert imported["content"] == "Nouveau récit." and imported["revision"] == 4
    assert bob.get(imported_path).status_code == 404
    history = alice.get(imported_path + "/history").json()
    assert history[-1]["content"] == original["content"]
    assert all(item["visibility"] == "private" for item in history)
    assert original["id"] in history[-1]["sources"][-1]["reference"]
    assert alice.get(path).json()["deleted"]  # No overwrite of original.
    exported = tmp_path / "reexport.zip"
    exported.write_bytes(alice.get(imported_path + "/export").content)
    assert verify_package(exported)["revision"] == 4
    for name in ("reader",):
        assert (
            clients[name].post("/api/v1/memory-import/preview", content=package, headers=headers).status_code
            == 403
        )
    assert alice.post("/api/v1/memory-import/preview", content=b"bad zip", headers=headers).status_code == 422
    assert (
        alice.post(
            "/api/v1/memory-import/preview", content=package, headers={**headers, "x-csrf-token": "wrong"}
        ).status_code
        == 403
    )


def test_portable_export_preserves_revisions_and_is_owner_only(household, tmp_path):
    clients, _ = household
    alice = clients["alice"]
    saved = alice.post("/api/v1/memories", json=draft()).json()
    path = f"/api/v1/memories/{saved['id']}"
    alice.put(path, json=draft(content="Version partagée — été.", visibility="family", expected_revision=1))
    assert clients["bob"].get(path + "/export").status_code == 403
    assert clients["outsider"].get(path + "/export").status_code == 404
    response = alice.get(path + "/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    package = tmp_path / "memory.zip"
    package.write_bytes(response.content)
    manifest = verify_package(package)
    assert manifest["revision"] == 2
    with ZipFile(package) as bundle:
        assert bundle.read("revisions/1/content.md").decode() == "My original recollection."
        assert bundle.read("revisions/2/content.md").decode() == "Version partagée — été."
        assert json.loads(bundle.read("revisions/1/metadata.json"))["visibility"] == "private"
    # Deletion must not destroy the owner's portable revision history.
    alice.post(path + "/delete", json={"expected_revision": 2, "confirmed": True})
    package.write_bytes(alice.get(path + "/export").content)
    assert verify_package(package)["revision"] == 3
    # Tampering and path injection are rejected without extracting any files.
    damaged = io.BytesIO()
    with ZipFile(package) as original, ZipFile(damaged, "w") as target:
        for name in original.namelist():
            target.writestr(name, b"changed" if name.endswith("content.md") else original.read(name))
    package.write_bytes(damaged.getvalue())
    with pytest.raises(ValueError, match="checksum"):
        verify_package(package)
    with ZipFile(package, "a") as bundle:
        bundle.writestr("../escape.txt", "unsafe")
    with pytest.raises(ValueError, match="Unexpected"):
        verify_package(package)


def test_private_shared_revocation_history_and_other_family(household):
    clients, _ = household
    alice, bob, outsider = (clients[name] for name in ("alice", "bob", "outsider"))
    saved = alice.post("/api/v1/memories", json=draft()).json()
    path = f"/api/v1/memories/{saved['id']}"
    for client in (bob, outsider):
        assert client.get(path).status_code == 404
        assert client.get("/api/v1/memories?q=summer").json() == []
        assert client.get(path + "/history").status_code == 404
    shared = alice.put(path, json=draft(visibility="family", expected_revision=1))
    assert shared.status_code == 200
    assert bob.get(path).json()["content"] == "My original recollection."
    assert outsider.get(path).status_code == 404
    assert bob.get(path + "/history").status_code == 403
    assert bob.put(path, json=draft(expected_revision=2)).status_code == 403
    assert alice.put(path, json=draft(expected_revision=2)).status_code == 200
    assert bob.get(path).status_code == 404
    assert len(alice.get(path + "/history").json()) == 3


def test_revision_conflict_delete_restore_and_persistence(household):
    clients, settings = household
    alice = clients["alice"]
    saved = alice.post("/api/v1/memories", json=draft(visibility="family")).json()
    path = f"/api/v1/memories/{saved['id']}"
    edited = alice.put(path, json=draft(content="Correction, with original retained.", expected_revision=1))
    assert edited.status_code == 200
    assert alice.put(path, json=draft(expected_revision=1)).status_code == 409
    archive = Archive(settings.data_dir)
    metadata, content = archive.read(UUID(saved["family_id"]), UUID(saved["owner_id"]), UUID(saved["id"]), 1)
    assert content == "My original recollection." and str(metadata.contributor_id) == saved["owner_id"]
    assert alice.post(path + "/delete", json={"expected_revision": 2, "confirmed": True}).status_code == 200
    assert alice.get("/api/v1/memories").json() == []
    assert len(alice.get("/api/v1/memories?deleted=true").json()) == 1
    assert clients["bob"].get(path).status_code == 404
    assert alice.post(path + "/restore", json={"expected_revision": 3, "confirmed": True}).status_code == 200
    assert alice.get(path).json()["revision"] == 4
    # A fresh application instance reads the same database and archive, not process state.
    restarted = create_app(settings)
    with TestClient(restarted, base_url="https://testserver") as client:
        client.cookies.update(alice.cookies)
        assert client.get(path).json()["content"] == "Correction, with original retained."


def test_confirmation_readonly_role_and_csrf(household):
    clients, _ = household
    assert clients["alice"].post("/api/v1/memories", json=draft(confirmed=False)).status_code == 422
    assert clients["reader"].post("/api/v1/memories", json=draft()).status_code == 403
    assert (
        clients["alice"]
        .post("/api/v1/memories", json=draft(), headers={"x-csrf-token": "invalid"})
        .status_code
        == 403
    )
    assert clients["alice"].post("/api/v1/memories", json=draft(owner_id="forged")).status_code == 422


def test_archive_catalogue_mismatch_fails_closed(household):
    clients, settings = household
    saved = clients["alice"].post("/api/v1/memories", json=draft(visibility="family")).json()
    archive = Archive(settings.data_dir)
    metadata, content = archive.read(UUID(saved["family_id"]), UUID(saved["owner_id"]), UUID(saved["id"]))
    # Simulate crash after archive commit but before catalogue commit, including sharing revocation.
    changed = metadata.model_copy(update={"revision": 2, "parent_revision": 1, "visibility": "private"})
    archive.write(changed, content, 1)
    response = clients["bob"].get(f"/api/v1/memories/{saved['id']}")
    assert response.status_code == 503
    assert content not in response.text
    engine = create_engine(settings.db_url())
    reconcile(engine, archive, UUID(saved["id"]))
    engine.dispose()
    assert clients["bob"].get(f"/api/v1/memories/{saved['id']}").status_code == 404
    assert clients["alice"].get(f"/api/v1/memories/{saved['id']}").json()["revision"] == 2
