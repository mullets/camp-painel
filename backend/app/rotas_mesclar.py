"""Cartão #156: despublicar um projeto e descartar um lote duplicado. Nada é apagado: tudo deixa rastro (quem, quando, por quê)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["mesclar"])


@router.post("/projetos/{codigo}/despublicar")
def despublicar(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Tira o projeto do ar: itens e página do projeto viram 'private' no Tainacan e o status vira fora_do_ar. É o 'tirar_do_ar' do Publicar, com o nome certo.
    A regra de quem pode é a mesma do Publicar: tirar do ar o que está PÚBLICO exige o admin master."""
    from .rotas_projetos import Publicacao, publicar
    con = connect()
    try:
        p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if not p["tainacan_item_id"] and not con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (codigo,)).fetchone():
            raise HTTPException(409, "Este projeto não tem nada no site para tirar do ar.")
    finally:
        con.close()
    r = publicar(codigo, Publicacao(acao="tirar_do_ar"), u)
    if r.get("ok") and not r.get("alterados"):
        raise HTTPException(409, r.get("mensagem") or "Este projeto não tem nada publicado no site para tirar do ar.")
    return r


class Descarte(BaseModel):
    motivo: str
    duplicata_de: int | None = None


@router.post("/filas/{lid}/descartar")
def descartar_lote(lid: int, d: Descarte, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Descarta um lote que é subpasta ou repetição de outro: some da Fila e dos contadores. NÃO apaga nada no QNAP nem no banco."""
    motivo = (d.motivo or "").strip()
    if len(motivo) < 3:
        raise HTTPException(400, "Explique o motivo (pelo menos 3 letras).")
    con = connect()
    try:
        l = con.execute("SELECT id, etapa, aprovado_em, descartado_em FROM lista_processamento WHERE id=?", (lid,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        if l["descartado_em"]:
            raise HTTPException(409, "Este lote já foi descartado.")
        if l["aprovado_em"] or l["etapa"] == "publicado":
            raise HTTPException(409, "Este lote já foi aprovado ou publicado: não dá para descartar.")
        if con.execute("SELECT COUNT(*) FROM item WHERE lote_id=?", (lid,)).fetchone()[0]:
            raise HTTPException(409, "Este lote já tem folhas importadas. Use Mover ou Mesclar projetos em vez de descartar.")
        if d.duplicata_de is not None:
            if d.duplicata_de == lid or not con.execute("SELECT 1 FROM lista_processamento WHERE id=?", (d.duplicata_de,)).fetchone():
                raise HTTPException(400, "O lote indicado como original não existe.")
        con.execute("UPDATE lista_processamento SET descartado_em=datetime('now'), descartado_por=?, descartado_motivo=?, descartado_duplicata_de=?, atualizado_em=datetime('now') WHERE id=?",
                    (u["email"], motivo[:300], d.duplicata_de, lid))
        import json
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'lote_descartado',?,?)",
                    (str(lid), u["email"], json.dumps({"motivo": motivo[:300], "duplicata_de": d.duplicata_de}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": lid}
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------------------------------
# MOVER folhas e MESCLAR projetos. O código da folha é a chave primária ({projeto}-{ano}-{série}-D{seq}) e aparece em
# item_agente, item_localizacao, pedido_releitura, item.duplicata_de e erro.codigo: tudo é trocado numa transação só,
# com a checagem de chave estrangeira adiada até o fim. Ou move tudo, ou não move nada.
# Folha PÚBLICA no site (no_ar) não é movida: despublique antes. Folha que já tinha registro no site (rascunho/privado)
# é movida e perde o vínculo (o registro antigo fica privado no site; ao publicar o destino, ela sobe com o código novo).
# ---------------------------------------------------------------------------------------------------------------------
import json as _json


class MoverItens(BaseModel):
    itens: list[str]
    destino: str
    motivo: str | None = None


class Destino(BaseModel):
    destino: str
    motivo: str | None = None


class MoverLote(BaseModel):
    projeto_codigo: str
    motivo: str | None = None


class DuplicataDe(BaseModel):
    codigo_original: str
    tipo: str = "mesma_folha"


def _destino_valido(con, destino: str):
    d = con.execute("SELECT codigo, ano, mesclado_em FROM projeto WHERE codigo=?", (destino,)).fetchone()
    if not d:
        raise HTTPException(404, f"O projeto de destino {destino} não existe.")
    if d["mesclado_em"]:
        raise HTTPException(409, f"O projeto {destino} já foi mesclado em {d['mesclado_em']}: use esse como destino.")
    return d


def _trocar_codigo(con, antigo: str, novo: str) -> None:
    con.execute("UPDATE item_agente SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE item_localizacao SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE pedido_releitura SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (novo, antigo))
    con.execute("UPDATE erro SET codigo=? WHERE codigo=?", (novo, antigo))


def _mover(con, codigos: list[str], destino: str, ator: str, motivo: str | None) -> dict:
    """Move as folhas para o destino (transação já aberta por quem chama). Devolve o que foi movido, as duplicatas e o que foi ignorado."""
    d = _destino_valido(con, destino)
    ano = int(d["ano"] or 0)
    seq = con.execute("SELECT COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=?", (destino,)).fetchone()[0]
    movidos, duplicatas, ignorados = [], [], []
    linhas = []
    for c in dict.fromkeys(codigos):                                   # sem repetir, na ordem dada
        it = con.execute("SELECT * FROM item WHERE codigo=?", (c,)).fetchone()
        if not it:
            raise HTTPException(404, f"A folha {c} não existe.")
        linhas.append(it)
    linhas.sort(key=lambda r: (r["serie_codigo"], r["sequencial"]))
    for it in linhas:
        c = it["codigo"]
        if it["projeto_codigo"] == destino:
            ignorados.append({"codigo": c, "motivo": "já está no destino"}); continue
        if it["status_site"] == "no_ar":
            raise HTTPException(409, f"A folha {c} está pública no site. Despublique o projeto antes de mover.")
        igual = None
        if it["titulo"] and it["folha"]:
            igual = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND titulo=? AND folha=? AND duplicata_de IS NULL LIMIT 1",
                                (destino, it["titulo"], it["folha"])).fetchone()
        if igual:                                                      # a mesma folha já existe no destino: marca, não copia
            con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata='mesma_folha', atualizado_em=datetime('now') WHERE codigo=?", (igual[0], c))
            duplicatas.append({"codigo": c, "duplicata_de": igual[0]}); continue
        seq += 1
        novo = f"{destino}-{ano:04d}-{it['serie_codigo']}-D{seq:05d}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (novo,)).fetchone():
            raise HTTPException(409, f"O código {novo} já existe; nada foi movido.")
        tinha_site = it["tainacan_item_id"]
        con.execute("""UPDATE item SET codigo=?, projeto_codigo=?, sequencial=?, codigo_anterior=?,
                       tainacan_item_id=NULL, status_site=CASE WHEN tainacan_item_id IS NOT NULL THEN 'nao_publicado' ELSE status_site END,
                       atualizado_em=datetime('now') WHERE codigo=?""", (novo, destino, seq, c, c))
        _trocar_codigo(con, c, novo)
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_movida',?,?)",
                    (novo, ator, _json.dumps({"de": c, "para": novo, "motivo": motivo, "tainacan_item_id_antigo": tinha_site}, ensure_ascii=False)))
        movidos.append({"de": c, "para": novo, "tinha_registro_no_site": bool(tinha_site)})
    return {"movidos": movidos, "duplicatas": duplicatas, "ignorados": ignorados}


def _transacao(fn):
    con = connect()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys = ON")
        r = fn(con)
        con.execute("COMMIT")
        return r
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        con.close()


@router.post("/itens/mover")
def mover_itens(d: MoverItens, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Move as folhas escolhidas para outro projeto, renumerando no destino (D continua de onde o destino parou)."""
    if not d.itens:
        raise HTTPException(400, "Escolha pelo menos uma folha.")
    return _transacao(lambda con: _mover(con, d.itens, d.destino, u["email"], d.motivo))


@router.post("/projetos/{origem}/mesclar-em")
def mesclar_em(origem: str, d: Destino, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Move TODAS as folhas e os lotes da origem para o destino. A origem não é apagada: fica marcada 'mesclado em' e some das listas."""
    if origem == d.destino:
        raise HTTPException(400, "Origem e destino são o mesmo projeto.")

    def fazer(con):
        o = con.execute("SELECT codigo, status_site, mesclado_em FROM projeto WHERE codigo=?", (origem,)).fetchone()
        if not o:
            raise HTTPException(404, f"O projeto {origem} não existe.")
        if o["mesclado_em"]:
            raise HTTPException(409, f"O projeto {origem} já foi mesclado em {o['mesclado_em']}.")
        if o["status_site"] == "no_ar":
            raise HTTPException(409, f"O projeto {origem} está público no site. Despublique antes de mesclar.")
        _destino_valido(con, d.destino)
        cods = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (origem,))]
        r = _mover(con, cods, d.destino, u["email"], d.motivo or f"mesclado em {d.destino}") if cods else {"movidos": [], "duplicatas": [], "ignorados": []}
        lotes = [x[0] for x in con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=?", (origem,))]
        con.execute("UPDATE lista_processamento SET projeto_codigo=?, atualizado_em=datetime('now') WHERE projeto_codigo=?", (d.destino, origem))
        con.execute("UPDATE pedido_releitura SET projeto_codigo=? WHERE projeto_codigo=?", (d.destino, origem))
        con.execute("UPDATE projeto SET mesclado_em=?, mesclado_por=?, mesclado_quando=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (d.destino, u["email"], origem))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'projeto_mesclado',?,?)",
                    (origem, u["email"], _json.dumps({"destino": d.destino, "folhas": len(r["movidos"]), "duplicatas": len(r["duplicatas"]), "lotes": lotes, "motivo": d.motivo}, ensure_ascii=False)))
        return {**r, "lotes": lotes, "origem": origem, "destino": d.destino}
    return _transacao(fazer)


@router.post("/filas/{lid}/mover-para")
def mover_lote(lid: int, d: MoverLote, u: dict = Depends(auth.exige("admin"))) -> dict:
    """O lote caiu no projeto errado: passa o lote e as folhas dele para o projeto certo."""
    def fazer(con):
        l = con.execute("SELECT id, projeto_codigo, descartado_em FROM lista_processamento WHERE id=?", (lid,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        if l["descartado_em"]:
            raise HTTPException(409, "Este lote foi descartado.")
        if l["projeto_codigo"] == d.projeto_codigo:
            raise HTTPException(400, "O lote já está nesse projeto.")
        _destino_valido(con, d.projeto_codigo)
        cods = [r[0] for r in con.execute("SELECT codigo FROM item WHERE lote_id=?", (lid,))]
        r = _mover(con, cods, d.projeto_codigo, u["email"], d.motivo or f"lote {lid} movido") if cods else {"movidos": [], "duplicatas": [], "ignorados": []}
        con.execute("UPDATE lista_processamento SET projeto_codigo=?, atualizado_em=datetime('now') WHERE id=?", (d.projeto_codigo, lid))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'lote_movido',?,?)",
                    (str(lid), u["email"], _json.dumps({"de": l["projeto_codigo"], "para": d.projeto_codigo, "folhas": len(r["movidos"]), "motivo": d.motivo}, ensure_ascii=False)))
        return {**r, "lote": lid, "de": l["projeto_codigo"], "para": d.projeto_codigo}
    return _transacao(fazer)


@router.post("/itens/{codigo}/duplicata-de")
def marcar_duplicata(codigo: str, d: DuplicataDe, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca a folha como duplicata de outra (nada é apagado; só a original vai ao site)."""
    if d.tipo not in ("exata", "perceptual", "mesma_folha"):
        raise HTTPException(400, "Tipo de duplicata inválido.")
    if codigo == d.codigo_original:
        raise HTTPException(400, "Uma folha não pode ser duplicata dela mesma.")
    con = connect()
    try:
        a = con.execute("SELECT codigo, status_site FROM item WHERE codigo=?", (codigo,)).fetchone()
        o = con.execute("SELECT codigo, duplicata_de FROM item WHERE codigo=?", (d.codigo_original,)).fetchone()
        if not a or not o:
            raise HTTPException(404, "Folha não existe.")
        if o["duplicata_de"]:
            raise HTTPException(409, f"{d.codigo_original} já é duplicata de {o['duplicata_de']}: aponte para a original.")
        if a["status_site"] == "no_ar":
            raise HTTPException(409, "Esta folha está pública no site. Despublique antes.")
        con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata=?, atualizado_em=datetime('now') WHERE codigo=?", (d.codigo_original, d.tipo, codigo))
        con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (d.codigo_original, codigo))   # quem apontava para esta passa a apontar para a original
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_marcada',?,?)",
                    (codigo, u["email"], _json.dumps({"original": d.codigo_original, "tipo": d.tipo}, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()
