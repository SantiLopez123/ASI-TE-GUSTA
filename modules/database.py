# -*- coding: utf-8 -*-
"""SQLite: conexión, creación automática de tablas y migraciones.

El usuario nunca ejecuta SQL a mano: `init_db()` crea todo en el primer
arranque y aplica migraciones pendientes en los siguientes.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

import config

# Ruta efectiva (las pruebas la reemplazan por una base temporal).
DB_PATH: Path = config.DB_PATH

MIGRATIONS: list[str] = [
    # ------------------------------------------------------------------ v1
    """
    CREATE TABLE IF NOT EXISTS customers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        birthday_day    INTEGER,
        birthday_month  INTEGER,
        usual_dish      TEXT,
        usual_drink     TEXT,
        preferences     TEXT,
        restrictions    TEXT,
        email           TEXT,
        phone           TEXT,
        visits_count    INTEGER NOT NULL DEFAULT 0,
        last_visit      TEXT,
        avg_ticket      INTEGER,
        is_demo         INTEGER NOT NULL DEFAULT 0,
        demo_key        TEXT,
        consent_given   INTEGER NOT NULL DEFAULT 0,
        consent_at      TEXT,
        face_enrolled   INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS face_embeddings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        embedding   BLOB    NOT NULL,
        model       TEXT,
        created_at  TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS token_transactions (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        kind                 TEXT    NOT NULL,   -- INITIAL | CONSUME | TOPUP | RESET
        delta                INTEGER NOT NULL,
        balance_after        INTEGER NOT NULL,
        customer_id          INTEGER REFERENCES customers(id) ON DELETE SET NULL,
        recognition_event_id INTEGER,
        note                 TEXT,
        created_at           TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS visits (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_code            TEXT    UNIQUE,
        customer_id           INTEGER REFERENCES customers(id) ON DELETE SET NULL,
        experiment_session_id TEXT,
        started_at            TEXT    NOT NULL,
        expires_at            TEXT    NOT NULL,
        closed_at             TEXT,
        source                TEXT,
        visit_number          INTEGER,
        prev_last_visit       TEXT,
        token_tx_id           INTEGER
    );

    CREATE TABLE IF NOT EXISTS recognition_events (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type            TEXT    NOT NULL,  -- CUSTOMER_RECOGNIZED | UNKNOWN_FACE
        customer_id           INTEGER REFERENCES customers(id) ON DELETE SET NULL,
        visit_code            TEXT,
        experiment_session_id TEXT,
        source                TEXT,              -- demo | camera | snapshot
        confidence            REAL,
        outcome               TEXT    NOT NULL,  -- CHARGED | COOLDOWN | NO_BALANCE | UNKNOWN
        token_consumed        INTEGER NOT NULL DEFAULT 0,
        balance_before        INTEGER,
        balance_after         INTEGER,
        visit_number          INTEGER,
        prev_last_visit       TEXT,
        created_at            TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS experiment_sessions (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id                  TEXT    NOT NULL UNIQUE,
        status                      TEXT    NOT NULL DEFAULT 'IN_PROGRESS',
        is_test                     INTEGER NOT NULL DEFAULT 0,
        date                        TEXT    NOT NULL,
        start_time                  TEXT    NOT NULL,
        end_time                    TEXT,
        duration_seconds            INTEGER,
        estimated_monthly_customers INTEGER,
        visits_per_customer         REAL,
        monthly_recognitions        INTEGER,
        monthly_fixed_cost          INTEGER,
        estimated_token_cost        INTEGER,
        breakeven_recognitions      REAL,
        cheaper_model_shown         TEXT,
        monthly_price_used          INTEGER,
        token_price_used            INTEGER,
        selected_model              TEXT,
        selected_model_reason       TEXT,
        choice_order                TEXT,
        pilot_requested             INTEGER,
        main_concern                TEXT,
        comments                    TEXT
    );

    CREATE TABLE IF NOT EXISTS experiment_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT,
        event_type  TEXT NOT NULL,
        page        TEXT,
        detail      TEXT,
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
        key        TEXT PRIMARY KEY,
        value      TEXT,
        updated_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_events_session ON experiment_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_recog_customer ON recognition_events(customer_id);
    CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id, closed_at);
    CREATE INDEX IF NOT EXISTS idx_embed_customer ON face_embeddings(customer_id);
    """,
]


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)  # transacciones manuales
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def db(immediate: bool = False):
    """Transacción: confirma al salir, revierte si hay excepción."""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crea/actualiza el esquema. Seguro de llamar muchas veces."""
    conn = _connect()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS, start=1):
            if version < i:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {i}")
    finally:
        conn.close()

    # Datos iniciales idempotentes
    from modules import customers, tokens  # import tardío: evita ciclos
    customers.seed_demo_customers()
    tokens.ensure_initial_balance()


# ---------------------------------------------------------------------------
# Helpers de consulta
# ---------------------------------------------------------------------------
def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


def scalar(sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
    with db() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row and row[0] is not None else default


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with db() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid or 0
