# -*- coding: utf-8 -*-
"""Tokens, visitas y reconocimiento de clientes.

Regla central del modelo de pago por consumo:

    cliente identificado  ->  evento CUSTOMER_RECOGNIZED  ->  1 token

* Un mismo cliente consume COMO MÁXIMO 1 token por visita. La visita dura
  `token_cooldown_minutes` (ventana fija desde el cobro).
* Si es detectado de nuevo dentro de esa ventana: no se cobra (COOLDOWN).
* Las personas no registradas (desconocidos) nunca consumen tokens.
* Sin saldo no se muestra el perfil (NO_BALANCE) y no se registra visita.

`process_recognition` es el ÚNICO punto de entrada: lo usan por igual la cámara
real, la foto instantánea y el modo demo, de modo que el flujo de negocio es
idéntico en los tres.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Optional

from modules import database, experiment, settings, utils

OUTCOME_CHARGED = "CHARGED"
OUTCOME_COOLDOWN = "COOLDOWN"
OUTCOME_NO_BALANCE = "NO_BALANCE"
OUTCOME_UNKNOWN = "UNKNOWN"


@dataclass
class RecognitionResult:
    status: str                      # CHARGED | COOLDOWN | NO_BALANCE | UNKNOWN
    source: str                      # demo | camera | snapshot
    token_consumed: int
    balance_before: int
    balance_after: int
    created_at: str
    customer: Optional[dict] = None
    visit_code: Optional[str] = None
    visit_number: Optional[int] = None
    prev_last_visit: Optional[str] = None
    cooldown_remaining_s: int = 0
    confidence: Optional[float] = None
    event_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Saldo (libro de movimientos)
# ---------------------------------------------------------------------------
def get_balance(conn=None) -> int:
    sql = "SELECT COALESCE(SUM(delta), 0) FROM token_transactions"
    if conn is not None:
        return int(conn.execute(sql).fetchone()[0])
    return int(database.scalar(sql))


def _add_transaction(conn, kind: str, delta: int, *, customer_id=None, event_id=None,
                     note: Optional[str] = None, when: Optional[datetime] = None) -> int:
    balance = get_balance(conn) + delta
    cur = conn.execute(
        """INSERT INTO token_transactions(kind, delta, balance_after, customer_id,
               recognition_event_id, note, created_at) VALUES(?,?,?,?,?,?,?)""",
        (kind, delta, balance, customer_id, event_id, note, utils.to_str(when or utils.now())),
    )
    return cur.lastrowid


def ensure_initial_balance() -> None:
    """Primer arranque: abona el saldo inicial si el libro está vacío."""
    with database.db(immediate=True) as conn:
        n = conn.execute("SELECT COUNT(*) FROM token_transactions").fetchone()[0]
        if n == 0:
            _add_transaction(conn, "INITIAL", settings.initial_token_balance(), note="Saldo inicial")


def top_up(amount: int, note: str = "Recarga (demo)") -> int:
    if amount <= 0:
        raise ValueError("La recarga debe ser mayor que cero.")
    with database.db(immediate=True) as conn:
        _add_transaction(conn, "TOPUP", int(amount), note=note)
        return get_balance(conn)


def reset_balance(to: Optional[int] = None) -> int:
    """Deja el saldo en `to` (por defecto el saldo inicial configurado)."""
    target = settings.initial_token_balance() if to is None else int(to)
    with database.db(immediate=True) as conn:
        current = get_balance(conn)
        if current != target:
            _add_transaction(conn, "RESET", target - current, note="Saldo restablecido")
        return target


def wipe_ledger_and_visits() -> None:
    """Borra libro, visitas y eventos de reconocimiento y reabona el saldo inicial."""
    with database.db(immediate=True) as conn:
        for table in ("recognition_events", "visits", "token_transactions"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN "
                     "('recognition_events','visits','token_transactions')")
        _add_transaction(conn, "INITIAL", settings.initial_token_balance(), note="Saldo inicial")


def close_open_visits() -> int:
    """Cierra todas las visitas abiertas (así nadie queda 'en cooldown')."""
    with database.db() as conn:
        cur = conn.execute("UPDATE visits SET closed_at = ? WHERE closed_at IS NULL",
                           (utils.to_str(utils.now()),))
        return cur.rowcount


def total_consumed() -> int:
    return int(-database.scalar("SELECT COALESCE(SUM(delta), 0) FROM token_transactions WHERE kind = 'CONSUME'"))


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------
def _active_visit(conn, customer_id: int, now: datetime) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM visits WHERE customer_id = ? AND closed_at IS NULL AND expires_at > ? "
        "ORDER BY id DESC LIMIT 1",
        (customer_id, utils.to_str(now)),
    ).fetchone()
    return dict(row) if row else None


def active_visit(customer_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """Visita abierta (dentro del cooldown) de un cliente, o None."""
    now = now or utils.now()
    with database.db() as conn:
        return _active_visit(conn, customer_id, now)


def process_recognition(customer_id: Optional[int], *, source: str,
                        confidence: Optional[float] = None,
                        session_id: Optional[str] = None,
                        now: Optional[datetime] = None) -> RecognitionResult:
    """Procesa una identificación. `customer_id=None` = rostro desconocido."""
    now = now or utils.now()
    now_s = utils.to_str(now)
    cooldown = timedelta(minutes=settings.cooldown_minutes())

    with database.db(immediate=True) as conn:
        balance = get_balance(conn)
        customer = None
        if customer_id is not None:
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
            customer = dict(row) if row else None

        # ---- Desconocido: nunca consume tokens --------------------------------
        if customer is None:
            cur = conn.execute(
                """INSERT INTO recognition_events(event_type, customer_id, experiment_session_id, source,
                       confidence, outcome, token_consumed, balance_before, balance_after, created_at)
                   VALUES('UNKNOWN_FACE', NULL, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (session_id, source, confidence, OUTCOME_UNKNOWN, balance, balance, now_s))
            experiment.log_event(session_id, "UNKNOWN_FACE_DETECTED", "recognition",
                                 {"source": source, "token_consumed": 0}, conn=conn)
            return RecognitionResult(
                status=OUTCOME_UNKNOWN, source=source, token_consumed=0, balance_before=balance,
                balance_after=balance, created_at=now_s, confidence=confidence, event_id=cur.lastrowid)

        # ---- Cliente ya reconocido en esta visita: no se cobra --------------------
        visit = _active_visit(conn, customer["id"], now)
        if visit is not None:
            remaining = int((utils.parse_dt(visit["expires_at"]) - now).total_seconds())
            cur = conn.execute(
                """INSERT INTO recognition_events(event_type, customer_id, visit_code, experiment_session_id,
                       source, confidence, outcome, token_consumed, balance_before, balance_after,
                       visit_number, prev_last_visit, created_at)
                   VALUES('CUSTOMER_RECOGNIZED', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)""",
                (customer["id"], visit["visit_code"], session_id, source, confidence, OUTCOME_COOLDOWN,
                 balance, balance, visit["visit_number"], visit["prev_last_visit"], now_s))
            experiment.log_event(session_id, "CUSTOMER_RECOGNIZED", "recognition", {
                "customer_id": customer["id"], "token_consumed": 0, "outcome": OUTCOME_COOLDOWN,
                "visit_code": visit["visit_code"], "source": source}, conn=conn)
            fresh = dict(conn.execute("SELECT * FROM customers WHERE id = ?", (customer["id"],)).fetchone())
            return RecognitionResult(
                status=OUTCOME_COOLDOWN, source=source, token_consumed=0, balance_before=balance,
                balance_after=balance, created_at=now_s, customer=fresh, visit_code=visit["visit_code"],
                visit_number=visit["visit_number"], prev_last_visit=visit["prev_last_visit"],
                cooldown_remaining_s=max(0, remaining), confidence=confidence, event_id=cur.lastrowid)

        # ---- Sin saldo: se identifica pero no se puede cobrar ni mostrar perfil -------
        if balance < 1:
            cur = conn.execute(
                """INSERT INTO recognition_events(event_type, customer_id, experiment_session_id, source,
                       confidence, outcome, token_consumed, balance_before, balance_after, created_at)
                   VALUES('CUSTOMER_RECOGNIZED', ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (customer["id"], session_id, source, confidence, OUTCOME_NO_BALANCE, balance, balance, now_s))
            experiment.log_event(session_id, "CUSTOMER_RECOGNIZED", "recognition", {
                "customer_id": customer["id"], "token_consumed": 0, "outcome": OUTCOME_NO_BALANCE,
                "source": source}, conn=conn)
            return RecognitionResult(
                status=OUTCOME_NO_BALANCE, source=source, token_consumed=0, balance_before=balance,
                balance_after=balance, created_at=now_s, customer={"id": customer["id"]},
                confidence=confidence, event_id=cur.lastrowid)

        # ---- Reconocimiento válido: 1 token + nueva visita --------------------------
        visit_number = int(customer["visits_count"]) + 1
        prev_last = customer["last_visit"]
        expires = utils.to_str(now + cooldown)
        vcur = conn.execute(
            """INSERT INTO visits(customer_id, experiment_session_id, started_at, expires_at, source,
                   visit_number, prev_last_visit) VALUES(?,?,?,?,?,?,?)""",
            (customer["id"], session_id, now_s, expires, source, visit_number, prev_last))
        visit_code = f"V-{vcur.lastrowid:05d}"
        conn.execute("UPDATE visits SET visit_code = ? WHERE id = ?", (visit_code, vcur.lastrowid))

        ecur = conn.execute(
            """INSERT INTO recognition_events(event_type, customer_id, visit_code, experiment_session_id,
                   source, confidence, outcome, token_consumed, balance_before, balance_after,
                   visit_number, prev_last_visit, created_at)
               VALUES('CUSTOMER_RECOGNIZED', ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (customer["id"], visit_code, session_id, source, confidence, OUTCOME_CHARGED,
             balance, balance - 1, visit_number, prev_last, now_s))
        tx_id = _add_transaction(conn, "CONSUME", -1, customer_id=customer["id"], event_id=ecur.lastrowid,
                                 note=f"Reconocimiento {visit_code}", when=now)
        conn.execute("UPDATE visits SET token_tx_id = ? WHERE id = ?", (tx_id, vcur.lastrowid))
        conn.execute("UPDATE customers SET visits_count = ?, last_visit = ? WHERE id = ?",
                     (visit_number, now_s, customer["id"]))

        experiment.log_event(session_id, "CUSTOMER_RECOGNIZED", "recognition", {
            "customer_id": customer["id"], "token_consumed": 1, "outcome": OUTCOME_CHARGED,
            "visit_code": visit_code, "source": source}, conn=conn)
        experiment.log_event(session_id, "TOKEN_CONSUMED", "recognition", {
            "customer_id": customer["id"], "balance_before": balance, "balance_after": balance - 1,
            "visit_code": visit_code}, conn=conn)

        fresh = dict(conn.execute("SELECT * FROM customers WHERE id = ?", (customer["id"],)).fetchone())
        return RecognitionResult(
            status=OUTCOME_CHARGED, source=source, token_consumed=1, balance_before=balance,
            balance_after=balance - 1, created_at=now_s, customer=fresh, visit_code=visit_code,
            visit_number=visit_number, prev_last_visit=prev_last,
            cooldown_remaining_s=int(cooldown.total_seconds()), confidence=confidence,
            event_id=ecur.lastrowid)
