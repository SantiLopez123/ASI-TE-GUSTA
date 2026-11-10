# -*- coding: utf-8 -*-
"""Pantalla · Decisión del participante. Los dos botones son idénticos y ninguno viene marcado."""
from __future__ import annotations

import streamlit as st

from modules import experiment, simulator, state, ui, utils

LABELS = {simulator.MODEL_TOKENS: "Pago por tokens", simulator.MODEL_MONTHLY: "Mensualidad fija"}


def _choose(model: str) -> None:
    sid = state.current_session()
    if sid:
        experiment.select_model(sid, model, state.choice_order(sid))


def _continue(sid: str) -> None:
    experiment.save_reason(sid, st.session_state.get("w_reason", ""))
    st.session_state.page = "pilot"


def render() -> None:
    sid = state.current_session()
    if sid is None:
        state.go("home")
        st.rerun()
    session = experiment.get_session(sid)

    ui.stepper("decision")
    ui.page_title("¿Qué modelo preferirías para tu restaurante?",
                  "Elige la forma de pago que escogerías para tu negocio.")

    if session["estimated_monthly_customers"] is None:
        ui.show_notice("Antes de decidir, revisa el simulador para comparar ambos modelos con tus clientes.", "info")
        st.button("Ir al simulador de costos", key="dec_to_sim", type="primary", on_click=state.go, args=("simulator",))
        ui.footer()
        return

    # Recordatorio neutral de lo que vio (mismo formato para ambos)
    ui.html(f'<div class="card lav small" style="text-align:center">Con <b>{utils.fmt_int(session["monthly_recognitions"])} reconocimientos al mes</b>: '
            f'Mensualidad fija {ui.cop(session["monthly_fixed_cost"])} · Pago por tokens {ui.cop(session["estimated_token_cost"])}</div>')
    st.write("")

    order = session["choice_order"] or state.choice_order(sid)
    models = ([simulator.MODEL_TOKENS, simulator.MODEL_MONTHLY] if order == "TOKENS_FIRST"
              else [simulator.MODEL_MONTHLY, simulator.MODEL_TOKENS])
    selected = session["selected_model"]

    with st.container(key="choice"):
        cols = st.columns(2, gap="large")
        for col, model in zip(cols, models):
            with col:
                st.button(LABELS[model].upper(), key=f"choose_{model}", width="stretch",
                          type="primary" if selected == model else "secondary",
                          on_click=_choose, args=(model,))

    if selected:
        st.write("")
        ui.show_notice(f"Elegiste: <b>{LABELS[selected]}</b>. Puedes cambiar tu elección antes de continuar.", "ok")
        st.write("")
        st.text_area("¿Qué hizo que eligieras esta opción?", key="w_reason", height=110,
                     value=session["selected_model_reason"] or "", placeholder="Cuéntanos con tus palabras (opcional)")
        st.button("Continuar", key="dec_next", type="primary", on_click=_continue, args=(sid,))
    ui.footer()
