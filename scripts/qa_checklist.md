# QA Checklist — Evidence Crusher

## Infra
- DB container `healthy`
- Redis container `healthy`
- MinIO container `healthy`
- Ollama container `healthy`
- Workers running: `ingest`, `embed`, `extract`, `audit`

## Backend
- `GET /ping` returns `database=ok`
- `POST /api/v1/cases` creates a case
- `POST /api/v1/documents` uploads a file and returns `document_id`
- `POST /api/v1/documents/{id}/process` returns `task_id`
- `POST /api/v1/documents/{id}/embed` returns `task_id`
- `GET /api/v1/documents/{id}/file` returns PDF bytes
- `POST /api/v1/cases/{id}/extract-metadata` returns `task_id`
- `GET /api/v1/tasks/{task_id}` returns valid status

## Frontend
- App loads without layout shift
- Case list renders without duplicates
- Upload works and document appears
- “Clasificar/Indexar” encola tareas
- Task panel muestra estados con chips
- PDF viewer abre y resalta bbox cuando hay fuente
- Chat contextual responde

## Data
- `document_chunks.embedding` usa 1024 dims
- `case_metadata` guarda source_doc_id + bbox

## Logs
- No errores fatales al subir/leer PDF
- No fallos de conexión a MinIO
- No errores de provider (Groq/OpenRouter)
