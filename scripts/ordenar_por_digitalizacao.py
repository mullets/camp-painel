#!/usr/bin/env python3
"""Ordenar as folhas de um projeto pela ordem de digitalização (15/11/2026, Memorial Residências F010-P0732).

As cópias que vieram das casas entraram agrupadas por casa (D90001…); no lote original a ordem era a da digitalização.
Este script põe as folhas na ordem do arquivo original da estação (item.arquivo_origem: o nome que a estação deu ao scan, em
sequência), e grava como "ordem definida à mão" do projeto (a mesma rota do arrastar: rotas_projetos.gravar_ordem_folhas).
Os códigos NÃO mudam. "Voltar à ordem do código", na tela, desfaz.

PADRÃO = SIMULAR (só mostra a ordem nova, com o nome original de cada folha).
  cd ~/camp-painel && source .venv/bin/activate
  PYTHONPATH=backend python scripts/ordenar_por_digitalizacao.py --projeto F010-P0732
  PYTHONPATH=backend python scripts/ordenar_por_digitalizacao.py --projeto F010-P0732 --aplicar
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import PurePosixPath, PureWindowsPath

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))

ATOR = "ordenar por digitalização (script)"


def _primeira_origem(v: str | None) -> str:
    return (str(v or "").split(" | ")[0]).strip()


def _nome(origem: str) -> str:
    return (PureWindowsPath(origem).name if "\\" in origem else PurePosixPath(origem).name) if origem else ""


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def chave(row) -> tuple:
    """Ordem de digitalização: nome do arquivo original (natural: Scan_2 antes de Scan_10), depois o caminho; sem origem vai ao fim."""
    o = _primeira_origem(row["arquivo_origem"])
    return (0 if o else 1, _natural(_nome(o)), _natural(o), row["serie_codigo"] or "", row["sequencial"] or 0)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--projeto", required=True)
    p.add_argument("--aplicar", action="store_true")
    a = p.parse_args(argv)
    from app.db import connect
    con = connect()
    try:
        rows = con.execute("SELECT codigo, arquivo_origem, serie_codigo, sequencial, copiada_de FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL",
                           (a.projeto,)).fetchall()
    finally:
        con.close()
    if not rows:
        sys.exit(f"O projeto {a.projeto} não tem folhas.")
    ordem = sorted(rows, key=chave)
    print(f"{'SIMULAÇÃO (nada é gravado)' if not a.aplicar else 'APLICANDO'} · ordem de digitalização de {a.projeto} ({len(ordem)} folhas)\n")
    for k, r in enumerate(ordem, 1):
        o = _primeira_origem(r["arquivo_origem"])
        print(f"  {k:>3}. {r['codigo'][-6:]}  ← {_nome(o) or '(sem arquivo original)'}" + (f"   [cópia de {r['copiada_de']}]" if r["copiada_de"] else ""))
    sem = sum(1 for r in ordem if not _primeira_origem(r["arquivo_origem"]))
    if sem:
        print(f"\n  {sem} folha(s) sem arquivo original ficaram no fim.")
    if not a.aplicar:
        print("\nNADA foi gravado. Se a ordem estiver certa, repita com --aplicar. (Na tela, \"Voltar à ordem do código\" desfaz.)")
        return
    from fastapi import BackgroundTasks
    from app.rotas_projetos import OrdemFolhas, gravar_ordem_folhas
    tarefas = BackgroundTasks()
    r = gravar_ordem_folhas(a.projeto, OrdemFolhas(ordem=[x["codigo"] for x in ordem]), tarefas, {"email": ATOR})
    if r.get("vai_ao_site"):           # folhas já no site: manda a ordem ao site agora (o mesmo envio da tela)
        import asyncio
        asyncio.run(tarefas())
    print(f"\nFeito: ordem gravada ({r.get('mudaram_de_lugar', 0)} folha(s) mudaram de lugar){' e enviada ao site' if r.get('vai_ao_site') else ''}.")


if __name__ == "__main__":
    main()
