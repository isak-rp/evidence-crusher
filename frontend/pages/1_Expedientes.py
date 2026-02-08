import time
import streamlit as st
import requests
import os

# Configuración
API_URL = "http://backend:8000/api/v1/cases"
DOCS_URL = "http://backend:8000/api/v1/documents"

st.set_page_config(page_title="Gestión de Expediente", layout="wide")


def get_with_retry(url, *, timeout=3, retries=3):
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, timeout=timeout)
        except requests.exceptions.ConnectionError:
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2


def post_with_retry(url, *, data=None, files=None, json=None, timeout=30, retries=3):
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            return requests.post(url, data=data, files=files, json=json, timeout=timeout)
        except requests.exceptions.ConnectionError:
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2


# --- SIDEBAR: GESTIÓN DE CASOS ---
st.sidebar.header("📁 Mis Expedientes")

# 1. Intentar cargar casos existentes
cases = []
try:
    res = get_with_retry(API_URL, timeout=3, retries=2)
    if res.status_code == 200:
        cases = res.json()
except Exception:
    st.sidebar.error("⚠️ Error conectando al backend.")

# 2. Botón para CREAR NUEVO CASO (¡El Salvavidas!)
with st.sidebar.expander("➕ Nuevo Expediente", expanded=(len(cases) == 0)):
    new_case_title = st.text_input("Nombre del Cliente/Caso:")
    if st.button("Crear Expediente"):
        if new_case_title:
            with st.spinner("Creando..."):
                # Crear caso en el backend
                try:
                    r = post_with_retry(
                        API_URL,
                        json={"title": new_case_title, "description": "Creado desde App"},
                        timeout=10,
                        retries=3,
                    )
                    if r.status_code == 200:
                        st.success("¡Creado!")
                        st.rerun() # Recargar para que aparezca en la lista
                    else:
                        st.error("Error al crear el expediente.")
                except Exception:
                    st.error("⚠️ Error conectando al backend.")
        else:
            st.warning("Escribe un nombre.")

st.sidebar.divider()

# 3. Selector de Casos
if not cases:
    st.info("👈 ¡Tu base de datos está limpia! Crea tu primer expediente en el menú de la izquierda.")
    st.stop() # Detener ejecución aquí si no hay casos

# Si hay casos, mostramos el selector
selected_case_id = st.sidebar.radio(
    "Seleccionar:", 
    [c["id"] for c in cases], 
    format_func=lambda x: next((c["title"] for c in cases if c["id"] == x), x)
)

if selected_case_id:
    # --- DETALLES DEL CASO SELECCIONADO ---
    case_res = None
    try:
        case_res = get_with_retry(f"{API_URL}/{selected_case_id}", timeout=3, retries=2)
    except Exception:
        st.error("⚠️ Error conectando al backend.")

    if case_res is not None and case_res.status_code == 200:
        case = case_res.json()
        st.title(f"📂 {case['title']}")
        
        # --- A. FICHA TÉCNICA (EXTRACCIÓN IA) ---
        st.markdown("### 🕵️ Ficha Técnica Automática")
        meta = case.get("metadata_info")
        
        col_metrics, col_actions = st.columns([3, 1])
        with col_metrics:
            c1, c2, c3 = st.columns(3)
            if meta:
                c1.metric("📅 Ingreso", meta.get("start_date") or "--")
                c2.metric("🛑 Baja/Despido", meta.get("end_date") or "--")
                c3.metric("💰 Salario Diario", f"${meta.get('daily_salary')}" if meta.get("daily_salary") else "--")
            else:
                st.info("Sin datos analizados.")
        
        with col_actions:
            if st.button("🔍 Analizar Caso", type="primary"):
                with st.spinner("La IA está leyendo el expediente..."):
                    try:
                        res = post_with_retry(
                            f"{API_URL}/{selected_case_id}/extract-metadata",
                            timeout=30,
                            retries=3,
                        )
                        if res.status_code == 200:
                            st.rerun()
                        else:
                            st.error("Error al analizar el caso.")
                    except Exception:
                        st.error("⚠️ Error conectando al backend.")

        st.divider()

        # --- B. GESTIÓN DE DOCUMENTOS ---
        col_upload, col_list = st.columns([1, 2])

        with col_upload:
            st.subheader("Subir Documento")
            uploaded_file = st.file_uploader("Archivo PDF/Imagen", type=["pdf", "png", "jpg", "jpeg"])
            
            if uploaded_file and st.button("Guardar Archivo"):
                with st.spinner("Subiendo..."):
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    # Enviamos tipo "AUTO" para que el backend decida
                    data = {"case_id": selected_case_id, "doc_type": "DETECTANDO..."}
                    try:
                        r = post_with_retry(
                            f"{DOCS_URL}/",
                            files=files,
                            data=data,
                            timeout=30,
                            retries=3,
                        )
                        if r.status_code == 200:
                            st.success("¡Subido!")
                            st.rerun()
                        else:
                            st.error("Error al subir.")
                    except Exception:
                        st.error("⚠️ Error conectando al backend.")

        with col_list:
            st.subheader("Documentos del Caso")
            docs = case.get("documents", [])
            
            if docs:
                for doc in docs:
                    with st.expander(f"📄 {doc.get('doc_type', 'DOC')} - {doc['filename']}"):
                        c1, c2, c3 = st.columns(3)
                        
                        # Botón 1: OCR + Clasificación
                        if c1.button("⚡ Procesar", key=f"ocr_{doc['id']}"):
                            with st.spinner("Leyendo..."):
                                try:
                                    res = post_with_retry(
                                        f"{DOCS_URL}/{doc['id']}/process",
                                        timeout=60,
                                        retries=3,
                                    )
                                    if res.status_code == 200:
                                        data = res.json()
                                        st.toast(f"Tipo detectado: {data.get('detected_type', 'OK')}")
                                        st.rerun()
                                    else:
                                        st.error("Error al procesar.")
                                except Exception:
                                    st.error("⚠️ Error conectando al backend.")
                        
                        # Botón 2: Indexar (Embeddings)
                        if c2.button("🧠 Indexar", key=f"emb_{doc['id']}"):
                            with st.spinner("Vectorizando..."):
                                try:
                                    res = post_with_retry(
                                        f"{DOCS_URL}/{doc['id']}/embed",
                                        timeout=120,
                                        retries=3,
                                    )
                                    if res.status_code == 200:
                                        st.success("¡Listo!")
                                    else:
                                        st.error("Error indexando.")
                                except Exception:
                                    st.error("⚠️ Error conectando al backend.")
            else:
                st.info("No hay documentos cargados.")
