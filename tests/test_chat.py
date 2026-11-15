import asyncio
import json
import os
from datetime import timedelta

import httpx
import pytest
from claire.config import Settings
from claire.db import Base, Conversation, Family, User, now
from claire.identity import passwords
from claire.main import create_app
from claire.providers import Ollama, ProviderUnavailable, local_endpoint
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


class TestProvider:
    __test__ = False

    def __init__(self):
        self.fail = False
        self.prompts = []

    def models(self):
        return ["synthetic-local-model"]

    def validate_model(self, model):
        if model not in self.models():
            raise ProviderUnavailable("Unknown test model")

    async def stream(self, model, messages):
        self.prompts.append(messages)
        yield "Synthetic "
        if self.fail:
            raise ProviderUnavailable("Injected transport failure")
        yield "response."


@pytest.fixture
def chat_household(tmp_path):
    provider = TestProvider()
    settings = Settings(
        database_url=os.environ.get("CLAIRE_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'chat.db'}"),
        data_dir=tmp_path / "archive",
        static_dir=tmp_path / "missing",
        origin="https://testserver",
    )
    app = create_app(settings, provider)
    Base.metadata.drop_all(app.state.engine)
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        family = Family(name="Test household")
        db.add(family)
        db.flush()
        for name, role in [("alice", "member"), ("bob", "family_admin")]:
            db.add(
                User(
                    email=f"{name}@example.test",
                    family_id=family.id,
                    role=role,
                    password_hash=passwords.hash("fictional-long-password"),
                )
            )
        db.commit()
    clients = []
    for name in ("alice", "bob"):
        client = TestClient(app, base_url="https://testserver")
        client.headers["origin"] = "https://testserver"
        result = client.post(
            "/api/v1/auth/login",
            json={"email": f"{name}@example.test", "password": "fictional-long-password"},
        )
        client.headers["x-csrf-token"] = result.json()["csrf_token"]
        clients.append(client)
    yield app, clients[0], clients[1], provider
    for client in clients:
        client.close()
    Base.metadata.drop_all(app.state.engine)
    app.state.engine.dispose()


def test_stream_persists_history_and_keeps_it_private(chat_household):
    _, alice, bob, provider = chat_household
    conversation = alice.post("/api/v1/conversations", json={"title": "Private chat"}).json()
    path = f"/api/v1/conversations/{conversation['id']}"
    response = alice.post(
        path + "/messages", json={"content": "A fictional question", "model": "synthetic-local-model"}
    )
    assert response.status_code == 200
    assert "event: token" in response.text and "event: done" in response.text
    saved = alice.get(path).json()["messages"]
    assert [message["role"] for message in saved] == ["user", "assistant"]
    assert saved[1]["content"] == "Synthetic response." and saved[1]["status"] == "complete"
    assert bob.get(path).status_code == 404
    assert bob.get("/api/v1/conversations").json() == []
    assert (
        bob.post(
            path + "/messages", json={"content": "Steal history", "model": "synthetic-local-model"}
        ).status_code
        == 404
    )
    assert len(provider.prompts) == 1
    assert [message["role"] for message in provider.prompts[0]] == ["system", "user"]


def test_provider_failure_is_not_reported_as_saved_success(chat_household):
    app, alice, _, provider = chat_household
    provider.fail = True
    conversation = alice.post("/api/v1/conversations", json={"title": "Failure"}).json()
    path = f"/api/v1/conversations/{conversation['id']}"
    response = alice.post(path + "/messages", json={"content": "Question", "model": "synthetic-local-model"})
    assert "event: error" in response.text and "event: done" not in response.text
    assert alice.get(path).json()["messages"][-1]["status"] == "failed"
    with Session(app.state.engine) as db:
        assert db.get(Conversation, conversation["id"]).active_run is None


def test_busy_conversation_rejects_overlapping_generation(chat_household):
    app, alice, _, provider = chat_household
    conversation = alice.post("/api/v1/conversations", json={"title": "Busy"}).json()
    with Session(app.state.engine) as db:
        row = db.get(Conversation, conversation["id"])
        row.active_run = "existing-run"
        row.active_until = now() + timedelta(minutes=5)
        db.commit()
    response = alice.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "Question", "model": "synthetic-local-model"},
    )
    assert response.status_code == 409 and provider.prompts == []


def test_remote_provider_endpoint_is_rejected():
    with pytest.raises(ProviderUnavailable):
        local_endpoint("https://8.8.8.8")
    with pytest.raises(ProviderUnavailable):
        local_endpoint("http://user:secret@127.0.0.1:11434")


def test_real_adapter_protocol_with_mock_transport(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "local:test"}, {"name": "unsafe:cloud"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        payload = json.loads(request.content)
        assert payload["stream"] and payload["think"] is False and "tools" not in payload
        return httpx.Response(200, content=b'{"message":{"content":"Hello"},"done":false}\n{"done":true}\n')

    transport = httpx.MockTransport(handler)
    sync_client, async_client = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: sync_client(transport=transport, **kwargs))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs))
    adapter = Ollama(Settings())
    assert adapter.models() == ["local:test"]
    adapter.validate_model("local:test")

    async def collect():
        return [
            token async for token in adapter.stream("local:test", [{"role": "user", "content": "Synthetic"}])
        ]

    assert asyncio.run(collect()) == ["Hello"]
    assert requests[-1].url.path == "/api/chat"


def test_cloud_backed_alias_is_rejected(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"remote_host": "https://cloud.example.test"})

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    adapter = Ollama(Settings())
    monkeypatch.setattr(adapter, "models", lambda: ["apparently-local"])
    with pytest.raises(ProviderUnavailable, match="Cloud-backed"):
        adapter.validate_model("apparently-local")
