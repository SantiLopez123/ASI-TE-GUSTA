# -*- coding: utf-8 -*-
"""Cálculo económico: mensualidad fija (Plan A) vs. pago por tokens (Plan B).

Funciones puras: reciben los precios como argumento (o los toman de
`settings`) para poder probarlas sin interfaz. Todo en pesos enteros (COP).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

import config
from modules import settings

MODEL_MONTHLY = "MENSUALIDAD"
MODEL_TOKENS = "TOKENS"
MODEL_LABELS = {MODEL_MONTHLY: "Mensualidad fija", MODEL_TOKENS: "Pago por tokens"}


@dataclass(frozen=True)
class Comparison:
    customers: int
    visits_per_customer: float
    recognitions: int          # reconocimientos (= tokens) al mes
    monthly_price: int         # precio de la mensualidad (Plan A)
    token_price: int           # precio de 1 token
    monthly_cost: int          # costo mensual Plan A
    token_cost: int            # costo mensual Plan B
    difference: int            # |A - B|
    cheaper: str               # MENSUALIDAD | TOKENS | IGUAL
    breakeven: Optional[float]  # reconocimientos/mes donde A y B cuestan lo mismo

    def as_dict(self) -> dict:
        return asdict(self)


def validate_inputs(customers, visits_per_customer=1.0) -> tuple[int, float]:
    """Normaliza y valida la entrada. Lanza ValueError con mensaje en español."""
    if customers is None:
        raise ValueError("Escribe cuántos clientes frecuentes recibes al mes.")
    try:
        c = float(customers)
        v = float(visits_per_customer if visits_per_customer is not None else 1.0)
    except (TypeError, ValueError):
        raise ValueError("Usa solo números.") from None
    if not (math.isfinite(c) and math.isfinite(v)):
        raise ValueError("Usa solo números.")
    if c < 0 or v < 0:
        raise ValueError("El número no puede ser negativo.")
    if c > config.SIMULATOR_MAX_CUSTOMERS:
        raise ValueError(f"El máximo permitido es {config.SIMULATOR_MAX_CUSTOMERS:,}.".replace(",", "."))
    if v > config.SIMULATOR_MAX_VISITS_PER_CUSTOMER:
        raise ValueError(f"Las visitas por cliente al mes no pueden superar {config.SIMULATOR_MAX_VISITS_PER_CUSTOMER}.")
    return int(round(c)), v


def breakeven(monthly_price: int, token_price: int) -> Optional[float]:
    """Reconocimientos mensuales en los que ambos planes cuestan lo mismo."""
    if token_price <= 0:
        return None
    return monthly_price / token_price


def compare(customers, visits_per_customer=1.0,
            monthly_price: Optional[int] = None, token_price: Optional[int] = None) -> Comparison:
    c, v = validate_inputs(customers, visits_per_customer)
    mp = settings.monthly_price() if monthly_price is None else int(monthly_price)
    tp = settings.token_price() if token_price is None else int(token_price)

    recognitions = int(round(c * v))
    token_cost = recognitions * tp
    if token_cost < mp:
        cheaper = MODEL_TOKENS
    elif token_cost > mp:
        cheaper = MODEL_MONTHLY
    else:
        cheaper = "IGUAL"
    return Comparison(
        customers=c, visits_per_customer=v, recognitions=recognitions,
        monthly_price=mp, token_price=tp, monthly_cost=mp, token_cost=token_cost,
        difference=abs(mp - token_cost), cheaper=cheaper, breakeven=breakeven(mp, tp),
    )


def cost_curve(monthly_price: int, token_price: int, max_recognitions: int, points: int = 60) -> list[dict]:
    """Serie para graficar costo vs reconocimientos (ambos planes)."""
    max_recognitions = max(int(max_recognitions), 1)
    step = max(max_recognitions / (points - 1), 1)
    rows = []
    x = 0.0
    while x <= max_recognitions + 1e-9:
        rows.append({"reconocimientos": round(x), "mensualidad": monthly_price, "tokens": round(x) * token_price})
        x += step
    return rows


def breakeven_sentence(monthly_price: int, token_price: int) -> str:
    """Frase objetiva del punto de equilibrio (sin favorecer ningún plan)."""
    be = breakeven(monthly_price, token_price)
    if be is None:
        return "Con el precio de token actual el punto de equilibrio no está definido."
    be_txt = f"{round(be):,}".replace(",", ".")
    return (f"Con aproximadamente {be_txt} reconocimientos mensuales ambos modelos tienen un costo similar. "
            f"Por debajo de ese volumen el pago por tokens cuesta menos; por encima, la mensualidad cuesta menos.")
