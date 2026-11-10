#!/usr/bin/env python3
"""Liga (ou desliga) "Sem legendas nas imagens do site" de um fundo (contrato painel ↔ site 1.9), pelo MESMO caminho da caixa no
"Editar" do fundo (PATCH /api/fundos/{codigo}: grava, evento 'editado', pendência 'pendente_sem_legendas_no_site' no mesmo commit)
e manda ao site na hora pela rota do hub (legendas_site.enviar). Falhou ou site antigo: a pendência fica e a rodada de reenvio refaz.
Fundo que ainda não está no site: grava no painel; o valor vai junto do "Enviar fundo ao site".

O fundo é achado pelo código (F006), pela sigla ou pelo nome (sem diferença de acento ou maiúscula); nome que acha mais de um = recusa.

PADRÃO: só SIMULA (mostra o fundo, o valor de agora, o novo e o que vai ao site). --aplicar grava; --desligar volta às legendas.
Uso: python scripts/fundo_sem_legendas.py --fundo "Chu Ming Silveira" [--desligar] [--aplicar] [--ator email]"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

ROTULO = {None: "nunca escolhido (com legendas)", 0: "desligado (com legendas)", 1: "ligado (sem legendas)"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().casefold()


def achar_fundo(con, termo: str) -> dict:
    termo = (termo or "").strip()
    r = con.execute("SELECT * FROM fundo WHERE UPPER(codigo)=? OR UPPER(COALESCE(sigla,''))=?", (termo.upper(), termo.upper())).fetchone()
    if r:
        return {"fundo": r}
    todos = con.execute("SELECT * FROM fundo ORDER BY codigo").fetchall()
    n = norm(termo)
    iguais = [f for f in todos if norm(f["titulo"]) == n]
    achados = iguais or [f for f in todos if n and n in norm(f["titulo"])]
    if len(achados) == 1:
        return {"fundo": achados[0]}
    if not achados:
        return {"erro": f"nenhum fundo com código, sigla ou nome \"{termo}\"", "candidatos": []}
    return {"erro": f"\"{termo}\" acha {len(achados)} fundos: use o código", "candidatos": [(f["codigo"], f["titulo"]) for f in achados]}


def planejar(con, termo: str, desligar: bool = False) -> dict:
    from app import legendas_site
    a = achar_fundo(con, termo)
    if "erro" in a:
        return {"ok": False, **a}
    f = a["fundo"]
    atual = f["sem_legendas"]
    novo = 0 if desligar else 1
    muda = (atual or 0) != novo
    d = con.execute("SELECT situacao FROM direitos_fundo WHERE fundo_codigo=?", (f["codigo"],)).fetchone()
    return {"ok": True, "codigo": f["codigo"], "titulo": f["titulo"], "termo": f["tainacan_term_id"], "atual": atual, "novo": novo, "muda": muda,
            "vai_ao_site": legendas_site.valor_hub(novo) if (muda and f["tainacan_term_id"]) else {}, "direitos": d[0] if d else "nao_definida"}


def aplicar(plano: dict, ator: str) -> dict:
    """Grava pela rota da tela e manda ao site na hora (sem esperar a tarefa em segundo plano)."""
    from fastapi import BackgroundTasks
    from app import legendas_site
    from app.rotas_fundos import EdicaoFundo, editar
    r = editar(plano["codigo"], EdicaoFundo(sem_legendas=bool(plano["novo"])), BackgroundTasks(), {"email": ator, "papel": "admin"})
    envio = legendas_site.enviar(plano["codigo"], ator) if r.get("sem_legendas_site") == "segundo_plano" else None
    return {**r, "envio": envio}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fundo", required=True, help="código (F006), sigla ou nome do fundo")
    ap.add_argument("--desligar", action="store_true", help="volta a mostrar as legendas")
    ap.add_argument("--aplicar", action="store_true", help="grava (sem isto, só simula)")
    ap.add_argument("--ator", default="script fundo_sem_legendas")
    a = ap.parse_args(argv)
    from app.db import connect
    con = connect()
    try:
        p = planejar(con, a.fundo, a.desligar)
    finally:
        con.close()
    if not p["ok"]:
        print(p["erro"])
        for c, t in p.get("candidatos", []):
            print(f"  {c}: {t}")
        return 2
    print(f"Fundo: {p['codigo']} · {p['titulo']} · {'no site (termo ' + str(p['termo']) + ')' if p['termo'] else 'ainda não está no site'} · direitos: {p['direitos']}")
    print(f"Sem legendas nas imagens do site: agora {ROTULO[p['atual']]} → {ROTULO[p['novo']]}")
    if not p["muda"]:
        print("Nada a fazer: já está assim."); return 0
    print("Vai ao site: " + (str(p["vai_ao_site"]) if p["vai_ao_site"] else "nada agora (vai junto do \"Enviar fundo ao site\")"))
    if not a.aplicar:
        print("\nSIMULAÇÃO: nada foi gravado. Para gravar: o mesmo comando com --aplicar"); return 0
    r = aplicar(p, a.ator)
    print("\nGravado no painel.")
    e = r.get("envio")
    if e is None:
        print("O fundo ainda não está no site: vai junto do \"Enviar fundo ao site\"."); return 0
    if e.get("erro"):
        print(f"O site não recebeu agora ({e['erro'][:200]}); ficou na lista do que falta enviar (a rodada de reenvio refaz)."); return 1
    print("Enviado ao site." if e.get("ok") else "Nada a enviar ao site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
