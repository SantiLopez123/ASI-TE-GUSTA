# -*- coding: utf-8 -*-
"""Pantalla · ¿Solicitar prueba piloto? Dos botones idénticos, sin manipulación."""
from __future__ import annotations

import streamlit as st

import config
from modules import experiment, state, ui


def _answer(requested: bool) -> None:
    sid = state.current_session()
    if sid:
        experiment.set_pilot(sid, requested)
    st.session_state.page = "finish"


def render() -> None:
    sid = state.current_session()
    if sid is None:
        state.go("home")
        st.rerun()
    session = experiment.get_session(sid)

    ui.stepper("pilot")
    ui.page_title(f"¿Te interesaría probar «{config.APP_NAME_TITLE}» en tu restaurante?",
                  "Una prueba piloto sería una implementación de prueba en tu restaurante durante un periodo corto.")
    st.write("")
    previous = session["pilot_requested"]
    with st.container(key="choice_pilot"):
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.button("SOLICITAR PRUEBA PILOTO", key="pilot_yes", width="stretch",
                      type="primary" if previous == 1 else "secondary", on_click=_answer, args=(True,))
        with c2:
            st.button("AHORA NO", key="pilot_no", width="stretch",
                      type="primary" if previous == 0 else "secondary", on_click=_answer, args=(False,))
    ui.footer()
