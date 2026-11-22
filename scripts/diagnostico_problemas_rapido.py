#!/usr/bin/env python3
"""Diagnóstico SÓ DE LEITURA das ações rápidas de Problemas (CAMP-PROB-REAL, 22/11/2026).

Para confirmar no servidor por que as linhas "Folha pode ser de outro projeto" não tinham botão nem miniatura. Abre o banco em modo
somente leitura (sqlite `mode=ro`): não grava, não migra, não toca no QNAP. Não imprime dado de pessoa (nem descrição, nem quem relatou,
nem e-mail): só códigos, fase, situação, origem, o começo da chave, se a folha existe e as CHAVES das pendências.

Uso (no servidor, na pasta do painel):
    python3 scripts/diagnostico_problemas_rapido.py              # o banco do .env (CAMP_DB_PATH), 12 exemplos
    python3 scripts/diagnostico_problemas_rapido.py /caminho/camp.db 30
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = re.compile(r"^(F\d{3})-(P\d{4})-(\d{4})-(S0[1-8]|S99)-D(\d{4,6})$")


def banco_padrao() -> str:
    v = os.environ.get("CAMP_DB_PATH")
    env = ROOT / "backend" / ".env"
    if not v and env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("CAMP_DB_PATH="):
                v = linha.split("=", 1)[1].strip().strip('"').strip("'")
    v = v or "./camp.db"
    return v if Path(v).is_absolute() else str((ROOT / "backend" / v).resolve())


def fala_de_outro(t) -> bool:      # o mesmo teste de importador_lote.fala_de_projeto_divergente
    t = "".join(ch for ch in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(ch) != "Mn").lower().replace("_", " ")
    return any(k in t for k in ("projeto divergente", "outro projeto", "outra obra", "outra pasta", "sem identificacao"))


def tipo_jpg(v) -> str:
    v = str(v or "")
    if not v:
        return "vazio"
    if v.startswith(("http://", "https://")):
        return "http"
    return ("absoluto " if v.startswith("/") else "relativo ") + (Path(v).suffix.lower() or "?")


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else banco_padrao()
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cfg = {r[0]: r[1] for r in con.execute("SELECT chave, valor FROM configuracao WHERE chave IN ('problemas.revisao_outra_pessoa','problemas.tipos_revisao')")}
    print(f"banco: {db} (somente leitura)")
    print(f"problemas.revisao_outra_pessoa = {cfg.get('problemas.revisao_outra_pessoa', '(padrão 0)')} · problemas.tipos_revisao = {cfg.get('problemas.tipos_revisao', '(padrão)')}")
    rows = [r for r in con.execute("""SELECT id, codigo, categoria, gravidade, situacao, fase, origem, chave FROM erro
                                      WHERE situacao IN ('aberto','em_correcao') ORDER BY (gravidade='bloqueia') DESC, id""")
            if r["categoria"] == "projeto_errado" or (r["origem"] == "campvision" and fala_de_outro(con.execute("SELECT descricao FROM erro WHERE id=?", (r["id"],)).fetchone()[0]))]
    resumo = Counter()
    linhas = []
    for r in rows:
        ch = r["chave"] or ""
        folha = ch[len("campvision:retirado:"):] if ch.startswith("campvision:retirado:") else (r["codigo"] if (r["codigo"] or "").count("-") >= 4 else None)
        it = con.execute("SELECT arquivo_jpg, pendencias FROM item WHERE codigo=?", (folha,)).fetchone() if folha else None
        try:
            pend = json.loads(it["pendencias"] or "{}") if it else None
        except ValueError:
            pend = {"(pendencias inválidas)": 1}
        ret = bool(folha) and con.execute("SELECT 1 FROM erro WHERE chave=?", (f"campvision:retirado:{folha}",)).fetchone() is not None
        lote = bool(folha) and con.execute("SELECT 1 FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL", (folha[:10],)).fetchone() is not None
        caso = ("sem folha (código do projeto)" if not folha else "folha no painel" if it else
                "folha fora do painel, retirada pelo CAMP Vision" if ret else "folha fora do painel, sem registro de retirada")
        resumo[(r["gravidade"], caso)] += 1
        if len(linhas) < n:
            linhas.append({"id": r["id"], "erro.codigo": r["codigo"], "gravidade": r["gravidade"], "situacao": r["situacao"], "fase": r["fase"], "origem": r["origem"],
                           "chave": (ch.split(":")[0] + ":" + ch.split(":")[1] + ":…") if ch.count(":") >= 2 else (ch or None),
                           "folha": folha, "formato_ok": bool(folha and DOC.match(folha)), "item_existe": bool(it), "retirada_registrada": ret, "lote_do_projeto": lote,
                           "arquivo_jpg": tipo_jpg(it["arquivo_jpg"]) if it else None,
                           "pendencias_chaves": sorted(pend.keys()) if isinstance(pend, dict) else None,
                           "previa_preenchida": bool(isinstance(pend, dict) and pend.get("previa")) if it else None, "caso": caso})
    print(f"\n{len(rows)} problemas abertos de 'folha de outro projeto'. Por gravidade e caso:")
    for (g, caso), k in sorted(resumo.items(), key=lambda t: -t[1]):
        print(f"  {k:5d}  {g:9s} {caso}")
    print(f"\nPrimeiros {len(linhas)} (bloqueia primeiro):")
    for x in linhas:
        print(json.dumps(x, ensure_ascii=False))
    con.close()


if __name__ == "__main__":
    main()
