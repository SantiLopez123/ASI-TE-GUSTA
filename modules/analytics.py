# -*- coding: utf-8 -*-
"""Datos del panel del restaurante.

Dos bloques que NUNCA se mezclan:
  * REAL      -> lo que ocurrió de verdad en esta instalación (base de datos).
  * SIMULADO  -> mes de ejemplo para que el panel se vea útil desde el inicio.
"""
from __future__ import annotations

import random
from datetime import timedelta

import pandas as pd

import config
from modules import customers, database, settings, tokens, utils


# ---------------------------------------------------------------------------
# REAL
# ---------------------------------------------------------------------------
def real_metrics() -> dict:
    charged = int(database.scalar(
        "SELECT COUNT(*) FROM recognition_events WHERE outcome = 'CHARGED'"))
    distinct = int(database.scalar(
        "SELECT COUNT(DISTINCT customer_id) FROM recognition_events WHERE outcome = 'CHARGED'"))
    recurrent = int(database.scalar(
        "SELECT COUNT(*) FROM (SELECT customer_id FROM recognition_events WHERE outcome = 'CHARGED' "
        "AND customer_id IS NOT NULL GROUP BY customer_id HAVING COUNT(*) >= 2)"))
    consumed = tokens.total_consumed()
    today = utils.now().strftime("%Y-%m-%d")
    return {
        "registered": customers.count_customers(),
        "registered_demo": customers.count_customers() - customers.count_customers(include_demo=False),
        "registered_real": customers.count_customers(include_demo=False),
        "faces_enrolled": customers.count_enrolled_faces(),
        "recognitions": charged,
        "recognitions_today": int(database.scalar(
            "SELECT COUNT(*) FROM recognition_events WHERE outcome = 'CHARGED' AND created_at LIKE ?",
            (today + "%",))),
        "recognitions_month": int(database.scalar(
            "SELECT COUNT(*) FROM recognition_events WHERE outcome = 'CHARGED' AND created_at LIKE ?",
            (today[:7] + "%",))),
        "distinct_recognized": distinct,
        "recurrent": recurrent,
        "tokens_consumed": consumed,
        "tokens_available": tokens.get_balance(),
        "token_cost": consumed * settings.token_price(),
        "visits": int(database.scalar("SELECT COUNT(*) FROM visits")),
        "cooldown_hits": int(database.scalar(
            "SELECT COUNT(*) FROM recognition_events WHERE outcome = 'COOLDOWN'")),
        "unknown_faces": int(database.scalar(
            "SELECT COUNT(*) FROM recognition_events WHERE outcome = 'UNKNOWN'")),
        "birthdays": customers.upcoming_birthdays(),
    }


def recent_events(limit: int = 8) -> pd.DataFrame:
    rows = database.fetch_all(
        """SELECT r.created_at, c.name AS customer, r.outcome, r.source, r.token_consumed, r.visit_code
           FROM recognition_events r LEFT JOIN customers c ON c.id = r.customer_id
           ORDER BY r.id DESC LIMIT ?""", (limit,))
    labels = {"CHARGED": "Reconocido · 1 token", "COOLDOWN": "Ya reconocido · sin cobro",
              "NO_BALANCE": "Sin saldo de tokens", "UNKNOWN": "No registrado · sin cobro"}
    src = {"demo": "Simulación", "camera": "Cámara", "snapshot": "Foto"}
    out = []
    for r in rows:
        out.append({
            "Hora": r["created_at"][5:16],
            "Cliente": r["customer"] or "Desconocido",
            "Resultado": labels.get(r["outcome"], r["outcome"]),
            "Origen": src.get(r["source"], r["source"] or ""),
            "Visita": r["visit_code"] or "—",
        })
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# SIMULADO
# ---------------------------------------------------------------------------
_WEEKDAY_WEIGHT = [0.70, 0.75, 0.85, 1.00, 1.40, 1.70, 1.20]   # lunes..domingo


def simulated_month() -> dict:
    """Mes de ejemplo determinista: suma exactamente DEMO_MONTH_RECOGNITIONS."""
    rng = random.Random(2026)
    today = utils.now().date()
    days = [today - timedelta(days=29 - i) for i in range(30)]
    weights = [_WEEKDAY_WEIGHT[d.weekday()] * rng.uniform(0.8, 1.2) for d in days]
    total = config.DEMO_MONTH_RECOGNITIONS
    raw = [w / sum(weights) * total for w in weights]
    counts = [int(x) for x in raw]
    # reparto del resto por mayor parte decimal
    order = sorted(range(30), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: total - sum(counts)]:
        counts[i] += 1
    df = pd.DataFrame({"fecha": pd.to_datetime(days), "reconocimientos": counts})
    return {
        "series": df,
        "recognitions": total,
        "recurring": config.DEMO_MONTH_RECURRING,
        "new": total - config.DEMO_MONTH_RECURRING,
        "tokens": total,
        "token_cost": total * settings.token_price(),
        "sales": config.DEMO_MONTH_SALES,
    }
