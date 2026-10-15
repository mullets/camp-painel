"""CAMP-051 · Amostra dos lotes "inferidos" (os 53 do aviso): 10% estratificado por fundo, relatório CSV para o Rafa revisar e decisão registrada por lote.
NÃO libera nada sozinho: só diz se a amostra foi validada; quem libera o resto é uma pessoa.

"Lote inferido" = lote (não descartado) em que o CAMP Vision SUGERIU dados do projeto em vez de lê-los do carimbo/pasta (bloco `projeto` do pacote:
programa/natureza sugeridos, lacunas): fica em lista_processamento.resultado → importacao.sugestoes_cv2. Outros critérios: `ids` (lista explícita)."""
from __future__ import annotations

import csv
import json
import math
import random

PERCENTUAL = 10


def lotes_inferidos(con, ids: list[int] | None = None) -> list[dict]:
    out = []
    for l in con.execute("""SELECT l.id, l.nome, l.projeto_codigo, l.resultado, l.etapa, p.fundo_codigo, p.titulo,
                                   (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id) AS folhas
                              FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo
                             WHERE l.descartado_em IS NULL ORDER BY p.fundo_codigo, l.id"""):
        if ids is not None:
            if l["id"] not in ids:
                continue
            motivo = "lote indicado na lista"
        else:
            try:
                sug = (json.loads(l["resultado"] or "{}") or {}).get("sugestoes_cv2") or {}      # gravado pela importação do lote (importador_lote)
            except ValueError:
                sug = {}
            if not sug:
                continue
            motivo = "CAMP Vision sugeriu: " + ", ".join(sorted(sug))
        out.append({"lote_id": l["id"], "nome": l["nome"], "projeto": l["projeto_codigo"], "titulo": l["titulo"], "fundo": l["fundo_codigo"], "folhas": l["folhas"], "etapa": l["etapa"], "motivo": motivo})
    return out


def planejar(lotes: list[dict], percentual: int = PERCENTUAL, semente: str = "camp-051") -> list[dict]:
    """10% (arredondado para cima, no mínimo 1) por fundo, sorteio reprodutível pela semente."""
    por_fundo: dict[str, list[dict]] = {}
    for l in lotes:
        por_fundo.setdefault(l["fundo"], []).append(l)
    sorteados = []
    for fundo, ls in sorted(por_fundo.items()):
        n = max(1, math.ceil(len(ls) * percentual / 100))
        rnd = random.Random(f"{semente}|{fundo}")
        sorteados += rnd.sample(sorted(ls, key=lambda x: x["lote_id"]), min(n, len(ls)))
    return sorteados


def sortear(con, lotes: list[dict], percentual: int = PERCENTUAL, semente: str = "camp-051", refazer: bool = False) -> dict:
    """Grava a amostra. Idempotente: lote já sorteado fica; `refazer` apaga só os sorteios SEM decisão antes de sortear de novo."""
    if refazer:
        con.execute("DELETE FROM amostra_lote_inferido WHERE decisao IS NULL")
    ja = {r[0] for r in con.execute("SELECT lote_id FROM amostra_lote_inferido")}
    existentes_por_fundo = {}
    for r in con.execute("SELECT fundo_codigo, COUNT(*) FROM amostra_lote_inferido GROUP BY fundo_codigo"):
        existentes_por_fundo[r[0]] = r[1]
    novos = 0
    for l in planejar(lotes, percentual, semente):
        if l["lote_id"] in ja or existentes_por_fundo.get(l["fundo"]):
            continue                                   # o fundo já tem amostra: não sorteia outra
        con.execute("INSERT OR IGNORE INTO amostra_lote_inferido (lote_id, fundo_codigo, semente) VALUES (?,?,?)", (l["lote_id"], l["fundo"], semente))
        novos += 1
    con.commit()
    return {"novos": novos, "total_amostra": con.execute("SELECT COUNT(*) FROM amostra_lote_inferido").fetchone()[0]}


def decidir(con, lote_id: int, decisao: str, motivo: str, por: str) -> dict:
    if decisao not in ("aprovado", "reprovado"):
        raise ValueError("decisão tem que ser 'aprovado' ou 'reprovado'")
    if decisao == "reprovado" and not (motivo or "").strip():
        raise ValueError("reprovar exige o motivo")
    r = con.execute("SELECT lote_id FROM amostra_lote_inferido WHERE lote_id=?", (lote_id,)).fetchone()
    if not r:
        raise ValueError(f"o lote {lote_id} não está na amostra (sorteie antes)")
    con.execute("UPDATE amostra_lote_inferido SET decisao=?, motivo=?, decidido_por=?, decidido_em=datetime('now') WHERE lote_id=?", (decisao, (motivo or "").strip()[:300] or None, por, lote_id))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'amostra_inferido_decisao',?,?)",
                (str(lote_id), por, json.dumps({"decisao": decisao, "motivo": (motivo or "").strip()[:300]}, ensure_ascii=False)))
    con.commit()
    return {"lote_id": lote_id, "decisao": decisao}


def resumo(con, total_populacao: int | None = None) -> dict:
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    n, ap, rp = q("SELECT COUNT(*) FROM amostra_lote_inferido"), q("SELECT COUNT(*) FROM amostra_lote_inferido WHERE decisao='aprovado'"), q("SELECT COUNT(*) FROM amostra_lote_inferido WHERE decisao='reprovado'")
    faltam = n - ap - rp
    if not n:
        conclusao = "Nenhuma amostra sorteada ainda."
    elif rp:
        conclusao = f"Há {rp} lote(s) reprovado(s) na amostra: NÃO liberar o resto sem o Rafa decidir o que fazer."
    elif faltam:
        conclusao = f"Faltam {faltam} lote(s) da amostra para revisar."
    else:
        conclusao = "Toda a amostra foi aprovada. Quem libera o resto dos lotes é o Rafa: este roteiro não libera nada."
    return {"populacao": total_populacao, "amostra": n, "aprovados": ap, "reprovados": rp, "faltam": faltam, "conclusao": conclusao}


def escrever_csv(con, lotes: list[dict], caminho) -> int:
    por_id = {l["lote_id"]: l for l in lotes}
    linhas = con.execute("SELECT * FROM amostra_lote_inferido ORDER BY fundo_codigo, lote_id").fetchall()
    with open(caminho, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fundo", "projeto", "titulo", "lote_id", "lote", "folhas", "motivo", "sorteado_em", "decisao", "motivo_da_decisao", "decidido_por", "decidido_em"])
        for r in linhas:
            l = por_id.get(r["lote_id"], {})
            w.writerow([r["fundo_codigo"], l.get("projeto", ""), l.get("titulo", ""), r["lote_id"], l.get("nome", ""), l.get("folhas", ""), l.get("motivo", ""), r["sorteado_em"],
                        r["decisao"] or "", r["motivo"] or "", r["decidido_por"] or "", r["decidido_em"] or ""])
    return len(linhas)
