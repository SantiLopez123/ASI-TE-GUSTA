# -*- coding: utf-8 -*-
"""Estado de navegación y sesión experimental (Streamlit session_state).

* La página actual y la sesión se reflejan en la URL (?p=...&s=EXP-0001) para
  que recargar el navegador no pierda al participante.
* Todo lo que pertenece a UN participante usa claves `p_*` / `w_*`; al terminar
  o al preparar una nueva demostración se borran de golpe.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

import config
from modules import demo, experiment

PAGES = ("home", "register", "recognition", "dashboard", "simulator",
         "decision", "pilot", "finish", "researcher")

NAV_ITEMS = [
    ("home", "Inicio"),
    ("register", "Registrar cliente"),
    ("recognition", "Reconocer cliente"),
    ("dashboard", "Panel"),
    ("simulator", "Simulador de costos"),
]

GUIDED_STEPS = [
    ("recognition", "Reconocer"),
    ("dashboard", "Panel"),
    ("simulator", "Simulador"),
    ("decision", "Decisión"),
    ("pilot", "Piloto"),
    ("finish", "Cierre"),
]

# Páginas que no necesitan sesión experimental
NO_SESSION_PAGES = {"home", "register", "researcher"}


def init() -> None:
    ss = st.session_state
    if ss.get("_initialized"):
        return
    ss._initialized = True
    ss.page = "home"
    ss.exp_session = None
    ss.researcher_ok = False
    ss.last_logged_page = None

    # Restaurar desde la URL (recarga del navegador)
    sid = st.query_params.get("s")
    page = st.query_params.get("p")
    if sid and experiment.is_active(sid):
        ss.exp_session = sid
        if page in PAGES and page != "researcher":
            ss.page = page


def sync_query_params() -> None:
    ss = st.session_state
    params = st.query_params
    page = ss.page if ss.page != "researcher" else None
    if page and page != "home":
        if params.get("p") != page:
            params["p"] = page
    elif "p" in params:
        del params["p"]
    if ss.exp_session:
        if params.get("s") != ss.exp_session:
            params["s"] = ss.exp_session
    elif "s" in params:
        del params["s"]


def go(page: str) -> None:
    """Callback de navegación (se ejecuta antes de volver a dibujar la página)."""
    if page in PAGES:
        st.session_state.page = page


def open_survey() -> None:
    """Atajo al Modo investigador con la pestaña «Sondeo de precio» abierta (pide la contraseña si hace falta)."""
    st.session_state.r_open_survey = True
    st.session_state.page = "researcher"


def current_session() -> Optional[str]:
    """Sesión activa de este navegador, o None si ya no existe / fue cerrada."""
    ss = st.session_state
    sid = ss.get("exp_session")
    if sid and not experiment.is_active(sid):
        ss.exp_session = None
        sid = None
    return sid


def ensure_session() -> str:
    ss = st.session_state
    sid = current_session()
    if sid is None:
        if config.AUTO_RESET_ON_NEW_SESSION:
            demo.reset_demo_state()
        sid = experiment.start_session()
        ss.exp_session = sid
        ss.last_logged_page = None
    return sid


def clear_participant_state() -> None:
    ss = st.session_state
    for key in list(ss.keys()):
        if key.startswith(("p_", "w_")):
            del ss[key]
    ss.exp_session = None
    ss.last_logged_page = None


def start_experience() -> None:
    """Botón «Iniciar experiencia»: crea (o retoma) la sesión y salta a Reconocer."""
    ss = st.session_state
    existing = current_session()
    if existing is not None:
        ss.page = ss.get("p_resume_page", "recognition")
        return
    clear_participant_state()
    sid = ensure_session()
    experiment.log_event(sid, "HOME_VIEWED", "home")
    ss.page = "recognition"


def end_participant() -> None:
    """Termina la atención al participante actual y vuelve al inicio."""
    clear_participant_state()
    st.session_state.page = "home"


def track_page_view(page: str) -> None:
    """Registra PAGE_VIEWED sólo cuando cambia de página (no en cada rerun)."""
    ss = st.session_state
    sid = current_session()
    if page in NO_SESSION_PAGES or sid is None:
        return
    if ss.get("last_logged_page") == page:
        return
    ss.last_logged_page = page
    experiment.log_event(sid, "PAGE_VIEWED", page)
    if page == "simulator":
        experiment.log_event(sid, "SIMULATOR_OPENED", page)
    if page in {g for g, _ in GUIDED_STEPS}:
        ss.p_resume_page = page


def choice_order(session_id: str) -> str:
    """Orden de los botones de decisión (A a la izquierda, B a la derecha por defecto)."""
    if config.RANDOMIZE_CHOICE_ORDER:
        try:
            n = int(session_id.split("-")[1])
        except (IndexError, ValueError):
            n = 1
        return "TOKENS_FIRST" if n % 2 == 0 else "MENSUALIDAD_FIRST"
    return "MENSUALIDAD_FIRST"     # = mismo orden que Plan A / Plan B del simulador
