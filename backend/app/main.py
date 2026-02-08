"""Minimal FastAPI application for Evidence Crusher.

Este módulo expone un endpoint de ping que verifica la
conectividad con la base de datos PostgreSQL y un endpoint
de prueba para la lógica legal (LFT).
"""

from decimal import Decimal
from typing import Any

import os

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg2 import Error as PsycopgError
from psycopg2.extras import RealDictCursor

from app.api.v1.endpoints.cases import router as cases_router
from app.api.v1.endpoints.documents import router as documents_router
from app.core.legal_constants import (
    INDEMNIZACION_CONSTITUCIONAL_MESES,
    LIQUIDACION_ESTIMACION_DIAS_POR_ANIO,
)
from app.db.session import init_db
from app.schemas.legal_ontology import PerfilActor


class PingResponse(BaseModel):
    """Response model for the ping endpoint.

    Attributes:
        message: Human readable message.
        database: Database connectivity status.
    """

    message: str
    database: str


def _get_db_connection() -> psycopg2.extensions.connection:
    """Create a new PostgreSQL connection using environment variables.

    Returns:
        psycopg2.extensions.connection: A live database connection.

    Raises:
        PsycopgError: If the connection cannot be established.
    """

    user: str | None = os.getenv("POSTGRES_USER")
    password: str | None = os.getenv("POSTGRES_PASSWORD")
    host: str = os.getenv("POSTGRES_SERVER", "localhost")
    port: str = os.getenv("POSTGRES_PORT", "5432")
    db_name: str | None = os.getenv("POSTGRES_DB")

    dsn: str = (
        f"dbname={db_name} user={user} password={password} "
        f"host={host} port={port}"
    )

    return psycopg2.connect(dsn)


app: FastAPI = FastAPI(title=os.getenv("PROJECT_NAME", "Evidence Crusher"))

app.include_router(cases_router, prefix="/api/v1/cases", tags=["Expedientes"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["Documentos"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/ping", response_model=PingResponse)
async def ping() -> PingResponse:
    """Ping endpoint to validate connectivity between API and database.

    Returns:
        PingResponse: Object containing a simple ping/pong message and
        database connectivity status.

    Raises:
        HTTPException: If the database is not reachable.
    """

    try:
        with _get_db_connection() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT 1 AS ok;")
                row: dict[str, Any] | None = cursor.fetchone()
    except PsycopgError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database connectivity error",
        ) from exc

    database_status: str = "ok" if row and row.get("ok") == 1 else "unknown"
    return PingResponse(message="pong", database=database_status)


# ---------------------------------------------------------------------------
# Test de lógica legal (LFT): antigüedad y estimación de liquidación
# ---------------------------------------------------------------------------
class TestLegalLogicResponse(BaseModel):
    """Respuesta del endpoint de prueba de lógica legal.

    Incluye antigüedad calculada y estimación básica (Art. 48 + días por año).
    """

    antiguedad_anios: float
    liquidacion_estimada_mxn: Decimal
    detalle: str


@app.post("/test-legal-logic/", response_model=TestLegalLogicResponse)
async def test_legal_logic(perfil: PerfilActor) -> TestLegalLogicResponse:
    """Prueba la lógica legal: calcula antigüedad y estima liquidación básica.

    Fórmula de estimación: 3 meses de salario (Art. 48 LFT) + 20 días de
    salario por cada año de antigüedad, usando constantes de legal_constants.
    Solo para verificación matemática, no sustituye el cálculo legal completo.

    Args:
        perfil: Datos del trabajador (fechas, salarios).

    Returns:
        TestLegalLogicResponse: Antigüedad en años y monto estimado en MXN.
    """
    # Salario mensual: integrado si existe, si no salario_diario * 30 (LFT)
    salario_mensual: Decimal = (
        perfil.salario_integrado
        if perfil.salario_integrado is not None
        else perfil.salario_diario * 30
    )
    # Parte por indemnización constitucional (Art. 48 — 3 meses)
    parte_meses: Decimal = (
        Decimal(INDEMNIZACION_CONSTITUCIONAL_MESES) * salario_mensual
    )
    # Parte por días por año (estimación: 20 días por año)
    parte_dias: Decimal = (
        perfil.salario_diario
        * LIQUIDACION_ESTIMACION_DIAS_POR_ANIO
        * Decimal(str(perfil.antiguedad_anios))
    )
    liquidacion_estimada: Decimal = parte_meses + parte_dias

    detalle: str = (
        f"Antigüedad: {perfil.antiguedad_anios} años. "
        f"3 meses (Art. 48): {parte_meses} MXN. "
        f"20 días/año: {parte_dias} MXN. Total estimado: {liquidacion_estimada} MXN."
    )
    return TestLegalLogicResponse(
        antiguedad_anios=perfil.antiguedad_anios,
        liquidacion_estimada_mxn=liquidacion_estimada,
        detalle=detalle,
    )
