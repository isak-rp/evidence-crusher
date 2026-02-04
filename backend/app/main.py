"""Minimal FastAPI application for Evidence Crusher.

Este módulo expone un endpoint de ping que verifica la
conectividad con la base de datos PostgreSQL.
"""

from typing import Any

import os

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg2 import Error as PsycopgError
from psycopg2.extras import RealDictCursor


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
