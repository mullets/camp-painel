"""Conexão SQLite e aplicação do schema (db/schema.sql)."""
import sqlite3
from pathlib import Path

from .config import settings

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def connect() -> sqlite3.Connection:
    # Espera por locks curtos em vez de derrubar a requisição com "database is locked".
    # WAL é ativado no startup; busy_timeout protege inclusive operações concorrentes.
    con = sqlite3.connect(settings.CAMP_DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    return con


def init_db() -> None:
    con = connect()
    # WAL permite leitores durante uma escrita longa do sincronizador.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fundo'"
    ).fetchone()
    if not existe:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.commit()
    con.close()


MIGRACOES = Path(__file__).resolve().parents[2] / "db" / "migrations"


def aplicar_migracoes() -> None:
    """Aplica db/migrations/*.sql em ordem, uma vez cada (registro em tabela migracao)."""
    con = connect()
    con.execute("CREATE TABLE IF NOT EXISTS migracao (nome TEXT PRIMARY KEY, aplicada_em TEXT DEFAULT (datetime('now')))")
    feitas = {r[0] for r in con.execute("SELECT nome FROM migracao")}
    for arq in sorted(MIGRACOES.glob("*.sql")):
        if arq.name in feitas:
            continue
        con.executescript(arq.read_text(encoding="utf-8"))
        con.execute("INSERT INTO migracao (nome) VALUES (?)", (arq.name,))
        con.commit()
    con.close()
