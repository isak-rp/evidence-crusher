import streamlit as st

# 1. Configuración MAESTRA (Debe ser idéntica a la de Expedientes)
st.set_page_config(
    page_title="Cargando Evidence Crusher...",
    layout="wide",
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

# 2. Redirección Inmediata
# En cuanto la app arranca, salta a la página de Expedientes.
# El usuario ni siquiera notará que pasó por aquí.
st.switch_page("pages/1_Expedientes.py")