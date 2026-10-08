"""Criação de projeto com número do contador oficial (usada pela estação, pelo painel e pela resolução de uma decisão)."""
from __future__ import annotations

import json


def criar_projeto(con, fundo_codigo: str, titulo: str, ano: int | None, cidade: str | None, identificacao: str | None, ator: str,
                  detalhe: dict, endereco_obra: str | None = None, reservado_por: int | None = None) -> dict:
    """Pega o próximo P do fundo, grava numero_p, projeto e o evento 'criado'. NÃO faz commit (quem chama controla a transação)."""
    prox = con.execute("SELECT proximo FROM v_proximo_p WHERE fundo_codigo=?", (fundo_codigo,)).fetchone()[0]
    numero = int(prox[1:])
    codigo = f"{fundo_codigo}-{prox}"
    con.execute("INSERT INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,?)", (fundo_codigo, numero, reservado_por))
    con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, endereco_obra, identificacao_original) VALUES (?,?,?,?,?,?,?,?)",
                (codigo, fundo_codigo, numero, titulo, ano or 0, cidade, endereco_obra, identificacao))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'criado',?,?)",
                (codigo, ator, json.dumps(detalhe, ensure_ascii=False)))
    return {"codigo": codigo, "numero_projeto": prox, "fundo_codigo": fundo_codigo, "titulo": titulo, "ano": ano or 0, "cidade": cidade,
            "identificacao_original": identificacao}


def resposta_de_projeto(con, codigo: str, **extra) -> dict | None:
    """O mesmo formato que /reservar devolve, para um projeto que já existe."""
    p = con.execute("SELECT codigo, fundo_codigo, numero, titulo, ano, cidade, identificacao_original FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        return None
    return {"codigo": p[0], "numero_projeto": f"P{p[2]:04d}", "fundo_codigo": p[1], "titulo": p[3], "ano": p[4] or 0, "cidade": p[5],
            "identificacao_original": p[6], **extra}
