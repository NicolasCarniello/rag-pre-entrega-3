"""Configuración central del sistema RAG.

Todos los parámetros se pueden sobreescribir con variables de entorno (archivo .env).
Las credenciales NUNCA se escriben en el código: se leen de OPENAI_API_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Rutas -------------------------------------------------------------------
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", BASE_DIR / "data"))
PERSIST_DIR = Path(os.getenv("RAG_PERSIST_DIR", BASE_DIR / "vectorstore"))
COLLECTION_NAME = os.getenv("RAG_COLLECTION", "andes_pay_docs")
SUPPORTED_EXTENSIONS = (".md", ".txt")

# --- Modelos -----------------------------------------------------------------
# El MISMO modelo de embeddings se usa para indexar y para consultar.
# Queda registrado en el manifiesto de la base para detectar desajustes.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# --- Chunking (en TOKENS, no en caracteres) ----------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
TOKENIZER_ENCODING = "cl100k_base"  # tokenizer de los modelos de OpenAI

# --- Recuperación ------------------------------------------------------------
# Entre 3 y 5 para evitar el "contexto infinito" / Lost in the Middle.
TOP_K = int(os.getenv("TOP_K", "4"))
if not 3 <= TOP_K <= 5:
    raise ValueError(f"TOP_K debe estar entre 3 y 5 (valor actual: {TOP_K}).")

# --- Respuesta ante falta de información -------------------------------------
UNKNOWN_ANSWER = "No lo sé. Esa información no está en los documentos disponibles."
MAX_QUERY_CHARS = 1000


def require_api_key() -> None:
    """Falla con un mensaje claro si no hay API key configurada."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "Falta la variable de entorno OPENAI_API_KEY. "
            "Copiá .env.example a .env y completá tu clave (el .env no se sube a Git)."
        )


def get_embeddings():
    """Modelo de embeddings por defecto (OpenAI)."""
    from langchain_openai import OpenAIEmbeddings

    require_api_key()
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def get_llm():
    """LLM por defecto (OpenAI), forzado a responder JSON."""
    from langchain_openai import ChatOpenAI

    require_api_key()
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        # Modo JSON: reduce errores de parseo del PydanticOutputParser.
        model_kwargs={"response_format": {"type": "json_object"}},
        timeout=60,
        max_retries=2,
    )
