import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from backend.app.core.config import Settings


class ProviderError(Exception):
    pass


class ChatProvider(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
    async def discover(self) -> str: ...
    async def close(self) -> None: ...


class OllamaProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.ollama_url,
            transport=transport,
            timeout=httpx.Timeout(settings.request_timeout, connect=5),
            trust_env=False,
            follow_redirects=False,
        )
        self.selected: str | None = None

    async def discover(self) -> str:
        response = await self.client.get("/api/tags")
        response.raise_for_status()
        names = [item["name"] for item in response.json().get("models", [])]
        if self.settings.model:
            candidates = [name for name in names if name == self.settings.model]
        else:
            candidates = [
                name
                for name in names
                if "deephat" in name.lower().replace("-", "").replace("_", "")
            ]
        if len(candidates) != 1:
            raise ProviderError(
                "Configure CODEPET_MODEL with an exact installed name from ollama list; automatic discovery requires exactly one DeepHat."
            )
        self.selected = candidates[0]
        return self.selected

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for token in self._stream(messages, {}):
            yield token

    async def stream_assistant(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for token in self._stream(messages, {
            "temperature": 0.2, "top_p": 0.85, "repeat_penalty": 1.1,
            "num_predict": min(self.settings.num_predict, 192),
        }):
            yield token

    async def stream_tutor(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for token in self._stream(messages, {
            "temperature": 0.2, "top_p": 0.85, "repeat_penalty": 1.1,
            "num_predict": min(self.settings.num_predict, 320),
        }):
            yield token

    async def _stream(self, messages: list[dict[str, str]], options: dict) -> AsyncIterator[str]:
        model = self.selected or await self.discover()
        async with self.client.stream(
            "POST",
            "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "keep_alive": f"{self.settings.ollama_keep_alive_minutes}m",
                "options": {
                    "num_ctx": self.settings.num_ctx,
                    "num_predict": self.settings.num_predict,
                    **options,
                },
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if len(line) > 131072:
                    raise ProviderError("Ollama returned an oversized chunk")
                data = json.loads(line)
                if data.get("error"):
                    raise ProviderError("Ollama rejected generation; inspect the local server")
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
                if data.get("done"):
                    return
            raise ProviderError("Ollama stream ended without completion")

    async def close(self) -> None:
        await self.client.aclose()
