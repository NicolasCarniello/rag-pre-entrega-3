"""Tests offline (no necesitan API key ni red).

Usan embeddings falsos deterministas y un LLM "guionado" para verificar la
mecánica del sistema: chunking, persistencia, async, Pydantic y anti-alucinación.

    pytest -q
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

import config
from ingest import count_tokens, ingest, load_documents, split_documents
from rag_chain import RAGPipeline, check_embedding_consistency
from schemas import LLMAnswer, RAGResponse

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def embeddings():
    return DeterministicFakeEmbedding(size=128)


@pytest.fixture
def data_dir(tmp_path):
    dst = tmp_path / "data"
    shutil.copytree(config.DATA_DIR, dst)
    return dst


@pytest.fixture
def persist_dir(tmp_path):
    return tmp_path / "vectorstore"


def scripted_llm(mode: str, calls: list | None = None):
    """LLM falso: lee los chunk_id del prompt y responde JSON según `mode`."""

    async def _respond(prompt_value):
        text = prompt_value.to_string()
        if calls is not None:
            calls.append(text)
        ids = re.findall(r"\[chunk_id: ([^ |]+)", text)
        if mode == "found":
            payload = {"answer": "Se reintenta 8 veces durante 3 días.",
                       "found_in_context": True, "cited_chunk_ids": ids[:1]}
        elif mode == "found_with_invented":
            payload = {"answer": "Respuesta.", "found_in_context": True,
                       "cited_chunk_ids": [ids[0], "inventado::chunk-99"]}
        elif mode == "only_invented":
            payload = {"answer": "Dato inventado.", "found_in_context": True,
                       "cited_chunk_ids": ["inventado::chunk-99"]}
        elif mode == "unknown":
            payload = {"answer": config.UNKNOWN_ANSWER, "found_in_context": False,
                       "cited_chunk_ids": []}
        else:
            raise ValueError(mode)
        await asyncio.sleep(0.2)  # simula latencia de red
        return AIMessage(content=json.dumps(payload, ensure_ascii=False))

    return RunnableLambda(_respond)


def make_pipeline(embeddings, data_dir, persist_dir, mode, calls=None):
    result = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                    embedding_model_name="fake-128")
    return RAGPipeline(result.vectorstore, scripted_llm(mode, calls))


# ---------------------------------------------------------------------------
# 1. Chunking e ingesta
# ---------------------------------------------------------------------------
def test_chunking_respeta_tamano_y_metadatos():
    docs = load_documents()
    chunks = split_documents(docs)
    assert len(docs) >= 3
    assert len(chunks) > len(docs), "cada documento debería generar varios chunks"
    assert {c.metadata["source"] for c in chunks} == {d.metadata["source"] for d in docs}
    for c in chunks:
        assert c.metadata["n_tokens"] <= config.CHUNK_SIZE
        assert c.page_content.startswith("Documento: ")  # header de contexto
        assert re.fullmatch(r".+::chunk-\d{2}", c.metadata["chunk_id"])
    assert len({c.id for c in chunks}) == len(chunks), "IDs duplicados"


def test_chunks_consecutivos_se_solapan():
    docs = {d.metadata["source"]: d.page_content for d in load_documents()}
    chunks = split_documents(load_documents())
    pairs = [(a, b) for a, b in zip(chunks, chunks[1:]) if a.metadata["source"] == b.metadata["source"]]
    assert pairs
    for a, b in pairs:
        a_body = a.page_content.split("\n\n", 1)[1]
        b_body = b.page_content.split("\n\n", 1)[1]
        a_end = a.metadata["start_index"] + len(a_body)
        # el chunk siguiente arranca dentro del anterior (comparten texto)...
        assert a.metadata["start_index"] < b.metadata["start_index"] < a_end
        shared = docs[a.metadata["source"]][b.metadata["start_index"]:a_end]
        assert a_body.endswith(shared.strip()) and b_body.startswith(shared.strip())
        # ...y el overlap es de hasta CHUNK_OVERLAP tokens, nunca cero
        assert 0 < b.metadata["overlap_tokens"] <= config.CHUNK_OVERLAP


def test_ingesta_no_reindexa_si_la_base_existe(embeddings, data_dir, persist_dir):
    first = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                   embedding_model_name="fake-128")
    second = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                    embedding_model_name="fake-128")
    assert first.reindexed and not second.reindexed
    assert second.vectorstore._collection.count() == first.n_chunks


def test_ingesta_reindexa_si_cambian_los_datos(embeddings, data_dir, persist_dir):
    first = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                   embedding_model_name="fake-128")
    (data_dir / "05_nuevo.txt").write_text("Documento nuevo sobre horarios de soporte.", encoding="utf-8")
    second = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                    embedding_model_name="fake-128")
    assert second.reindexed
    assert second.vectorstore._collection.count() == first.n_chunks + 1  # sin duplicados


def test_ingesta_forzada(embeddings, data_dir, persist_dir):
    ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings, embedding_model_name="fake-128")
    forced = ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings,
                    embedding_model_name="fake-128", force=True)
    assert forced.reindexed
    assert forced.vectorstore._collection.count() == forced.n_chunks


def test_detecta_embeddings_no_coincidentes(embeddings, data_dir, persist_dir):
    ingest(data_dir=data_dir, persist_dir=persist_dir, embeddings=embeddings, embedding_model_name="fake-128")
    with pytest.raises(RuntimeError, match="Reindexá"):
        check_embedding_consistency("otro-modelo", persist_dir)


# ---------------------------------------------------------------------------
# 2. Arquitectura asíncrona y recuperación
# ---------------------------------------------------------------------------
async def test_recupera_top_k_fragmentos(embeddings, data_dir, persist_dir):
    calls: list[str] = []
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "found", calls)
    await pipe.aget_response("¿Cuántas veces se reintenta un webhook?")
    assert len(re.findall(r"\[chunk_id: ", calls[0])) == config.TOP_K


async def test_consultas_concurrentes(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "found")
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    responses = await asyncio.gather(*(pipe.aget_response(f"pregunta {i}") for i in range(5)))
    elapsed = loop.time() - t0
    assert len(responses) == 5
    # 5 llamadas de 0.2 s en serie tardarían ≥1 s; en paralelo, mucho menos.
    assert elapsed < 0.8, f"no se ejecutaron en paralelo ({elapsed:.2f}s)"


async def test_consulta_vacia(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "found")
    with pytest.raises(ValueError):
        await pipe.aget_response("   ")


# ---------------------------------------------------------------------------
# 3. Pydantic y fuentes
# ---------------------------------------------------------------------------
async def test_respuesta_con_referencias(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "found")
    resp = await pipe.aget_response("¿Cuántas veces se reintenta un webhook?")
    assert isinstance(resp, RAGResponse)
    assert resp.found_in_context and len(resp.references) == 1
    ref = resp.references[0]
    assert ref.source.endswith(".md") and ref.chunk_id and -1 <= ref.score <= 1


async def test_descarta_citas_inventadas(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "found_with_invented")
    resp = await pipe.aget_response("pregunta")
    assert [r.chunk_id for r in resp.references] != []
    assert all(not r.chunk_id.startswith("inventado") for r in resp.references)


def test_parser_rechaza_json_invalido():
    with pytest.raises(ValidationError):
        LLMAnswer.model_validate({"answer": "", "found_in_context": True})


def test_no_lo_se_limpia_referencias():
    a = LLMAnswer(answer="algo", found_in_context=False, cited_chunk_ids=["x::chunk-00"])
    assert a.answer == config.UNKNOWN_ANSWER and a.cited_chunk_ids == []


# ---------------------------------------------------------------------------
# 4. Robustez: preguntas fuera de contexto y credenciales
# ---------------------------------------------------------------------------
async def test_pregunta_trampa_responde_no_lo_se(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "unknown")
    resp = await pipe.aget_response("¿Quién ganó el Mundial 2022?")
    assert not resp.found_in_context
    assert resp.answer.startswith("No lo sé") and resp.references == []


async def test_respuesta_sin_evidencia_se_convierte_en_no_lo_se(embeddings, data_dir, persist_dir):
    pipe = make_pipeline(embeddings, data_dir, persist_dir, "only_invented")
    resp = await pipe.aget_response("¿Qué tasa cobra Andes Pay por adelantos?")
    assert not resp.found_in_context and resp.answer == config.UNKNOWN_ANSWER


def test_env_esta_en_gitignore():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored and "vectorstore/" in ignored


def test_no_hay_api_keys_en_el_codigo():
    pattern = re.compile(r"sk-(proj-)?[A-Za-z0-9_\-]{20,}")
    try:  # si es un repo git, revisar solo lo versionado
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.split()
        paths = [ROOT / f for f in files]
    except Exception:
        paths = [p for p in ROOT.rglob("*") if p.is_file()
                 and not {".env", "vectorstore", ".venv", "venv", "__pycache__", ".git"} & set(p.parts)]
    for p in paths:
        if p.suffix in {".py", ".md", ".txt", ".json", ".example", ".ini", ".toml", ".ipynb"}:
            assert not pattern.search(p.read_text(encoding="utf-8", errors="ignore")), f"posible API key en {p}"


def test_count_tokens_funciona():
    assert count_tokens("hola mundo") >= 1
