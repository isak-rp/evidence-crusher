# Frontend (Streamlit)
La interfaz visual para los abogados.

## Estructura
- **main.py**: Punto de entrada (Login y Navegación).
- **/pages**: Las vistas funcionales (Dashboard, Auditoría, Configuración).
- **/assets**: CSS personalizado e imágenes.

## Reglas
- Usar `requests` para hablar con el Backend. NUNCA conectar a la base de datos directamente desde aquí.
- Manejar estados de carga (spinners) para mejorar la UX.
