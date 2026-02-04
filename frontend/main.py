"""Minimal Streamlit application for Evidence Crusher.

Esta aplicación solo realiza un ping al Backend para
validar la conexión Frontend -> Backend -> Base de Datos.
"""

from typing import Any, Dict

import os

import requests
import streamlit as st


BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")


def ping_backend() -> Dict[str, Any]:
    """Call the backend ping endpoint and return its JSON response.

    Returns:
        Dict[str, Any]: Parsed JSON response from the backend.

    Raises:
        requests.RequestException: If the request fails.
    """

    response: requests.Response = requests.get(
        f"{BACKEND_URL}/ping",
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    """Entry point for the minimal Streamlit app."""

    st.set_page_config(page_title="Evidence Crusher - Hello World")
    st.title("Evidence Crusher - Hello World")
    st.write(
        "Ping/Pong test entre Frontend, Backend y Base de Datos "
        "a través del endpoint `/ping`."
    )

    if st.button("Ping backend"):
        with st.spinner("Contactando con el backend..."):
            try:
                data: Dict[str, Any] = ping_backend()
            except requests.RequestException as exc:
                st.error(f"Error al contactar con el backend: {exc}")
            else:
                st.success("Conexión exitosa con Backend y Base de Datos.")
                st.json(data)


if __name__ == "__main__":
    main()
