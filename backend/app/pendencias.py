"""Fonte ÚNICA do que espera alguém (cartão H6b): painel inicial, contadores do menu e Filas contam com ESTAS funções.

Regras (nenhuma é nova; só juntadas num lugar para os números baterem entre as telas):
- fase de cada lote = filas_fase.fase_da_lista, sobre os MESMOS lotes da Fila (lista_processamento sem descartado_em);
- "pronto para publicar" = lote na fase publicar cujo projeto passa no plano da publicação guiada sem bloqueio (a mesma regra do botão Publicar, P0-9);
- "travado por direitos" = fundo cujo direitos_permitem_publicar recusa e que tem folhas esperando para ir ao site;
- erro que bloqueia, pedido aguardando e decisão pendente: as mesmas consultas de /api/painel, /api/erros, /api/solicitacoes e /api/decisoes.
Proibido recalcular estes números no navegador.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .filas_fase import fase_da_lista

_PREFIXO_PASTA = re.compile(r"^(?:lote\s+)?[A-Za-z]{1,3}\d{1,5}[_ -]+", re.I)


def titulo_limpo(t: str | None) -> str:
    """O nome que uma pessoa reconhece: sem o prefixo de pasta do scanner ("T098_", "P2 ") e sem sublinhados."""
    s = (t or "").strip()
    s2 = _PREFIXO_PASTA.sub("", s)
    s = (s2 or s).replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def _horas_desde(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return max(0.0, (datetime.utcnow() - datetime.fromisoformat(str(ts).replace("T", " ")[:19])).total_seconds() / 3600)
    except ValueError:
        return None


def texto_espera(horas: float | None) -> str:
    if horas is None:
        return ""
    if horas < 1:
        return "chegou agora há pouco"
    if horas < 48:
        return f"esperando há {round(horas)} h"
    return f"esperando há {round(horas / 24)} dias"


def lotes(con) -> list[dict]:
    """Os lotes da Fila (os mesmos de /api/filas), cada um com a fase."""
    saida = []
    for r in con.execute("""SELECT l.id, l.nome, l.etapa, l.aprovado_em, l.atualizado_em, l.criado_em, l.projeto_codigo, l.folhas_esperadas, l.folhas_encontradas,
                                   p.titulo AS projeto_titulo, p.fundo_codigo, p.status_site,
                                   (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id) AS itens_total,
                                   (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.revisao='pendente') AS itens_pendentes
                              FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo
                             WHERE l.descartado_em IS NULL AND p.mesclado_em IS NULL"""):
        d = dict(r)
        d["fase"] = fase_da_lista(d["etapa"], d["itens_total"], d["itens_pendentes"], d.get("aprovado_em"))
        saida.append(d)
    return saida


def _plano_projeto(con, codigo: str, cache: dict) -> dict | None:
    if codigo not in cache:
        from .publicacao_guiada import plano
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        cache[codigo] = plano(con, p) if p else None
    return cache[codigo]


def _situacao_publicar(pl: dict | None) -> dict:
    """pronto | parcial (algumas folhas já no site) | travado (com o que falta, em frase)."""
    if not pl:
        return {"estado": "travado", "falta": "projeto não encontrado"}
    if pl["bloqueios"]:
        b = pl["bloqueios"][0]
        return {"estado": "travado", "falta": b.get("detalhe") or b.get("texto"), "acao": b.get("acao")}
    if not pl["folhas_a_publicar"]:
        return {"estado": "travado", "falta": "nenhuma folha pronta para ir ao site"}
    no_site = pl["folhas_a_publicar"] - pl["folhas_a_enviar"]
    if pl["folhas_a_enviar"] and no_site > 0:
        return {"estado": "parcial", "no_site": no_site, "total": pl["folhas_a_publicar"], "faltam": pl["folhas_a_enviar"]}
    return {"estado": "pronto", "total": pl["folhas_a_publicar"], "faltam": pl["folhas_a_enviar"]}


def fundos_travados(con) -> list[dict]:
    """Fundos que a regra de direitos impede de publicar e que têm folhas esperando para ir ao site."""
    from .rotas_gestao import direitos_permitem_publicar
    out = []
    for f in con.execute("""SELECT f.codigo, f.sigla, f.titulo, COUNT(DISTINCT p.codigo) AS projetos
                              FROM fundo f JOIN projeto p ON p.fundo_codigo=f.codigo
                             WHERE f.ativo=1 AND p.status_site!='no_ar' AND p.mesclado_em IS NULL
                               AND EXISTS (SELECT 1 FROM item i WHERE i.projeto_codigo=p.codigo)
                             GROUP BY f.codigo ORDER BY projetos DESC, f.codigo"""):
        msg = direitos_permitem_publicar(con, f["codigo"])
        if msg:
            out.append({"codigo": f["codigo"], "sigla": f["sigla"], "titulo": f["titulo"], "projetos": f["projetos"], "motivo": msg})
    return out


def _decisoes(con) -> list[dict]:
    out = []
    for d in con.execute("""SELECT d.*, (SELECT COUNT(*) FROM decisao_chave c WHERE c.decisao_id=d.id) AS chaves_extra
                              FROM decisao d WHERE d.situacao='pendente' ORDER BY d.criada_em, d.id"""):
        try:
            ctx = json.loads(d["contexto"] or "{}")
        except ValueError:
            ctx = {}
        cand = (ctx.get("candidatos") or [{}])[0] if ctx.get("candidatos") else {}
        out.append({"id": d["id"], "titulo": d["titulo"], "fundo": d["fundo_codigo"], "origem": d["origem"], "criada_em": d["criada_em"],
                    "vezes": 1 + (d["chaves_extra"] or 0), "pasta": (ctx.get("pedido") or {}).get("identificacao_original"),
                    "candidato": {"codigo": cand.get("codigo"), "titulo": cand.get("titulo")} if cand else None})
    return out


def contar_pendencias(con, *, com_listas: bool = False) -> dict:
    """{decisoes, decisoes_pastas, decisoes_estacao, lotes_importar, lotes_conferir, folhas_conferir, lotes_aprovar, lotes_publicar,
    prontos_publicar, publicando_parcial, travados_direitos, travados_projetos, erros_bloqueantes, pedidos_aguardando,
    lotes_processando, lotes_lendo, lotes_na_fila, lotes_erro, publicando, material_novo, esperam_admin}.
    decisoes = perguntas abertas; decisoes_pastas = quantas vezes elas chegaram (a mesma pergunta repetida pela estação vira UMA decisão, com várias chaves)."""
    L = lotes(con)
    por = {}
    for l in L:
        por.setdefault(l["fase"], []).append(l)
    planos: dict = {}
    publicar = por.get("publicar", [])
    for l in publicar:
        l["publicar"] = _situacao_publicar(_plano_projeto(con, l["projeto_codigo"], planos))
    dec = _decisoes(con)
    trav = fundos_travados(con)
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    n = {
        "decisoes": len(dec),
        "decisoes_pastas": sum(d["vezes"] for d in dec),
        "decisoes_estacao": sum(1 for d in dec if d["origem"] == "estacao"),
        "lotes_importar": len(por.get("importar", [])),
        "lotes_conferir": len(por.get("conferir", [])),
        "folhas_conferir": sum(l["itens_pendentes"] for l in por.get("conferir", [])),
        "lotes_aprovar": len(por.get("aprovar", [])),
        "lotes_publicar": len(publicar),
        "prontos_publicar": sum(1 for l in publicar if l["publicar"]["estado"] in ("pronto", "parcial")),
        "publicando_parcial": sum(1 for l in publicar if l["publicar"]["estado"] == "parcial"),
        "travados_direitos": len(trav),
        "travados_projetos": sum(f["projetos"] for f in trav),
        "erros_bloqueantes": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'"),
        "pedidos_aguardando": q("SELECT COUNT(*) FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento')"),
        "erros_abertos": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')"),             # a aba "Abertos" de Erros
        "pedidos_abertos": q("SELECT COUNT(*) FROM solicitacao WHERE situacao NOT IN ('entregue','recusada')"),  # a aba "Abertas" de Solicitações
        "lotes_processando": len(por.get("processando", [])),
        "lotes_lendo": sum(1 for l in por.get("processando", []) if l["etapa"] == "processando"),
        "lotes_na_fila": sum(1 for l in por.get("processando", []) if l["etapa"] == "enviado"),
        "lotes_erro": len(por.get("erro", [])),
        "publicando": q("SELECT COUNT(*) FROM tarefa_publicacao WHERE estado='rodando' AND tipo='publicar'"),
    }
    n["material_novo"] = n["lotes_importar"] + n["lotes_conferir"]            # contador do menu: o que é de operador
    n["esperam_admin"] = n["lotes_aprovar"] + n["lotes_publicar"]
    if com_listas:
        n["_lotes"], n["_decisoes"], n["_travados"] = L, dec, trav
    return n


# ---------------- tarefas do painel inicial (o que fazer agora, agrupado e com dono) ----------------
FINALIDADE = {"publicacao": "publicação", "pesquisa": "pesquisa", "editorial": "uso editorial", "familia": "a família", "exposicao": "exposição"}


def _acao(rotulo: str, tipo: str, alvo) -> dict:
    return {"rotulo": rotulo, "tipo": tipo, "alvo": alvo}


def tarefas(con, papel: str, n: dict | None = None, por_grupo: int = 3) -> list[dict]:
    """Grupos na ordem Decidir → Conferir → Aprovar e publicar → Problemas que bloqueiam → Pedidos. Cada linha: sev (r|a|b), titulo, codigo, detalhe, acao."""
    n = n or contar_pendencias(con, com_listas=True)
    admin = papel in ("admin", "master")
    leitura = papel == "leitura"
    L, dec = n["_lotes"], n["_decisoes"]
    grupos: list[dict] = []

    # 1) decidir: o CAMP Vision pode estar parado esperando
    linhas = []
    for d in dec:
        c = d.get("candidato") or {}
        tit = f"“{d['titulo']}” é o mesmo projeto que “{c.get('titulo')}”?" if c.get("titulo") else f"“{d['titulo']}”: projeto novo ou um que já existe?"
        partes = [f"chegou {d['vezes']} vezes" if d["vezes"] > 1 else None, texto_espera(_horas_desde(d["criada_em"])),
                  "o CAMP Vision está parado nesta pasta" if d["origem"] == "estacao" else None]
        linhas.append({"sev": "r" if d["origem"] == "estacao" else "a", "titulo": tit, "codigo": c.get("codigo") or d["fundo"],
                       "detalhe": " · ".join(p for p in partes if p), "acao": _acao("Decidir" if admin else "Ver", "decisao", d["id"])})
    if linhas:
        grupos.append({"id": "decidir", "titulo": "Decidir", "quem": "admin", "total": len(linhas), "itens": linhas[:por_grupo],
                       "ver_todos": {"rotulo": f"Ver as {len(linhas)} decisões", "rota": "decisoes"}})

    # 2) trazer e conferir folhas (operador): o maior lote primeiro, depois o mais antigo
    conf = sorted([l for l in L if l["fase"] in ("importar", "conferir")],      # importar primeiro (um clique e destrava a conferência), depois o maior lote, depois o mais antigo
                  key=lambda l: (0 if l["fase"] == "importar" else 1, -(l["itens_pendentes"] or 0), str(l["atualizado_em"] or "")))
    maior = max((l["itens_pendentes"] or 0 for l in conf if l["fase"] == "conferir"), default=0)
    linhas = []
    for l in conf:
        h = _horas_desde(l["atualizado_em"])
        if l["fase"] == "conferir":
            det = [f"{l['itens_pendentes']} de {l['itens_total']} folhas a conferir", "o maior lote da fila" if l["itens_pendentes"] == maior and len(conf) > 1 else None,
                   texto_espera(h) if h and h > 48 else None]
            linhas.append({"sev": "a", "titulo": titulo_limpo(l["projeto_titulo"]), "codigo": l["projeto_codigo"], "detalhe": " · ".join(p for p in det if p),
                           "acao": _acao("Conferir", "conferir", l["projeto_codigo"])})
        else:
            linhas.append({"sev": "b", "titulo": titulo_limpo(l["projeto_titulo"]), "codigo": l["projeto_codigo"],
                           "detalhe": "o CAMP Vision terminou a leitura; falta trazer as folhas para o painel" + (f" · {texto_espera(h)}" if h and h > 48 else ""),
                           "acao": _acao("Importar", "importar", l["id"])})
    if linhas:
        grupos.append({"id": "conferir", "titulo": "Conferir folhas", "quem": "operador", "total": len(linhas), "itens": linhas[:por_grupo],
                       "ver_todos": {"rotulo": f"Ver os {len(linhas)} lotes para importar e conferir", "rota": "filas/operador"}})

    # 3) aprovar e publicar (admin)
    linhas = []
    for l in sorted([l for l in L if l["fase"] == "aprovar"], key=lambda l: str(l["atualizado_em"] or "")):
        linhas.append({"sev": "b", "titulo": titulo_limpo(l["projeto_titulo"]), "codigo": l["projeto_codigo"],
                       "detalhe": f"as {l['itens_total']} folhas já foram conferidas · falta aprovar o lote", "acao": _acao("Aprovar", "aprovar", l["id"])})
    ordem = {"parcial": 0, "pronto": 1, "travado": 2}
    for l in sorted([l for l in L if l["fase"] == "publicar"], key=lambda l: (ordem[l["publicar"]["estado"]], str(l["atualizado_em"] or ""))):
        s = l["publicar"]
        if s["estado"] == "parcial":
            det, rot, sev = f"{s['no_site']} de {s['total']} folhas já no site · falta {s['faltam']} e publicar", "Terminar de publicar", "b"
        elif s["estado"] == "pronto":
            det, rot, sev = f"{s['total']} folhas prontas · nada impede publicar", "Publicar", "b"
        else:
            det, rot, sev = f"travado: {s['falta']}", "Ver o que falta", "a"
        linhas.append({"sev": sev, "titulo": titulo_limpo(l["projeto_titulo"]), "codigo": l["projeto_codigo"], "detalhe": det,
                       "acao": _acao(rot, "publicar" if s["estado"] != "travado" else "projeto", l["projeto_codigo"])})
    if linhas and admin:
        grupos.append({"id": "aprovar_publicar", "titulo": "Aprovar e publicar", "quem": "admin", "total": len(linhas), "itens": linhas[:por_grupo],
                       "ver_todos": {"rotulo": f"Ver os {len(linhas)} lotes que esperam um admin", "rota": "filas/admin"}})

    # 4) problemas que bloqueiam: erro bloqueante aberto e lote parado com erro no CAMP Vision
    linhas = []
    for e in con.execute("""SELECT id, codigo, descricao, criado_em FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'
                            ORDER BY criado_em"""):
        no_ar = con.execute("SELECT 1 FROM projeto WHERE status_site='no_ar' AND (?=codigo OR ? LIKE codigo||'-%')", (e["codigo"], e["codigo"])).fetchone()
        linhas.append({"sev": "r", "titulo": e["descricao"], "codigo": e["codigo"],
                       "detalhe": " · ".join(p for p in ("o projeto está no site com este problema" if no_ar else "impede publicar", texto_espera(_horas_desde(e["criado_em"]))) if p),
                       "acao": _acao("Ver o problema", "erro", e["id"])})
    for l in [l for l in L if l["fase"] == "erro"]:
        linhas.append({"sev": "r", "titulo": f"O CAMP Vision parou com erro em {titulo_limpo(l['projeto_titulo'])}", "codigo": l["projeto_codigo"],
                       "detalhe": texto_espera(_horas_desde(l["atualizado_em"])), "acao": _acao("Ver o erro", "fila_erro", l["id"])})
    if linhas:
        grupos.append({"id": "problemas", "titulo": "Problemas que bloqueiam", "quem": "operador", "total": len(linhas), "itens": linhas[:por_grupo],
                       "ver_todos": {"rotulo": f"Ver os {len(linhas)} problemas", "rota": "erros"}})

    # 5) pedidos esperando resposta
    linhas = []
    for s in con.execute("SELECT id, solicitante, situacao, recebida_em, finalidade FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento') ORDER BY recebida_em"):
        fin = FINALIDADE.get(s["finalidade"])
        linhas.append({"sev": "a", "titulo": f"{s['solicitante']} pediu material" + (f" para {fin}" if fin else ""), "codigo": None,
                       "detalhe": " · ".join(p for p in ("aguarda a sua resposta" if s["situacao"] == "aguarda_resposta" else "aguarda o orçamento",
                                                         texto_espera(_horas_desde(s["recebida_em"]))) if p),
                       "acao": _acao("Responder", "pedido", s["id"])})
    if linhas:
        grupos.append({"id": "pedidos", "titulo": "Pedidos esperando resposta", "quem": "operador", "total": len(linhas), "itens": linhas[:por_grupo],
                       "ver_todos": {"rotulo": f"Ver os {len(linhas)} pedidos", "rota": "solicitacoes"}})

    if leitura:                                       # quem só lê vê o que está acontecendo, sem botão de ação: a linha abre a página
        for g in grupos:
            for i in g["itens"]:
                i["acao"] = None
    return grupos


def caminho(con, n: dict) -> list[dict]:
    """Os 7 passos do material com a quantidade em cada um. 'acumula' = o passo de gente com mais trabalho; 'pronto' = pode avançar."""
    from . import qnap_coletor
    snap = qnap_coletor.ultima(con)
    entrada = (snap or {}).get("entrada_bruta")
    cv = n["lotes_processando"] + n["decisoes_estacao"] + n["lotes_erro"]
    cv_partes = [f"{n['lotes_lendo']} lendo" if n["lotes_lendo"] else None, f"{n['lotes_na_fila']} na fila" if n["lotes_na_fila"] else None,
                 f"{n['decisoes_estacao']} {'decisão' if n['decisoes_estacao'] == 1 else 'decisões'}" if n["decisoes_estacao"] else None,
                 f"{n['lotes_erro']} com erro" if n["lotes_erro"] else None]
    passos = [
        {"id": "digitalizar", "nome": "Digitalizar", "q": None, "detalhe": "estações de captura", "rota": "estacoes"},
        {"id": "qnap", "nome": "No QNAP", "q": entrada, "detalhe": "pastas na entrada" if entrada is not None else "sem leitura do QNAP", "rota": "estacoes"},
        {"id": "campvision", "nome": "CAMP Vision", "q": cv, "detalhe": " · ".join(p for p in cv_partes if p) or "nada em leitura", "rota": "filas/processando"},
        {"id": "importar", "nome": "Importar", "q": n["lotes_importar"], "detalhe": "lote para trazer" if n["lotes_importar"] == 1 else "lotes para trazer", "rota": "filas/importar"},
        {"id": "conferir", "nome": "Conferir", "q": n["lotes_conferir"], "detalhe": f"{'lote' if n['lotes_conferir'] == 1 else 'lotes'} · {n['folhas_conferir']} folhas", "rota": "filas/conferir"},
        {"id": "aprovar", "nome": "Aprovar", "q": n["lotes_aprovar"], "detalhe": "lote conferido" if n["lotes_aprovar"] == 1 else "lotes conferidos", "rota": "filas/aprovar"},
        {"id": "publicar", "nome": "Publicar", "q": n["lotes_publicar"],
         "detalhe": (f"{n['prontos_publicar']} {'pronto' if n['prontos_publicar'] == 1 else 'prontos'}" + (f" · {n['lotes_publicar'] - n['prontos_publicar']} {'travado' if n['lotes_publicar'] - n['prontos_publicar'] == 1 else 'travados'}" if n["lotes_publicar"] > n["prontos_publicar"] else "")) if n["lotes_publicar"] else "nada aprovado esperando", "rota": "filas/publicar"},
    ]
    gente = [p for p in passos if p["id"] in ("importar", "conferir", "aprovar", "publicar") and p["q"]]
    pior = max(gente, key=lambda p: p["q"], default=None)
    for p in passos:
        p["estado"] = "acumula" if p is pior else ("pronto" if p["id"] in ("aprovar", "publicar") and p["q"] else "")
    return passos


def no_site(con) -> dict:
    """Quanto do acervo já está no site (substitui "Acervo em números")."""
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "folhas": {"no_ar": q("SELECT COUNT(*) FROM item WHERE status_site='no_ar'"), "total": q("SELECT COUNT(*) FROM item")},
        "projetos": {"no_ar": q("SELECT COUNT(*) FROM projeto WHERE status_site='no_ar' AND mesclado_em IS NULL"),
                     "total": q("SELECT COUNT(*) FROM projeto WHERE mesclado_em IS NULL"),
                     "sem_folhas": q("SELECT COUNT(*) FROM projeto p WHERE p.mesclado_em IS NULL AND p.status_site!='no_ar' AND NOT EXISTS (SELECT 1 FROM item i WHERE i.projeto_codigo=p.codigo)")},
        "fundos": {"no_ar": q("SELECT COUNT(*) FROM fundo WHERE ativo=1 AND status_site='no_ar'"), "total": q("SELECT COUNT(*) FROM fundo WHERE ativo=1")},
    }


# ---------------- "Hoje": até 6 frases do dia, com os eventos repetidos juntos ----------------
_VERBOS = {
    "site_publicar": "publicou", "site_despublicar": "despublicou", "revisao_aprovada": "aprovou o lote de", "revisao_reaberta": "reabriu a revisão de",
    "folhas_importadas_do_lote": "importou as folhas de", "criado": "criou o projeto", "projeto_mesclado": "juntou", "lote_movido": "moveu um lote de",
    "lote_descartado": "descartou um lote de", "publicacao_guiada": "publicou", "releitura_pedida": "pediu nova leitura de",
}


def _nome(con, ator: str, cache: dict) -> str:
    if ator not in cache:
        r = con.execute("SELECT nome FROM usuario WHERE email=?", (ator,)).fetchone()
        cache[ator] = r[0].split()[0] if r and r[0] else ("CAMP Vision" if (ator or "").startswith("campvision") else (ator or "alguém").split("@")[0])
    return cache[ator]


def atividade_hoje(con, limite: int = 6) -> list[dict]:
    """[{quando, texto, codigo}] mais recente primeiro. Em `texto`, {codigo} marca onde o código entra (a tela o mostra como código)."""
    evs = con.execute("""SELECT id, entidade, codigo, tipo, ator, quando, detalhe FROM evento
                          WHERE date(quando,'localtime')=date('now','localtime') AND tipo NOT IN ('login','login_falhou','visto') ORDER BY id DESC LIMIT 400""").fetchall()
    nomes: dict = {}
    grupos: dict = {}
    ordem: list = []
    for e in evs:
        cod = e["codigo"] or ""
        proj = "-".join(cod.split("-")[:2]) if e["entidade"] == "item" and cod.count("-") >= 2 else cod
        if e["entidade"] == "item" and e["tipo"] in ("revisao", "site_item_criado", "giro", "editado", "folha_retida", "folha_liberada"):
            chave = ("item", e["tipo"], e["ator"], proj)
        elif e["tipo"] in ("material_novo_pronto", "folhas_importadas_do_lote") and (e["ator"] or "").startswith("campvision"):
            chave = ("cv", proj.split("-")[0])
        elif e["tipo"] == "revisao_em_lote":
            chave = ("rev_lote", e["ator"], proj)
        else:
            chave = ("ev", e["id"])
        if chave not in grupos:
            grupos[chave] = {"evs": [], "proj": proj}
            ordem.append(chave)
        grupos[chave]["evs"].append(e)
    out = []
    for chave in ordem:
        g = grupos[chave]
        e0 = g["evs"][0]
        quem = _nome(con, e0["ator"], nomes)
        n = len(g["evs"])
        projs = sorted({ev["codigo"] for ev in g["evs"]})
        if chave[0] == "item":
            o_que = {"revisao": "conferiu", "site_item_criado": "enviou ao site (escondida)", "giro": "girou", "editado": "editou",
                     "folha_retida": "reteve", "folha_liberada": "liberou"}[chave[1]]
            if chave[1] == "site_item_criado":
                texto = f"{quem} enviou {n} {'folha' if n == 1 else 'folhas'} de {{codigo}} ao site (ainda escondidas)"
            else:
                texto = f"{quem} {o_que} {n} {'folha' if n == 1 else 'folhas'} de {{codigo}}"
            cod = g["proj"]
        elif chave[0] == "cv":
            if len(projs) == 1:
                texto, cod = "CAMP Vision entregou {codigo}; as folhas vieram para o painel", projs[0]
            else:
                f = con.execute("SELECT titulo FROM fundo WHERE codigo=?", (chave[1],)).fetchone()
                texto, cod = f"CAMP Vision entregou {len(projs)} projetos do {{codigo}}" + (f" ({f[0]})" if f else ""), chave[1]
        elif chave[0] == "rev_lote":
            tot = 0
            for ev in g["evs"]:
                try:
                    tot += int((json.loads(ev["detalhe"] or "{}") or {}).get("conferidas") or 0)
                except (ValueError, TypeError, AttributeError):
                    pass
            texto, cod = f"{quem} conferiu {tot or 'as'} {'folha' if tot == 1 else 'folhas'} de {{codigo}} de uma vez", g["proj"]
        else:
            verbo = _VERBOS.get(e0["tipo"]) if e0["entidade"] in ("projeto", "lista") else None
            if verbo:
                titulo = ""
                if e0["entidade"] == "projeto":
                    p = con.execute("SELECT titulo FROM projeto WHERE codigo=?", (e0["codigo"],)).fetchone()
                    titulo = f" {titulo_limpo(p[0])}" if p and p[0] else ""
                texto, cod = f"{quem} {verbo} {{codigo}}{titulo}", e0["codigo"]
            else:
                continue                                # evento técnico sem frase: fica no histórico completo, não no resumo do dia
        out.append({"quando": e0["quando"], "texto": texto, "codigo": cod})
        if len(out) >= limite:
            break
    return out


def ritmo(con, dias: int = 14) -> dict:
    """Folhas conferidas, importadas e enviadas ao site por dia (horário de São Paulo), últimos N dias, com a média e a previsão."""
    dias = max(1, min(int(dias), 90))
    base = {r[0]: {"dia": r[0], "conferidas": 0, "importadas": 0, "publicadas": 0}
            for r in con.execute(f"WITH RECURSIVE d(n) AS (SELECT 0 UNION ALL SELECT n+1 FROM d WHERE n<{dias - 1}) SELECT date('now','-3 hours', '-' || n || ' days') FROM d")}
    for dia, n in con.execute("SELECT date(revisado_em,'-3 hours'), COUNT(*) FROM item WHERE revisado_em IS NOT NULL AND revisao IN ('conferida','corrigida') AND revisado_em >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["conferidas"] = n
    for dia, n in con.execute("SELECT date(criado_em,'-3 hours'), COUNT(*) FROM item WHERE lote_id IS NOT NULL AND criado_em >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["importadas"] = n
    for dia, n in con.execute("SELECT date(quando,'-3 hours'), COUNT(*) FROM evento WHERE tipo='site_item_criado' AND quando >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["publicadas"] = n
    serie = sorted(base.values(), key=lambda x: x["dia"])
    com_trabalho = [x["conferidas"] for x in serie if x["conferidas"] > 0]
    media = round(sum(com_trabalho) / len(com_trabalho), 1) if com_trabalho else 0
    falta = contar_pendencias(con)["folhas_conferir"]
    return {"dias": serie, "media_conferidas": media, "folhas_a_conferir": falta,
            "dias_para_zerar": (round(falta / media) if media else None)}


def alertas_criticos(con) -> list[dict]:
    """Só o que PARA o trabalho (faixa vermelha do painel): QNAP crítico, CAMP Vision sem sinal há mais de 1 h, site sem resposta 2 vezes seguidas.
    Mesmas regras do e-mail (alertas.avaliar); o site usa a última medição em cache (nunca espera a rede)."""
    from . import alertas, qnap_coletor
    from .rotas_gestao import site_em_cache
    av = alertas.avaliar(con, medir_site=site_em_cache, estado_backup=lambda: {})
    out = []
    if av.get("qnap", {}).get("critico"):
        snap = qnap_coletor.ultima(con) or {}
        _, pct = qnap_coletor.nivel_espaco(con, snap.get("total_gb"), snap.get("livre_gb"))
        _, dias = qnap_coletor._tendencia(con, snap.get("livre_gb"))
        ritmo_txt = f" No ritmo desta semana, enche em cerca de {dias} {'dia' if dias == 1 else 'dias'}." if dias else ""
        out.append({"id": "qnap", "titulo": f"QNAP quase cheio: {round(snap.get('livre_gb') or 0)} GB livres ({str(pct).replace('.', ',')}%).",
                    "texto": (ritmo_txt + " Libere espaço antes de digitalizar mais.").strip(), "acao": {"rotulo": "Ver o que ocupa espaço", "rota": "estacoes"}})
    cv = av.get("campvision") or {}
    if cv.get("parado"):
        out.append({"id": "campvision", "titulo": f"CAMP Vision sem dar sinal há {cv['parado_h']} h.",
                    "texto": "Os lotes novos não estão sendo lidos. Confira se o computador do CAMP Vision está ligado.", "acao": {"rotulo": "Ver as máquinas", "rota": "estacoes"}})
    if (av.get("replica") or {}).get("critico"):            # cartão 149: o acervo ficou com uma cópia só
        out.append({"id": "replica", "titulo": "A cópia do acervo parou.", "texto": av["replica"]["texto"].replace("A réplica do acervo parou: ", "").strip(),
                    "acao": {"rotulo": "Ver a cópia do acervo", "rota": "estacoes"}})
    if (av.get("site") or {}).get("critico"):
        out.append({"id": "site", "titulo": "O site não respondeu em duas verificações seguidas.",
                    "texto": "Confira se camp.arq.br abre; se não abrir, avise a hospedagem.", "acao": {"rotulo": "Ver o site", "rota": "estacoes"}})
    return out
