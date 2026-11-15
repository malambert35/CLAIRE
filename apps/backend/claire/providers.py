"""Local-only Ollama adapter; no remote fallback and no tools or archive context."""

import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import httpx


class ProviderUnavailable(ValueError):
    pass


def local_endpoint(url: str):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderUnavailable("Configure a local Ollama URL without embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ProviderUnavailable("Ollama URL must be a server origin")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
        if not addresses or any(
            not (ipaddress.ip_address(item[4][0]).is_private or ipaddress.ip_address(item[4][0]).is_loopback)
            for item in addresses
        ):
            raise ProviderUnavailable("Remote endpoints are disabled; use a local/private Ollama server")
    except (OSError, ValueError) as error:
        raise ProviderUnavailable("Ollama must resolve to a local/private server") from error
    return url.rstrip("/")


class Ollama:
    def __init__(self, settings):
        self.settings = settings

    def models(self):
        endpoint = local_endpoint(self.settings.llm_base_url)
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = client.get(endpoint + "/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
            return [
                item["name"]
                for item in models
                if isinstance(item.get("name"), str)
                and "cloud" not in item["name"].lower()
                and not item.get("remote_host")
                and not item.get("remote_model")
            ][:100]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailable(
                "Ollama is unavailable. Check CLAIRE_LLM_BASE_URL and the local service."
            ) from error

    def validate_model(self, model):
        if model not in self.models():
            raise ProviderUnavailable("Select an installed local model; cloud models are disabled")
        endpoint = local_endpoint(self.settings.llm_base_url)
        try:
            with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
                response = client.post(endpoint + "/api/show", json={"model": model})
                response.raise_for_status()
                details = response.json()
            if details.get("remote_host") or details.get("remote_model"):
                raise ProviderUnavailable("Cloud-backed Ollama models are disabled")
        except httpx.HTTPError as error:
            raise ProviderUnavailable("Unable to verify this local model") from error

    async def stream(self, model, messages):
        endpoint = await asyncio.to_thread(local_endpoint, self.settings.llm_base_url)
        async with (
            asyncio.timeout(self.settings.llm_timeout_seconds),
            httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=5), trust_env=False, follow_redirects=False
            ) as client,
            client.stream(
                "POST",
                endpoint + "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 2048, "num_ctx": 8192},
                },
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise ProviderUnavailable("Local model generation failed")
                content = event.get("message", {}).get("content", "")
                if content:
                    yield content
                if event.get("done"):
                    return
        raise ProviderUnavailable("Ollama ended without a completed response")
