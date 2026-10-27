"""Publicar com um clique: o painel conhece a receita e faz sozinho o que dá, parando só no que é decisão de gente.

A receita (antes, cada passo era um botão solto): dossiê do projeto no site -> folhas no site (rascunho) -> autorizar -> publicar.
- plano(): mostra o que vai ser feito, o que fica de fora e o que SÓ uma pessoa resolve (direitos do fundo, autoria divergente/erros bloqueantes,
  lote de teste, nenhuma folha conferida). Não muda nada.
- executar(): faz a sequência. Idempotente (repetir continua de onde parou) e dividido em fatias de tempo: um projeto com muitas folhas devolve
  `parcial` e a tela chama de novo, com progresso. Todos os portões de `publicar` continuam valendo (ele revalida no fim).
"""
from __future__ import annotations

import json
import threading
import time

from fastapi import HTTPException

from .db import connect
from .publicacao import ELEGIVEL_LOCAL, condicoes_projeto

from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402


def envio_paralelo() -> int:
    """Quantas folhas vão ao site ao mesmo tempo (configuração site.envio_paralelo, 1 a 6; sem a chave: 3)."""
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='site.envio_paralelo'").fetchone()
    finally:
        con.close()
    try:
        return max(1, min(6, int(str(r[0]).strip()))) if r and str(r[0]).strip() else 3
    except ValueError:
        return 3

def publicar_arquiteto_junto() -> bool:
    """21/10: configuração site.publicar_arquiteto_junto (sem a chave: sim)."""
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='site.publicar_arquiteto_junto'").fetchone()
    finally:
        con.close()
    return not r or str(r[0]).strip() != "0"


def publicar_um_passo() -> bool:
    """CAMP-148: configuração publicacao.publicar_um_passo (sem a chave ou 0: desligado, como antes)."""
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='publicacao.publicar_um_passo'").fetchone()
    finally:
        con.close()
    return bool(r) and str(r[0]).strip() == "1"


def pode_publicar(u: dict) -> bool:
    """Quem pode apertar Publicar: admin; com publicar_um_passo ligado, o operador também (CAMP-148, decisão do Rafa)."""
    return u["papel"] in ("admin", "master") or (u["papel"] == "operador" and publicar_um_passo())


def lotes_para_aprovar(con, codigo: str) -> tuple[list[int], int]:
    """([lotes conferidos e ainda não aprovados], quantos lotes não aprovados existem). Só lote com folhas e nenhuma a conferir."""
    nao_aprovados = con.execute("""SELECT l.id, (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo) AS tot,
                                          (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo AND i.revisao='pendente' AND i.duplicata_de IS NULL) AS pen
                                     FROM lista_processamento l
                                    WHERE l.projeto_codigo=? AND l.aprovado_em IS NULL AND l.descartado_em IS NULL AND l.etapa IN ('revisao','rascunho')""", (codigo,)).fetchall()
    com_folhas = [r for r in nao_aprovados if r["tot"]]
    return [r["id"] for r in com_folhas if not r["pen"]], len(com_folhas)


def aprovar_junto(con, codigo: str, u: dict) -> list[int]:
    """CAMP-148: aprova os lotes conferidos do projeto como parte do Publicar (fica no histórico como 'revisao_aprovada' junto_com_publicar)."""
    ids, _ = lotes_para_aprovar(con, codigo)
    for lid in ids:
        c = con.execute("""SELECT COUNT(*) AS total, SUM(CASE WHEN revisao='bloqueado' THEN 1 ELSE 0 END) AS bloq FROM item WHERE lote_id=?""", (lid,)).fetchone()
        con.execute("UPDATE lista_processamento SET aprovado_por=?, aprovado_em=datetime('now'), atualizado_em=datetime('now') WHERE id=? AND aprovado_em IS NULL", (u["email"], lid))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'revisao_aprovada',?,?)",
                    (codigo, u["email"], json.dumps({"lote_id": lid, "folhas": c["total"], "bloqueadas": c["bloq"] or 0, "junto_com_publicar": True})))
    if ids:
        con.commit()
    return ids


ORCAMENTO_S = 40.0             # tempo máximo de envio de folhas por chamada (a tela repete até acabar)
ANO_FOLHA_DIFERENTE = 5        # anos de diferença entre a folha e o projeto a partir dos quais o plano avisa
_trava = threading.Lock()
_em_andamento: set[str] = set()
JANELA_REPETIDO_S = 60         # UX-17: Publicar de novo logo depois de publicar, sem nada novo, não publica 2×


def publicacao_recente(con, codigo: str, janela_s: int = JANELA_REPETIDO_S) -> dict | None:
    """A publicação guiada que deu certo neste projeto nos últimos `janela_s` segundos ({quando, detalhe}), ou None.
    Vem do evento 'publicacao_guiada' (banco): vale para o caminho com tarefa e o direto, e para dois processos."""
    r = con.execute("""SELECT quando, detalhe FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='publicacao_guiada'
                         AND quando >= datetime('now', ?) ORDER BY id DESC LIMIT 1""", (codigo, f"-{int(janela_s)} seconds")).fetchone()
    if not r:
        return None
    try:
        det = json.loads(r["detalhe"] or "{}") or {}
    except ValueError:
        det = {}
    return {"quando": r["quando"], "detalhe": det} if det.get("ok") else None


def repetido_sem_novidade(con, p, pend: list) -> dict | None:
    """UX-17: o segundo clique (ou a segunda aba) que chega quando a publicação já terminou: projeto público, nenhuma folha nova
    para enviar e uma publicação guiada que deu certo há menos de 1 min. Devolve a resposta "nada foi feito de novo" (sem chamar o site)."""
    if p["status_site"] != "no_ar" or pend:
        return None
    rec = publicacao_recente(con, p["codigo"])
    if not rec:
        return None
    return {"ok": True, "parcial": False, "etapa": "publicar", "repetido": True, "feitos": [], "folhas_criadas": 0, "publicados": 0,
            "publicado_em": rec["quando"], **resultado_publicacao(con, p["codigo"]),
            "mensagem": "Este projeto acabou de ser publicado: nada foi feito de novo (clique repetido)."}


def plano(con, p) -> dict:
    """O que o botão Publicar vai fazer. Só lê."""
    codigo = p["codigo"]
    cond = condicoes_projeto(con, p)
    por_id = {c["id"]: c for c in cond["condicoes"]}
    q = lambda sql: con.execute(sql, (codigo,)).fetchone()[0]
    elegiveis = q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {ELEGIVEL_LOCAL}")
    a_enviar = q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL}")
    nao_conferidas = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL AND revisao='pendente' AND duplicata_de IS NULL")
    duplicadas = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND duplicata_de IS NOT NULL")
    total_locais = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=?")
    divergentes = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND autoria_divergente=1")
    retidas = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1")

    bloqueios = [{"id": i, "texto": por_id[i]["texto"], "detalhe": por_id[i]["detalhe"], "acao": por_id[i]["acao"]}
                 for i in ("direitos", "bloqueios", "titulo", "aceite_cv", "teste", "revisao")
                 if i in por_id and por_id[i]["bloqueia"] and not por_id[i]["ok"]]   # 21/10: só o que BLOQUEIA (o aceite do CAMP Vision virou aviso)
    um_passo = publicar_um_passo()
    a_aprovar: list[int] = []
    # O admin sempre pode concluir a revisão das folhas JÁ conferidas no mesmo
    # clique de Publicar. A flag permanece para liberar operador, não para
    # obrigar o admin a procurar e aprovar cada lote manualmente.
    a_aprovar, nao_aprovados = lotes_para_aprovar(con, codigo)
    if a_aprovar and len(a_aprovar) == nao_aprovados and por_id.get("revisao", {}).get("detalhe") == "O lote ainda não foi aprovado na Revisão do lote":
        bloqueios = [b for b in bloqueios if b["id"] != "revisao"]
    else:
        a_aprovar = []
        falta = q("SELECT COUNT(*) FROM item i JOIN lista_processamento l ON l.id=i.lote_id WHERE i.projeto_codigo=? AND l.aprovado_em IS NULL AND i.revisao='pendente' AND i.duplicata_de IS NULL")
        for b_ in bloqueios:
            if b_["id"] == "revisao" and falta:      # o que falta de verdade é conferir (aprovar vem junto com o Publicar)
                b_.update(texto="Folhas a conferir", detalhe=f"Falta conferir {falta} folha{'' if falta == 1 else 's'} do lote (a aprovação vem junto com o Publicar)",
                          acao={"tipo": "revisao", "rotulo": "Conferir as folhas", "alvo": codigo})
    dossie = bool(p["tainacan_item_id"])
    passos = ([{"id": "aprovar", "texto": "Aprovar o lote conferido" if len(a_aprovar) == 1 else f"Aprovar os {len(a_aprovar)} lotes conferidos", "estado": "sera_feito"}] if a_aprovar else []) + [
        {"id": "dossie", "texto": "Criar a página do projeto no site (ainda escondida)" if not dossie else "Página do projeto no site", "estado": "feito" if dossie else "sera_feito"},
        {"id": "folhas", "texto": (f"Enviar {a_enviar} folha(s) ao site (ainda escondidas)" if a_enviar else "Folhas no site") if elegiveis else f"0 de {total_locais} folhas prontas ({nao_conferidas} a conferir)",
         "estado": "sera_feito" if a_enviar else ("feito" if elegiveis else "aguarda")},
        {"id": "autorizar", "texto": "Marcar o projeto como liberado" if not p["autorizado_site"] else "Projeto liberado para publicação", "estado": "feito" if p["autorizado_site"] else "sera_feito"},
        {"id": "publicar", "texto": f"Tornar a página e as {elegiveis} folha(s) visíveis para todos", "estado": "sera_feito"},
    ]
    # AVISOS (não bloqueiam): coisas que a pessoa provavelmente quer ver antes de tornar público
    import re as _re
    avisos = []
    tit = (p["titulo"] or "").strip()
    from .similaridade import titulo_tecnico
    if _re.match(r"^[A-Za-z]{1,3}\d{1,5}[_ -]+\S", tit) and not titulo_tecnico(tit):   # UX-15: o técnico já é bloqueio (id "titulo")
        limpo = _re.sub(r"^[A-Za-z]{1,3}\d{1,5}[_ -]+", "", tit).replace("_", " ").strip()
        avisos.append({"id": "titulo", "campo": "titulo", "texto": f"O título “{tit}” parece ter um prefixo de pasta. Como ficaria: “{limpo}”."})
    cidade = p["cidade"] if "cidade" in p.keys() else None
    sem = [n for n, v in (("ano", p["ano"]), ("cidade", cidade)) if not v or str(v) == "0"]
    if sem:
        avisos.append({"id": "vazios", "campo": sem[0], "texto": "Sem " + " e sem ".join(sem) + ": a página fica sem essa informação. Preencha agora ou publique assim mesmo."})
    # T4 (acervo novo): folha sem título é publicada com o título genérico da série, repetido. Só avisa: decisão do Rafa se vira bloqueio.
    sem_titulo = q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL} AND TRIM(COALESCE(titulo,''))=''")
    if sem_titulo:
        avisos.append({"id": "folhas_sem_titulo", "campo": None, "texto": (f"{sem_titulo} folhas sem título" if sem_titulo != 1 else "1 folha sem título")
                       + ": no site aparecem com o nome da série. Preencha na conferência ou publique assim mesmo."})
    # T5: o ano lido na folha foge muito do ano do projeto (ex.: 1917 num projeto de 1971)
    try:
        ano_p = int(str(p["ano"] or "").strip()[:4])
    except ValueError:
        ano_p = None
    if ano_p:
        fora = [r[0] for r in con.execute(f"SELECT codigo FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL} AND ano_folha IS NOT NULL AND ABS(ano_folha-?)>=?",
                                          (codigo, ano_p, ANO_FOLHA_DIFERENTE))]
        if fora:
            avisos.append({"id": "ano_fora_do_projeto", "campo": None, "texto": f"{len(fora)} folha(s) com ano muito diferente do projeto ({ano_p}), por exemplo {fora[0][-6:]}: confira o ano antes de publicar."})
    if "pagina_arquiteto" in por_id:     # CAMP-015; 21/10: sem a página do arquiteto pública, o site esconde o projeto
        junto = publicar_arquiteto_junto() and not por_id["pagina_arquiteto"].get("sem_arquiteto")
        avisos.append({"id": "pagina_arquiteto", "campo": None, "publica_junto": junto,
                       "texto": "A página do arquiteto ainda não está pública no site: " + ("ela será publicada junto, porque sem ela o projeto não aparece."
                                if junto else "o projeto fica publicado, mas só aparece no site quando a página do arquiteto for publicada (quadro “Página do arquiteto no site”, no fundo).")})
    if divergentes:     # CAMP-046 (contrato 2.4): aviso, não bloqueio
        avisos.append({"id": "autoria_nao_confirmada", "campo": None, "texto": (f"{divergentes} folha(s) com autoria não confirmada" if divergentes != 1 else "1 folha com autoria não confirmada")
                       + ": sobem ao site com o crédito “Autoria não confirmada”."})
    return {"passos": passos, "bloqueios": bloqueios, "avisos": avisos, "pode_executar": not bloqueios, "ja_publicado": p["status_site"] == "no_ar",
            "folhas_a_enviar": a_enviar, "folhas_a_publicar": elegiveis, "um_passo": um_passo, "lotes_a_aprovar": a_aprovar,
            "fora": {"duplicadas": duplicadas, "autoria_divergente": divergentes, "nao_conferidas": nao_conferidas, "retidas": retidas}}


def executar(codigo: str, u: dict, progresso=None) -> dict:
    """Faz a sequência. Devolve {ok, parcial, etapa, mensagem, ...}. Levanta 400 (com o plano) se algo que só uma pessoa resolve impede."""
    from . import publicador
    from .rotas_projetos import Publicacao, publicar

    with _trava:
        if codigo in _em_andamento:
            raise HTTPException(409, "Este projeto já está sendo publicado agora. Aguarde terminar.")
        _em_andamento.add(codigo)
    try:
        con = connect()
        try:
            p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            if not p:
                raise HTTPException(404, "Projeto não existe")
            if p["mesclado_em"] or p["descartado_em"]:
                raise HTTPException(409, "Este projeto foi " + (f"mesclado em {p['mesclado_em']}" if p["mesclado_em"] else "descartado") + ": publique o projeto de destino.")
            pl = plano(con, p)
            pend = [r[0] for r in con.execute(f"SELECT codigo FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL} ORDER BY sequencial", (codigo,))]
            rep = repetido_sem_novidade(con, p, pend)
        finally:
            con.close()
        if rep:
            return rep
        if pl["bloqueios"]:
            raise HTTPException(400, "Não dá para publicar ainda: " + " | ".join(b["detalhe"] or b["texto"] for b in pl["bloqueios"]))
        feitos: list[str] = []

        def _p(**kw):
            if progresso:
                try:
                    progresso(kw)
                except Exception:  # noqa: BLE001  (o acompanhamento nunca derruba a publicação)
                    pass
        _p(evento="inicio", total=len(pend))

        if not p["tainacan_item_id"]:                                                       # 1) dossiê
            r = publicador.criar_dossie_no_site(codigo, u["email"])
            if r.get("erro") or not r.get("item_id"):
                return {"ok": False, "parcial": False, "etapa": "dossie", "feitos": feitos, "mensagem": f"Não consegui criar o dossiê no site: {r.get('erro') or 'sem resposta'}. Nada foi publicado."}
            feitos.append("dossie")
            _p(evento="dossie")

        t0, criadas, falhas = time.monotonic(), 0, []                                      # 2) folhas, em fatias de tempo (sempre avança ao menos uma)
        # 21/10: várias folhas ao mesmo tempo (site.envio_paralelo, padrão 3). Cada folha é uma chamada inteira e independente (item próprio
        # no site, conexão própria no banco); os avisos de andamento saem daqui, na ordem em que as folhas terminam.
        n = envio_paralelo()
        with ThreadPoolExecutor(max_workers=n) as ex:
            for i0 in range(0, len(pend), n):
                if criadas + len(falhas) > 0 and time.monotonic() - t0 >= ORCAMENTO_S:
                    break
                fatia = pend[i0:i0 + n]
                for c in fatia:
                    _p(evento="folha", codigo=c, feitas=criadas, total=len(pend))
                futuros = {ex.submit(publicador.criar_folha_no_site, c, u["email"]): c for c in fatia}
                for fu in as_completed(futuros):
                    c = futuros[fu]
                    try:
                        r = fu.result()
                    except Exception as e:  # noqa: BLE001
                        r = {"erro": str(e)[:300]}
                    if r.get("erro"):
                        falhas.append({"codigo": c, "erro": r["erro"]})
                        _p(evento="folha_falhou", codigo=c, erro=r["erro"])
                    else:
                        criadas += 1
                        _p(evento="folha_ok", codigo=c, feitas=criadas, total=len(pend))
        restam = len(pend) - criadas - len(falhas)
        if falhas:
            primeira = falhas[0]
            detalhe = f" {primeira['codigo']}: {str(primeira['erro'])[:150]}."
            return {"ok": False, "parcial": False, "etapa": "folhas", "feitos": feitos, "folhas_criadas": criadas, "falhas": falhas,
                    "mensagem": ("1 folha não subiu" if len(falhas) == 1 else f"{len(falhas)} folhas não subiram")
                    + " ao site." + detalhe
                    + " A publicação não foi concluída; verifique esta folha e tente novamente. As demais já enviadas não serão duplicadas."}
        if restam > 0:
            return {"ok": False, "parcial": True, "etapa": "folhas", "feitos": feitos, "folhas_criadas": criadas, "restam": restam,
                    "mensagem": f"Enviadas {criadas} folha(s); faltam {restam}."}

        _p(evento="autorizar")
        con = connect()                                                                     # 3) autorizar (os requisitos já foram checados no plano)
        try:
            if not con.execute("SELECT autorizado_site FROM projeto WHERE codigo=?", (codigo,)).fetchone()[0]:
                con.execute("UPDATE projeto SET autorizado_site=1, atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'autorizado_ao_publicar',?,NULL)", (codigo, u["email"]))
                con.commit()
                feitos.append("autorizar")
        finally:
            con.close()

        _p(evento="publicar")
        res = publicar(codigo, Publicacao(acao="publicar"), u)                              # 4) publicar (revalida TODOS os portões)
        if res.get("ok") and p["tainacan_item_id"]:                                           # 21/10: o público vê na hora (renova o cache do site)
            try:
                from . import wp as _wpmod
                publicador.renovar_no_site(_wpmod.WP(), p["tainacan_item_id"], codigo, projeto=True)
            except Exception:  # noqa: BLE001
                pass
        con = connect()
        try:
            resultado = resultado_publicacao(con, codigo) if res.get("ok") else {}
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'publicacao_guiada',?,?)",
                        (codigo, u["email"], json.dumps({"feitos": feitos, "folhas_criadas": criadas, "publicados": res.get("alterados"), "ok": res.get("ok"),
                                                         **({"folhas_publicadas": resultado["folhas_publicadas"]} if resultado else {})}, ensure_ascii=False)))
            if res.get("ok"):          # a Fila deixa de pedir ação: as listas JÁ APROVADAS deste projeto passam a "publicadas"
                for (lid,) in con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? AND aprovado_em IS NOT NULL AND etapa IN ('revisao','rascunho')", (codigo,)).fetchall():
                    con.execute("UPDATE lista_processamento SET etapa='publicado', atualizado_em=datetime('now') WHERE id=?", (lid,))
                    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'etapa_publicado',?,?)", (str(lid), u["email"], json.dumps({"pela": "publicacao_guiada"})))
            con.commit()
        finally:
            con.close()
        arq = None
        if res.get("ok") and publicar_arquiteto_junto():           # 5) 21/10: a página do arquiteto, sem a qual o projeto não aparece no site
            from . import fundo_site
            c2 = connect()
            try:
                pg = fundo_site.pagina_arquiteto(c2, p["fundo_codigo"])
            finally:
                c2.close()
            if not pg["publica"]:
                _p(evento="arquiteto")
                arq = fundo_site.mudar_pagina_arquiteto(p["fundo_codigo"], True, u["email"])
                if arq.get("ok"):
                    feitos.append("arquiteto")
        out = {**res, "parcial": False, "etapa": "publicar", "feitos": feitos, "folhas_criadas": criadas, "publicados": res.get("alterados", 0), **resultado}
        if arq is not None:
            out["arquiteto"] = arq
            if not arq.get("ok"):
                out["aviso_arquiteto"] = ("O projeto foi publicado, mas a página do arquiteto não: " + (arq.get("erro") or "o site não respondeu")
                                          + ". Sem ela o projeto não aparece no site: publique-a no quadro “Página do arquiteto no site”, no fundo.")
        return out
    finally:
        with _trava:
            _em_andamento.discard(codigo)


def resultado_publicacao(con, codigo: str) -> dict:
    """#104 · O que ficou público depois de publicar, para a tela de resultado: o projeto, quantas folhas, o que ficou de fora
    e o endereço da página pública (o REAL do espelho do site quando existe; senão o confirmado; senão o presumido)."""
    from .rotas_projetos import _pagina_publica_projeto
    p = con.execute("SELECT titulo, cidade FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    q = lambda sql: con.execute(sql, (codigo,)).fetchone()[0]  # noqa: E731
    pub = _pagina_publica_projeto(con, codigo, p["titulo"], p["cidade"])
    return {"projeto": {"codigo": codigo, "titulo": p["titulo"]},
            "folhas_publicadas": q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'"),
            "folhas_fora": q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND (status_site IS NULL OR status_site<>'no_ar')"),
            "url_publica": pub["url"], "url_origem": pub["origem"]}
