# Evidence Crusher - Plataforma LegalTech
Este repositorio contiene una arquitectura de microservicios para auditoría legal automatizada.

## Estructura
- **/backend**: API REST en FastAPI. Lógica de negocio e IA.
- **/frontend**: Interfaz de usuario en Streamlit.
- **/infra**: Scripts de inicialización de Base de Datos y Docker.

## Quick Start
1. Crea y activa tu entorno virtual: `python -m venv .venv`
2. Instala dependencias: `pip install -r backend/requirements.txt`
3. Levanta la infra: `docker-compose up -d`
