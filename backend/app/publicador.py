"""Escritas no site que acompanham cadastros do painel. Falha no site nunca desfaz o cadastro local:
registra divergência para tentar de novo."""
from __future__ import annotations

import functools
import json
import re
import unicodedata

from fastapi import HTTPException

from .db import connect
from .wp import WP


def nome_arquivo_site(titulo_folha: str | None, projeto_titulo: str | None, codigo: str) -> str:
    """B11 · Nome do arquivo que o site guarda (vira o nome da imagem no Google): o que é a folha + o projeto + o código.
    Ex.: planta-de-situacao-edificio-taruma-F026-P0001-1968-S01-D00003.jpg. Só vale para envios novos (o WordPress não renomeia)."""
    base = " ".join(x for x in (titulo_folha, projeto_titulo) if x)
    s = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80].rstrip("-")
    return f"{s}-{codigo}.jpg" if s else f"{codigo}.jpg"

CREDITO_AUTORIA_NAO_CONFIRMADA = "Autoria não confirmada"   # CAMP-046 (contrato 2.4)
CONVIDADO = "F000"  # fundo Convidado: material de terceiros, nunca vai ao site



def descricao_folha(i) -> str:
    """Frase da descrição da folha no site, montada só com as partes que existem: folha sem título NÃO começa com '. ',
    e 'Projeto X' não vira 'do projeto Projeto X'."""
    pt = (i["projeto_titulo"] or "").strip()
    de = "de" if pt.lower().startswith("projeto") else "do projeto"
    corpo = f"{i['serie_nome']} {de} {pt} ({i['projeto_ano'] or 's.d.'}), fundo {i['fundo_titulo']}"
    partes = [i["titulo"].strip()] if (i["titulo"] or "").strip() else []
    partes.append(corpo)
    return ". ".join(partes) + "."

def _nunca_convidado(func):
    """F000 · Convidado guarda material de TERCEIROS digitalizado na CAMP: nada dele
    (fundo, dossiê, folha, status) pode ser criado ou mudado no site."""
    @functools.wraps(func)
    def envolto(*args, **kwargs):
        codigo = kwargs.get("codigo", args[0] if args else "")
        if str(codigo or "").strip().upper().startswith(CONVIDADO):
            raise HTTPException(403, "F000 · Convidado é material de terceiros — não vai ao site")
        return func(*args, **kwargs)
    return envolto

COL_PROJETOS = 8007


def _tax(con, nome):
    r = con.execute("SELECT id FROM wp_taxonomia WHERE nome=?", (nome,)).fetchone()
    return r[0] if r else None


# IDs dos metadados que o plugin do site (camp-acervo-auto-pages, includes/class-config.php) conhece. O espelho (wp_metadado, por NOME) manda;
# estes entram quando o espelho não tem o nome (sincronização antiga ou nome diferente no site). CAMP-035/036.
IDS_METADADOS_DO_PLUGIN = {
    8013: {"Código do documento": 8030, "Fundo": 8032, "Arquiteto": 8035, "Série": 8038, "Tipo de arquivo": 8041, "Projeto": 8044,
           "Ano": 8046, "Cliente": 8048, "Endereço": 8050, "Escala": 8052, "Folha": 8054, "Título": 808},
    8007: {"Fundo": 8400, "Arquiteto": 8403, "Ano": 8439, "Código de Catalogação": 811},
}
APELIDOS_METADADO = {"Suporte": ("Suporte original",)}      # o painel diz "Suporte" (como o plugin); o espelho antigo pode ter o nome velho


def _meta(con, colecao_id, nome):
    """(id, tipo) do metadado: primeiro pelo nome no espelho do site; depois pelo ID que o plugin do site conhece; senão (None, None)."""
    for n in (nome, *APELIDOS_METADADO.get(nome, ())):
        r = con.execute("SELECT id, tipo FROM wp_metadado WHERE colecao_id=? AND nome=?", (colecao_id, n)).fetchone()
        if r:
            return (r[0], r[1])
    fixo = IDS_METADADOS_DO_PLUGIN.get(int(colecao_id), {}).get(nome)
    return (fixo, None) if fixo else (None, None)


import threading as _threading  # noqa: E402
_TRAVA_METADADO = _threading.Lock()   # 21/10: folhas vão ao site em paralelo; só uma cria o metadado (a outra acha o que já existe)


def _garantir_metadado_origem(con, wp) -> int | None:
    """CV-01: cria UMA vez, na coleção Acervo CAMP, o metadado de texto "Arquivo de origem" (oculto ao público)
    e o registra no espelho. Falhou: devolve None e a folha sobe sem ele (fica pendência)."""
    with _TRAVA_METADADO:
        ja = con.execute("SELECT id FROM wp_metadado WHERE colecao_id=? AND nome='Arquivo de origem'", (COL_ACERVO,)).fetchone()
        if ja:
            return ja[0]
        return _criar_metadado_origem(con, wp)


def _criar_metadado_origem(con, wp) -> int | None:
    try:
        m = wp.criar_metadado(COL_ACERVO, "Arquivo de origem",
                              "Pasta + nome original do arquivo digitalizado (CAMP Vision). Uso interno: reconciliação e releitura.")
    except Exception as e:  # noqa: BLE001
        _pendencia(con, "colecao", str(COL_ACERVO), "pendente_metadado_Arquivo de origem", str(e)[:200])
        return None
    mid = m.get("id") if isinstance(m, dict) else None
    if mid:
        con.execute("INSERT OR REPLACE INTO wp_metadado (id, colecao_id, nome, tipo, taxonomia_id, json) VALUES (?,?,?,?,?,?)",
                    (mid, COL_ACERVO, "Arquivo de origem", m.get("metadata_type"), None, json.dumps(m, ensure_ascii=False)))
    return mid


def _pendencia(con, entidade, codigo, campo, detalhe):
    if con.execute("SELECT 1 FROM divergencia_site WHERE entidade=? AND codigo=? AND campo=? AND resolvida=0", (entidade, codigo, campo)).fetchone():
        return                                    # já está na lista: publicar de novo não empilha o mesmo aviso
    con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)",
                (entidade, codigo, campo, detalhe[:300], None))


HUB_LIMPAR = "__limpar__"     # CAMP-015: valor especial que o painel manda para APAGAR um campo do hub no site (vazio continua ignorado pelo site)
EM_ORGANIZACAO = "Documentação em organização."
TIPO_ENTRADA = {"doacao": "Doação", "comodato": "Comodato", "deposito": "Depósito", "compra": "Compra", "transferencia": "Transferência", "outro": "Outra forma de entrada"}


# B1: campos da seção "Sobre o acervo" da página-hub do arquiteto no site (post meta da página, lidos pelo
# plugin camp-acervo-auto-pages em class-render.php::acervo_description). Os marcados "sempre" vão com o texto
# padrão quando vazios; os outros, vazios, apagam o campo no site.
HUB_CAMPOS = [("_camp_acervo_periodo", "Período abrangido", False), ("_camp_acervo_extensao", "Extensão física", False),
              ("_camp_acervo_historico", "Histórico do acervo e da custódia", False), ("_camp_acervo_procedencia", "Procedência", True),
              ("_camp_acervo_ingresso", "Forma e data de ingresso", True), ("_camp_acervo_doador", "Doador / cedente", False),
              ("_camp_acervo_acesso", "Condições de acesso e reprodução", True)]


def _frase(t: str) -> str:
    t = (t or "").strip()
    return t if not t or t[-1] in ".!?" else t + "."


def campos_hub_fundo(con, codigo: str, com_padrao: bool = False) -> tuple[dict, list]:
    """B1: {meta do site: texto} e a lista do que ainda falta preencher no painel.

    CAMP-037: campo vazio no painel NÃO leva mais o texto padrão "Documentação em organização." ao site (o painel não consegue ler o que já
    está lá e sobrescreveria texto escrito à mão no WordPress). O site já esconde o campo vazio. `com_padrao=True` devolve o texto antigo.

    O nome de quem entregou o acervo só sai com fundo.mostrar_doador; sem isso, a procedência que cita
    o nome também não sai (a forma de entrada sai, sem o nome).
    """
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f:
        return {}, []
    mostrar = bool(f["mostrar_doador"])
    entradas = con.execute("SELECT tipo, data, entregue_por FROM entrada_acervo WHERE fundo_codigo=? ORDER BY COALESCE(data,''), id", (codigo,)).fetchall()
    dr = con.execute("SELECT licenca, restricoes, credito_exigido FROM direitos_fundo WHERE fundo_codigo=?", (codigo,)).fetchone()
    nomes = list(dict.fromkeys(e["entregue_por"].strip() for e in entradas if (e["entregue_por"] or "").strip()))
    proc = (f["procedencia"] or "").strip()
    if proc and not mostrar and any(n.lower() in proc.lower() for n in nomes):
        proc = ""
    ingresso = "; ".join(TIPO_ENTRADA.get(e["tipo"], e["tipo"]) + (f" em {e['data'][:4]}" if e["data"] else "") for e in entradas)
    repro = (f["condicoes_reproducao"] or "").strip()
    if not repro and dr:
        repro = " ".join(x for x in [_frase(dr["licenca"]), _frase(f"Restrições: {dr['restricoes'].strip()}") if (dr["restricoes"] or "").strip() else "",
                                     _frase(f"Crédito obrigatório: {dr['credito_exigido'].strip()}") if (dr["credito_exigido"] or "").strip() else ""] if x)
    acesso = " ".join(x for x in [_frase(f"Acesso: {f['condicoes_acesso'].strip()}") if (f["condicoes_acesso"] or "").strip() else "",
                                  _frase(f"Reprodução: {repro}") if repro else ""] if x)
    periodo = f"{f['data_inicio'] or ''}–{f['data_fim'] or ''}".strip("–") if (f["data_inicio"] or f["data_fim"]) else ""
    valores = {"_camp_acervo_periodo": periodo, "_camp_acervo_extensao": f["dimensao_suporte"], "_camp_acervo_historico": f["historia_arquivistica"],
               "_camp_acervo_procedencia": proc, "_camp_acervo_ingresso": ingresso, "_camp_acervo_doador": "; ".join(nomes) if mostrar else "",
               "_camp_acervo_acesso": acesso}
    meta = {k: ((valores[k] or "").strip() or (EM_ORGANIZACAO if (sempre and com_padrao) else "")) for k, _r, sempre in HUB_CAMPOS}
    faltam = [r for r, v in (("Procedência", proc), ("Forma de entrada", ingresso), ("Condições de acesso", f["condicoes_acesso"]),
                             ("Condições de reprodução", repro)) if not (v or "").strip()]
    return meta, faltam


def descricao_publica_fundo(con, codigo: str) -> str:
    """B1: a prévia do "Sobre o acervo" no site, uma linha "Rótulo: texto" por campo preenchido."""
    meta, _ = campos_hub_fundo(con, codigo)
    return "\n\n".join(f"{rot}: {meta[k]}" for k, rot, _s in HUB_CAMPOS if meta.get(k))


@_nunca_convidado
def atualizar_descricao_fundo_no_site(codigo: str, ator: str) -> dict:
    """B1: grava "Sobre o acervo" na página-hub do arquiteto (rota camp/v1/painel/hub do site, docs/site/painel-hub.php).
    Sem termo do fundo no site ainda, não faz nada. Falhou: fica pendência e o salvamento no painel continua valendo."""
    con = connect()
    out = {"ok": False, "erro": None, "enviado": False}
    try:
        f = con.execute("SELECT tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
        if not f or not f[0]:
            out["ok"] = True
            return out
        meta, _ = campos_hub_fundo(con, codigo)
        r = WP().gravar_hub(f[0], meta)
        out.update(ok=True, enviado=True, pagina=r.get("page_id"))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'site_descricao_atualizada',?,?)",
                    (codigo, ator, json.dumps({"termo": f[0], "pagina": r.get("page_id"), "campos": [k for k, v in meta.items() if v]}, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "fundo", codigo, "pendente_descricao_no_site", out["erro"])
    finally:
        con.commit(); con.close()
    return out


def enviar_agente_ao_hub(aid: int, meta: dict, ator: str) -> dict:
    """B9: grava retrato/biografia do arquiteto na página-hub de cada fundo que ele produziu e que já está no site.
    O retrato sobe uma vez para a biblioteca de mídia; o id do anexo vai como _camp_foto_id."""
    con = connect()
    out = {"ok": False, "erro": None, "fundos": []}
    try:
        termos = con.execute("""SELECT f.codigo, f.tainacan_term_id FROM fundo_agente fa JOIN fundo f ON f.codigo=fa.fundo_codigo
                                WHERE fa.agente_id=? AND fa.papel='produtor' AND f.tainacan_term_id IS NOT NULL
                                AND UPPER(f.codigo) NOT LIKE ?""", (aid, CONVIDADO + "%")).fetchall()
        if not termos:
            out["ok"] = True
            return out
        wp = WP()
        meta = dict(meta)
        if meta.get("_camp_foto_id") == 0:
            meta["_camp_foto_id"] = HUB_LIMPAR            # CAMP-015: foto removida no painel = apagar o campo no site
        if meta.get("_camp_foto_id") == "subir":
            r = con.execute("SELECT r.imagem, r.tipo, a.forma_autorizada FROM agente_retrato r JOIN agente a ON a.id=r.agente_id WHERE r.agente_id=?", (aid,)).fetchone()
            import tempfile, os
            ext = ".png" if r["tipo"] == "image/png" else ".jpg"
            fd, tmp = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, "wb") as fh:
                fh.write(bytes(r["imagem"]))
            try:
                base = unicodedata.normalize("NFKD", r["forma_autorizada"] or "").encode("ascii", "ignore").decode("ascii").lower()
                nome = "retrato-" + (re.sub(r"[^a-z0-9]+", "-", base).strip("-") or str(aid)) + ext
                m = wp.upload_media(tmp, f"Retrato de {r['forma_autorizada']}", nome=nome)
            finally:
                os.unlink(tmp)
            con.execute("UPDATE agente_retrato SET media_id=? WHERE agente_id=?", (m["id"], aid))
            meta["_camp_foto_id"] = m["id"]
        for codigo, termo in termos:
            wp.gravar_hub(termo, meta)
            out["fundos"].append(codigo)
        out["ok"] = True
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('agente',?,'site_hub_arquiteto',?,?)",
                    (str(aid), ator, json.dumps({"campos": sorted(meta), "fundos": out["fundos"]}, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "agente", str(aid), "pendente_hub_no_site", out["erro"])
    finally:
        con.commit(); con.close()
    return out


@_nunca_convidado
def criar_fundo_no_site(codigo: str, ator: str) -> dict:
    """Cria termos 'Fundos' e 'Arquitetos' para o fundo. Idempotente (não recria se já há term_id)."""
    con = connect()
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    out = {"fundo_termo": f["tainacan_term_id"], "arquiteto_termo": None, "erro": None}
    try:
        wp = WP()
        tf, ta = _tax(con, "Fundos"), _tax(con, "Arquitetos")
        if not tf:
            raise RuntimeError("Taxonomia 'Fundos' não encontrada no espelho; rode a sincronização")
        if not f["tainacan_term_id"]:
            ja = con.execute("SELECT id FROM wp_termo WHERE taxonomia_id=? AND nome=?", (tf, f["titulo"])).fetchone()
            t = {"id": ja[0]} if ja else wp.criar_termo(tf, f["titulo"], f"{codigo} · {f['sigla'] or ''}".strip(" ·"))
            con.execute("UPDATE fundo SET tainacan_term_id=? WHERE codigo=?", (t["id"], codigo))
            con.execute("INSERT OR IGNORE INTO fundo_termo_site (nome_site, fundo_codigo, observacao) VALUES (?,?,?)", (f["titulo"], codigo, "criado pelo painel"))
            con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, codigo_detectado, json) VALUES (?,?,?,?,?,?)",
                        (t["id"], tf, f["titulo"], t.get("slug"), codigo, json.dumps(t, ensure_ascii=False)))
            out["fundo_termo"] = t["id"]
        if ta:
            for a in con.execute("SELECT a.id, a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor'", (codigo,)).fetchall():
                ja = con.execute("SELECT id FROM wp_termo WHERE taxonomia_id=? AND nome=?", (ta, a[1])).fetchone()
                aid = con.execute("SELECT tainacan_term_id FROM agente WHERE id=?", (a[0],)).fetchone()[0]
                if not aid:
                    t = {"id": ja[0]} if ja else wp.criar_termo(ta, a[1])
                    con.execute("UPDATE agente SET tainacan_term_id=? WHERE id=?", (t["id"], a[0]))
                    con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, json) VALUES (?,?,?,?,?)", (t["id"], ta, a[1], t.get("slug"), json.dumps(t, ensure_ascii=False)))
                    out["arquiteto_termo"] = t["id"]
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'site_termo_criado',?,?)", (codigo, ator, json.dumps(out)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "fundo", codigo, "pendente_criar_no_site", out["erro"])
    con.commit(); con.close()
    return out


def renomear_fundo_no_site(codigo: str, novo_titulo: str, ator: str) -> dict:
    con = connect()
    f = con.execute("SELECT tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    out = {"ok": False, "erro": None}
    try:
        if f and f[0]:
            wp = WP()
            wp.atualizar_termo(_tax(con, "Fundos"), f[0], name=novo_titulo)
            con.execute("UPDATE wp_termo SET nome=? WHERE id=?", (novo_titulo, f[0]))
            con.execute("UPDATE fundo_termo_site SET nome_site=? WHERE fundo_codigo=?", (novo_titulo, codigo))
            out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]; _pendencia(con, "fundo", codigo, "pendente_renomear_no_site", out["erro"])
    con.commit(); con.close()
    return out


@_nunca_convidado
def criar_dossie_no_site(codigo: str, ator: str) -> dict:
    """Cria o item do projeto na coleção 'Projetos CAMP' como rascunho, com os metadados que o site usa."""
    con = connect()
    con.isolation_level = None   # 21/10: não segura o banco travado durante os pedidos ao site (ver criar_folha_no_site)
    p = con.execute("SELECT p.*, f.titulo AS fundo_titulo, f.tainacan_term_id AS fundo_termo FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?", (codigo,)).fetchone()
    out = {"item_id": p["tainacan_item_id"], "metadados": [], "erro": None}
    if p["tainacan_item_id"]:
        con.close(); return out
    try:
        wp = WP()
        titulo = f"{codigo.split('-')[1]} — {p['titulo']}" + (f", {p['cidade']}" if p["cidade"] else "")
        it = wp.criar_item(COL_PROJETOS, titulo, "draft", p["ambito_conteudo"] or "")
        iid = it["id"]
        con.execute("UPDATE projeto SET tainacan_item_id=? WHERE codigo=?", (iid, codigo))
        con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, codigo_detectado, fundo_detectado, projeto_detectado, metadados, json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, COL_PROJETOS, "draft", titulo, it.get("slug"), it.get("url"), codigo, p["fundo_codigo"], codigo, "{}", json.dumps(it, ensure_ascii=False)))
        arq = con.execute("SELECT a.tainacan_term_id, a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor' ORDER BY fa.inicio LIMIT 1", (p["fundo_codigo"],)).fetchone()
        valores = {"Código de Catalogação": codigo, "Ano": str(p["ano"]) if p["ano"] else None, "Cidade": p["cidade"],
                   "Programa / uso": p["tipologia"], "Cliente (divulgável)": p["cliente"],
                   "Autoria do projeto": p["autoria"], "Papel no projeto": PAPEIS_PROJETO.get(p["papel_no_projeto"] or "", p["papel_no_projeto"]),
                   "Natureza do trabalho": p["natureza"], "Modalidade": p["modalidade"], "Situação da obra": p["situacao_obra"],
                   "Fundo": p["fundo_termo"] or p["fundo_titulo"], "Arquiteto": (arq[0] or arq[1]) if arq else None}
        for nome, valor in valores.items():
            if valor in (None, ""):
                continue
            mid, tipo = _meta(con, COL_PROJETOS, nome)
            if not mid:
                _pendencia(con, "projeto", codigo, f"pendente_metadado_{nome}", f"O site não tem o metadado “{nome}” (nem pelo nome, nem pelo ID conhecido): o valor não foi gravado.")
                continue
            try:
                col = {v_: k_ for k_, v_ in CAMPOS_PROJETO_SITE.items()}.get(nome)
                if col in ("tipologia", "natureza", "modalidade", "situacao_obra"):
                    valor = _valor_para_site(con, col, valor, tipo)   # B3: taxonomia do site recebe id(s)
                wp.definir_metadado(iid, mid, valor)
                out["metadados"].append(nome)
            except Exception as e:  # noqa: BLE001
                _pendencia(con, "projeto", codigo, f"pendente_metadado_{nome}", str(e)[:200])
        out["item_id"] = iid
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_dossie_criado',?,?)", (codigo, ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "projeto", codigo, "pendente_criar_no_site", out["erro"])
    con.commit(); con.close()
    return out


COL_ACERVO = 8013
CAMPOS_PROJETO_SITE = {"ano": "Ano", "cidade": "Cidade", "cliente": "Cliente (divulgável)", "tipologia": "Programa / uso",
                       "autoria": "Autoria do projeto", "papel_no_projeto": "Papel no projeto",
                       "natureza": "Natureza do trabalho", "modalidade": "Modalidade", "situacao_obra": "Situação da obra"}
# B4: papel do titular do fundo no projeto. O painel guarda a chave; o site recebe o rótulo.
PAPEIS_PROJETO = {"autor": "Autor", "coautor": "Coautoria", "consultor": "Consultor", "colaborador": "Colaborador", "terceiros": "Projeto de terceiros"}


def papel_do_site(texto: str | None) -> str | None:
    """Rótulo vindo do site -> chave do painel (sem acento, pelo começo da palavra). Desconhecido fica como veio."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().strip().lower()
    if not t:
        return None
    for pref, chave in (("coaut", "coautor"), ("co-aut", "coautor"), ("consult", "consultor"), ("colabor", "colaborador"), ("terceir", "terceiros"), ("autor", "autor")):
        if t.startswith(pref) or (pref == "terceir" and "terceir" in t):
            return chave
    return t


def _valor_para_site(con, campo: str, v, tipo_meta: str | None):
    """B3: faceta de tipologia num metadado de taxonomia vai como id(s) do termo no site (o Tainacan não aceita termo novo)."""
    from . import tipologia as tp
    chave = tp.COLUNAS.get(campo)
    if chave and "axonomy" in str(tipo_meta or ""):
        ids = tp.ids_do_site(con, chave, v)
        if ids is None:
            raise RuntimeError(f"{tp.FACETAS[chave][1]}: “{v}” não existe na taxonomia do site (sincronize ou escolha da lista)")
        return ids if tp.FACETAS[chave][4] else (ids[0] if ids else "")
    return _valor_site(campo, v)


def _valor_site(campo: str, v):
    if campo == "papel_no_projeto":
        return PAPEIS_PROJETO.get(v or "", v or "")
    return "" if v in (None, 0) else str(v)


def atualizar_dossie_no_site(codigo: str, campos: dict, ator: str) -> dict:
    """Edição de campos do projeto no painel -> metadados do dossiê no Tainacan."""
    con = connect()
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    out = {"enviados": [], "erro": None}
    if not p or not p["tainacan_item_id"]:
        con.close(); return out
    try:
        wp = WP()
        if "titulo" in campos or "cidade" in campos or "ambito_conteudo" in campos:
            titulo = f"{codigo.split('-')[1]} — {p['titulo']}" + (f", {p['cidade']}" if p["cidade"] else "")
            wp.patch_item(COL_PROJETOS, p["tainacan_item_id"], title=titulo, description=p["ambito_conteudo"] or "")
            out["enviados"].append("título/descrição")
        for campo, nome in CAMPOS_PROJETO_SITE.items():
            if campo in campos:
                mid, tipo_meta = _meta(con, COL_PROJETOS, nome)
                if mid:
                    wp.definir_metadado(p["tainacan_item_id"], mid, _valor_para_site(con, campo, p[campo], tipo_meta))
                    out["enviados"].append(nome)
                else:
                    _pendencia(con, "projeto", codigo, f"pendente_metadado_{nome}", f"O site não tem o metadado “{nome}” (nem pelo nome, nem pelo ID conhecido): a mudança não foi gravada.")
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_metadados',?,?)", (codigo, ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]; _pendencia(con, "projeto", codigo, "pendente_metadados_no_site", out["erro"])
    con.commit(); con.close()
    return out


def media_da_folha(con, codigo: str) -> int | None:
    """B12: id do anexo da imagem da folha no site (gravado no envio; para as antigas, o que o espelho do site diz)."""
    r = con.execute("SELECT i.site_media_id, w.json FROM item i LEFT JOIN wp_item w ON w.id=i.tainacan_item_id WHERE i.codigo=?", (codigo,)).fetchone()
    if not r:
        return None
    if r["site_media_id"]:
        return int(r["site_media_id"])
    try:
        j = json.loads(r["json"] or "{}")
    except ValueError:
        return None
    for chave in ("_thumbnail_id", "thumbnail_id"):
        if str(j.get(chave) or "").isdigit() and int(j[chave]):
            return int(j[chave])
    if j.get("document_type") == "attachment" and str(j.get("document") or "").isdigit():
        return int(j["document"])
    return None


def capa_no_site(codigo_projeto: str, ator: str, limpar: bool = False) -> dict:
    """B12: põe a folha escolhida como miniatura do dossiê no site (o plugin usa como capa e como og:image).
    Folha que ainda não está no site: fica guardada e vai quando a folha subir (criar_folha_no_site)."""
    con = connect()
    out = {"enviado": False, "erro": None, "aguardando": False}
    try:
        p = con.execute("SELECT tainacan_item_id, capa_item FROM projeto WHERE codigo=?", (codigo_projeto,)).fetchone()
        if p and limpar and not p["capa_item"] and p["tainacan_item_id"]:   # voltou à capa automática: tira a miniatura que o painel tinha posto
            WP().patch_item(COL_PROJETOS, p["tainacan_item_id"], _thumbnail_id="")
            out["enviado"] = True
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_capa',?,?)",
                        (codigo_projeto, ator, json.dumps({"folha": None, "media": None})))
            return out
        if not p or not p["capa_item"]:
            return out
        media = media_da_folha(con, p["capa_item"])
        if not p["tainacan_item_id"] or not media:
            out["aguardando"] = True
            return out
        WP().patch_item(COL_PROJETOS, p["tainacan_item_id"], _thumbnail_id=media)
        out["enviado"] = True
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_capa',?,?)",
                    (codigo_projeto, ator, json.dumps({"folha": p["capa_item"], "media": media})))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "projeto", codigo_projeto, "pendente_capa_no_site", out["erro"])
    finally:
        con.commit(); con.close()
    return out


def renomear_agente_no_site(agente_id: int, novo_nome: str, ator: str) -> dict:
    con = connect()
    a = con.execute("SELECT tainacan_term_id FROM agente WHERE id=?", (agente_id,)).fetchone()
    out = {"ok": False, "erro": None}
    try:
        if a and a[0]:
            WP().atualizar_termo(_tax(con, "Arquitetos"), a[0], name=novo_nome)
            con.execute("UPDATE wp_termo SET nome=? WHERE id=?", (novo_nome, a[0])); out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]; _pendencia(con, "agente", str(agente_id), "pendente_renomear_no_site", out["erro"])
    con.commit(); con.close()
    return out


@_nunca_convidado
def propagar_status_fundo(codigo: str, acao: str, ator: str) -> dict:
    """Propaga status remoto sem manter transação SQLite aberta durante chamadas de rede.

    Em WAL, uma conexão que leu dados e depois tenta virar escritora pode receber
    SQLITE_BUSY/SQLITE_BUSY_SNAPSHOT se outra escrita ocorreu no intervalo. Por isso:
    1) lemos e fechamos o banco;
    2) atualizamos WordPress/Tainacan sem conexão SQLite aberta;
    3) abrimos uma conexão nova, curta, só para persistir o resultado local.
    """
    alvo = {"no_ar": "publish", "rascunho": "draft", "fora_do_ar": "private"}[acao]
    st_painel = acao
    feitos, falhas, tentados = 0, [], 0

    # Fase 1: snapshot somente leitura. Nada de conexão aberta durante chamadas HTTP.
    con = connect()
    try:
        cfg_proj = con.execute(
            "SELECT valor FROM configuracao WHERE chave='tainacan.projetos_collection_id'"
        ).fetchone()
        cfg_item = con.execute(
            "SELECT valor FROM configuracao WHERE chave='tainacan.itens_collection_id'"
        ).fetchone()

        def cfg_int(row, padrao):
            try:
                return int(row[0]) if row and str(row[0]).strip() else padrao
            except (TypeError, ValueError):
                return padrao

        padrao_proj = cfg_int(cfg_proj, COL_PROJETOS)
        padrao_item = cfg_int(cfg_item, COL_ACERVO)

        from .publicacao import condicoes_projeto, motivos_bloqueio
        projetos = con.execute("SELECT * FROM projeto WHERE fundo_codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL ORDER BY codigo", (codigo,)).fetchall()
        ignorados = []
        alvos = []
        for p in projetos:
            if not p["tainacan_item_id"]:
                if alvo == "publish":
                    ignorados.append({"codigo": p["codigo"], "motivo": "ainda não tem dossiê no site"})
                continue
            if alvo == "publish":   # mesmas regras do botão do projeto: nada de publicar por um atalho o que ele recusaria
                falta = motivos_bloqueio(condicoes_projeto(con, p))
                if falta:
                    ignorados.append({"codigo": p["codigo"], "motivo": "; ".join(falta)})
                    continue

            wid = int(p["tainacan_item_id"])
            r = con.execute("SELECT colecao_id FROM wp_item WHERE id=?", (wid,)).fetchone()
            alvos.append(("projeto", p["codigo"], wid, int(r[0]) if r and r[0] else padrao_proj, alvo))

            itens = con.execute(
                "SELECT codigo, tainacan_item_id, COALESCE(retida,0) AS retida FROM item "
                "WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL AND (lote_id IS NULL OR revisao<>'pendente')",
                (p["codigo"],),
            ).fetchall()
            for i in itens:
                iwid = int(i["tainacan_item_id"])
                ir = con.execute("SELECT colecao_id FROM wp_item WHERE id=?", (iwid,)).fetchone()
                # 21/10: folha retida NUNCA vai ao ar: ao publicar, ela fica (ou volta a ficar) privada
                esc = alvo == "publish" and i["retida"]
                alvos.append(("item", i["codigo"], iwid, int(ir[0]) if ir and ir[0] else padrao_item, "private" if esc else alvo))
    finally:
        con.close()

    # Fase 2: rede. Não segura qualquer lock/transação SQLite.
    try:
        wp = WP()
    except Exception as e:  # noqa: BLE001
        erro = str(e)[:300]
        falhas.append({"codigo": codigo, "erro": erro, "etapa": "conexao_wordpress"})
        alvos = []

    sucessos = []
    if not falhas:
        for tipo, cod, wid, cid, st in alvos:
            tentados += 1
            try:
                wp.atualizar_status_item(cid, wid, st)
                sucessos.append((tipo, cod, wid, st))
                feitos += 1
            except Exception as e:  # noqa: BLE001
                falhas.append({
                    "codigo": cod,
                    "colecao_id": cid,
                    "tainacan_item_id": wid,
                    "erro": str(e)[:220],
                })

    completo = tentados > 0 and not falhas and feitos == tentados

    # Fase 3: escrita local curta numa conexão NOVA. BEGIN IMMEDIATE evita
    # upgrade de transação de leitura e o busy_timeout aguarda outro escritor.
    import sqlite3
    import time

    ultimo_erro_db = None
    for tentativa in range(4):
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for tipo, cod, wid, st in sucessos:
                stp = st_painel if st == alvo else "fora_do_ar"
                con.execute(
                    f"UPDATE {tipo} SET status_site=?, atualizado_em=datetime('now'), "
                    "publicado_em=CASE WHEN ?='no_ar' THEN COALESCE(publicado_em, datetime('now')) ELSE publicado_em END WHERE codigo=?",
                    (stp, stp, cod),
                )
                con.execute("UPDATE wp_item SET status=? WHERE id=?", (st, wid))

            if completo:
                con.execute(
                    "UPDATE fundo SET status_site=?, "
                    "motivo_fora_do_ar=CASE WHEN ?='fora_do_ar' THEN motivo_fora_do_ar ELSE NULL END "
                    "WHERE codigo=?",
                    (acao, acao, codigo),
                )
            else:
                detalhe = (
                    falhas[0]["erro"] if falhas
                    else (f"Nenhum projeto estava pronto para publicar ({len(ignorados)} ficaram de fora). Primeiro motivo: {ignorados[0]['codigo']} — {ignorados[0]['motivo']}"
                          if ignorados else "Nenhum projeto com vínculo ao site foi encontrado para alterar.")
                )
                _pendencia(con, "fundo", codigo, "pendente_status_no_site", detalhe)

            con.execute(
                "INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) "
                "VALUES ('fundo',?,?,?,?)",
                (
                    codigo,
                    f"site_{acao}" if completo else f"site_{acao}_parcial",
                    ator,
                    json.dumps(
                        {
                            "ok": feitos,
                            "tentados": tentados,
                            "falhas": len(falhas),
                            "completo": completo,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            con.commit()
            ultimo_erro_db = None
            break
        except sqlite3.OperationalError as e:
            con.rollback()
            ultimo_erro_db = str(e)
            if "locked" not in ultimo_erro_db.lower() or tentativa == 3:
                break
            time.sleep(0.5 * (tentativa + 1))
        finally:
            con.close()

    if ultimo_erro_db:
        falhas.append({
            "codigo": codigo,
            "erro": f"Falha ao registrar resultado local após publicação: {ultimo_erro_db}"[:300],
            "etapa": "sqlite",
        })
        completo = False

    verbo = {"publish": "publicados", "draft": "voltaram para rascunho", "private": "despublicados"}[alvo]
    if falhas:
        erro = falhas[0]["erro"]
    elif completo:
        erro = None
    elif ignorados:
        erro = (f"Nenhum projeto estava pronto para publicar: {len(ignorados)} ficaram de fora. "
                f"Primeiro motivo: {ignorados[0]['codigo']} — {ignorados[0]['motivo']}")
    else:
        erro = "Nenhum projeto deste fundo tem registro no site para alterar."
    mensagem = (f"{feitos} registro(s) {verbo}." if feitos else "Nada foi alterado.") + \
               (f" {len(ignorados)} projeto(s) ficaram de fora por não estarem prontos." if ignorados and feitos else "")
    return {
        "ok": completo,
        "alterados": feitos,
        "tentados": tentados,
        "falhas": falhas,
        "erro": erro,
        "mensagem": mensagem,
        "ignorados_total": len(ignorados),
        "ignorados": ignorados[:50],
    }

def _tipos_para_site(con, codigo: str, mid, valor):
    """19/10: folha com mais de um tipo ("Planta; Corte"). Se o metadado do site aceita vários valores, vão todos (lista);
    se aceita um só, vai o primeiro e fica uma pendência dizendo o que não foi."""
    from .tipos_documento import separar
    tipos = separar(valor)
    if len(tipos) <= 1:
        return tipos[0] if tipos else valor
    r = con.execute("SELECT json FROM wp_metadado WHERE id=?", (mid,)).fetchone()
    try:
        multiplo = str((json.loads(r[0]) if r and r[0] else {}).get("multiple") or "").lower() == "yes"
    except Exception:  # noqa: BLE001
        multiplo = False
    if multiplo:
        return tipos
    _pendencia(con, "item", codigo, "pendente_metadado_Tipo de desenho",
               f"O metadado “Tipo de desenho” do site aceita um só valor: foi enviado “{tipos[0]}”; ficaram de fora: {', '.join(tipos[1:])}.")
    return tipos[0]


def _termo_por_nome(con, taxonomia_nome: str, nome: str):
    tid = _tax(con, taxonomia_nome)
    if not tid or not nome:
        return None
    r = con.execute("SELECT id FROM wp_termo WHERE taxonomia_id=? AND lower(nome)=lower(?)", (tid, nome)).fetchone()
    return r[0] if r else None


def imagem_pronta_para_o_site(con, i, giro: int | None = None, ajuste: tuple | None = None) -> tuple[str | None, int | None]:
    """(caminho, lado maior em px) da imagem da folha como ela vai ao site (CAMP-048): derivado JPEG q85 sRGB com lado maior <= 1920 px
    (menos, se os direitos do fundo pedem), feito da prévia do CAMP Vision (já girada) com o giro/espelho que a pessoa escolheu na revisão.
    Fica em cache em disco. O TIF e a prévia de ~3000 px NUNCA vão ao site. `giro` (graus, horário) substitui o giro_manual gravado.
    Sem imagem: (None, None). Sem Pillow: levanta RuntimeError (melhor não subir nada do que subir a imagem grande).
    `i` precisa ter pendencias, arquivo_jpg, fundo_codigo, giro_manual, espelhado e espelho_manual.
    19/10: com recorte/alinhamento (item.recorte/alinhamento, ou `ajuste` = (recorte, ângulo) que substitui o gravado), sobe o JPG
    corrigido que o painel gera (ajuste_imagem.garantir), reduzido como sempre."""
    from .imagem_site import imagem_para_o_site, lado_publico
    caminho_img = imagem_para_o_site(con, i)
    if not caminho_img:
        return None, None
    from .giro_imagem import derivado_publico, disponivel, espelho_efetivo, lado_real
    if not disponivel():
        raise RuntimeError("O painel não tem a biblioteca de imagens (Pillow): sem ela não dá para gerar a versão de até 1920 px. Instale e tente de novo")
    lado = lado_publico(con, i["fundo_codigo"])
    g = (i["giro_manual"] or 0) if giro is None else giro % 360
    esp = espelho_efetivo(i)
    from . import ajuste_imagem
    rec, ang = ajuste if ajuste is not None else ajuste_imagem.ler(i)
    try:
        if ajuste_imagem.tem_ajuste(rec, ang):          # o JPG corrigido já vem espelhado/girado/endireitado/recortado
            caminho_img, g, esp = ajuste_imagem.garantir(i["codigo"], caminho_img, g, esp, ang, rec)[0], 0, False
        derivado = derivado_publico(caminho_img, g, lado, esp)
    except OSError as e:
        raise RuntimeError(f"Não consegui preparar a imagem pública: {e}") from e
    return str(derivado), (lado_real(derivado) or lado)


def girar_imagem_no_site(codigo: str, giro: int, ajuste: tuple | None = None) -> dict:
    """Girar folha já publicada: troca o ARQUIVO do anexo da imagem no WordPress pela imagem girada `giro` graus (sentido horário,
    o mesmo giro_manual que a folha vai ter), MANTENDO o ID do anexo (o item do Tainacan, a capa do projeto e os links continuam valendo).
    Não grava nada no painel: quem chama grava o giro só se isto não levantar erro. Levanta RuntimeError com frase em português.
    `ajuste` = (recorte, ângulo) que a folha vai ter (19/10: recorte e alinhamento); None = o gravado."""
    con = connect()
    try:
        i = con.execute("""SELECT i.*, p.fundo_codigo, p.titulo AS projeto_titulo, s.nome AS serie_nome FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
                           LEFT JOIN serie s ON s.codigo=i.serie_codigo WHERE i.codigo=?""", (codigo,)).fetchone()
        if not i:
            raise RuntimeError("Folha não existe")
        media = media_da_folha(con, codigo)
        if not media:
            raise RuntimeError("Não achei a imagem desta folha no site (o anexo não está registrado no painel). Sincronize com o site e tente de novo")
        caminho, lado_pub = imagem_pronta_para_o_site(con, i, giro, ajuste)
        if not caminho:
            raise RuntimeError("A imagem desta folha não está no QNAP: sem ela não dá para mandar a versão girada ao site")
    finally:
        con.close()
    nome = nome_arquivo_site(i["titulo"] or i["tipo_documento"] or i["serie_nome"], i["projeto_titulo"], codigo)
    m = WP().substituir_midia(media, caminho, nome=nome)
    if int(m.get("id") or media) != int(media):
        raise RuntimeError(f"O site devolveu outro anexo ({m.get('id')}) em vez de trocar o arquivo do anexo {media}")
    try:
        c2 = connect(); c2.execute("UPDATE item SET site_imagem_lado=? WHERE codigo=?", (lado_pub, codigo)); c2.commit(); c2.close()
    except Exception:  # noqa: BLE001  (só informativo)
        pass
    return {"media_id": media, "url": m.get("source_url"), "lado_px": lado_pub}


STATUS_DO_SITE = {"publish": "no_ar", "draft": "rascunho", "pending": "rascunho", "private": "fora_do_ar"}
META_CODIGO_DOCUMENTO = 8030      # "Código do documento" na coleção Acervo CAMP (o espelho wp_metadado manda, se tiver)


def item_existente_no_site(con, wp, codigo: str, fundo: str | None = None, projeto: str | None = None) -> dict | None:
    """Antes de criar a folha no Tainacan: já existe um item com este código? (um rascunho de envio anterior cuja ligação se perdeu).
    1) o espelho do site (wp_item.codigo_detectado); 2) o próprio site, pelo metadado "Código do documento" (8030).
    Item já ligado a OUTRA folha do painel não serve. Devolve {"id", "status", "como"} ou None. Falha na busca do site não impede criar."""
    ligados = "SELECT tainacan_item_id FROM item WHERE tainacan_item_id IS NOT NULL AND codigo<>?"
    r = con.execute(f"""SELECT id, status FROM wp_item WHERE colecao_id=? AND upper(codigo_detectado)=upper(?) AND id NOT IN ({ligados})
                        ORDER BY (status='publish') DESC, id LIMIT 1""", (COL_ACERVO, codigo, codigo)).fetchone()
    if r:
        return {"id": int(r["id"]), "status": r["status"], "como": "espelho do site"}
    buscar = getattr(wp, "buscar_por_codigo", None)
    if not buscar:
        return None
    mid = _meta(con, COL_ACERVO, "Código do documento")[0] or META_CODIGO_DOCUMENTO
    try:
        achados = buscar(COL_ACERVO, mid, codigo) or []
    except Exception as e:  # noqa: BLE001
        from .log_tecnico import registrar
        try:
            registrar(30, "busca_codigo_no_site_falhou", "Não consegui procurar o código no site antes de criar a folha", codigo=codigo, erro=str(e)[:200])
        except Exception:  # noqa: BLE001
            pass
        return None
    ja = {x[0] for x in con.execute(ligados, (codigo,))}
    from .wp import detectar_codigo, metadados_texto
    for it in sorted(achados, key=lambda x: (x.get("status") != "publish", int(x.get("id") or 0))):
        if not it.get("id") or int(it["id"]) in ja:
            continue
        md = metadados_texto(it)
        if detectar_codigo(it.get("title", ""), it.get("slug", ""), *md.values())[0] != codigo.upper():
            continue                                              # o site devolveu algo parecido, mas não é este código
        con.execute("INSERT OR IGNORE INTO wp_item (id, colecao_id, status, titulo, slug, url, codigo_detectado, fundo_detectado, projeto_detectado, metadados, json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (int(it["id"]), COL_ACERVO, it.get("status"), it.get("title"), it.get("slug"), it.get("url"), codigo, fundo, projeto,
                     json.dumps(md, ensure_ascii=False), json.dumps(it, ensure_ascii=False)))
        return {"id": int(it["id"]), "status": it.get("status"), "como": "busca no site pelo código"}
    return None


@_nunca_convidado
def atualizar_serie_no_site(codigo: str, ator: str) -> dict:
    """CAMP-139 (21/10): a folha mudou de série (tipo de material) e continua com o MESMO item no site (o endereço vem do título, não do
    código): grava no item os metadados que mudam — "Código do documento", "Série" e "Tipo de desenho". Falha vira pendência; nunca levanta."""
    con = connect()
    con.isolation_level = None
    out = {"codigo": codigo, "metadados": [], "erro": None}
    try:
        i = con.execute("""SELECT i.*, s.nome AS serie_nome FROM item i LEFT JOIN serie s ON s.codigo=i.serie_codigo WHERE i.codigo=?""", (codigo,)).fetchone()
        if not i or not i["tainacan_item_id"]:
            out["erro"] = "a folha não tem item no site"; return out
        iid = int(i["tainacan_item_id"])
        wp = WP()
        valores = {"Código do documento": codigo, "Série": _termo_por_nome(con, "Séries", i["serie_nome"]) or i["serie_nome"],
                   "Tipo de desenho": i["tipos_documento"] or i["tipo_documento"]}
        for nome, valor in valores.items():
            if valor in (None, ""):
                continue
            mid, _ = _meta(con, COL_ACERVO, nome)
            if not mid:
                _pendencia(con, "item", codigo, f"pendente_metadado_{nome}", f"O site não tem o metadado “{nome}”: o valor novo não foi gravado.")
                continue
            if nome == "Tipo de desenho":
                valor = _tipos_para_site(con, codigo, mid, valor)
            wp.definir_metadado(iid, mid, valor); out["metadados"].append(nome)
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_serie_atualizada',?,?)",
                    (codigo, ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "item", codigo, "pendente_serie_no_site", "O tipo de material mudou no painel, mas o site não aceitou o código/série novos: " + out["erro"])
    finally:
        con.close()
    return out


def criar_folha_no_site(codigo: str, ator: str, enviar_imagem: bool = True) -> dict:
    """Item na coleção 'Acervo CAMP' (rascunho) a partir de uma folha do painel. Sobe o JPG como documento quando houver arquivo local."""
    con = connect()
    # 21/10: cada gravação local vale na hora (autocommit). Antes, o UPDATE do começo abria uma transação que só fechava no fim, depois de
    # ~15 pedidos ao site (~50 s): o banco ficava travado para escrita e o resto do painel dava "database is locked" (busy_timeout = 30 s).
    # Gravar o vínculo com o site logo de cara também é o certo: se a rede cair no meio, o próximo envio liga no item que já existe.
    con.isolation_level = None
    i = con.execute("""SELECT i.*, p.tainacan_item_id AS dossie_id, p.titulo AS projeto_titulo, p.fundo_codigo, p.ano AS projeto_ano,
                              f.titulo AS fundo_titulo, f.tainacan_term_id AS fundo_termo, s.nome AS serie_nome
                       FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo JOIN serie s ON s.codigo=i.serie_codigo
                       WHERE i.codigo=?""", (codigo,)).fetchone()
    out = {"item_id": i["tainacan_item_id"] if i else None, "metadados": [], "imagem": None, "erro": None}
    if not i:
        con.close(); out["erro"] = "folha não existe"; return out
    if i["tainacan_item_id"]:
        con.close(); return out
    if i["duplicata_de"]:
        con.close(); out["erro"] = "folha duplicada não sobe ao site"; return out
    if i["lote_id"] and i["revisao"] == "pendente":
        con.close(); out["erro"] = "a folha ainda não foi conferida na revisão do lote: confira antes de enviar ao site"; return out
    if not i["dossie_id"]:
        con.close(); out["erro"] = "o projeto ainda não tem dossiê no site (crie o projeto no site primeiro)"; return out
    try:
        wp = WP()
        p_num = codigo.split("-")[1]
        titulo = f"{(i['titulo'] or i['tipo_documento'] or i['serie_nome'])} — {p_num} — {i['projeto_titulo']}"
        existente = item_existente_no_site(con, wp, codigo, i["fundo_codigo"], i["projeto_codigo"])
        if existente:                                             # já há um item com este código no site (rascunho de um envio anterior): liga, não cria outro
            iid = existente["id"]
            st = STATUS_DO_SITE.get(existente.get("status"), "rascunho")
            con.execute("UPDATE item SET tainacan_item_id=?, status_site=? WHERE codigo=?", (iid, st, codigo))
            out["reaproveitado"] = {"item_id": iid, "como": existente["como"], "status": existente.get("status")}
            if media_da_folha(con, codigo):                       # já tem imagem lá: não sobe outra
                out["item_id"] = iid; out["imagem"] = "já estava no site"
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_item_reaproveitado',?,?)", (codigo, ator, json.dumps(out, ensure_ascii=False)))
                con.commit(); con.close()
                return out
        else:
            it = wp.criar_item(COL_ACERVO, titulo, "draft", descricao_folha(i))
            iid = it["id"]
            con.execute("UPDATE item SET tainacan_item_id=?, status_site='rascunho' WHERE codigo=?", (iid, codigo))
            con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, codigo_detectado, fundo_detectado, projeto_detectado, metadados, json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (iid, COL_ACERVO, "draft", titulo, it.get("slug"), it.get("url"), codigo, i["fundo_codigo"], i["projeto_codigo"], "{}", json.dumps(it, ensure_ascii=False)))
            arq = con.execute("SELECT a.tainacan_term_id, a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor' ORDER BY fa.inicio LIMIT 1", (i["fundo_codigo"],)).fetchone()
            valores = {"Código do documento": codigo, "Projeto": str(i["dossie_id"]), "Série": _termo_por_nome(con, "Séries", i["serie_nome"]) or i["serie_nome"],
                       "Tipo de arquivo": _termo_por_nome(con, "Tipos de arquivo", "Preview (JPG)") or "Preview (JPG)",
                       "Ano": str(i["ano_folha"] or i["projeto_ano"] or ""), "Escala": i["escala"], "Folha": i["folha"], "Tipo de desenho": i["tipos_documento"] or i["tipo_documento"],
                       "Título": titulo, "Fundo": i["fundo_termo"] or i["fundo_titulo"], "Arquiteto": (arq[0] or arq[1]) if arq else None,
                       "Crédito": CREDITO_AUTORIA_NAO_CONFIRMADA if i["autoria_divergente"] else None,   # CAMP-046: nunca o nome lido como fato
                       "Suporte": i["suporte"], "Arquivo de origem": i["arquivo_origem"] if "arquivo_origem" in i.keys() else None}
            for nome, valor in valores.items():
                if valor in (None, ""):
                    continue
                mid, _ = _meta(con, COL_ACERVO, nome)
                if nome == "Tipo de desenho" and mid:
                    valor = _tipos_para_site(con, codigo, mid, valor)
                if not mid and nome == "Arquivo de origem":
                    mid = _garantir_metadado_origem(con, wp)
                if not mid:
                    if nome != "Arquivo de origem":     # (a falha do "Arquivo de origem" já deixou a própria pendência)
                        _pendencia(con, "item", codigo, f"pendente_metadado_{nome}", f"O site não tem o metadado “{nome}” (nem pelo nome, nem pelo ID conhecido): o valor não foi gravado.")
                    continue
                try:
                    wp.definir_metadado(iid, mid, valor); out["metadados"].append(nome)
                except Exception as e:  # noqa: BLE001
                    _pendencia(con, "item", codigo, f"pendente_metadado_{nome}", str(e)[:200])
            # 19/10: escritórios parceiros. O painel NÃO cria metadado no site: só envia se a coleção já tiver um de texto com nome
            # conhecido (parceiros.NOMES_NO_SITE). Sem ele, os parceiros ficam só no painel (e na exportação EAD), sem pendência.
            from . import parceiros as _parc
            lista_p = _parc.ler(i["parceiros"] if "parceiros" in i.keys() else None)
            if lista_p:
                mid_p, nome_p = _parc.metadado_no_site(con, COL_ACERVO)
                if mid_p:
                    try:
                        wp.definir_metadado(iid, mid_p, _parc.texto(lista_p)); out["metadados"].append(nome_p)
                    except Exception as e:  # noqa: BLE001
                        _pendencia(con, "item", codigo, f"pendente_metadado_{nome_p}", str(e)[:200])
        caminho_img, lado = imagem_pronta_para_o_site(con, i) if enviar_imagem else (None, None)
        if caminho_img:
            out["lado_max_px"] = lado
        if caminho_img:
            try:
                m = wp.upload_media(caminho_img, titulo, nome=nome_arquivo_site(i["titulo"] or i["tipo_documento"] or i["serie_nome"], i["projeto_titulo"], codigo))
                wp.definir_documento(COL_ACERVO, iid, m["id"])
                con.execute("UPDATE wp_item SET documento_url=?, thumb_url=? WHERE id=?", (m.get("source_url"), m.get("source_url"), iid))
                out["imagem"] = m.get("source_url")
                con.execute("UPDATE item SET site_media_id=?, site_imagem_lado=? WHERE codigo=?", (m["id"], lado, codigo))
                if i["dossie_id"] and con.execute("SELECT 1 FROM projeto WHERE codigo=? AND capa_item=?", (i["projeto_codigo"], codigo)).fetchone():
                    wp.patch_item(COL_PROJETOS, i["dossie_id"], _thumbnail_id=m["id"])   # B12: a capa escolhida chegou ao site
                    out["capa"] = True
            except Exception as e:  # noqa: BLE001
                _pendencia(con, "item", codigo, "pendente_imagem_no_site", str(e)[:200]); out["imagem"] = f"falhou: {e}"[:120]
        out["item_id"] = iid
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                    (codigo, "site_item_reaproveitado" if existente else "site_item_criado", ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]; _pendencia(con, "item", codigo, "pendente_criar_no_site", out["erro"])
    con.commit(); con.close()
    return out


def atualizar_folha_no_site(codigo: str, wid: int, colecao_id: int, titulo: str | None, descricao: str | None,
                            metadados: dict, ator: str) -> dict:
    """Envia ao Tainacan os textos públicos editados de uma folha.

    metadados: {nome: (metadado_id, valor_para_api, valor_texto_para_espelho)}.
    Nunca levanta exceção: cada campo falha isoladamente, vira pendência e é devolvido em `falhas`,
    para o salvamento local (já feito) nunca ser desfeito por uma falha do site.
    """
    out = {"enviados": [], "falhas": []}
    con = connect()

    def falha(campo, erro):
        out["falhas"].append({"campo": campo, "erro": str(erro)[:240]})
        _pendencia(con, "item", codigo, f"pendente_{campo}_no_site", str(erro))

    try:
        try:
            wp = WP()
        except Exception as e:  # noqa: BLE001  (ex.: Application Password não configurada)
            for campo in ([("título", 1)] if titulo is not None else []) + ([("descrição", 1)] if descricao is not None else []) \
                    + [(n, 1) for n in metadados]:
                falha(campo[0], e)
            return out
        if titulo is not None or descricao is not None:
            corpo = {}
            if titulo is not None:
                corpo["title"] = titulo
            if descricao is not None:
                corpo["description"] = descricao
            try:
                wp.patch_item(colecao_id, wid, **corpo)
                if titulo is not None:
                    out["enviados"].append("título da página"); con.execute("UPDATE wp_item SET titulo=? WHERE id=?", (titulo, wid))
                if descricao is not None:
                    out["enviados"].append("descrição")
                    row = con.execute("SELECT json, metadados FROM wp_item WHERE id=?", (wid,)).fetchone()
                    try:
                        j = json.loads(row["json"] or "{}") if row else {}
                    except ValueError:
                        j = {}
                    j["description"] = descricao
                    con.execute("UPDATE wp_item SET json=? WHERE id=?", (json.dumps(j, ensure_ascii=False), wid))
            except Exception as e:  # noqa: BLE001
                if titulo is not None:
                    falha("título", e)
                if descricao is not None:
                    falha("descrição", e)
        for nome, (mid, valor_api, valor_txt) in metadados.items():
            try:
                wp.definir_metadado(wid, mid, valor_api)
                out["enviados"].append(nome)
                row = con.execute("SELECT metadados FROM wp_item WHERE id=?", (wid,)).fetchone()
                try:
                    md = json.loads((row["metadados"] if row else None) or "{}")
                except ValueError:
                    md = {}
                md[nome] = valor_txt
                con.execute("UPDATE wp_item SET metadados=? WHERE id=?", (json.dumps(md, ensure_ascii=False), wid))
            except Exception as e:  # noqa: BLE001
                falha(nome, e)
    finally:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_texto_editado',?,?)",
                    (codigo, ator, json.dumps(out, ensure_ascii=False)))
        con.commit(); con.close()
    return out
