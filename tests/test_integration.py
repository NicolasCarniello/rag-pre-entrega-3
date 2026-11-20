"""Tests de integración con el LLM real (se saltean si falta la API key del proveedor).

    pytest -q -m integration
"""

import pytest

import config
from rag_chain import get_rag_response

def _sin_clave() -> bool:
    try:
        config.require_api_key()
        return False
    except RuntimeError:
        return True


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_sin_clave(), reason="requiere la API key del proveedor (.env)"),
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
