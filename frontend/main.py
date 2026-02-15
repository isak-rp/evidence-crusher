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
                uploaded_file = st.file_uploader("Archivo PDF/Imagen", type=["pdf", "png", "jpg", "jpeg"])
                if uploaded_file and st.button("Guardar Archivo"):
                    with st.spinner("Subiendo..."):
                        files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                        data = {"case_id": selected_case_id, "doc_type": "DETECTANDO..."}
                        r = safe_request('POST', f"{DOCS_URL}/", files=files, data=data, timeout=60)
                        if r and r.status_code == 200:
                            st.success("¡Subido!")
                            st.session_state.show_upload_panel = False
                            st.rerun()
                        else:
                            st.error(f"Error: {r.text if r else 'Timeout'}")

            st.subheader("Expediente Digital")
            st.caption("Leyenda: 🟢 listo | 🟡 pendiente")
            has_active_doc_tasks = False
            if docs:
                for doc in docs:
                    doc_type = doc.get("doc_type") or "SIN_CLASIFICAR"
                    is_classified, is_indexed, chunk_count, indexed_chunk_count = doc_pipeline_status(doc)
                    icon = "📄"
                    label_display = f"{doc_type}"
                    if "REVISION_REQUERIDA" in doc_type:
                        icon = "⚠️"
                        label_display = ":red[REVISIÓN REQUERIDA]"
                    elif "CONTRATO" in doc_type:
                        icon = "🤝"
                    elif "DEMANDA" in doc_type:
                        icon = "⚖️"

                    with st.expander(f"{icon} {label_display} - {doc['filename']}"):
                        classify_badge = "🟢 Clasificado" if is_classified else "🟡 Sin clasificar"
                        index_badge = (
                            f"🟢 Indexado ({indexed_chunk_count}/{chunk_count})"
                            if is_indexed
                            else f"🟡 Sin indexar ({indexed_chunk_count}/{chunk_count})"
                        )
                        st.markdown(f"{classify_badge}  |  {index_badge}")

                        if "REVISION_REQUERIDA" in doc_type:
                            st.warning("⚠️ Documento fuera de norma patronal.")

                        c1, c2, c3, c4 = st.columns(4)
                        # OCR
                        classify_disabled = is_classified
                        classify_help = "Documento ya clasificado." if classify_disabled else None
                        if c1.button("⚡ Clasificar", key=f"ocr_{doc['id']}", disabled=classify_disabled, help=classify_help):
                            with st.spinner("Leyendo..."):
                                res = safe_request('POST', f"{DOCS_URL}/{doc['id']}/process", timeout=60)
                                if res and res.status_code == 200:
                                    payload = res.json()
                                    if payload.get("task_id"):
                                        register_task(
                                            payload["task_id"],
                                            action="Clasificar documento",
                                            doc_id=doc["id"],
                                            filename=doc["filename"],
                                        )
                                    st.rerun()
                                else:
                                    st.error("Error.")
                        # Embed
                        index_disabled = is_indexed
                        index_help = "Documento ya indexado." if index_disabled else None
                        if c2.button("🧠 Indexar", key=f"emb_{doc['id']}", disabled=index_disabled, help=index_help):
                            with st.spinner("Memorizando..."):
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
                                else:
                                    st.error("Error.")
                        # Borrar Doc
                        if c3.button("🗑️ Borrar", key=f"del_{doc['id']}"):
                            with st.spinner("Eliminando..."):
                                res = safe_request('DELETE', f"{DOCS_URL}/{doc['id']}")
                                if res and res.status_code == 200:
                                    st.success("Borrado.")
                                    st.rerun()
                                else:
                                    st.error("Error.")
                        # Ver Doc
                        if c4.button("👁️ Ver", key=f"view_{doc['id']}"):
                            set_viewer_state(doc["id"], page=1, bbox=None)
                            st.rerun()

                        classify_tid, classify_state = find_latest_doc_task(
                            doc["id"],
                            "Clasificar documento",
                        )
                        if classify_state in {"PENDING", "STARTED"}:
                            has_active_doc_tasks = True
                            should_force_refresh = True
                            st.markdown(
                                f"{active_loader_html(classify_state)}Clasificando documento... `{classify_tid}`",
                                unsafe_allow_html=True,
                            )

                        embed_tid, embed_state = find_latest_doc_task(
                            doc["id"],
                            "Indexar embeddings",
                        )
                        if embed_state in {"PENDING", "STARTED"}:
                            has_active_doc_tasks = True
                            should_force_refresh = True
                            st.markdown(
                                f"{active_loader_html(embed_state)}Indexando embeddings... `{embed_tid}`",
                                unsafe_allow_html=True,
                            )

                        doc_task_ids = []
                        for tid in reversed(st.session_state.task_ids):
                            meta = st.session_state.task_meta.get(tid, {})
                            if meta.get("doc_id") == doc["id"]:
                                doc_task_ids.append(tid)
                            if len(doc_task_ids) >= 2:
                                break
                        for tid in doc_task_ids:
                            snapshot = get_task_status(tid)
                            state = snapshot.get("status", "ERROR")
                            task_meta = st.session_state.task_meta.get(tid, {})
                            st.caption(
                                f"{status_icon(state)} {task_meta.get('action', 'Tarea')} [{state}]"
                            )
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
            st.markdown("### 🕵️ Inteligencia Artificial")
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

            technical_sheet = get_technical_sheet_cached(selected_case_id)
            if technical_sheet:
                summary = technical_sheet.get("executive_summary", {})
                overall = (summary.get("overall_status") or "YELLOW").upper()
                semaphore = {
                    "RED": "🔴 CRÍTICO",
                    "YELLOW": "🟡 ALERTA",
                    "GREEN": "🟢 BLINDADO",
                }.get(overall, "🟡 ALERTA")
                st.markdown(f"#### 🚦 Semáforo General: {semaphore}")
                st.info(summary.get("litis_narrative") or "Narrativa no disponible.")
                high_alerts = summary.get("high_impact_alerts") or []
                if high_alerts:
                    st.markdown("**⚠️ Alertas de Alto Impacto**")
                    for msg in high_alerts:
                        st.warning(msg)

                pillars = technical_sheet.get("pillars") or {}
                fx_a, fx_b, fx_c = st.columns(3)
                only_critical = fx_a.checkbox("Solo críticos", value=False, key="tech_only_critical")
                only_missing = fx_b.checkbox("Solo missing", value=False, key="tech_only_missing")
                only_conflict = fx_c.checkbox("Solo conflictos", value=False, key="tech_only_conflict")
                for pillar_name, facts in pillars.items():
                    filtered_facts = []
                    for fact in facts:
                        if only_critical and (fact.get("risk_level") or "").upper() != "CRITICAL":
                            continue
                        if only_missing and (fact.get("truth_status") or "").upper() != "MISSING":
                            continue
                        if only_conflict and (fact.get("truth_status") or "").upper() != "CONFLICT":
                            continue
                        filtered_facts.append(fact)
                    with st.expander(f"{pillar_name} ({len(facts)})", expanded=False):
                        if not filtered_facts:
                            st.caption("Sin datos.")
                            continue
                        for fact in filtered_facts:
                            row = st.columns([2, 2, 2, 1, 1])
                            row[0].markdown(f"**{fact.get('field_key', '-') }**")
                            row[1].write(fact.get("value_raw") or "-")
                            row[2].caption(f"{risk_badge(fact.get('risk_level', ''))} · {fact.get('truth_status', '-')}")
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

                conflicts = technical_sheet.get("conflicts") or []
                if conflicts:
                    st.markdown("#### ⚖️ Conflictos Detectados")
                    for c in conflicts:
                        st.error(f"{c.get('field_key')}: {c.get('value_raw')}")
                missing_required = technical_sheet.get("missing_required_docs") or []
                if missing_required:
                    st.markdown("#### 📌 Faltantes Obligatorios")
                    for alert in missing_required:
                        req = alert.get("required_doc_type") or "DOCUMENTO_OBLIGATORIO"
                        field_key = alert.get("field_key") or "campo"
                        st.warning(f"{alert.get('message')} · Campo: `{field_key}` · Documento requerido: `{req}`")
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
