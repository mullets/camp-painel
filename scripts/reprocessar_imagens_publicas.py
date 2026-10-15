#!/usr/bin/env python3
"""CAMP-048 · Imagens públicas ≤ 1920 px: lista (e, se pedido, reenvia ao site) as folhas cuja imagem no site passa de 1920 px
ou subiu antes do limite (tamanho desconhecido). O reenvio troca o arquivo do anexo (mesmo ID) pelo derivado público (JPEG q85 sRGB, lado ≤ 1920),
feito da prévia do CAMP Vision. O TIF e a prévia de 3000 px nunca vão ao site.

PADRÃO: só LISTA (--simular / --sim). Reenviar: --aplicar [--limite N] [--fundo F026] [--projeto F026-P0001].
Uso: python scripts/reprocessar_imagens_publicas.py [--simular | --aplicar] [--limite N] [--fundo F] [--projeto P]"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", "--sim", action="store_true", help="só lista (padrão)")
    ap.add_argument("--aplicar", action="store_true", help="reenvia ao site")
    ap.add_argument("--limite", type=int, default=0, help="no máximo N folhas por execução (0 = todas)")
    ap.add_argument("--fundo")
    ap.add_argument("--projeto")
    ap.add_argument("--ator", default="script:reprocessar_imagens_publicas")
    a = ap.parse_args(argv)
    from app.db import connect, init_db, aplicar_migracoes
    from app import reprocessar_imagens as rp
    init_db(); aplicar_migracoes()
    con = connect()
    cand = rp.candidatos(con, a.fundo, a.projeto)
    con.close()
    print(f"{len(cand)} folha(s) com imagem pública acima de 1920 px ou de tamanho desconhecido")
    for c in cand:
        lado = f"{c['lado_no_site']} px" if c["lado_no_site"] else "tamanho desconhecido (subiu antes do limite)"
        print(f"  {c['codigo']}  anexo {c['media_id']}  {lado}" + ("" if c["tem_imagem_local"] else "  [SEM imagem local: não dá para reenviar]"))
    if not a.aplicar or a.simular:
        print("\nSIMULAÇÃO: nada foi enviado. Para reenviar: --aplicar (use --limite para ir aos poucos).")
        return 0
    feitas = falhas = 0
    for c in cand[: a.limite or None]:
        if not c["tem_imagem_local"]:
            falhas += 1; print(f"  PULOU {c['codigo']}: sem imagem local"); continue
        r = rp.reenviar(c["codigo"], a.ator)
        if r["ok"]:
            feitas += 1; print(f"  ok    {c['codigo']} → {r.get('lado_px')} px")
        else:
            falhas += 1; print(f"  FALHA {c['codigo']}: {r['erro']}")
    print(f"\nReenviadas: {feitas} · falhas: {falhas} · restam: {max(0, len(cand) - feitas - falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
