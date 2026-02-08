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
        title = st.text_input("TÃ­tulo del caso")
        description = st.text_area("DescripciÃ³n")
        submitted = st.form_submit_button("Crear Caso")

    if submitted:
        if not title.strip():
            st.warning("El tÃ­tulo es obligatorio.")
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

                st.write("ðŸ“„ **Documentos en este expediente:**")

                detail_res = requests.get(f"{API_URL}/{selected_case_id}")
                if detail_res.status_code == 200:
                    docs = detail_res.json().get("documents", [])
                    if docs:
                        for doc in docs:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"- ðŸ“„ **{doc['doc_type']}**: {doc['filename']}")
                            with col2:
                                if st.button("âš¡ Procesar", key=doc["id"]):
                                    with st.spinner("Leyendo documento..."):
                                        proc_res = requests.post(
                                            f"{BACKEND_URL}/api/v1/documents/{doc['id']}/process",
                                            timeout=30,
                                        )
                                        if proc_res.status_code == 200:
                                            data = proc_res.json()
                                            st.success(
                                                f"Â¡LeÃ­do! ({data['strategy']}) - {data['chunks']} fragmentos."
                                            )
                                        else:
                                            st.error("Error al procesar.")
                    else:
                        st.info("No hay documentos cargados aÃºn.")
    else:
        st.info("No hay expedientes registrados.")
