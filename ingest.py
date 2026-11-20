"""Módulo de ingesta: lee /data, fragmenta (chunking) y persiste en ChromaDB.

Uso:
    python ingest.py            # indexa solo si la base no existe o cambiaron los datos
    python ingest.py --force    # fuerza la reindexación completa

Estrategia de chunking:
1. Tamaño medido en TOKENS (tiktoken, cl100k_base): chunks de hasta 500 tokens
   con 50 tokens de overlap (CHUNK_SIZE / CHUNK_OVERLAP en config.py).
2. RecursiveCharacterTextSplitter corta por líneas (párrafos, ítems, filas de
   tabla, títulos) y solo baja a oraciones/palabras si una línea es muy larga.
   A cada parte se le antepone el final del texto anterior (~50 tokens, desde
   el inicio de una palabra), así el overlap está garantizado en todos los chunks.
3. "Contextual chunk header": a cada fragmento se le antepone el título del
   documento y la sección a la que pertenece, para que el embedding conserve
   el contexto aunque el fragmento quede separado del resto del archivo.
4. IDs deterministas (archivo + número de chunk): reindexar no duplica datos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

logger = logging.getLogger("rag.ingest")

MANIFEST_NAME = "ingest_manifest.json"
# Subir este número si cambia el algoritmo de chunking: fuerza la reindexación.
CHUNKING_VERSION = 2
HEADER_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Conteo de tokens
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _get_encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding(config.TOKENIZER_ENCODING)
    except Exception as exc:  # sin red la primera vez, por ejemplo
        warnings.warn(
            f"No se pudo cargar tiktoken ({exc}). Se usa una aproximación de "
            "1 token ≈ 4 caracteres.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None


def count_tokens(text: str) -> int:
    encoder = _get_encoder()
    if encoder is None:
        return max(1, len(text) // 4)
    return len(encoder.encode(text))


# ---------------------------------------------------------------------------
# Carga y chunking
# ---------------------------------------------------------------------------
def load_documents(data_dir: Path = config.DATA_DIR) -> list[Document]:
    """Lee todos los .md / .txt de la carpeta de datos."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de datos: {data_dir}")

    files = sorted(
        p for p in data_dir.iterdir() if p.suffix.lower() in config.SUPPORTED_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(f"No hay archivos .md/.txt en {data_dir}")

    docs = []
    for path in files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            logger.warning("Archivo vacío, se ignora: %s", path.name)
            continue
        title_match = HEADER_RE.search(text)
        title = title_match.group(2) if title_match else path.stem
        docs.append(
            Document(page_content=text, metadata={"source": path.name, "title": title})
        )
    return docs


def build_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter de la parte "nueva" de cada chunk.

    Cada chunk final = overlap (hasta CHUNK_OVERLAP tokens del texto anterior)
    + parte nueva (hasta CHUNK_SIZE - CHUNK_OVERLAP tokens), así nunca supera
    CHUNK_SIZE. El overlap se agrega en `_overlap_start` y no depende del
    splitter: el de LangChain solo arrastra líneas enteras que entren en el
    overlap, y si la última línea es más larga, el chunk se queda sin overlap.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE - config.CHUNK_OVERLAP,
        chunk_overlap=0,
        length_function=count_tokens,  # tamaño medido en tokens
        # Unidad mínima = línea (párrafo, ítem de lista, fila de tabla o título),
        # así los cortes no parten una idea al medio. Solo si una línea supera
        # el tamaño se baja a oraciones y palabras.
        separators=["\n", ". ", " ", ""],
        keep_separator="end",
        strip_whitespace=True,
    )


def _overlap_start(text: str, start: int, max_tokens: int = config.CHUNK_OVERLAP) -> int:
    """Posición desde la que arrancar para incluir hasta `max_tokens` tokens del
    texto anterior a `start`, cortando siempre en el inicio de una palabra."""
    words = list(re.finditer(r"\S+\s*", text[:start]))
    begin = start
    for word in reversed(words):
        if count_tokens(text[word.start():start]) > max_tokens:
            break
        begin = word.start()
    return begin


def _sections_for(text: str, start: int, end: int) -> list[str]:
    """Secciones (##/###) que abarca el fragmento [start, end).

    Incluye la sección "abierta" donde empieza el chunk aunque su título haya
    quedado en el chunk anterior: así no se pierde a qué tema pertenece.
    """
    current, inside = "", []
    for match in HEADER_RE.finditer(text):
        if len(match.group(1)) < 2:  # ignorar el título H1 del documento
            continue
        if match.start() <= start:
            current = match.group(2)
        elif match.start() < end:
            inside.append(match.group(2))
    return ([current] if current else []) + inside


def split_documents(docs: list[Document]) -> list[Document]:
    """Fragmenta y enriquece cada chunk con metadatos y un header de contexto."""
    splitter = build_splitter()
    chunks: list[Document] = []
    for doc in docs:
        stem = Path(doc.metadata["source"]).stem
        pieces = splitter.split_documents([doc])
        search_from = 0
        for i, piece in enumerate(pieces):
            # Posición de la parte nueva en el texto original.
            new_start = doc.page_content.find(piece.page_content, search_from)
            if new_start == -1:
                new_start = search_from
            end = new_start + len(piece.page_content)
            search_from = end
            # Overlap: se antepone el final del texto anterior (≈50 tokens).
            start = _overlap_start(doc.page_content, new_start) if i > 0 else new_start
            body = doc.page_content[start:end].strip()
            sections = _sections_for(doc.page_content, start, end)
            section = " / ".join(sections)
            header = f"Documento: {doc.metadata['title']}"
            if section:
                header += f" | Secciones: {section}"
            chunk_id = f"{stem}::chunk-{i:02d}"
            chunks.append(
                Document(
                    page_content=f"{header}\n\n{body}",
                    metadata={
                        "source": doc.metadata["source"],
                        "title": doc.metadata["title"],
                        "section": section,
                        "chunk_id": chunk_id,
                        "chunk_index": i,
                        "start_index": start,
                        "n_tokens": count_tokens(body),
                        "overlap_tokens": count_tokens(doc.page_content[start:new_start]) if start < new_start else 0,
                    },
                    id=chunk_id,
                )
            )
    return chunks


# ---------------------------------------------------------------------------
# Persistencia en ChromaDB
# ---------------------------------------------------------------------------
@dataclass
class IngestResult:
    vectorstore: Chroma
    reindexed: bool
    n_chunks: int


def _fingerprint(docs: list[Document], embedding_model: str) -> str:
    """Hash de los datos + parámetros: si algo cambia, hay que reindexar."""
    h = hashlib.sha256()
    for d in docs:
        h.update(d.metadata["source"].encode())
        h.update(d.page_content.encode())
    h.update(f"v{CHUNKING_VERSION}|{config.CHUNK_SIZE}|{config.CHUNK_OVERLAP}|{embedding_model}".encode())
    return h.hexdigest()


def read_manifest(persist_dir: Path = config.PERSIST_DIR) -> dict | None:
    path = Path(persist_dir) / MANIFEST_NAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def open_vectorstore(
    embeddings: Embeddings,
    persist_dir: Path = config.PERSIST_DIR,
    collection_name: str = config.COLLECTION_NAME,
) -> Chroma:
    """Cliente persistente de Chroma con métrica coseno."""
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
        collection_metadata={"hnsw:space": "cosine"},
    )


def ingest(
    *,
    data_dir: Path = config.DATA_DIR,
    persist_dir: Path = config.PERSIST_DIR,
    collection_name: str = config.COLLECTION_NAME,
    embeddings: Embeddings | None = None,
    embedding_model_name: str = config.EMBEDDING_MODEL,
    force: bool = False,
) -> IngestResult:
    """Indexa los documentos solo si hace falta.

    Se saltea la indexación (ahorrando tiempo y costo de API) cuando la base ya
    existe, tiene datos, y el manifiesto coincide con los archivos actuales y el
    modelo de embeddings configurado.
    """
    persist_dir = Path(persist_dir)
    docs = load_documents(data_dir)
    fingerprint = _fingerprint(docs, embedding_model_name)

    embeddings = embeddings or config.get_embeddings()
    vectorstore = open_vectorstore(embeddings, persist_dir, collection_name)
    manifest = read_manifest(persist_dir)
    current_count = vectorstore._collection.count()

    if (
        not force
        and manifest
        and manifest.get("fingerprint") == fingerprint
        and current_count == manifest.get("n_chunks")
    ):
        logger.info(
            "La base vectorial ya existe y está al día (%d chunks). Se omite la ingesta.",
            current_count,
        )
        return IngestResult(vectorstore, reindexed=False, n_chunks=current_count)

    reason = "forzada" if force else ("datos nuevos o modificados" if manifest else "base inexistente")
    logger.info("Indexando documentos (%s)...", reason)

    chunks = split_documents(docs)
    if current_count:
        vectorstore.reset_collection()  # borra y recrea la colección
    vectorstore.add_documents(chunks, ids=[c.id for c in chunks])

    persist_dir.mkdir(parents=True, exist_ok=True)
    (persist_dir / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "embedding_model": embedding_model_name,
                "collection": collection_name,
                "chunk_size": config.CHUNK_SIZE,
                "chunk_overlap": config.CHUNK_OVERLAP,
                "n_chunks": len(chunks),
                "files": sorted({c.metadata["source"] for c in chunks}),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logger.info("Ingesta completa: %d documentos → %d chunks.", len(docs), len(chunks))
    return IngestResult(vectorstore, reindexed=True, n_chunks=len(chunks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de documentos en ChromaDB")
    parser.add_argument("--force", action="store_true", help="forzar reindexación")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    result = ingest(force=args.force)
    for chunk in split_documents(load_documents()):
        m = chunk.metadata
        print(f"  {m['chunk_id']:<40} {m['n_tokens']:>4} tok (overlap {m['overlap_tokens']:>2}) | {m['section'] or '(intro)'}")
    print(f"\nTotal: {result.n_chunks} chunks en '{config.PERSIST_DIR}'"
          f" ({'reindexado' if result.reindexed else 'sin cambios'}).")


if __name__ == "__main__":
    main()
