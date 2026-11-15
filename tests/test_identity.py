import os

import pytest
from claire.config import Settings
from claire.db import Base, Family, LoginSession, User
from claire.identity import digest, passwords
from claire.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def app(tmp_path):
    url = os.environ.get("CLAIRE_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    app = create_app(
        Settings(
            database_url=url,
            origin="https://testserver",
            static_dir=tmp_path / "missing",
        )
    )
    Base.metadata.drop_all(app.state.engine)
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        first, second = Family(name="First"), Family(name="Second")
        db.add_all([first, second])
        db.flush()
        for email, family in [("alice@example.test", first), ("bob@example.test", second)]:
            db.add(
                User(
                    email=email, family_id=family.id, password_hash=passwords.hash("fictional-long-password")
                )
            )
        db.commit()
    yield app
    Base.metadata.drop_all(app.state.engine)
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as client:
        client.headers["origin"] = "https://testserver"
        yield client


def sign_in(client):
    return client.post(
        "/api/v1/auth/login", json={"email": "alice@example.test", "password": "fictional-long-password"}
    )


def test_authentication_and_secure_cookies(client, app):
    assert client.get("/api/v1/auth/me").status_code == 401
    response = sign_in(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert client.get("/api/v1/auth/me").json()["email"] == "alice@example.test"
    with Session(app.state.engine) as db:
        assert db.get(LoginSession, digest(client.cookies.get("claire_session"))) is not None


def test_family_boundary(client):
    sign_in(client)
    members = client.get("/api/v1/family/members").json()
    assert [m["email"] for m in members] == ["alice@example.test"]


def test_csrf_origin_and_revocation(client):
    csrf = sign_in(client).json()["csrf_token"]
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"origin": "https://evil.test", "x-csrf-token": csrf}
        ).status_code
        == 403
    )
    old_cookie = client.cookies.get("claire_session")
    assert client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf}).status_code == 204
    client.cookies.set("claire_session", old_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_credentials_are_generic_and_throttled(client):
    for _ in range(10):
        result = client.post(
            "/api/v1/auth/login", json={"email": "missing@example.test", "password": "wrong"}
        )
        assert result.status_code == 401
        assert result.json()["detail"] == "Invalid credentials"
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "missing@example.test", "password": "wrong"}
        ).status_code
        == 429
    )


def test_health_is_not_readiness(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503


def test_disabled_capabilities_do_not_claim_success(client):
    sign_in(client)
    flags = client.get("/api/v1/capabilities").json()
    assert not flags["remote_ai"] and not flags["chat"] and not flags["memories"]
    assert client.get("/api/v1/memories").status_code == 404
