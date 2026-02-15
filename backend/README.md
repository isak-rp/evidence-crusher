# Backend (FastAPI)
El cerebro de la aplicación. Aquí reside la lógica de IA, OCR y gestión de datos.

## Estructura de Directorios
- **/api**: Definición de Endpoints (Rutas). Solo manejan HTTP requests/responses.
- **/core**: Configuración (Settings, Seguridad).
- **/db**: Modelos SQLAlchemy y conexión a Postgres.
- **/schemas**: Modelos Pydantic (Validación de datos).
- **/services**: LÓGICA PURA. Aquí va el código de LangChain, OCR, Cálculos. Los endpoints llaman a estos servicios.

## Reglas
- **Separation of Concerns:** Un endpoint nunca debe contener lógica de negocio compleja. Debe llamar a un `service`.
- **Typing:** Todo debe tener tipos estrictos.

## Tests
- Instalar dependencias de pruebas:
  - `pip install -r requirements-dev.txt`
- Ejecutar suite legal sintetica:
  - `pytest tests -q`
