"""Dados da foto: ano da foto, estágio e fotógrafo (21/10/2026).

Pedido (Rafa): "seria bom separar as fotos por época… fotos de 1990, 2000, 2010, de diferentes fotógrafos e contextos" e
"fotos precisa por ano da foto, estagio, fotografo".

- Guardado na folha: item.foto_ano (texto: "1992", "c. 1992", "década de 1990"), item.foto_estagio, item.foto_fotografo (migração 144).
- Preenchido pela revisão da folha (PATCH /api/itens/{c}) ou em lote: POST /api/itens/fotos/dados (marca as fotos e preenche os três).
- A página do projeto agrupa as fotos (S03, S04, S05) em blocos por ano da foto, estágio e fotógrafo, do ano mais antigo ao mais novo.
- O "fotógrafo" que o CAMP Vision lê (contrato 2.2) entra como valor inicial na importação, só se a folha ainda não tiver um.
- Site: o painel NÃO cria metadado. Envia cada valor só se a coleção já tiver um metadado de TEXTO com um dos nomes de NOMES_NO_SITE
  (o site tem "Fotógrafo", "Época" e "Contexto": ano da foto → Época, estágio → Contexto). Folha já no site recebe o valor
  novo em segundo plano; falha vira pendência e nunca desfaz o que foi salvo no painel.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["fotos"])

SERIES_FOTO = ("S03", "S04", "S05")          # Fotografias, Negativos, Slides
CAMPOS = ("foto_ano", "foto_estagio", "foto_fotografo")
ROTULOS = {"foto_ano": "Ano da foto", "foto_estagio": "Estágio", "foto_fotografo": "Fotógrafo"}
LIMITES = {"foto_ano": 40, "foto_estagio": 80, "foto_fotografo": 200}
# sugestões na tela (a pessoa pode escrever outro); a lista final é decisão do Rafa
ESTAGIOS = ("Em construção", "Obra concluída", "Em uso", "Reforma", "Maquete", "Evento")
# metadados que o site PODE já ter (procura por nome, sem diferenciar maiúsculas); o primeiro que existir recebe o valor
# 21/10: o site criou "Época" e "Contexto" (camp-wordpress CAMP-055, roteiro FOTOS-2) e agrupa as fotos por eles: esses vêm primeiro
NOMES_NO_SITE = {"foto_ano": ("Época", "Data do registro fotográfico", "Ano da foto", "Data da foto"),
                 "foto_estagio": ("Contexto", "Estágio da obra", "Estágio", "Fase da obra"),
                 "foto_fotografo": ("Fotógrafo", "Fotógrafa", "Fotógrafo(a)", "Autor da fotografia")}
MAX_ITENS = 2000
_ANO = re.compile(r"(?<!\d)(1[89]\d\d|20\d\d|2100)(?!\d)")


def _limpo(v) -> str:
    return " ".join(str(v or "").split())


def ano_de(texto) -> int | None:
    """Primeiro ano de 4 dígitos (1800–2100) do texto: a ordem dos blocos. "década de 1990" → 1990; "c. 1992" → 1992."""
    m = _ANO.search(str(texto or ""))
    return int(m.group(1)) if m else None


def normalizar(campo: str, valor) -> str | None:
    """Valor da tela → coluna. Vazio = limpa (None). Inválido → HTTPException 400 com a mensagem para a pessoa."""
    v = _limpo(valor)
    if not v:
        return None
    if len(v) > LIMITES[campo]:
        raise HTTPException(400, f"{ROTULOS[campo]}: máximo de {LIMITES[campo]} caracteres (tem {len(v)})")
    if campo == "foto_ano" and ano_de(v) is None:
        raise HTTPException(400, "Ano da foto: escreva o ano com 4 dígitos (ex.: 1992, c. 1992, década de 1990)")
    return v


def metadado_no_site(con, colecao_id: int, campo: str):
    """(id, nome) do metadado de texto que a coleção do site já tem para este campo; senão (None, None). O painel nunca o cria."""
    for nome in NOMES_NO_SITE[campo]:
        r = con.execute("SELECT id, nome, tipo FROM wp_metadado WHERE colecao_id=? AND lower(nome)=lower(?)", (colecao_id, nome)).fetchone()
        if r and not any(t in (r["tipo"] or "") for t in ("Taxonomy", "Relationship", "Compound", "Date", "Numeric")):
            return r["id"], r["nome"]
    return None, None


def para_o_site(con, colecao_id: int, item) -> list[tuple[int, str, str]]:
    """[(metadado_id, nome, valor)] dos dados da foto preenchidos que o site sabe receber."""
    out = []
    for c in CAMPOS:
        v = item[c] if c in item.keys() else None
        if not v:
            continue
        mid, nome = metadado_no_site(con, colecao_id, c)
        if mid:
            out.append((mid, nome, v))
    return out


def enviar_ao_site(codigo: str, ator: str) -> dict:
    """Folha já no site: grava nela os dados da foto de agora (inclusive o que foi apagado). Nunca levanta; falha vira pendência."""
    from . import publicador
    con = connect()
    con.isolation_level = None
    out = {"codigo": codigo, "metadados": [], "erro": None}
    try:
        i = con.execute("SELECT * FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i or not i["tainacan_item_id"]:
            out["erro"] = "a folha não tem item no site"; return out
        envio = []
        for c in CAMPOS:
            mid, nome = metadado_no_site(con, publicador.COL_ACERVO, c)
            if mid:
                envio.append((mid, nome, i[c] or ""))
        if not envio:
            return out
        wp = publicador.WP()
        for mid, nome, v in envio:
            wp.definir_metadado(int(i["tainacan_item_id"]), mid, v); out["metadados"].append(nome)
        publicador.renovar_no_site(wp, int(i["tainacan_item_id"]), codigo)     # 21/10: o público vê na hora
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_dados_foto',?,?)",
                    (codigo, ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        publicador._pendencia(con, "item", codigo, "pendente_dados_foto_no_site",
                              "Os dados da foto (ano, estágio, fotógrafo) mudaram no painel, mas o site não aceitou: " + out["erro"])
    finally:
        con.close()
    return out


def enviar_varios(codigos: list[str], ator: str) -> None:
    for c in codigos:
        try:
            enviar_ao_site(c, ator)
        except Exception:  # noqa: BLE001
            pass


def valor_inicial_fotografo(con, codigo: str, lido) -> None:
    """Importação: o fotógrafo que o CAMP Vision leu entra só se a folha ainda não tiver um (nunca sobrescreve o da pessoa)."""
    v = _limpo(lido)[:LIMITES["foto_fotografo"]]
    if v:
        con.execute("UPDATE item SET foto_fotografo=? WHERE codigo=? AND (foto_fotografo IS NULL OR foto_fotografo='')", (v, codigo))


class DadosFoto(BaseModel):
    itens: list[str]
    ano: str | None = None           # ausente = não mexe; "" = apaga
    estagio: str | None = None
    fotografo: str | None = None


@router.post("/itens/fotos/dados")
def gravar_dados(d: DadosFoto, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Preenche ano da foto, estágio e fotógrafo de várias folhas de uma vez. Campo que não veio fica como está; vazio apaga."""
    mudar = {}
    for campo, chave in (("foto_ano", "ano"), ("foto_estagio", "estagio"), ("foto_fotografo", "fotografo")):
        if chave in d.model_fields_set:
            mudar[campo] = normalizar(campo, getattr(d, chave))
    itens = list(dict.fromkeys(c.strip() for c in d.itens if c and c.strip()))
    if not itens:
        raise HTTPException(400, "Marque pelo menos uma folha.")
    if len(itens) > MAX_ITENS:
        raise HTTPException(400, f"No máximo {MAX_ITENS} folhas de uma vez.")
    if not mudar:
        raise HTTPException(400, "Preencha o ano da foto, o estágio ou o fotógrafo.")
    con = connect()
    try:
        marca = ",".join("?" * len(itens))
        linhas = {r["codigo"]: r for r in con.execute(f"SELECT codigo, tainacan_item_id, {', '.join(CAMPOS)} FROM item WHERE codigo IN ({marca})", itens)}
        faltam = [c for c in itens if c not in linhas]
        if faltam:
            raise HTTPException(404, "Folha não existe: " + ", ".join(faltam[:5]) + (" …" if len(faltam) > 5 else ""))
        mudadas, no_site = [], []
        for c in itens:
            i = linhas[c]
            novos = {k: v for k, v in mudar.items() if (i[k] or None) != v}
            if not novos:
                continue
            con.execute(f"UPDATE item SET {', '.join(f'{k}=?' for k in novos)}, atualizado_em=datetime('now') WHERE codigo=?", (*novos.values(), c))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (c, u["email"], json.dumps({"antes": {k: i[k] for k in novos}, "depois": novos, "em_lote": len(itens)}, ensure_ascii=False)))
            mudadas.append(c)
            if i["tainacan_item_id"]:
                no_site.append(c)
        con.commit()
    finally:
        con.close()
    if no_site:
        tarefas.add_task(enviar_varios, no_site, u["email"])
    return {"ok": True, "mudadas": mudadas, "iguais": len(itens) - len(mudadas), "site_em_segundo_plano": no_site}


@router.get("/fotos/sugestoes")
def sugestoes(fundo: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Estágios e fotógrafos para escolher (os já usados no fundo primeiro). Só sugestão: a pessoa pode escrever outro."""
    con = connect()
    try:
        def usados(col):
            vistos, out = set(), []
            consultas = []
            if fundo:
                consultas.append((f"SELECT {col}, COUNT(*) FROM item WHERE {col} IS NOT NULL AND {col}<>'' AND codigo LIKE ? GROUP BY 1 ORDER BY 2 DESC LIMIT 50", (fundo.upper() + "-%",)))
            consultas.append((f"SELECT {col}, COUNT(*) FROM item WHERE {col} IS NOT NULL AND {col}<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 100", ()))
            for q, a in consultas:
                for (v, _n) in con.execute(q, a):
                    if v.casefold() not in vistos:
                        vistos.add(v.casefold()); out.append(v)
            return out
        est = usados("foto_estagio")
        est += [e for e in ESTAGIOS if e.casefold() not in {x.casefold() for x in est}]
        return {"estagios": est, "fotografos": usados("foto_fotografo"), "series_foto": list(SERIES_FOTO)}
    finally:
        con.close()
