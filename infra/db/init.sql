-- Script de inicialización SQL para Evidence Crusher
-- Este script se ejecuta automáticamente al crear la base de datos.

-- Extensión para embeddings (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tablas base siguiendo las convenciones del proyecto

CREATE TABLE IF NOT EXISTS firms (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    firm_id INTEGER NOT NULL REFERENCES firms (id),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients (id),
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tabla de ejemplo para futuros vectores de IA
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    firm_id INTEGER NOT NULL REFERENCES firms (id),
    event TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
