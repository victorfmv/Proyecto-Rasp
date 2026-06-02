"""
app/database.py
Logs de acceso en SQLite usando la librería estándar (sin ORM extra).
Guarda cada intento de acceso: quién, cuándo, si fue autorizado.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("logs/access_log.db")


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # retorna filas como dicts
    return conn


def init_db():
    """Crea la tabla si no existe. Llamar una vez al inicio."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                authorized  INTEGER NOT NULL,
                confidence  REAL,
                action      TEXT
            )
        """)
    logger.info("Base de datos inicializada.")


def log_access(name: str, authorized: bool, confidence: float | None, action: str | None):
    """Registra un evento de acceso."""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO access_log (timestamp, name, authorized, confidence, action)
               VALUES (?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                name,
                1 if authorized else 0,
                round(confidence, 3) if confidence else None,
                action,
            ),
        )
    logger.debug(f"Log guardado: {name} | auth={authorized}")


def get_recent_logs(limit: int = 50) -> list[dict]:
    """Retorna los últimos N registros como lista de dicts."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM access_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    """Estadísticas básicas para mostrar en la UI."""
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM access_log").fetchone()[0]
        authorized = conn.execute(
            "SELECT COUNT(*) FROM access_log WHERE authorized=1"
        ).fetchone()[0]
        denied = total - authorized
        last_entry = conn.execute(
            "SELECT timestamp, name FROM access_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return {
        "total_attempts": total,
        "authorized": authorized,
        "denied": denied,
        "last_access": dict(last_entry) if last_entry else None,
    }
