"""CAMP-HOME-UX (22/11/2026, documento do Rafael "Redesenho do painel inicial / Precisa de você"): o que a Home ganhou além do que já existia.

1. **Prioridade explicável (§8)**: cada linha de "O que fazer agora" recebe uma nota de 0 a 100 com os pesos do documento
   (gravidade 40 · tempo parado 20, com teto · bloqueio de outra etapa 20 · prazo/risco 20) e a frase do porquê
   ("Prioridade alta porque impede a publicação e aguarda há 19 dias"). Só usa sinais que o painel TEM (tipo da tarefa, o CAMP Vision
   parado, problema que bloqueia ou que já está no site, tempo na etapa, prazo vencido do empréstimo); nada é inventado.
2. **Responsável (§3/§5)**: o painel não tinha dono de tarefa. `tarefa_responsavel` guarda quem pegou cada tarefa (a chave é a mesma
   do "Agora não": decisao:3, lote:12, erro:5, pedido:2…), com evento no Histórico. Pedido e empréstimo já tinham responsável: valem
   enquanto ninguém atribuir outro. "Minha fila" = atribuída a mim (ou que eu peguei), ou problema que eu relatei.
3. **Progresso e conquistas (§6, piloto cuidadoso)**: pontos SÓ de eventos validados, lidos do estado atual do banco (folha conferida
   que continua conferida, lote aprovado que continua aprovado, decisão respondida, problema corrigido com a frase do que foi feito).
   Desfez (reabriu a revisão, reabriu o problema, desaprovou o lote)? O ponto some sozinho, porque a conta é sempre refeita do estado
   atual. Meta coletiva da semana (`meta.semana`, admin muda), nível pessoal, conquistas que não comparam pessoas, "ocultar conquistas"
   por pessoa e, só se um admin ligar (`jogo.ranking_equipe`, padrão desligado), o quadro da equipe. Sem cobrança por dias parados.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["home"])

# ---------------------------------------------------------------- 1. prioridade (§8) ----------------------------------------------------
PESOS = {"gravidade": 40, "tempo": 20, "bloqueio": 20, "risco": 20}
TEMPO_TETO_H = 14 * 24           # depois de 14 dias parado o tempo não soma mais (teto: não favorece infinitamente o que é antigo)
NIVEIS = ((60, "critico", "Crítico"), (45, "alto", "Alto"), (25, "medio", "Médio"), (0, "baixo", "Baixo"))
_NA_FRASE = {"critico": "crítica", "alto": "alta", "medio": "média", "baixo": "baixa"}   # "Prioridade alta porque…"
# gravidade (0..1) e bloqueio (0..1) pelo tipo da ação da linha; a frase do bloqueio entra no "porquê"
_GRAV = {"problema": 0.5, "aviso": 0.15,   # CAMP-PROB-UX: problema que pede correção e aviso (a Central de Problemas usa esta mesma nota)
         "decisao": 0.6, "erro": 0.8, "fila_erro": 0.9, "reler": 0.6, "destino": 0.5, "importar": 0.4, "conferir": 0.5, "aprovar": 0.5,
         "publicar": 0.5, "projeto": 0.4, "pedido": 0.5, "emprestimo": 0.6, "rota": 0.5}
_BLOQ = {"decisao": (0.5, "o projeto espera a resposta"), "erro": (1.0, "impede a publicação"), "fila_erro": (1.0, "o lote parou no CAMP Vision"),
         "reler": (1.0, "a leitura do lote parou"), "destino": (1.0, "impede a conferência"), "importar": (1.0, "impede a conferência"),
         "conferir": (1.0, "impede aprovar e publicar"), "aprovar": (1.0, "impede a publicação"), "publicar": (0.5, "falta só publicar"),
         "projeto": (0.5, "falta resolver para publicar")}


def _txt_espera(h: float | None) -> str:
    if h is None:
        return ""
    if h < 24:
        return "aguarda há menos de 1 dia"
    d = round(h / 24)
    return f"aguarda há {d} {'dia' if d == 1 else 'dias'}"


def prioridade(item: dict, grupo: str | None = None) -> dict:
    """Nota 0–100 e o porquê, para UMA linha da fila. Função pura (sem banco): o teste chama direto.
    gravidade = impacto do tipo de trabalho (o CAMP Vision parado e problema já no site valem o máximo); tempo = horas na etapa / 14 dias
    (teto); bloqueio = a linha segura a etapa seguinte; risco = prazo vencido (empréstimo), dado errado já público, pedido sem resposta
    há mais de 7 dias, aviso de lote incompleto do CAMP Vision."""
    a = item.get("acao") or {}
    tipo = a.get("tipo") or ""
    base = grupo == "base" or item.get("filtro") == "base"
    urg = str(item.get("urgente") or "")
    det = str(item.get("detalhe") or "")
    esp = item.get("espera_h")
    esp = float(esp) if isinstance(esp, (int, float)) else None
    if base:
        g, (b, btxt) = 0.15, (0.0, "")
    else:
        g = _GRAV.get(tipo, 0.5)
        b, btxt = _BLOQ.get(tipo, (0.0, ""))
    motivos = []
    r, rtxt = 0.0, ""
    if "parado nesta pasta" in urg or "parado nesta pasta" in det:            # decisão que segura o CAMP Vision
        g, b, btxt = 1.0, 1.0, "o CAMP Vision está parado esperando"
    if tipo == "erro" and "está no site" in (urg + det):                       # problema que bloqueia e o projeto já está publicado
        g, r, rtxt = 1.0, 1.0, "o projeto já está no site com este problema"
    if tipo == "fila_erro" and str(item.get("titulo") or "").startswith("O CAMP Vision avisou"):
        r, rtxt = 0.5, "o CAMP Vision avisou um lote incompleto"
    if tipo == "emprestimo":
        dias = round((esp or 0) / 24)
        r, rtxt = min(1.0, 0.5 + dias / 14), f"o prazo do empréstimo venceu há {dias} {'dia' if dias == 1 else 'dias'}"
    if tipo == "pedido" and esp is not None and esp >= 7 * 24:
        r, rtxt = (1.0 if esp >= 14 * 24 else 0.5), "o pedido espera resposta há mais de 7 dias"
    t = 0.0 if esp is None or base else min(esp, TEMPO_TETO_H) / TEMPO_TETO_H
    partes = {"gravidade": round(PESOS["gravidade"] * g), "tempo": round(PESOS["tempo"] * t),
              "bloqueio": round(PESOS["bloqueio"] * b), "risco": round(PESOS["risco"] * r)}
    nota = max(0, min(100, sum(partes.values())))
    nivel, rotulo = next((n, rr) for corte, n, rr in NIVEIS if nota >= corte)
    if rtxt:
        motivos.append(rtxt)
    if btxt and b >= 0.5:
        motivos.append(btxt)
    te = "" if base else _txt_espera(esp)
    if te and not (rtxt and tipo in ("emprestimo", "pedido")) and (t >= 0.07 or not motivos):   # empréstimo e pedido atrasado: o tempo já está no motivo                                     # 1 dia ou mais (ou é o único motivo)
        motivos.append(te)
    if base:
        motivos = ["melhora a base, quando sobrar tempo"]
    frase = f"Prioridade {_NA_FRASE[nivel]}" + (" porque " + _juntar(motivos) if motivos else "")
    return {"nota": nota, "nivel": nivel, "rotulo": rotulo, "motivo": frase, "partes": partes}


def _juntar(l: list[str]) -> str:
    return l[0] if len(l) == 1 else ", ".join(l[:-1]) + " e " + l[-1]


REGRA_PRIORIDADE = ("Nota de 0 a 100: gravidade do tipo de trabalho (até 40), tempo parado na etapa (até 20; para de somar em 14 dias), "
                    "se segura a etapa seguinte (até 20) e prazo vencido ou risco público (até 20). Crítico a partir de 60, alto a partir de 45, médio a partir de 25; abaixo disso, baixo.")


# ---------------------------------------------------------------- 2. responsável --------------------------------------------------------
def _tem_tabela(con, nome: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone())


def responsaveis(con, chaves: list[str]) -> dict:
    """{tarefa_id: {"id", "nome", "origem"}}: a atribuição feita no painel; senão o responsável que pedido/empréstimo já tinham."""
    out: dict = {}
    if not chaves:
        return out
    if _tem_tabela(con, "tarefa_responsavel"):
        for i in range(0, len(chaves), 400):
            parte = chaves[i:i + 400]
            for r in con.execute(f"""SELECT t.tarefa_id, u.id, u.nome FROM tarefa_responsavel t JOIN usuario u ON u.id=t.usuario_id
                                     WHERE t.tarefa_id IN ({','.join('?' * len(parte))})""", parte):
                out[r[0]] = {"id": r[1], "nome": r[2], "origem": "painel"}
    ped = [int(k.split(":")[1]) for k in chaves if k.startswith("pedido:") and k not in out and k.split(":")[1].isdigit()]
    if ped:
        for r in con.execute(f"""SELECT s.id, u.id, u.nome FROM solicitacao s JOIN usuario u ON u.id=s.responsavel
                                 WHERE s.id IN ({','.join('?' * len(ped))})""", ped):
            out[f"pedido:{r[0]}"] = {"id": r[1], "nome": r[2], "origem": "pedido"}
    emp = [int(k.split(":")[1]) for k in chaves if k.startswith("emprestimo:") and k not in out and k.split(":")[1].isdigit()]
    if emp:
        for r in con.execute(f"""SELECT e.id, u.id, u.nome FROM emprestimo e JOIN usuario u ON u.id=e.responsavel_id
                                 WHERE e.id IN ({','.join('?' * len(emp))})""", emp):
            out[f"emprestimo:{r[0]}"] = {"id": r[1], "nome": r[2], "origem": "emprestimo"}
    return out


def _relatados_por(con, email: str, erros: list[int]) -> set:
    if not erros or not email:
        return set()
    return {int(r[0]) for r in con.execute(f"""SELECT DISTINCT codigo FROM evento WHERE entidade='erro' AND tipo='criado' AND ator=?
                                              AND codigo IN ({','.join('?' * len(erros))})""", (email, *[str(e) for e in erros]))}


_RE_PROJ = re.compile(r"^F\d{3}-P\d{4}$")


def anotar_fila(con, fila: dict, u: dict) -> dict:
    """Acrescenta à fila da Home (campos novos, opcionais): responsavel, minha, miniatura e, na fila, `abas` (Minha fila · Todos ·
    Críticos · Sem responsável), com a mesma regra da tela. A prioridade já vem de pendencias.fila_da_home."""
    itens = (fila or {}).get("itens") or []
    chaves = [i["adiar"] for i in itens if i.get("adiar")]
    resp = responsaveis(con, chaves)
    erros = [int(i["adiar"].split(":")[1]) for i in itens if str(i.get("adiar") or "").startswith("erro:") and i["adiar"].split(":")[1].isdigit()]
    meus_erros = _relatados_por(con, u.get("email") or "", erros)
    from .rotas_projetos import _SQL_MINIATURA_PROJETO
    cods = sorted({i["codigo"] for i in itens if _RE_PROJ.match(str(i.get("codigo") or ""))})
    mini = {}
    for c in cods[:300]:
        r = con.execute(f"SELECT {_SQL_MINIATURA_PROJETO} FROM projeto p WHERE p.codigo=?", (c,)).fetchone()
        if r and r[0]:
            mini[c] = r[0]
    ab = {"minha": 0, "todos": 0, "criticos": 0, "sem_responsavel": 0}
    for i in itens:
        k = i.get("adiar")
        i["responsavel"] = resp.get(k) if k else None
        relatado = k and k.startswith("erro:") and k.split(":")[1].isdigit() and int(k.split(":")[1]) in meus_erros
        i["minha"] = bool((i["responsavel"] and i["responsavel"]["id"] == u.get("id")) or relatado)
        if i.get("codigo") in mini:
            i["miniatura"] = mini[i["codigo"]]
        if i.get("filtro") == "base":
            continue
        ab["todos"] += 1
        ab["minha"] += i["minha"]
        ab["criticos"] += (i.get("prioridade") or {}).get("nivel") == "critico"
        ab["sem_responsavel"] += not i["responsavel"]
    fila["abas"] = ab
    fila["regra_prioridade"] = REGRA_PRIORIDADE
    return fila


class Responsavel(BaseModel):
    usuario_id: int | None = None
    titulo: str | None = None


_RE_TAREFA = re.compile(r"^(decisao|lote|erro|pedido|emprestimo|alerta|sem_processar):[A-Za-z0-9_.,-]{1,120}$")


@router.get("/painel/pessoas")
def pessoas(u: dict = Depends(auth.exige("operador"))) -> list[dict]:
    """Quem pode receber uma tarefa (ativos que editam). Só id e nome: a tela põe os nomes em data-*."""
    con = connect()
    try:
        return [{"id": r[0], "nome": r[1], "eu": r[0] == u["id"]} for r in
                con.execute("SELECT id, nome FROM usuario WHERE ativo=1 AND papel IN ('operador','admin','master') ORDER BY nome COLLATE NOCASE")]
    finally:
        con.close()


def atribuir_tarefa(con, tarefa_id: str, usuario_id: int | None, u: dict, titulo: str | None = None) -> dict | None:
    """A regra única de responsável (Home e Central de Problemas): operador pega para si ou devolve a que é dele; admin/master atribui a
    qualquer pessoa ativa que edita. Grava o evento 'tarefa_atribuida' / 'tarefa_devolvida'. Levanta HTTPException; não faz commit.
    Devolve o novo responsável ({id, nome, origem}) ou None."""
    admin = u["papel"] in ("admin", "master")
    atual = con.execute("SELECT usuario_id FROM tarefa_responsavel WHERE tarefa_id=?", (tarefa_id,)).fetchone()
    titulo = (titulo or "").strip()[:200] or None
    if usuario_id is None:
        if not atual:
            return None
        if not admin and atual[0] != u["id"]:
            raise HTTPException(403, "Só quem pegou a tarefa (ou um admin) pode devolvê-la")
        con.execute("DELETE FROM tarefa_responsavel WHERE tarefa_id=?", (tarefa_id,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('tarefa',?,'tarefa_devolvida',?,?)",
                    (tarefa_id, u["email"], json.dumps({"titulo": titulo, "antes": atual[0]}, ensure_ascii=False)))
        return None
    if not admin and usuario_id != u["id"]:
        raise HTTPException(403, "Atribuir a outra pessoa é de admin: você pode pegar a tarefa para você")
    if not admin and atual and atual[0] != u["id"]:
        raise HTTPException(409, "Esta tarefa já está com outra pessoa: peça a ela ou a um admin")
    p = con.execute("SELECT id, nome FROM usuario WHERE id=? AND ativo=1 AND papel IN ('operador','admin','master')", (usuario_id,)).fetchone()
    if not p:
        raise HTTPException(400, "Escolha uma pessoa ativa que edita o painel")
    if atual and atual[0] == p[0]:
        return {"id": p[0], "nome": p[1], "origem": "painel"}
    con.execute("""INSERT INTO tarefa_responsavel (tarefa_id, usuario_id, atribuido_por) VALUES (?,?,?)
                   ON CONFLICT(tarefa_id) DO UPDATE SET usuario_id=excluded.usuario_id, atribuido_por=excluded.atribuido_por, atribuido_em=datetime('now')""",
                (tarefa_id, p[0], u["email"]))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('tarefa',?,'tarefa_atribuida',?,?)",
                (tarefa_id, u["email"], json.dumps({"titulo": titulo, "para": p[1], "para_id": p[0], "antes": atual[0] if atual else None}, ensure_ascii=False)))
    return {"id": p[0], "nome": p[1], "origem": "painel"}


@router.put("/painel/tarefas/{tarefa_id}/responsavel")
def atribuir(tarefa_id: str, d: Responsavel, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Atribuir (ou devolver) uma tarefa da fila. Operador: pega para si ou devolve a que é dele. Admin/master: atribui a qualquer pessoa
    que edita. Fica no Histórico de ações (evento 'tarefa_atribuida' / 'tarefa_devolvida')."""
    if not _RE_TAREFA.match(tarefa_id or ""):
        raise HTTPException(400, "Tarefa desconhecida")
    con = connect()
    try:
        r = atribuir_tarefa(con, tarefa_id, d.usuario_id, u, d.titulo)
        con.commit()
        return {"ok": True, "responsavel": r}
    finally:
        con.close()


# ---------------------------------------------------------------- 3. progresso e conquistas (§6) ---------------------------------------
PONTOS_PADRAO = {"folha_conferida": 1, "lote_aprovado": 10, "decisao_resolvida": 5, "problema_resolvido": 20, "problema_critico_resolvido": 30}
PONTOS_ROTULO = {"folha_conferida": ("folha conferida (e que continua conferida)", "folhas conferidas"),
                 "lote_aprovado": ("lote aprovado (e que continua aprovado)", "lotes aprovados"),
                 "decisao_resolvida": ("decisão respondida (descartar não conta)", "decisões respondidas"),
                 "problema_resolvido": ("problema corrigido com a frase do que foi feito", "problemas corrigidos"),
                 "problema_critico_resolvido": ("problema que bloqueava, corrigido com a frase do que foi feito", "problemas que bloqueavam, corrigidos")}
NIVEIS_XP = ((0, "Primeiros passos"), (100, "Olhar atento"), (300, "Mão firme"), (700, "Guardião do Acervo"), (1600, "Memória viva"), (3000, "Referência do acervo"))
META_PADRAO = 100


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return r[0] if r and r[0] not in (None, "") else padrao


def pontos(con) -> dict:
    """A tabela de pontos (configuração `jogo.pontos`, JSON; o que faltar ou vier inválido usa o padrão)."""
    out = dict(PONTOS_PADRAO)
    try:
        cfg = json.loads(_cfg(con, "jogo.pontos", "{}") or "{}")
        for k, v in (cfg or {}).items():
            if k in out and isinstance(v, (int, float)) and 0 <= v <= 1000:
                out[k] = int(v)
    except (ValueError, TypeError):
        pass
    return out


def jogo_ligado(con) -> bool:
    return _cfg(con, "jogo.ligado", "1").strip() not in ("0", "false", "nao", "não")


def meta_semana(con) -> int:
    try:
        v = int(float(_cfg(con, "meta.semana", str(META_PADRAO))))
        return v if v > 0 else META_PADRAO
    except ValueError:
        return META_PADRAO


def _sp_agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)


def inicio_semana_utc(agora_sp: datetime | None = None) -> str:
    """Segunda-feira 00:00 de São Paulo, em UTC (o banco grava datetime('now') em UTC)."""
    sp = agora_sp or _sp_agora()
    seg = datetime(sp.year, sp.month, sp.day) - timedelta(days=sp.weekday())
    return (seg + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


def eventos_validados(con, desde: str | None = None) -> list[dict]:
    """Os eventos que contam ponto, tirados do ESTADO ATUAL (desfez = sumiu). Cada um: tipo, email, quando, ref.
    Só conta quem é usuário do painel (e-mail de usuário): o que o CAMP Vision, o site ou uma regra automática fizeram não conta."""
    emails = {r[0] for r in con.execute("SELECT email FROM usuario WHERE email IS NOT NULL")}
    w = " AND {col} >= ?" if desde else ""
    p = (desde,) if desde else ()
    out = []
    for r in con.execute("SELECT codigo, revisado_por, revisado_em FROM item WHERE revisao IN ('conferida','corrigida') AND revisado_em IS NOT NULL"
                         + w.format(col="revisado_em"), p):
        if r[1] in emails:
            out.append({"tipo": "folha_conferida", "email": r[1], "quando": r[2], "ref": r[0]})
    for r in con.execute("SELECT id, aprovado_por, aprovado_em FROM lista_processamento WHERE aprovado_em IS NOT NULL AND descartado_em IS NULL"
                         + w.format(col="aprovado_em"), p):
        if r[1] in emails:
            out.append({"tipo": "lote_aprovado", "email": r[1], "quando": r[2], "ref": f"lote:{r[0]}"})
    for r in con.execute("SELECT id, resolvida_por, resolvida_em FROM decisao WHERE situacao='resolvida' AND COALESCE(escolha,'')<>'descartar'"
                         " AND resolvida_em IS NOT NULL" + w.format(col="resolvida_em"), p):
        if r[1] in emails:
            out.append({"tipo": "decisao_resolvida", "email": r[1], "quando": r[2], "ref": f"decisao:{r[0]}"})
    # problema: corrigido (não "ignorado"), com a frase do que foi feito; quem conta é quem o marcou como corrigido (o último evento)
    for r in con.execute("SELECT id, gravidade, resolvido_em FROM erro WHERE situacao='corrigido' AND LENGTH(TRIM(COALESCE(resolucao,'')))>=3"
                         " AND resolvido_em IS NOT NULL" + w.format(col="resolvido_em"), p):
        # CAMP-PROB-UX: a Central de Problemas resolve pelo evento 'fase' (para "resolvido"); com revisão, o crédito é de quem resolveu
        ev = con.execute("""SELECT ator, detalhe FROM evento WHERE entidade='erro' AND codigo=? AND ((tipo='editado' AND detalhe LIKE '%"corrigido"%')
                            OR (tipo='fase' AND detalhe LIKE '%"para": "resolvido"%')) ORDER BY id DESC LIMIT 1""", (str(r[0]),)).fetchone()
        quem = ev[0] if ev else None
        if ev and ev[1] and '"credito"' in ev[1]:
            try:
                quem = json.loads(ev[1]).get("credito") or quem
            except ValueError:
                pass
        if quem in emails:
            out.append({"tipo": "problema_critico_resolvido" if r[1] == "bloqueia" else "problema_resolvido", "email": quem, "quando": r[2], "ref": f"erro:{r[0]}"})
    return out


def nivel_xp(xp: int) -> dict:
    i = max(k for k, (corte, _) in enumerate(NIVEIS_XP) if xp >= corte)
    prox = NIVEIS_XP[i + 1][0] if i + 1 < len(NIVEIS_XP) else None
    return {"nivel": i + 1, "nome": NIVEIS_XP[i][1], "xp": xp, "de": NIVEIS_XP[i][0], "ate": prox}


# conquistas: marcos pessoais, verificáveis, que não comparam pessoas (id, rótulo, tipo contado, quantidade)
CONQUISTAS = (("folha_1", "Primeira folha conferida", "folha_conferida", 1), ("folha_10", "10 folhas conferidas", "folha_conferida", 10),
              ("folha_100", "100 folhas conferidas", "folha_conferida", 100), ("folha_1000", "1.000 folhas conferidas", "folha_conferida", 1000),
              ("lote_1", "1 lote aprovado", "lote_aprovado", 1), ("lote_10", "10 lotes aprovados", "lote_aprovado", 10),
              ("decisao_1", "Primeira decisão respondida", "decisao_resolvida", 1),
              ("problema_1", "Problema corrigido com evidência", "problema_resolvido", 1),
              ("critico_1", "Problema que bloqueava, resolvido com evidência", "problema_critico_resolvido", 1))


def _dias_seguidos(dias: set) -> int:
    """Dias corridos seguidos com algum evento validado, terminando hoje ou ontem (fato neutro: não some nada se parar)."""
    hoje = _sp_agora().date()
    d = hoje if hoje.isoformat() in dias else hoje - timedelta(days=1)
    n = 0
    while d.isoformat() in dias:
        n += 1
        d -= timedelta(days=1)
    return n


def _dia_sp(ts: str) -> str:
    try:
        return (datetime.strptime(str(ts)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S") - timedelta(hours=3)).date().isoformat()
    except ValueError:
        return ""


def progresso(con, u: dict, ocultar: bool | None = None) -> dict:
    """Meta coletiva da semana, nível e conquistas da pessoa (se ela não ocultou) e, só com `jogo.ranking_equipe`=1, o quadro da equipe."""
    tab = pontos(con)
    desde = inicio_semana_utc()
    todos = eventos_validados(con)
    semana = [e for e in todos if str(e["quando"]) >= desde]
    feito = sum(tab[e["tipo"]] for e in semana)
    meta = meta_semana(con)
    por_tipo = {k: sum(1 for e in semana if e["tipo"] == k) for k in tab}
    out = {"ligado": jogo_ligado(con), "pontos": tab, "pontos_rotulo": {k: v[0] for k, v in PONTOS_ROTULO.items()},
           "semana": {"desde": desde, "meta": meta, "feito": feito, "pct": min(100, round(100 * feito / meta)) if meta else 0,
                      "acoes": len(semana), "por_tipo": por_tipo,
                      "por_tipo_rotulo": {k: PONTOS_ROTULO[k][1] for k in tab}},
           "regra": "Contam só ações validadas e que continuam valendo: se alguém desfaz (reabre a revisão, reabre o problema, "
                    "desaprova o lote), o ponto some. Descartar decisão e marcar \"não era problema\" não contam."}
    if not out["ligado"]:
        return {"ligado": False}
    if ocultar is None:
        r = con.execute("SELECT valor FROM usuario_preferencia WHERE usuario_id=? AND chave='conquistas.ocultar'", (u.get("id"),)).fetchone()
        ocultar = bool(r and r[0] == "1")
    out["oculto"] = ocultar
    if u.get("papel") != "leitura" and not ocultar:
        meus = [e for e in todos if e["email"] == u.get("email")]
        xp = sum(tab[e["tipo"]] for e in meus)
        cont = {k: sum(1 for e in meus if e["tipo"] == k) for k in tab}
        ganhas = [{"id": i, "rotulo": r} for i, r, t, n in CONQUISTAS if cont.get(t, 0) >= n]
        prox = next(({"id": i, "rotulo": r, "feito": cont.get(t, 0), "de": n} for i, r, t, n in CONQUISTAS if cont.get(t, 0) < n and cont.get(t, 0) > 0), None)
        dias = {_dia_sp(e["quando"]) for e in meus}
        dias_semana = {_dia_sp(e["quando"]) for e in meus if str(e["quando"]) >= desde}
        if len(dias_semana) >= 3:
            ganhas.append({"id": "semana_consistente", "rotulo": "Semana consistente (3 dias com trabalho validado)"})
        out["eu"] = {**nivel_xp(xp), "xp_semana": sum(tab[e["tipo"]] for e in meus if str(e["quando"]) >= desde), "contagens": cont,
                     "conquistas": ganhas, "proxima": prox, "dias_seguidos": _dias_seguidos(dias)}
    if _cfg(con, "jogo.ranking_equipe", "0").strip() == "1" and u.get("papel") != "leitura":
        nomes = {r[0]: r[1] for r in con.execute("SELECT email, nome FROM usuario WHERE email IS NOT NULL")}
        soma: dict = {}
        for e in semana:
            soma[e["email"]] = soma.get(e["email"], 0) + tab[e["tipo"]]
        out["equipe"] = [{"nome": nomes.get(k, k), "pontos": v} for k, v in sorted(soma.items(), key=lambda kv: (-kv[1], nomes.get(kv[0], kv[0])))]
    return out


@router.get("/painel/progresso")
def ver_progresso(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return progresso(con, u)
    finally:
        con.close()


class Meta(BaseModel):
    valor: int


@router.put("/painel/meta")
def mudar_meta(d: Meta, u: dict = Depends(auth.exige("admin"))) -> dict:
    """A meta coletiva da semana (em pontos validados). Admin muda; fica no Histórico como qualquer configuração."""
    if not 1 <= int(d.valor) <= 100000:
        raise HTTPException(400, "A meta vai de 1 a 100.000 pontos")
    con = connect()
    try:
        antes = _cfg(con, "meta.semana", str(META_PADRAO))
        con.execute("""INSERT INTO configuracao (chave, valor, descricao) VALUES ('meta.semana', ?, 'Meta coletiva da semana na Home (pontos validados)')
                       ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, atualizado_em=datetime('now'), atualizado_por=?""", (str(int(d.valor)), u["email"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config','meta.semana','alterada',?,?)",
                    (u["email"], json.dumps({"antes": {"valor": antes}, "depois": {"valor": str(int(d.valor))}}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "meta": int(d.valor)}
    finally:
        con.close()
