# -*- coding: utf-8 -*-
"""Sesiones experimentales, trazabilidad de eventos, métricas y exportación CSV.

Una sesión = un participante anónimo (EXP-0001, EXP-0002...). Se registran los
eventos principales con marca de tiempo para poder reconstruir el recorrido.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

import config
from modules import database, settings, simulator, utils

STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETED = "COMPLETED"
STATUS_ABANDONED = "ABANDONED"

UPDATABLE_FIELDS = {
    "estimated_monthly_customers", "visits_per_customer", "monthly_recognitions",
    "monthly_fixed_cost", "estimated_token_cost", "breakeven_recognitions",
    "cheaper_model_shown", "monthly_price_used", "token_price_used",
    "selected_model", "selected_model_reason", "choice_order",
    "pilot_requested", "main_concern", "comments",
}


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------
def _next_session_id(conn, prefix: str) -> str:
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(session_id, ?) AS INTEGER)) FROM experiment_sessions WHERE session_id LIKE ?",
        (len(prefix) + 2, f"{prefix}-%"),
    ).fetchone()
    return f"{prefix}-{(row[0] or 0) + 1:04d}"


def start_session(is_test: Optional[bool] = None) -> str:
    """Crea una sesión nueva y registra SESSION_STARTED. Devuelve su identificador."""
    if is_test is None:
        is_test = settings.rehearsal_mode()
    prefix = config.TEST_SESSION_PREFIX if is_test else config.SESSION_PREFIX
    t = utils.now()
    with database.db(immediate=True) as conn:
        sid = _next_session_id(conn, prefix)
        conn.execute(
            "INSERT INTO experiment_sessions(session_id, status, is_test, date, start_time) VALUES(?,?,?,?,?)",
            (sid, STATUS_IN_PROGRESS, 1 if is_test else 0, t.strftime("%Y-%m-%d"), utils.to_str(t)),
        )
        log_event(sid, "SESSION_STARTED", detail={"is_test": bool(is_test)}, conn=conn)
    return sid


def get_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None
    return database.fetch_one("SELECT * FROM experiment_sessions WHERE session_id = ?", (session_id,))


def is_active(session_id: Optional[str]) -> bool:
    s = get_session(session_id)
    return bool(s and s["status"] == STATUS_IN_PROGRESS)


def update_session(session_id: str, **fields: Any) -> None:
    bad = set(fields) - UPDATABLE_FIELDS
    if bad:
        raise KeyError(f"Campos no permitidos: {sorted(bad)}")
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    database.execute(f"UPDATE experiment_sessions SET {cols} WHERE session_id = ?",
                     (*fields.values(), session_id))


def log_event(session_id: Optional[str], event_type: str, page: Optional[str] = None,
              detail: Optional[dict] = None, conn=None) -> None:
    """Registra un evento. Sin sesión activa no se registra nada."""
    if not session_id:
        return
    payload = json.dumps(detail, ensure_ascii=False, default=str) if detail else None
    row = (session_id, event_type, page, payload, utils.to_str(utils.now()))
    sql = "INSERT INTO experiment_events(session_id, event_type, page, detail, created_at) VALUES(?,?,?,?,?)"
    if conn is not None:
        conn.execute(sql, row)
    else:
        database.execute(sql, row)


def _close(session_id: str, status: str) -> None:
    s = get_session(session_id)
    if not s or s["status"] != STATUS_IN_PROGRESS:
        return
    end = utils.now()
    start = utils.parse_dt(s["start_time"]) or end
    database.execute(
        "UPDATE experiment_sessions SET status = ?, end_time = ?, duration_seconds = ? WHERE session_id = ?",
        (status, utils.to_str(end), max(0, int((end - start).total_seconds())), session_id),
    )


def abandon_active_sessions() -> int:
    """Marca como ABANDONED toda sesión en curso (p. ej., al preparar otra demo)."""
    rows = database.fetch_all("SELECT session_id FROM experiment_sessions WHERE status = ?",
                              (STATUS_IN_PROGRESS,))
    for r in rows:
        log_event(r["session_id"], "SESSION_ABANDONED")
        _close(r["session_id"], STATUS_ABANDONED)
    return len(rows)


# ---------------------------------------------------------------------------
# Acciones del recorrido
# ---------------------------------------------------------------------------
def record_simulation(session_id: Optional[str], customers, visits_per_customer=1.0) -> simulator.Comparison:
    """Calcula la comparación, la guarda en la sesión y registra el evento."""
    comp = simulator.compare(customers, visits_per_customer)
    if session_id:
        update_session(
            session_id,
            estimated_monthly_customers=comp.customers,
            visits_per_customer=comp.visits_per_customer,
            monthly_recognitions=comp.recognitions,
            monthly_fixed_cost=comp.monthly_cost,
            estimated_token_cost=comp.token_cost,
            breakeven_recognitions=comp.breakeven,
            cheaper_model_shown=comp.cheaper,
            monthly_price_used=comp.monthly_price,
            token_price_used=comp.token_price,
        )
        log_event(session_id, "SIMULATOR_VALUE_CHANGED", "simulator", {
            "customers": comp.customers, "visits_per_customer": comp.visits_per_customer,
            "recognitions": comp.recognitions, "monthly_cost": comp.monthly_cost,
            "token_cost": comp.token_cost, "cheaper": comp.cheaper,
        })
    return comp


def select_model(session_id: str, model: str, order: str) -> None:
    if model not in simulator.MODEL_LABELS:
        raise ValueError("Modelo de pago desconocido")
    update_session(session_id, selected_model=model, choice_order=order)
    log_event(session_id, "PAYMENT_MODEL_SELECTED", "decision", {"model": model, "order_shown": order})


def save_reason(session_id: str, reason: str) -> None:
    reason = (reason or "").strip()
    update_session(session_id, selected_model_reason=reason or None)
    log_event(session_id, "CHOICE_REASON_SUBMITTED", "decision", {"has_text": bool(reason)})


def set_pilot(session_id: str, requested: bool) -> None:
    update_session(session_id, pilot_requested=1 if requested else 0)
    log_event(session_id, "PILOT_SELECTED", "pilot", {"requested": bool(requested)})


def complete_session(session_id: str, concern: Optional[str], comments: Optional[str]) -> None:
    concern = concern or None
    comments = (comments or "").strip() or None
    update_session(session_id, main_concern=concern, comments=comments)
    log_event(session_id, "CONCERN_SUBMITTED", "finish",
              {"concern": concern, "has_comment": bool(comments)})
    log_event(session_id, "SESSION_COMPLETED", "finish")
    _close(session_id, STATUS_COMPLETED)


# ---------------------------------------------------------------------------
# Consultas, métricas y exportación
# ---------------------------------------------------------------------------
_SESSIONS_SQL = """
SELECT s.*,
  (SELECT COUNT(*) FROM experiment_events e WHERE e.session_id = s.session_id
       AND e.event_type = 'TOKEN_CONSUMED')               AS tokens_consumed_in_session,
  (SELECT COUNT(*) FROM experiment_events e WHERE e.session_id = s.session_id
       AND e.event_type = 'SIMULATOR_VALUE_CHANGED')      AS simulator_changes,
  (SELECT COUNT(*) FROM experiment_events e WHERE e.session_id = s.session_id
       AND e.event_type = 'PAYMENT_MODEL_SELECTED')       AS model_selections
FROM experiment_sessions s
{where}
ORDER BY s.id
"""


def _where(include_incomplete: bool, include_test: bool) -> str:
    clauses = []
    if not include_incomplete:
        clauses.append(f"s.status = '{STATUS_COMPLETED}'")
    if not include_test:
        clauses.append("s.is_test = 0")
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


def sessions_df(include_incomplete: bool = True, include_test: bool = True) -> pd.DataFrame:
    rows = database.fetch_all(_SESSIONS_SQL.format(where=_where(include_incomplete, include_test)))
    df = pd.DataFrame(rows)
    if df.empty:
        cols = [c for c in database.fetch_all("PRAGMA table_info(experiment_sessions)")]
        return pd.DataFrame(columns=[c["name"] for c in cols] +
                            ["tokens_consumed_in_session", "simulator_changes", "model_selections"])
    return df


def events_df(include_incomplete: bool = True, include_test: bool = True) -> pd.DataFrame:
    sess = sessions_df(include_incomplete, include_test)
    ids = list(sess["session_id"]) if not sess.empty else []
    if not ids:
        return pd.DataFrame(columns=["id", "session_id", "event_type", "page", "detail",
                                     "created_at", "seconds_from_start"])
    marks = ",".join("?" * len(ids))
    ev = pd.DataFrame(database.fetch_all(
        f"SELECT * FROM experiment_events WHERE session_id IN ({marks}) ORDER BY id", ids))
    if ev.empty:
        return pd.DataFrame(columns=["id", "session_id", "event_type", "page", "detail",
                                     "created_at", "seconds_from_start"])
    starts = sess.set_index("session_id")["start_time"].to_dict()
    ev["seconds_from_start"] = [
        int((pd.to_datetime(r.created_at) - pd.to_datetime(starts.get(r.session_id, r.created_at))).total_seconds())
        for r in ev.itertuples()
    ]
    return ev


def metrics(include_incomplete: bool = False, include_test: bool = False) -> dict:
    df = sessions_df(include_incomplete, include_test)
    total = len(df)

    def pct(n):
        return round(100 * n / total, 1) if total else None

    tokens_n = int((df["selected_model"] == simulator.MODEL_TOKENS).sum()) if total else 0
    monthly_n = int((df["selected_model"] == simulator.MODEL_MONTHLY).sum()) if total else 0
    pilot_yes = int((df["pilot_requested"] == 1).sum()) if total else 0
    pilot_no = int((df["pilot_requested"] == 0).sum()) if total else 0

    concerns = Counter(c for c in (df["main_concern"] if total else []) if isinstance(c, str) and c)
    all_df = sessions_df(True, True)
    return {
        "total": total,
        "tokens_n": tokens_n, "tokens_pct": pct(tokens_n),
        "monthly_n": monthly_n, "monthly_pct": pct(monthly_n),
        "pilot_n": pilot_yes, "pilot_pct": pct(pilot_yes), "pilot_no": pilot_no,
        "no_choice": total - tokens_n - monthly_n,
        "concerns": concerns.most_common(),
        "avg_duration": float(df["duration_seconds"].dropna().mean()) if total and df["duration_seconds"].notna().any() else None,
        "avg_customers": float(df["estimated_monthly_customers"].dropna().mean()) if total and df["estimated_monthly_customers"].notna().any() else None,
        "incomplete": int((all_df["status"] != STATUS_COMPLETED).sum()) if len(all_df) else 0,
        "test_sessions": int((all_df["is_test"] == 1).sum()) if len(all_df) else 0,
        "target": config.TARGET_PARTICIPANTS,
        "token_threshold": config.SUCCESS_TOKEN_MIN,
        "pilot_threshold": config.SUCCESS_PILOT_MIN,
    }


def _export(df: pd.DataFrame, stem: str, excel_format: bool) -> Path:
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_excel" if excel_format else ""
    path = config.EXPORT_DIR / f"asi_te_gusta_{stem}_{utils.now().strftime('%Y-%m-%d')}{suffix}.csv"
    # utf-8-sig: Excel abre bien tildes y ñ. ';' para Excel con configuración regional en español.
    df.to_csv(path, index=False, encoding="utf-8-sig", sep=";" if excel_format else ",")
    return path


def export_sessions_csv(include_incomplete: bool = True, include_test: bool = False,
                        excel_format: bool = False) -> Path:
    return _export(sessions_df(include_incomplete, include_test), "experiment_sessions", excel_format)


def export_events_csv(include_incomplete: bool = True, include_test: bool = False,
                      excel_format: bool = False) -> Path:
    return _export(events_df(include_incomplete, include_test), "experiment_events", excel_format)


# ---------------------------------------------------------------------------
# Reinicios y datos de ejemplo
# ---------------------------------------------------------------------------
def reset_experiment_data() -> None:
    """Borra sesiones y eventos del experimento y reinicia la numeración."""
    with database.db() as conn:
        conn.execute("DELETE FROM experiment_events")
        conn.execute("DELETE FROM experiment_sessions")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('experiment_events','experiment_sessions')")


def delete_test_sessions() -> int:
    with database.db() as conn:
        ids = [r[0] for r in conn.execute("SELECT session_id FROM experiment_sessions WHERE is_test = 1")]
        for sid in ids:
            conn.execute("DELETE FROM experiment_events WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM experiment_sessions WHERE is_test = 1")
    return len(ids)


def generate_sample_sessions(n: int = 10, seed: int = 7) -> list[str]:
    """Sesiones SINTÉTICAS marcadas como ensayo (PRB-xxxx) para ver el panel con datos.

    No cuentan en las métricas reales mientras `include_test` esté desactivado.
    """
    rng = random.Random(seed)
    concerns = config.CONCERN_OPTIONS
    created = []
    for _ in range(n):
        sid = start_session(is_test=True)
        customers = rng.choice([80, 150, 250, 300, 420, 600, 800, 1200])
        comp = record_simulation(sid, customers, 1.0)
        model = rng.choice([simulator.MODEL_TOKENS] * 3 + [simulator.MODEL_MONTHLY])
        select_model(sid, model, "TOKENS_FIRST")
        save_reason(sid, "Respuesta sintética de ejemplo")
        set_pilot(sid, rng.random() < 0.5)
        complete_session(sid, rng.choice(concerns), "SESIÓN DE EJEMPLO (sintética, no es un participante real)")
        # duración sintética plausible
        start = utils.parse_dt(get_session(sid)["start_time"])
        dur = rng.randint(240, 720)
        database.execute(
            "UPDATE experiment_sessions SET duration_seconds = ?, end_time = ? WHERE session_id = ?",
            (dur, utils.to_str(start + timedelta(seconds=dur)), sid))
        created.append(sid)
    return created
