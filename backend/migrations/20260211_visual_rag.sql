-- Visual RAG + trazabilidad
-- 1) Aumentar dimensión del embedding a 1024 (Ollama mxbai-embed-large)
ALTER TABLE document_chunks
    ALTER COLUMN embedding TYPE vector(1024);

-- 2) Trazabilidad de metadatos en case_metadata
ALTER TABLE case_metadata
    ADD COLUMN IF NOT EXISTS start_date_source_doc_id UUID NULL,
    ADD COLUMN IF NOT EXISTS start_date_page INTEGER NULL,
    ADD COLUMN IF NOT EXISTS start_date_bbox JSONB NULL,
    ADD COLUMN IF NOT EXISTS end_date_source_doc_id UUID NULL,
    ADD COLUMN IF NOT EXISTS end_date_page INTEGER NULL,
    ADD COLUMN IF NOT EXISTS end_date_bbox JSONB NULL,
    ADD COLUMN IF NOT EXISTS daily_salary_source_doc_id UUID NULL,
    ADD COLUMN IF NOT EXISTS daily_salary_page INTEGER NULL,
    ADD COLUMN IF NOT EXISTS daily_salary_bbox JSONB NULL;

ALTER TABLE case_metadata
    ADD CONSTRAINT IF NOT EXISTS fk_case_metadata_start_date_doc
    FOREIGN KEY (start_date_source_doc_id) REFERENCES documents(id) ON DELETE SET NULL;

ALTER TABLE case_metadata
    ADD CONSTRAINT IF NOT EXISTS fk_case_metadata_end_date_doc
    FOREIGN KEY (end_date_source_doc_id) REFERENCES documents(id) ON DELETE SET NULL;

ALTER TABLE case_metadata
    ADD CONSTRAINT IF NOT EXISTS fk_case_metadata_daily_salary_doc
    FOREIGN KEY (daily_salary_source_doc_id) REFERENCES documents(id) ON DELETE SET NULL;
