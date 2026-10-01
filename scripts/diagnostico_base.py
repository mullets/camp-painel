#!/usr/bin/env python3
"""Diagnóstico seguro das bases SQLite do CAMP Painel.

Não altera nenhum banco. Resolve o CAMP_DB_PATH exatamente como a aplicação e
compara com outros .db encontrados no repositório para evitar subir uma base
vazia por engano.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    p = BACKEND / ".env"
    if not p.exists():
        return env
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolver_db() -> Path:
    env = ler_env()
    raw = env.get("CAMP_DB_PATH") or os.getenv("CAMP_DB_PATH") or "./camp.db"
    p = Path(raw)
    if not p.is_absolute():
        p = (BACKEND / p).resolve()
    return p


def counts(path: Path) -> dict:
    out = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "fundos": None,
        "projetos": None,
        "itens": None,
        "usuarios": None,
        "erro": None,
    }
    if not path.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        for table, key in [
            ("fundo", "fundos"),
            ("projeto", "projetos"),
            ("item", "itens"),
            ("usuario", "usuarios"),
        ]:
            try:
                out[key] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                out[key] = None
        con.close()
    except Exception as e:
        out["erro"] = str(e)
    return out


def score(info: dict) -> int:
    return sum(int(info.get(k) or 0) for k in ("fundos", "projetos", "itens", "usuarios"))


def main() -> int:
    atual = resolver_db()
    candidatos = {atual}
    for p in ROOT.glob("*.db"):
        candidatos.add(p.resolve())
    for p in BACKEND.glob("*.db"):
        candidatos.add(p.resolve())
    infos = [counts(p) for p in sorted(candidatos)]
    atual_info = next(x for x in infos if x["path"] == str(atual))
    outros = sorted((x for x in infos if x["path"] != str(atual)), key=score, reverse=True)

    print(json.dumps({
        "db_configurado": atual_info,
        "outros_bancos_encontrados": outros,
    }, ensure_ascii=False, indent=2))

    # Banco inexistente ou claramente vazio: nunca deixar updater reiniciar em silêncio.
    if not atual_info["exists"]:
        print("\nERRO: banco configurado não existe. Atualização abortada.", flush=True)
        return 20

    fundos = atual_info.get("fundos")
    usuarios = atual_info.get("usuarios")
    if fundos == 0 or usuarios == 0:
        melhor = outros[0] if outros else None
        print("\nERRO: o banco configurado parece vazio/inicial.", flush=True)
        if melhor and score(melhor) > score(atual_info):
            print(f"Existe outro banco com mais dados: {melhor['path']}", flush=True)
        print("Atualização abortada para proteger a base.", flush=True)
        return 21

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
