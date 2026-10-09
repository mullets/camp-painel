"""Fila de decisões: o painel verifica antes de agir e, na dúvida, PERGUNTA. Hoje: 'este projeto já existe no fundo? é o mesmo?'."""
from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException

from .projetos_novos import criar_projeto
from .similaridade import normalizar


def chave_efetiva(chave_reserva: str, fundo: str, titulo: str) -> str:
    """A chave da estação; sem ela, uma derivada do fundo + nome, para o mesmo pedido repetido cair na MESMA decisão."""
    return chave_reserva or "auto-" + hashlib.sha1(f"{fundo}|{normalizar(titulo)}".encode()).hexdigest()[:16]


def da_chave(con, chave: str):
    return con.execute("SELECT * FROM decisao WHERE chave=?", (chave,)).fetchone()


def abrir_projeto_parecido(con, chave: str, fundo: str, titulo: str, pedido: dict, parecidos: list[dict], origem: str) -> int:
    """Abre (ou devolve, se a chave já tem) a decisão 'é o mesmo projeto?'. NÃO faz commit."""
    ja = da_chave(con, chave)
    if ja:
        return ja["id"]
    return con.execute("INSERT INTO decisao (tipo, chave, fundo_codigo, titulo, contexto, origem) VALUES ('projeto_parecido',?,?,?,?,?)",
                       (chave, fundo, titulo, json.dumps({"pedido": pedido, "candidatos": parecidos}, ensure_ascii=False), origem)).lastrowid


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def resolver(con, did: int, acao: str, projeto_codigo: str | None, ator: str) -> dict:
    """'mesmo' = o que chegou é do projeto existente `projeto_codigo` (nada novo é criado). 'novo' = cria o projeto. NÃO faz commit."""
    d = con.execute("SELECT * FROM decisao WHERE id=?", (did,)).fetchone()
    if not d:
        raise HTTPException(404, "Decisão não existe")
    if d["situacao"] != "pendente":
        raise HTTPException(409, "Esta decisão já foi resolvida")
    if acao not in ("mesmo", "novo"):
        raise HTTPException(400, "acao deve ser 'mesmo' ou 'novo'")
    pedido = json.loads(d["contexto"]).get("pedido", {})
    if acao == "mesmo":
        if not projeto_codigo:
            raise HTTPException(400, "Escolha o projeto existente")
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=? AND fundo_codigo=?", (projeto_codigo, d["fundo_codigo"])).fetchone():
            raise HTTPException(400, "O projeto escolhido não existe neste fundo")
        codigo = projeto_codigo
        _evento(con, "projeto", codigo, "material_adicionado_ao_existente", ator,
                {"decisao_id": did, "titulo_recebido": d["titulo"], "origem": d["origem"], "identificacao_original": pedido.get("identificacao_original")})
    else:
        real = None if d["chave"].startswith("auto-") else d["chave"]
        novo = criar_projeto(con, d["fundo_codigo"], d["titulo"], pedido.get("ano"), pedido.get("cidade"), pedido.get("identificacao_original"), ator,
                             {"titulo": d["titulo"], "origem": d["origem"] if d["origem"] == "estacao" else "painel", "identificacao_original": pedido.get("identificacao_original"),
                              "operador": pedido.get("operador"), "chave_reserva": real, "decisao_id": did,
                              "proximo_p_local": pedido.get("proximo_p_local")}, reservado_por=None)
        codigo = novo["codigo"]
    con.execute("UPDATE decisao SET situacao='resolvida', resolucao=?, projeto_codigo=?, resolvida_em=datetime('now'), resolvida_por=? WHERE id=?",
                (acao, codigo, ator, did))
    _evento(con, "decisao", str(did), "decisao_resolvida", ator, {"acao": acao, "projeto": codigo, "titulo": d["titulo"]})
    return {"ok": True, "acao": acao, "projeto_codigo": codigo}
