import os

import pytest

from backend.app.core.config import Settings
from backend.app.llm.ollama import OllamaProvider


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("CODEPET_LIVE") != "1", reason="Opt-in real Ollama validation: CODEPET_LIVE=1"
)
async def test_local_model_streams_without_external_provider():
    provider = OllamaProvider(Settings())
    try:
        name = await provider.discover()
        assert name
        chunks = [
            part
            async for part in provider.stream(
                [{"role": "user", "content": "Responda apenas: Olá."}]
            )
        ]
        assert "".join(chunks).strip()
    finally:
        await provider.close()
