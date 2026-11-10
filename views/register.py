# -*- coding: utf-8 -*-
"""Pantalla 2 · Registro de cliente (consentimiento + rostro) y eliminación de datos."""
from __future__ import annotations

import hashlib

import cv2
import streamlit as st

import config
from modules import customers, experiment, recognition, state, ui, utils


def _goto_camera_recognition() -> None:
    """Tras registrar un rostro: abrir Reconocer ya en modo «Cámara real»."""
    st.session_state.w_rec_mode = "Cámara real"
    state.go("recognition")


def _nonce() -> int:
    return st.session_state.setdefault("p_reg_nonce", 0)


def _k(name: str) -> str:
    return f"w_reg_{name}_{_nonce()}"


def _process_photo(data: bytes, engine) -> None:
    """Convierte una foto en embedding (la foto NO se guarda) y la acumula como muestra."""
    ss = st.session_state
    digest = hashlib.sha1(data).hexdigest()
    if ss.get("p_reg_last_hash") == digest:
        return
    ss.p_reg_last_hash = digest
    res = engine.embedding_for_enrollment(engine.decode(data))
    samples = ss.setdefault("p_reg_samples", [])
    if res.ok:
        if len(samples) < config.FACE_MAX_ENROLL_SAMPLES:
            samples.append(res.embedding)
        ss.p_reg_msg = ("ok", f"Rostro detectado. Muestras guardadas: {len(samples)} de {config.FACE_MAX_ENROLL_SAMPLES}.")
    else:
        ss.p_reg_msg = ("err", res.message)


def _browser_capture_panel(engine) -> None:
    """Versión web: fotos con la cámara del navegador (st.camera_input). Cada foto distinta suma una muestra."""
    ss = st.session_state
    n = len(ss.get("p_reg_samples", []))
    ui.html('<p class="small muted" style="margin:0 0 .4rem 0">Permite el acceso a la cámara cuando el navegador lo pida y '
            'toma una foto mirando de frente. Con 1 foto basta; 2 o 3 (girando un poco la cabeza) mejoran el reconocimiento. '
            'No se guarda ninguna foto.</p>')
    if n < config.FACE_MAX_ENROLL_SAMPLES:
        shot = st.camera_input(f"Foto {n + 1} de {config.FACE_MAX_ENROLL_SAMPLES}", key=_k(f"cam{n}"))
        if shot is not None:
            _process_photo(shot.getvalue(), engine)
            if len(ss.get("p_reg_samples", [])) > n:
                st.rerun()
    if n:
        st.button("Borrar fotos y empezar de nuevo", key=_k("reset_samples"),
                  on_click=lambda: ss.update(p_reg_samples=[], p_reg_msg=None, p_reg_last_hash=None))
    with st.expander("Prefiero subir una foto"):
        up = st.file_uploader("Foto con un solo rostro", type=["jpg", "jpeg", "png"], key=_k("upload"),
                              label_visibility="collapsed")
        if up is not None:
            _process_photo(up.getvalue(), engine)
    msg = ss.get("p_reg_msg")
    if msg:
        ui.show_notice(utils.esc(msg[1]), "ok" if msg[0] == "ok" else "err")


def _capture_panel(engine) -> None:
    """Captura facial con la cámara del equipo (OpenCV): 3 muestras automáticas, vista previa en espejo.

    Es la ÚNICA vía de cámara de la app (la misma del reconocimiento), así nunca hay dos cámaras
    compitiendo por el hardware. La foto no se guarda: sólo los embeddings.
    """
    if config.WEB_MODE:
        _browser_capture_panel(engine)
        return
    ss = st.session_state
    n = len(ss.get("p_reg_samples", []))
    started = st.button("Repetir captura" if n else "Activar cámara y capturar mi rostro", key="reg_capture",
                        type="secondary" if n else "primary", width="stretch")
    slot, status = st.empty(), st.empty()
    cam_index = ui.camera_selector("w_cam_choice")
    if started:
        ss.p_reg_samples, ss.p_reg_msg = [], None
        cap = recognition.open_camera(cam_index)
        if cap is None:
            ss.p_reg_msg = ("err", "Cámara no disponible. Cierra otras aplicaciones que la usen y vuelve a intentar, "
                                   "sube una foto o registra al cliente sin rostro (modo demostración).")
        else:
            def paint(img_bgr, msg: str) -> None:
                slot.image(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), channels="RGB", width=460)
                status.caption(msg)

            try:
                res = recognition.capture_samples(
                    engine, cap, wanted=config.FACE_MAX_ENROLL_SAMPLES, seconds=config.ENROLL_CAPTURE_SECONDS,
                    spacing=config.ENROLL_SAMPLE_SPACING, on_frame=paint)
            finally:
                cap.release()
            ss.p_reg_samples = res.samples
            ss.p_reg_msg = ("ok" if res.samples else "err", res.message)
        slot.empty()
        status.empty()
    with st.expander("No tengo cámara: subir una foto"):
        up = st.file_uploader("Foto con un solo rostro", type=["jpg", "jpeg", "png"], key=_k("upload"),
                              label_visibility="collapsed")
        if up is not None:
            _process_photo(up.getvalue(), engine)
    msg = ss.get("p_reg_msg")
    if msg:
        ui.show_notice(utils.esc(msg[1]), "ok" if msg[0] == "ok" else "err")
    else:
        ui.html('<p class="small muted" style="margin:.3rem 0 0 0">Se tomarán 3 muestras en unos segundos: mira de frente '
                'y gira un poco la cabeza. No se guarda ninguna foto.</p>')


def _submit(profile: dict, consent: bool) -> None:
    ss = st.session_state
    samples = list(ss.get("p_reg_samples", []))
    errors = customers.validate_profile(profile)
    if not consent:
        errors.append("Marca la autorización para poder registrarte.")
    if customers.name_exists(profile["name"] or ""):
        errors.append("Ya existe un cliente con ese nombre. Agrega un apellido o una inicial.")
    if samples and not errors:
        engine = recognition.get_engine()
        _, best = engine.best_match(samples[0], customers.load_gallery())
        if best >= config.FACE_MATCH_THRESHOLD:
            errors.append("Este rostro ya parece estar registrado. Si es tu perfil, elimínalo primero y vuelve a registrarte.")
    if errors:
        ss.p_reg_errors = errors
        return
    try:
        cid = customers.create_customer(profile, consent, samples)
    except (ValueError, PermissionError) as exc:
        ss.p_reg_errors = [str(exc)]
        return
    sid = state.current_session()
    experiment.log_event(sid, "CUSTOMER_REGISTERED", "register", {"customer_id": cid, "face": bool(samples)})
    ss.p_reg_done = {"name": profile["name"], "face": bool(samples)}
    ss.p_reg_errors = []
    ss.p_reg_nonce = _nonce() + 1
    ss.p_reg_samples = []
    ss.p_reg_last_hash = None
    ss.p_reg_msg = None


def render() -> None:
    ss = st.session_state
    engine = recognition.get_engine()

    ui.page_title("Registrar cliente",
                  "Un cliente se registra de forma voluntaria. Sin su autorización no se guarda nada.")

    if ss.get("p_reg_done"):
        done = ss.p_reg_done
        extra = ("Guardamos únicamente una huella numérica de su rostro; la fotografía no se almacena."
                 if done["face"] else "Se registró sin rostro: podrá usarse en el modo demostración, pero la cámara no lo reconocerá.")
        ui.show_notice(f"<b>{utils.esc(done['name'])} quedó registrado.</b> {extra}", "ok")
        st.write("")
        c1, c2, _ = st.columns([1.4, 1, 1.4])
        with c1:
            if done["face"]:
                st.button("Reconocerme con la cámara", key="reg_goto_rec", type="primary", on_click=_goto_camera_recognition,
                          width="stretch")
            else:
                st.button("Ir a reconocer", key="reg_goto_rec", type="primary", on_click=state.go, args=("recognition",),
                          width="stretch")
        with c2:
            st.button("Registrar otro cliente", key="reg_another", on_click=lambda: ss.pop("p_reg_done", None), width="stretch")
    else:
        left, right = st.columns([1.1, 1], gap="large")
        with left:
            ui.html('<div class="sec-head" style="margin-top:0"><h3>Datos del cliente</h3><div class="line"></div></div>')
            name = st.text_input("Nombre *", key=_k("name"), placeholder="Nombre y apellido", max_chars=80)
            b1, b2 = st.columns(2)
            with b1:
                day = st.selectbox("Cumpleaños · día", list(range(1, 32)), index=None, placeholder="Día", key=_k("day"))
            with b2:
                month = st.selectbox("Cumpleaños · mes", list(range(1, 13)), index=None, placeholder="Mes",
                                     format_func=lambda m: utils.MONTHS_ES[m - 1].capitalize(), key=_k("month"))
            d1, d2 = st.columns(2)
            with d1:
                dish = st.text_input("Plato habitual", key=_k("dish"), placeholder="Ej.: Bandeja paisa sin aguacate", max_chars=100)
            with d2:
                drink = st.text_input("Bebida habitual", key=_k("drink"), placeholder="Ej.: Limonada de coco", max_chars=100)
            p1, p2 = st.columns(2)
            with p1:
                prefs = st.text_input("Preferencias", key=_k("prefs"), placeholder="Ej.: Mesa interior", max_chars=120)
            with p2:
                restr = st.text_input("Restricciones", key=_k("restr"), placeholder="Ej.: Alergia a los mariscos", max_chars=120)
            e1, e2 = st.columns(2)
            with e1:
                email = st.text_input("Correo (opcional)", key=_k("email"), placeholder="nombre@correo.com", max_chars=120)
            with e2:
                phone = st.text_input("Celular (opcional)", key=_k("phone"), placeholder="300 123 4567", max_chars=20)

        with right:
            ui.html('<div class="sec-head" style="margin-top:0"><h3>Autorización y rostro</h3><div class="line"></div></div>')
            consent = st.checkbox("Autorizo el uso de mi información y registro facial para esta demostración.",
                                  key=_k("consent"), width="stretch")
            ui.html('<p class="small muted" style="margin:.2rem 0 .6rem 0">Guardamos solo una huella numérica de tu rostro, '
                    'nunca tu fotografía. '
                    + ('Se guarda temporalmente en el servidor de esta demostración'
                       if config.WEB_MODE else 'Todo permanece en este computador')
                    + ' y puedes eliminarlo cuando quieras.</p>')

            if not engine.available:
                ui.show_notice("<b>Reconocimiento facial no disponible en este equipo.</b> Puedes registrar al cliente sin rostro "
                               "y usarlo en el modo demostración.", "warn")
            elif not consent:
                ui.show_notice("Marca la autorización para activar la cámara.", "info")
            else:
                _capture_panel(engine)

        samples = ss.get("p_reg_samples", [])
        label = "Registrar cliente" if samples else "Registrar cliente sin rostro"
        if consent and not samples and engine.available:
            ui.show_notice("Sin foto, la cámara no podrá reconocer a este cliente (solo funcionará en modo demostración).", "warn")

        if ss.get("p_reg_errors"):
            ui.show_notice("<br>".join(utils.esc(e) for e in ss.p_reg_errors), "err")

        profile = dict(name=name, birthday_day=day, birthday_month=month, usual_dish=dish, usual_drink=drink,
                       preferences=prefs, restrictions=restr, email=email, phone=phone)
        b, _ = st.columns([1, 2])
        with b:
            if st.button(label, key="reg_submit", type="primary", disabled=not consent, width="stretch"):
                _submit(profile, consent)
                st.rerun()

    _render_profiles()
    ui.footer()


def _render_profiles() -> None:
    ss = st.session_state
    ui.section_head("Perfiles registrados y eliminación de datos")
    registered = customers.list_customers(include_demo=False)
    demo = [c for c in customers.list_customers() if c["is_demo"]]

    c1, c2 = st.columns([1.3, 1], gap="large")
    with c1:
        if registered:
            rows = [{"Nombre": c["name"], "Rostro": "Sí" if c["face_enrolled"] else "No",
                     "Visitas": c["visits_count"], "Registrado": c["created_at"][:10]} for c in registered]
            st.dataframe(rows, hide_index=True, width="stretch")
        else:
            ui.html('<div class="card flat muted small">Aún no hay clientes con registro propio. '
                    f'Hay {len(demo)} clientes de demostración (sin rostro) listos para el modo demo.</div>')
    with c2:
        if ss.get("p_del_msg"):
            ui.show_notice(utils.esc(ss.pop("p_del_msg")), "ok")
        if registered:
            ui.html('<div class="card lav"><b>Eliminar mis datos</b><br><span class="small muted">Elige tu perfil, qué quieres borrar y confirma.</span></div>')
            options = {c["name"]: c["id"] for c in registered}
            sel = st.selectbox("Perfil", list(options), index=None, placeholder="Selecciona un perfil", key="w_del_sel")
            scope = st.radio("Qué eliminar", ["Solo mi registro facial (conservar el perfil)", "Todo mi perfil y mis datos"],
                             key="w_del_scope")
            ok = st.checkbox("Confirmo que quiero eliminar estos datos. No se puede deshacer.", key="w_del_ok")
            if st.button("Eliminar mis datos", key="del_go", disabled=not (sel and ok), width="stretch"):
                cid = options[sel]
                if scope.startswith("Solo"):
                    customers.delete_biometrics(cid)
                    ss.p_del_msg = f"Se eliminó el registro facial de {sel}. Su perfil se conserva."
                else:
                    customers.delete_customer(cid)
                    ss.p_del_msg = f"Se eliminó por completo el perfil de {sel}."
                for key in ("w_del_sel", "w_del_scope", "w_del_ok"):
                    ss.pop(key, None)
                st.rerun()
