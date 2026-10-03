"""Conexão SQLite e aplicação do schema (db/schema.sql)."""
import re
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


_ADD_COLUNA = re.compile(r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+(?:COLUMN\s+)?(\w+)", re.I)


def _sem_comentarios_iniciais(sql: str) -> str:
    return re.sub(r"^(?:\s*--[^\n]*\n)+", "", sql + "\n").strip()


def executar_script_idempotente(con: sqlite3.Connection, texto: str) -> None:
    """Executa um script SQL statement a statement.

    Diferença para executescript(): `ALTER TABLE ... ADD COLUMN` de uma coluna que já existe
    é ignorado. O SQLite não tem ADD COLUMN IF NOT EXISTS, e o schema.sql de um banco novo
    já inclui colunas que migrações antigas adicionam em bancos existentes.
    """
    buf = ""
    for linha in texto.splitlines(keepends=True):
        buf += linha
        if not sqlite3.complete_statement(buf):
            continue
        sql, buf = buf.strip(), ""
        limpo = _sem_comentarios_iniciais(sql)
        if not limpo:
            continue
        m = _ADD_COLUNA.match(limpo)
        if m:
            tabela, coluna = m.groups()
            existentes = {r[1].lower() for r in con.execute(f"PRAGMA table_info({tabela})")}
            if coluna.lower() in existentes:
                continue
        con.execute(sql)
    if re.sub(r"--[^\n]*", "", buf).strip():
        con.execute(buf)


def aplicar_migracoes() -> None:
    """Aplica db/migrations/*.sql em ordem, uma vez cada (registro em tabela migracao)."""
    con = connect()
    con.execute("CREATE TABLE IF NOT EXISTS migracao (nome TEXT PRIMARY KEY, aplicada_em TEXT DEFAULT (datetime('now')))")
    feitas = {r[0] for r in con.execute("SELECT nome FROM migracao")}
    for arq in sorted(MIGRACOES.glob("*.sql")):
        if arq.name in feitas:
            continue
        try:
            executar_script_idempotente(con, arq.read_text(encoding="utf-8"))
        except Exception:
            con.rollback()
            raise
        con.execute("INSERT INTO migracao (nome) VALUES (?)", (arq.name,))
        con.commit()
    con.close()
