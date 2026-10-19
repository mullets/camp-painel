"""Revisão pós-CAMP Vision: CONSENSO do lote. Entre as folhas de um lote (ou do projeto inteiro), o valor mais frequente do ano,
do endereço e do cliente lidos em cada carimbo. Mostra o consenso e as folhas que divergem; a pessoa decide trocar, folha a folha ou em todas.
Nada é trocado sozinho. Duplicatas não votam (seriam o mesmo carimbo contado duas vezes)."""
import json
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["consenso"])

# campo da tela -> (coluna da folha, rótulo, coluna do projeto)
CAMPOS = {"ano": ("ano_folha", "Ano", "ano"), "endereco": ("endereco_folha", "Endereço da obra", "endereco_obra"),
          "cliente": ("cliente_folha", "Cliente", "cliente")}
MINIMO_VOTOS = 2      # um carimbo sozinho não é consenso


def _limpo(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v or None
    t = " ".join(str(v).split())
    return t or None


def _chave(v):
    return v if isinstance(v, int) else str(v).casefold()


def _folhas(con, codigo: str, lote_id: int | None) -> list[dict]:
    sql = """SELECT i.codigo, i.sequencial, i.lote_id, i.status_site, i.ano_folha, i.endereco_folha, i.cliente_folha, l.aprovado_em
               FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id
              WHERE i.projeto_codigo=? AND i.duplicata_de IS NULL"""
    par: list = [codigo]
    if lote_id is not None:
        sql += " AND i.lote_id=?"; par.append(lote_id)
    return [dict(r) for r in con.execute(sql + " ORDER BY i.serie_codigo, i.sequencial", par)]


def _trava(f: dict) -> str | None:
    if f["status_site"] in ("rascunho", "no_ar"):
        return "já está no site"
    if f["aprovado_em"]:
        return "o lote já foi aprovado"
    return None


def calcular(con, codigo: str, lote_id: int | None) -> dict:
    p = con.execute("SELECT codigo, ano, endereco_obra, cliente FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        raise HTTPException(404, "Projeto não existe")
    if lote_id is not None and not con.execute("SELECT 1 FROM lista_processamento WHERE id=? AND projeto_codigo=?", (lote_id, codigo)).fetchone():
        raise HTTPException(404, "Este lote não é deste projeto")
    folhas = _folhas(con, codigo, lote_id)
    mantidos = {}   # 19/10: "Manter o do projeto" (o último registro por campo vale enquanto o consenso for o mesmo)
    for r in con.execute("SELECT ator, quando, detalhe FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='consenso_mantido' ORDER BY id", (codigo,)):
        try:
            dt = json.loads(r["detalhe"] or "{}")
        except ValueError:
            continue
        if isinstance(dt, dict) and dt.get("campo") in CAMPOS:
            mantidos[dt["campo"]] = {"por": r["ator"], "em": r["quando"], "consenso": dt.get("consenso"), "projeto": dt.get("projeto")}
    campos = []
    for campo, (col, rotulo, col_p) in CAMPOS.items():
        votos, forma = Counter(), {}
        for f in folhas:
            v = _limpo(f[col])
            if v is not None:
                votos[_chave(v)] += 1
                forma.setdefault(_chave(v), Counter())[v] += 1
        ranking = votos.most_common()
        consenso = empate = None
        if ranking and ranking[0][1] >= MINIMO_VOTOS:
            if len(ranking) > 1 and ranking[1][1] == ranking[0][1]:
                empate = True
            else:
                consenso = forma[ranking[0][0]].most_common(1)[0][0]
        divergentes = []
        if consenso is not None:
            for f in folhas:
                v = _limpo(f[col])
                if v is None or _chave(v) != _chave(consenso):
                    divergentes.append({"codigo": f["codigo"], "valor": v, "vazio": v is None, "trava": _trava(f)})
        proj = _limpo(p[col_p]) if col_p != "ano" else (p["ano"] or None)
        difere = consenso is not None and proj is not None and _chave(proj) != _chave(consenso)
        m = mantidos.get(campo)
        mantido = ({"por": m["por"], "em": m["em"]} if difere and m and m["consenso"] is not None and _chave(m["consenso"]) == _chave(consenso)
                   and m["projeto"] is not None and _chave(m["projeto"]) == _chave(proj) else None)
        campos.append({"projeto_difere": difere, "mantido": mantido, "campo": campo, "rotulo": rotulo, "consenso": consenso, "votos": ranking[0][1] if ranking else 0,
                       "com_valor": sum(votos.values()), "empate": bool(empate),
                       "valores": [{"valor": forma[k].most_common(1)[0][0], "folhas": n} for k, n in ranking[:8]],
                       "divergentes": divergentes, "projeto": proj})
    return {"projeto": codigo, "lote_id": lote_id, "folhas": len(folhas), "campos": campos}


@router.get("/projetos/{codigo}/consenso")
def consenso(codigo: str, lote_id: int | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return calcular(con, codigo, lote_id)
    finally:
        con.close()


class AplicarConsenso(BaseModel):
    campo: str
    itens: list[str] | None = None      # None = em todas as folhas que divergem
    lote_id: int | None = None


@router.post("/projetos/{codigo}/consenso/aplicar")
def aplicar(codigo: str, d: AplicarConsenso, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Troca o valor das folhas escolhidas (ou de todas as que divergem) pelo valor do consenso, calculado de novo aqui (a tela não manda o valor).
    Folha já no site ou de lote aprovado fica de fora e volta na resposta, com o motivo."""
    if d.campo not in CAMPOS:
        raise HTTPException(400, "Campo inválido: use ano, endereco ou cliente")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        c = next(x for x in calcular(con, codigo, d.lote_id)["campos"] if x["campo"] == d.campo)
        if c["consenso"] is None:
            raise HTTPException(409, "Não há consenso para este campo (empate ou poucas folhas com valor).")
        div = {x["codigo"]: x for x in c["divergentes"]}
        alvo = list(div) if d.itens is None else list(dict.fromkeys(d.itens))
        if not alvo:
            raise HTTPException(400, "Nenhuma folha diverge do consenso.")
        col = CAMPOS[d.campo][0]
        aplicadas, ignoradas = [], []
        for cod in alvo:
            x = div.get(cod)
            if not x:
                ignoradas.append({"codigo": cod, "motivo": "já segue o consenso ou não é deste lote"}); continue
            if x["trava"]:
                ignoradas.append({"codigo": cod, "motivo": x["trava"]}); continue
            con.execute(f"UPDATE item SET {col}=?, atualizado_em=datetime('now') WHERE codigo=?", (c["consenso"], cod))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'consenso_aplicado',?,?)",
                        (cod, u["email"], json.dumps({"campo": d.campo, "de": x["valor"], "para": c["consenso"], "lote_id": d.lote_id}, ensure_ascii=False)))
            aplicadas.append(cod)
        con.commit()
        return {"ok": True, "campo": d.campo, "valor": c["consenso"], "aplicadas": aplicadas, "ignoradas": ignoradas}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class ManterProjeto(BaseModel):
    campo: str
    lote_id: int | None = None


@router.post("/projetos/{codigo}/consenso/manter")
def manter(codigo: str, d: ManterProjeto, u: dict = Depends(auth.exige("operador"))) -> dict:
    """19/10: a pessoa olhou a diferença entre o consenso das folhas e o campo do projeto e decidiu MANTER o do projeto.
    Só registra (histórico do projeto); nada muda no projeto nem nas folhas. Se o consenso ou o projeto mudarem, a diferença volta a aparecer."""
    if d.campo not in CAMPOS:
        raise HTTPException(400, "Campo inválido: use ano, endereco ou cliente")
    con = connect()
    try:
        c = next(x for x in calcular(con, codigo, d.lote_id)["campos"] if x["campo"] == d.campo)
        if not c["projeto_difere"]:
            raise HTTPException(409, "O projeto já segue o consenso das folhas (ou não há consenso).")
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'consenso_mantido',?,?)",
                    (codigo, u["email"], json.dumps({"campo": d.campo, "consenso": c["consenso"], "projeto": c["projeto"], "lote_id": d.lote_id}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "campo": d.campo, "projeto": c["projeto"]}
    finally:
        con.close()
