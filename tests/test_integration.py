"""Tests de integración con OpenAI real (se saltean si no hay OPENAI_API_KEY).

    pytest -q -m integration
"""

import os

import pytest

import config
from rag_chain import get_rag_response

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requiere OPENAI_API_KEY"),
]


async def test_pregunta_en_contexto():
    resp = await get_rag_response(
        "¿Cuántas veces reintenta Andes Pay el envío de un webhook y durante cuánto tiempo?"
    )
    assert resp.found_in_context
    assert "8" in resp.answer
    assert any(r.source == "02_api_autenticacion_y_limites.md" for r in resp.references)


async def test_pregunta_trampa():
    resp = await get_rag_response("¿Quién ganó el Mundial de fútbol 2022?")
    assert not resp.found_in_context
    assert resp.answer == config.UNKNOWN_ANSWER
    assert resp.references == []
