"""Bounded Streamable HTTP MCP client for barryw/ImmichMCP; no arbitrary tools."""

import ipaddress
import json
import socket
import time
from urllib.parse import urlsplit

import httpx

READ_TOOLS = frozenset(
    {
        "immich_ping",
        "immich_assets_list",
        "immich_albums_list",
        "immich_search_metadata",
        "immich_people_list",
        "immich_people_assets",
    }
)
BOOTSTRAP = frozenset({"immich_tools_list", "immich_tools_enable"})
PROTOCOL = "2025-03-26"


class MCPError(ValueError):
    pass


def endpoint_url(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/mcp"
            or any(not 33 <= ord(c) <= 126 for c in value)
            or "%" in parsed.netloc
            or "\\" in value
        ):
            raise ValueError()
        if not 1 <= (parsed.port or 443 if parsed.scheme == "https" else parsed.port or 80) <= 65535:
            raise ValueError()
        return value.rstrip("/")
    except ValueError:
        raise MCPError(
            "Use an HTTP(S) MCP address ending in /mcp, without credentials or query parameters"
        ) from None


def pinned_endpoint(value):
    value = endpoint_url(value)
    parsed = urlsplit(value)
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
        ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
        if not ips or any(
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
            or (parsed.scheme == "http" and not ip.is_private)
            for ip in ips
        ):
            raise ValueError()
        address = str(ips[0])
    except (OSError, ValueError):
        raise MCPError(
            "MCP must resolve to a reachable server; loopback/link-local addresses and public HTTP are blocked"
        ) from None
    # Pin validated DNS results; preserve virtual-host routing and TLS certificate identity.
    return httpx.URL(value).copy_with(host=address), parsed.netloc, parsed.hostname


class ImmichMCP:
    def __init__(self, endpoint, token="", transport=None):
        self.url, self.host, self.hostname = pinned_endpoint(endpoint)
        self.headers = {
            "Host": self.host,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.client = httpx.Client(timeout=10, trust_env=False, follow_redirects=False, transport=transport)
        self.counter = 0
        self.deadline = time.monotonic() + 45
        self.tools = {}
        self.server = ""

    def __enter__(self):
        try:
            result = self.rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "CLAIRE", "version": "0.1.0"},
                },
            )
            if result.get("protocolVersion") != PROTOCOL:
                raise MCPError("MCP protocol version not supported by this adapter")
            self.server = str(result.get("serverInfo", {}).get("name", "MCP"))[:120]
            self.headers["MCP-Protocol-Version"] = PROTOCOL
            self.rpc("notifications/initialized", notification=True)
            self.discover()
            if "immich_tools_list" in self.tools and "immich_tools_enable" in self.tools:
                inventory = self.call("immich_tools_list", {"include_tools": True})
                candidates = {
                    tool.get("name")
                    for category in inventory.get("categories", [])
                    for tool in category.get("tools", [])
                }
                selected = sorted(candidates & READ_TOOLS)
                if selected:
                    self.call("immich_tools_enable", {"tools": selected})
                    self.discover()
            if not READ_TOOLS.intersection(self.tools):
                raise MCPError("No compatible read-only Immich tools discovered")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if "Mcp-Session-Id" in self.headers:
            try:
                self.client.delete(
                    self.url, headers=self.headers, extensions={"sni_hostname": self.hostname}, timeout=2
                )
            except httpx.HTTPError:
                pass
        self.client.close()

    def rpc(self, method, params=None, notification=False):
        self.counter += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            payload["id"] = self.counter
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise MCPError("MCP connection timed out")
        try:
            with self.client.stream(
                "POST",
                self.url,
                json=payload,
                headers=self.headers,
                extensions={"sni_hostname": self.hostname},
                timeout=min(10, remaining),
            ) as response:
                if response.status_code in {401, 403}:
                    raise MCPError("MCP access denied; check proxy authentication and server permissions")
                if response.is_redirect:
                    raise MCPError("MCP redirects are blocked; configure the final /mcp address")
                response.raise_for_status()
                if method == "initialize" and response.headers.get("mcp-session-id"):
                    session = response.headers["mcp-session-id"]
                    if len(session) > 256 or any(not 33 <= ord(c) <= 126 for c in session):
                        raise MCPError("Invalid MCP session identifier")
                    self.headers["Mcp-Session-Id"] = session
                if notification:
                    return {}
                sse = "text/event-stream" in response.headers.get("content-type", "")
                buffer = bytearray()
                event = []
                used = 0
                for chunk in response.iter_bytes():
                    used += len(chunk)
                    if used > 2 * 1024 * 1024 or time.monotonic() > self.deadline:
                        raise MCPError("MCP response exceeded its size or time limit")
                    buffer.extend(chunk)
                    if sse:
                        while b"\n" in buffer:
                            line, _, rest = buffer.partition(b"\n")
                            buffer = bytearray(rest)
                            line = line.rstrip(b"\r")
                            if line.startswith(b"data:"):
                                event.append(line[5:].lstrip())
                            elif not line and event:
                                message = json.loads(b"\n".join(event))
                                event = []
                                result = self.result(message, payload["id"])
                                if result is not None:
                                    return result
                if not sse:
                    result = self.result(json.loads(buffer), payload["id"])
                    if result is not None:
                        return result
                raise MCPError("MCP ended without a matching response")
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError, TypeError, AttributeError):
            # Never return upstream bodies: they can contain secrets and internal URLs.
            raise MCPError(
                "MCP unavailable or incompatible response; verify its address, transport and server logs"
            ) from None

    @staticmethod
    def result(message, expected):
        if not isinstance(message, dict) or message.get("id") != expected:
            return None
        if "error" in message or not isinstance(message.get("result"), dict):
            raise MCPError("MCP rejected this operation")
        return message["result"]

    def discover(self):
        tools = {}
        cursor = None
        for _ in range(5):
            result = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            for item in result.get("tools", []):
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    tools[item["name"]] = item
            if len(tools) > 500:
                raise MCPError("MCP tool inventory too large")
            cursor = result.get("nextCursor")
            if not cursor:
                self.tools = tools
                return
        raise MCPError("MCP tool inventory pagination limit exceeded")

    def call(self, name, arguments):
        if name not in READ_TOOLS | BOOTSTRAP or name not in self.tools:
            raise MCPError("This read-only Immich operation is not available")
        if name == "immich_tools_enable" and (
            set(arguments) != {"tools"} or not set(arguments["tools"]) <= READ_TOOLS
        ):
            raise MCPError("Write-capable MCP tools cannot be enabled")
        schema = self.tools[name].get("inputSchema", {})
        properties = schema.get("properties", {})
        if any(key not in properties for key in arguments) or any(
            key not in arguments for key in schema.get("required", [])
        ):
            raise MCPError("Immich tool arguments are incompatible with this server version")
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPError(
                "Immich could not complete this read operation; check its permissions and server logs"
            )
        content = result.get("structuredContent")
        if content is None:
            texts = [part.get("text", "") for part in result.get("content", []) if part.get("type") == "text"]
            try:
                content = json.loads("\n".join(texts))
            except (ValueError, TypeError):
                raise MCPError("Expected structured Immich data") from None
        if not isinstance(content, dict) or content.get("ok") is False:
            raise MCPError("Immich returned an error; check its permissions and server logs")
        return content.get("result", content)
