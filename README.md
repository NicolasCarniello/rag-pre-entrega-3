# Pre-entrega 3 — Sistema de recuperación semántica local (RAG)

Sistema RAG *end-to-end* en Python con **Google Gemini** (LLM + embeddings, usando la capa gratuita de la API). Recibe una pregunta, busca los fragmentos relevantes en una base vectorial local (**ChromaDB**) y genera una respuesta **basada solo en esos fragmentos**, con una cadena **LCEL asíncrona** de LangChain y salida validada con **Pydantic** (texto + referencias). Si la respuesta no está en los documentos, el sistema responde **"No lo sé"**.

El dataset de ejemplo (`/data`) son 4 documentos internos de **Andes Pay**, una fintech **ficticia**: política de reembolsos, guía de la API, onboarding/KYC y seguridad. Al ser ficticios, el modelo no puede responder "de memoria": todo lo que diga tiene que salir del contexto.

---

## Arquitectura

```
                 ┌──────────────── INGESTA (ingest.py) ────────────────┐
 data/*.md,txt → │ carga → chunking por tokens (500 / overlap 50)      │
                 │       → header de contexto (documento + secciones)  │
                 │       → embeddings gemini-embedding-001             │ → ChromaDB persistente
                 │       → IDs deterministas + manifiesto de ingesta   │   ./vectorstore (coseno)
                 └─────────────────────────────────────────────────────┘

                 ┌──────────── CONSULTA (rag_chain.py, LCEL async) ────────────┐
 pregunta ────►  │ RunnableParallel ─┬─ question (passthrough)                  │
                 │                   └─ docs: embedding + similitud top-k=4     │
                 │ → prompt "filtro de veracidad" + CONTEXTO [chunk_id | fuente]│
                 │ → Gemini Flash (ainvoke, modo JSON)                          │
                 │ → PydanticOutputParser(LLMAnswer)  (+1 reintento si falla)   │
                 │ → verificación de citas contra lo recuperado                 │ → RAGResponse
                 └──────────────────────────────────────────────────────────────┘
```

## Estructura del repo

| Archivo | Qué hace |
|---|---|
| `ingest.py` | **Módulo de ingesta**: lee `/data`, fragmenta y persiste en ChromaDB. Solo reindexa si hace falta. |
| `rag_chain.py` | **Retriever + generación grounded**: cadena LCEL y la función asíncrona `get_rag_response(query)`. |
| `schemas.py` | Modelos Pydantic: `LLMAnswer` (contrato del LLM) y `RAGResponse` (salida final con referencias). |
| `config.py` | Parámetros (modelos, chunking, top-k, rutas). Todo se puede cambiar por variables de entorno. |
| `main.py` | Demo: corre las pruebas (preguntas en contexto + preguntas trampa) en paralelo y guarda la evidencia. |
| `tests/` | `test_offline.py` (18 tests sin API key) y `test_integration.py` (con Gemini real). |
| `data/` | Dataset de ejemplo (4 archivos `.md`). |
| `evidencia/` | Resultados de las pruebas reales (`resultados_pruebas.json`). |

---

## Cómo ejecutarlo

### 1. Entorno virtual y dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Credenciales (nunca en el código)

```bash
cp .env.example .env
# editá .env y completá GOOGLE_API_KEY=...  (gratis en https://aistudio.google.com/apikey)
```

`.env` y `vectorstore/` están en `.gitignore`, así que no se suben al repo.

### 3. Ingesta

```bash
python ingest.py           # indexa (o no hace nada si la base ya está al día)
python ingest.py --force   # fuerza la reindexación
```

Muestra cada chunk con su cantidad de tokens, el overlap con el anterior y las secciones que cubre. Si lo corrés dos veces seguidas, la segunda dice `sin cambios` y no llama a la API de embeddings.

### 4. Pruebas de validación (en contexto + trampa)

```bash
python main.py
```

Lanza 4 consultas **en paralelo** (`asyncio.gather`), verifica cada resultado e imprime ✅/❌. Además guarda todo en `evidencia/resultados_pruebas.json`. El proceso termina con código 0 solo si todas las pruebas pasan.

| Pregunta | Tipo | Resultado esperado |
|---|---|---|
| ¿Cuántas veces reintenta Andes Pay el envío de un webhook y durante cuánto tiempo? | En contexto | "8 veces en 3 días" + referencia a `02_api_autenticacion_y_limites.md` |
| ¿Cuánto cuesta un contracargo y qué pasa si el comercio no presenta documentación? | En contexto | "USD 15; se da por perdido" + referencia a `01_politica_reembolsos.md` |
| ¿Qué tasa de interés cobra Andes Pay por adelantar las liquidaciones? | **Trampa** (suena plausible, pero no está) | "No lo sé", sin referencias |
| ¿Quién ganó el Mundial de fútbol 2022? | **Trampa** (el modelo lo sabe, pero no está en el contexto) | "No lo sé", sin referencias |

Para hacer una consulta puntual:

```bash
python main.py "¿Cuál es el límite de peticiones por minuto del plan Pro?"
```

### 5. Tests automáticos

```bash
pytest -q                 # 18 tests offline: no necesitan API key ni red
pytest -q -m integration  # 2 tests contra Gemini real (requieren GOOGLE_API_KEY)
```

### Uso desde código

```python
import asyncio
from rag_chain import get_rag_response

resp = asyncio.run(get_rag_response("¿Cuánto tarda la revisión manual del KYC?"))
print(resp.answer)
for ref in resp.references:
    print(ref.source, ref.chunk_id, ref.score)
```

Forma de la salida (`RAGResponse`):

```json
{
  "question": "...",
  "answer": "...",
  "found_in_context": true,
  "references": [
    {"source": "03_onboarding_kyc.md", "chunk_id": "03_onboarding_kyc::chunk-01",
     "section": "3.2 Persona jurídica / 4. Plazos de revisión / ...",
     "score": 0.0, "excerpt": "..."}
  ]
}
```

---

## Decisiones de diseño (por criterio de evaluación)

### 1. Chunking e ingesta
- **Tamaño medido en tokens, no en caracteres**: chunks de hasta **500 tokens** con **50 tokens de overlap**, contados con `tiktoken` (`cl100k_base`).
- **Cortes que respetan la estructura**: `RecursiveCharacterTextSplitter` corta por líneas (párrafo, ítem de lista, fila de tabla, título) y solo baja a oraciones y palabras si una línea es muy larga.
- **Overlap garantizado**: el splitter de LangChain solo arrastra líneas enteras que entren en el overlap, y cuando la última línea de un chunk es larga, el siguiente se queda sin overlap. Por eso el overlap se arma aparte: a cada chunk se le anteponen los ~50 tokens anteriores del texto original (empezando siempre en una palabra completa). Así cada chunk mide como máximo 450 tokens nuevos + 50 de overlap = 500. El overlap real de cada chunk queda en el metadato `overlap_tokens`, y hay un test que lo verifica.
- **Header de contexto en cada chunk**: se antepone `Documento: <título> | Secciones: <secciones que cubre>`. Así un fragmento que arranca a mitad de una tabla sigue "sabiendo" de qué trata, y el embedding lo refleja.
- **Metadatos**: `source`, `title`, `section`, `chunk_id`, `chunk_index`, `start_index`, `n_tokens`, `overlap_tokens`.
- **Persistencia inteligente**: `ingest()` calcula un hash de los archivos + parámetros de chunking + modelo de embeddings y lo guarda en `vectorstore/ingest_manifest.json`. Si coincide y la colección tiene los chunks esperados, **no reindexa** (ahorra tiempo y costo). Si cambian los datos, recrea la colección; los IDs deterministas evitan duplicados.

### 2. Arquitectura asíncrona y recuperación
- `get_rag_response(query)` es `async`. La cadena LCEL se ejecuta con `ainvoke`: la búsqueda en Chroma (`asimilarity_search_with_relevance_scores`) y la llamada al LLM no bloquean el *event loop*.
- `RunnableParallel` arma `question` y `docs` en paralelo; la inicialización (que puede incluir ingesta) corre con `asyncio.to_thread` y se protege con un `asyncio.Lock` para que consultas concurrentes no indexen dos veces.
- **Top-k = 4** (validado entre 3 y 5 en `config.py`) para evitar el "contexto infinito" y el efecto *Lost in the Middle*.
- **Mismo modelo de embeddings para indexar y consultar**: el modelo queda registrado en el manifiesto y `check_embedding_consistency()` corta la ejecución si no coincide con el configurado (el error #1 de la consigna).
- Colección configurada con **similitud coseno** (`hnsw:space = cosine`).

### 3. Validación con Pydantic
- `PydanticOutputParser(LLMAnswer)` con sus `format_instructions` inyectadas en el prompt (que exige devolver solo JSON), el **modo JSON nativo** del modelo activado (`response_mime_type="application/json"` en Gemini) y **un reintento** si el parseo falla.
- `LLMAnswer` normaliza: si `found_in_context=false`, la respuesta pasa a ser exactamente "No lo sé…" y se vacían las citas.
- `RAGResponse` exige coherencia: una respuesta encontrada **debe** tener referencias, y un "No lo sé" **no puede** tenerlas.
- Las referencias (archivo, chunk, sección, score, extracto) se construyen a partir de los fragmentos **realmente recuperados**, no de lo que el LLM dice.

### 4. Robustez y seguridad
- **Filtro de veracidad en el prompt**: responder solo con el CONTEXTO, no usar conocimiento previo, decir "No lo sé" si falta información, y tratar el contexto como datos (no como instrucciones, contra *prompt injection*).
- **Verificación de citas**: si el LLM cita un `chunk_id` que no fue recuperado, se descarta; si responde "encontrado" pero ninguna cita es válida, la respuesta se reemplaza por "No lo sé".
- **Validación de entrada**: rechaza consultas vacías o de más de 1000 caracteres.
- **Credenciales**: solo por variable de entorno (`.env` en `.gitignore`, `.env.example` sin claves). Un test recorre los archivos versionados buscando patrones de API key.

---

## Proveedores

| Pieza | Por defecto | Alternativas (variables en `.env`) |
|---|---|---|
| LLM | Gemini `gemini-flash-latest` (`GOOGLE_API_KEY`, capa gratuita) | `LLM_PROVIDER=openai` · `LLM_PROVIDER=anthropic` (Claude) · `LLM_PROVIDER=ollama` (local) |
| Embeddings | Gemini `gemini-embedding-001` | `EMBEDDING_PROVIDER=openai` → `text-embedding-3-small` · `EMBEDDING_PROVIDER=huggingface` → `intfloat/multilingual-e5-small` (local) |

- Se eligió Gemini porque su API tiene una capa gratuita que alcanza para este proyecto, y una sola clave sirve para generar texto y embeddings.
- `gemini-flash-latest` es un alias que apunta siempre al modelo Flash más reciente. Si querés fijar una versión, poné `LLM_MODEL=<id del modelo>`.
- Los embeddings de Gemini usan `task_type=RETRIEVAL_DOCUMENT` al indexar y `RETRIEVAL_QUERY` al consultar (es el mismo modelo, optimizado para cada lado de la búsqueda).
- Los modelos Gemini recientes no aceptan `temperature`, así que con Gemini no se envía. Para otros proveedores se usa `0`.
- Las alternativas necesitan sus paquetes opcionales (ver el final de `requirements.txt`). Cambiar de proveedor no requiere tocar código.
- La capa gratuita tiene límites por minuto y por día. Si aparece un error `429 RESOURCE_EXHAUSTED`, esperá un minuto y volvé a correr.

## Notas
- Si cambiás el modelo o el proveedor de embeddings, corré `python ingest.py --force`. Si no lo hacés, el sistema lo detecta y se niega a consultar (para no mezclar espacios vectoriales).
- `chunk_size` se mide con `tiktoken` (`cl100k_base`) como unidad estándar de tokens. Ese tokenizer descarga su vocabulario la primera vez (necesita internet); si no puede, usa una aproximación (1 token ≈ 4 caracteres) y avisa con un warning.
