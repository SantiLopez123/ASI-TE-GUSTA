# -*- coding: utf-8 -*-
"""Modo investigador · Sondeo de precio (Sprint 1 y 2): cuánto pagarían los restaurantes y precio ajustado."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import config
from modules import settings, survey, ui, utils


def _apply(rec) -> None:
    settings.set_economic("monthly_price", rec.mensual_sugerido)
    settings.set_economic("token_price", rec.token_sugerido)
    st.session_state.r_flash = ("ok", f"Precios ajustados: mensualidad {utils.fmt_cop(rec.mensual_sugerido)} y token {utils.fmt_cop(rec.token_sugerido)}.")


def render() -> None:
    try:
        df = survey.load()
    except (OSError, ValueError):
        ui.show_notice("No se encontró el archivo del sondeo (<code>data/sondeo_precio.csv</code>).", "err")
        return
    rec = survey.recommend(df)

    ui.section_head("Sondeo de disposición a pagar · Sprint 1 y 2")
    ui.html('<p class="muted small" style="margin:0 0 .6rem 0">Pregunta central: <b>¿cuánto pagarías al mes por «Así te gusta»?</b> y '
            '<b>¿cuánto pagarías por cada cliente reconocido (token)?</b> Respuestas de referencia preparadas por el equipo con '
            'restaurantes de Medellín; el archivo <code>data/sondeo_precio.csv</code> se amplía con cada entrevista.</p>')

    cols = st.columns(4)
    cards = [
        ("Restaurantes consultados", str(rec.n), f"Promedio {utils.fmt_int(rec.clientes_promedio)} clientes frecuentes/mes"),
        ("Pagarían al mes (promedio)", ui.cop(rec.mensual_promedio), f"Mediana {ui.cop(rec.mensual_mediana)} · rango {ui.cop(rec.mensual_min)}–{ui.cop(rec.mensual_max)}"),
        ("Pagarían por token (promedio)", ui.cop(rec.token_promedio), f"Mediana {ui.cop(rec.token_mediana)} · rango {ui.cop(rec.token_min)}–{ui.cop(rec.token_max)}"),
        ("Prefieren tokens · piden piloto", f"{rec.pct_tokens:.0f} % · {rec.pct_piloto:.0f} %", "Declarado en el sondeo"),
    ]
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            ui.html(ui.kpi(label, value, sub))

    ui.section_head("Precio ajustado con el promedio")
    a, b, c = st.columns(3)
    with a:
        ui.html(ui.kpi("Mensualidad sugerida", ui.cop(rec.mensual_sugerido), f"Base del experimento {ui.cop(config.MONTHLY_PRICE)} · promedio redondeado a $5.000"))
    with b:
        ui.html(ui.kpi("Precio por token sugerido", ui.cop(rec.token_sugerido), f"Base del experimento {ui.cop(config.TOKEN_PRICE)} · promedio redondeado a $50"))
    with c:
        ui.html(ui.kpi("Nuevo punto de equilibrio", f"{utils.fmt_int(rec.equilibrio)}", f"reconocimientos al mes (antes {utils.fmt_int(config.MONTHLY_PRICE / config.TOKEN_PRICE)})"))
    ui.html(ui.notice(
        f"Con el precio sugerido, un restaurante promedio ({utils.fmt_int(rec.clientes_promedio)} clientes/mes) pagaría "
        f"<b>{ui.cop(rec.ingreso_tokens_promedio)}</b> al mes por tokens frente a <b>{ui.cop(rec.mensual_sugerido)}</b> de mensualidad. "
        "Los precios actuales del simulador: "
        f"mensualidad <b>{ui.cop(settings.monthly_price())}</b>, token <b>{ui.cop(settings.token_price())}</b>."))
    st.write("")
    st.button("Aplicar precios sugeridos al simulador", key="r_apply_survey", type="primary", on_click=_apply, args=(rec,))

    ui.section_head("Respuestas del sondeo")
    view = df.copy()
    view["pagaria_mensual_cop"] = view["pagaria_mensual_cop"].map(utils.fmt_cop)
    view["pagaria_token_cop"] = view["pagaria_token_cop"].map(utils.fmt_cop)
    st.dataframe(view.drop(columns=["id"]), hide_index=True, width="stretch", column_config={
        "nombre": "Nombre", "municipio": "Municipio", "clientes_frecuentes_mes": "Clientes/mes",
        "pagaria_mensual_cop": "Pagaría al mes", "pagaria_token_cop": "Pagaría por token", "modelo_preferido": "Prefiere",
        "pediria_piloto": "Piloto", "comentario": st.column_config.TextColumn("Comentario", width="large")})

    st.markdown("**Disposición a pagar por restaurante**")
    fig = go.Figure()
    fig.add_bar(x=df["nombre"], y=df["pagaria_mensual_cop"], name="Pagaría al mes", marker_color="#5B2BB0")
    fig.add_hline(y=rec.mensual_promedio, line=dict(color="#2B1058", dash="dash"),
                  annotation_text=f"Promedio {utils.fmt_cop(rec.mensual_promedio)}", annotation_position="top left")
    fig.update_layout(height=320, margin=dict(l=8, r=8, t=20, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1EBFC"), separators=",.",
                      font=dict(family="Segoe UI, system-ui", size=12), showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    ui.section_head("Qué pagaría cada restaurante con el precio ajustado")
    pr = survey.per_restaurant(df, rec)
    for k in ("costo_tokens", "costo_mensualidad"):
        pr[k] = pr[k].map(utils.fmt_cop)
    st.dataframe(pr, hide_index=True, width="stretch", column_config={
        "nombre": "Nombre", "municipio": "Municipio", "clientes_frecuentes_mes": "Clientes/mes",
        "modelo_preferido": "Prefiere", "costo_tokens": "Costo con tokens", "costo_mensualidad": "Costo mensualidad",
        "mas_economico": "Le sale más barato"})
    st.download_button("Descargar respuestas del sondeo (CSV)", data=survey.SURVEY_CSV.read_bytes(),
                       file_name="asi_te_gusta_sondeo_precio.csv", mime="text/csv", key="dl_survey")
