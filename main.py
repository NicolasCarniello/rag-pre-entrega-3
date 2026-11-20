"""Demo end-to-end + pruebas de validación (pregunta en contexto y preguntas trampa).

Uso:
    python main.py                       # corre las pruebas y guarda evidencia/
    python main.py "tu pregunta acá"     # consulta puntual
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from rag_chain import get_rag_response
from schemas import RAGResponse

EVIDENCE_DIR = config.BASE_DIR / "evidencia"

# (pregunta, ¿la respuesta está en los documentos?, palabras que deben aparecer)
TEST_CASES = [
    (
        "¿Cuántas veces reintenta Andes Pay el envío de un webhook y durante cuánto tiempo?",
        True,
        ["8", "3 días"],
    ),
    (
        "¿Cuánto cuesta un contracargo y qué pasa si el comercio no presenta documentación?",
        True,
        ["15"],
    ),
    # Trampa 1: suena a algo que debería estar en los documentos, pero no está.
    (
        "¿Qué tasa de interés cobra Andes Pay por adelantar las liquidaciones a los comercios?",
        False,
        [],
    ),
    # Trampa 2: el modelo lo sabe por conocimiento general, pero NO está en el contexto.
    ("¿Quién ganó el Mundial de fútbol 2022?", False, []),
]


def check(resp: RAGResponse, expected_found: bool, must_contain: list[str]) -> tuple[bool, str]:
    if resp.found_in_context != expected_found:
        return False, f"found_in_context={resp.found_in_context}, se esperaba {expected_found}"
    if expected_found:
        missing = [w for w in must_contain if w.lower() not in resp.answer.lower()]
        if missing:
            return False, f"faltan en la respuesta: {missing}"
        if not resp.references:
            return False, "no tiene referencias"
        return True, f"respondió con {len(resp.references)} referencia(s)"
    if resp.answer != config.UNKNOWN_ANSWER or resp.references:
        return False, "debía responder 'No lo sé' sin referencias (posible alucinación)"
    return True, "respondió 'No lo sé' sin inventar (no alucinó)"


async def run_tests() -> int:
    t0 = time.perf_counter()
    # Las consultas se lanzan en paralelo gracias a la arquitectura asíncrona.
    responses = await asyncio.gather(*(get_rag_response(q) for q, _, _ in TEST_CASES))
    elapsed = time.perf_counter() - t0

    results, all_ok = [], True
    for (question, expected, words), resp in zip(TEST_CASES, responses):
        ok, detail = check(resp, expected, words)
        all_ok &= ok
        kind = "EN CONTEXTO" if expected else "TRAMPA"
        print(f"\n{'✅' if ok else '❌'} [{kind}] {question}")
        print(f"   → {resp.answer}")
        for ref in resp.references:
            print(f"     · {ref.source} [{ref.chunk_id}] score={ref.score}")
        print(f"   ({detail})")
        results.append({"tipo": kind, "ok": ok, "detalle": detail, "respuesta": resp.model_dump()})

    print(f"\n{len(TEST_CASES)} consultas concurrentes en {elapsed:.1f}s — "
          f"{'TODAS OK' if all_ok else 'HAY FALLAS'}")

    EVIDENCE_DIR.mkdir(exist_ok=True)
    out = EVIDENCE_DIR / "resultados_pruebas.json"
    out.write_text(
        json.dumps(
            {
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "llm": f"{config.LLM_PROVIDER}:{config.LLM_MODEL}",
                "embeddings": f"{config.EMBEDDING_PROVIDER}:{config.EMBEDDING_MODEL}",
                "top_k": config.TOP_K,
                "chunk_size": config.CHUNK_SIZE,
                "chunk_overlap": config.CHUNK_OVERLAP,
                "segundos_totales": round(elapsed, 2),
                "todas_ok": all_ok,
                "resultados": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Evidencia guardada en {out.relative_to(config.BASE_DIR)}")
    return 0 if all_ok else 1


async def ask(question: str) -> int:
    resp = await get_rag_response(question)
    print(resp.model_dump_json(indent=2))
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    try:
        config.require_api_key()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(2)
    if len(sys.argv) > 1:
        sys.exit(asyncio.run(ask(" ".join(sys.argv[1:]))))
    sys.exit(asyncio.run(run_tests()))


if __name__ == "__main__":
    main()
