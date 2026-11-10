#!/usr/bin/env python3
"""Grava a biografia (história + fonte citada) de um arquiteto do painel a partir de um arquivo, pelo MESMO caminho da tela
(PATCH /api/agentes/{id}: exige fonte, grava o evento 'editado' e manda a biografia à página do arquiteto no site, nos fundos
dele que já estão no site; falha vira pendência 'pendente_hub_no_site' e a rodada de reenvio refaz).

Arquivo (ex.: docs/biografias/chu-ming-silveira.md): uma linha "Fonte: …" (a fonte citada) e, depois da primeira linha "---",
o texto (parágrafos separados por linha em branco). O texto vai como está.

O arquiteto é achado pelo id ou pelo nome, sem diferença de acento ou maiúscula; nome que acha mais de um = recusa.
Fundo do arquiteto com restrição de direitos REGISTRADA (restrito / não autorizado): mostra e NÃO grava, a não ser com
--mesmo-com-restricao (decisão de pessoa). A biografia não publica a página do arquiteto: com a página em rascunho, o texto
fica guardado no site e só aparece quando a página for publicada (o que a restrição continua impedindo).

PADRÃO: só SIMULA (mostra o arquiteto, o texto de agora e o novo, a fonte e para onde vai). --aplicar grava.
Uso: python scripts/gravar_biografia.py --agente "Chu Ming Silveira" --arquivo docs/biografias/chu-ming-silveira.md [--aplicar] [--ator email]"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

RESTRICOES = ("restrito", "nao_autorizado")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().casefold()


def ler_arquivo(caminho: str) -> tuple[str, str]:
    """(texto, fonte). Levanta ValueError se faltar a linha 'Fonte:' ou o texto depois de '---'."""
    linhas = pathlib.Path(caminho).read_text(encoding="utf-8").splitlines()
    if "---" not in [l.strip() for l in linhas]:
        raise ValueError("o arquivo precisa de uma linha '---' antes do texto")
    i = [l.strip() for l in linhas].index("---")
    fonte = next((l.split(":", 1)[1].strip() for l in linhas[:i] if l.strip().lower().startswith("fonte:")), "")
    texto = "\n".join(linhas[i + 1:]).strip()
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    if not fonte:
        raise ValueError("o arquivo precisa da linha 'Fonte: …' antes do '---' (história exige fonte citada)")
    if not texto:
        raise ValueError("o arquivo não tem texto depois do '---'")
    return texto, fonte


def achar_agente(con, termo: str) -> dict:
    """{'agente': row} ou {'erro': '…', 'candidatos': [...]}. Id, nome igual (sem acento/maiúscula) ou, sem nome igual, nome que contém."""
    termo = (termo or "").strip()
    if termo.isdigit():
        r = con.execute("SELECT * FROM agente WHERE id=?", (int(termo),)).fetchone()
        return {"agente": r} if r else {"erro": f"nenhum arquiteto com id {termo}", "candidatos": []}
    todos = con.execute("SELECT * FROM agente ORDER BY id").fetchall()
    n = norm(termo)
    iguais = [a for a in todos if norm(a["forma_autorizada"]) == n]
    achados = iguais or [a for a in todos if n and n in norm(a["forma_autorizada"])]
    if len(achados) == 1:
        return {"agente": achados[0]}
    if not achados:
        return {"erro": f"nenhum arquiteto com o nome \"{termo}\"", "candidatos": []}
    return {"erro": f"\"{termo}\" acha {len(achados)} arquitetos: use o id", "candidatos": [(a["id"], a["forma_autorizada"]) for a in achados]}


def fundos_do_agente(con, aid: int) -> list[dict]:
    out = []
    for f in con.execute("""SELECT f.codigo, f.titulo, f.tainacan_term_id, COALESCE(d.situacao,'nao_definida') AS direitos
                            FROM fundo_agente fa JOIN fundo f ON f.codigo=fa.fundo_codigo LEFT JOIN direitos_fundo d ON d.fundo_codigo=f.codigo
                            WHERE fa.agente_id=? AND fa.papel='produtor' ORDER BY f.codigo""", (aid,)):
        out.append(dict(f))
    return out


def planejar(con, termo: str, caminho: str) -> dict:
    texto, fonte = ler_arquivo(caminho)
    a = achar_agente(con, termo)
    if "erro" in a:
        return {"ok": False, **a}
    ag = a["agente"]
    fundos = fundos_do_agente(con, ag["id"])
    restritos = [f for f in fundos if f["direitos"] in RESTRICOES]
    igual = (ag["historia"] or "").strip() == texto and (ag["fonte_historia"] or "").strip() == fonte
    return {"ok": True, "id": ag["id"], "nome": ag["forma_autorizada"], "historia_atual": ag["historia"], "fonte_atual": ag["fonte_historia"],
            "historia_nova": texto, "fonte_nova": fonte, "igual": igual, "fundos": fundos, "restritos": restritos,
            "no_site": [f["codigo"] for f in fundos if f["tainacan_term_id"] and not str(f["codigo"]).upper().startswith("F000")]}


def aplicar(plano: dict, ator: str) -> dict:
    """Grava pelo caminho da tela (rotas_fundos.editar_agente)."""
    from app.rotas_fundos import EdicaoAgente, editar_agente
    return editar_agente(plano["id"], EdicaoAgente(historia=plano["historia_nova"], fonte_historia=plano["fonte_nova"]), {"email": ator, "papel": "admin"})


def _mostrar(p: dict) -> None:
    print(f"Arquiteto: {p['nome']} (id {p['id']})")
    for f in p["fundos"]:
        print(f"  fundo {f['codigo']} · {f['titulo']} · {'no site (termo ' + str(f['tainacan_term_id']) + ')' if f['tainacan_term_id'] else 'ainda não está no site'} · direitos: {f['direitos']}")
    print("\nTexto de AGORA no painel:\n" + ((p["historia_atual"] or "(vazio)").strip()))
    print(f"Fonte de agora: {p['fonte_atual'] or '(vazia)'}")
    print("\nTexto NOVO:\n" + p["historia_nova"])
    print(f"Fonte nova: {p['fonte_nova']}")
    print("\nVai à página do arquiteto no site nos fundos: " + (", ".join(p["no_site"]) or "nenhum (vai quando o fundo for ao site)"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agente", required=True, help="nome (sem diferença de acento) ou id do arquiteto")
    ap.add_argument("--arquivo", required=True)
    ap.add_argument("--aplicar", action="store_true", help="grava (sem isto, só simula)")
    ap.add_argument("--mesmo-com-restricao", action="store_true", help="grava mesmo com restrição de direitos registrada (decisão de pessoa)")
    ap.add_argument("--ator", default="script gravar_biografia")
    a = ap.parse_args(argv)
    from app.db import connect
    con = connect()
    try:
        p = planejar(con, a.agente, a.arquivo)
    except ValueError as e:
        print(f"Arquivo recusado: {e}"); return 2
    finally:
        con.close()
    if not p["ok"]:
        print(p["erro"])
        for i, nome in p.get("candidatos", []):
            print(f"  id {i}: {nome}")
        return 2
    _mostrar(p)
    if p["restritos"]:
        print("\nATENÇÃO: restrição de direitos registrada em " + ", ".join(f"{f['codigo']} ({f['direitos']})" for f in p["restritos"])
              + ". A página do arquiteto não pode ser publicada enquanto ela valer.")
    if p["igual"]:
        print("\nNada a fazer: o painel já tem este texto e esta fonte."); return 0
    if not a.aplicar:
        print("\nSIMULAÇÃO: nada foi gravado. Para gravar: o mesmo comando com --aplicar"); return 0
    if p["restritos"] and not a.mesmo_com_restricao:
        print("\nNÃO gravado: há restrição de direitos registrada. Se a família/titular liberou, registre em Fundo → Direitos, ou use --mesmo-com-restricao."); return 3
    r = aplicar(p, a.ator)
    hub = r.get("hub") or {}
    print(f"\nGravado no painel ({', '.join(r.get('campos') or [])}).")
    if hub.get("erro"):
        print(f"O site não recebeu agora ({hub['erro'][:200]}); ficou na lista do que falta enviar (a rodada de reenvio refaz)."); return 1
    print("Enviado à página do arquiteto no site: " + (", ".join(hub.get("fundos") or []) or "nenhum fundo no site ainda (vai junto quando for)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
