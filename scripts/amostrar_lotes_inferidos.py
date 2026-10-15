#!/usr/bin/env python3
"""CAMP-051 · Amostra dos lotes "inferidos" (os 53): sorteia 10% estratificado por fundo, gera o relatório CSV para o Rafa revisar e registra a decisão por lote.
NÃO libera nada sozinho (só diz se a amostra foi validada; quem libera o resto é uma pessoa).

PADRÃO: só MOSTRA a população e a amostra que seria sorteada (--simular). Para gravar:
  --sortear [--semente TEXTO] [--percentual 10] [--refazer]   grava a amostra (idempotente; reprodutível pela semente)
  --csv ARQUIVO                                               escreve o relatório CSV (com as decisões já registradas)
  --decidir LOTE --decisao aprovado|reprovado --motivo "..." --por email
  --resumo                                                    quantos revisados e o que isso significa
  --ids 12,15,40                                              em vez do critério padrão (CAMP Vision sugeriu dados do projeto), usa estes lotes
Uso: python scripts/amostrar_lotes_inferidos.py [--simular] [--sortear] [--csv relatorio.csv] [--resumo] [--decidir N --decisao D --por E]"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", "--sim", action="store_true")
    ap.add_argument("--sortear", action="store_true")
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--semente", default="camp-051")
    ap.add_argument("--percentual", type=int, default=10)
    ap.add_argument("--ids")
    ap.add_argument("--csv")
    ap.add_argument("--decidir", type=int)
    ap.add_argument("--decisao")
    ap.add_argument("--motivo", default="")
    ap.add_argument("--por", default="")
    ap.add_argument("--resumo", action="store_true")
    a = ap.parse_args(argv)
    from app.db import connect, init_db, aplicar_migracoes
    from app import amostra_lotes as al
    init_db(); aplicar_migracoes()
    con = connect()
    ids = [int(x) for x in a.ids.split(",") if x.strip().isdigit()] if a.ids else None
    lotes = al.lotes_inferidos(con, ids)
    print(f"{len(lotes)} lote(s) inferido(s) em {len({l['fundo'] for l in lotes})} fundo(s)")
    if a.decidir is not None:
        if not a.por:
            print("Informe --por (e-mail de quem decide)."); return 2
        try:
            r = al.decidir(con, a.decidir, a.decisao or "", a.motivo, a.por)
        except ValueError as e:
            print("Não registrei:", e); return 2
        print(f"Decisão registrada: lote {r['lote_id']} {r['decisao']}")
    elif a.sortear:
        r = al.sortear(con, lotes, a.percentual, a.semente, a.refazer)
        print(f"Amostra: {r['novos']} lote(s) novo(s) sorteado(s); {r['total_amostra']} no total")
    else:
        plano = al.planejar(lotes, a.percentual, a.semente)
        print(f"SIMULAÇÃO: a amostra de {a.percentual}% teria {len(plano)} lote(s):")
        for l in plano:
            print(f"  fundo {l['fundo']}  lote {l['lote_id']}  {l['projeto']}  {l['motivo']}")
        print("Nada foi gravado. Para gravar: --sortear.")
    if a.csv:
        n = al.escrever_csv(con, lotes, a.csv)
        print(f"Relatório CSV: {a.csv} ({n} linha(s))")
    if a.resumo or a.decidir is not None:
        r = al.resumo(con, len(lotes))
        print(f"Amostra {r['amostra']} · aprovados {r['aprovados']} · reprovados {r['reprovados']} · faltam {r['faltam']}\n{r['conclusao']}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
