# -*- coding: utf-8 -*-
"""Sondeo de disposición a pagar (Sprint 1 y 2): promedio de lo que pagarían los restaurantes y precio ajustado."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import config

SURVEY_CSV = config.BASE_DIR / "data" / "sondeo_precio.csv"


def load(path: Path = SURVEY_CSV) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


@dataclass(frozen=True)
class PriceRecommendation:
    n: int
    mensual_promedio: float
    mensual_mediana: float
    mensual_min: int
    mensual_max: int
    token_promedio: float
    token_mediana: float
    token_min: int
    token_max: int
    mensual_sugerido: int        # promedio redondeado a $5.000
    token_sugerido: int          # promedio redondeado a $50
    equilibrio: float            # reconocimientos/mes donde ambos planes cuestan lo mismo
    pct_tokens: float
    pct_piloto: float
    clientes_promedio: float
    ingreso_tokens_promedio: float   # lo que pagaría en promedio cada restaurante por tokens con su volumen


def recommend(df: pd.DataFrame) -> PriceRecommendation:
    m, t = df["pagaria_mensual_cop"], df["pagaria_token_cop"]
    mens, tok = _round_to(m.mean(), 5000), _round_to(t.mean(), 50)
    return PriceRecommendation(
        n=len(df), mensual_promedio=float(m.mean()), mensual_mediana=float(m.median()),
        mensual_min=int(m.min()), mensual_max=int(m.max()),
        token_promedio=float(t.mean()), token_mediana=float(t.median()), token_min=int(t.min()), token_max=int(t.max()),
        mensual_sugerido=mens, token_sugerido=tok, equilibrio=mens / tok if tok else 0.0,
        pct_tokens=100 * float((df["modelo_preferido"] == "Tokens").mean()),
        pct_piloto=100 * float((df["pediria_piloto"] == "Sí").mean()),
        clientes_promedio=float(df["clientes_frecuentes_mes"].mean()),
        ingreso_tokens_promedio=float((df["clientes_frecuentes_mes"] * tok).mean()),
    )


def per_restaurant(df: pd.DataFrame, rec: PriceRecommendation) -> pd.DataFrame:
    """Costo mensual de cada restaurante con los precios sugeridos y cuál le sale más barato."""
    out = df[["nombre", "municipio", "clientes_frecuentes_mes", "modelo_preferido"]].copy()
    out["costo_tokens"] = out["clientes_frecuentes_mes"] * rec.token_sugerido
    out["costo_mensualidad"] = rec.mensual_sugerido
    out["mas_economico"] = out.apply(lambda r: "Tokens" if r.costo_tokens < r.costo_mensualidad
                                     else ("Igual" if r.costo_tokens == r.costo_mensualidad else "Mensualidad"), axis=1)
    return out
