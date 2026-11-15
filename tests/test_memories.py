import os
from uuid import UUID

import pytest
from claire.archive import Archive
from claire.archive_admin import reconcile
from claire.config import Settings
from claire.db import Base, Family, User
from claire.identity import passwords
from claire.main import create_app
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
