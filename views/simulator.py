# -*- coding: utf-8 -*-
"""Pantalla · Simulador económico: mensualidad fija (Plan A) vs. pago por tokens (Plan B).

Neutralidad: ambos planes usan exactamente el mismo diseño, tamaño y jerarquía,
no hay valor por defecto y la decisión NO se toma aquí.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import config
from modules import experiment, settings, simulator, state, ui, utils

DEEP, MID, LINE = "#2B1058", "#8B5CF6", "#E4DAF6"


def _set_customers(value: int) -> None:
    st.session_state.w_sim_customers = value


def _plan_card(label: str, name: str, price_html: str, rule: str, cost_value: str, cost_sub: str) -> str:
    return (f'<div class="plan"><div class="plan-label">{label}</div><div class="plan-name">{name}</div>'
            f'<div class="plan-price">{price_html}</div><div class="plan-rule">{rule}</div>'
            f'<div class="plan-cost"><div class="k">Costo mensual con tu volumen</div>'
            f'<div class="v">{cost_value}</div><div class="s">{cost_sub}</div></div></div>')


def _chart(comp: simulator.Comparison | None, mp: int, tp: int) -> go.Figure:
    be = simulator.breakeven(mp, tp)
    user_x = comp.recognitions if comp else 0
    x_max = int(max((be * 2) if be else 1000, user_x * 1.4, 200))
    rows = simulator.cost_curve(mp, tp, x_max)
    xs = [r["reconocimientos"] for r in rows]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=[r["mensualidad"] for r in rows], name="Plan A · Mensualidad fija",
                    line=dict(color=DEEP, width=3), hovertemplate="%{y:$,.0f}")
    fig.add_scatter(x=xs, y=[r["tokens"] for r in rows], name="Plan B · Pago por tokens",
                    line=dict(color=MID, width=3), hovertemplate="%{y:$,.0f}")
    if be and be <= x_max:
        fig.add_scatter(x=[be], y=[mp], mode="markers", name="Punto de equilibrio", hoverinfo="skip",
                        marker=dict(size=11, color="white", line=dict(color=DEEP, width=2.5)))
        fig.add_annotation(x=be, y=mp, text=f"Equilibrio ≈ {round(be):,}".replace(",", "."), showarrow=True,
                           arrowhead=0, ay=-34, ax=0, font=dict(size=12, color=DEEP), bgcolor="white",
                           bordercolor=LINE, borderpad=4)
    if comp is not None:
        fig.add_vline(x=user_x, line=dict(color="#6B6485", width=1.5, dash="dash"))
        fig.add_annotation(x=user_x, y=1, yref="paper", text=f"Tu volumen: {user_x:,}".replace(",", "."),
                           showarrow=False, yanchor="bottom", font=dict(size=12, color="#4B4565"))
    fig.update_layout(
        height=340, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, system-ui, sans-serif", color="#1D0F3A", size=13), separators=",.",
        hovermode="x unified", legend=dict(orientation="h", y=-.3, x=0),
        xaxis=dict(title="Reconocimientos (tokens) por mes", gridcolor="#F1EBFC", zeroline=False),
        yaxis=dict(title="Costo mensual (COP)", gridcolor="#F1EBFC", zeroline=False, tickprefix="$", tickformat=",.0f"),
    )
    return fig


def render() -> None:
    ss = st.session_state
    sid = state.current_session()
    if sid:
        ui.stepper("simulator")
    ui.page_title("¿Qué modelo funciona mejor para tu restaurante?",
                  "Es la misma herramienta con dos formas de pago. Escribe cuántos clientes frecuentes recibes al mes y compara.")

    mp, tp = settings.monthly_price(), settings.token_price()

    # ------------------------------------------------------------ entrada
    box = st.container(border=True)
    with box:
        customers_n = st.number_input("¿Cuántos clientes frecuentes recibe aproximadamente cada mes?",
                                      min_value=0, max_value=config.SIMULATOR_MAX_CUSTOMERS, value=None, step=10,
                                      placeholder="Escribe un número", key="w_sim_customers")
        ui.html('<p class="small muted" style="margin:.1rem 0 .4rem 0">O elige un ejemplo:</p>')
        cols = st.columns(len(config.PRESET_VOLUMES))
        for col, v in zip(cols, config.PRESET_VOLUMES):
            with col:
                st.button(utils.fmt_int(v), key=f"preset_{v}", on_click=_set_customers, args=(v,), width="stretch")
        with st.expander("Ajustar visitas por cliente (opcional)"):
            visits = st.number_input("Visitas de cada cliente al mes", min_value=0.0,
                                     max_value=float(config.SIMULATOR_MAX_VISITS_PER_CUSTOMER), value=1.0, step=0.5,
                                     key="w_sim_visits", help="Cada visita es un reconocimiento. Por defecto, 1 visita al mes por cliente.")

    comp = None
    if customers_n is not None:
        try:
            comp = simulator.compare(customers_n, visits, mp, tp)
        except ValueError as exc:
            ui.show_notice(utils.esc(str(exc)), "err")
        else:
            key = (comp.customers, comp.visits_per_customer)
            if sid and ss.get("p_sim_logged") != key:
                experiment.record_simulation(sid, comp.customers, comp.visits_per_customer)
                ss.p_sim_logged = key
    else:
        ui.show_notice("Escribe un número (o elige un ejemplo) para ver cuánto costaría cada modelo con tu volumen.", "info")

    # ------------------------------------------------------------ planes (idénticos en forma)
    st.write("")
    a, b = st.columns(2, gap="large")
    if comp is not None:
        detail = (f"{utils.fmt_int(comp.customers)} clientes × {str(comp.visits_per_customer).rstrip('0').rstrip('.')} visitas = "
                  f"{utils.fmt_int(comp.recognitions)} reconocimientos") if comp.visits_per_customer != 1 else \
                 f"{utils.fmt_int(comp.recognitions)} reconocimientos al mes"
        a_cost, a_sub = ui.cop(comp.monthly_cost), "Mismo valor sin importar el volumen"
        b_cost, b_sub = ui.cop(comp.token_cost), f"{utils.fmt_int(comp.recognitions)} tokens × {ui.cop(tp)}"
    else:
        detail, a_cost, a_sub, b_cost, b_sub = "", "—", "Escribe tu volumen", "—", "Escribe tu volumen"
    with a:
        ui.html(_plan_card("Plan A", "Mensualidad fija", f'{ui.cop(mp)} <small>{config.CURRENCY} / mes</small>',
                           "Un valor fijo cada mes, con reconocimientos ilimitados.", a_cost, a_sub))
    with b:
        ui.html(_plan_card("Plan B", "Pago por tokens", f'{ui.cop(tp)} <small>{config.CURRENCY} / token</small>',
                           "Un valor por cada reconocimiento: 1 reconocimiento = 1 token.", b_cost, b_sub))

    # ------------------------------------------------------------ comparación objetiva
    if comp is not None:
        if comp.cheaper == "IGUAL":
            headline = "Con este volumen ambos modelos cuestan lo mismo."
            diff = ""
        else:
            winner = simulator.MODEL_LABELS[comp.cheaper]
            headline = f"Con este volumen, la opción más económica sería: <b>{winner}</b>."
            diff = f" Diferencia estimada: <b>{ui.cop(comp.difference)}</b> al mes."
        ui.html(f'<div class="verdict"><div class="big">{headline}{diff}</div>'
                f'<p class="muted small" style="margin:.4rem 0 0 0">{detail}</p></div>')
        st.write("")
        ui.html(ui.notice(f"<b>Punto de equilibrio.</b> {utils.esc(simulator.breakeven_sentence(mp, tp))}"))

    ui.section_head("Costo según el número de reconocimientos")
    st.plotly_chart(_chart(comp, mp, tp), width="stretch", config={"displayModeBar": False})
    ui.html('<p class="small muted" style="margin:0">Precios de demostración. Ambos planes incluyen la misma funcionalidad; '
            'solo cambia la forma de pago.</p>')

    # ------------------------------------------------------------ avanzar
    if sid:
        st.write("")
        st.button("Ya revisé los dos modelos: quiero decidir", key="sim_next", type="primary", disabled=comp is None,
                  on_click=state.go, args=("decision",))
        if comp is None:
            st.caption("Escribe tu volumen mensual para continuar.")
    ui.footer()
