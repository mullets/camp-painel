#!/usr/bin/env python3
"""Folhas do F026 que foram giradas DIRETO no WordPress (a imagem no site já está certa): grava no painel o giro_manual delas,
para a prévia do painel e um reenvio futuro ficarem iguais ao site. NÃO envia nada ao site.

Convenção (backend/app/giro_imagem.py): giro_manual em graus no sentido HORÁRIO, 0/90/180/270.
  90° horário = 90 · 90° anti-horário = 270 · de cabeça para baixo = 180.
O giro feito no site foi aplicado sobre a imagem que o painel tinha enviado (que já levava o giro_manual de então),
por isso o valor gravado é (giro_manual atual + giro do site) % 360.

A folha é achada pelo projeto + número D (qualquer ano ou série). Mais de uma folha com o mesmo D no projeto = ambígua: avisa e não grava.
Folha sem registro no site (sem tainacan_item_id) também não é gravada: avisa.
Rodar 2x não soma de novo: a folha que já tem o evento 'giro_marcado' com o mesmo giro é pulada.

PADRÃO: só LISTA. Com --aplicar grava, com um evento 'giro_marcado' por folha.
Uso: python scripts/marcar_giro_publicado.py [--aplicar] [--ator email]"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

FUNDO = "F026"
H, A, C = 90, 270, 180     # horário, anti-horário, de cabeça para baixo
GIROS = {
    "P0092": {2: H, 3: H, 4: H, 5: H, 6: H, 9: H, 12: H, 7: A, 10: A, 13: A, 14: A},
    "P0084": {2: H, 3: H, 4: H, 5: A},
    "P0111": {4: H, 2: A},
    "P0030": {13: H, 11: A, 12: A, 1: C, 2: C, 4: C},
    "P0168": {12: C, 15: C},
    "P0095": {8: H, 16: H, 4: A, 19: A, 23: A, 24: A, 26: A, 28: A, 1: C},
}
NOME_GIRO = {90: "90° horário", 270: "90° anti-horário", 180: "180°"}


def planejar(con, giros: dict | None = None, fundo: str = FUNDO) -> list[dict]:
    """Uma linha por folha pedida: {projeto, d, giro, situacao, codigo?, de?, para?, motivo?}.
    situacao: 'gravar' | 'ja_marcada' | 'nao_achada' | 'ambigua' | 'fora_do_site'."""
    out = []
    for p, folhas in (giros or GIROS).items():
        proj = f"{fundo}-{p}"
        for d, giro in sorted(folhas.items()):
            linha = {"projeto": proj, "d": d, "giro": giro}
            achadas = {r["codigo"]: r for r in con.execute(
                "SELECT codigo, giro_manual, status_site, tainacan_item_id FROM item WHERE projeto_codigo=? AND (sequencial=? OR codigo LIKE ?)",
                (proj, d, f"{proj}-%-D{d:05d}"))}
            if not achadas:
                out.append({**linha, "situacao": "nao_achada", "motivo": "nenhuma folha com esse D no projeto"}); continue
            if len(achadas) > 1:
                out.append({**linha, "situacao": "ambigua", "motivo": "mais de uma folha com esse D: " + ", ".join(sorted(achadas))}); continue
            r = next(iter(achadas.values()))
            linha.update({"codigo": r["codigo"], "de": r["giro_manual"] or 0})
            if not r["tainacan_item_id"]:
                out.append({**linha, "situacao": "fora_do_site", "motivo": f"sem registro no site (situação: {r['status_site']})"}); continue
            ja = [json.loads(e[0] or "{}") for e in con.execute("SELECT detalhe FROM evento WHERE entidade='item' AND codigo=? AND tipo='giro_marcado'", (r["codigo"],))]
            if any(x.get("giro_no_site") == giro for x in ja):
                out.append({**linha, "situacao": "ja_marcada", "para": linha["de"]}); continue
            out.append({**linha, "situacao": "gravar", "para": (linha["de"] + giro) % 360})
    return out


def aplicar(con, plano: list[dict], ator: str) -> int:
    n = 0
    for x in plano:
        if x["situacao"] != "gravar":
            continue
        con.execute("UPDATE item SET giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (x["para"], x["codigo"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'giro_marcado',?,?)",
                    (x["codigo"], ator, json.dumps({"de": x["de"], "para": x["para"], "giro_no_site": x["giro"],
                                                     "motivo": "folha girada direto no site; nada foi reenviado"}, ensure_ascii=False)))
        n += 1
    con.commit()
    return n


def main(argv: list[str]) -> int:
    from app.db import connect
    gravar = "--aplicar" in argv
    ator = argv[argv.index("--ator") + 1] if "--ator" in argv and argv.index("--ator") + 1 < len(argv) else "script marcar_giro_publicado"
    con = connect()
    try:
        plano = planejar(con)
        rot = {"gravar": "vai gravar", "ja_marcada": "já marcada", "nao_achada": "NÃO ACHADA", "ambigua": "AMBÍGUA", "fora_do_site": "FORA DO SITE"}
        for x in plano:
            alvo = x.get("codigo") or f"{x['projeto']} D{x['d']:05d}"
            extra = f"giro_manual {x['de']} -> {x['para']}" if x["situacao"] in ("gravar", "ja_marcada") else x.get("motivo", "")
            print(f"  [{rot[x['situacao']]}] {alvo} · {NOME_GIRO[x['giro']]} · {extra}")
        conta = {k: sum(1 for x in plano if x["situacao"] == k) for k in rot}
        print(f"{len(plano)} folha(s): {conta['gravar']} a gravar, {conta['ja_marcada']} já marcada(s), {conta['nao_achada']} não achada(s), "
              f"{conta['ambigua']} ambígua(s), {conta['fora_do_site']} fora do site")
        if conta["ambigua"] or conta["nao_achada"] or conta["fora_do_site"]:
            print("ATENÇÃO: as folhas não achadas, ambíguas ou fora do site NÃO são gravadas. Confira à mão.")
        if not gravar:
            if conta["gravar"]:
                print("Nada foi alterado. Para gravar: python scripts/marcar_giro_publicado.py --aplicar")
            return 0
        n = aplicar(con, plano, ator)
        print(f"Gravado o giro de {n} folha(s). Nada foi enviado ao site.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
