# -*- coding: utf-8 -*-
"""Parámetros editables en tiempo de ejecución (tabla `settings`).

Los valores de fábrica salen de `config.py`; el Modo investigador puede
sobrescribirlos sin tocar código.
"""
from __future__ import annotations

from typing import Optional

import config
from modules import database, utils

# clave -> (valor de fábrica, mínimo, máximo)
ECONOMIC_KEYS: dict[str, tuple[int, int, int]] = {
    "monthly_price": (config.MONTHLY_PRICE, 0, 100_000_000),
    "token_price": (config.TOKEN_PRICE, 0, 10_000_000),
    "initial_token_balance": (config.INITIAL_TOKEN_BALANCE, 0, 10_000_000),
    "token_cooldown_minutes": (config.TOKEN_COOLDOWN_MINUTES, 0, 24 * 60),
}


def _raw(key: str) -> Optional[str]:
    row = database.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else None


def get_int(key: str) -> int:
    default, lo, hi = ECONOMIC_KEYS[key]
    raw = _raw(key)
    if raw is None:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def set_value(key: str, value) -> None:
    database.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, str(value), utils.to_str(utils.now())),
    )


def set_economic(key: str, value: int) -> int:
    if key not in ECONOMIC_KEYS:
        raise KeyError(key)
    _, lo, hi = ECONOMIC_KEYS[key]
    value = int(value)
    if not lo <= value <= hi:
        raise ValueError(f"{key} debe estar entre {lo} y {hi}")
    set_value(key, value)
    return value


def reset_economic() -> None:
    database.execute(
        "DELETE FROM settings WHERE key IN (%s)" % ",".join("?" * len(ECONOMIC_KEYS)),
        tuple(ECONOMIC_KEYS),
    )


def monthly_price() -> int:
    return get_int("monthly_price")


def token_price() -> int:
    return get_int("token_price")


def initial_token_balance() -> int:
    return get_int("initial_token_balance")


def cooldown_minutes() -> int:
    return get_int("token_cooldown_minutes")


def economic_snapshot() -> dict:
    return {
        "monthly_price": monthly_price(),
        "token_price": token_price(),
        "initial_token_balance": initial_token_balance(),
        "token_cooldown_minutes": cooldown_minutes(),
    }


def rehearsal_mode() -> bool:
    return _raw("rehearsal_mode") == "1"


def set_rehearsal_mode(on: bool) -> None:
    set_value("rehearsal_mode", "1" if on else "0")
