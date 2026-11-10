# -*- coding: utf-8 -*-
"""Clientes del restaurante: perfiles, datos DEMO, eliminación de datos."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

import config
from modules import database, utils

EMBEDDING_DIM = 128
MODEL_TAG = "opencv-sface-2021dec"

# Clientes de demostración (SIN rostro: sólo sirven para el modo demo).
DEMO_CUSTOMERS = [
    dict(demo_key="carlos", name="Carlos Gómez", birthday_day=18, birthday_month=11,
         usual_dish="Bandeja paisa sin aguacate", usual_drink="Coca-Cola Zero",
         preferences="Mesa interior", restrictions="",
         visits_count=16, last_days=12, avg_ticket=68_000),
    dict(demo_key="ana", name="Ana Martínez", birthday_day=25, birthday_month=10,
         usual_dish="Ajiaco santafereño", usual_drink="Limonada de coco",
         preferences="Mesa en la terraza", restrictions="Sin lácteos",
         visits_count=9, last_days=5, avg_ticket=54_000),
    dict(demo_key="luis", name="Luis Herrera", birthday_day=2, birthday_month=11,
         usual_dish="Sancocho de gallina", usual_drink="Cerveza artesanal",
         preferences="Barra, cerca de la cocina", restrictions="Sin picante",
         visits_count=24, last_days=3, avg_ticket=82_000),
    dict(demo_key="sofia", name="Sofía Restrepo", birthday_day=8, birthday_month=12,
         usual_dish="Salmón a la plancha con ensalada", usual_drink="Agua con gas",
         preferences="Mesa tranquila, lejos del ruido", restrictions="Alergia a los mariscos",
         visits_count=5, last_days=21, avg_ticket=71_000),
    dict(demo_key="valentina", name="Valentina Ríos", birthday_day=30, birthday_month=10,
         usual_dish="Pasta carbonara", usual_drink="Jugo de mora en leche",
         preferences="Mesa para cuatro junto a la ventana", restrictions="",
         visits_count=2, last_days=30, avg_ticket=46_000),
]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def list_customers(include_demo: bool = True) -> list[dict]:
    sql = "SELECT * FROM customers"
    if not include_demo:
        sql += " WHERE is_demo = 0"
    sql += " ORDER BY is_demo DESC, name COLLATE NOCASE"
    return database.fetch_all(sql)


def get_customer(customer_id: int) -> Optional[dict]:
    return database.fetch_one("SELECT * FROM customers WHERE id = ?", (customer_id,))


def count_customers(include_demo: bool = True) -> int:
    if include_demo:
        return int(database.scalar("SELECT COUNT(*) FROM customers"))
    return int(database.scalar("SELECT COUNT(*) FROM customers WHERE is_demo = 0"))


def count_enrolled_faces() -> int:
    return int(database.scalar("SELECT COUNT(*) FROM customers WHERE face_enrolled = 1"))


def name_exists(name: str) -> bool:
    return bool(database.scalar(
        "SELECT COUNT(*) FROM customers WHERE lower(trim(name)) = lower(trim(?))", (name,)))


def segment_label(visits: int) -> str:
    if visits >= config.FREQUENT_MIN_VISITS:
        return "Cliente frecuente"
    if visits >= 2:
        return "Cliente ocasional"
    return "Cliente nuevo"


def upcoming_birthdays(window_days: Optional[int] = None) -> list[dict]:
    """Clientes con cumpleaños dentro de la ventana, ordenados por cercanía."""
    window_days = config.BIRTHDAY_WINDOW_DAYS if window_days is None else window_days
    today = utils.now().date()
    out = []
    for c in list_customers():
        d = utils.days_until_birthday(c["birthday_day"], c["birthday_month"], today)
        if d is not None and d <= window_days:
            out.append({**c, "days_until": d})
    out.sort(key=lambda c: c["days_until"])
    return out


# ---------------------------------------------------------------------------
# Validación y alta
# ---------------------------------------------------------------------------
def validate_profile(data: dict) -> list[str]:
    errors: list[str] = []
    name = (data.get("name") or "").strip()
    if len(name) < 2:
        errors.append("Escribe el nombre del cliente.")
    elif len(name) > 80:
        errors.append("El nombre es demasiado largo (máximo 80 caracteres).")

    day, month = data.get("birthday_day"), data.get("birthday_month")
    if (day and not month) or (month and not day):
        errors.append("Para el cumpleaños indica día y mes (o deja ambos vacíos).")
    elif day and month:
        try:
            datetime(2024, int(month), int(day))      # 2024 es bisiesto
        except ValueError:
            errors.append("La fecha de cumpleaños no es válida.")

    email = (data.get("email") or "").strip()
    if email and not _EMAIL_RE.match(email):
        errors.append("El correo no parece válido (puedes dejarlo vacío).")
    phone = re.sub(r"[\s\-()+]", "", data.get("phone") or "")
    if phone and not (phone.isdigit() and 7 <= len(phone) <= 15):
        errors.append("El celular no parece válido (puedes dejarlo vacío).")
    return errors


def _clean(value) -> Optional[str]:
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def create_customer(data: dict, consent: bool, embeddings: Optional[list[np.ndarray]] = None) -> int:
    """Crea un cliente. Sin consentimiento NO se registra nada."""
    if not consent:
        raise PermissionError("Se requiere consentimiento explícito para registrar al cliente.")
    errors = validate_profile(data)
    if errors:
        raise ValueError(" ".join(errors))
    name = data["name"].strip()
    if name_exists(name):
        raise ValueError("Ya existe un cliente con ese nombre. Agrega un apellido o una inicial.")

    ts = utils.to_str(utils.now())
    embeddings = embeddings or []
    with database.db(immediate=True) as conn:
        cur = conn.execute(
            """INSERT INTO customers(name, birthday_day, birthday_month, usual_dish, usual_drink,
                   preferences, restrictions, email, phone, visits_count, last_visit, avg_ticket,
                   is_demo, consent_given, consent_at, face_enrolled, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,0,NULL,NULL,0,1,?,?,?)""",
            (name, data.get("birthday_day") or None, data.get("birthday_month") or None,
             _clean(data.get("usual_dish")), _clean(data.get("usual_drink")),
             _clean(data.get("preferences")), _clean(data.get("restrictions")),
             _clean(data.get("email")), _clean(data.get("phone")),
             ts, 1 if embeddings else 0, ts),
        )
        cid = cur.lastrowid
        for emb in embeddings:
            conn.execute(
                "INSERT INTO face_embeddings(customer_id, embedding, model, created_at) VALUES(?,?,?,?)",
                (cid, np.asarray(emb, dtype=np.float32).ravel().tobytes(), MODEL_TAG, ts),
            )
    return cid


# ---------------------------------------------------------------------------
# Biometría
# ---------------------------------------------------------------------------
def load_gallery() -> list[tuple[int, np.ndarray]]:
    """[(customer_id, embedding_normalizado)] de todos los rostros registrados."""
    rows = database.fetch_all("SELECT customer_id, embedding FROM face_embeddings")
    gallery = []
    for r in rows:
        emb = np.frombuffer(r["embedding"], dtype=np.float32)
        if emb.size != EMBEDDING_DIM:
            continue
        norm = float(np.linalg.norm(emb))
        if norm > 0:
            gallery.append((r["customer_id"], emb / norm))
    return gallery


def delete_biometrics(customer_id: int) -> None:
    """Elimina los datos biométricos del cliente pero conserva su perfil."""
    with database.db() as conn:
        conn.execute("DELETE FROM face_embeddings WHERE customer_id = ?", (customer_id,))
        conn.execute("UPDATE customers SET face_enrolled = 0 WHERE id = ?", (customer_id,))


def delete_all_biometrics() -> int:
    with database.db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM face_embeddings").fetchone()[0]
        conn.execute("DELETE FROM face_embeddings")
        conn.execute("UPDATE customers SET face_enrolled = 0")
    return n


def delete_customer(customer_id: int) -> bool:
    """Elimina perfil + biometría. Los eventos históricos quedan anonimizados."""
    with database.db() as conn:
        cur = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        return cur.rowcount > 0


def delete_registered_customers() -> int:
    """Elimina todos los clientes NO demo (y su biometría)."""
    with database.db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM customers WHERE is_demo = 0").fetchone()[0]
        conn.execute("DELETE FROM customers WHERE is_demo = 0")
    return n


# ---------------------------------------------------------------------------
# Datos DEMO
# ---------------------------------------------------------------------------
def _demo_last_visit(days: int) -> str:
    base = utils.now().replace(hour=19, minute=30, second=0)
    return utils.to_str(base - timedelta(days=days))


def seed_demo_customers() -> int:
    """Inserta los clientes DEMO que falten (idempotente). Devuelve cuántos creó."""
    created = 0
    ts = utils.to_str(utils.now())
    with database.db(immediate=True) as conn:
        existing = {r[0] for r in conn.execute(
            "SELECT demo_key FROM customers WHERE demo_key IS NOT NULL").fetchall()}
        for d in DEMO_CUSTOMERS:
            if d["demo_key"] in existing:
                continue
            conn.execute(
                """INSERT INTO customers(name, birthday_day, birthday_month, usual_dish, usual_drink,
                       preferences, restrictions, visits_count, last_visit, avg_ticket, is_demo,
                       demo_key, consent_given, consent_at, face_enrolled, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,1,?,1,?,0,?)""",
                (d["name"], d["birthday_day"], d["birthday_month"], d["usual_dish"], d["usual_drink"],
                 d["preferences"], d["restrictions"] or None, d["visits_count"],
                 _demo_last_visit(d["last_days"]), d["avg_ticket"], d["demo_key"], ts, ts),
            )
            created += 1
    return created


def reset_demo_customers() -> None:
    """Restaura visitas y última visita de los clientes DEMO a su estado inicial."""
    seed_demo_customers()
    with database.db() as conn:
        for d in DEMO_CUSTOMERS:
            conn.execute(
                "UPDATE customers SET visits_count = ?, last_visit = ?, avg_ticket = ? WHERE demo_key = ?",
                (d["visits_count"], _demo_last_visit(d["last_days"]), d["avg_ticket"], d["demo_key"]),
            )
