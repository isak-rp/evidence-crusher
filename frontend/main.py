import time
import streamlit as st
import requests
import os
from streamlit_pdf_viewer import pdf_viewer

# --- CONFIGURACIÓN DE LA APP ---
st.set_page_config(
    page_title="Evidence Crusher",  # Nombre de la App
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

# --- CONFIGURACIÓN DE URLS ---
BACKEND_HOST = os.getenv("BACKEND_URL", "http://backend:8000")
API_URL = f"{BACKEND_HOST}/api/v1/cases"
DOCS_URL = f"{BACKEND_HOST}/api/v1/documents"

# --- ESTILOS CSS ---
st.markdown("""
<style>
    /* Ocultar menú default de Streamlit para look de App nativa */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Botones de acción */
    div[data-testid="stButton"] button:contains("ELIMINAR") {
        border-color: #ff4b4b;
        color: #ff4b4b;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .badge-chip {
        display: inline-block;
        padding: 2px 8px;
        margin-right: 6px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        color: #1b1b1b;
        background: #e5e7eb;
        border: 1px solid #d1d5db;
    }
    .chip-pending { background: #fde68a; border-color: #f59e0b; }
    .chip-started { background: #bfdbfe; border-color: #3b82f6; }
    .chip-success { background: #bbf7d0; border-color: #22c55e; }
    .chip-failure { background: #fecaca; border-color: #ef4444; }
    .chip-retry { background: #e9d5ff; border-color: #a855f7; }
    .chip-revoked { background: #e5e7eb; border-color: #9ca3af; }
    .task-loader {
        display: inline-block;
        width: 10px;
        height: 10px;
        margin-right: 6px;
        border: 2px solid #60a5fa;
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        vertical-align: middle;
    }
    @keyframes spin {
        to { transform: rotate(360deg); }
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
            if method == 'GET':
                return requests.get(url, **kwargs)
            if method == 'POST':
                return requests.post(url, **kwargs)
            if method == 'DELETE':
                return requests.delete(url, **kwargs)
        except requests.exceptions.ConnectionError:
            if attempt == retries:
                return None
            time.sleep(delay)
            delay *= 2
        except requests.exceptions.ReadTimeout:
            return None
    return None

# --- CACHÉ ---
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


def set_viewer_state(doc_id: str | None, page: int | None = None, bbox: dict | None = None):
    st.session_state.viewer_doc_id = doc_id
    st.session_state.viewer_page = page
    st.session_state.viewer_bbox = bbox


@st.cache_data(ttl=300, show_spinner=False)
def get_document_bytes(doc_id: str):
    res = safe_request('GET', f"{DOCS_URL}/{doc_id}/file", timeout=30)
    if res and res.status_code == 200:
        return res.content
    return None


def bbox_to_annotation(bbox: dict | None):
    if not bbox:
        return None
    try:
        return {
            "page": max(int(bbox.get("page", 1)) - 1, 0),
            "x": bbox.get("x0"),
            "y": bbox.get("y0"),
            "width": (bbox.get("x1") - bbox.get("x0")) if bbox.get("x1") is not None else None,
            "height": (bbox.get("y1") - bbox.get("y0")) if bbox.get("y1") is not None else None,
            "color": "yellow",
        }
    except Exception:
        return None


def ask_document_chat(doc_id: str, question: str):
    payload = {"question": question, "limit": 5}
    res = safe_request('POST', f"{DOCS_URL}/{doc_id}/chat", json=payload, timeout=60)
    if res and res.status_code == 200:
        return res.json()
    return {"answer": "Error consultando el modelo.", "sources": []}


@st.cache_data(ttl=5, show_spinner=False)
def get_technical_sheet_cached(case_id: str):
    res = safe_request('GET', f"{API_URL}/{case_id}/technical-sheet", timeout=10)
    if res and res.status_code == 200:
        return res.json()
    return None


def get_task_status(task_id: str):
    res = safe_request('GET', f"{BACKEND_HOST}/api/v1/tasks/{task_id}", timeout=10)
    if res and res.status_code == 200:
        return res.json()
    return {"task_id": task_id, "status": "ERROR", "result": None}


def register_task(task_id: str, action: str, doc_id: str | None = None, filename: str | None = None):
    st.session_state.task_ids.append(task_id)
    st.session_state.task_meta[task_id] = {
        "action": action,
        "doc_id": doc_id,
        "filename": filename,
        "created_at": time.time(),
    }


def status_icon(status: str) -> str:
    icons = {
        "PENDING": "⏳",
        "STARTED": "▶",
        "SUCCESS": "✓",
        "FAILURE": "✖",
        "RETRY": "↻",
        "REVOKED": "■",
        "ERROR": "!",
    }
    return icons.get(status, "?")


def active_loader_html(status: str) -> str:
    if status in {"PENDING", "STARTED"}:
        return '<span class="task-loader"></span>'
    return ""


def find_latest_doc_task(doc_id: str, action: str):
    for tid in reversed(st.session_state.task_ids):
        meta = st.session_state.task_meta.get(tid, {})
        if meta.get("doc_id") == doc_id and meta.get("action") == action:
            snapshot = get_task_status(tid)
            return tid, snapshot.get("status", "ERROR")
    return None, None


def status_chip(status: str) -> str:
    cls_map = {
        "PENDING": "chip-pending",
        "STARTED": "chip-started",
        "SUCCESS": "chip-success",
        "FAILURE": "chip-failure",
        "RETRY": "chip-retry",
        "REVOKED": "chip-revoked",
        "ERROR": "chip-failure",
    }
    css_class = cls_map.get(status, "chip-revoked")
    return f'<span class="badge-chip {css_class}">{status}</span>'


def doc_pipeline_status(doc: dict) -> tuple[bool, bool, int, int]:
    is_classified = bool(doc.get("is_classified"))
    is_indexed = bool(doc.get("is_indexed"))
    chunk_count = int(doc.get("chunk_count") or 0)
    indexed_chunk_count = int(doc.get("indexed_chunk_count") or 0)
    return is_classified, is_indexed, chunk_count, indexed_chunk_count


def looks_like_duplicate_case_error(response) -> bool:
    if not response:
        return False
    text_chunks = []
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("detail", "message", "error", "msg"):
                if key in payload:
                    text_chunks.append(str(payload.get(key, "")))
            # FastAPI/Pydantic puede devolver lista de errores en "detail"
            detail = payload.get("detail")
            if isinstance(detail, list):
                for item in detail:
                    if isinstance(item, dict):
                        text_chunks.append(str(item.get("msg", "")))
                        text_chunks.append(str(item.get("type", "")))
    except ValueError:
        pass
    text_chunks.append(response.text or "")
    haystack = " ".join(text_chunks).lower()
    duplicate_markers = [
        "duplic",
        "exist",
        "already",
        "unique",
        "integrity",
        "constraint",
    ]
    return any(marker in haystack for marker in duplicate_markers)


def risk_badge(level: str) -> str:
    level = (level or "").upper()
    return {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🟢 LOW",
    }.get(level, "⚪ UNKNOWN")


FIELD_LABELS = {
    "start_date_real": "Fecha real de ingreso",
    "termination_date": "Fecha de salida",
    "termination_cause": "Motivo de terminación",
    "salary_sd": "Salario diario",
    "salary_sdi": "Salario diario integrado",
    "claimed_amount": "Monto reclamado",
    "closure_offer": "Oferta de cierre",
    "contract_type": "Tipo de contrato",
    "position": "Puesto",
    "attendance_control": "Control de asistencia",
    "imss_registration": "Registro en IMSS",
    "repse_status": "Estatus REPSE",
    "nom035_status": "Estatus NOM-035",
    "reglamento_status": "Reglamento interior",
    "comisiones_mixtas_status": "Comisiones mixtas",
    "nda_status": "Confidencialidad",
}


def humanize_field_key(key: str) -> str:
    if not key:
        return "-"
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    clean = str(key).replace("_", " ").strip()
    return clean[:1].upper() + clean[1:]


def humanize_value(value):
    if value is None:
        return "-"
    text = str(value).strip()
    normalized = text.replace("_", " ").upper()
    replacements = {
        "AUSENTE": "No encontrado",
        "PRESENTE": "Disponible",
        "SIN COBERTURA": "Sin evidencia",
        "INSUFICIENTE": "Información incompleta",
        "VENCIDO": "Vencido",
        "FACT": "Hecho",
        "CLAIM": "Dicho por una de las partes",
        "CONFLICT": "Conflicto entre documentos",
        "MISSING": "Falta evidencia",
    }
    if normalized in replacements:
        return replacements[normalized]
    if "_" in text:
        text = text.replace("_", " ")
    return text


def friendly_alert_text(message: str, field_key: str | None = None, required_doc_type: str | None = None) -> str:
    msg = (message or "").strip()
    if msg.startswith("FALTA_EVIDENCIA:"):
        parts = msg.split(":")
        raw_field = field_key or (parts[1] if len(parts) > 1 else "campo")
        raw_doc = required_doc_type or (parts[2] if len(parts) > 2 else "documento")
        return f"Falta evidencia para {humanize_field_key(raw_field)}. Documento sugerido: {humanize_field_key(raw_doc)}."
    msg = msg.replace("_", " ")
    return msg[:1].upper() + msg[1:] if msg else "Alerta de revisión."


# --- SIDEBAR: GESTIÓN DE CASOS ---
st.sidebar.header("📁 Mis Expedientes")

if "viewer_doc_id" not in st.session_state:
    set_viewer_state(None)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "task_ids" not in st.session_state:
    st.session_state.task_ids = []
if "task_meta" not in st.session_state:
    st.session_state.task_meta = {}

# Cargar casos
cases = get_cases_cached()

# Formulario Crear
with st.sidebar.expander("➕ Nuevo Expediente", expanded=False):
    with st.form("create_case_form", clear_on_submit=True):
        new_case_title = st.text_input("Nombre del Cliente/Caso:")
        submitted = st.form_submit_button("Crear Expediente")
        
        if submitted:
            title_clean = new_case_title.strip()
            if not title_clean:
                st.error("Nombre obligatorio.")
            else:
                existing_titles = {
                    str(c.get("title", "")).strip().lower()
                    for c in cases
                    if isinstance(c, dict)
                }
                if title_clean.lower() in existing_titles:
                    st.caption("El nombre del caso o cliente ya existe.")
                else:
                    with st.spinner("Creando..."):
                        r = safe_request('POST', API_URL, json={"title": title_clean, "description": "App"}, timeout=10)
                        if r and r.status_code in [200, 201]:
                            st.success("¡Creado!")
                            clear_cache()
                            time.sleep(0.5)
                            st.rerun()
                        elif (r and r.status_code in [400, 409, 422]) or looks_like_duplicate_case_error(r):
                            if looks_like_duplicate_case_error(r):
                                st.caption("El nombre del caso o cliente ya existe.")
                            else:
                                st.warning("⚠️ Error al crear. Revisar más a fondo.")
                        else:
                            st.warning("⚠️ Error al crear. Revisar más a fondo.")

st.sidebar.divider()

if not cases:
    st.info("👈 Crea tu primer expediente.")
    st.stop() 

# Selector de casos
cases_map = {c["id"]: c["title"] for c in cases}
valid_ids = list(cases_map.keys())
selected_case_id = st.sidebar.radio(
    "Seleccionar:", 
    options=valid_ids,
    format_func=lambda x: cases_map.get(x, "Desconocido")
)


# --- PÁGINA PRINCIPAL ---
if selected_case_id:
    should_force_refresh = False

    # No cacheamos esto para ver los documentos frescos al subir
    case_res = safe_request('GET', f"{API_URL}/{selected_case_id}", timeout=5)

    if case_res and case_res.status_code == 200:
        case = case_res.json()
        st.title(f"📂 {case['title']}")

        viewer_active = st.session_state.get("viewer_doc_id") is not None
        if viewer_active:
            col_left, col_right = st.columns([1, 1], gap="large")
            with col_left:
                tab_docs, tab_info, tab_config = st.tabs(["📄 Documentos", "📊 Ficha Técnica", "⚙️ Configuración"])
            with col_right:
                st.subheader("👁️ Visor del Documento")
                if st.button("✖️ Cerrar visor"):
                    set_viewer_state(None)
                    st.rerun()
                viewer_doc_id = st.session_state.get("viewer_doc_id")
                viewer_page = st.session_state.get("viewer_page")
                viewer_bbox = st.session_state.get("viewer_bbox")
                pdf_bytes = get_document_bytes(viewer_doc_id) if viewer_doc_id else None
                if pdf_bytes:
                    annotations = []
                    ann = bbox_to_annotation(viewer_bbox)
                    if ann:
                        annotations.append(ann)
                    try:
                        if annotations and viewer_page is not None:
                            pdf_viewer(
                                pdf_bytes,
                                annotations=annotations,
                                page=viewer_page - 1,
                                height=900,
                            )
                        else:
                            pdf_viewer(pdf_bytes, height=900)
                    except TypeError:
                        pdf_viewer(pdf_bytes, height=900)
                else:
                    st.info("Selecciona un documento para visualizar.")

                st.markdown("### 💬 Chat Contextual")
                question = st.text_input("Pregunta sobre el documento", key="doc_chat_input")
                if st.button("Preguntar", key="doc_chat_btn") and viewer_doc_id and question:
                    response = ask_document_chat(viewer_doc_id, question)
                    st.session_state.chat_history.append({
                        "q": question,
                        "a": response.get("answer"),
                        "sources": response.get("sources", []),
                    })
                for item in reversed(st.session_state.chat_history):
                    st.markdown(f"**Q:** {item['q']}")
                    st.markdown(f"**A:** {item['a']}")
                    if item["sources"]:
                        st.markdown("Fuentes:")
                        for s in item["sources"]:
                            st.write(f"- p{s['page']}: {s['text']}")
        else:
            tab_docs, tab_info, tab_config = st.tabs(["📄 Documentos", "📊 Ficha Técnica", "⚙️ Configuración"])

        # TAB 1: DOCUMENTOS
        with tab_docs:
            docs = case.get("documents", [])
            if "show_upload_panel" not in st.session_state:
                st.session_state.show_upload_panel = False
            has_docs = len(docs) > 0

            show_full_uploader = not has_docs
            if has_docs:
                up_col_a, up_col_b = st.columns([1, 1])
                if up_col_a.button("➕ Subir", key="show_upload_btn"):
                    st.session_state.show_upload_panel = not st.session_state.show_upload_panel
                if st.session_state.show_upload_panel and up_col_b.button("✖ Cerrar", key="hide_upload_btn"):
                    st.session_state.show_upload_panel = False
                show_full_uploader = st.session_state.show_upload_panel

            if show_full_uploader:
                st.subheader("Subir")
                uploaded_files = st.file_uploader(
                    "Archivo PDF/Imagen",
                    type=["pdf", "png", "jpg", "jpeg"],
                    accept_multiple_files=True,
                )
                if uploaded_files and st.button("Guardar Archivo(s)"):
                    with st.spinner("Subiendo..."):
                        uploaded_count = 0
                        queued_classify = 0
                        for uf in uploaded_files:
                            files = {"file": (uf.name, uf, uf.type)}
                            data = {"case_id": selected_case_id, "doc_type": "DETECTANDO..."}
                            r = safe_request('POST', f"{DOCS_URL}/", files=files, data=data, timeout=60)
                            if r and r.status_code == 200:
                                uploaded_count += 1
                                payload = r.json()
                                doc_id = payload.get("document_id")
                                if doc_id:
                                    c_res = safe_request('POST', f"{DOCS_URL}/{doc_id}/process", timeout=60)
                                    if c_res and c_res.status_code == 200:
                                        c_payload = c_res.json()
                                        if c_payload.get("task_id"):
                                            register_task(
                                                c_payload["task_id"],
                                                action="Clasificar documento",
                                                doc_id=doc_id,
                                                filename=uf.name,
                                            )
                                            queued_classify += 1
                        if uploaded_count > 0:
                            st.success(f"Se guardaron {uploaded_count} archivo(s). Clasificación automática en progreso ({queued_classify}).")
                            st.session_state.show_upload_panel = False
                            st.session_state[f"pending_index_prompt_{selected_case_id}"] = True
                            st.rerun()
                        else:
                            st.error("No se pudo guardar ningún archivo.")

            st.subheader("Expediente Digital")
            st.caption("Estados: clasificado e indexado siempre visibles")
            has_active_doc_tasks = False
            selection_key = f"selected_docs_{selected_case_id}"
            if selection_key not in st.session_state:
                st.session_state[selection_key] = []
            if docs:
                doc_map = {d["id"]: d for d in docs}
                selected_docs = [d for d in st.session_state[selection_key] if d in doc_map]
                st.session_state[selection_key] = selected_docs

                toolbar_left, toolbar_right = st.columns([4, 1])
                with toolbar_left:
                    act1, act2, act3, act4, act5, act6 = st.columns([0.9, 0.9, 1.0, 1.0, 1.1, 0.8])
                with toolbar_right:
                    st.caption(f"Seleccionados: {len(selected_docs)} de {len(docs)}")

                if act1.button("☑️ Todo", key=f"sel_all_{selected_case_id}", use_container_width=True):
                    st.session_state[selection_key] = [d["id"] for d in docs]
                    st.rerun()
                if act2.button("⬜ Limpiar", key=f"clear_sel_{selected_case_id}", use_container_width=True):
                    st.session_state[selection_key] = []
                    st.rerun()
                if act3.button("🧠 Indexar", key=f"bulk_index_{selected_case_id}", disabled=len(selected_docs) == 0, use_container_width=True):
                    pending_to_index = [doc_map[doc_id] for doc_id in selected_docs if not bool(doc_map[doc_id].get("is_indexed"))]
                    if not pending_to_index:
                        st.info("Los documentos seleccionados ya están indexados.")
                    else:
                        for doc in pending_to_index:
                            res = safe_request('POST', f"{DOCS_URL}/{doc['id']}/embed", timeout=120)
                            if res and res.status_code == 200:
                                payload = res.json()
                                if payload.get("task_id"):
                                    register_task(
                                        payload["task_id"],
                                        action="Indexar embeddings",
                                        doc_id=doc["id"],
                                        filename=doc["filename"],
                                    )
                        st.success(f"Indexación en cola para {len(pending_to_index)} documento(s).")
                        st.rerun()
                if act4.button("🗑️ Borrar", key=f"bulk_delete_{selected_case_id}", disabled=len(selected_docs) == 0, use_container_width=True):
                    deleted = 0
                    for doc_id in selected_docs:
                        res = safe_request('DELETE', f"{DOCS_URL}/{doc_id}")
                        if res and res.status_code == 200:
                            deleted += 1
                    st.session_state[selection_key] = []
                    st.success(f"Se eliminaron {deleted} documento(s).")
                    st.rerun()
                if act5.button("👁️ Ver", key=f"bulk_view_{selected_case_id}", disabled=len(selected_docs) != 1, use_container_width=True):
                    only_doc_id = selected_docs[0]
                    set_viewer_state(only_doc_id, page=1, bbox=None)
                    st.rerun()
                if act6.button("↻", key=f"refresh_docs_{selected_case_id}", use_container_width=True):
                    clear_cache()
                    st.rerun()

                st.markdown("---")
                hdr = st.columns([0.6, 4.5, 2.2, 2.2])
                hdr[0].caption("Sel.")
                hdr[1].caption("Documento")
                hdr[2].caption("Clasificación")
                hdr[3].caption("Indexación")

                all_classified = True
                for doc in docs:
                    is_classified, is_indexed, chunk_count, indexed_chunk_count = doc_pipeline_status(doc)
                    if not is_classified:
                        all_classified = False
                    doc_id = doc["id"]
                    check_key = f"doc_sel_{selected_case_id}_{doc_id}"
                    st.session_state[check_key] = doc_id in st.session_state[selection_key]
                    row = st.columns([0.6, 4.5, 2.2, 2.2])
                    checked = row[0].checkbox("", key=check_key, label_visibility="collapsed")
                    if checked and doc_id not in st.session_state[selection_key]:
                        st.session_state[selection_key].append(doc_id)
                    if (not checked) and doc_id in st.session_state[selection_key]:
                        st.session_state[selection_key].remove(doc_id)

                    doc_type = doc.get("doc_type") or "SIN_CLASIFICAR"
                    row[1].markdown(f"**{doc['filename']}**  \n:gray[{humanize_field_key(doc_type)}]")
                    row[2].caption("🟢 Listo" if is_classified else "🟡 En proceso")
                    row[3].caption(
                        f"🟢 Listo ({indexed_chunk_count}/{chunk_count})"
                        if is_indexed
                        else f"🟡 Pendiente ({indexed_chunk_count}/{chunk_count})"
                    )

                    classify_tid, classify_state = find_latest_doc_task(doc_id, "Clasificar documento")
                    if classify_state in {"PENDING", "STARTED"}:
                        has_active_doc_tasks = True
                        should_force_refresh = True
                    embed_tid, embed_state = find_latest_doc_task(doc_id, "Indexar embeddings")
                    if embed_state in {"PENDING", "STARTED"}:
                        has_active_doc_tasks = True
                        should_force_refresh = True

                prompt_key = f"pending_index_prompt_{selected_case_id}"
                dismiss_key = f"dismissed_index_prompt_{selected_case_id}"
                any_unindexed = any(not bool(d.get("is_indexed")) for d in docs)
                if prompt_key not in st.session_state:
                    st.session_state[prompt_key] = False
                if dismiss_key not in st.session_state:
                    st.session_state[dismiss_key] = False
                if all_classified and any_unindexed and st.session_state[prompt_key] and not st.session_state[dismiss_key]:
                    st.info("Todos los documentos ya están clasificados. ¿Deseas indexarlos ahora?")
                    p1, p2 = st.columns(2)
                    if p1.button("Sí, indexar ahora", key=f"prompt_index_now_{selected_case_id}"):
                        to_index = [d for d in docs if not bool(d.get("is_indexed"))]
                        for doc in to_index:
                            res = safe_request('POST', f"{DOCS_URL}/{doc['id']}/embed", timeout=120)
                            if res and res.status_code == 200:
                                payload = res.json()
                                if payload.get("task_id"):
                                    register_task(
                                        payload["task_id"],
                                        action="Indexar embeddings",
                                        doc_id=doc["id"],
                                        filename=doc["filename"],
                                    )
                        st.session_state[prompt_key] = False
                        st.session_state[dismiss_key] = True
                        st.success("Indexación en cola.")
                        st.rerun()
                    if p2.button("Más tarde", key=f"prompt_index_later_{selected_case_id}"):
                        st.session_state[dismiss_key] = True
                        st.session_state[prompt_key] = False
                        st.rerun()
            else:
                st.info("Carpeta vacía.")

            if has_active_doc_tasks:
                st.caption("Actualizando estado de tareas...")
                try:
                    st.autorefresh(interval=3000, key=f"docs_tasks_autorefresh_{selected_case_id}")
                except Exception:
                    pass

        # TAB 2: FICHA TÉCNICA
        with tab_info:
            technical_sheet = get_technical_sheet_cached(selected_case_id)
            st.markdown("### 🧾 Resumen rápido con fuentes")
            meta = case.get("metadata_info")
            col_met, col_btn = st.columns([3, 1])
            with col_met:
                fields = []
                if meta:
                    if meta.get("start_date"):
                        fields.append({
                            "label": "📅 Ingreso",
                            "value": meta.get("start_date"),
                            "doc_id": meta.get("start_date_source_doc_id"),
                            "page": meta.get("start_date_page"),
                            "bbox": meta.get("start_date_bbox"),
                        })
                    if meta.get("end_date"):
                        fields.append({
                            "label": "🛑 Baja",
                            "value": meta.get("end_date"),
                            "doc_id": meta.get("end_date_source_doc_id"),
                            "page": meta.get("end_date_page"),
                            "bbox": meta.get("end_date_bbox"),
                        })
                    if meta.get("daily_salary") is not None:
                        fields.append({
                            "label": "💰 Salario",
                            "value": f"${meta.get('daily_salary')}",
                            "doc_id": meta.get("daily_salary_source_doc_id"),
                            "page": meta.get("daily_salary_page"),
                            "bbox": meta.get("daily_salary_bbox"),
                        })
                # Fallback a ficha técnica cuando metadata tradicional no tiene todos los datos.
                facts = (technical_sheet or {}).get("facts") or []
                facts_by_key = {f.get("field_key"): f for f in facts}
                has_salary = any("Salario" in f["label"] for f in fields)
                if not has_salary and facts_by_key.get("salary_sd"):
                    fs = facts_by_key.get("salary_sd")
                    fields.append({
                        "label": "💰 Salario",
                        "value": f"${fs.get('value_raw')}" if fs.get("value_raw") is not None else "-",
                        "doc_id": fs.get("source_doc_id"),
                        "page": fs.get("source_page"),
                        "bbox": fs.get("source_bbox"),
                    })
                if fields:
                    for i, field in enumerate(fields):
                        row = st.columns([2, 1])
                        row[0].metric(field["label"], field["value"])
                        if field["doc_id"] and field["page"]:
                            if row[1].button("🔗 Ver Fuente", key=f"src_{i}_{field['doc_id']}"):
                                set_viewer_state(field["doc_id"], page=field["page"], bbox=field["bbox"])
                                st.rerun()
                        else:
                            row[1].button("🔗 Ver Fuente", key=f"src_{i}_disabled", disabled=True)
                else:
                    st.info("No se han extraído datos clave aún.")
            with col_btn:
                if st.button("🔍 Analizar Todo", type="primary"):
                    with st.spinner("Analizando..."):
                        res = safe_request('POST', f"{API_URL}/{selected_case_id}/extract-metadata", timeout=60)
                        if res and res.status_code == 200:
                            payload = res.json()
                            st.success(f"En cola: {payload.get('task_id', 'analizando')}")
                            if payload.get("task_id"):
                                register_task(
                                    payload["task_id"],
                                    action="Analizar ficha técnica",
                                    doc_id=None,
                                    filename=None,
                                )
                            get_technical_sheet_cached.clear()
                            st.rerun()
                        else:
                            st.error("Error al analizar.")

            st.divider()
            st.markdown("### 🧠 Auditor Integral 360°")
            ctl_a, ctl_b = st.columns([1, 2])
            with ctl_a:
                if st.button("🏗️ Construir Ficha 360", key="build_techsheet_btn"):
                    with st.spinner("Construyendo ficha técnica 360..."):
                        res = safe_request('POST', f"{API_URL}/{selected_case_id}/build-technical-sheet", timeout=30)
                        if res and res.status_code == 200:
                            payload = res.json()
                            st.success(f"En cola: {payload.get('task_id', 'build')}")
                            if payload.get("task_id"):
                                register_task(
                                    payload["task_id"],
                                    action="Construir ficha técnica 360",
                                    doc_id=None,
                                    filename=None,
                                )
                            get_technical_sheet_cached.clear()
                            st.rerun()
                        else:
                            st.warning("⚠️ No se pudo encolar la construcción de ficha 360.")
            with ctl_b:
                if st.button("🔄 Refrescar Ficha 360", key="refresh_techsheet_btn"):
                    get_technical_sheet_cached.clear()
                    st.rerun()

            if technical_sheet:
                summary = technical_sheet.get("executive_summary", {})
                conflicts = technical_sheet.get("conflicts") or []
                if conflicts:
                    st.markdown("#### ⚖️ Conflictos Detectados (Prioridad)")
                    to_show = conflicts[:3]
                    for c in to_show:
                        c_key = humanize_field_key(c.get("field_key", "-"))
                        c_val = c.get("value_raw", "-")
                        st.markdown(
                            f"<div style='border-left:4px solid #ef4444;padding:8px 12px;"
                            f"background:rgba(239,68,68,0.08);border-radius:8px;margin-bottom:8px;'>"
                            f"<strong>🔴 {c_key}</strong><br>{humanize_value(c_val)}</div>",
                            unsafe_allow_html=True,
                        )
                        src_doc = c.get("source_doc_id")
                        src_page = c.get("source_page")
                        src_bbox = c.get("source_bbox")
                        if src_doc and src_page and st.button("🔗 Ver Fuente Conflicto", key=f"conf_src_{c.get('id')}"):
                            set_viewer_state(src_doc, page=src_page, bbox=src_bbox)
                            st.rerun()
                    if len(conflicts) > 3:
                        with st.expander(f"Ver todos los conflictos ({len(conflicts)})", expanded=False):
                            for c in conflicts[3:]:
                                c_key = humanize_field_key(c.get("field_key", "-"))
                                st.error(f"{c_key}: {humanize_value(c.get('value_raw', '-'))}")
                                src_doc = c.get("source_doc_id")
                                src_page = c.get("source_page")
                                src_bbox = c.get("source_bbox")
                                if src_doc and src_page:
                                    if st.button("🔗 Ver Fuente Conflicto", key=f"conf_src_more_{c.get('id')}"):
                                        set_viewer_state(src_doc, page=src_page, bbox=src_bbox)
                                        st.rerun()

                missing_required = technical_sheet.get("missing_required_docs") or []
                if missing_required:
                    st.markdown("#### 📌 Documentos obligatorios faltantes")
                    for alert in missing_required:
                        req = alert.get("required_doc_type") or "DOCUMENTO_OBLIGATORIO"
                        field_key = alert.get("field_key") or "campo"
                        st.warning(
                            f"{friendly_alert_text(alert.get('message', ''), field_key, req)} "
                            f"(Campo: {humanize_field_key(field_key)})."
                        )

                overall = (summary.get("overall_status") or "YELLOW").upper()
                semaphore = {
                    "RED": "🔴 CRÍTICO",
                    "YELLOW": "🟡 ALERTA",
                    "GREEN": "🟢 BLINDADO",
                }.get(overall, "🟡 ALERTA")
                st.markdown(f"#### 🚦 Semáforo General: {semaphore}")
                st.info(summary.get("litis_narrative") or "Narrativa no disponible.")
                narrative_mode = summary.get("narrative_mode", "DETERMINISTIC")
                st.caption(f"Modo narrativa: {narrative_mode}")
                scores = summary.get("dimension_scores") or {}
                if scores:
                    s1, s2, s3 = st.columns(3)
                    with s1:
                        eco = scores.get("economico") or {}
                        st.metric("Riesgo Económico", f"{eco.get('score', 0)} / 100", eco.get("level", "N/A"))
                    with s2:
                        doc = scores.get("documental") or {}
                        st.metric("Riesgo Documental", f"{doc.get('score', 0)} / 100", doc.get("level", "N/A"))
                    with s3:
                        comp = scores.get("compliance") or {}
                        st.metric("Riesgo de Cumplimiento", f"{comp.get('score', 0)} / 100", comp.get("level", "N/A"))
                high_alerts = summary.get("high_impact_alerts") or []
                if high_alerts:
                    st.markdown("**⚠️ Alertas de Alto Impacto**")
                    for msg in high_alerts[:3]:
                        st.warning(friendly_alert_text(msg))
                    if len(high_alerts) > 3:
                        with st.expander(f"Ver todas las alertas ({len(high_alerts)})", expanded=False):
                            for msg in high_alerts[3:]:
                                st.warning(friendly_alert_text(msg))

                pillars = technical_sheet.get("pillars") or {}
                fx_a, fx_b, fx_c = st.columns(3)
                only_critical = fx_a.checkbox("Solo críticos", value=False, key="tech_only_critical")
                only_missing = fx_b.checkbox("Solo missing", value=False, key="tech_only_missing")
                only_conflict = fx_c.checkbox("Solo conflictos", value=True, key="tech_only_conflict")
                only_authority = st.checkbox("Solo autoridad", value=False, key="tech_only_authority")
                for pillar_name, facts in pillars.items():
                    filtered_facts = []
                    for fact in facts:
                        if only_critical and (fact.get("risk_level") or "").upper() != "CRITICAL":
                            continue
                        if only_missing and (fact.get("truth_status") or "").upper() != "MISSING":
                            continue
                        if only_conflict and (fact.get("truth_status") or "").upper() != "CONFLICT":
                            continue
                        if only_authority and (fact.get("party_side") or "").upper() != "AUTORIDAD":
                            continue
                        filtered_facts.append(fact)
                    with st.expander(f"{pillar_name} ({len(facts)})", expanded=False):
                        if not filtered_facts:
                            st.caption("Sin datos.")
                            continue
                        for fact in filtered_facts:
                            row = st.columns([2, 2, 2, 1, 1])
                            row[0].markdown(f"**{humanize_field_key(fact.get('field_key', '-'))}**")
                            row[1].write(humanize_value(fact.get("value_raw") or "-"))
                            row[2].caption(
                                f"{risk_badge(fact.get('risk_level', ''))} · {humanize_value(fact.get('truth_status', '-'))}"
                            )
                            src_doc = fact.get("source_doc_id")
                            src_page = fact.get("source_page")
                            src_bbox = fact.get("source_bbox")
                            fact_id = fact.get("id", "")
                            if src_doc and src_page:
                                if row[3].button("🔗 Ver Fuente", key=f"tech_src_{fact_id}"):
                                    set_viewer_state(src_doc, page=src_page, bbox=src_bbox)
                                    st.rerun()
                            else:
                                row[3].button("🔗 Ver Fuente", key=f"tech_src_dis_{fact_id}", disabled=True)
                            if row[4].button("ℹ️ Detalle", key=f"tech_detail_{fact_id}"):
                                st.session_state[f"show_detail_{fact_id}"] = not st.session_state.get(f"show_detail_{fact_id}", False)
                            if st.session_state.get(f"show_detail_{fact_id}", False):
                                st.caption(f"Regla: {fact.get('rule_applied') or '-'}")
                                st.code(str(fact.get("value_normalized") or {}))
                                excerpt = fact.get("source_text_excerpt")
                                if excerpt:
                                    st.write(excerpt)
                                if (fact.get("risk_level") or "").upper() == "CRITICAL":
                                    st.error(f"Qué faltó: {fact.get('why_critical') or 'Evidencia crítica ausente.'}")
                                    st.info(f"Qué documento lo resolvería: {fact.get('evidence_hint') or 'Agregar documento obligatorio del campo.'}")

                cmp_empresa = [f for f in (technical_sheet.get("facts") or []) if (f.get("party_side") or "").upper() == "EMPRESA"]
                cmp_autoridad = [f for f in (technical_sheet.get("facts") or []) if (f.get("party_side") or "").upper() == "AUTORIDAD"]
                cmp_trabajador = [f for f in (technical_sheet.get("facts") or []) if (f.get("party_side") or "").upper() == "TRABAJADOR"]
                st.markdown("#### 🧭 Comparativo de Fuentes")
                col_emp, col_aut, col_tra = st.columns(3)
                with col_emp:
                    st.markdown("**🔵 Empresa**")
                    for f in cmp_empresa[:8]:
                        st.caption(f"{humanize_field_key(f.get('field_key'))}: {humanize_value(f.get('value_raw'))}")
                with col_aut:
                    st.markdown("**⚫ Autoridad**")
                    for f in cmp_autoridad[:8]:
                        st.caption(f"{humanize_field_key(f.get('field_key'))}: {humanize_value(f.get('value_raw'))}")
                with col_tra:
                    st.markdown("**🔴 Trabajador**")
                    for f in cmp_trabajador[:8]:
                        st.caption(f"{humanize_field_key(f.get('field_key'))}: {humanize_value(f.get('value_raw'))}")
            else:
                st.caption("Construye la Ficha 360 para ver semáforo, narrativa y smart fields.")

        # TAB 3: CONFIGURACIÓN
        with tab_config:
            st.header("⚙️ Administración")
            st.warning("Zona de Peligro")
            st.markdown("### 🧾 Estado de Tareas")
            st.markdown(
                """
                <div>
                    <span class="badge-chip chip-pending">PENDING</span>
                    <span class="badge-chip chip-started">STARTED</span>
                    <span class="badge-chip chip-success">SUCCESS</span>
                    <span class="badge-chip chip-failure">FAILURE/ERROR</span>
                    <span class="badge-chip chip-retry">RETRY</span>
                    <span class="badge-chip chip-revoked">REVOKED</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            auto_refresh = st.checkbox("Auto-refresh", value=False)
            status_filter = st.selectbox(
                "Filtrar por estado",
                options=["ALL", "PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY", "REVOKED"],
                index=0,
            )
            if auto_refresh:
                try:
                    st.autorefresh(interval=5000, key="tasks_autorefresh")
                except Exception:
                    pass

            if st.session_state.task_ids:
                recent_ids = list(dict.fromkeys(st.session_state.task_ids))[-15:]
                for tid in recent_ids:
                    status = get_task_status(tid)
                    state = status.get("status")
                    if status_filter != "ALL" and state != status_filter:
                        continue
                    if state in {"PENDING", "STARTED"}:
                        should_force_refresh = True
                    meta = st.session_state.task_meta.get(tid, {})
                    action = meta.get("action", "Tarea")
                    filename = meta.get("filename")
                    label = f"{action}" if not filename else f"{action} - {filename}"
                    st.markdown(
                        f"- {status_icon(state)} `{tid}` {status_chip(state)}  \n  {label}",
                        unsafe_allow_html=True,
                    )
                    if state in {"FAILURE", "RETRY", "ERROR"}:
                        result = status.get("result")
                        traceback_text = status.get("traceback")
                        with st.expander(f"Detalle de error: {tid}", expanded=False):
                            if result is None:
                                st.write("Sin detalle disponible.")
                            elif isinstance(result, (dict, list)):
                                st.json(result)
                            else:
                                st.code(str(result))
                            if traceback_text:
                                st.caption("Traceback")
                                st.code(str(traceback_text))
            else:
                st.info("No hay tareas recientes.")
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
                        else:
                            st.error("Error al eliminar.")
                with c_no:
                    if st.button("CANCELAR"):
                        st.session_state[f"del_confirm_{selected_case_id}"] = False
                        st.rerun()
    else:
        st.warning("No se pudo cargar el expediente. Posiblemente fue eliminado.")

if selected_case_id and should_force_refresh:
    # Refresco continuo mientras existan tareas activas para evitar
    # que la UI se quede en PENDING/STARTED hasta una interacción manual.
    time.sleep(2.5)
    st.rerun()
