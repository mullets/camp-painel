"""CAMP-124 (P3, 20/10): o que o painel tem de diferente do site num projeto já publicado, e "Enviar N alterações ao site".

Corrigir uma folha já publicada (título, tipo, nº de folha, escala, ano) grava só no painel: o site continua com o valor
antigo até alguém reenviar. Antes nada dizia isso na tela. Aqui:
- `conta_site(...)`: a conta "31 no site = 34 − 3 retidas", com o que falta/sobra quando não fecha;
- `pendentes(con, projeto)`: folhas no site com campo corrigido DEPOIS do último envio ao site (ou imagem girada/recortada);
- `enviar(projeto, ator)`: reenvia só esses campos (e a imagem), pelo mesmo caminho da edição pelo site (publicador).
O "último envio" é o evento do item 'site_item_criado' / 'site_item_reaproveitado' / 'site_alteracoes_enviadas' (ou, sem
nenhum deles, a 1ª publicação). Um campo que voltou ao valor de antes não conta.
"""
from __future__ import annotations

import json

from .db import connect

# campo local → (rótulo na tela, metadado no site)
CAMPOS = {
    "titulo": ("Título", "Título"),
    "tipo_documento": ("Tipo", "Tipo de desenho"),
    "folha": ("Nº da folha", "Folha"),
    "escala": ("Escala", "Escala"),
    "ano_folha": ("Ano", "Ano"),
}
EVENTOS_ENVIO = ("site_item_criado", "site_item_reaproveitado", "site_alteracoes_enviadas")


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def conta_site(itens_local: list[dict], codigos_site: list[str]) -> dict:
    """A conta painel × site por código. Explica a diferença pelas retidas e duplicatas (que não vão ao site);
    o que sobrar sem explicação (folha que devia estar no site e não está, ou que só existe no site) vai listado."""
    locais = {x["codigo"]: x for x in itens_local}
    # no site = o espelho do site (sincronização) + o que o próprio painel publicou (publicado ou rascunho), que o espelho ainda pode não ter
    no_site = {c for c in codigos_site if c} | {c for c, x in locais.items() if x.get("status_site") in ("no_ar", "rascunho")}
    retidas, duplicatas, nao_enviadas = [], [], []
    for c, x in locais.items():
        if c in no_site:
            continue
        if x.get("retida"):
            retidas.append(c)
        elif x.get("duplicata_de"):
            duplicatas.append(c)
        else:
            nao_enviadas.append(c)
    so_site = sorted(c for c in no_site if c not in locais)
    return {"painel": len(locais), "site": len(no_site), "retidas": sorted(retidas), "duplicatas": sorted(duplicatas),
            "nao_enviadas": sorted(nao_enviadas), "so_site": so_site, "fecha": not nao_enviadas and not so_site}


def pendentes(con, projeto: str) -> list[dict]:
    from .rotas_revisao import imagem_site_pendente
    itens = [dict(r) for r in con.execute(
        """SELECT codigo, titulo, tipo_documento, tipos_documento, folha, escala, ano_folha, status_site, publicado_em, tainacan_item_id
             FROM item WHERE projeto_codigo=? AND status_site IN ('no_ar','rascunho') AND tainacan_item_id IS NOT NULL ORDER BY codigo""", (projeto,))]
    if not itens:
        return []
    codigos = [i["codigo"] for i in itens]
    por_cod = {i["codigo"]: i for i in itens}
    marca = ",".join("?" * len(codigos))
    base: dict[str, int] = {}
    for r in con.execute(f"SELECT codigo, MAX(id) FROM evento WHERE entidade='item' AND codigo IN ({marca}) AND tipo IN ({','.join('?' * len(EVENTOS_ENVIO))}) GROUP BY codigo",
                         (*codigos, *EVENTOS_ENVIO)):
        base[r[0]] = r[1]
    antes: dict[str, dict] = {c: {} for c in codigos}
    # 21/10: sem evento de envio da folha, a referência é a 1ª publicação do projeto pela ORDEM dos eventos (id). Pela hora (em segundos),
    # a correção feita no mesmo segundo da publicação, ANTES dela, contava como "depois" e aparecia como alteração não enviada.
    pub_ev = con.execute("SELECT MIN(id) FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='site_publicar'", (projeto,)).fetchone()[0]
    for r in con.execute(f"SELECT id, codigo, detalhe, quando FROM evento WHERE entidade='item' AND tipo='editado' AND codigo IN ({marca}) ORDER BY id", codigos):
        i = por_cod[r["codigo"]]
        if r["codigo"] in base:
            if r["id"] <= base[r["codigo"]]:
                continue
        elif pub_ev and r["id"] < pub_ev:
            continue
        elif i["publicado_em"] and r["quando"] < i["publicado_em"]:
            continue
        try:
            a = (json.loads(r["detalhe"] or "{}") or {}).get("antes") or {}
        except ValueError:
            a = {}
        for k in CAMPOS:
            if k in a and k not in antes[r["codigo"]]:
                antes[r["codigo"]][k] = a[k]          # o valor que o site tem é o de ANTES da 1ª correção depois do envio
    out = []
    for i in itens:
        c = i["codigo"]
        campos = []
        for k, v0 in antes[c].items():
            agora = (i["tipos_documento"] or i["tipo_documento"]) if k == "tipo_documento" else i[k]
            if _txt(agora) != _txt(v0):
                campos.append({"campo": k, "rotulo": CAMPOS[k][0], "antes": _txt(v0), "depois": _txt(agora)})
        img = imagem_site_pendente(con, c)
        if campos or img:
            out.append({"codigo": c, "campos": campos, "imagem": img})
    return out


def enviar_sozinho() -> bool:
    """21/10 (Rafa: "ao alterar aí, já altere no site automaticamente"): configuração site.enviar_correcoes_sozinho (sem a chave: sim)."""
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='site.enviar_correcoes_sozinho'").fetchone()
    finally:
        con.close()
    return not r or str(r[0]).strip() != "0"


import threading as _threading  # noqa: E402
_TRAVAS: dict = {}
_TRAVA_GERAL = _threading.Lock()


def enviar_folhas_agora(codigos: list[str], ator: str) -> None:
    """Segundo plano, logo depois de salvar: a folha já publicada recebe no site a correção (campos e imagem). Nunca levanta.
    Uma vez por projeto de cada vez (duas correções seguidas não mandam a mesma coisa duas vezes). Se o site recusar, a folha
    continua em "alteradas depois de publicar", com o botão para tentar de novo."""
    if not codigos or not enviar_sozinho():
        return
    por_projeto: dict = {}
    for c in codigos:
        por_projeto.setdefault(str(c)[:10], []).append(c)
    for pj, cs in por_projeto.items():
        with _TRAVA_GERAL:
            trava = _TRAVAS.setdefault(pj, _threading.Lock())
        with trava:
            try:
                enviar(pj, ator, cs)
            except Exception:  # noqa: BLE001
                pass


def enviar(projeto: str, ator: str, codigos: list[str] | None = None) -> dict:
    """Reenvia ao site os campos corrigidos e a imagem nova de cada folha pendente (ou só das `codigos`). Nunca desfaz nada no painel;
    a folha só sai da lista quando o site aceitou tudo dela."""
    from . import publicador
    from .rotas_revisao import _imagem_site_resolvida
    con = connect()
    try:
        lista = pendentes(con, projeto)
        if codigos is not None:
            lista = [x for x in lista if x["codigo"] in set(codigos)]
        dados = {}
        for p in lista:
            i = con.execute("""SELECT i.*, p.titulo AS projeto_titulo, p.ano AS projeto_ano, s.nome AS serie_nome
                                 FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo LEFT JOIN serie s ON s.codigo=i.serie_codigo
                                WHERE i.codigo=?""", (p["codigo"],)).fetchone()
            md, titulo_pag = {}, None
            for c in p["campos"]:
                k = c["campo"]
                nome = CAMPOS[k][1]
                if k == "titulo":
                    titulo_pag = f"{(i['titulo'] or i['tipo_documento'] or i['serie_nome'])} — {p['codigo'].split('-')[1]} — {i['projeto_titulo']}"
                    valor = titulo_pag
                elif k == "ano_folha":
                    valor = str(i["ano_folha"] or i["projeto_ano"] or "")
                elif k == "tipo_documento":
                    valor = i["tipos_documento"] or i["tipo_documento"] or ""
                else:
                    valor = _txt(i[k])
                mid, _ = publicador._meta(con, publicador.COL_ACERVO, nome)
                if not mid:
                    continue
                api = publicador._tipos_para_site(con, p["codigo"], mid, valor) if k == "tipo_documento" and valor else valor
                md[nome] = (mid, api, valor)
            dados[p["codigo"]] = (i["tainacan_item_id"], titulo_pag, md, p["imagem"], i["giro_manual"] or 0, p)
        con.commit()
    finally:
        con.close()
    enviadas, falhas = [], []
    for cod, (wid, titulo_pag, md, img, giro, p) in dados.items():
        erros = []
        if titulo_pag is not None or md:
            r = publicador.atualizar_folha_no_site(cod, wid, publicador.COL_ACERVO, titulo_pag, None, md, ator)
            erros += [f"{x['campo']}: {x['erro']}" for x in r.get("falhas") or []]
        if img:
            try:
                publicador.girar_imagem_no_site(cod, giro)
            except Exception as e:  # noqa: BLE001
                erros.append(f"imagem: {str(e)[:200]}")
        con = connect()
        try:
            if not erros:
                if img:
                    _imagem_site_resolvida(con, cod)
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_alteracoes_enviadas',?,?)",
                            (cod, ator, json.dumps({"campos": p["campos"], "imagem": img}, ensure_ascii=False)))
                enviadas.append(cod)
            else:
                falhas.append({"codigo": cod, "erro": "; ".join(erros)[:300]})
            con.commit()
        finally:
            con.close()
    return {"ok": not falhas, "enviadas": enviadas, "falhas": falhas, "total": len(dados)}
