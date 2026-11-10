# -*- coding: utf-8 -*-
"""Estado base de la demostración: todos los participantes parten del mismo punto."""
from __future__ import annotations

from modules import customers, tokens


def reset_demo_state() -> None:
    """Cierra visitas abiertas (sin cooldown), restablece los tokens al saldo inicial
    y devuelve a los clientes DEMO a sus visitas/última visita iniciales.

    No borra sesiones experimentales ni clientes registrados por personas reales.
    """
    tokens.close_open_visits()
    tokens.reset_balance()
    customers.reset_demo_customers()
