import json

import httpx
import pytest

from backend.app.llm.ollama import OllamaProvider, ProviderError


async def test_discover_exact_name_and_stream(settings):
    seen = []

    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "org/DeepHat-V1:7b-q4"}]})
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, text='{"message":{"content":"Oi"},"done":false}\n{"done":true}\n'
        )

    provider = OllamaProvider(settings, httpx.MockTransport(handle))
    assert [token async for token in provider.stream([{"role": "user", "content": "hi"}])] == ["Oi"]
    assert seen[0]["model"] == "org/DeepHat-V1:7b-q4"
    assert seen[0]["stream"] is True
    await provider.close()


async def test_ambiguous_model_requires_configuration(settings):
    provider = OllamaProvider(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"models": [{"name": "deephat:a"}, {"name": "deephat:b"}]}
            )
        ),
    )
    with pytest.raises(ProviderError):
        await provider.discover()
    await provider.close()


async def test_truncated_stream_is_error(settings):
    settings.model = "deephat:a"

    def handle(request):
        return (
            httpx.Response(200, json={"models": [{"name": "deephat:a"}]})
            if request.method == "GET"
            else httpx.Response(200, text='{"message":{"content":"partial"}}\n')
        )

    provider = OllamaProvider(settings, httpx.MockTransport(handle))
    with pytest.raises(ProviderError):
        _ = [token async for token in provider.stream([])]
    await provider.close()


async def test_assistant_uses_shorter_low_temperature_generation(settings):
    requests = []
    settings.model = "deephat:a"

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "deephat:a"}]})
        requests.append(json.loads(request.content))
        return httpx.Response(200, text='{"message":{"content":"Olá"},"done":true}\n')

    provider = OllamaProvider(settings, httpx.MockTransport(handle))
    assert [part async for part in provider.stream_assistant([])] == ["Olá"]
    assert requests[0]["options"]["num_predict"] == 192
    assert requests[0]["options"]["temperature"] == 0.2
    await provider.close()
