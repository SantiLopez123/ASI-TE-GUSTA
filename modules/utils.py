# -*- coding: utf-8 -*-
"""Utilidades compartidas: reloj, formatos en español, registro de errores."""
from __future__ import annotations

import html
import logging
import logging.handlers
from datetime import date, datetime
from typing import Callable, Optional

import config

DT_FMT = "%Y-%m-%d %H:%M:%S"

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# --------------------------------------------------------------------------
# Reloj (reemplazable en pruebas)
# --------------------------------------------------------------------------
_clock: Optional[Callable[[], datetime]] = None


def set_clock(fn: Optional[Callable[[], datetime]]) -> None:
    """Permite a las pruebas fijar la hora. `None` restaura el reloj real."""
    global _clock
    _clock = fn


def now() -> datetime:
    if _clock is not None:
        return _clock()
    return datetime.now().replace(microsecond=0)


def to_str(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, DT_FMT)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Formatos
# --------------------------------------------------------------------------
def fmt_int(n) -> str:
    """1234567 -> '1.234.567' (separador de miles colombiano)."""
    try:
        return f"{int(round(n)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def fmt_cop(n) -> str:
    """250000 -> '$250.000'."""
    try:
        value = int(round(n))
    except (TypeError, ValueError):
        value = 0
    sign = "-" if value < 0 else ""
    return f"{sign}${fmt_int(abs(value))}"


def fmt_cop_full(n) -> str:
    return f"{fmt_cop(n)} {config.CURRENCY}"


def esc(value) -> str:
    """Escapa texto del usuario antes de insertarlo en HTML."""
    return html.escape("" if value is None else str(value), quote=True)


def birthday_text(day: Optional[int], month: Optional[int]) -> str:
    if not day or not month or not (1 <= month <= 12):
        return "No registrado"
    return f"{day} de {MONTHS_ES[month - 1]}"


def days_until_birthday(day: Optional[int], month: Optional[int], today: Optional[date] = None) -> Optional[int]:
    """Días hasta el próximo cumpleaños (0 = hoy). None si no hay fecha válida."""
    if not day or not month:
        return None
    today = today or now().date()
    for year in (today.year, today.year + 1):
        try:
            nxt = date(year, month, day)
        except ValueError:      # 29 de febrero en año no bisiesto
            nxt = date(year, 3, 1)
        if nxt >= today:
            return (nxt - today).days
    return None


def relative_time_es(past: Optional[datetime], reference: Optional[datetime] = None) -> str:
    """'Hace 12 días', 'Ayer', 'Hoy', 'Primera visita'..."""
    if past is None:
        return "Primera visita"
    reference = reference or now()
    days = (reference.date() - past.date()).days
    if days <= 0:
        return "Hoy"
    if days == 1:
        return "Ayer"
    if days < 60:
        return f"Hace {days} días"
    months = days // 30
    if months < 12:
        return f"Hace {months} meses"
    years = days // 365
    return f"Hace {years} año" + ("s" if years > 1 else "")


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def first_name(name: str) -> str:
    parts = (name or "").split()
    return parts[0] if parts else ""


# --------------------------------------------------------------------------
# Registro interno de errores (nunca se muestra el traceback al participante)
# --------------------------------------------------------------------------
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        logger = logging.getLogger("asi_te_gusta")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            try:
                config.LOG_DIR.mkdir(parents=True, exist_ok=True)
                handler = logging.handlers.RotatingFileHandler(
                    config.LOG_DIR / "app.log", maxBytes=500_000, backupCount=2, encoding="utf-8"
                )
                handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                logger.addHandler(handler)
            except OSError:
                logger.addHandler(logging.NullHandler())
        _logger = logger
    return _logger


def log_exception(context: str) -> None:
    get_logger().exception("Error en %s", context)
