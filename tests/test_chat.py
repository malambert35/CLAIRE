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


def test_chat_retrieves_matching_passage_late_in_document(chat_household):
    _, alice, _, provider = chat_household
    response = alice.post(
        "/api/v1/memories/documents",
        json={
            "filename": "journal.txt",
            "title": "Journal du bateau",
            "confirmed": True,
            "content": "Préambule. " * 300 + "Le code Orion est ZEPHYR742.",
        },
    )
    assert response.status_code == 201
    conversation = alice.post("/api/v1/conversations", json={"title": "Document"}).json()
    result = alice.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "content": "Quel est le code Orion ?",
            "model": "synthetic-local-model",
        },
    )
    assert "event: done" in result.text
    assert "ZEPHYR742" in provider.prompts[-1][0]["content"]


def test_chat_retrieves_current_authorized_memories(chat_household):
    _, alice, bob, provider = chat_household

    def memory(client, title, content, visibility="private"):
        response = client.post(
            "/api/v1/memories",
            json={
                "title": title,
                "content": content,
                "visibility": visibility,
                "confirmed": True,
            },
        )
        assert response.status_code == 201
        return response.json()

    own = memory(alice, "Voyage Orion", "Orion était notre bateau à Tadoussac.")
    memory(bob, "Orion privé", "SECRET-BATEAU")
    shared = memory(bob, "Orion partagé", "PARTAGE-BATEAU", "family")
    gone = memory(alice, "Orion effacé", "EFFACE-BATEAU")
    alice.post(
        f"/api/v1/memories/{gone['id']}/delete",
        json={
            "expected_revision": 1,
            "confirmed": True,
        },
    )
    cid = alice.post("/api/v1/conversations", json={"title": "Archives"}).json()["id"]

    def ask():
        result = alice.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Que sais-tu du voyage Orion ?",
                "model": "synthetic-local-model",
            },
        )
        assert "event: done" in result.text
        return provider.prompts[-1][0]["content"]

    prompt = ask()
    assert "Tadoussac" in prompt and "PARTAGE-BATEAU" in prompt
    assert "SECRET-BATEAU" not in prompt and "EFFACE-BATEAU" not in prompt
    assert own["id"] in prompt and '"revision": 1' in prompt
    bob.put(
        f"/api/v1/memories/{shared['id']}",
        json={
            "title": "Orion partagé",
            "content": "PARTAGE-BATEAU",
            "visibility": "private",
            "expected_revision": 1,
            "confirmed": True,
        },
    )
    assert "PARTAGE-BATEAU" not in ask()


@pytest.mark.skipif(os.environ.get("CLAIRE_LIVE_OLLAMA") != "1", reason="Opt-in local inference")
def test_real_ollama_answers_from_new_memory(chat_household):
    _, alice, _, provider = chat_household
    ollama = Ollama(Settings())

    async def real_stream(model, messages):
        async for delta in ollama.stream("qwen3:8b", messages):
            yield delta

    provider.stream = real_stream
    created = alice.post(
        "/api/v1/memories",
        json={
            "title": "Code du bateau Orion",
            "content": "Le code fictif du bateau Orion est LUMI742.",
            "confirmed": True,
        },
    )
    assert created.status_code == 201
    cid = alice.post("/api/v1/conversations", json={"title": "Orion"}).json()["id"]
    response = alice.post(
        f"/api/v1/conversations/{cid}/messages",
        json={
            "content": "Quel est le code du bateau Orion ? Cite le titre du souvenir.",
            "model": "synthetic-local-model",
        },
    )
    assert "event: done" in response.text
    answer = alice.get(f"/api/v1/conversations/{cid}").json()["messages"][-1]["content"]
    assert "LUMI742" in answer
    assert "Code du bateau Orion" in answer


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


def test_immich_chat_grounding_and_admin_isolation(chat_household, monkeypatch):
    from claire import immich

    _, alice, bob, provider = chat_household
    calls = []

    class Client:
        def __init__(self, endpoint, token):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, tool, arguments):
            calls.append((tool, arguments))
            return [{"albumName": "Synthetic garden", "id": "example", "secret_url": "DO_NOT_SEND"}]

    original = immich.read_immich
    monkeypatch.setattr(immich, "read_immich", lambda *args: original(*args, client_factory=Client))
    config = {
        "endpoint": "http://immich.test:5000/mcp",
        "enabled": True,
        "expected_revision": 0,
        "confirmed": True,
    }
    assert bob.put("/api/v1/integrations/immich", json=config).status_code == 200

    def ask(client):
        cid = client.post("/api/v1/conversations", json={"title": "Immich"}).json()["id"]
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "As tu acces a mon Immich?", "model": "synthetic-local-model"},
        )
        assert "event: done" in response.text
        return provider.prompts[-1][0]["content"]

    prompt = ask(bob)
    assert '"status": "available"' in prompt and "Synthetic garden" in prompt
    assert "DO_NOT_SEND" not in prompt and "immich.test" not in prompt
    assert calls == [("immich_albums_list", {})]
    prompt = ask(alice)
    assert '"status": "not_authorized"' in prompt and "Synthetic garden" not in prompt
    assert len(calls) == 1
    config.update(enabled=False, expected_revision=1)
    assert bob.put("/api/v1/integrations/immich", json=config).status_code == 200
    assert '"status": "disabled_missing_or_changed"' in ask(bob)
    assert len(calls) == 1
    config.update(enabled=True, expected_revision=2)
    assert bob.put("/api/v1/integrations/immich", json=config).status_code == 200

    def fail(*args):
        raise immich.MCPError("Synthetic failure")

    monkeypatch.setattr(Client, "call", fail)
    prompt = ask(bob)
    assert '"status": "unavailable"' in prompt and "Synthetic garden" not in prompt


def test_immich_chat_discards_results_when_disconnected(chat_household, monkeypatch):
    from claire import immich

    _, _, bob, provider = chat_household
    assert (
        bob.put(
            "/api/v1/integrations/immich",
            json={
                "endpoint": "http://immich.test:5000/mcp",
                "enabled": True,
                "expected_revision": 0,
                "confirmed": True,
            },
        ).status_code
        == 200
    )

    class Client:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, *args):
            assert bob.delete("/api/v1/integrations/immich").status_code == 204
            return [{"albumName": "Revoked synthetic album"}]

    original = immich.read_immich
    monkeypatch.setattr(immich, "read_immich", lambda *args: original(*args, client_factory=Client))
    cid = bob.post("/api/v1/conversations", json={"title": "Revocation"}).json()["id"]
    response = bob.post(
        f"/api/v1/conversations/{cid}/messages",
        json={
            "content": "Mes albums Immich",
            "model": "synthetic-local-model",
        },
    )
    assert "event: done" in response.text
    prompt = provider.prompts[-1][0]["content"]
    assert "Revoked synthetic album" not in prompt
    assert '"status": "disabled_missing_or_changed"' in prompt


@pytest.mark.parametrize(
    "question,people,status",
    [
        ("Photos de Camille", [{"id": "p1", "name": "Camille", "isHidden": False}], "available"),
        ("Photos de CAMILLE", [{"id": "p1", "name": "Camille Test", "isHidden": False}], "available"),
        (
            "Photos de Camille",
            [
                {"id": "p1", "name": "Camille Test", "isHidden": False},
                {"id": "p2", "name": "Camille Autre", "isHidden": False},
            ],
            "ambiguous_person",
        ),
        ("Photos de Camille", [{"id": "p1", "name": "Camille", "isHidden": True}], "person_not_found"),
        ("Photos de Camille", [], "person_not_found"),
    ],
)
def test_chat_immich_person_filter(chat_household, monkeypatch, question, people, status):
    from claire import immich

    _, alice, bob, provider = chat_household
    calls = []

    class Client:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, name, arguments):
            calls.append((name, arguments))
            if name == "immich_people_list":
                assert arguments == {"withHidden": False, "page": 1, "size": 100}
                return {"people": people}
            assert name == "immich_people_assets"
            assert arguments == {"personId": "p1", "page": 1, "size": 25}
            return [{"originalFileName": "person-match.jpg", "type": "IMAGE"}]

    original = immich.read_immich
    monkeypatch.setattr(immich, "read_immich", lambda *args: original(*args, client_factory=Client))
    assert (
        bob.put(
            "/api/v1/integrations/immich",
            json={
                "endpoint": "http://immich.test:5000/mcp",
                "enabled": True,
                "expected_revision": 0,
                "confirmed": True,
            },
        ).status_code
        == 200
    )
    for client in (bob, alice):
        cid = client.post("/api/v1/conversations", json={"title": "Person lookup"}).json()["id"]
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": question, "model": "synthetic-local-model"},
        )
        assert "event: done" in response.text
        prompt = provider.prompts[-1][0]["content"]
        expected = status if client is bob else "not_authorized"
        assert f'"status": "{expected}"' in prompt
        assert ("person-match.jpg" in prompt) == (client is bob and status == "available")
    assert len(calls) == (2 if status == "available" else 1)
