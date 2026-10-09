"""Criação de projeto com número do contador oficial (usada pela estação, pelo painel e pela resolução de uma decisão)."""
from __future__ import annotations

import json
import re


def proximo_numero(con, fundo_codigo: str, proximo_p_local: str | None = None) -> int:
    """Próximo P livre do fundo, sem nunca reusar um número (CV-27): o maior entre
    - o contador do painel (numero_p),
    - os códigos que o espelho do site já viu (wp_item.codigo_detectado),
    - os projetos em pastas do acervo que o CAMP Vision mandou (proximo_p_local = maior P local + 1)."""
    candidatos = [int(con.execute("SELECT proximo FROM v_proximo_p WHERE fundo_codigo=?", (fundo_codigo,)).fetchone()[0][1:])]
    padrao = re.compile(rf"^{re.escape(fundo_codigo)}-P(\d{{4}})")
    try:
        for (cod,) in con.execute("SELECT codigo_detectado FROM wp_item WHERE codigo_detectado LIKE ?", (f"{fundo_codigo}-P%",)):
            m = padrao.match(cod or "")
            if m:
                candidatos.append(int(m.group(1)) + 1)
    except Exception:  # noqa: BLE001 - banco sem o espelho do site: fica o contador
        pass
    m = re.match(rf"^{re.escape(fundo_codigo)}-P(\d{{4}})$", (proximo_p_local or "").strip().upper())
    if m:
        candidatos.append(int(m.group(1)))
    numero = max(candidatos)
    while con.execute("SELECT 1 FROM projeto WHERE codigo=?", (f"{fundo_codigo}-P{numero:04d}",)).fetchone():
        numero += 1                                     # nunca reusa
    return numero


def criar_projeto(con, fundo_codigo: str, titulo: str, ano: int | None, cidade: str | None, identificacao: str | None, ator: str,
                  detalhe: dict, endereco_obra: str | None = None, reservado_por: int | None = None) -> dict:
    """Pega o próximo P do fundo, grava numero_p, projeto e o evento 'criado'. NÃO faz commit (quem chama controla a transação)."""
    numero = proximo_numero(con, fundo_codigo, detalhe.get("proximo_p_local"))
    prox = f"P{numero:04d}"
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
