from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "evidence_crusher",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_queue=os.getenv("CELERY_QUEUE", "default"),
    task_routes={
        "app.tasks.process_document": {"queue": "ingest"},
        "app.tasks.embed_document": {"queue": "embed"},
        "app.tasks.extract_case_metadata": {"queue": "extract"},
        "app.tasks.build_technical_sheet": {"queue": "extract"},
        "app.tasks.audit_case": {"queue": "audit"},
    },
)
