# -*- coding: utf-8 -*-
"""Pantalla final · Gracias + principal preocupación + comentario."""
from __future__ import annotations

import streamlit as st

import config
from modules import experiment, state, ui


def _finish(sid: str) -> None:
    ss = st.session_state
    experiment.complete_session(sid, ss.get("w_concern"), ss.get("w_comment", ""))
    ss.p_finished = True


def render() -> None:
    ss = st.session_state
    sid = state.current_session()

    if ss.get("p_finished"):
        ui.html(f'<div class="page-title" style="text-align:center;margin-top:2rem"><h1>Gracias por probar {config.APP_NAME_TITLE}.</h1>'
                '<p style="margin:.6rem auto 0 auto">Tu experiencia quedó registrada. Puedes avisar a quien dirige la prueba.</p></div>')
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            st.button("Volver al inicio", key="fin_home", type="primary", on_click=state.end_participant, width="stretch")
        return

    if sid is None:
        state.go("home")
        st.rerun()

    ui.stepper("finish")
    ui.page_title(f"Gracias por probar {config.APP_NAME_TITLE}.",
                  "Una última pregunta, y terminamos.")
    st.radio("¿Qué sería lo que más te preocuparía antes de implementar esta solución?",
             config.CONCERN_OPTIONS, index=None, key="w_concern", horizontal=True)
    st.text_area("¿Quieres agregar algo más? (opcional)", key="w_comment", height=110,
                 placeholder="Comentarios, dudas o ideas")
    st.button("Finalizar", key="fin_go", type="primary", on_click=_finish, args=(sid,))
    ui.footer()
