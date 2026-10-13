"""Consulta presencial e empréstimo de originais: quem está com o quê, até quando, e a devolução.

Regras:
- "em aberto" = ainda não devolvido; "atrasado" = em aberto com o prazo antes de hoje (dia de São Paulo);
- uma folha está FORA quando ela própria ou o recipiente em que está guardada (item_localizacao) está num empréstimo em aberto;
- a mesma folha ou o mesmo recipiente não pode estar em dois empréstimos abertos ao mesmo tempo.
Tudo vira evento (entidade 'emprestimo') no histórico.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["emprestimos"])

HOJE_SQL = "date('now','-3 hours')"      # o dia em São Paulo (as outras telas usam a mesma conta)
TIPOS = {"consulta": "consulta presencial", "emprestimo": "empréstimo"}


class NovoEmprestimo(BaseModel):
    tipo: str = "emprestimo"
    nome: str
    contato: str | None = None
    instituicao: str | None = None
    saida_em: str | None = None          # AAAA-MM-DD; vazio = hoje
    prazo: str | None = None             # AAAA-MM-DD; vazio só na consulta presencial (= o mesmo dia)
    responsavel_id: int | None = None    # vazio = quem está registrando
    observacao: str | None = None
    itens: list[str] = []                # códigos de folha
    localizacoes: list[int] = []         # ids de caixa/tubo/gaveta…


class Devolucao(BaseModel):
    observacao: str | None = None


def _evento(con, codigo, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('emprestimo',?,?,?,?)",
                (str(codigo), tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _data(v: str | None, campo: str) -> str | None:
    if v is None or not str(v).strip():
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10]).isoformat()
    except ValueError:
        raise HTTPException(400, f"Data inválida em {campo}: use o formato AAAA-MM-DD")


def _hoje(con) -> str:
    return con.execute(f"SELECT {HOJE_SQL}").fetchone()[0]


_SELECT = f"""SELECT e.*, r.nome AS responsavel, d.nome AS devolvido_por_nome,
                     (SELECT COUNT(*) FROM emprestimo_item x WHERE x.emprestimo_id=e.id AND x.item_codigo IS NOT NULL) AS n_folhas,
                     (SELECT COUNT(*) FROM emprestimo_item x WHERE x.emprestimo_id=e.id AND x.localizacao_id IS NOT NULL) AS n_locais,
                     CASE WHEN e.devolvido_em IS NOT NULL THEN 'devolvido'
                          WHEN e.prazo < {HOJE_SQL} THEN 'atrasado' ELSE 'aberto' END AS situacao,
                     CAST(julianday({HOJE_SQL}) - julianday(e.prazo) AS INTEGER) AS dias_atraso
                FROM emprestimo e LEFT JOIN usuario r ON r.id=e.responsavel_id LEFT JOIN usuario d ON d.id=e.devolvido_por"""


def _linha(r) -> dict:
    d = dict(r)
    d["tipo_rotulo"] = TIPOS.get(d["tipo"], d["tipo"])
    if d["situacao"] != "atrasado":
        d["dias_atraso"] = 0
    return d


def _conteudo(con, eid: int) -> dict:
    folhas = [dict(r) for r in con.execute("""SELECT x.item_codigo AS codigo, i.titulo, i.folha, i.projeto_codigo, p.titulo AS projeto
                                                FROM emprestimo_item x JOIN item i ON i.codigo=x.item_codigo JOIN projeto p ON p.codigo=i.projeto_codigo
                                               WHERE x.emprestimo_id=? AND x.item_codigo IS NOT NULL ORDER BY x.item_codigo""", (eid,))]
    locais = [dict(r) for r in con.execute("""SELECT l.id, l.tipo, l.identificador, l.fundo_codigo, l.descricao,
                                                     (SELECT COUNT(*) FROM item_localizacao il WHERE il.localizacao_id=l.id) AS folhas
                                                FROM emprestimo_item x JOIN localizacao_fisica l ON l.id=x.localizacao_id
                                               WHERE x.emprestimo_id=? AND x.localizacao_id IS NOT NULL ORDER BY l.identificador""", (eid,))]
    return {"folhas": folhas, "localizacoes": locais}


def contar_atrasados(con) -> int:
    """Usado pelo painel inicial e pelo contador do menu (pendencias.py)."""
    try:
        return con.execute(f"SELECT COUNT(*) FROM emprestimo WHERE devolvido_em IS NULL AND prazo < {HOJE_SQL}").fetchone()[0]
    except Exception:  # noqa: BLE001  (banco sem a migração 092: zero, nunca derruba o painel)
        return 0


def atrasados(con, limite: int = 50) -> list[dict]:
    try:
        out = [_linha(r) for r in con.execute(_SELECT + f" WHERE e.devolvido_em IS NULL AND e.prazo < {HOJE_SQL} ORDER BY e.prazo, e.id LIMIT ?", (limite,))]
    except Exception:  # noqa: BLE001
        return []
    for e in out:
        c = _conteudo(con, e["id"])
        e["resumo"] = [x["identificador"] for x in c["localizacoes"]] + [f"{len(c['folhas'])} folha{'s' if len(c['folhas']) != 1 else ''}"] * bool(c["folhas"])
    return out


@router.get("/emprestimos")
def listar(situacao: str = "aberto", u: dict = Depends(auth.exige("leitura"))) -> dict:
    """situacao: aberto (inclui os atrasados, atrasados primeiro) | atrasado | devolvido | todos."""
    if situacao not in ("aberto", "atrasado", "devolvido", "todos"):
        raise HTTPException(400, "Situação inválida: use aberto, atrasado, devolvido ou todos")
    con = connect()
    try:
        filtro = {"aberto": "WHERE e.devolvido_em IS NULL", "atrasado": f"WHERE e.devolvido_em IS NULL AND e.prazo < {HOJE_SQL}",
                  "devolvido": "WHERE e.devolvido_em IS NOT NULL", "todos": ""}[situacao]
        ordem = "ORDER BY e.devolvido_em DESC, e.id DESC" if situacao == "devolvido" else \
                f"ORDER BY (e.devolvido_em IS NOT NULL), (e.prazo < {HOJE_SQL}) DESC, e.prazo, e.id"
        itens = [_linha(r) for r in con.execute(f"{_SELECT} {filtro} {ordem} LIMIT 500")]
        for it in itens:                 # o que saiu, em poucas palavras, para a lista
            c = _conteudo(con, it["id"])
            it["resumo"] = [x["identificador"] for x in c["localizacoes"]] + [x["codigo"] for x in c["folhas"]]
        q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
        resumo = {"aberto": q("SELECT COUNT(*) FROM emprestimo WHERE devolvido_em IS NULL"),
                  "atrasado": contar_atrasados(con),
                  "devolvido": q("SELECT COUNT(*) FROM emprestimo WHERE devolvido_em IS NOT NULL")}
        return {"situacao": situacao, "itens": itens, "resumo": resumo, "hoje": _hoje(con)}
    finally:
        con.close()


@router.get("/emprestimos/fora")
def fora(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """O que está fora agora: {localizacoes: {id: {...}}, itens: {codigo: {...}}} (para marcar a tela Onde está guardado)."""
    con = connect()
    try:
        locs, its = {}, {}
        for r in con.execute(f"""SELECT x.item_codigo, x.localizacao_id, e.id, e.nome, e.tipo, e.prazo, (e.prazo < {HOJE_SQL}) AS atrasado
                                   FROM emprestimo_item x JOIN emprestimo e ON e.id=x.emprestimo_id WHERE e.devolvido_em IS NULL"""):
            info = {"emprestimo_id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "prazo": r["prazo"], "atrasado": bool(r["atrasado"])}
            if r["localizacao_id"] is not None:
                locs[str(r["localizacao_id"])] = info
            else:
                its[r["item_codigo"]] = info
        return {"localizacoes": locs, "itens": its}
    finally:
        con.close()


@router.get("/emprestimos/responsaveis")
def responsaveis(u: dict = Depends(auth.exige("operador"))) -> list[dict]:
    """Quem pode ser o responsável da CAMP por um empréstimo: usuários ativos que não são só de leitura."""
    con = connect()
    try:
        return [{**dict(r), "eu": r["id"] == u["id"]} for r in con.execute("SELECT id, nome FROM usuario WHERE ativo=1 AND papel!='leitura' ORDER BY nome")]
    finally:
        con.close()


def _emprestimo_do_item(con, codigo: str):
    return con.execute(f"""SELECT e.id, e.nome, e.tipo, e.prazo, (e.prazo < {HOJE_SQL}) AS atrasado,
                                  CASE WHEN x.localizacao_id IS NULL THEN NULL ELSE l.identificador END AS via
                             FROM emprestimo_item x JOIN emprestimo e ON e.id=x.emprestimo_id
                             LEFT JOIN localizacao_fisica l ON l.id=x.localizacao_id
                            WHERE e.devolvido_em IS NULL
                              AND (x.item_codigo=? OR x.localizacao_id=(SELECT localizacao_id FROM item_localizacao WHERE item_codigo=?))
                            ORDER BY e.id DESC LIMIT 1""", (codigo, codigo)).fetchone()


@router.get("/itens/{codigo}/emprestimo")
def emprestimo_do_item(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict | None:
    """O empréstimo em aberto que tirou esta folha do lugar (ela mesma ou o recipiente dela), ou null."""
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM item WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, f"A folha {codigo} não existe no painel")
        r = _emprestimo_do_item(con, codigo)
        return {**dict(r), "atrasado": bool(r["atrasado"])} if r else None
    finally:
        con.close()


@router.get("/emprestimos/{eid}")
def detalhe(eid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        r = con.execute(_SELECT + " WHERE e.id=?", (eid,)).fetchone()
        if not r:
            raise HTTPException(404, "Empréstimo não encontrado")
        hist = [dict(h) for h in con.execute("SELECT tipo, ator, detalhe, quando FROM evento WHERE entidade='emprestimo' AND codigo=? ORDER BY id", (str(eid),))]
        return {**_linha(r), **_conteudo(con, eid), "historico": hist}
    finally:
        con.close()


@router.post("/emprestimos")
def criar(d: NovoEmprestimo, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.tipo not in TIPOS:
        raise HTTPException(400, "Tipo inválido: use consulta ou emprestimo")
    nome = (d.nome or "").strip()
    if not nome:
        raise HTTPException(400, "Informe o nome de quem vai consultar ou levar o material")
    cods = list(dict.fromkeys(c.strip().upper() for c in d.itens if c and c.strip()))
    lids = list(dict.fromkeys(int(x) for x in d.localizacoes))
    if not cods and not lids:
        raise HTTPException(400, "Escolha ao menos uma folha ou uma caixa")
    con = connect()
    try:
        hoje = _hoje(con)
        saida = _data(d.saida_em, "data de saída") or hoje
        prazo = _data(d.prazo, "prazo")
        if not prazo:
            if d.tipo == "emprestimo":
                raise HTTPException(400, "Informe até quando o material deve voltar (prazo)")
            prazo = saida
        if prazo < saida:
            raise HTTPException(400, "O prazo não pode ser antes da data de saída")
        resp = d.responsavel_id or u["id"]
        if not con.execute("SELECT 1 FROM usuario WHERE id=? AND ativo=1 AND papel!='leitura'", (resp,)).fetchone():
            raise HTTPException(400, "Responsável inválido")
        for c in cods:
            if not con.execute("SELECT 1 FROM item WHERE codigo=?", (c,)).fetchone():
                raise HTTPException(404, f"A folha {c} não existe no painel. Confira o código.")
        for lid in lids:
            if not con.execute("SELECT 1 FROM localizacao_fisica WHERE id=?", (lid,)).fetchone():
                raise HTTPException(404, f"A caixa ou local {lid} não existe")
        # o que já está fora não sai de novo
        for c in cods:
            r = _emprestimo_do_item(con, c)
            if r:
                raise HTTPException(409, f"A folha {c} já está fora: com {r['nome']} até {_br(r['prazo'])}" + (f" (dentro de {r['via']})" if r["via"] else ""))
        for lid in lids:
            r = con.execute("""SELECT e.nome, e.prazo, l.identificador FROM emprestimo_item x JOIN emprestimo e ON e.id=x.emprestimo_id
                                 JOIN localizacao_fisica l ON l.id=x.localizacao_id WHERE e.devolvido_em IS NULL AND x.localizacao_id=?""", (lid,)).fetchone()
            if r:
                raise HTTPException(409, f"{r['identificador']} já está fora: com {r['nome']} até {_br(r['prazo'])}")
        eid = con.execute("""INSERT INTO emprestimo (tipo, nome, contato, instituicao, saida_em, prazo, responsavel_id, observacao, criado_por)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                          (d.tipo, nome, (d.contato or "").strip() or None, (d.instituicao or "").strip() or None, saida, prazo, resp,
                           (d.observacao or "").strip() or None, u["id"])).lastrowid
        for c in cods:
            con.execute("INSERT INTO emprestimo_item (emprestimo_id, item_codigo) VALUES (?,?)", (eid, c))
        for lid in lids:
            con.execute("INSERT INTO emprestimo_item (emprestimo_id, localizacao_id) VALUES (?,?)", (eid, lid))
        idents = [con.execute("SELECT identificador FROM localizacao_fisica WHERE id=?", (lid,)).fetchone()[0] for lid in lids]
        _evento(con, eid, "criado", u["email"], {"tipo": d.tipo, "nome": nome, "prazo": prazo, "folhas": cods, "locais": idents})
        for lid in lids:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,?,?,?)",
                        (str(lid), "emprestada", u["email"], json.dumps({"emprestimo": eid, "nome": nome, "prazo": prazo}, ensure_ascii=False)))
        con.commit()
        partes = [f"{len(cods)} folha{'s' if len(cods) != 1 else ''}" if cods else None, ", ".join(idents) if idents else None]
        o_que = " e ".join(p for p in partes if p)
        return {"id": eid, "mensagem": f"{'Consulta presencial registrada' if d.tipo == 'consulta' else 'Empréstimo registrado'}: {o_que} com {nome} até {_br(prazo)}"}
    finally:
        con.close()


@router.post("/emprestimos/{eid}/devolver")
def devolver(eid: int, d: Devolucao | None = None, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT id, nome, devolvido_em, observacao FROM emprestimo WHERE id=?", (eid,)).fetchone()
        if not r:
            raise HTTPException(404, "Empréstimo não encontrado")
        if r["devolvido_em"]:
            raise HTTPException(409, "Este material já foi devolvido")
        obs = (d.observacao or "").strip() if d else ""
        nova_obs = r["observacao"]
        if obs:
            nova_obs = ((r["observacao"] + "\n") if r["observacao"] else "") + "Na devolução: " + obs
        con.execute("UPDATE emprestimo SET devolvido_em=datetime('now'), devolvido_por=?, observacao=? WHERE id=?", (u["id"], nova_obs, eid))
        _evento(con, eid, "devolvido", u["email"], {"nome": r["nome"], "observacao": obs} if obs else {"nome": r["nome"]})
        con.commit()
        return {"ok": True, "mensagem": f"Devolução registrada: o material de {r['nome']} voltou"}
    finally:
        con.close()


def _br(iso: str | None) -> str:
    if not iso:
        return "—"
    s = str(iso)[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
