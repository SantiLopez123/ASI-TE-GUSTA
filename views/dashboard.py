# -*- coding: utf-8 -*-
"""Pantalla · Panel del restaurante (lo REAL y lo SIMULADO, claramente separados)."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import config
from modules import analytics, settings, state, ui, utils

P900, P600, P500, L300, L100, INK = "#2B1058", "#5B2BB0", "#7A45D6", "#CDBBF3", "#F1EBFC", "#1D0F3A"


def _style(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, system-ui, sans-serif", color=INK, size=13), showlegend=False,
        hoverlabel=dict(bgcolor="white", font_size=13),
    )
    return fig


def render() -> None:
    if state.current_session():
        ui.stepper("dashboard")
    ui.page_title("Panel del restaurante",
                  "Lo que ves aquí es lo que tu equipo obtiene: a quién reconoce, cuántas visitas genera y cuántos tokens usa.")

    m = analytics.real_metrics()

    # ----------------------------------------------------------- REAL
    ui.section_head("Actividad registrada en esta demostración", ui.TAG_REAL)
    names = ", ".join(utils.esc(utils.first_name(b["name"])) for b in m["birthdays"][:4]) or "Ninguno por ahora"
    row1 = [
        ("Clientes registrados", utils.fmt_int(m["registered"]),
         f'{m["registered_demo"]} de demostración · {m["registered_real"]} con registro propio'),
        ("Reconocimientos del mes", utils.fmt_int(m["recognitions_month"]), "Clientes identificados con cobro"),
        ("Clientes recurrentes", utils.fmt_int(m["recurrent"]), "Reconocidos 2 veces o más"),
        ("Visitas registradas", utils.fmt_int(m["visits"]), f'{m["cooldown_hits"]} detecciones repetidas sin cobro'),
    ]
    row2 = [
        ("Tokens consumidos", utils.fmt_int(m["tokens_consumed"]), "1 por cliente reconocido"),
        ("Tokens disponibles", utils.fmt_int(m["tokens_available"]), "Saldo de la demostración"),
        ("Costo estimado de tokens", ui.cop(m["token_cost"]), f'{utils.fmt_int(m["tokens_consumed"])} × {ui.cop(settings.token_price())} por token'),
        ("Próximos cumpleaños", utils.fmt_int(len(m["birthdays"])), f'En {config.BIRTHDAY_WINDOW_DAYS} días: {names}'),
    ]
    for row in (row1, row2):
        cols = st.columns(4)
        for col, (label, value, sub) in zip(cols, row):
            with col:
                ui.html(ui.kpi(label, value, sub))
        st.write("")

    t1, t2 = st.columns([1.5, 1], gap="large")
    with t1:
        st.markdown("**Últimos reconocimientos**")
        ev = analytics.recent_events()
        if ev.empty:
            ui.html('<div class="card flat muted small">Todavía no hay reconocimientos. Ve a «Reconocer cliente» y simula una entrada.</div>')
        else:
            st.dataframe(ev, hide_index=True, width="stretch")
    with t2:
        st.markdown("**Cumpleaños próximos**")
        if m["birthdays"]:
            rows = "".join(
                f'<div class="cust-tile"><div class="avatar">{utils.esc(utils.initials(b["name"]))}</div><div>'
                f'<div class="nm">{utils.esc(b["name"])}</div><div class="sb">{utils.esc(utils.birthday_text(b["birthday_day"], b["birthday_month"]))} · '
                f'{"hoy" if b["days_until"] == 0 else "en " + str(b["days_until"]) + " días"}</div></div></div>'
                for b in m["birthdays"][:5])
            ui.html(rows)
        else:
            ui.html(f'<div class="card flat muted small">Sin cumpleaños en los próximos {config.BIRTHDAY_WINDOW_DAYS} días.</div>')

    # -------------------------------------------------------- SIMULADO
    sim = analytics.simulated_month()
    ui.section_head("Así se vería un mes de operación", ui.TAG_SIM)
    ui.html(ui.notice("<b>Datos de ejemplo.</b> Estas cifras son simuladas para mostrar el potencial del panel; "
                      "no provienen de ningún restaurante real.", "warn"))
    st.write("")
    sim_row = [
        ("Clientes reconocidos", utils.fmt_int(sim["recognitions"]), "En el mes"),
        ("Clientes recurrentes", utils.fmt_int(sim["recurring"]), f'{round(100 * sim["recurring"] / sim["recognitions"])} % de los reconocidos'),
        ("Tokens utilizados", utils.fmt_int(sim["tokens"]), "1 por reconocimiento"),
        ("Costo de tokens", ui.cop(sim["token_cost"]), f'A {ui.cop(settings.token_price())} por token'),
        ("Ventas asociadas", ui.cop(sim["sales"]), "Dato demostrativo"),
    ]
    cols = st.columns(5)
    for col, (label, value, sub) in zip(cols, sim_row):
        with col:
            ui.html(ui.kpi(label, value, sub, ui.TAG_SIM))

    st.write("")
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        st.markdown("**Reconocimientos por día** · cada uno = 1 token")
        df = sim["series"]
        fig = go.Figure(go.Bar(x=df["fecha"], y=df["reconocimientos"], marker_color=P600,
                               hovertemplate="%{x|%d %b}: %{y} reconocimientos<extra></extra>"))
        fig.update_xaxes(tickformat="%d %b", showgrid=False, linecolor=L300)
        fig.update_yaxes(gridcolor=L100, zeroline=False)
        st.plotly_chart(_style(fig), width="stretch", config={"displayModeBar": False})
    with c2:
        st.markdown("**Clientes recurrentes vs. nuevos**")
        fig2 = go.Figure(go.Pie(labels=["Recurrentes", "Nuevos"], values=[sim["recurring"], sim["new"]], hole=.62,
                                marker=dict(colors=[P900, L300]), textinfo="percent", sort=False,
                                hovertemplate="%{label}: %{value}<extra></extra>"))
        fig2.update_layout(showlegend=True, legend=dict(orientation="h", y=-.05))
        st.plotly_chart(_style(fig2).update_layout(showlegend=True), width="stretch", config={"displayModeBar": False})

    if state.current_session():
        st.write("")
        st.button("Continuar al simulador de costos", key="dash_next", type="primary", on_click=state.go, args=("simulator",))
    ui.footer()
