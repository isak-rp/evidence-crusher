"""Streamlit page for Case Management Core."""

from __future__ import annotations

from typing import Any, Dict, List
import os

import pandas as pd
import requests
import streamlit as st


BACKEND_URL: str = os.getenv("BACKEND_URL", "http://backend:8000")
API_URL = f"{BACKEND_URL}/api/v1/cases"


def _handle_http_error(exc: requests.RequestException) -> None:
    st.error(f"Error al contactar con el backend: {exc}")


def create_case(title: str, description: str) -> Dict[str, Any]:
    response = requests.post(
        f"{API_URL}/",
        json={"title": title, "description": description},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_cases() -> List[Dict[str, Any]]:
    response = requests.get(f"{API_URL}/", timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_case_detail(case_id: str) -> Dict[str, Any]:
    response = requests.get(f"{API_URL}/{case_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def upload_document(case_id: str, file_bytes: bytes, filename: str, doc_type: str) -> Dict[str, Any]:
    files = {"file": (filename, file_bytes, "application/pdf")}
    data = {"doc_type": doc_type}
    response = requests.post(
        f"{API_URL}/{case_id}/documents/",
        files=files,
        data=data,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Expedientes - Evidence Crusher")
st.title("Expedientes")

tab_new, tab_explorer = st.tabs(["Nuevo Caso", "Explorador"])

with tab_new:
    st.subheader("Crear expediente")
    with st.form("create_case_form"):
        title = st.text_input("Título del caso")
        description = st.text_area("Descripción")
        submitted = st.form_submit_button("Crear Caso")

    if submitted:
        if not title.strip():
            st.warning("El título es obligatorio.")
        else:
            try:
                case = create_case(title.strip(), description.strip())
            except requests.RequestException as exc:
                _handle_http_error(exc)
            else:
                st.success("Expediente creado.")
                st.json(case)

with tab_explorer:
    st.subheader("Explorador de expedientes")
    try:
        cases = fetch_cases()
    except requests.RequestException as exc:
        _handle_http_error(exc)
        cases = []

    if cases:
        df = pd.DataFrame(
            [
                {
                    "id": case["id"],
                    "title": case["title"],
                    "status": case["status"],
                    "created_at": case["created_at"],
                }
                for case in cases
            ]
        )
        st.dataframe(df, use_container_width=True)

        case_options = {f"{case['title']} ({case['id']})": case["id"] for case in cases}
        selected_label = st.selectbox("Selecciona un caso", list(case_options.keys()))
        selected_case_id = case_options.get(selected_label)

        if selected_case_id:
            try:
                detail = fetch_case_detail(selected_case_id)
            except requests.RequestException as exc:
                _handle_http_error(exc)
                detail = {}

            if detail:
                st.markdown("**Detalles del caso**")
                st.json(detail)

                st.markdown("**Subir documento (PDF)**")
                with st.form("upload_document_form"):
                    doc_type = st.text_input("Tipo de documento (DEMANDA, PRUEBA, CONTRATO...)")
                    uploaded_file = st.file_uploader("Archivo PDF", type=["pdf"])
                    upload_submitted = st.form_submit_button("Subir Documento")

                if upload_submitted:
                    if not doc_type.strip():
                        st.warning("El tipo de documento es obligatorio.")
                    elif uploaded_file is None:
                        st.warning("Debes seleccionar un PDF.")
                    else:
                        try:
                            upload_document(
                                selected_case_id,
                                uploaded_file.getvalue(),
                                uploaded_file.name,
                                doc_type.strip(),
                            )
                        except requests.RequestException as exc:
                            _handle_http_error(exc)
                        else:
                            st.success("Documento subido.")
                            detail = fetch_case_detail(selected_case_id)

                st.write("📄 **Documentos en este expediente:**")

                detail_res = requests.get(f"{API_URL}/{selected_case_id}")
                if detail_res.status_code == 200:
                    docs = detail_res.json().get("documents", [])
                    if docs:
                        for doc in docs:
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.markdown(f"- 📄 **{doc['doc_type']}**: {doc['filename']}")

                            with col2:
                                if st.button("⚡ Procesar", key=f"proc_{doc['id']}"):
                                    with st.spinner("Leyendo documento..."):
                                        proc_res = requests.post(
                                            f"{BACKEND_URL}/api/v1/documents/{doc['id']}/process",
                                            timeout=30,
                                        )
                                        if proc_res.status_code == 200:
                                            data = proc_res.json()
                                            st.success(
                                                f"¡Leído! ({data['strategy']}) - {data['chunks']} fragmentos."
                                            )
                                        else:
                                            st.error("Error al procesar.")

                            with col3:
                                if st.button("🧠 Indexar", key=f"emb_{doc['id']}"):
                                    with st.spinner("Generando vectores..."):
                                        res = requests.post(
                                            f"{BACKEND_URL}/api/v1/documents/{doc['id']}/embed",
                                            timeout=60,
                                        )
                                        if res.status_code == 200:
                                            st.success(
                                                f"Indexado: {res.json()['chunks_embedded']} chunks"
                                            )
                                        else:
                                            st.error("Error indexando")

                            query = st.text_input(
                                "Preguntar al documento:",
                                key=f"search_{doc['id']}",
                                placeholder="Ej: ¿Cuál es la fecha de ingreso?",
                            )
                            if query:
                                payload = {"query": query, "limit": 3}
                                res_search = requests.post(
                                    f"{BACKEND_URL}/api/v1/documents/{doc['id']}/search",
                                    json=payload,
                                    timeout=60,
                                )
                                if res_search.status_code == 200:
                                    results = res_search.json()
                                    for r in results:
                                        st.info(f"Pág {r['page']}: {r['text']}")
                                else:
                                    st.warning("Primero debes procesar e indexar el documento.")
                            st.divider()
                    else:
                        st.info("No hay documentos cargados aún.")
    else:
        st.info("No hay expedientes registrados.")
