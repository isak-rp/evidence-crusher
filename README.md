# Evidence Crusher

Plataforma LegalTech para ingesta, clasificacion, extraccion estructurada y analisis con trazabilidad.
Incluye visor PDF con RAG contextual, citaciones y auditoria de inconsistencias.

## Arquitectura (Nivel 3)
- Backend: FastAPI + Celery + pgvector
- Frontend: Streamlit
- Storage: MinIO (S3-compatible)
- LLM/Embeddings: Ollama (local pequeno) + Groq/OpenRouter (pesados)
- Queue: Redis

## Servicios
- `backend`: API REST
- `frontend`: UI Streamlit
- `db`: PostgreSQL + pgvector
- `ollama`: LLMs (`llama3.2:3b`, `qwen2.5:7b`, `command-r`, `deepseek-r1`)
- `redis`: broker/result backend Celery
- `minio`: almacenamiento S3-compatible
- `worker-ingest`: OCR + clasificacion
- `worker-embed`: embeddings
- `worker-extract`: extraccion estructurada con trazabilidad
- `worker-audit`: cross-check legal

## Modelos (Ensamble por etapa)
- Ingestion Stage: `llama3.2:1b` local (clasificacion rapida)
- Extraction Stage: API (Groq/OpenRouter) para JSON estructurado con trazabilidad
- RAG/Viewer Stage: API (Groq/OpenRouter) para chat con citaciones
- Reasoning Stage: API (Groq/OpenRouter) para auditoria de inconsistencias

## Variables de entorno
Revisa `.env.example` y crea `.env`.

MinIO:
```env
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=evidence-crusher
S3_REGION=us-east-1
```

Celery/Redis:
```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

Ollama / Proveedores AI:
```env
OLLAMA_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=mxbai-embed-large
OLLAMA_LLM_MODEL=llama3.2:1b
AI_PROVIDER=ollama|groq|openrouter
GROQ_API_KEY=
OPENROUTER_API_KEY=
```

Workers:
- `ingest` / `embed`: `AI_PROVIDER=ollama`
- `extract` / `audit`: `AI_PROVIDER=groq`

## Quick Start (Docker)
1. Arranca todo:
```bash
docker-compose up --build
```
2. Frontend: `http://localhost:8501`
3. API: `http://localhost:8000`
4. MinIO Console: `http://localhost:9001`

## Migraciones (Alembic)
Alembic se inicializa desde cero en `backend/alembic`.

Pasos recomendados:
1. Crear revision inicial:
```bash
cd backend
alembic revision --autogenerate -m "init"
```
2. Aplicar:
```bash
alembic upgrade head
```

Si ya tienes datos, usa la migracion manual:
`backend/migrations/20260211_visual_rag.sql`

## Flujo de trabajo
1. Subir documento
2. Procesar (OCR + clasificar) -> Celery queue `ingest`
3. Indexar (embeddings) -> Celery queue `embed`
4. Extraer metadata -> Celery queue `extract`
5. Auditoria -> Celery queue `audit`

## Endpoints clave
- `POST /api/v1/documents/{id}/process` (cola)
- `POST /api/v1/documents/{id}/embed` (cola)
- `GET /api/v1/documents/{id}/file` (stream del PDF)
- `POST /api/v1/documents/{id}/chat` (RAG con citaciones)
- `POST /api/v1/cases/{id}/extract-metadata` (cola)
- `POST /api/v1/cases/{id}/audit` (cola, si se agrega en fase siguiente)
- `GET /api/v1/tasks/{task_id}` (estado de tarea)

## Estado del visor
El frontend muestra:
- Vista dividida con PDF + highlights
- Boton "Ver Fuente" para deep-link y resaltado
- Chat contextual con `command-r`

## Notas de escalabilidad
- Archivos en MinIO, no en disco local
- Procesos pesados fuera del request HTTP
- Workers horizontales por cola

## Seguridad y operaciones
- Limitar CORS en produccion
- Montar secretos como variables de entorno
- Backups: DB y MinIO
- Monitoreo: logs JSON + metricas (siguiente fase)
