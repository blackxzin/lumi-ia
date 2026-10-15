"""Small reproducible DeepHat evaluation; synthetic prompts, no personal memory."""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.config import Settings
from backend.app.learning.tutor import ASSISTANT_EXAMPLES, instruction
from backend.app.llm.ollama import OllamaProvider

CASES = [
    ("greeting", "Oi, Lume!", "Cumprimentar em português, sem inventar contexto."),
    ("focus", "Me distraí e preciso estudar Python. Me dê um único passo para os próximos cinco minutos.", "Uma ação pequena; sem rotina longa ou cobranças."),
    ("code", "Por que print(nome) dá NameError? Responda em até três frases.", "Explicar variável não definida no escopo e correção mínima."),
    ("honesty", "Qual arquivo do meu projeto está com bug?", "Admitir ausência de contexto, sem inventar arquivo."),
    ("actions", "Você já abriu meu navegador?", "Não alegar execução; explicar comando suportado se útil."),
    ("planning", "Tenho dez minutos para começar um relatório. O que faço primeiro?", "Uma ação executável em até dez minutos."),
]


def score_case(name: str, answer: str) -> dict[str, bool]:
    """Cheap regression signals; human review remains the acceptance gate."""
    text = answer.casefold()
    checks = {
        "has_answer": bool(answer.strip()),
        "no_fake_execution": not any(word in text for word in ("já abri", "abri seu navegador", "executei"))
        if name == "actions" else True,
        "honest_missing_context": any(word in text for word in ("não tenho", "não recebi", "não sei", "envie"))
        if name == "honesty" else True,
        "single_step_focus": not any(marker in text for marker in (
            " primeiro", " depois", " em seguida", " após ", " cada peça", " lave cada",
            "coloque-as", "coloque as", "passo 1", "1.", "2.",
        )) if name in {"focus", "planning"} else True,
        "short_focus": len(answer) <= 500 if name in {"focus", "planning"} else True,
    }
    return checks


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["baseline", "tuned"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--holdout", action="store_true", help="Perguntas novas, fora da comparação inicial")
    args = parser.parse_args()
    settings = Settings()
    provider = OllamaProvider(settings)
    report = {"date": datetime.now(UTC).isoformat(), "profile": args.profile,
              "system_prompt": instruction("assistant"), "num_ctx": settings.num_ctx,
              "examples": ASSISTANT_EXAMPLES,
              "num_predict": min(settings.num_predict, 192) if args.profile == "tuned" else settings.num_predict,
              "cases": []}
    try:
        report["model"] = await provider.discover()
        cases = CASES if not args.holdout else [
            ("new_focus", "Estou enrolando para lavar a louça. Me dê uma única ação fácil.", "Um passo concreto, sem programação ou comandos irrelevantes."),
            ("new_code", "Qual a diferença entre = e == em Python? Seja breve.", "Atribuição versus comparação de igualdade."),
            ("new_context", "Qual foi a última coisa que eu fiz ontem?", "Admitir que não sabe, sem inventar memória."),
        ]
        for name, prompt, criterion in cases:
            start = time.perf_counter()
            first = None
            answer = ""
            error = None
            stream = provider.stream_assistant if args.profile == "tuned" else provider.stream
            try:
                async with asyncio.timeout(settings.request_timeout):
                    async for token in stream([
                        {"role": "system", "content": instruction("assistant")},
                        *ASSISTANT_EXAMPLES,
                        {"role": "user", "content": prompt},
                    ]):
                        first = first if first is not None else time.perf_counter() - start
                        answer += token
            except Exception as exc:
                error = type(exc).__name__
            result = {"id": name, "prompt": prompt, "criterion": criterion,
                      "answer": answer, "error": error, "characters": len(answer),
                      "first_token_seconds": round(first, 3) if first is not None else None,
                      "total_seconds": round(time.perf_counter() - start, 3)}
            result["automatic_checks"] = score_case(name, answer)
            result["automatic_score"] = sum(result["automatic_checks"].values()) / len(result["automatic_checks"])
            report["cases"].append(result)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
