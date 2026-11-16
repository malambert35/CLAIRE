import json
import socket

import httpx
import pytest
from claire import immich_mcp
from claire.db import ImmichConnection, User
from claire.immich_mcp import READ_TOOLS, ImmichMCP, MCPError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_memories import household  # noqa: F401

TOOLS = {
    "immich_ping": {},
    "immich_assets_list": {"size": {}},
    "immich_albums_list": {},
    "immich_search_metadata": {"originalFileName": {}, "size": {}},
    "immich_tools_list": {"include_tools": {}},
    "immich_tools_enable": {"tools": {}},
    "immich_assets_delete": {"ids": {}},
}


class FakeMCP:
    def __init__(self, gateway=False, sse=False):
        self.gateway, self.sse = gateway, sse
        self.enabled = False
        self.calls = []

    def __call__(self, request):
        assert request.url.host == "192.168.1.20"
        assert request.headers["host"] == "immich.test:5000"
        if request.method == "DELETE":
            return httpx.Response(204)
        body = json.loads(request.content)
        self.calls.append(body)
        method = body["method"]
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "ImmichMCP"}}
        elif method == "notifications/initialized":
            return httpx.Response(202)
        else:
            assert request.headers["mcp-session-id"] == "synthetic-session"
            if method == "tools/list":
                names = (
                    ["immich_tools_list", "immich_tools_enable"]
                    if self.gateway and not self.enabled
                    else TOOLS
                )
                result = {
                    "tools": [
                        {"name": name, "inputSchema": {"type": "object", "properties": TOOLS[name]}}
                        for name in names
                    ]
                }
            else:
                name = body["params"]["name"]
                if name == "immich_tools_list":
                    value = {"categories": [{"tools": [{"name": name} for name in TOOLS]}]}
                elif name == "immich_tools_enable":
                    assert set(body["params"]["arguments"]["tools"]) <= READ_TOOLS
                    self.enabled = True
                    value = {"enabled": True}
                elif name == "immich_ping":
                    value = {"ok": True, "result": {"connected": True}}
                else:
                    assert name in READ_TOOLS
                    value = {
                        "ok": True,
                        "result": [
                            {
                                "id": "synthetic-asset",
                                "originalFileName": "garden.jpg",
                                "type": "IMAGE",
                                "secretUrl": "do-not-return",
                            }
                        ],
                    }
                result = {"content": [{"type": "text", "text": json.dumps(value)}]}
        payload = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        headers = {"Mcp-Session-Id": "synthetic-session"}
        if self.sse:
            return httpx.Response(
                200,
                text="event: message\ndata: " + json.dumps(payload) + "\n\n",
                headers={**headers, "Content-Type": "text/event-stream"},
            )
        return httpx.Response(200, json=payload, headers=headers)


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.20", 5000))],
    )


@pytest.mark.parametrize("gateway,sse", [(False, False), (True, True)])
def test_protocol_discovery_gateway_allowlist_and_sse(network, gateway, sse):
    server = FakeMCP(gateway, sse)
    with ImmichMCP("http://immich.test:5000/mcp", transport=httpx.MockTransport(server)) as client:
        assert client.call("immich_ping", {})["connected"]
        with pytest.raises(MCPError):
            client.call("immich_assets_delete", {"ids": ["anything"]})
        with pytest.raises(MCPError):
            client.call("immich_tools_enable", {"tools": ["immich_assets_delete"]})
        with pytest.raises(MCPError):
            client.call("immich_assets_list", {"unexpected": True})
    assert not any(c.get("params", {}).get("name") == "immich_assets_delete" for c in server.calls)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "169.254.169.254", "::1", "0.0.0.0", "224.0.0.1", "8.8.8.8"]
)
def test_endpoint_blocks_unsafe_http_targets(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 5000))],
    )
    with pytest.raises(MCPError):
        immich_mcp.pinned_endpoint("http://immich.test:5000/mcp")


def test_admin_configuration_secret_isolation_and_disable(household, network, monkeypatch):  # noqa: F811
    clients, settings = household
    bob, alice, outsider = (clients[name] for name in ("bob", "alice", "outsider"))
    path = "/api/v1/integrations/immich"
    body = {
        "endpoint": "http://immich.test:5000/mcp",
        "enabled": True,
        "token": "synthetic-token",
        "expected_revision": 0,
        "confirmed": True,
    }
    assert alice.put(path, json=body).status_code == 403
    assert alice.get(path).status_code == 403
    invalid = bob.put(path, json={**body, "token": "secret-with-newline\n"})
    assert invalid.status_code == 422 and "secret-with-newline" not in invalid.text
    assert bob.put(path, json={**body, "confirmed": False}).status_code == 422
    response = bob.put(path, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["has_token"] and "synthetic-token" not in response.text
    assert outsider.get(path).json()["revision"] == 0
    engine = create_engine(settings.db_url())
    with Session(engine) as db:
        row = db.scalar(select(ImmichConnection))
        assert row.token_cipher and "synthetic-token" not in row.token_cipher
        member = db.scalar(select(User).where(User.email == "alice@example.test"))
        member.role = "family_admin"
        db.commit()
    assert alice.get(path).json()["revision"] == 0  # even another admin cannot read the owner's connection
    with Session(engine) as db:
        member = db.scalar(select(User).where(User.email == "alice@example.test"))
        member.role = "member"
        db.commit()
    original_client = httpx.Client
    server = FakeMCP(gateway=True, sse=True)
    monkeypatch.setattr(
        immich_mcp.httpx,
        "Client",
        lambda **kwargs: original_client(**{**kwargs, "transport": httpx.MockTransport(server)}),
    )
    tested = bob.post(path + "/read", json={"action": "test"})
    assert tested.status_code == 200, tested.text
    assert tested.json()["connected"]
    recent = bob.post(path + "/read", json={"action": "recent"})
    assert recent.json()["items"][0]["title"] == "garden.jpg"
    assert "do-not-return" not in recent.text
    assert alice.post(path + "/read", json={"action": "recent"}).status_code == 403
    assert outsider.post(path + "/read", json={"action": "recent"}).status_code == 409
    assert bob.post(path + "/read", json={"action": "immich_assets_delete"}).status_code == 422
    assert bob.put(path, json={**body, "expected_revision": 0}).status_code == 409
    assert (
        bob.put(
            path,
            json={**body, "endpoint": "http://other.test:5000/mcp", "token": None, "expected_revision": 1},
        ).status_code
        == 422
    )
    assert (
        bob.put(path, json={**body, "enabled": False, "token": "", "expected_revision": 1}).status_code == 200
    )
    assert not bob.get(path).json()["has_token"]
    assert bob.post(path + "/read", json={"action": "recent"}).status_code == 409
    assert bob.delete(path).status_code == 204
    assert bob.get(path).json()["revision"] == 0
    engine.dispose()
