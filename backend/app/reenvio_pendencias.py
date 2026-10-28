"""UX-47: reenvio ao site das escritas pendentes de FUNDO, PROJETO e ARQUITETO.

Quando uma gravação no site falha, o painel guarda a pendência em divergencia_site ('pendente_*', ver publicador._pendencia).
Até a UX-40 só as correções de folhas tinham reenvio (fila_correcao_site); as de fundo, projeto e arquiteto ficavam paradas.
Aqui, cada tipo reenviável é refeito a partir do estado ATUAL do painel (vai o valor de agora, não o antigo), pela mesma rotina
que a tela usa, e nunca cria no site o que já está lá:
- fundo  · pendente_criar_no_site      -> criar_fundo_no_site, depois de procurar no site o termo com o mesmo nome (não duplica)
- fundo  · pendente_renomear_no_site   -> renomear_fundo_no_site com o nome de agora
- fundo  · pendente_descricao_no_site  -> atualizar_descricao_fundo_no_site ("Sobre o acervo" de agora; vazio o site ignora)
- projeto· pendente_criar_no_site      -> procura o dossiê no site pelo código (espelho, depois o próprio site); achou: liga e completa
                                          os metadados; não achou: criar_dossie_no_site. Busca que falha = não cria.
- projeto· pendente_metadados_no_site  -> atualizar_dossie_no_site com os campos editados desde o último envio confirmado
- projeto· pendente_metadado_<nome>    -> grava esse metadado com o valor de agora
- projeto· pendente_capa_no_site       -> capa_no_site (a capa escolhida agora; sem escolha, volta à capa automática)
- agente · pendente_hub_no_site        -> enviar_agente_ao_hub com biografia, fontes, datas e retrato de agora (retrato já subido
                                          não sobe de novo; só apaga no site o que foi apagado no painel depois do último envio)
- agente · pendente_renomear_no_site   -> renomear_agente_no_site com o nome de agora
Ficam de fora (não são só escrita: publicam ou tiram do ar): 'pendente_status_no_site' e 'pendente_pagina_arquiteto' do fundo.

Sucesso fecha a pendência (_resolver_pendencia). Falha mantém, com o erro novo, e espera a próxima tentativa
(reenvio_pendencia_site). Erro passageiro (wp.erro_passageiro: site lento, 429/502/503/504) fica "ainda na fila", não conta como falha.
Quem chama (fila_correcao_site.executar_pendentes) segura a trava da rodada: botão e automático nunca andam juntos.
"""
from __future__ import annotations

import json
import time

from .db import connect

FIXOS = {("fundo", "pendente_criar_no_site"), ("fundo", "pendente_renomear_no_site"), ("fundo", "pendente_descricao_no_site"),
         ("projeto", "pendente_criar_no_site"), ("projeto", "pendente_metadados_no_site"), ("projeto", "pendente_capa_no_site"),
         ("agente", "pendente_hub_no_site"), ("agente", "pendente_renomear_no_site")}
PREFIXO_METADADO = "pendente_metadado_"
NOMES_ENTIDADE = {"fundo": "fundo", "projeto": "projeto", "agente": "arquiteto"}
# ordem na rodada: o que os outros usam vai antes (termo do fundo, nome do arquiteto, dossiê) e o resto depois
_ORDEM = {"fundo:pendente_criar_no_site": 0, "agente:pendente_renomear_no_site": 1, "fundo:pendente_renomear_no_site": 1,
          "projeto:pendente_criar_no_site": 2}


class NadaAEnviar(Exception):
    """O site não tem o que receber agora (ex.: o fundo ainda não está no site): a pendência fecha; o valor de agora vai quando ele for criado."""


def _tipo_conhecido(entidade: str, campo: str) -> bool:
    if (entidade, campo) in FIXOS:
        return True
    if entidade == "projeto" and campo.startswith(PREFIXO_METADADO):
        from .publicador import CAMPOS_PROJETO_SITE
        return campo[len(PREFIXO_METADADO):] in set(CAMPOS_PROJETO_SITE.values()) | {"Código de Catalogação", "Fundo", "Arquiteto"}
    return False


def _valida(con, entidade: str, codigo: str) -> bool:
    """A entidade existe e pode ir ao site (F000 · Convidado nunca vai; projeto mesclado ou descartado não recebe nada)."""
    from .publicador import CONVIDADO
    if entidade in ("fundo", "projeto") and str(codigo).upper().startswith(CONVIDADO):
        return False
    if entidade == "fundo":
        return bool(con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone())
    if entidade == "projeto":
        return bool(con.execute("SELECT 1 FROM projeto WHERE codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL", (codigo,)).fetchone())
    if entidade == "agente":
        return str(codigo).isdigit() and bool(con.execute("SELECT 1 FROM agente WHERE id=?", (int(codigo),)).fetchone())
    return False


def listar(con) -> list[dict]:
    """As pendências abertas de fundo/projeto/arquiteto que esta rotina sabe reenviar, uma por (entidade, código, campo), com `pronta`."""
    base = """SELECT d.id, d.entidade, d.codigo, d.campo, d.valor_painel, d.detectada_em{extra}
              FROM divergencia_site d{join}
              WHERE d.resolvida=0 AND d.entidade IN ('fundo','projeto','agente') AND d.campo LIKE 'pendente\\_%' ESCAPE '\\'
              ORDER BY d.id"""
    try:
        rows = con.execute(base.format(extra=", r.tentativas, r.proxima_em, (r.proxima_em IS NULL OR r.proxima_em <= datetime('now')) AS pronta",
                                       join=" LEFT JOIN reenvio_pendencia_site r ON r.divergencia_id=d.id")).fetchall()
    except Exception:  # noqa: BLE001 — banco sem a migração 199: todas prontas
        rows = con.execute(base.format(extra=", 0 AS tentativas, NULL AS proxima_em, 1 AS pronta", join="")).fetchall()
    out, vistos = [], set()
    for r in rows:
        chave = (r["entidade"], r["codigo"], r["campo"])
        if chave in vistos or not _tipo_conhecido(r["entidade"], r["campo"]) or not _valida(con, r["entidade"], r["codigo"]):
            continue
        vistos.add(chave)
        out.append({**dict(r), "pronta": bool(r["pronta"]), "tentativas": r["tentativas"] or 0})
    return out


def contar(con) -> dict:
    """Quantas pendências reenviáveis há, quantas já podem sair, a próxima tentativa e quantas por entidade (fundo, projeto, agente)."""
    try:
        lst = listar(con)
    except Exception:  # noqa: BLE001 — banco muito antigo
        return {"total": 0, "prontas": 0, "proxima_em": None, "por_entidade": {}}
    por = {}
    for x in lst:
        por[x["entidade"]] = por.get(x["entidade"], 0) + 1
    esperando = [x["proxima_em"] for x in lst if not x["pronta"] and x["proxima_em"]]
    return {"total": len(lst), "prontas": sum(1 for x in lst if x["pronta"]), "proxima_em": min(esperando) if esperando else None,
            "por_entidade": por}


def rotulo(con, entidade: str, codigo: str) -> str:
    """Como a pendência aparece no andamento e no resultado: "F040 (fundo)", "F040-P0001 (projeto)", "Nome (arquiteto)"."""
    if entidade == "agente":
        try:
            a = con.execute("SELECT forma_autorizada FROM agente WHERE id=?", (int(codigo),)).fetchone()
            if a and a[0]:
                return f"{a[0]} (arquiteto)"
        except (TypeError, ValueError):
            pass
    return f"{codigo} ({NOMES_ENTIDADE.get(entidade, entidade)})"


# ---------------------------------------------------------------- reenvio de cada tipo

def _ler(sql: str, args=()):
    con = connect()
    try:
        return con.execute(sql, args).fetchone()
    finally:
        con.close()


def _erro(r: dict):
    if r.get("erro"):
        raise RuntimeError(r["erro"])


def _fundo_criar(codigo: str, ator: str) -> str:
    from . import publicador as pub
    con = connect()
    try:
        f = con.execute("SELECT titulo, tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
        if f["tainacan_term_id"]:
            return "o fundo já está no site"
        tf, ta = pub._tax(con, "Fundos"), pub._tax(con, "Arquitetos")
        procurar = []                                  # (taxonomia, nome) que a criação ainda criaria
        if tf and not con.execute("SELECT 1 FROM wp_termo WHERE taxonomia_id=? AND nome=?", (tf, f["titulo"])).fetchone():
            procurar.append((tf, f["titulo"]))
        if ta:
            for a in con.execute("""SELECT a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id
                                    WHERE fa.fundo_codigo=? AND fa.papel='produtor' AND a.tainacan_term_id IS NULL""", (codigo,)).fetchall():
                if not con.execute("SELECT 1 FROM wp_termo WHERE taxonomia_id=? AND nome=?", (ta, a[0])).fetchone():
                    procurar.append((ta, a[0]))
    finally:
        con.close()
    # Não duplica: uma tentativa anterior pode ter criado o termo no site sem a resposta chegar ao painel. Procura no próprio site
    # (todos os termos da taxonomia) e põe no espelho o que já existe: criar_fundo_no_site usa o do espelho em vez de criar outro.
    achados = []
    if procurar:
        wp = pub.WP()
        for tid in {t for t, _n in procurar}:
            nomes = {" ".join(str(n).split()).casefold(): n for t, n in procurar if t == tid}
            for termo in wp.termos(tid):                   # falha aqui (site fora) = não cria; a pendência espera a próxima tentativa
                nome = " ".join(str(termo.get("name") or "").split()).casefold()
                if nome in nomes and termo.get("id"):
                    achados.append((tid, nomes.pop(nome), termo))
                if not nomes:
                    break
    if achados:
        con = connect()
        try:
            for tid, nome, t in achados:
                con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, json) VALUES (?,?,?,?,?)",
                            (int(t["id"]), tid, nome, t.get("slug"), json.dumps(t, ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
    _erro(pub.criar_fundo_no_site(codigo, ator))
    return "termo do fundo no site" + (" (o site já tinha: ligado, sem criar outro)" if achados else "")


def _fundo_renomear(codigo: str, ator: str) -> str:
    from . import publicador as pub
    f = _ler("SELECT titulo, tainacan_term_id FROM fundo WHERE codigo=?", (codigo,))
    if not f["tainacan_term_id"]:
        raise NadaAEnviar("o fundo ainda não está no site; o nome de agora vai quando ele for criado")
    r = pub.renomear_fundo_no_site(codigo, f["titulo"], ator)
    _erro(r)
    if not r.get("ok"):
        raise RuntimeError("O site não confirmou o nome do fundo")
    return f"nome do fundo: {f['titulo']}"


def _fundo_descricao(codigo: str, ator: str) -> str:
    from . import publicador as pub
    r = pub.atualizar_descricao_fundo_no_site(codigo, ator)
    _erro(r)
    if not r.get("enviado"):
        raise NadaAEnviar("o fundo ainda não está no site; o texto de agora vai quando ele for criado")
    return "texto do fundo (Sobre o acervo)"


def _projeto(codigo: str):
    return _ler("""SELECT p.*, f.titulo AS fundo_titulo, f.tainacan_term_id AS fundo_termo FROM projeto p
                   JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?""", (codigo,))


def dossie_existente_no_site(codigo: str) -> dict | None:
    """O dossiê deste projeto já existe no site? (uma criação anterior que o site fez sem a resposta chegar ao painel)
    1) o espelho do site; 2) o próprio site, pelo metadado "Código de Catalogação". Item ligado a OUTRO projeto não serve.
    Falha na busca do site LEVANTA (quem chama não cria às cegas)."""
    from . import publicador as pub
    from .wp import metadados_texto
    con = connect()
    try:
        ligados = {x[0] for x in con.execute("SELECT tainacan_item_id FROM projeto WHERE tainacan_item_id IS NOT NULL AND codigo<>?", (codigo,))}
        rows = [r for r in con.execute("SELECT id, status FROM wp_item WHERE colecao_id=? AND upper(codigo_detectado)=upper(?)",
                                       (pub.COL_PROJETOS, codigo)).fetchall() if r["id"] not in ligados]
        mid = pub._meta(con, pub.COL_PROJETOS, "Código de Catalogação")[0]
    finally:
        con.close()
    if rows:
        r = sorted(rows, key=lambda x: pub._ordem_preferida(x["status"], x["id"]))[0]
        return {"id": int(r["id"]), "status": r["status"], "como": "espelho do site", "item": None}
    wp = pub.WP()
    buscar = getattr(wp, "buscar_por_codigo", None)
    if not buscar or not mid:
        raise RuntimeError("Não consegui procurar o dossiê no site pelo código antes de criar: nada foi criado")
    bons = []
    for it in buscar(pub.COL_PROJETOS, mid, codigo) or []:
        if not it.get("id") or int(it["id"]) in ligados:
            continue
        if any(str(v).strip().upper() == codigo.upper() for v in metadados_texto(it).values()):
            bons.append(it)
    if not bons:
        return None
    it = sorted(bons, key=lambda x: pub._ordem_preferida(x.get("status"), x["id"]))[0]
    return {"id": int(it["id"]), "status": it.get("status"), "como": "busca no site pelo código", "item": it}


def _projeto_criar(codigo: str, ator: str) -> str:
    from . import publicador as pub
    p = _projeto(codigo)
    if p["tainacan_item_id"]:
        return "o dossiê já está no site"
    ja = dossie_existente_no_site(codigo)
    if not ja:
        r = pub.criar_dossie_no_site(codigo, ator)
        _erro(r)
        return "dossiê criado no site (rascunho)"
    # Já existe: liga (sem criar outro) e completa os metadados de agora, como a criação faria.
    iid = ja["id"]
    wp = pub.WP()
    con = connect()
    try:
        con.execute("UPDATE projeto SET tainacan_item_id=? WHERE codigo=? AND tainacan_item_id IS NULL", (iid, codigo))
        if ja["item"]:
            it = ja["item"]
            con.execute("INSERT OR IGNORE INTO wp_item (id, colecao_id, status, titulo, slug, url, codigo_detectado, fundo_detectado, projeto_detectado, metadados, json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (iid, pub.COL_PROJETOS, it.get("status"), it.get("title"), it.get("slug"), it.get("url"), codigo, p["fundo_codigo"], codigo,
                         "{}", json.dumps(it, ensure_ascii=False)))
        con.commit()
        valores = pub.valores_dossie(con, codigo, p)
    finally:
        con.close()
    feitos, falhas = [], []
    con = connect()
    con.isolation_level = None          # nada de transação aberta durante os pedidos ao site
    try:
        for nome, valor in valores.items():
            if valor in (None, ""):
                continue
            try:
                pub.gravar_metadado_dossie(con, wp, iid, nome, valor); feitos.append(nome)
            except Exception as e:  # noqa: BLE001 — cada metadado que falhar vira a sua própria pendência
                falhas.append(nome)
                pub._pendencia(con, "projeto", codigo, f"{PREFIXO_METADADO}{nome}", str(e)[:200])
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_dossie_ligado',?,?)",
                    (codigo, ator, json.dumps({"item_id": iid, "como": ja["como"], "metadados": feitos, "falharam": falhas}, ensure_ascii=False)))
    finally:
        con.close()
    return f"o site já tinha o dossiê ({iid}): ligado, sem criar outro"


_CAMPOS_EDITAVEIS_DOSSIE = ("titulo", "cidade", "ambito_conteudo", "endereco_obra")


def _campos_desde_ultimo_envio(codigo: str) -> dict:
    """Os campos do projeto mudados no painel depois do último envio confirmado ao site (evento site_metadados): é o que falhou."""
    from .publicador import CAMPOS_PROJETO_SITE
    validos = set(CAMPOS_PROJETO_SITE) | set(_CAMPOS_EDITAVEIS_DOSSIE)
    con = connect()
    try:
        ult = con.execute("SELECT COALESCE(MAX(id),0) FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='site_metadados'", (codigo,)).fetchone()[0]
        campos = {}
        for ev in con.execute("""SELECT tipo, detalhe FROM evento WHERE entidade='projeto' AND codigo=? AND id>? AND tipo IN ('editado','autoria_registrada')
                                 ORDER BY id""", (codigo, ult)).fetchall():
            try:
                d = json.loads(ev["detalhe"] or "{}")
            except ValueError:
                continue
            chaves = (d.get("depois") or {}).keys() if ev["tipo"] == "editado" else ("autoria", "papel_no_projeto")
            campos.update({k: True for k in chaves if k in validos})
        if not campos:                      # sem histórico: manda o que o painel tem preenchido (vazio não apaga nada no site)
            p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            campos = {k: True for k in CAMPOS_PROJETO_SITE if p[k] not in (None, "")}
        return campos
    finally:
        con.close()


def _projeto_metadados(codigo: str, ator: str) -> str:
    from . import publicador as pub
    p = _projeto(codigo)
    if not p["tainacan_item_id"]:
        raise NadaAEnviar("o projeto ainda não tem página no site; os dados de agora vão quando ela for criada")
    campos = _campos_desde_ultimo_envio(codigo)
    if not campos:
        raise NadaAEnviar("nenhum dado do projeto para enviar")
    r = pub.atualizar_dossie_no_site(codigo, campos, ator)
    _erro(r)
    return "dados do projeto: " + (", ".join(r.get("enviados") or []) or "nenhum (o site não tem esses campos)")


def _projeto_metadado(codigo: str, nome: str, ator: str) -> str:
    from . import publicador as pub
    p = _projeto(codigo)
    if not p["tainacan_item_id"]:
        raise NadaAEnviar("o projeto ainda não tem página no site; o valor de agora vai quando ela for criada")
    con = connect()
    try:
        valor = pub.valores_dossie(con, codigo, p).get(nome)
    finally:
        con.close()
    if valor in (None, ""):
        raise NadaAEnviar(f"“{nome}” está vazio no painel")
    wp = pub.WP()
    con = connect()
    try:
        pub.gravar_metadado_dossie(con, wp, p["tainacan_item_id"], nome, valor)
    finally:
        con.close()
    pub.renovar_no_site(wp, p["tainacan_item_id"], codigo, projeto=True)
    return f"{nome} do projeto"


def _projeto_capa(codigo: str, ator: str) -> str:
    from . import publicador as pub
    r = pub.capa_no_site(codigo, ator, limpar=True)       # sem capa escolhida agora: volta à capa automática do site
    _erro(r)
    if r.get("aguardando"):
        raise NadaAEnviar("a folha da capa ainda não está no site; a capa vai junto com ela")
    if not r.get("enviado"):
        raise NadaAEnviar("o projeto ainda não tem página no site")
    return "capa do projeto"


def meta_hub_agente(aid: int) -> dict:
    """O que vai à página do arquiteto agora: o preenchido (biografia, fontes, datas, retrato) e "__limpar__" só para o que foi
    APAGADO no painel depois do último envio confirmado (evento site_hub_arquiteto). Retrato já subido não sobe de novo."""
    from .publicador import HUB_LIMPAR, datas_hub_agente
    con = connect()
    try:
        a = con.execute("SELECT * FROM agente WHERE id=?", (aid,)).fetchone()
        r = con.execute("SELECT media_id FROM agente_retrato WHERE agente_id=?", (aid,)).fetchone()
        ult = con.execute("SELECT COALESCE(MAX(id),0) FROM evento WHERE entidade='agente' AND codigo=? AND tipo='site_hub_arquiteto'", (str(aid),)).fetchone()[0]
        apagados = set()
        for ev in con.execute("""SELECT tipo, detalhe FROM evento WHERE entidade='agente' AND codigo=? AND id>?
                                 AND tipo IN ('editado','biografia_apagada','retrato_removido')""", (str(aid), ult)).fetchall():
            if ev["tipo"] == "biografia_apagada":
                apagados |= {"historia", "fonte_historia"}
            elif ev["tipo"] == "retrato_removido":
                apagados.add("retrato")
            else:
                try:
                    dep = json.loads(ev["detalhe"] or "{}").get("depois") or {}
                except ValueError:
                    dep = {}
                apagados |= {k for k in ("historia", "fonte_historia") if k in dep and not (dep[k] or "").strip()}
    finally:
        con.close()
    meta = {}
    for campo, chave in (("historia", "_camp_bio"), ("fonte_historia", "_camp_bio_fontes")):
        if (a[campo] or "").strip():
            meta[chave] = a[campo].strip()
        elif campo in apagados:
            meta[chave] = HUB_LIMPAR
    meta.update(datas_hub_agente(a))
    if r:
        meta["_camp_foto_id"] = int(r["media_id"]) if r["media_id"] else "subir"
    elif "retrato" in apagados:
        meta["_camp_foto_id"] = HUB_LIMPAR
    return meta


def _agente_hub(codigo: str, ator: str) -> str:
    from . import publicador as pub
    aid = int(codigo)
    meta = meta_hub_agente(aid)
    if not meta:
        raise NadaAEnviar("nada preenchido para a página do arquiteto")
    r = pub.enviar_agente_ao_hub(aid, meta, ator)
    _erro(r)
    if not r.get("fundos"):
        raise NadaAEnviar("o arquiteto ainda não tem fundo no site; vai junto quando tiver")
    return "página do arquiteto (" + ", ".join(r["fundos"]) + ")"


def _agente_renomear(codigo: str, ator: str) -> str:
    from . import publicador as pub
    a = _ler("SELECT forma_autorizada, tainacan_term_id FROM agente WHERE id=?", (int(codigo),))
    if not a["tainacan_term_id"]:
        raise NadaAEnviar("o arquiteto ainda não está no site; o nome de agora vai quando ele for criado")
    r = pub.renomear_agente_no_site(int(codigo), a["forma_autorizada"], ator)
    _erro(r)
    if not r.get("ok"):
        raise RuntimeError("O site não confirmou o nome do arquiteto")
    return f"nome do arquiteto: {a['forma_autorizada']}"


def reenviar(p: dict, ator: str) -> str:
    """Refaz a gravação de UMA pendência com o estado atual do painel. Devolve o que foi enviado; levanta NadaAEnviar ou o erro do site."""
    e, c, campo = p["entidade"], p["codigo"], p["campo"]
    if e == "projeto" and campo.startswith(PREFIXO_METADADO):
        return _projeto_metadado(c, campo[len(PREFIXO_METADADO):], ator)
    fn = {("fundo", "pendente_criar_no_site"): _fundo_criar, ("fundo", "pendente_renomear_no_site"): _fundo_renomear,
          ("fundo", "pendente_descricao_no_site"): _fundo_descricao, ("projeto", "pendente_criar_no_site"): _projeto_criar,
          ("projeto", "pendente_metadados_no_site"): _projeto_metadados, ("projeto", "pendente_capa_no_site"): _projeto_capa,
          ("agente", "pendente_hub_no_site"): _agente_hub, ("agente", "pendente_renomear_no_site"): _agente_renomear}[(e, campo)]
    return fn(c, ator)


# ---------------------------------------------------------------- a rodada

def _registrar(p: dict, estado: str, erro: str | None) -> None:
    """Grava o resultado numa conexão curta: sucesso fecha a pendência; falha mantém, com o erro novo, e adia a próxima tentativa."""
    from .publicador import _resolver_pendencia
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        if estado == "enviada":
            _resolver_pendencia(con, p["entidade"], p["codigo"], p["campo"])
            try:
                con.execute("DELETE FROM reenvio_pendencia_site WHERE divergencia_id=?", (p["id"],))
            except Exception:  # noqa: BLE001 — banco sem a migração 199
                pass
        else:
            con.execute("UPDATE divergencia_site SET valor_painel=? WHERE entidade=? AND codigo=? AND campo=? AND resolvida=0",
                        ((erro or "")[:300], p["entidade"], p["codigo"], p["campo"]))
            segundos = min(3600, 60 * 2 ** min(int(p.get("tentativas") or 0), 6))
            try:
                con.execute("""INSERT INTO reenvio_pendencia_site (divergencia_id, tentativas, proxima_em, ultimo_erro, atualizado_em)
                               VALUES (?, 1, datetime('now', ?), ?, datetime('now'))
                               ON CONFLICT(divergencia_id) DO UPDATE SET tentativas=tentativas+1, proxima_em=excluded.proxima_em,
                               ultimo_erro=excluded.ultimo_erro, atualizado_em=excluded.atualizado_em""",
                            (p["id"], f"+{segundos} seconds", (erro or "")[:300]))
            except Exception:  # noqa: BLE001
                pass
        con.commit()
    finally:
        con.close()


def rodada(limite: int, orcamento_s: float, ator: str, ao_terminar_item=None) -> dict:
    """Uma passada pelas pendências prontas (no máximo `limite`, dentro de `orcamento_s`). Quem chama segura a trava da rodada."""
    from .wp import erro_passageiro
    resumo = {"enviadas": [], "falhas": [], "na_fila": [], "tentadas": 0}
    if limite <= 0:
        return resumo
    con = connect()
    try:
        prontas = [p for p in listar(con) if p["pronta"]]
        prontas.sort(key=lambda p: (_ORDEM.get(f"{p['entidade']}:{p['campo']}", 3), p["id"]))
        rot = {(p["entidade"], p["codigo"]): rotulo(con, p["entidade"], p["codigo"]) for p in prontas}
    finally:
        con.close()
    inicio = time.monotonic()
    for p in prontas[:limite]:
        if time.monotonic() - inicio >= orcamento_s:
            break
        resumo["tentadas"] += 1
        nome = rot[(p["entidade"], p["codigo"])]
        try:
            reenviar(p, ator)
            estado, erro = "enviada", None
        except NadaAEnviar:
            estado, erro = "enviada", None        # o site não tem o que receber agora; o valor de agora vai quando a coisa for criada
        except Exception as e:  # noqa: BLE001
            erro = str(e)[:300]
            estado = "na_fila" if erro_passageiro(e) or erro_passageiro(erro) else "falhou"
        _registrar(p, estado, erro)
        if estado == "enviada":
            resumo["enviadas"].append(nome)
        else:
            resumo["na_fila" if estado == "na_fila" else "falhas"].append({"codigo": nome, "erro": erro})
        if ao_terminar_item:
            try:
                if estado == "na_fila":
                    ao_terminar_item(nome, False, erro, na_fila=True)
                else:
                    ao_terminar_item(nome, estado == "enviada", erro)
            except Exception:  # noqa: BLE001 — o andamento na tela nunca derruba a rodada
                pass
    return resumo
