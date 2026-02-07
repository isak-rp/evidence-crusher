"""Streamlit page for Case Management Core."""

from __future__ import annotations

from typing import Any, Dict, List
import os

import pandas as pd
import requests
import streamlit as st


BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")


def _handle_http_error(exc: requests.RequestException) -> None:
    st.error(f"Error al contactar con el backend: {exc}")


def create_case(title: str, description: str) -> Dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}/cases/",
        json={"title": title, "description": description},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_cases() -> List[Dict[str, Any]]:
    response = requests.get(f"{BACKEND_URL}/cases/", timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_case_detail(case_id: str) -> Dict[str, Any]:
    response = requests.get(f"{BACKEND_URL}/cases/{case_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def upload_document(case_id: str, file_bytes: bytes, filename: str, doc_type: str) -> Dict[str, Any]:
    files = {"file": (filename, file_bytes, "application/pdf")}
    data = {"doc_type": doc_type}
    response = requests.post(
        f"{BACKEND_URL}/cases/{case_id}/documents/",
        files=files,
        data=data,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Expedientes - Evidence Crusher")
st.title("Núcleo de Gestión de Expedientes")

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

                documents = detail.get("documents", [])
                if documents:
                    st.markdown("**Documentos registrados**")
                    doc_df = pd.DataFrame(documents)
                    st.dataframe(doc_df, use_container_width=True)
                else:
                    st.info("Este caso aún no tiene documentos.")
    else:
        st.info("No hay expedientes registrados.")
