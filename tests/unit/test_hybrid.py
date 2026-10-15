import pytest

from backend.app.llm.hybrid import HybridProvider
from backend.app.llm.ollama import ProviderError


class StubProvider:
    def __init__(self, name: str, parts: tuple[str, ...] = (), error: Exception | None = None):
        self.name = name
        self.parts = parts
        self.error = error
        self.closed = False

    async def discover(self) -> str:
        if self.error:
            raise self.error
        return self.name

    async def stream(self, messages):
        if self.error:
            raise self.error
        for part in self.parts:
            yield part

    async def close(self) -> None:
        self.closed = True


async def test_hybrid_streams_local_then_second_opinion():
    provider = HybridProvider(
        StubProvider("DeepHat-V1", ("resposta local",)),
        StubProvider("Codex CLI", ("resposta online",)),
    )

    output = "".join([part async for part in provider.stream([{"role": "user", "content": "oi"}])])

    assert "[DeepHat local]" in output
    assert "resposta local" in output
    assert "[Segunda opinião: Codex CLI]" in output
    assert "resposta online" in output


async def test_hybrid_keeps_local_when_codex_is_unavailable():
    local = StubProvider("DeepHat-V1", ("resposta local",))
    provider = HybridProvider(local, StubProvider("Codex CLI", error=ProviderError("offline")))

    output = "".join([part async for part in provider.stream([])])

    assert "resposta local" in output
    assert "segunda opinião indisponível" in output


async def test_hybrid_uses_codex_when_local_fails():
    provider = HybridProvider(
        StubProvider("DeepHat-V1", error=ProviderError("Ollama offline")),
        StubProvider("Codex CLI", ("resposta online",)),
    )

    output = "".join([part async for part in provider.stream([])])

    assert "DeepHat não respondeu" in output
    assert "resposta online" in output


@pytest.mark.asyncio
async def test_hybrid_closes_both_providers():
    local = StubProvider("DeepHat")
    online = StubProvider("Codex")
    provider = HybridProvider(local, online)

    await provider.close()

    assert local.closed and online.closed


async def test_assistant_has_one_online_answer_without_provider_labels():
    provider = HybridProvider(StubProvider("local", ("local",)), StubProvider("online", ("Próximo passo.",)))
    assert "".join([part async for part in provider.stream_assistant([])]) == "Próximo passo."


async def test_assistant_falls_back_to_local_when_online_is_unavailable():
    provider = HybridProvider(StubProvider("local", ("Resposta local.",)), StubProvider("online", error=ProviderError("offline")))
    assert "".join([part async for part in provider.stream_assistant([])]) == "Resposta local."


async def test_assistant_does_not_mix_answers_after_partial_online_failure():
    class BrokenStream(StubProvider):
        async def stream(self, messages):
            yield "Resposta parcial"
            raise ProviderError("offline")

    provider = HybridProvider(StubProvider("local", ("local",)), BrokenStream("online"))
    parts = []
    with pytest.raises(ProviderError, match="interrompida"):
        async for part in provider.stream_assistant([]):
            parts.append(part)
    assert parts == ["Resposta parcial"]
