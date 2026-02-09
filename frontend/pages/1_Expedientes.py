import time
import streamlit as st
import requests
import os

st.set_page_config(page_title="Gestión de Expediente", layout="wide", page_icon="⚖️")

# Configuración
API_URL = "http://backend:8000/api/v1/cases"
DOCS_URL = "http://backend:8000/api/v1/documents"

# ⚠️ TRUCO PARA EVITAR PANTALLA BLANCA:
# Asegúrate de que tu archivo 'Home.py' o 'Main.py' TAMBIÉN tenga layout="wide".
# Si uno es "centered" y el otro "wide", el cambio brusco causa el error.

# --- ESTILOS CSS ---
st.markdown("""
<style>
    div[data-testid="stButton"] button:contains("ELIMINAR") {
        border-color: #ff4b4b;
        color: #ff4b4b;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
</style>
""", unsafe_allow_html=True)


# --- HELPERS DE RED ---
def safe_request(method, url, **kwargs):
    kwargs.setdefault('timeout', 10)
    retries = kwargs.pop('retries', 3)
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            if method == 'GET': return requests.get(url, **kwargs)
            elif method == 'POST': return requests.post(url, **kwargs)
            elif method == 'DELETE': return requests.delete(url, **kwargs)
        except requests.exceptions.ConnectionError:
            if attempt == retries: return None
            time.sleep(delay)
            delay *= 2
        except requests.exceptions.ReadTimeout:
            return None
    return None

# --- CACHÉ INTELIGENTE (LA SOLUCIÓN AL BLANCO) ---
@st.cache_data(ttl=10, show_spinner=False)
def get_cases_cached():
    """Obtiene los casos y los guarda en memoria RAM por 10 seg."""
    res = safe_request('GET', API_URL, timeout=5)
    if res and res.status_code == 200:
        return res.json()[::-1]
    return []

def clear_cache():
    """Borra la memoria para obligar a recargar datos."""
    get_cases_cached.clear()


# --- SIDEBAR: GESTIÓN DE CASOS ---
st.sidebar.header("📁 Mis Expedientes")

# 1. Cargar casos (¡Ahora es instantáneo!)
cases = get_cases_cached()

# 2. FORMULARIO CREAR
with st.sidebar.expander("➕ Nuevo Expediente", expanded=False):
    with st.form("create_case_form", clear_on_submit=True):
        new_case_title = st.text_input("Nombre del Cliente/Caso:")
        submitted = st.form_submit_button("Crear Expediente")
        
        if submitted:
            if not new_case_title.strip():
                st.error("Nombre obligatorio.")
            else:
                with st.spinner("Creando..."):
                    r = safe_request('POST', API_URL, json={"title": new_case_title.strip(), "description": "App"}, timeout=10)
                    if r and r.status_code in [200, 201]:
                        st.success("¡Creado!")
                        clear_cache() # 🧹 Limpiamos caché para ver el nuevo
                        time.sleep(0.5)
                        st.rerun()
                    elif r and r.status_code == 400:
                        st.error("⚠️ Nombre duplicado.")
                    else:
                        st.error("Error al crear.")

st.sidebar.divider()

if not cases:
    st.info("👈 Crea tu primer expediente.")
    st.stop() # Detiene la ejecución aquí si no hay datos

# 3. SELECTOR
cases_map = {c["id"]: c["title"] for c in cases}
# Protección contra IDs eliminados que sigan en caché
valid_ids = list(cases_map.keys())
selected_case_id = st.sidebar.radio(
    "Seleccionar:", 
    options=valid_ids,
    format_func=lambda x: cases_map.get(x, "Desconocido")
)


# --- PÁGINA PRINCIPAL ---
if selected_case_id:
    # Obtener detalles del caso seleccionado
    # No cacheamos esto para ver los documentos frescos al subir
    case_res = safe_request('GET', f"{API_URL}/{selected_case_id}", timeout=5)

    if case_res and case_res.status_code == 200:
        case = case_res.json()
        st.title(f"📂 {case['title']}")
        
        tab_docs, tab_info, tab_config = st.tabs(["📄 Documentos", "📊 Ficha Técnica", "⚙️ Configuración"])

        # TAB 1: DOCUMENTOS
        with tab_docs:
            col_upload, col_list = st.columns([1, 2])
            with col_upload:
                st.subheader("Subir")
                uploaded_file = st.file_uploader("Archivo PDF/Imagen", type=["pdf", "png", "jpg", "jpeg"])
                if uploaded_file and st.button("Guardar Archivo"):
                    with st.spinner("Subiendo..."):
                        files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                        data = {"case_id": selected_case_id, "doc_type": "DETECTANDO..."}
                        r = safe_request('POST', f"{DOCS_URL}/", files=files, data=data, timeout=60)
                        if r and r.status_code == 200:
                            st.success("¡Subido!")
                            st.rerun()
                        else:
                            st.error(f"Error: {r.text if r else 'Timeout'}")

            with col_list:
                st.subheader("Expediente Digital")
                docs = case.get("documents", [])
                if docs:
                    for doc in docs:
                        doc_type = doc.get("doc_type") or "SIN_CLASIFICAR"
                        icon = "📄"
                        label_display = f"{doc_type}"
                        if "REVISION_REQUERIDA" in doc_type:
                            icon = "⚠️"
                            label_display = ":red[REVISIÓN REQUERIDA]"
                        elif "CONTRATO" in doc_type: icon = "🤝"
                        elif "DEMANDA" in doc_type: icon = "⚖️"

                        with st.expander(f"{icon} {label_display} - {doc['filename']}"):
                            if "REVISION_REQUERIDA" in doc_type:
                                st.warning("⚠️ Documento fuera de norma patronal.")
                            
                            c1, c2, c3 = st.columns(3)
                            # OCR
                            if c1.button("⚡ Clasificar", key=f"ocr_{doc['id']}"):
                                with st.spinner("Leyendo..."):
                                    res = safe_request('POST', f"{DOCS_URL}/{doc['id']}/process", timeout=60)
                                    if res and res.status_code == 200:
                                        st.toast(f"Detectado: {res.json().get('type')}")
                                        time.sleep(1)
                                        st.rerun()
                                    else: st.error("Error.")
                            # Embed
                            if c2.button("🧠 Indexar", key=f"emb_{doc['id']}"):
                                with st.spinner("Memorizando..."):
                                    res = safe_request('POST', f"{DOCS_URL}/{doc['id']}/embed", timeout=120)
                                    if res and res.status_code == 200: st.success("¡Listo!")
                                    else: st.error("Error.")
                            # Borrar Doc
                            if c3.button("🗑️ Borrar", key=f"del_{doc['id']}"):
                                with st.spinner("Eliminando..."):
                                    res = safe_request('DELETE', f"{DOCS_URL}/{doc['id']}")
                                    if res and res.status_code == 200:
                                        st.success("Borrado.")
                                        st.rerun()
                                    else: st.error("Error.")
                else:
                    st.info("Carpeta vacía.")

        # TAB 2: FICHA TÉCNICA
        with tab_info:
            st.markdown("### 🕵️ Inteligencia Artificial")
            meta = case.get("metadata_info")
            col_met, col_btn = st.columns([3, 1])
            with col_met:
                fields = []
                if meta:
                    if meta.get("start_date"): fields.append(("📅 Ingreso", meta.get("start_date")))
                    if meta.get("end_date"): fields.append(("🛑 Baja", meta.get("end_date")))
                    if meta.get("daily_salary"): fields.append(("💰 Salario", f"${meta.get('daily_salary')}"))
                if fields:
                    cols = st.columns(len(fields))
                    for i, (l, v) in enumerate(fields): cols[i].metric(l, v)
                else: st.info("No se han extraído datos clave aún.")
            with col_btn:
                if st.button("🔍 Analizar Todo", type="primary"):
                    with st.spinner("Analizando..."):
                        res = safe_request('POST', f"{API_URL}/{selected_case_id}/extract-metadata", timeout=60)
                        if res and res.status_code == 200: st.rerun()
                        else: st.error("Error al analizar.")

        # TAB 3: CONFIGURACIÓN
        with tab_config:
            st.header("⚙️ Administración")
            st.warning("Zona de Peligro")
            if f"del_confirm_{selected_case_id}" not in st.session_state:
                st.session_state[f"del_confirm_{selected_case_id}"] = False

            if not st.session_state[f"del_confirm_{selected_case_id}"]:
                if st.button("🗑️ ELIMINAR EXPEDIENTE COMPLETO"):
                    st.session_state[f"del_confirm_{selected_case_id}"] = True
                    st.rerun()
            else:
                st.error(f"¿Estás seguro de borrar '{case['title']}'?")
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if st.button("SÍ, ELIMINAR", type="primary"):
                        res = safe_request('DELETE', f"{API_URL}/{selected_case_id}")
                        if res and res.status_code == 200:
                            st.success("Caso eliminado.")
                            clear_cache() # 🧹 Limpieza obligatoria
                            time.sleep(1)
                            st.rerun()
                        else: st.error("Error al eliminar.")
                with c_no:
                    if st.button("CANCELAR"):
                        st.session_state[f"del_confirm_{selected_case_id}"] = False
                        st.rerun()
    else:
        st.warning("No se pudo cargar el expediente. Posiblemente fue eliminado.")
