import asyncio
from uuid import uuid4

import pytest

from backend.app.agents.tutor import Tutor
from backend.app.memory.store import MemoryStore
from backend.app.schemas.messages import ChatRequest


async def test_context_budget_and_notes_after_many_messages(settings, provider):
    memory = MemoryStore(settings.database, True)
    memory.add("demo", "preference", "Use exemplos simples")
    for index in range(110):
        memory.add("demo", "user", str(index), "old-session")
    assert memory.notes("demo")[0]["content"] == "Use exemplos simples"
    tutor = Tutor(provider, memory, settings)
    request = ChatRequest(request_id=uuid4(), session=uuid4(), project="demo", prompt="Explique")

    # wait_for also gives restricted runners a timer for thread completion wakeups.
    async def collect():
        return [part async for part in tutor.stream(request, {"selection": "a" * 20000})]

    assert await asyncio.wait_for(collect(), 3)
    assert sum(len(item["content"]) for item in provider.messages) <= settings.context_chars
    memory.close()


async def test_oversized_prompt_budget_rejects_before_inference(settings, provider):
    settings.context_chars = 2000
    memory = MemoryStore(settings.database, True)
    tutor = Tutor(provider, memory, settings)
    request = ChatRequest(request_id=uuid4(), session=uuid4(), project="demo", prompt="a" * 3000)

    async def collect():
        return [part async for part in tutor.stream(request, None)]

    with pytest.raises(ValueError):
        await asyncio.wait_for(collect(), 3)
    assert not provider.messages
    memory.close()


async def test_assistant_mode_reaches_provider_with_short_conversation_instructions(settings, provider):
    memory = MemoryStore(settings.database, True)
    tutor = Tutor(provider, memory, settings)
    request = ChatRequest(request_id=uuid4(), session=uuid4(), project="demo", prompt="Ajude com minha tarefa", mode="assistant")
    assert tutor.selected_skill_ids(request) == []
    assert [part async for part in tutor.stream(request, None)]
    assert "uma a três frases" in provider.messages[0]["content"]
    memory.close()


async def test_selected_provider_is_exclusive_per_request(settings, provider):
    class Online:
        calls = 0

        async def stream(self, messages):
            self.calls += 1
            yield "Online"

    online = Online()
    memory = MemoryStore(settings.database, True)
    tutor = Tutor(provider, memory, settings, providers={"ollama": provider, "codex": online})
    request = ChatRequest(request_id=uuid4(), session=uuid4(), project="demo", prompt="Oi", provider="codex", mode="assistant")
    assert [part async for part in tutor.stream(request, None)] == ["Online"]
    assert not provider.messages
    request = request.model_copy(update={"provider": "ollama", "request_id": uuid4()})
    assert [part async for part in tutor.stream(request, None)] == ["Olá", ", mundo!"]
    assert online.calls == 1
    assert provider.messages
    memory.close()
