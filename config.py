"""Configuración central del sistema RAG.

Todos los parámetros se pueden sobreescribir con variables de entorno (archivo .env).
Las credenciales NUNCA se escriben en el código: se leen de variables de entorno
(GOOGLE_API_KEY para Gemini, OPENAI_API_KEY u ANTHROPIC_API_KEY según el proveedor).
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
# LLM: "gemini" (por defecto, tiene capa gratuita), "openai", "anthropic" u "ollama".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
_DEFAULT_LLM = {
    "gemini": "gemini-flash-latest",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1:8b",
}
LLM_MODEL = os.getenv("LLM_MODEL", _DEFAULT_LLM.get(LLM_PROVIDER, ""))
# Los modelos Gemini recientes no aceptan temperature: solo se envía si se define.
_temp = os.getenv("LLM_TEMPERATURE")
LLM_TEMPERATURE = float(_temp) if _temp else (None if LLM_PROVIDER == "gemini" else 0.0)

# Embeddings: "gemini" (por defecto, capa gratuita), "openai" o "huggingface" (local).
# El MISMO modelo se usa para indexar y para consultar; queda registrado en el
# manifiesto de la base para detectar desajustes.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
_DEFAULT_EMB = {
    "gemini": "gemini-embedding-001",
    "huggingface": "intfloat/multilingual-e5-small",
    "openai": "text-embedding-3-small",
}
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", _DEFAULT_EMB.get(EMBEDDING_PROVIDER, ""))

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


_KEY_FOR = {"gemini": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def require_api_key() -> None:
    """Falla con un mensaje claro si falta la clave del proveedor elegido."""
    needed = {_KEY_FOR[p] for p in (LLM_PROVIDER, EMBEDDING_PROVIDER) if p in _KEY_FOR}
    missing = sorted(k for k in needed if not os.getenv(k))
    if missing:
        raise RuntimeError(
            f"Falta la variable de entorno {', '.join(missing)}. "
            "Copiá .env.example a .env y completá tu clave (el .env no se sube a Git)."
        )


def get_embeddings():
    """Modelo de embeddings según EMBEDDING_PROVIDER."""
    if EMBEDDING_PROVIDER == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        # La familia E5 espera los prefijos "query: " y "passage: ".
        e5 = "e5" in EMBEDDING_MODEL.lower()
        return HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True, **({"prompt": "passage: "} if e5 else {})},
            query_encode_kwargs={"normalize_embeddings": True, **({"prompt": "query: "} if e5 else {})},
        )
    if EMBEDDING_PROVIDER == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        require_api_key()
        # Usa task_type RETRIEVAL_DOCUMENT al indexar y RETRIEVAL_QUERY al consultar.
        return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    if EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings

        require_api_key()
        return OpenAIEmbeddings(model=EMBEDDING_MODEL)
    raise ValueError(f"EMBEDDING_PROVIDER desconocido: {EMBEDDING_PROVIDER}")


def get_llm():
    """LLM según LLM_PROVIDER."""
    if LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        require_api_key()
        return ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            # Modo JSON nativo: reduce errores de parseo del PydanticOutputParser.
            response_mime_type="application/json",
            timeout=60,
            max_retries=3,  # la capa gratuita puede devolver 429 momentáneos
        )
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        require_api_key()
        return ChatAnthropic(
            model=LLM_MODEL, temperature=LLM_TEMPERATURE, max_tokens=1024,
            timeout=60, max_retries=2,
        )
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        require_api_key()
        return ChatOpenAI(
            model=LLM_MODEL, temperature=LLM_TEMPERATURE,
            # Modo JSON: reduce errores de parseo del PydanticOutputParser.
            model_kwargs={"response_format": {"type": "json_object"}},
            timeout=60, max_retries=2,
        )
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=LLM_MODEL, temperature=LLM_TEMPERATURE, format="json")
    raise ValueError(f"LLM_PROVIDER desconocido: {LLM_PROVIDER}")
