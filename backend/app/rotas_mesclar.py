"""Cartão #156: despublicar um projeto e descartar um lote duplicado. Nada é apagado: tudo deixa rastro (quem, quando, por quê)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["mesclar"])


@router.post("/projetos/{codigo}/despublicar")
def despublicar(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Tira o projeto do ar: itens e página do projeto viram 'private' no Tainacan e o status vira fora_do_ar. É o 'tirar_do_ar' do Publicar, com o nome certo.
    A regra de quem pode é a mesma do Publicar: despublicar o que está PÚBLICO exige o admin master."""
    from .rotas_projetos import Publicacao, publicar
    con = connect()
    try:
        p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if not p["tainacan_item_id"] and not con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (codigo,)).fetchone():
            raise HTTPException(409, "Este projeto não tem nada no site para despublicar.")
    finally:
        con.close()
    r = publicar(codigo, Publicacao(acao="tirar_do_ar"), u)
    if r.get("ok") and not r.get("alterados"):
        raise HTTPException(409, r.get("mensagem") or "Este projeto não tem nada publicado no site para despublicar.")
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
import re


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
    con.execute("UPDATE revisao_campo SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE emprestimo_item SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE projeto SET capa_item=? WHERE capa_item=?", (novo, antigo))
    con.execute("UPDATE reserva SET projeto_codigo=? WHERE projeto_codigo=?", (novo, antigo))     # a reserva repetida devolve o código NOVO


def _status_velho(con, codigo: str, ator: str) -> None:
    """Folha marcada no_ar mas sem registro no site (o despublicar responde "nada no site"): corrige para nao_publicado."""
    con.execute("UPDATE item SET status_site='nao_publicado', atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'status_site_corrigido',?,?)",
                (codigo, ator, _json.dumps({"de": "no_ar", "para": "nao_publicado", "motivo": "sem registro no site"}, ensure_ascii=False)))


def _ano_da_folha(con, it) -> int:
    """Destino sem ano: mantém o ano do projeto de origem, ou o que já estava no código da folha (nunca 0000 se havia ano)."""
    o = con.execute("SELECT ano FROM projeto WHERE codigo=?", (it["projeto_codigo"],)).fetchone()
    if o and o["ano"]:
        return int(o["ano"])
    m = re.search(r"-(\d{4})-[^-]+-D\d+$", it["codigo"])
    return int(m.group(1)) if m else 0


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
            if it["tainacan_item_id"]:
                raise HTTPException(409, f"A folha {c} está pública no site. Despublique o projeto antes de mover.")
            _status_velho(con, c, ator)                                # marcada como publicada mas sem registro no site: status velho, não trava
        igual = None
        if it["titulo"] and it["folha"]:
            igual = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND titulo=? AND folha=? AND duplicata_de IS NULL LIMIT 1",
                                (destino, it["titulo"], it["folha"])).fetchone()
        if igual:                                                      # a mesma folha já existe no destino: marca, não copia
            con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata='mesma_folha', atualizado_em=datetime('now') WHERE codigo=?", (igual[0], c))
            duplicatas.append({"codigo": c, "duplicata_de": igual[0]}); continue
        seq += 1
        novo = f"{destino}-{(ano or _ano_da_folha(con, it)):04d}-{it['serie_codigo']}-D{seq:05d}"
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
            tem_site = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (origem,)).fetchone()[0] or \
                con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (origem,)).fetchone()
            if tem_site:
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
        troca = o["duplicata_de"] == codigo                      # "qual publica": a original passa a ser a cópia e vice-versa
        if o["duplicata_de"] and not troca:
            raise HTTPException(409, f"{d.codigo_original} já é duplicata de {o['duplicata_de']}: aponte para a original.")
        if a["status_site"] == "no_ar" and con.execute("SELECT tainacan_item_id FROM item WHERE codigo=?", (codigo,)).fetchone()[0]:
            raise HTTPException(409, "Esta folha está pública no site. Despublique antes.")
        if troca:
            con.execute("UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, atualizado_em=datetime('now') WHERE codigo=?", (d.codigo_original,))
        con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata=?, atualizado_em=datetime('now') WHERE codigo=?", (d.codigo_original, d.tipo, codigo))
        con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (d.codigo_original, codigo))   # quem apontava para esta passa a apontar para a original
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_marcada',?,?)",
                    (codigo, u["email"], _json.dumps({"original": d.codigo_original, "tipo": d.tipo, "trocou": troca}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "trocou": troca}
    finally:
        con.close()


@router.delete("/itens/{codigo}/duplicata-de")
def desmarcar_duplicata(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Desfaz a marcação ("Não é duplicata"): a folha deixa de ser duplicata e volta a poder ir ao site. Fica registrado de quem ela era cópia.
    Também solta o que o CAMP Vision prendeu por causa da duplicata: o aviso de duplicata entre os bloqueios da folha, a situação
    'bloqueado' (quando a duplicata era o único bloqueio) e os problemas de duplicata em aberto desta folha."""
    con = connect()
    try:
        a = con.execute("SELECT duplicata_de, tipo_duplicata, status_site, pendencias, autoria_divergente FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not a:
            raise HTTPException(404, "Folha não existe.")
        if not a["duplicata_de"]:
            raise HTTPException(409, "Esta folha não está marcada como duplicata.")
        liberou = liberar_bloqueios_de_duplicata(con, codigo, a, u["email"])
        con.execute("UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_desmarcada',?,?)",
                    (codigo, u["email"], _json.dumps({"era_de": a["duplicata_de"], "tipo": a["tipo_duplicata"], **liberou}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "era_de": a["duplicata_de"], **liberou}
    finally:
        con.close()


def _e_de_duplicata(texto) -> bool:
    return "duplicat" in str(texto or "").lower()


def liberar_bloqueios_de_duplicata(con, codigo: str, a, ator: str) -> dict:
    """Tira o que prendia a folha só por ser duplicata. Não faz commit. Devolve o que foi solto (vai para o evento e para a tela)."""
    out = {"bloqueios_tirados": [], "situacao_liberada": False, "problemas_fechados": 0}
    try:
        pend = _json.loads(a["pendencias"] or "{}") or {}
    except ValueError:
        pend = {}
    bloq = list(pend.get("bloqueios") or []) if isinstance(pend, dict) else []
    tirar = [b for b in bloq if _e_de_duplicata(b)]
    if tirar:
        pend["bloqueios"] = [b for b in bloq if not _e_de_duplicata(b)]
        con.execute("UPDATE item SET pendencias=? WHERE codigo=?", (_json.dumps(pend, ensure_ascii=False), codigo))
        out["bloqueios_tirados"] = tirar
    if a["status_site"] == "bloqueado" and not (pend.get("bloqueios") if isinstance(pend, dict) else None) and not a["autoria_divergente"]:
        con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))     # o CAMP Vision bloqueou por causa da duplicata
        out["situacao_liberada"] = True
    out["problemas_fechados"] = con.execute(
        """UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'),
                  resolucao=? WHERE codigo=? AND categoria='duplicata' AND situacao IN ('aberto','em_correcao')""",
        (f"Não é duplicata: desmarcada por {ator} no painel.", codigo)).rowcount
    return out


# ---------------- B7 · duplicados já cadastrados: varredura por fundo ----------------
class ParNao(BaseModel):
    a: str
    b: str


@router.get("/fundos/{codigo}/duplicados")
def duplicados_do_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Pares de projetos do mesmo fundo que parecem ser o mesmo (nome, ano, cidade, identificação original), do mais para o menos parecido.
    Os pares que alguém marcou "não são o mesmo" não voltam."""
    from .similaridade import nivel, pontuar
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Fundo não existe")
        ps = [dict(r) for r in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.identificacao_original, p.status_site,
                                                     (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                                                FROM projeto p WHERE p.fundo_codigo=? AND p.mesclado_em IS NULL ORDER BY p.codigo""", (codigo,))]
        nao = {(r[0], r[1]) for r in con.execute("SELECT a, b FROM par_nao_duplicado")}
        pares = []
        for i, x in enumerate(ps):
            for y in ps[i + 1:]:
                if (x["codigo"], y["codigo"]) in nao:
                    continue
                score, motivos = pontuar(x, y)
                n = nivel(score)
                if n:
                    pares.append({"a": x, "b": y, "score": score, "nivel": n, "motivos": motivos})
        pares.sort(key=lambda p: (-p["score"], p["a"]["codigo"]))
        return {"fundo": codigo, "projetos": len(ps), "total": len(pares), "pares": pares[:200]}
    finally:
        con.close()


@router.post("/fundos/{codigo}/duplicados/nao-sao")
def marcar_nao_duplicado(codigo: str, d: ParNao, u: dict = Depends(auth.exige("operador"))) -> dict:
    a, b = sorted([d.a.strip().upper(), d.b.strip().upper()])
    if a == b or not (a.startswith(codigo + "-") and b.startswith(codigo + "-")):
        raise HTTPException(400, "Informe dois projetos diferentes deste fundo")
    con = connect()
    try:
        con.execute("INSERT OR IGNORE INTO par_nao_duplicado (a, b, por) VALUES (?,?,?)", (a, b, u["email"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'nao_duplicado',?,?)",
                    (a, u["email"], _json.dumps({"outro": b}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------------
# Sobras #9 · RECODIFICAR um projeto (ex.: o número P errado): F014-P0004 → F014-P0009, no MESMO fundo.
# Mesma regra do mover: uma transação só, com a checagem de chave estrangeira adiada até o fim (ou troca tudo, ou nada).
# Cada folha ganha o código novo ({novo}-{ano}-{série}-D{seq}, mesmo ano/série/sequencial) e guarda o antigo em codigo_anterior;
# o projeto e cada folha entram na tabela redirecionamento (codigo_antigo → codigo_novo, já prevista no schema), que o site lê em GET /api/redirecionamentos para o 301.
# O número antigo continua reservado (numero_p): nunca é reusado. A pasta no QNAP não é renomeada.
# ---------------------------------------------------------------------------------------------------------------------
_COD_PROJETO = re.compile(r"^F\d{3}-P\d{4}$")


class Recodificar(BaseModel):
    novo: str
    motivo: str | None = None


def _prefixo(con, tabela: str, coluna: str, antigo: str, novo: str, onde: str = "") -> int:
    """Troca o prefixo `antigo` por `novo` na coluna (o próprio código do projeto e os das folhas, que começam por 'antigo-')."""
    n = len(antigo)
    return con.execute(f"UPDATE {tabela} SET {coluna} = ? || substr({coluna}, ?) WHERE ({coluna} = ? OR substr({coluna}, 1, ?) = ?){onde}",
                       (novo, n + 1, antigo, n + 1, antigo + "-")).rowcount


def _recodificar(con, antigo: str, novo: str, ator: str, motivo: str | None) -> dict:
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (antigo,)).fetchone()
    if not p:
        raise HTTPException(404, f"O projeto {antigo} não existe.")
    if p["mesclado_em"]:
        raise HTTPException(409, f"O projeto {antigo} já foi mesclado em {p['mesclado_em']}: mude o código de lá, se precisar.")
    if not novo.startswith(p["fundo_codigo"] + "-"):
        raise HTTPException(400, f"O código novo tem que ser do mesmo fundo ({p['fundo_codigo']}-P….). Para levar a outro fundo, use Mesclar.")
    if con.execute("SELECT 1 FROM projeto WHERE codigo=?", (novo,)).fetchone():
        raise HTTPException(409, f"O código {novo} já é de outro projeto. Escolha um número livre (ou use Mesclar, se for o mesmo projeto).")
    numero = int(novo[-4:])
    if numero < 1:
        raise HTTPException(400, "O número P tem que ser 0001 ou maior.")
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,NULL)", (p["fundo_codigo"], numero))
    con.execute("UPDATE projeto SET codigo=?, numero=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, numero, antigo))
    folhas = []
    for it in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY serie_codigo, sequencial", (antigo,)).fetchall():
        c = it["codigo"]
        nc = novo + c[len(antigo):] if c.startswith(antigo + "-") else f"{novo}-{c.split('-', 2)[-1]}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (nc,)).fetchone():
            raise HTTPException(409, f"O código {nc} já existe; nada foi mudado.")
        con.execute("UPDATE item SET codigo=?, projeto_codigo=?, codigo_anterior=?, atualizado_em=datetime('now') WHERE codigo=?", (nc, novo, c, c))
        _trocar_codigo(con, c, nc)                                     # item_agente, localização, releitura, duplicata_de, erro, revisão
        folhas.append({"de": c, "para": nc})
    # o que aponta para o PROJETO (e, por prefixo, para as folhas) fora das chaves estrangeiras
    for tabela, coluna in (("lista_processamento", "projeto_codigo"), ("pedido_releitura", "projeto_codigo"), ("decisao", "projeto_codigo"),
                           ("cv_resposta", "projeto_codigo"), ("tarefa_publicacao", "projeto_codigo"), ("tarefa_publicacao", "folha_atual"),
                           ("uso_download", "projeto_codigo"), ("uso_download", "material_codigo"), ("estacao_heartbeat", "projeto_codigo"),
                           ("solicitacao_item", "codigo"), ("etiqueta_impressao", "codigo"), ("divergencia_site", "codigo"), ("erro", "codigo"),
                           ("projeto", "capa_item"), ("projeto", "mesclado_em"), ("reserva", "projeto_codigo")):
        _prefixo(con, tabela, coluna, antigo, novo)
    _prefixo(con, "cv_resposta", "chave", antigo, novo, " AND tipo='retirado'")
    _prefixo(con, "evento", "codigo", antigo, novo, " AND entidade IN ('projeto','item')")   # o histórico acompanha o projeto
    for r in con.execute("SELECT a, b, por, em FROM par_nao_duplicado WHERE a=? OR b=?", (antigo, antigo)).fetchall():
        a, b = sorted([novo if r["a"] == antigo else r["a"], novo if r["b"] == antigo else r["b"]])
        con.execute("DELETE FROM par_nao_duplicado WHERE a=? AND b=?", (r["a"], r["b"]))
        con.execute("INSERT OR IGNORE INTO par_nao_duplicado (a, b, por, em) VALUES (?,?,?,?)", (a, b, r["por"], r["em"]))
    # mapa antigo → novo: quem já apontava para o antigo passa a apontar para o novo (sem cadeia), e entra o que mudou agora
    _prefixo(con, "redirecionamento", "codigo_novo", antigo, novo)
    con.execute("UPDATE redirecionamento SET aplicado_no_site=0 WHERE codigo_novo = ? OR substr(codigo_novo, 1, ?) = ?", (novo, len(novo) + 1, novo + "-"))
    con.execute("DELETE FROM redirecionamento WHERE codigo_antigo = codigo_novo")
    mot = (motivo or "").strip()[:300] or "código do projeto corrigido"
    for de, para, tipo in [(antigo, novo, "projeto")] + [(f["de"], f["para"], "item") for f in folhas]:
        con.execute("""INSERT INTO redirecionamento (codigo_antigo, codigo_novo, entidade, motivo, criado_por) VALUES (?,?,?,?,?)
                       ON CONFLICT(codigo_antigo) DO UPDATE SET codigo_novo=excluded.codigo_novo, entidade=excluded.entidade, motivo=excluded.motivo,
                                                                criado_por=excluded.criado_por, criado_em=datetime('now'), aplicado_no_site=0""", (de, para, tipo, mot, ator))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'projeto_recodificado',?,?)",
                (novo, ator, _json.dumps({"de": antigo, "para": novo, "folhas": len(folhas), "motivo": mot}, ensure_ascii=False)))
    no_site = bool(p["tainacan_item_id"] or p["wp_page_id"]) or bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (novo,)).fetchone())
    avisos = []
    if no_site:
        avisos.append("O projeto já tem registro no site: publique de novo para o site mostrar o código novo. Os endereços antigos redirecionam quando o site ler o mapa de redirecionamentos.")
    if p["pasta_qnap"]:
        avisos.append("A pasta no QNAP continua com o nome antigo; renomeie lá se quiser.")
    return {"ok": True, "de": antigo, "para": novo, "folhas": folhas, "no_site": no_site, "avisos": avisos}


@router.post("/projetos/{codigo}/recodificar")
def recodificar(codigo: str, d: Recodificar, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Muda o código do projeto e de todas as folhas dele. Só admin. O antigo fica guardado e vira redirecionamento."""
    antigo, novo = codigo.strip().upper(), (d.novo or "").strip().upper()
    if not _COD_PROJETO.match(novo):
        raise HTTPException(400, "Use o código completo do projeto, ex.: F014-P0009.")
    if novo == antigo:
        raise HTTPException(400, "O código novo é igual ao atual.")
    return _transacao(lambda con: _recodificar(con, antigo, novo, u["email"], d.motivo))


@router.get("/redirecionamentos")
def redirecionamentos(tipo: str | None = None, desde: str | None = None) -> dict:
    """PÚBLICA (sem login), para o site responder 301: só códigos antigo → novo, nada além. Ver docs/pedidos-do-site.md."""
    sql, p = "SELECT codigo_antigo AS antigo, codigo_novo AS novo, entidade AS tipo, criado_em FROM redirecionamento WHERE 1=1", []
    if tipo in ("fundo", "projeto", "item"):
        sql += " AND entidade=?"; p.append(tipo)
    if desde and re.match(r"^\d{4}-\d{2}-\d{2}", desde):
        sql += " AND criado_em >= ?"; p.append(desde[:19].replace("T", " "))
    con = connect()
    try:
        itens = [dict(r) for r in con.execute(sql + " ORDER BY criado_em, rowid", p)]
    finally:
        con.close()
    return {"total": len(itens), "itens": itens}
