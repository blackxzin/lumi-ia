from uuid import uuid4

import pytest

from backend.app.agents.tutor import Tutor
from backend.app.memory.store import MemoryStore
from backend.app.schemas.messages import ChatRequest
from backend.app.skills.catalog import SkillCatalog


def test_catalog_loads_user_skill_and_ignores_symlink(tmp_path):
    directory = tmp_path / "skills"
    skill_dir = directory / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Minha skill\ndescription: Ajuda com testes.\n---\nUse exemplos curtos.\n"
    )
    (directory / "linked").symlink_to(skill_dir, target_is_directory=True)
    catalog = SkillCatalog(directory)
    assert catalog.get("my-skill").instructions == "Use exemplos curtos."
    assert "linked" not in {item.id for item in catalog.list()}


@pytest.mark.asyncio
async def test_selected_skill_enters_system_prompt_and_respects_budget(settings, provider):
    catalog = SkillCatalog(settings.skills_dir)
    memory = MemoryStore(settings.database, settings.retention)
    tutor = Tutor(provider, memory, settings, catalog)
    request = ChatRequest(
        request_id=uuid4(),
        session=uuid4(),
        project="demo",
        prompt="Explique isto",
        skill="explain-code",
    )
    assert "".join([token async for token in tutor.stream(request, None)]) == "Olá, mundo!"
    assert "SKILL ATIVA" in provider.messages[0]["content"]
    assert "fluxo dos dados" in provider.messages[0]["content"]
    assert sum(len(item["content"]) for item in provider.messages) <= settings.context_chars
    memory.close()


@pytest.mark.asyncio
async def test_graphify_uses_only_existing_authorized_report(settings, provider):
    root = settings.projects["demo"]
    report = root / "graphify-out" / "GRAPH_REPORT.md"
    report.parent.mkdir()
    report.write_text("Module alpha imports beta.\n")
    memory = MemoryStore(settings.database, settings.retention)
    tutor = Tutor(provider, memory, settings)
    request = ChatRequest(
        request_id=uuid4(),
        session=uuid4(),
        project="demo",
        prompt="Qual a arquitetura?",
    )
    assert tutor.selected_skill_ids(request) == ["ponytail", "caveman", "graphify"]
    assert "".join([token async for token in tutor.stream(request, None)])
    assert "Module alpha imports beta" in provider.messages[1]["content"]

    report.unlink()
    request = request.model_copy(update={"request_id": uuid4(), "session": uuid4()})
    assert "".join([token async for token in tutor.stream(request, None)])
    assert len(provider.messages) == 2
    assert "graph_report" not in provider.messages[1]["content"]
    memory.close()


@pytest.mark.asyncio
async def test_greeting_ignores_empty_context_and_old_chat(settings, provider):
    memory = MemoryStore(settings.database, settings.retention)
    session = str(uuid4())
    memory.add_turn("demo", session, "oi", "Falta um relatório gráfico")
    tutor = Tutor(provider, memory, settings)
    request = ChatRequest(request_id=uuid4(), session=session, project="demo", prompt="oi")
    assert "".join([token async for token in tutor.stream(request, None)])
    assert len(provider.messages) == 2
    assert provider.messages[1] == {"role": "user", "content": "oi"}
    assert "cumprimente brevemente" in provider.messages[0]["content"]
    assert "Falta um relatório" not in str(provider.messages)
    memory.close()
