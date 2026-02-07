"""Streamlit UI for legal ontology tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict

import os

import requests
import streamlit as st


BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")


@dataclass(frozen=True)
class LegalTestPayload:
    fecha_ingreso: date
    fecha_salida: date
    salario_diario: float

    def to_json(self) -> Dict[str, Any]:
        return {
            "fecha_ingreso": self.fecha_ingreso.strftime("%Y-%m-%d"),
            "fecha_salida": self.fecha_salida.strftime("%Y-%m-%d"),
            "salario_diario": self.salario_diario,
        }


def call_legal_logic(payload: LegalTestPayload) -> Dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}/test-legal-logic/",
        json=payload.to_json(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def render_metrics(data: Dict[str, Any]) -> None:
    antiguedad = data.get("antiguedad_anios")
    vacaciones = data.get("vacaciones")
    liquidacion = data.get("liquidacion_estimada_mxn")

    cols = st.columns(3)
    cols[0].metric("Antigüedad", "-" if antiguedad is None else str(antiguedad))
    cols[1].metric("Vacaciones", "-" if vacaciones is None else str(vacaciones))
    cols[2].metric("Liquidación Estimada", "-" if liquidacion is None else str(liquidacion))


def main() -> None:
    st.set_page_config(page_title="Evidence Crusher - Hello World")
    st.title("Evidence Crusher - Hello World")

    st.write("Use este formulario para probar la lógica legal del backend.")

    with st.form("legal_logic_form"):
        st.subheader("🛠️ Prueba de Ontología Legal (MVP)")
        worker_name = st.text_input("Nombre del Trabajador")
        start_date = st.date_input("Fecha de Ingreso")
        end_date = st.date_input("Fecha de Salida")
        daily_salary = st.number_input(
            "Salario Diario",
            min_value=0.0,
            step=1.0,
            format="%.2f",
        )
        submitted = st.form_submit_button("Calcular Liquidación")

    if submitted:
        payload = LegalTestPayload(
            fecha_ingreso=start_date,
            fecha_salida=end_date,
            salario_diario=float(daily_salary),
        )
        with st.spinner("Calculando..."):
            try:
                data = call_legal_logic(payload)
            except requests.RequestException as exc:
                st.error(f"Error al contactar con el backend: {exc}")
            else:
                render_metrics(data)
                st.json(data)


if __name__ == "__main__":
    main()
