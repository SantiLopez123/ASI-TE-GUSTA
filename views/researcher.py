# -*- coding: utf-8 -*-
"""MODO INVESTIGADOR · resultados, exportación y control de la demostración.

Protegido con contraseña DEMO (config.RESEARCHER_PASSWORD). No forma parte del
recorrido del participante y nunca muestra resultados mientras éste participa.
"""
from __future__ import annotations

import hmac

import plotly.graph_objects as go
import streamlit as st

import config
from modules import customers, demo, experiment, settings, simulator, state, tokens, ui, utils


# ---------------------------------------------------------------------------
# Acciones
# ---------------------------------------------------------------------------
def _flash(text: str, kind: str = "ok") -> None:
    st.session_state.r_flash = (kind, text)


def prepare_new_demo() -> None:
    abandoned = experiment.abandon_active_sessions()
    demo.reset_demo_state()
    state.clear_participant_state()
    _flash("Lista para el siguiente participante: sesión activa cerrada"
           + (f" ({abandoned} sin terminar quedó como ABANDONADA)" if abandoned else "")
           + f", saldo restablecido a {utils.fmt_int(settings.initial_token_balance())} tokens, "
             "clientes demo restaurados y cooldown limpio.")


def reset_experiment() -> None:
    experiment.abandon_active_sessions()
    experiment.reset_experiment_data()
    tokens.wipe_ledger_and_visits()
    customers.reset_demo_customers()
    state.clear_participant_state()
    _flash("Datos experimentales restablecidos: sesiones, eventos, reconocimientos y tokens en cero. "
           "Los clientes registrados se conservaron.")


def _quit_app() -> None:
    """Cierra SOLO esta aplicación: lanza `cerrar.pyw` desvinculado (cierra la ventana y detiene el servidor)."""
    try:
        from launcher import appctl
        appctl.spawn_close_detached()
        _flash("Cerrando «Así te gusta»… puedes cerrar esta ventana.")
    except Exception:                                   # noqa: BLE001
        utils.log_exception("cerrar la aplicación desde el modo investigador")
        _flash("No se pudo cerrar automáticamente. Usa el acceso directo «CERRAR ASÍ TE GUSTA» del escritorio.", "err")


def _quit_section() -> None:
    ui.section_head("Cerrar la aplicación")
    ui.html('<p class="muted small" style="margin:0 0 .6rem 0">Cierra la ventana y detiene el servidor de «Así te gusta». '
            'Solo se cierra este programa; no afecta a otras aplicaciones. Para volver a abrirla: acceso directo «ASÍ TE GUSTA» del escritorio.</p>')
    ok_q = st.checkbox("Confirmo que quiero cerrar la aplicación", key="w_r_ok_quit")
    st.button("Cerrar Así te gusta", key="r_quit", disabled=not ok_q, on_click=_quit_app)


def _set_rehearsal() -> None:
    settings.set_rehearsal_mode(bool(st.session_state.get("w_r_rehearsal")))


# ---------------------------------------------------------------------------
# Vista
# ---------------------------------------------------------------------------
def render() -> None:
    ss = st.session_state
    if not ss.get("researcher_ok"):
        _login()
        return

    c1, c2 = st.columns([4, 1.2], vertical_alignment="center")
    with c1:
        ui.html(f'<div class="brand">{ui._logo_svg()}<div><div class="brand-name">MODO INVESTIGADOR</div>'
                '<div class="brand-sub">Solo para el equipo · no mostrar al participante</div></div></div>')
    with c2:
        st.button("Salir al inicio", key="r_exit", on_click=_logout, width="stretch")

    if ss.get("r_flash"):
        kind, text = ss.pop("r_flash")
        ui.show_notice(utils.esc(text), kind)

    f1, f2, f3 = st.columns([1, 1, 1.4], vertical_alignment="center")
    with f1:
        inc_inc = st.checkbox("Incluir sesiones incompletas", key="w_r_inc")
    with f2:
        inc_test = st.checkbox("Incluir sesiones de ensayo", key="w_r_test")
    with f3:
        st.toggle("Modo ensayo (las nuevas sesiones se marcan PRB)", value=settings.rehearsal_mode(),
                  key="w_r_rehearsal", on_change=_set_rehearsal)

    t_res, t_ses, t_ev, t_sur, t_cfg, t_demo = st.tabs(
        ["Resumen", "Sesiones", "Eventos", "Sondeo de precio", "Parámetros", "Demostración"],
        default="Sondeo de precio" if ss.get("r_open_survey") else None)
    with t_res:
        _tab_summary(inc_inc, inc_test)
    with t_ses:
        _tab_sessions(inc_inc, inc_test)
    with t_ev:
        _tab_events(inc_inc, inc_test)
    with t_cfg:
        _tab_settings()
    with t_sur:
        from views import survey_tab
        survey_tab.render()
    with t_demo:
        _tab_demo()


def _login() -> None:
    ui.page_title("Modo investigador", "Acceso restringido al equipo."
                  + (" Al entrar se abre el sondeo de precio." if st.session_state.get("r_open_survey") else ""))
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("researcher_login"):
            pw = st.text_input("Contraseña", type="password", placeholder="Contraseña del equipo")
            ok = st.form_submit_button("Entrar", type="primary", width="stretch")
        if ok:
            if hmac.compare_digest(pw.encode("utf-8"), settings_password().encode("utf-8")):
                st.session_state.researcher_ok = True
                st.rerun()
            else:
                ui.show_notice("Contraseña incorrecta.", "err")
        st.button("Volver al inicio", key="r_back", on_click=_logout, width="stretch")


def settings_password() -> str:
    return config.RESEARCHER_PASSWORD


def _logout() -> None:
    st.session_state.researcher_ok = False
    st.session_state.r_open_survey = False
    st.session_state.page = "home"


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
def _pct(p) -> str:
    return "—" if p is None else f"{p:.0f} %"


def _tab_summary(inc_inc: bool, inc_test: bool) -> None:
    m = experiment.metrics(inc_inc, inc_test)
    total = m["total"]

    cols = st.columns(4)
    cards = [
        ("Total participantes", utils.fmt_int(total), f'Meta: {m["target"]} · {m["incomplete"]} incompletas · {m["test_sessions"]} de ensayo'),
        ("Tokens", f'{m["tokens_n"]} / {total}', f'{_pct(m["tokens_pct"])} eligió pago por tokens'),
        ("Mensualidad", f'{m["monthly_n"]} / {total}', f'{_pct(m["monthly_pct"])} eligió mensualidad fija'),
        ("Solicitud de piloto", f'{m["pilot_n"]} / {total}', f'{_pct(m["pilot_pct"])} solicitó prueba piloto'),
    ]
    if total == 0:                                           # sin datos reales: nada de «— eligió…»
        cards = [(label, value, "Sin datos todavía" if i else sub) for i, (label, value, sub) in enumerate(cards)]
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            ui.html(ui.kpi(label, value, sub))

    ui.section_head("Criterios de éxito predefinidos")
    tok_pct, pil_pct = 100 * m["token_threshold"] / m["target"], 100 * m["pilot_threshold"] / m["target"]
    status = "Pendiente de ejecución" if total < m["target"] else f"Muestra completa (n = {total}) · interpretación a cargo del equipo"
    rows = [
        ("Métrica principal · preferencia por tokens", f'≥ {m["token_threshold"]} de {m["target"]} (≥ {tok_pct:.0f} %)',
         f'{m["tokens_n"]} / {total} ({_pct(m["tokens_pct"])})'),
        ("Métrica secundaria · solicitud de piloto", f'≥ {m["pilot_threshold"]} de {m["target"]} (≥ {pil_pct:.0f} %)',
         f'{m["pilot_n"]} / {total} ({_pct(m["pilot_pct"])})'),
    ]
    body = "".join(
        f'<tr><td style="padding:.5rem .6rem"><b>{a}</b></td><td style="padding:.5rem .6rem">{b}</td>'
        f'<td style="padding:.5rem .6rem">{c}</td><td style="padding:.5rem .6rem">{ui.tag(status, "neutral")}</td></tr>'
        for a, b, c in rows)
    ui.html('<div class="card flat"><table style="width:100%;border-collapse:collapse;font-size:.93rem">'
            '<tr style="text-align:left;color:var(--muted);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase">'
            '<th style="padding:.3rem .6rem">Métrica</th><th style="padding:.3rem .6rem">Criterio definido</th>'
            f'<th style="padding:.3rem .6rem">Observado</th><th style="padding:.3rem .6rem">Estado</th></tr>{body}</table></div>')
    ui.html('<p class="small muted" style="margin:.5rem 0 0 0"><b>Criterio de éxito definido para futura ejecución.</b> '
            'Este panel no declara la hipótesis como validada ni refutada; sólo muestra los datos observados.</p>')

    ui.section_head("Principales objeciones")
    if m["concerns"]:
        labels, values = zip(*reversed(m["concerns"]))
        fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color="#5B2BB0",
                               hovertemplate="%{y}: %{x}<extra></extra>"))
        fig.update_layout(height=max(180, 38 * len(labels) + 40), margin=dict(l=8, r=8, t=8, b=8), bargap=0.45,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis=dict(dtick=1, gridcolor="#F1EBFC", range=[0, max(3, max(values))]),
                          font=dict(family="Segoe UI, system-ui", size=13))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        ui.html('<div class="card flat muted small">Aún no hay objeciones registradas.</div>')

    d1, d2 = st.columns(2)
    with d1:
        ui.html(ui.kpi("Duración promedio", utils.fmt_duration(m["avg_duration"]), "De sesiones completas"))
    with d2:
        ui.html(ui.kpi("Clientes/mes estimados (promedio)",
                       "—" if m["avg_customers"] is None else utils.fmt_int(m["avg_customers"]), "Dato declarado por los participantes"))


def _download(path, label: str, key: str) -> None:
    st.download_button(label, data=path.read_bytes(), file_name=path.name, mime="text/csv", key=key, width="stretch")


def _tab_sessions(inc_inc: bool, inc_test: bool) -> None:
    df = experiment.sessions_df(inc_inc, inc_test)
    ui.section_head("Tabla de sesiones")
    if df.empty:
        ui.html('<div class="card flat muted small">Todavía no hay sesiones con estos filtros.</div>')
    else:
        view = df.copy()
        view["is_test"] = view["is_test"].map({1: "Ensayo", 0: "Real"})
        view["status"] = view["status"].map({"COMPLETED": "Completa", "IN_PROGRESS": "En curso", "ABANDONED": "Abandonada"}).fillna(view["status"])
        view["selected_model"] = view["selected_model"].map({"TOKENS": "Tokens", "MENSUALIDAD": "Mensualidad"}).fillna("—")
        view["pilot_requested"] = view["pilot_requested"].map({1: "Sí", 0: "No"}).fillna("—")
        view["main_concern"] = view["main_concern"].fillna("—")
        for money in ("monthly_fixed_cost", "estimated_token_cost"):
            view[money] = view[money].map(lambda v: "—" if v != v or v is None else utils.fmt_cop(v))
        cols = ["session_id", "status", "is_test", "date", "duration_seconds", "estimated_monthly_customers",
                "monthly_fixed_cost", "estimated_token_cost", "selected_model", "pilot_requested", "main_concern"]
        st.dataframe(view[cols], hide_index=True, width="stretch", column_config={
            "session_id": st.column_config.TextColumn("Sesión", width="small"),
            "status": st.column_config.TextColumn("Estado", width="small"),
            "is_test": st.column_config.TextColumn("Tipo", width="small"),
            "date": st.column_config.TextColumn("Fecha", width="small"),
            "duration_seconds": st.column_config.NumberColumn("Duración (s)", width="small"),
            "estimated_monthly_customers": st.column_config.NumberColumn("Clientes/mes", width="small"),
            "monthly_fixed_cost": st.column_config.TextColumn("Mensualidad", width="small"),
            "estimated_token_cost": st.column_config.TextColumn("Costo tokens", width="small"),
            "selected_model": st.column_config.TextColumn("Modelo", width="small"),
            "pilot_requested": st.column_config.TextColumn("Piloto", width="small"),
            "main_concern": st.column_config.TextColumn("Objeción principal", width="medium"),
        })
        with st.expander("Ver todas las columnas (tal como se exportan)"):
            st.dataframe(df, hide_index=True, width="stretch")
    ui.section_head("Exportar resultados del experimento")
    std = experiment.export_sessions_csv(inc_inc, inc_test)
    xl = experiment.export_sessions_csv(inc_inc, inc_test, excel_format=True)
    c1, c2 = st.columns(2)
    with c1:
        _download(std, "Exportar resultados del experimento (CSV)", "dl_sessions")
    with c2:
        _download(xl, "CSV para Excel en español (separador «;»)", "dl_sessions_xl")
    ui.html(f'<p class="small muted">También quedó guardado en <code>{utils.esc(str(std.parent))}</code></p>')


def _tab_events(inc_inc: bool, inc_test: bool) -> None:
    df = experiment.events_df(inc_inc, inc_test)
    ui.section_head("Eventos del recorrido")
    if df.empty:
        ui.html('<div class="card flat muted small">Todavía no hay eventos con estos filtros.</div>')
    else:
        sid = st.selectbox("Filtrar por sesión", ["Todas"] + sorted(df["session_id"].unique()), key="w_r_ev_sid")
        view = df if sid == "Todas" else df[df["session_id"] == sid]
        st.dataframe(view.drop(columns=["id"]), hide_index=True, width="stretch")
    ui.section_head("Exportar eventos")
    std = experiment.export_events_csv(inc_inc, inc_test)
    xl = experiment.export_events_csv(inc_inc, inc_test, excel_format=True)
    c1, c2 = st.columns(2)
    with c1:
        _download(std, "Exportar eventos (CSV)", "dl_events")
    with c2:
        _download(xl, "CSV para Excel en español (separador «;»)", "dl_events_xl")


def _tab_settings() -> None:
    ui.section_head("Parámetros económicos")
    ui.show_notice("Cambiar precios en medio del experimento afecta la comparabilidad. Cada sesión guarda los precios que vio.", "warn")
    st.write("")
    cur = settings.economic_snapshot()
    with st.form("econ_form"):
        c1, c2 = st.columns(2)
        with c1:
            mp = st.number_input("Mensualidad fija (COP / mes)", 0, 100_000_000, cur["monthly_price"], step=10_000)
            ib = st.number_input("Saldo inicial de tokens", 0, 10_000_000, cur["initial_token_balance"], step=50)
        with c2:
            tp = st.number_input("Precio de 1 token (COP)", 0, 10_000_000, cur["token_price"], step=50)
            cd = st.number_input("Cooldown por cliente (minutos)", 0, 1440, cur["token_cooldown_minutes"], step=5,
                                 help="1 token por cliente cada N minutos. 0 = cobra en cada detección.")
        saved = st.form_submit_button("Guardar parámetros", type="primary")
    if saved:
        settings.set_economic("monthly_price", mp)
        settings.set_economic("token_price", tp)
        settings.set_economic("initial_token_balance", ib)
        settings.set_economic("token_cooldown_minutes", cd)
        _flash("Parámetros guardados.")
        st.rerun()
    be = simulator.breakeven(settings.monthly_price(), settings.token_price())
    ui.html(f'<p class="small muted">Punto de equilibrio actual: {"—" if be is None else utils.fmt_int(round(be))} reconocimientos/mes · '
            f'Valores de fábrica en <code>config.py</code>.</p>')
    st.button("Restaurar valores de fábrica", key="r_econ_reset", on_click=lambda: (settings.reset_economic(), _flash("Valores de fábrica restaurados.")))

    ui.section_head("Saldo de tokens")
    w1, w2, w3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    with w1:
        ui.html(ui.wallet(tokens.get_balance()))
    with w2:
        amount = st.number_input("Recargar tokens", 1, 100_000, 100, step=50, key="w_r_topup")
    with w3:
        st.button("Recargar", key="r_topup", on_click=lambda: (tokens.top_up(int(amount), "Recarga (investigador)"), _flash("Saldo recargado.")), width="stretch")
    st.button("Poner el saldo en cero (probar «sin saldo»)", key="r_zero",
              on_click=lambda: (tokens.reset_balance(0), _flash("Saldo en cero. Un reconocimiento ahora mostrará «Saldo agotado».", "warn")))


def _tab_demo() -> None:
    ui.section_head("Preparar nueva demostración")
    ui.html('<p class="muted small" style="margin:0 0 .6rem 0">Mantiene los clientes DEMO (restaura sus visitas), cierra la sesión activa '
            '(si quedó sin terminar se marca ABANDONADA), restablece los tokens y limpia el cooldown.</p>')
    st.button("Preparar nueva demostración", key="r_prepare", type="primary", on_click=prepare_new_demo)

    ui.section_head("Sesiones de ejemplo")
    ui.html('<p class="muted small" style="margin:0 0 .6rem 0">Crea 10 sesiones SINTÉTICAS marcadas como ensayo (PRB-xxxx) para ver '
            'el panel con datos. No cuentan en las métricas salvo que actives «Incluir sesiones de ensayo».</p>')
    e1, e2 = st.columns(2)
    with e1:
        st.button("Generar 10 sesiones de ejemplo", key="r_gen", width="stretch",
                  on_click=lambda: (experiment.generate_sample_sessions(10), _flash("10 sesiones de ejemplo creadas (PRB).")))
    with e2:
        st.button("Eliminar sesiones de ensayo", key="r_deltest", width="stretch",
                  on_click=lambda: _flash(f"{experiment.delete_test_sessions()} sesiones de ensayo eliminadas."))

    ui.section_head("Datos personales y biométricos")
    ui.html(f'<p class="muted small" style="margin:0 0 .6rem 0">Clientes registrados con rostro: <b>{customers.count_enrolled_faces()}</b> · '
            f'Clientes con registro propio: <b>{customers.count_customers(include_demo=False)}</b></p>')
    b1, b2 = st.columns(2)
    with b1:
        ok_b = st.checkbox("Confirmo eliminar TODOS los datos biométricos", key="w_r_ok_bio")
        st.button("Eliminar datos biométricos", key="r_del_bio", disabled=not ok_b, width="stretch",
                  on_click=lambda: _flash(f"Se eliminaron {customers.delete_all_biometrics()} huellas faciales."))
    with b2:
        ok_c = st.checkbox("Confirmo eliminar TODOS los clientes registrados (no demo)", key="w_r_ok_cust")
        st.button("Eliminar clientes registrados", key="r_del_cust", disabled=not ok_c, width="stretch",
                  on_click=lambda: _flash(f"Se eliminaron {customers.delete_registered_customers()} perfiles."))

    if not config.WEB_MODE:                                 # en la web no se apaga el servidor desde la app
        _quit_section()

    ui.section_head("Zona de riesgo")
    ui.show_notice("<b>Restablecer datos experimentales</b> borra TODAS las sesiones y eventos (también los reales) y reinicia la numeración "
                   "(EXP-0001). Exporta los CSV antes.", "err")
    st.write("")
    phrase = st.text_input("Escribe BORRAR para confirmar", key="w_r_reset_phrase")
    st.button("Restablecer datos experimentales", key="r_reset_all", disabled=phrase.strip().upper() != "BORRAR",
              on_click=reset_experiment)
