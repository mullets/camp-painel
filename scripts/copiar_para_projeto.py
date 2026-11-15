#!/usr/bin/env python3
"""Copiar para um projeto as folhas de outros projetos (15/11/2026, Memorial Residências F010-P0732).

O CAMP Vision dividiu o lote "Memorial Residências" em projetos, um por casa, e o memorial ficou vazio. O Rafael quer manter os
projetos das casas e ter CÓPIAS das folhas deles no memorial, com o registro "copiada de / copiada para".

Usa a mesma rotina da tela "Copiar folhas para outro projeto" (app.copiar.copiar): código novo na faixa do painel (D90001+), mesma
imagem e dados, a conferir, não publicada; a original não muda; eventos dos dois lados. Nada no QNAP nem no site.

PADRÃO = SIMULAR (nada é gravado: tudo roda numa transação desfeita no fim).

No servidor do painel:
  cd ~/camp-painel && source .venv/bin/activate
  PYTHONPATH=backend python scripts/copiar_para_projeto.py --destino F010-P0732 --da-pasta Memorial          # simula
  PYTHONPATH=backend python scripts/copiar_para_projeto.py --destino F010-P0732 --da-pasta Memorial --aplicar
  Origens também podem ser dadas à mão: --origem F010-P0735 --origem F014-P0063 (pode repetir).
  --da-pasta TEXTO acha os projetos com lote cuja pasta ou nome contém TEXTO (sem diferenciar maiúsculas).
  Desfazer: --desfazer ARQUIVO.json (simula) e com --aplicar (retira as cópias criadas; as originais não mudam).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

ATOR = "copiar para projeto (script)"


def _con():
    from app.db import connect
    return connect()


def _origens(con, destino: str, maos: list[str], pasta: str | None) -> list[str]:
    out = list(dict.fromkeys(maos))
    if pasta:
        q = f"%{pasta.lower()}%"
        rows = con.execute("""SELECT DISTINCT i.projeto_codigo FROM item i JOIN lista_processamento l ON l.id=i.lote_id
                              WHERE (lower(l.pasta_qnap) LIKE ? OR lower(l.nome) LIKE ?) ORDER BY i.projeto_codigo""", (q, q)).fetchall()
        out += [r[0] for r in rows if r[0] not in out]
    return [c for c in out if c and c != destino]


def _folhas(con, proj: str) -> list[str]:
    # folhas do painel (as "só no site" não são linhas de item); cópias de formato ficam de fora (copia-se a original)
    return [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL "
                                      "ORDER BY serie_codigo, sequencial", (proj,))]


def _titulo(con, proj: str) -> str:
    r = con.execute("SELECT titulo FROM projeto WHERE codigo=?", (proj,)).fetchone()
    return (r[0] if r else "?") or ""


def copiar(a) -> None:
    from app import copiar as cp
    con = _con()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (a.destino,)).fetchone():
            sys.exit(f"ERRO: o projeto de destino {a.destino} não existe.")
        origens = _origens(con, a.destino, a.origem or [], a.da_pasta)
        if not origens:
            sys.exit("Nenhum projeto de origem encontrado. Use --origem F0xx-P0yyy ou --da-pasta TEXTO.")
        print(f"{'SIMULAÇÃO (nada é gravado)' if not a.aplicar else 'APLICANDO'} · destino {a.destino} “{_titulo(con, a.destino)}”\n")
        con.execute("BEGIN IMMEDIATE")
        feitas, total = [], 0
        for o in origens:
            cods = _folhas(con, o)
            if not cods:
                print(f"  {o} “{_titulo(con, o)}”: sem folhas para copiar")
                continue
            r = cp.copiar(con, cods, a.destino, ATOR, f"cópia do projeto {o} para {a.destino}")
            n = len(r["copiadas"])
            total += n
            feitas += r["copiadas"]
            print(f"  {o} “{_titulo(con, o)}”: {n} folha(s) copiada(s)" + (f", {len(r['ignorados'])} não (ex.: {r['ignorados'][0]['motivo']})" if r["ignorados"] else ""))
            for x in r["copiadas"][:3]:
                print(f"      {x['de']}  →  {x['para']}")
            if n > 3:
                print(f"      … e mais {n - 3}")
        print(f"\nTOTAL: {total} folha(s) copiada(s) para {a.destino} de {len(origens)} projeto(s).")
        if not a.aplicar:
            con.execute("ROLLBACK")
            print("NADA foi gravado. Para aplicar, rode o mesmo comando com --aplicar.")
            return
        con.execute("COMMIT")
        arq = Path.home() / f"copiar_para_{a.destino}_{datetime.now():%Y%m%d_%H%M%S}.json"
        arq.write_text(json.dumps({"destino": a.destino, "copiadas": feitas}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Feito. Lista das cópias (para desfazer): {arq}")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def desfazer(a) -> None:
    d = json.loads(Path(a.desfazer).read_text(encoding="utf-8"))
    cods = [x["para"] for x in d.get("copiadas", [])]
    con = _con()
    try:
        con.execute("BEGIN IMMEDIATE")
        presos = [c for c in cods if con.execute("SELECT 1 FROM item WHERE codigo=? AND (tainacan_item_id IS NOT NULL OR status_site='no_ar')", (c,)).fetchone()]
        if presos:
            con.execute("ROLLBACK")
            sys.exit(f"RECUSADO: {len(presos)} cópia(s) já foram para o site (ex.: {presos[0]}). Despublique antes. Nada foi desfeito.")
        n = 0
        for c in cods:
            for t, col in (("item_agente", "item_codigo"), ("revisao_campo", "item_codigo"), ("item_localizacao", "item_codigo")):
                try:
                    con.execute(f"DELETE FROM {t} WHERE {col}=?", (c,))
                except Exception:  # tabela ausente em banco antigo
                    pass
            n += con.execute("DELETE FROM item WHERE codigo=?", (c,)).rowcount
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'copia_desfeita',?,?)",
                        (c, ATOR, json.dumps({"arquivo": str(a.desfazer)}, ensure_ascii=False)))
        print(f"{'SIMULAÇÃO' if not a.aplicar else 'APLICANDO'}: {n} cópia(s) seriam retiradas de {d.get('destino')}; as originais não mudam.")
        con.execute("COMMIT" if a.aplicar else "ROLLBACK")
        if not a.aplicar:
            print("NADA foi gravado. Para desfazer de verdade, repita com --aplicar.")
    finally:
        con.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--destino")
    p.add_argument("--origem", action="append")
    p.add_argument("--da-pasta")
    p.add_argument("--aplicar", action="store_true")
    p.add_argument("--desfazer")
    a = p.parse_args(argv)
    if a.desfazer:
        return desfazer(a)
    if not a.destino:
        p.error("--destino é obrigatório")
    copiar(a)


if __name__ == "__main__":
    main()
