from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configuración de conexión
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:legalpassword123@db:5432/legal_audit_db",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Inicializa la base de datos creando extensiones necesarias."""
    try:
        # 1. ACTIVAR LA EXTENSIÓN VECTOR (El paso que faltaba)
        with engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()
            print("✅ Extensión 'vector' activada correctamente.")

    except Exception as e:
        print(f"❌ Error inicializando DB: {e}")
        raise e
