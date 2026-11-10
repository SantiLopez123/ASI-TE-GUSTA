# -*- coding: utf-8 -*-
"""Pantalla 1 · Inicio."""
from __future__ import annotations

import streamlit as st

import config
from modules import analytics, state, ui, utils


def render() -> None:
    active = state.current_session() is not None

    with st.container(key="hero"):
        ui.html(f'<div style="margin-bottom:.2rem">{ui.tag("Prototipo académico · Idear Empresarial", "dark")}</div>')
        ui.html('<div class="hero-title">Reconoce. <em>Personaliza.</em> Fideliza.</div>')
        ui.html('<p class="hero-text">Reconoce a tus clientes frecuentes —con su autorización— y atiéndelos con lo que más '
                'les gusta desde que cruzan la puerta. Tu equipo ve su nombre, sus preferencias y su historial en segundos.</p>')
        ui.html('<div class="hero-role"><b>Imagina que eres el dueño de este restaurante.</b> '
                'Explora la herramienta y decide si la contratarías y bajo qué modalidad.</div>')
        c1, _ = st.columns([1.1, 2.4])
        with c1:
            st.button("Continuar experiencia" if active else "Iniciar experiencia", key="cta_start",
                      type="primary", on_click=state.start_experience, width="stretch")

    tiles = [
        ("user-plus", "Registrar cliente", "Un cliente se registra con su autorización y su rostro.", "register", "Abrir registro"),
        ("scan", "Reconocer cliente", "La cámara identifica a un cliente registrado al entrar.", "recognition", "Abrir reconocimiento"),
        ("chart", "Panel", "Clientes, visitas, tokens usados y cumpleaños próximos.", "dashboard", "Abrir panel"),
        ("calc", "Simulador de costos", "Calcula cuánto costaría según tus clientes al mes.", "simulator", "Abrir simulador"),
    ]
    cols = st.columns(4)
    for col, (ico, title, text, target, btn) in zip(cols, tiles):
        with col:
            ui.html(f'<div class="tile"><div class="ico">{ui.icon(ico)}</div><h4>{title}</h4><p>{text}</p></div>')
            st.button(btn, key=f"tile_{target}", on_click=state.go, args=(target,), width="stretch")

    m = analytics.real_metrics()
    ui.section_head("Así va tu restaurante", ui.TAG_REAL)
    k = st.columns(4)
    items = [
        ("Clientes registrados", utils.fmt_int(m["registered"]),
         f'{m["registered_demo"]} de demostración · {m["registered_real"]} con registro propio'),
        ("Tokens disponibles", utils.fmt_int(m["tokens_available"]), "1 reconocimiento válido = 1 token"),
        ("Reconocimientos hoy", utils.fmt_int(m["recognitions_today"]), "Clientes identificados hoy"),
        ("Cumpleaños próximos", utils.fmt_int(len(m["birthdays"])), f"En los próximos {config.BIRTHDAY_WINDOW_DAYS} días"),
    ]
    for col, (label, value, sub) in zip(k, items):
        with col:
            ui.html(ui.kpi(label, value, sub))

    ui.section_head("Cómo funciona")
    s = st.columns(3)
    steps = [
        ("1 · El cliente autoriza", "Se registra voluntariamente y acepta el uso de su información y su rostro."),
        ("2 · La cámara lo reconoce", "Al entrar, el sistema lo identifica. Los desconocidos aparecen como «Desconocido»."),
        ("3 · Tu equipo lo atiende mejor", "Nombre, plato habitual, preferencias y cumpleaños, al instante."),
    ]
    for col, (t, d) in zip(s, steps):
        with col:
            ui.html(f'<div class="card flat"><h4>{t}</h4><p class="muted small" style="margin:0">{d}</p></div>')

    ui.html(ui.notice(f"<b>Privacidad.</b> {utils.esc(config.ACADEMIC_NOTICE)} "
                      "Nadie es reconocido sin haber dado su consentimiento y puede eliminar sus datos cuando quiera."))
    ui.footer()
