SHELL := /bin/sh

.PHONY: up down logs ruff alembic-autogen alembic-upgrade alembic-current migrate-manual

up:
\tdocker-compose up --build

down:
\tdocker-compose down

logs:
\tdocker-compose logs -f

ruff:
\tpython -m ruff check .

alembic-autogen:
\tcd backend && python -m alembic revision --autogenerate -m "autogen"

alembic-upgrade:
\tcd backend && python -m alembic upgrade head

alembic-current:
\tcd backend && python -m alembic current

migrate-manual:
\tcd backend && psql -f migrations/20260211_visual_rag.sql
