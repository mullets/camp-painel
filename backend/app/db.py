"""Conexão SQLite e aplicação do schema (db/schema.sql)."""
import sqlite3
from pathlib import Path

from .config import settings

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(settings.CAMP_DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    con = connect()
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fundo'"
    ).fetchone()
    if not existe:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.commit()
    con.close()
