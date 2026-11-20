"""Modelos Pydantic del sistema RAG.

- `LLMAnswer`: contrato que se le exige al LLM. Lo valida el PydanticOutputParser.
- `RAGResponse`: salida final de `get_rag_response`, con texto + referencias
  verificadas contra los fragmentos que realmente se recuperaron.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from config import UNKNOWN_ANSWER


class LLMAnswer(BaseModel):
    """Respuesta estructurada que debe devolver el modelo de lenguaje."""

    answer: str = Field(
        description=(
            "Respuesta en español basada EXCLUSIVAMENTE en el CONTEXTO. "
            f'Si la información no está en el contexto, debe ser exactamente: "{UNKNOWN_ANSWER}"'
        )
    )
    found_in_context: bool = Field(
        description="true si el CONTEXTO contiene la información para responder; false si no."
    )
    cited_chunk_ids: list[str] = Field(
        default_factory=list,
        description=(
            "IDs exactos (campo chunk_id) de los fragmentos del CONTEXTO usados para "
            "responder. Lista vacía si found_in_context es false."
        ),
    )

    @field_validator("answer")
    @classmethod
    def answer_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La respuesta no puede estar vacía.")
        return v

    @model_validator(mode="after")
    def enforce_unknown_consistency(self) -> "LLMAnswer":
        # Si el modelo dice que no encontró la info, normalizamos la respuesta y
        # descartamos cualquier cita: no puede haber fuentes de algo que no está.
        if not self.found_in_context:
            self.answer = UNKNOWN_ANSWER
            self.cited_chunk_ids = []
        # Si el modelo responde "No lo sé" pero marcó found_in_context=true, gana el "No lo sé".
        elif self.answer.lower().startswith("no lo sé"):
            self.found_in_context = False
            self.answer = UNKNOWN_ANSWER
            self.cited_chunk_ids = []
        return self


class Reference(BaseModel):
    """Fragmento de la base vectorial que respalda la respuesta."""

    source: str = Field(description="Archivo de origen dentro de /data")
    chunk_id: str
    section: str = ""
    score: float = Field(ge=-1.0, le=1.0, description="Relevancia (1 - distancia coseno)")
    excerpt: str = Field(description="Primeros caracteres del fragmento, para inspección")


class RAGResponse(BaseModel):
    """Salida final del sistema."""

    question: str
    answer: str
    found_in_context: bool
    references: list[Reference] = Field(default_factory=list)

    @model_validator(mode="after")
    def references_required_when_found(self) -> "RAGResponse":
        if self.found_in_context and not self.references:
            raise ValueError("Una respuesta encontrada en el contexto debe tener referencias.")
        if not self.found_in_context and self.references:
            raise ValueError("Una respuesta 'No lo sé' no puede tener referencias.")
        return self
