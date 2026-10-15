"""Provider that combines the local DeepHat answer with an optional second opinion."""

import time
from collections.abc import AsyncIterator

from backend.app.llm.ollama import ChatProvider, ProviderError


class HybridProvider:
    """Stream DeepHat first, then ask the authenticated Chat/Codex provider.

    The local response remains useful on its own.  The online provider is only
    contacted when the user explicitly selects ``CODEPET_PROVIDER=hybrid`` and
    is treated as a second opinion, never as a prerequisite for local use.
    """

    def __init__(self, local: ChatProvider, online: ChatProvider):
        self.local = local
        self.online = online
        self._online_checked = False
        self._online_name: str | None = None
        self._online_checked_at = 0.0
        self._online_retry_seconds = 30.0

    async def _check_online(self) -> str | None:
        now = time.monotonic()
        if self._online_checked and (
            self._online_name is not None
            or now - self._online_checked_at < self._online_retry_seconds
        ):
            return self._online_name
        self._online_checked = True
        self._online_checked_at = now
        try:
            self._online_name = await self.online.discover()
        except Exception:
            # A missing login, network failure, or unavailable CLI must not
            # disable the local model.
            self._online_name = None
        return self._online_name

    async def discover(self) -> str:
        local_name: str | None = None
        try:
            local_name = await self.local.discover()
        except Exception:
            pass
        online_name = await self._check_online()
        if local_name and online_name:
            return f"Híbrido: {local_name} + {online_name}"
        if local_name:
            return f"Híbrido: {local_name} (segunda opinião indisponível)"
        if online_name:
            return f"Híbrido: DeepHat indisponível + {online_name}"
        raise ProviderError("DeepHat e provider online estão indisponíveis")

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        local_started = False
        local_error: Exception | None = None
        yield "[DeepHat local]\n"
        try:
            async for part in self.local.stream(messages):
                local_started = True
                yield part
        except Exception as exc:
            local_error = exc

        online_name = await self._check_online()
        if online_name:
            if local_error and not local_started:
                yield "DeepHat não respondeu; usando a segunda opinião do Chat/Codex.\n\n"
            else:
                yield f"\n\n[Segunda opinião: {online_name}]\n"
            try:
                async for part in self.online.stream(messages):
                    yield part
                return
            except Exception as exc:
                if not local_started:
                    raise ProviderError("Nenhum provider conseguiu responder") from exc
                yield "\n\n[Provider online indisponível; mantendo a resposta local.]"
                return

        if local_started:
            yield "\n\n[DeepHat local; segunda opinião indisponível.]"
            return
        raise ProviderError("DeepHat e provider online estão indisponíveis") from local_error

    async def close(self) -> None:
        await self.local.close()
        await self.online.close()

    async def stream_assistant(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """One spoken answer: online first, local fallback before any content."""
        if await self._check_online():
            started = False
            try:
                async for part in self.online.stream(messages):
                    if part:
                        started = True
                        yield part
                if started:
                    return
            except Exception as exc:
                if started:
                    raise ProviderError("A resposta online foi interrompida. Tente novamente.") from exc
        stream = getattr(self.local, "stream_assistant", self.local.stream)
        async for part in stream(messages):
            yield part
