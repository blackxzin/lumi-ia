"""Real backend + Ollama smoke test. Explicitly runs inference; no external API."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from websockets.asyncio.client import connect

from backend.app.core.config import Settings


async def main():
    parser = argparse.ArgumentParser(description="Conversa de teste com o backend real")
    parser.add_argument("--mode", choices=["tutor", "assistant"], default="tutor")
    parser.add_argument("--provider", choices=["default", "ollama", "codex"], default="default")
    parser.add_argument("--prompt", default="Explique em duas frases o que é uma variável em Python.")
    args = parser.parse_args()
    settings = Settings()
    if not settings.projects:
        raise SystemExit("Configure an authorized project first")
    start = time.perf_counter()
    first_token = None
    response = ""
    async with asyncio.timeout(settings.request_timeout + 10):
        async with connect("ws://127.0.0.1:8765/v1/chat", max_size=65536) as ws:
            await ws.send(
                json.dumps({"v": 1, "type": "auth", "token": settings.token.get_secret_value()})
            )
            ready = json.loads(await ws.recv())
            if ready["type"] != "ready":
                raise RuntimeError("Authentication failed")
            await ws.send(
                json.dumps(
                    {
                        "v": 1,
                        "type": "chat",
                        "request_id": str(uuid4()),
                        "session": str(uuid4()),
                        "project": next(iter(settings.projects)),
                        "prompt": args.prompt,
                        "mode": args.mode,
                        "provider": args.provider,
                    }
                )
            )
            async for raw in ws:
                event = json.loads(raw)
                if event["type"] == "token":
                    first_token = first_token or time.perf_counter()
                    response += event["content"]
                    print(event["content"], end="", flush=True)
                elif event["type"] == "done":
                    if not response.strip():
                        raise RuntimeError("Empty model response")
                    print(
                        "\n"
                        + json.dumps(
                            {
                                "first_token_seconds": round(first_token - start, 3),
                                "total_seconds": round(time.perf_counter() - start, 3),
                                "response_characters": len(response),
                            }
                        )
                    )
                    return
                elif event["type"] in {"error", "cancelled"}:
                    raise RuntimeError(event.get("message", "Generation cancelled"))
            raise RuntimeError("Connection closed without completion")


if __name__ == "__main__":
    asyncio.run(main())
