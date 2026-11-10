# -*- coding: utf-8 -*-
"""Componentes visuales compartidos (HTML/CSS) para ASÍ TE GUSTA."""
from __future__ import annotations

from functools import lru_cache

import streamlit as st

import config
from modules import state, utils

# ---------------------------------------------------------------------------
# Iconos (trazos simples, 24x24)
# ---------------------------------------------------------------------------
_ICONS = {
    "user-plus": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M19 8v6M16 11h6"/>',
    "scan": '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="10.5" r="2.6"/><path d="M7.5 17c.8-2 2.4-3 4.5-3s3.7 1 4.5 3"/>',
    "chart": '<path d="M4 20V11M10 20V4M16 20v-7M22 20H2"/>',
    "calc": '<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7.5h7M8.5 12h.01M12 12h.01M15.5 12h.01M8.5 16h.01M12 16h.01M15.5 16h.01"/>',
    "coin": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M9.6 10c0-1 1-1.6 2.4-1.6s2.4.6 2.4 1.6-1 1.4-2.4 1.8-2.4.8-2.4 1.8 1 1.6 2.4 1.6 2.4-.6 2.4-1.6"/>',
    "shield": '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
    "cake": '<path d="M4 20h16v-6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2z"/><path d="M12 12V8M12 5v.01M4 16c2 1.5 4 1.5 6 0s4-1.5 6 0 2.6 1 4 0"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def icon(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICONS[name]}</svg>')


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
_css_cache: dict = {}


def _css() -> str:
    """CSS con caché por fecha de modificación (los cambios de estilo se ven al recargar)."""
    path = config.ASSETS_DIR / "style.css"
    mtime = path.stat().st_mtime
    if _css_cache.get("mtime") != mtime:
        _css_cache.update(mtime=mtime, text=path.read_text(encoding="utf-8"))
    return _css_cache["text"]


@lru_cache(maxsize=1)
def _logo_svg() -> str:
    svg = (config.ASSETS_DIR / "logo_mark.svg").read_text(encoding="utf-8")
    return svg.replace(' width="48" height="48"', "", 1).replace("\n", "")


def inject_css() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def html(markup: str) -> None:
    """Dibuja HTML sin que Markdown lo interprete (sin líneas en blanco ni sangrías)."""
    cleaned = "\n".join(line.strip() for line in markup.strip().splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def cop(n) -> str:
    """Pesos para insertar en HTML: '$' como entidad para que Markdown no lo trate como LaTeX."""
    return utils.fmt_cop(n).replace("$", "&#36;")


def md_cop(n) -> str:
    """Pesos para texto Markdown normal."""
    return utils.fmt_cop(n).replace("$", "\\$")


def brand(light: bool = False) -> str:
    cls = "brand light" if light else "brand"
    return (f'<div class="{cls}">{_logo_svg()}<div><div class="brand-name">ASÍ <span>TE</span> GUSTA</div>'
            f'<div class="brand-sub">{utils.esc(config.TAGLINE)}</div></div></div>')


def tag(text: str, kind: str = "neutral") -> str:
    return f'<span class="tag tag-{kind}">{utils.esc(text)}</span>'


TAG_SIM = tag("Simulado", "sim")
TAG_REAL = tag("Real", "real")


def kpi(label: str, value: str, sub: str = "", tag_html: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    tag_row = f'<div style="margin-top:.5rem">{tag_html}</div>' if tag_html else ""
    return (f'<div class="kpi"><div class="kpi-label">{utils.esc(label)}</div>'
            f'<div class="kpi-value">{value}</div>{sub_html}{tag_row}</div>')


def notice(text_html: str, kind: str = "info") -> str:
    ico = {"info": "info", "warn": "alert", "ok": "check", "err": "alert"}[kind]
    cls = "" if kind == "info" else f" {kind}"
    return f'<div class="notice{cls}">{icon(ico)}<div>{text_html}</div></div>'


def show_notice(text_html: str, kind: str = "info") -> None:
    html(notice(text_html, kind))


def section_head(title: str, tag_html: str = "") -> None:
    html(f'<div class="sec-head"><h3>{utils.esc(title)}</h3>{tag_html}<div class="line"></div></div>')


def page_title(title: str, subtitle: str = "") -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    html(f'<div class="page-title"><h1>{utils.esc(title)}</h1>{sub}</div>')


def stepper(current: str) -> None:
    """Indicador de progreso del recorrido guiado."""
    keys = [k for k, _ in state.GUIDED_STEPS]
    if current not in keys:
        return
    idx = keys.index(current)
    items = []
    for i, (_, label) in enumerate(state.GUIDED_STEPS):
        cls = "now" if i == idx else ("done" if i < idx else "")
        mark = "✓" if i < idx else str(i + 1)
        items.append(f'<div class="step {cls}"><i>{mark}</i>{utils.esc(label)}</div>')
    html(f'<div class="steps">{"".join(items)}</div>')


def camera_selector(key: str):
    """Selector discreto de cámara. Devuelve None (= automática) o el número de cámara elegido."""
    if config.WEB_MODE:                                     # en la web la cámara la elige el navegador
        return None
    options = ["Automática", "Cámara 0", "Cámara 1", "Cámara 2", "Cámara 3"]
    with st.expander("Opciones de cámara"):
        choice = st.selectbox("Cámara", options, key=key,
                              help="Automática prueba las cámaras del equipo hasta encontrar una con imagen. "
                                   "Elige un número si el equipo tiene varias (la cámara integrada suele ser la 0).")
    return None if choice == options[0] else int(choice.split()[-1])


def wallet(balance: int) -> str:
    return (f'<div class="wallet"><div class="coin">{icon("coin")}</div><div>'
            f'<div class="lbl">Tokens disponibles</div><div class="num">{utils.fmt_int(balance)}</div></div></div>')


# ---------------------------------------------------------------------------
# Navegación superior
# ---------------------------------------------------------------------------
def topnav(page: str) -> None:
    with st.container(key="topnav"):
        cols = st.columns([2.7, 0.9, 1.55, 1.6, 0.8, 1.7], vertical_alignment="center")
        with cols[0]:
            html(brand())
        for col, (key, label) in zip(cols[1:], state.NAV_ITEMS):
            with col:
                st.button(label, key=f"nav_{key}", type="primary" if page == key else "tertiary",
                          on_click=state.go, args=(key,), width="stretch")


def footer() -> None:
    html(f'<div class="footer-note">{utils.esc(config.ACADEMIC_NOTICE)}<br>'
         f'{utils.esc(config.APP_NAME_TITLE)} · Idear Empresarial · Reto 3: Prototipado y diseño de experimentos</div>')
    _, left, right, _ = st.columns([1.6, 1, 1.25, 1.6], vertical_alignment="center")
    with left:
        with st.container(key="researcher_link"):
            st.button("Modo investigador", key="open_researcher", on_click=state.go,
                      args=("researcher",), width="stretch")
    with right:
        with st.container(key="survey_link"):
            st.button("Ver sondeo de precio", key="open_survey", icon=":material/bar_chart:",
                      on_click=state.open_survey, width="stretch")
