# -*- coding: utf-8 -*-
"""Pantalla · Reconocimiento de clientes (cámara real o simulación con el MISMO flujo)."""
from __future__ import annotations

import hashlib
import time

import cv2
import streamlit as st

import config
from modules import customers, experiment, recognition, settings, state, tokens, ui, utils

MODE_DEMO = "Simular entrada de cliente"
MODE_CAMERA = "Cámara real"


# ---------------------------------------------------------------------------
# Flujo de negocio único (demo y cámara pasan por aquí)
# ---------------------------------------------------------------------------
def register_recognition(customer_id, source: str, confidence=None) -> None:
    """Callback seguro: cualquier fallo se muestra como aviso amable."""
    try:
        res = tokens.process_recognition(customer_id, source=source, confidence=confidence,
                                         session_id=state.current_session())
        st.session_state.p_last_recognition = res.to_dict()
    except Exception:                                   # noqa: BLE001
        utils.log_exception("process_recognition")
        st.session_state.p_last_recognition = {"status": "ERROR"}


def top_up(amount: int) -> None:
    tokens.top_up(amount)
    experiment.log_event(state.current_session(), "TOKENS_TOPPED_UP", "recognition", {"amount": amount})
    st.session_state.p_last_recognition = None


# ---------------------------------------------------------------------------
# Tarjeta de resultado
# ---------------------------------------------------------------------------
def _fact(label: str, value: str, extra_cls: str = "") -> str:
    return f'<div class="fact {extra_cls}"><div class="k">{utils.esc(label)}</div><div class="v">{value}</div></div>'


def _card_html(res: dict) -> str:
    status = res["status"]
    coin = ui.icon("coin")
    created = utils.parse_dt(res["created_at"])

    if status == tokens.OUTCOME_UNKNOWN:
        return (
            '<div class="recog">'
            '<div class="recog-head neutral"><div class="avatar">?</div><div>'
            '<div class="recog-kicker">Persona no registrada</div><div class="recog-name">Desconocido</div>'
            '<div class="recog-meta"><span class="chip">Sin perfil</span></div></div></div>'
            '<div class="recog-body"><div class="fact wide"><div class="v" style="font-size:1.05rem;font-weight:600">'
            'Esta persona no está registrada, así que no se muestra información ni se cobra nada. '
            'Si es un cliente nuevo, invítalo a registrarse con su autorización.</div></div></div>'
            f'<div class="recog-foot none"><div class="token-badge">{ui.icon("shield")} NO SE CONSUMIÓ TOKEN</div>'
            f'<div class="balance">Saldo actual <b>{utils.fmt_int(res["balance_after"])}</b></div></div></div>')

    if status == tokens.OUTCOME_NO_BALANCE:
        return (
            '<div class="recog">'
            '<div class="recog-head warn"><div class="avatar">!</div><div>'
            '<div class="recog-kicker">Cliente identificado</div><div class="recog-name">Saldo de tokens agotado</div>'
            '</div></div>'
            '<div class="recog-body"><div class="fact wide"><div class="v" style="font-size:1.05rem;font-weight:600">'
            'El cliente fue identificado, pero no hay tokens disponibles para mostrar su perfil. '
            'Recarga tokens para continuar.</div></div></div>'
            f'<div class="recog-foot cooldown"><div class="token-badge">{coin} 0 TOKENS DISPONIBLES</div>'
            '<div class="balance">No se registró la visita</div></div></div>')

    c = res["customer"]
    name = c["name"]
    visits = int(res["visit_number"] or c["visits_count"])
    seg = customers.segment_label(visits)
    prev = utils.parse_dt(res["prev_last_visit"])
    days_bd = utils.days_until_birthday(c["birthday_day"], c["birthday_month"], created.date() if created else None)

    chips = [f'<span class="chip {"gold" if seg == "Cliente frecuente" else ""}">{seg}</span>',
             f'<span class="chip">{visits} visita{"s" if visits != 1 else ""}</span>']
    if days_bd is not None and days_bd <= 14:
        chips.append('<span class="chip gold">¡Hoy es su cumpleaños!</span>' if days_bd == 0
                     else f'<span class="chip gold">Cumpleaños en {days_bd} día{"s" if days_bd != 1 else ""}</span>')

    bday = utils.birthday_text(c["birthday_day"], c["birthday_month"])
    facts = [
        _fact("Pedido habitual", utils.esc(c["usual_dish"] or "Sin registrar"), "big wide"),
        _fact("Bebida", utils.esc(c["usual_drink"] or "Sin registrar")),
        _fact("Preferencia", utils.esc(c["preferences"] or "Sin registrar")),
        _fact("Cumpleaños", utils.esc(bday)),
        _fact("Última visita", utils.esc(utils.relative_time_es(prev, created))),
    ]
    if c.get("restrictions"):
        facts.append(_fact("Restricción", utils.esc(c["restrictions"]), "alert"))
    if c.get("is_demo") and c.get("avg_ticket"):
        facts.append(_fact("Gasto promedio", f'{ui.cop(c["avg_ticket"])} {ui.tag("Demo", "sim")}'))

    if status == tokens.OUTCOME_CHARGED:
        foot = (f'<div class="recog-foot charged"><div class="token-badge">{coin} 1 TOKEN UTILIZADO</div>'
                f'<div class="balance">Saldo antes <b>{utils.fmt_int(res["balance_before"])}</b><span class="arrow">→</span>'
                f'Saldo después <b>{utils.fmt_int(res["balance_after"])}</b></div></div>')
    else:   # COOLDOWN
        mins = max(1, round(res["cooldown_remaining_s"] / 60))
        foot = (f'<div class="recog-foot cooldown"><div><b>Cliente ya reconocido durante esta visita.</b><br>'
                f'No se consumió un token adicional.</div>'
                f'<div class="balance">Saldo actual <b>{utils.fmt_int(res["balance_after"])}</b><br>'
                f'<span class="small muted">Un nuevo cobro sería posible en ~{mins} min</span></div></div>')

    return (
        '<div class="recog">'
        f'<div class="recog-head"><div class="avatar">{utils.esc(utils.initials(name))}</div><div>'
        '<div class="recog-kicker">Cliente reconocido</div>'
        f'<div class="recog-name">Bienvenido, {utils.esc(utils.first_name(name))} 👋</div>'
        f'<div class="recog-meta">{"".join(chips)}</div></div></div>'
        f'<div class="recog-body">{"".join(facts)}</div>{foot}</div>')


def _render_result() -> None:
    res = st.session_state.get("p_last_recognition")
    if not res:
        ui.html(f'<div class="waiting"><div><div class="scan" style="color:var(--p500)">{ui.icon("scan")}</div>'
                '<h3>Esperando a un cliente</h3><p class="muted" style="margin:0">'
                'Simula una entrada o activa la cámara.<br>Aquí aparecerá el perfil del cliente reconocido.</p></div></div>')
        return
    if res["status"] == "ERROR":
        ui.show_notice("No pudimos procesar el reconocimiento. Inténtalo de nuevo.", "err")
        return

    ui.html(_card_html(res))
    src = {"demo": "Entrada simulada (modo demostración)", "camera": "Cámara en vivo", "snapshot": "Foto de la cámara"}
    extra = f" · Visita {res['visit_code']}" if res.get("visit_code") else ""
    conf = f" · Similitud {res['confidence']:.2f}" if res.get("confidence") is not None else ""
    ui.html(f'<p class="small muted" style="margin:.5rem .3rem 0 .3rem">Origen: {src.get(res["source"], res["source"])}{extra}{conf} · {res["created_at"][11:]}</p>')

    if res["status"] == tokens.OUTCOME_NO_BALANCE:
        st.button("Recargar 100 tokens (demo)", key="topup", type="primary", on_click=top_up, args=(100,))
    if res["status"] == tokens.OUTCOME_UNKNOWN:
        st.button("Registrar a este cliente", key="goto_register", on_click=state.go, args=("register",))


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
def _tile(c: dict) -> str:
    active = tokens.active_visit(c["id"])
    visits = int(c["visits_count"])
    sub = f"{visits} visita{'s' if visits != 1 else ''} · {customers.segment_label(visits)}"
    if active:
        sub = f'En el restaurante hasta las {active["expires_at"][11:16]}'
    return (f'<div class="cust-tile"><div class="avatar">{utils.esc(utils.initials(c["name"]))}</div><div>'
            f'<div class="nm">{utils.esc(c["name"])}</div><div class="sb">{utils.esc(sub)}</div></div></div>')


def _demo_controls() -> None:
    ui.html('<p class="muted small" style="margin:.2rem 0 .6rem 0">Elige quién entra al restaurante. Se ejecuta el mismo '
            'flujo que con la cámara: identificar, mostrar el perfil, usar un token y registrar el evento.</p>')
    people = customers.list_customers()
    for i in range(0, len(people), 2):
        cols = st.columns(2)
        for col, c in zip(cols, people[i:i + 2]):
            with col:
                ui.html(_tile(c))
                st.button("Simular entrada", key=f"sim_{c['id']}", on_click=register_recognition,
                          args=(c["id"], "demo"), width="stretch")
    ui.html('<div class="cust-tile unknown"><div class="avatar">?</div><div><div class="nm">Persona no registrada</div>'
            '<div class="sb">Nunca consume tokens</div></div></div>')
    st.button("Simular persona desconocida", key="sim_unknown", on_click=register_recognition,
              args=(None, "demo"), width="stretch")


def _camera_controls() -> None:
    """Reconocimiento con la cámara del equipo (OpenCV). Es la única vía de cámara de la app."""
    ss = st.session_state
    engine = recognition.get_engine()
    if not engine.available:
        ui.show_notice("<b>Reconocimiento facial no disponible en este equipo.</b> Continúa con el modo demostración.", "warn")
        st.button("Usar modo demostración", key="to_demo_a", type="primary",
                  on_click=lambda: ss.__setitem__("w_rec_mode", MODE_DEMO))
        return
    gallery = customers.load_gallery()
    if not gallery:
        ui.show_notice("Aún no hay rostros registrados. Registra a un cliente con su autorización para poder reconocerlo con la cámara.", "info")
        st.button("Ir a registrar un cliente", key="to_reg", on_click=state.go, args=("register",))
        return

    if config.WEB_MODE:
        _snapshot_scan(engine, gallery)
        return
    ui.html(f'<p class="muted small" style="margin:.2rem 0 .5rem 0">Se abre la cámara del equipo hasta {config.LIVE_SCAN_SECONDS} s '
            'y se detiene al reconocer a alguien. Mira de frente a la cámara.</p>')
    started = st.button("Iniciar escaneo con la cámara", key="scan_start", type="primary", width="stretch")
    frame_slot = st.empty()
    status_slot = st.empty()
    cam_index = ui.camera_selector("w_cam_choice")
    if started:
        _live_scan(engine, gallery, frame_slot, status_slot, cam_index)


def _snapshot_scan(engine, gallery) -> None:
    """Versión web: una foto con la cámara del navegador pasa por el MISMO flujo de negocio."""
    ss = st.session_state
    ui.html('<p class="muted small" style="margin:.2rem 0 .5rem 0">Permite el acceso a la cámara, mira de frente y toma la foto. '
            'El sistema identifica al cliente y, si está registrado, usa 1 token.</p>')
    nonce = ss.setdefault("p_rec_snap_nonce", 0)
    shot = st.camera_input("Tomar foto para reconocer", key=f"w_rec_snap_{nonce}")
    if shot is None:
        return
    data = shot.getvalue()
    digest = hashlib.sha1(data).hexdigest()
    if ss.get("p_rec_snap_hash") == digest:
        return
    ss.p_rec_snap_hash = digest
    res = engine.identify(engine.decode(data), gallery)
    if res.status in ("MATCH", "UNKNOWN"):
        register_recognition(res.customer_id if res.status == "MATCH" else None, "snapshot", res.score)
        ss.p_rec_snap_nonce = nonce + 1                     # la próxima persona usa una cámara limpia
        st.rerun()
    else:
        ui.show_notice(utils.esc(res.message or "No se detectó un rostro. Acércate y mira de frente."), "warn")


def _live_scan(engine, gallery, frame_slot, status_slot, cam_index) -> None:
    cap = recognition.open_camera(cam_index)
    if cap is None:
        with status_slot.container():
            ui.show_notice("<b>Cámara no disponible.</b> Continuar con modo demostración.", "warn")
            st.button("Usar modo demostración", key="to_demo_b", type="primary",
                      on_click=lambda: st.session_state.__setitem__("w_rec_mode", MODE_DEMO))
        return
    t0 = time.time()
    streak_id, streak, unknown_streak = None, 0, 0
    outcome = None
    try:
        while time.time() - t0 < config.LIVE_SCAN_SECONDS:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            res = engine.identify(frame, gallery)
            small = engine.shrink(frame)
            label, color = "", (143, 45, 107)
            hint = ""
            if res.status == "MATCH":
                streak_id, streak = (res.customer_id, streak + 1) if res.customer_id == streak_id else (res.customer_id, 1)
                unknown_streak = 0
                label = "Identificando…"
                if streak >= config.LIVE_CONFIRM_FRAMES:
                    outcome = ("MATCH", res.customer_id, res.score)
            elif res.status == "UNKNOWN":
                streak_id, streak = None, 0
                unknown_streak += 1
                label, color = "Desconocido", (110, 100, 130)
                if unknown_streak >= 4:
                    outcome = ("UNKNOWN", None, res.score)
            else:
                streak_id, streak, unknown_streak = None, 0, 0
                hint = " · " + (res.message if res.face is not None else "colócate frente a la cámara")
            frame_slot.image(cv2.cvtColor(recognition.draw_face(small, res.face, label, color, mirror=True), cv2.COLOR_BGR2RGB),
                             channels="RGB", width=460)
            left = max(0, int(config.LIVE_SCAN_SECONDS - (time.time() - t0)))
            status_slot.caption(f"Escaneando… {left} s{hint}")
            if outcome:
                break
            time.sleep(0.02)
    finally:
        cap.release()
    status_slot.empty()
    frame_slot.empty()
    if outcome:
        register_recognition(outcome[1], "camera", outcome[2])
    else:
        with status_slot.container():
            ui.show_notice("No detectamos a nadie frente a la cámara. Inténtalo de nuevo o usa el modo demostración.", "warn")


# ---------------------------------------------------------------------------
def render() -> None:
    ss = st.session_state
    if state.current_session():
        ui.stepper("recognition")
    ui.page_title("Reconocimiento de clientes",
                  "Cuando un cliente registrado llega, el sistema lo identifica y tu equipo ve su perfil. "
                  "<b>Cada reconocimiento válido usa 1 token.</b>")

    left, right = st.columns([1, 1.25], gap="large")
    with right:
        slot = st.empty()
    with left:
        ui.html(ui.wallet(tokens.get_balance()))
        ui.html(f'<p class="small muted" style="margin:.5rem 0 .8rem 0">Un mismo cliente consume como máximo 1 token cada '
                f'{settings.cooldown_minutes()} minutos (una visita). Los desconocidos no consumen tokens.</p>')
        mode = st.radio("Modo", [MODE_DEMO, MODE_CAMERA], horizontal=True, key="w_rec_mode", label_visibility="collapsed")
        if mode == MODE_DEMO:
            _demo_controls()
        else:
            _camera_controls()

    with slot.container():
        _render_result()
        if state.current_session():
            st.write("")
            st.button("Continuar al panel", key="rec_next", type="primary", on_click=state.go, args=("dashboard",))
    ui.footer()
