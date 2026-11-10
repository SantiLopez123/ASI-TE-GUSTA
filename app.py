# -*- coding: utf-8 -*-
"""ASÍ TE GUSTA · prototipo académico (Streamlit).

Ejecutar:  streamlit run app.py   (o doble clic en run.bat)
"""
import os

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import streamlit as st

import config

st.set_page_config(
    page_title=f"{config.APP_NAME_TITLE} · CRM para restaurantes",
    page_icon=str(config.ASSETS_DIR / "favicon.png") if (config.ASSETS_DIR / "favicon.png").exists() else None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

from modules import database, state, ui, utils            # noqa: E402
from views import (dashboard, decision, finish, home, pilot, recognition,   # noqa: E402
                   register, researcher, simulator)

VIEWS = {
    "home": home, "register": register, "recognition": recognition, "dashboard": dashboard,
    "simulator": simulator, "decision": decision, "pilot": pilot, "finish": finish, "researcher": researcher,
}


@st.cache_resource(show_spinner=False)
def _boot() -> bool:
    """Crea la base de datos y los datos DEMO en el primer arranque."""
    database.init_db()
    return True


def main() -> None:
    ui.inject_css()
    try:
        if not database.DB_PATH.exists():       # alguien borró app.db con la app abierta: se recrea
            _boot.clear()
        _boot()
    except Exception:                                       # noqa: BLE001
        utils.log_exception("arranque de la base de datos")
        ui.show_notice("<b>No pudimos abrir la base de datos local.</b> Cierra otras ventanas de la app y recarga la página.", "err")
        return

    state.init()
    ss = st.session_state
    page = ss.page if ss.page in VIEWS else "home"

    # Las páginas del recorrido necesitan una sesión experimental (se crea sola).
    needs_session = page not in state.NO_SESSION_PAGES and not (page == "finish" and ss.get("p_finished"))
    try:
        if needs_session:
            state.ensure_session()
        state.track_page_view(page)
        state.sync_query_params()

        if page != "researcher" and not (page == "finish"):
            ui.topnav(page)
        elif page == "finish":
            ui.html(f'<div style="margin-bottom:1rem">{ui.brand()}</div>')

        VIEWS[page].render()
    except Exception:                                       # noqa: BLE001  (RerunException no hereda de Exception)
        utils.log_exception(f"vista {page}")
        ui.show_notice("<b>Algo no salió como esperábamos.</b> Tu información está a salvo. "
                       "Vuelve al inicio e inténtalo de nuevo.", "err")
        st.button("Volver al inicio", key="err_home", type="primary", on_click=state.go, args=("home",))


main()
