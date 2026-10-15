#!/usr/bin/env python3
"""CAMP-047 · Roteiro: folhas que hoje são S07 (Redesenhos) passam a S08 (Redesenhos); S07 fica só "Publicações".
O código da folha muda (…-S07-D00001 → …-S08-D00001) e o antigo vira redirecionamento (que o site e o painel usam).

PADRÃO: só LISTA o que mudaria (--simular, o padrão). Nada roda sozinho, e este roteiro NÃO é para rodar em produção sem o Rafa.
  --aplicar            troca as folhas que NÃO estão no site (uma transação só: ou troca tudo, ou nada)
  --incluir-no-site    também troca as que já estão no site (passam pelo fluxo de redirecionamento do site: o redirecionamento fica na fila
                       de envio e o código/série no site são atualizados; falha do site vira pendência e não desfaz o local)
Uso: python scripts/migrar_serie_s08.py [--simular | --aplicar [--incluir-no-site]] [--ator email]"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", "--sim", action="store_true", help="só lista (padrão)")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--incluir-no-site", action="store_true")
    ap.add_argument("--ator", default="script:migrar_serie_s08")
    a = ap.parse_args(argv)
    from app.db import connect, aplicar_migracoes, init_db
    from app import serie_s08
    init_db(); aplicar_migracoes()
    con = connect()
    plano = serie_s08.planejar(con)
    print(f"{plano['total']} folha(s) S07 → S08: {plano['locais']} só no painel, {plano['no_site']} já no site, {plano['conflitos']} com conflito de código")
    for f in plano["folhas"]:
        marca = "CONFLITO " if f["conflito"] else ("no site  " if f["no_site"] else "local    ")
        print(f"  {marca}{f['antigo']} → {f['novo']}")
    if not a.aplicar or a.simular:
        print("\nSIMULAÇÃO: nada foi gravado. Para trocar de verdade: --aplicar (e --incluir-no-site para as que já estão no site).")
        con.close(); return 0
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        r = serie_s08.aplicar(con, a.ator, incluir_no_site=a.incluir_no_site)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    print(f"\nTrocadas: {len(r['trocadas'])} · ficaram de fora: {len(r['ignoradas'])}")
    for f in r["ignoradas"]:
        print(f"  ficou: {f['antigo']} ({f['motivo']})")
    if a.incluir_no_site and any(f["no_site"] for f in r["trocadas"]):
        s = serie_s08.atualizar_site_das_trocadas(r["trocadas"], a.ator)
        print(f"Site: {s['atualizadas']} atualizada(s), {len(s['falhas'])} falha(s) (viraram pendência)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
