"""Central de Problemas (CAMP-PROB-UX, 22/11/2026; documento de produto de Rafael, "Redesenho da Central de Problemas" 1.0).

A tabela `erro` continua a mesma e a coluna `situacao` continua sendo a regra de quem já lê (menu, Precisa de você, publicação,
relatórios, fechamentos automáticos). Aqui ficam, por cima dela:

- **Fase do trabalho** (`fase`): Novo → Em triagem → Em análise → Aguardando revisão → Resolvido, com Aguardando informação, Devolvido,
  Reaberto e Duplicado/Inválido. Cada fase cai em UMA situação antiga (FASE_SITUACAO); problema antigo (fase NULL) ou mexido por uma rota
  antiga tem a fase deduzida da situação (`fase_efetiva`), por isso as duas nunca se contradizem.
- **Transições e campos obrigatórios** (`TRANSICOES`, `requisitos`): resolver exige conclusão e evidência ou justificativa (autoria e
  crédito exigem fonte); reabrir e invalidar exigem justificativa; duplicado exige a referência. Quem e quando ficam gravados.
- **Revisão por outra pessoa** (`problemas.revisao_outra_pessoa`, desligada por padrão) para os tipos de `problemas.tipos_revisao`.
- **Prioridade explicável** (`prioridade`): a MESMA nota 0–100 da Home (`home_trabalho.prioridade`: gravidade, tempo parado com teto,
  bloqueio, risco público), com o motivo em palavras, mais o impacto documental do tipo ("autoria conflitante") como desempate e a marca
  "resolução rápida".
- **Responsável**: a `tarefa_responsavel` da Home (chave `erro:<id>`) e a mesma regra (`home_trabalho.atribuir_tarefa`).
- **Reconhecimento**: UM sistema de pontos, o da Home (`home_trabalho.eventos_validados`, recontado do estado: reabriu, o ponto some);
  aqui só se acrescentam conquistas de qualidade, sem pontos. Nada disso muda o estado real de um problema.
Só lê e grava o banco (nunca o QNAP)."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api/problemas", tags=["problemas"])

ATOR_SISTEMA = "painel (automático)"
FASES = ("novo", "triagem", "em_analise", "aguardando_informacao", "aguardando_revisao", "devolvido", "reaberto",
         "resolvido", "duplicado", "invalido")
FASE_SITUACAO = {"novo": "aberto", "triagem": "aberto", "reaberto": "aberto",
                 "em_analise": "em_correcao", "aguardando_informacao": "em_correcao", "aguardando_revisao": "em_correcao", "devolvido": "em_correcao",
                 "resolvido": "corrigido", "duplicado": "ignorado", "invalido": "ignorado"}
ROTULO_FASE = {"novo": "Novo", "triagem": "Em triagem", "em_analise": "Em análise", "aguardando_informacao": "Aguardando informação",
               "aguardando_revisao": "Aguardando revisão", "devolvido": "Devolvido", "reaberto": "Reaberto", "resolvido": "Resolvido",
               "duplicado": "Duplicado", "invalido": "Inválido"}
FASES_ABERTAS = tuple(f for f in FASES if FASE_SITUACAO[f] in ("aberto", "em_correcao"))
FASES_FECHADAS = ("resolvido", "duplicado", "invalido")
FASES_EM_ANALISE = ("triagem", "em_analise", "aguardando_informacao", "devolvido")
_SEGUE_NOVO = {"triagem", "em_analise", "aguardando_informacao", "aguardando_revisao", "resolvido", "duplicado", "invalido"}
TRANSICOES = {
    "novo": _SEGUE_NOVO, "reaberto": _SEGUE_NOVO,
    "triagem": _SEGUE_NOVO - {"triagem"},
    "em_analise": (_SEGUE_NOVO - {"em_analise"}),
    "aguardando_informacao": {"em_analise", "duplicado", "invalido"},
    "aguardando_revisao": {"resolvido", "devolvido"},
    "devolvido": {"em_analise", "aguardando_revisao", "resolvido", "duplicado", "invalido"},
    "resolvido": {"reaberto"}, "duplicado": {"reaberto"}, "invalido": {"reaberto"},
}
SEVERIDADE = {"bloqueia": ("critico", "Crítico"), "corrigir": ("medio", "Médio"), "aviso": ("baixo", "Baixo")}
ROTULO_TIPO = {"autoria_divergente": "Autoria", "projeto_errado": "Folha de outro projeto", "duplicata": "Duplicata", "orientacao": "Orientação",
               "espelhado": "Digitalizado pelo verso", "codigo": "Código", "metadado": "Metadados", "credito": "Crédito",
               "arquivo_corrompido": "Arquivo danificado", "outro": "Outro"}
# o título curto, na forma "o que está errado" (a lista mostra este título; a descrição completa fica no painel)
TITULO_TIPO = {"autoria_divergente": "Autoria não confirmada", "projeto_errado": "Folha pode ser de outro projeto", "duplicata": "Registro duplicado no acervo",
               "orientacao": "Folha virada", "espelhado": "Folha digitalizada pelo verso", "codigo": "Código errado", "metadado": "Informação errada ou faltando",
               "credito": "Crédito errado ou faltando", "arquivo_corrompido": "Arquivo da imagem danificado", "outro": "Problema relatado"}
TIPOS_COM_FONTE = ("autoria_divergente", "credito")      # concluir exige fonte/evidência (não basta justificativa); nunca inventar fonte
TIPOS_RAPIDOS = ("orientacao", "espelhado")
EVIDENCIA_TIPOS = ("texto", "link", "folha", "justificativa")
SQL_SITUACAO_NORM = "(CASE situacao WHEN 'fechado' THEN 'corrigido' ELSE situacao END)"
_SIT_DA_FASE = "(CASE fase " + " ".join(f"WHEN '{f}' THEN '{s}'" for f, s in FASE_SITUACAO.items()) + " END)"
FASE_SQL = (f"(CASE WHEN fase IS NOT NULL AND {_SIT_DA_FASE} = {SQL_SITUACAO_NORM} THEN fase "
            "WHEN situacao='aberto' THEN 'novo' WHEN situacao='em_correcao' THEN 'em_analise' "
            "WHEN situacao='ignorado' THEN (CASE WHEN duplicado_de IS NOT NULL OR resolucao LIKE 'Mensagem repetida%' THEN 'duplicado' ELSE 'invalido' END) "
            "ELSE 'resolvido' END)")
SISTEMA_SQL = ("(fechado_por = 'painel (automático)' OR resolucao LIKE 'Resolvido sozinho:%' OR resolucao LIKE 'Resolvido na conferência:%' "
               "OR resolucao LIKE 'Limpeza criteriosa:%' OR (fechado_por IS NULL AND resolucao LIKE 'Mensagem repetida%'))")


def fase_efetiva(situacao: str | None, fase: str | None, duplicado_de=None, resolucao: str | None = None) -> str:
    sit = "corrigido" if situacao == "fechado" else (situacao or "aberto")
    if fase in FASE_SITUACAO and FASE_SITUACAO[fase] == sit:
        return fase
    if sit == "aberto":
        return "novo"
    if sit == "em_correcao":
        return "em_analise"
    if sit == "ignorado":
        return "duplicado" if duplicado_de or str(resolucao or "").startswith("Mensagem repetida") else "invalido"
    return "resolvido"


def cfg(con, chave: str, padrao: str = "") -> str:
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    except Exception:  # noqa: BLE001
        return padrao
    return r[0] if r and r[0] is not None else padrao


def revisao_ligada(con) -> bool:
    return cfg(con, "problemas.revisao_outra_pessoa", "0").strip() == "1"


def tipos_revisao(con) -> set[str]:
    return {t.strip() for t in cfg(con, "problemas.tipos_revisao", "autoria_divergente,credito,projeto_errado").split(",") if t.strip()}


def precisa_revisao(con, categoria: str) -> bool:
    return revisao_ligada(con) and categoria in tipos_revisao(con)


def _dias(ts) -> int:
    s = str(ts or "").replace("T", " ")[:19]
    try:
        d = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return 0
    return max(0, (datetime.now(timezone.utc) - d).days)


# ---------------- prioridade explicável ----------------
IMPACTO = {"autoria_divergente": (25, "autoria conflitante"), "credito": (20, "crédito em dúvida"), "projeto_errado": (20, "folha pode ser de outro projeto"),
           "codigo": (15, "código errado"), "arquivo_corrompido": (15, "arquivo danificado"), "duplicata": (10, "possível duplicata"),
           "metadado": (10, "informação errada ou faltando"), "orientacao": (3, "folha virada"), "espelhado": (3, "folha pelo verso"), "outro": (5, "problema relatado")}


def prioridade(e: dict, no_ar: bool = False) -> dict:
    """A nota da Home (home_trabalho.prioridade, 0–100, com a frase do porquê) para um problema, mais o impacto documental do tipo e a
    origem (visitante do site) na frase e no desempate. Pura (sem banco): a tela e os testes usam a mesma conta."""
    from .home_trabalho import prioridade as nota_home
    fase = e.get("fase") or "novo"
    desde = e.get("enviado_revisao_em") if fase == "aguardando_revisao" and e.get("enviado_revisao_em") else e.get("criado_em")
    tipo = "erro" if e.get("gravidade") == "bloqueia" else ("aviso" if e.get("gravidade") == "aviso" else "problema")
    item = {"acao": {"tipo": tipo}, "espera_h": _horas(desde), "urgente": "está no site" if no_ar and e.get("gravidade") == "bloqueia" else ""}
    h = nota_home(item)
    imp = IMPACTO.get(e.get("categoria"), IMPACTO["outro"])
    extras = [imp[1]]
    if e.get("origem") == "site":
        extras.append("avisado por visitante do site")
    if fase == "aguardando_revisao":
        extras.append("aguardando revisão")
    elif fase == "devolvido":
        extras.append("devolvido pela revisão")
    razao = h["motivo"] + " · " + " · ".join(extras)
    return {"nota": h["nota"], "nivel": h["nivel"], "rotulo": h["rotulo"], "razao": razao, "motivos": [h["motivo"]] + extras,
            "partes": h["partes"], "impacto": imp[0] + (15 if e.get("origem") == "site" else 0), "rapida": e.get("categoria") in TIPOS_RAPIDOS}


def _horas(ts) -> float | None:
    s_ = str(ts or "").replace("T", " ")[:19]
    try:
        d = datetime.strptime(s_, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 3600)


# ---------------- listagem ----------------
def _nomes(con) -> dict:
    try:
        return {r[0]: r[1] for r in con.execute("SELECT email, nome FROM usuario WHERE email IS NOT NULL")}
    except Exception:  # noqa: BLE001
        return {}


def enriquecer(con, rows, usuario: dict | None = None) -> list[dict]:
    """Os campos da Central (opcionais) por cima de problemas.enriquecer: fase, severidade, título curto, tipo, responsável (nome),
    prioridade (nota, razão), idade, onde (fundo > projeto > folha), CTA."""
    from . import problemas
    from .bloqueio_folha import frase_erro
    base = problemas.enriquecer(con, rows)
    projs = {x["projeto_codigo"] for x in base if x.get("projeto_codigo")}
    no_ar = set()
    for i in range(0, len(projs), 400):
        parte = list(projs)[i:i + 400]
        no_ar |= {r[0] for r in con.execute(f"SELECT codigo FROM projeto WHERE status_site='no_ar' AND codigo IN ({','.join('?' * len(parte))})", parte)}
    from .home_trabalho import responsaveis
    resp = responsaveis(con, [f"erro:{x['id']}" for x in base])
    eu = (usuario or {}).get("email")
    out = []
    for x in base:
        f = fase_efetiva(x.get("situacao"), x.get("fase"), x.get("duplicado_de"), x.get("resolucao"))
        x["fase"] = f
        x["fase_rotulo"] = ROTULO_FASE[f]
        sev = SEVERIDADE.get(x.get("gravidade"), SEVERIDADE["corrigir"])
        x["severidade"], x["severidade_rotulo"] = sev
        x["tipo_rotulo"] = ROTULO_TIPO.get(x.get("categoria"), "Outro")
        x["titulo"] = ("Folha retirada pelo CAMP Vision" if x.get("tipo") == "retirada" else
                       "Folha recusada na importação" if x.get("tipo") == "recusada" else TITULO_TIPO.get(x.get("categoria"), "Problema relatado"))
        x["frase_bloqueio"] = frase_erro(x)                  # CAMP-BLOQUEIO (campo novo, opcional): o que bloqueia, em frase
        r_ = resp.get(f"erro:{x['id']}")
        x["responsavel_id"], x["responsavel_nome"] = (r_["id"], r_["nome"]) if r_ else (None, None)
        x["idade_dias"] = _dias(x.get("criado_em"))
        x["aberto"] = f in FASES_ABERTAS
        x["prioridade"] = prioridade(x, (x.get("projeto_codigo") in no_ar)) if x["aberto"] else None
        x["revisar_eu"] = bool(f == "aguardando_revisao" and eu and x.get("enviado_revisao_por") != eu)
        x["cta"] = ("Revisar" if f == "aguardando_revisao" else "Continuar" if f in ("em_analise", "aguardando_informacao", "devolvido", "triagem") else
                    "Analisar" if x["aberto"] else "Ver")
        x["resolvido_pelo_sistema"] = (not x["aberto"]) and (x.get("fechado_por") == ATOR_SISTEMA or str(x.get("resolucao") or "").startswith(("Resolvido sozinho:", "Resolvido na conferência:", "Limpeza criteriosa:")))
        out.append(x)
    return out


IDADES = {"0-7": (0, 7), "8-30": (8, 30), "31-90": (31, 90), "90+": (91, 100000)}


class Filtros(BaseModel):
    aba: str = "prioridades"          # prioridades · minha_fila · todos · concluidos
    q: str | None = None
    fase: str | None = None           # uma ou mais, separadas por vírgula
    gravidade: str | None = None
    categoria: str | None = None
    origem: str | None = None
    responsavel: str | None = None    # eu · ninguem · id da pessoa
    fundo: str | None = None
    projeto: str | None = None
    de: str | None = None
    ate: str | None = None
    idade: str | None = None          # 0-7 · 8-30 · 31-90 · 90+
    chip: str | None = None           # critico · sem_responsavel · minha_revisao · antigos · rapidos · avisos · talvez (vírgula combina)


def _where(f: Filtros, u: dict, escondidos: list[int], com_aba: bool = True) -> tuple[list[str], list]:
    from .contagens import SEM_CONVIDADO_ERRO
    from .rotas_operacao import CATS, GRAV, ORIGENS_MANUAIS
    w, p = [SEM_CONVIDADO_ERRO], []
    aba = f.aba if com_aba else "todos_qualquer"
    if aba in ("prioridades", "minha_fila", "todos"):
        w.append("situacao IN ('aberto','em_correcao')")
        if escondidos:
            w.append(f"id NOT IN ({','.join('?' * len(escondidos))})"); p += escondidos
    if aba == "prioridades":
        w.append("gravidade<>'aviso'")
    elif aba == "minha_fila":
        # a mesma "Minha fila" da Home: atribuído a mim ou relatado por mim
        w.append("(EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id AND tr.usuario_id=?) OR EXISTS (SELECT 1 FROM evento ev WHERE ev.entidade='erro' AND ev.tipo='criado' AND ev.codigo=CAST(erro.id AS TEXT) AND ev.ator=?))"); p += [u.get("id") or 0, u.get("email") or ""]
    elif aba == "concluidos":
        w.append("situacao IN ('corrigido','fechado','ignorado')")
    elif aba not in ("todos", "todos_qualquer"):
        raise HTTPException(400, f"Aba inválida: {aba}")
    if f.fase:
        fs = [x.strip() for x in f.fase.split(",") if x.strip()]
        if any(x not in FASES for x in fs):
            raise HTTPException(400, "Fase inválida")
        w.append(f"{FASE_SQL} IN ({','.join('?' * len(fs))})"); p += fs
    for col, v, ok_ in (("gravidade", f.gravidade, GRAV), ("categoria", f.categoria, CATS), ("origem", f.origem, ("campvision",) + ORIGENS_MANUAIS)):
        if v:
            vs = [x.strip() for x in v.split(",") if x.strip()]
            if any(x not in ok_ for x in vs):
                raise HTTPException(400, f"Filtro inválido: {v}")
            w.append(f"{col} IN ({','.join('?' * len(vs))})"); p += vs
    if f.responsavel:
        if f.responsavel == "ninguem":
            w.append("NOT EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id)")
        elif f.responsavel == "eu":
            w.append("EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id AND tr.usuario_id=?)"); p.append(u.get("id") or 0)
        elif f.responsavel.strip().isdigit():
            w.append("EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id AND tr.usuario_id=?)"); p.append(int(f.responsavel.strip()))
        else:
            raise HTTPException(400, "Responsável inválido")
    if f.fundo and re.fullmatch(r"F\d{3}", f.fundo.strip().upper()):
        w.append("substr(codigo,1,4)=?"); p.append(f.fundo.strip().upper())
    if f.projeto and f.projeto.strip():
        pr = f.projeto.strip().upper()
        w.append("(codigo=? OR codigo LIKE ? || '-%')"); p += [pr, pr]
    if f.de and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.de):
        w.append("criado_em >= ?"); p.append(f.de)
    if f.ate and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.ate):
        w.append("criado_em < date(?, '+1 day')"); p.append(f.ate)
    if f.idade:
        if f.idade not in IDADES:
            raise HTTPException(400, "Faixa de idade inválida")
        a, b = IDADES[f.idade]
        w.append("julianday('now') - julianday(criado_em) >= ? AND julianday('now') - julianday(criado_em) < ?"); p += [a, b + 1]
    for chip in [c.strip() for c in (f.chip or "").split(",") if c.strip()]:
        if chip == "critico":
            w.append("gravidade='bloqueia'")
        elif chip == "sem_responsavel":
            w.append("NOT EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id)")
        elif chip == "minha_revisao":
            w.append(f"{FASE_SQL}='aguardando_revisao' AND COALESCE(enviado_revisao_por,'')<>?"); p.append(u.get("email") or "")
        elif chip == "antigos":
            w.append("julianday('now') - julianday(criado_em) >= 30")
        elif chip == "rapidos":
            w.append(f"categoria IN ({','.join('?' * len(TIPOS_RAPIDOS))})"); p += list(TIPOS_RAPIDOS)
        elif chip == "avisos":
            w.append("gravidade='aviso'")
        elif chip == "talvez":
            pass                          # pede a explicação (problemas.py): filtrado depois
        else:
            raise HTTPException(400, f"Filtro rápido inválido: {chip}")
    if f.q and f.q.strip():
        t = f.q.strip()
        num = re.fullmatch(r"#?(\d{1,9})", t)
        tl = "%" + t.lower() + "%"
        cond = ("lower(codigo) LIKE ? OR lower(descricao) LIKE ? OR lower(coalesce(relatado_por,'')) LIKE ? OR lower(coalesce(resolucao,'')) LIKE ? "
                "OR EXISTS (SELECT 1 FROM tarefa_responsavel tr JOIN usuario uu ON uu.id=tr.usuario_id WHERE tr.tarefa_id='erro:'||erro.id AND lower(uu.nome) LIKE ?) "
                "OR EXISTS (SELECT 1 FROM projeto pj WHERE pj.codigo=substr(erro.codigo,1,10) AND (lower(pj.titulo) LIKE ? OR lower(coalesce(pj.cidade,'')) LIKE ?)) "
                "OR EXISTS (SELECT 1 FROM fundo fd WHERE fd.codigo=substr(erro.codigo,1,4) AND (lower(fd.titulo) LIKE ? OR lower(coalesce(fd.sigla,'')) LIKE ?)) "
                "OR EXISTS (SELECT 1 FROM erro_evidencia ev WHERE ev.erro_id=erro.id AND lower(ev.valor) LIKE ?)")
        pp = [tl] * 10
        if num:
            cond = "id=? OR " + cond; pp = [int(num.group(1))] + pp
        w.append("(" + cond + ")"); p += pp
    return w, p


def _escondidos(con, u: dict) -> list[int]:
    from .rotas_operacao import _escondidos as esc
    return esc(con, u.get("id"))


ORDENS = {"prioridade", "recentes", "antigos", "atualizados"}


def listar(con, f: Filtros, u: dict, ordem: str = "prioridade", pagina: int = 1, por_pagina: int = 25, agrupar: bool = False, rapido: bool = False) -> dict:
    """`agrupar` (CAMP-PROB-RAPIDO): o mesmo projeto + o mesmo tipo viram UMA linha (a página conta linhas; `total` continua contando
    problemas). `rapido`: as decisões rápidas da linha (problemas_rapido.anotar); o CSV não pede (só a tela)."""
    if ordem not in ORDENS:
        raise HTTPException(400, "Ordem inválida")
    por_pagina = max(5, min(200, por_pagina)); pagina = max(1, pagina)
    w, p = _where(f, u, _escondidos(con, u))
    sql_w = " WHERE " + " AND ".join(w)
    chips = {c.strip() for c in (f.chip or "").split(",")}
    if f.aba == "concluidos" and ordem == "prioridade":
        ordem = "recentes"
    agrupar = agrupar and f.aba != "concluidos"
    pyth = ordem == "prioridade" or "talvez" in chips or agrupar
    if not pyth:
        o = {"recentes": "COALESCE(resolvido_em, criado_em) DESC, id DESC" if f.aba == "concluidos" else "criado_em DESC, id DESC",
             "antigos": "criado_em ASC, id ASC", "atualizados": "COALESCE(fase_em, resolvido_em, criado_em) DESC, id DESC"}[ordem]
        total = con.execute("SELECT COUNT(*) FROM erro" + sql_w, p).fetchone()[0]
        rows = con.execute(f"SELECT * FROM erro{sql_w} ORDER BY {o} LIMIT ? OFFSET ?", p + [por_pagina, (pagina - 1) * por_pagina]).fetchall()
        itens = enriquecer(con, rows, u)
    else:
        todos = enriquecer(con, con.execute("SELECT * FROM erro" + sql_w, p).fetchall(), u)
        if "talvez" in chips:
            todos = [x for x in todos if x.get("resolvido_sozinho")]
        if ordem == "prioridade":
            todos.sort(key=lambda x: (-((x.get("prioridade") or {}).get("nota") or 0), -((x.get("prioridade") or {}).get("impacto") or 0), x.get("criado_em") or "", x["id"]))
        else:
            todos.sort(key=lambda x: x.get("criado_em") or "", reverse=ordem != "antigos")
        total = len(todos)
        if agrupar:
            from .problemas_rapido import _Sugestoes, agrupar_linhas, anotar, rapido_do_grupo
            linhas = agrupar_linhas(todos)
            itens = linhas[(pagina - 1) * por_pagina: pagina * por_pagina]
            soltos = [x for x in itens if not x.get("grupo")]
            membros = [m for g in itens if g.get("grupo") for m in g["membros"]]
            sug = _Sugestoes(con)
            anotar(con, soltos + membros, u, sug)
            for g in itens:
                if g.get("grupo"):
                    rapido_do_grupo(g, u)
            return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "paginas": max(1, -(-len(linhas) // por_pagina)), "ordem": ordem,
                    "itens": itens, "agrupado": True, "linhas": len(linhas), "grupos": sum(1 for x in linhas if x.get("grupo"))}
        itens = todos[(pagina - 1) * por_pagina: pagina * por_pagina]
    if rapido:
        from .problemas_rapido import anotar
        anotar(con, itens, u)
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "paginas": max(1, -(-total // por_pagina)), "ordem": ordem, "itens": itens}


def _conta(con, w: list[str], p: list, extra: str | None = None, ep: list | None = None) -> int:
    ww = w + ([extra] if extra else [])
    return con.execute("SELECT COUNT(*) FROM erro WHERE " + " AND ".join(ww), p + (ep or [])).fetchone()[0]


def resumo(con, f: Filtros, u: dict) -> dict:
    """Os cartões (sem filtro: o retrato do acervo) e as contagens das abas e dos filtros rápidos (com os filtros da tela).
    Cada número é um COUNT de linhas da tabela erro: um problema conta uma vez, nunca por evento."""
    from .contagens import ERROS_ABERTOS, agora_iso
    esc = _escondidos(con, u)
    w0, p0 = [ERROS_ABERTOS], []
    if esc:
        w0.append(f"id NOT IN ({','.join('?' * len(esc))})"); p0 += esc
    cartoes = {
        "em_aberto": _conta(con, w0, p0),
        "pedem_acao": _conta(con, w0, p0, "gravidade<>'aviso'"),
        "avisos": _conta(con, w0, p0, "gravidade='aviso'"),
        "criticos": _conta(con, w0, p0, "gravidade='bloqueia'"),
        "em_analise": _conta(con, w0, p0, f"{FASE_SQL} IN ({','.join('?' * len(FASES_EM_ANALISE))})", list(FASES_EM_ANALISE)),
        "aguardando_revisao": _conta(con, w0, p0, f"{FASE_SQL}='aguardando_revisao'"),
        "sem_responsavel": _conta(con, w0, p0, "NOT EXISTS (SELECT 1 FROM tarefa_responsavel tr WHERE tr.tarefa_id='erro:'||erro.id)"),
    }
    from .contagens import SEM_CONVIDADO_ERRO
    fech = [SEM_CONVIDADO_ERRO, "situacao IN ('corrigido','fechado')"]
    cartoes["resolvidos"] = {
        "hoje": _conta(con, fech, [], "resolvido_em >= date('now')"),
        "semana": _conta(con, fech, [], "resolvido_em >= date('now','-6 days')"),
        "mes": _conta(con, fech, [], "resolvido_em >= date('now','-29 days')"),
    }
    cartoes["resolvidos_sistema_mes"] = _conta(con, fech, [], f"resolvido_em >= date('now','-29 days') AND {SISTEMA_SQL}")
    abas = {}
    for a in ("prioridades", "minha_fila", "todos", "concluidos"):
        ff = f.model_copy(update={"aba": a, "chip": None})
        w, p = _where(ff, u, esc)
        abas[a] = _conta(con, w, p)
    chips = {}
    ativos = [x.strip() for x in (f.chip or "").split(",") if x.strip() and x.strip() != "talvez"]
    base = f.model_copy(update={"chip": ",".join(ativos) or None})
    for c in ("critico", "sem_responsavel", "minha_revisao", "antigos", "rapidos", "avisos"):   # quantos ficam se este filtro rápido entrar junto dos ativos
        w, p = _where(base.model_copy(update={"chip": ",".join(dict.fromkeys(ativos + [c]))}), u, esc)
        chips[c] = _conta(con, w, p)
    w, p = _where(base, u, esc)
    if base.aba != "concluidos":
        from . import problemas
        chips["talvez"] = sum(1 for x in problemas.enriquecer(con, con.execute("SELECT * FROM erro WHERE " + " AND ".join(w), p).fetchall()) if x.get("resolvido_sozinho"))
    return {"cartoes": cartoes, "abas": abas, "chips": chips, "medido_em": agora_iso(),
            "revisao_outra_pessoa": revisao_ligada(con), "tipos_revisao": sorted(tipos_revisao(con))}


def graficos(con) -> dict:
    """"Problemas por tipo" (abertos agora, por categoria) e "Evolução de resolução" (4 semanas: abertos, resolvidos por pessoas e pelo sistema).
    Só contagens reais; sem dado, a lista vem vazia e a tela diz que não há."""
    from .contagens import ERROS_ABERTOS, SEM_CONVIDADO_ERRO
    tipos = [{"categoria": r[0], "rotulo": ROTULO_TIPO.get(r[0], r[0]), "n": r[1]}
             for r in con.execute(f"SELECT categoria, COUNT(*) FROM erro WHERE {ERROS_ABERTOS} GROUP BY categoria ORDER BY COUNT(*) DESC, categoria")]
    semanas = []
    for k in range(3, -1, -1):
        ini = con.execute(f"SELECT date('now','weekday 1','-{7 * (k + 1)} days')").fetchone()[0]
        fim = con.execute("SELECT date(?, '+7 days')", (ini,)).fetchone()[0]
        res = [SEM_CONVIDADO_ERRO, "situacao IN ('corrigido','fechado')", "resolvido_em >= ?", "resolvido_em < ?"]
        sist = con.execute("SELECT COUNT(*) FROM erro WHERE " + " AND ".join(res + [SISTEMA_SQL]), (ini, fim)).fetchone()[0]
        tot = con.execute("SELECT COUNT(*) FROM erro WHERE " + " AND ".join(res), (ini, fim)).fetchone()[0]
        novos = con.execute(f"SELECT COUNT(*) FROM erro WHERE {SEM_CONVIDADO_ERRO} AND criado_em >= ? AND criado_em < ?", (ini, fim)).fetchone()[0]
        semanas.append({"inicio": ini, "fim": fim, "resolvidos": tot, "pelo_sistema": sist, "por_pessoas": tot - sist, "novos": novos})
    return {"por_tipo": tipos, "total_abertos": sum(t["n"] for t in tipos), "semanas": semanas}


def por_fundo(con) -> list[dict]:
    """Contadores por fundo, com a proporção sobre as folhas AVALIADAS (conferidas ou corrigidas no painel), nunca sobre um total presumido."""
    from .contagens import ERROS_ABERTOS
    out = {}
    for r in con.execute(f"""SELECT substr(codigo,1,4) AS f, COUNT(*) AS n, SUM(gravidade='bloqueia') AS crit FROM erro
                             WHERE {ERROS_ABERTOS} AND codigo GLOB 'F[0-9][0-9][0-9]*' GROUP BY substr(codigo,1,4)"""):
        out[r["f"]] = {"fundo": r["f"], "abertos": r["n"], "criticos": r["crit"] or 0}
    if not out:
        return []
    nomes = {r[0]: r[1] for r in con.execute("SELECT codigo, titulo FROM fundo")}
    for fcod, x in out.items():
        x["titulo"] = nomes.get(fcod)
        av = con.execute("""SELECT COUNT(*) FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE p.fundo_codigo=?
                            AND (i.revisao IN ('conferida','corrigida') OR i.revisado_em IS NOT NULL)""", (fcod,)).fetchone()[0]
        com = con.execute(f"""SELECT COUNT(DISTINCT e.codigo) FROM erro e JOIN item i ON i.codigo=e.codigo
                              WHERE e.situacao IN ('aberto','em_correcao') AND substr(e.codigo,1,4)=?
                              AND (i.revisao IN ('conferida','corrigida') OR i.revisado_em IS NOT NULL)""", (fcod,)).fetchone()[0]
        x["folhas_avaliadas"] = av
        x["avaliadas_com_problema"] = com
        x["proporcao"] = round(com / av, 4) if av else None
    return sorted(out.values(), key=lambda x: (-x["criticos"], -x["abertos"], x["fundo"]))


# ---------------- detalhe, transições, evidências ----------------
def _erro(con, eid: int):
    e = con.execute("SELECT * FROM erro WHERE id=?", (eid,)).fetchone()
    if not e:
        raise HTTPException(404, "Este problema não existe")
    return e


def _evento(con, eid, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('erro',?,?,?,?)",
                (str(eid), tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def evidencias(con, eid: int) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM erro_evidencia WHERE erro_id=? ORDER BY id", (eid,))]


def requisitos(con, e, alvo: str) -> list[str]:
    """O que a fase de destino exige (texto para a tela)."""
    if alvo in ("resolvido", "aguardando_revisao"):
        r = ["conclusão"]
        r.append("fonte ou evidência" if e["categoria"] in TIPOS_COM_FONTE else "evidência ou justificativa")
        return r
    if alvo in ("reaberto", "invalido"):
        return ["justificativa"]
    if alvo in ("aguardando_informacao", "devolvido"):
        return ["motivo"]
    if alvo == "duplicado":
        return ["número do problema que fica"]
    return []


class MudarFase(BaseModel):
    fase: str
    conclusao: str | None = None        # resolver / enviar para revisão
    justificativa: str | None = None    # reabrir / inválido / (resolver sem evidência)
    motivo: str | None = None           # aguardando informação / devolvido
    referencia: int | None = None       # duplicado: o problema que fica
    evidencia: str | None = None        # uma evidência junto (texto ou link)


def mudar_fase(con, eid: int, d: MudarFase, u: dict, extra: dict | None = None) -> dict:
    """`extra` (CAMP-PROB-RAPIDO): campos a mais no evento 'fase' (ex.: a ação rápida e o modelo usado)."""
    e = _erro(con, eid)
    atual = fase_efetiva(e["situacao"], e["fase"], e["duplicado_de"], e["resolucao"])
    alvo = d.fase
    if alvo not in FASES:
        raise HTTPException(400, "Fase inválida")
    if alvo not in TRANSICOES.get(atual, set()):
        raise HTTPException(409, f"De \"{ROTULO_FASE[atual]}\" não se vai para \"{ROTULO_FASE[alvo]}\"")
    ator = u["email"]
    conc = (d.conclusao or "").strip()[:2000]
    just = (d.justificativa or "").strip()[:1000]
    mot = (d.motivo or "").strip()[:500]
    if d.evidencia and d.evidencia.strip():
        _add_evidencia(con, eid, d.evidencia, None, ator)
    ev = evidencias(con, eid)
    fontes = [x for x in ev if x["tipo"] != "justificativa"]
    sets, vals = [], []
    det = {"de": atual, "para": alvo, **(extra or {})}
    if alvo in ("resolvido", "aguardando_revisao"):
        if alvo == "resolvido" and atual == "aguardando_revisao" and not conc:
            conc = e["resolucao"] or ""
        if len(conc) < 5:
            raise HTTPException(400, "Escreva a conclusão: o que foi decidido ou feito")
        if e["categoria"] in TIPOS_COM_FONTE and not fontes:
            raise HTTPException(400, "Este tipo pede fonte ou evidência (documento, link, folha): adicione antes de concluir. Nada de fonte inventada")
        if not fontes and len(just) < 5 and not [x for x in ev if x["tipo"] == "justificativa"]:
            raise HTTPException(400, "Adicione uma evidência ou escreva a justificativa")
        if just:
            _add_evidencia(con, eid, just, None, ator, tipo="justificativa")
        sets += ["resolucao=?"]; vals += [conc]
    if alvo == "resolvido":
        if precisa_revisao(con, e["categoria"]):
            if atual != "aguardando_revisao":
                raise HTTPException(409, "Este tipo precisa da revisão de outra pessoa: envie para revisão")
            if (e["enviado_revisao_por"] or "") == ator:
                raise HTTPException(409, "A revisão tem de ser de outra pessoa: quem enviou não aprova a própria resolução")
        sets += ["situacao='corrigido'", "resolvido_em=datetime('now')", "fechado_por=?", "motivo_pendencia=NULL"]; vals += [ator]
        if atual == "aguardando_revisao":
            sets += ["revisado_por=?", "revisado_em=datetime('now')"]; vals += [ator]
        if e["categoria"] == "autoria_divergente":
            con.execute("UPDATE item SET autoria_divergente=0 WHERE codigo=?", (e["codigo"],))
        quem = (e["enviado_revisao_por"] if atual == "aguardando_revisao" and e["enviado_revisao_por"] else ator)
        # os pontos são os da Home (recontados do estado); "credito" diz quem resolveu quando outra pessoa aprovou na revisão
        det.update(conclusao=conc, validado_por_revisao=atual == "aguardando_revisao", credito=quem)
        con.execute("DELETE FROM erro_rascunho WHERE erro_id=?", (eid,))
    elif alvo == "aguardando_revisao":
        sets += ["situacao='em_correcao'", "enviado_revisao_por=?", "enviado_revisao_em=datetime('now')", "revisado_por=NULL", "revisado_em=NULL"]; vals += [ator]
        det.update(conclusao=conc)
        con.execute("DELETE FROM erro_rascunho WHERE erro_id=?", (eid,))
    elif alvo in ("aguardando_informacao", "devolvido"):
        if len(mot) < 3:
            raise HTTPException(400, "Diga o motivo (o que falta ou o que precisa mudar)")
        sets += ["situacao='em_correcao'", "motivo_pendencia=?"]; vals += [mot]
        if alvo == "devolvido":
            sets += ["revisado_por=?", "revisado_em=datetime('now')"]; vals += [ator]
        det.update(motivo=mot)
    elif alvo == "reaberto":
        if len(just) < 5:
            raise HTTPException(400, "Para reabrir, escreva a justificativa")
        sets += ["situacao='aberto'", "resolvido_em=NULL", "fechado_por=NULL", "duplicado_de=NULL", "revisado_por=NULL", "revisado_em=NULL", "motivo_pendencia=?"]; vals += [just]
        det.update(justificativa=just)
    elif alvo == "invalido":
        if len(just) < 5:
            raise HTTPException(400, "Escreva por que não é problema")
        sets += ["situacao='ignorado'", "resolvido_em=datetime('now')", "fechado_por=?", "resolucao=?"]; vals += [ator, just]
        det.update(justificativa=just)
    elif alvo == "duplicado":
        juntar_duplicado(con, e, d.referencia, ator, just)
        return {"ok": True, "fase": "duplicado", "duplicado_de": d.referencia}
    else:                                   # triagem, em_analise
        sets += [f"situacao='{FASE_SITUACAO[alvo]}'", "motivo_pendencia=NULL"]
        if alvo == "em_analise" and not con.execute("SELECT 1 FROM tarefa_responsavel WHERE tarefa_id=?", (f"erro:{eid}",)).fetchone():
            from .home_trabalho import atribuir_tarefa
            atribuir_tarefa(con, f"erro:{eid}", u["id"], u, TITULO_TIPO.get(e["categoria"]))   # quem começa a analisar assume (dá para trocar)
            det["assumiu"] = True
    sets += ["fase=?", "fase_em=datetime('now')"]; vals += [alvo]
    con.execute(f"UPDATE erro SET {', '.join(sets)} WHERE id=?", (*vals, eid))
    _evento(con, eid, "fase", ator, det)
    return {"ok": True, "fase": alvo}


def juntar_duplicado(con, e, ref: int | None, ator: str, just: str = "") -> None:
    """Junta este problema a outro (o que fica): este vira Duplicado com a referência; as evidências são copiadas para o que fica
    (marcando de onde vieram); os dois guardam o histórico. Nada é apagado."""
    if not ref:
        raise HTTPException(400, "Diga o número do problema que fica")
    if int(ref) == e["id"]:
        raise HTTPException(400, "Um problema não é duplicado dele mesmo")
    alvo = _erro(con, int(ref))
    seen = {e["id"]}
    while alvo["duplicado_de"] and alvo["situacao"] == "ignorado" and alvo["id"] not in seen:   # cadeia: aponta para o que ficou de verdade
        seen.add(alvo["id"]); alvo = _erro(con, alvo["duplicado_de"])
    if alvo["id"] == e["id"]:
        raise HTTPException(400, "Esse problema já foi juntado a este")
    for x in evidencias(con, e["id"]):
        con.execute("INSERT INTO erro_evidencia (erro_id, tipo, valor, hipotese, autor, criado_em, origem_erro_id) VALUES (?,?,?,?,?,?,?)",
                    (alvo["id"], x["tipo"], x["valor"], x["hipotese"], x["autor"], x["criado_em"], e["id"]))
    res = f"Duplicado do nº {alvo['id']}." + (f" {just}" if just else "")
    con.execute("""UPDATE erro SET situacao='ignorado', fase='duplicado', fase_em=datetime('now'), duplicado_de=?, resolvido_em=datetime('now'),
                   fechado_por=?, resolucao=? WHERE id=?""", (alvo["id"], ator, res, e["id"]))
    r_ = con.execute("SELECT usuario_id FROM tarefa_responsavel WHERE tarefa_id=?", (f"erro:{e['id']}",)).fetchone()
    if r_ and not con.execute("SELECT 1 FROM tarefa_responsavel WHERE tarefa_id=?", (f"erro:{alvo['id']}",)).fetchone():
        con.execute("INSERT INTO tarefa_responsavel (tarefa_id, usuario_id, atribuido_por) VALUES (?,?,?)", (f"erro:{alvo['id']}", r_[0], ator))   # o responsável segue
    _evento(con, e["id"], "duplicado_juntado", ator, {"fica": alvo["id"], "justificativa": just or None})
    _evento(con, alvo["id"], "recebeu_duplicado", ator, {"duplicado": e["id"], "codigo": e["codigo"]})


def _add_evidencia(con, eid: int, valor: str, hipotese: str | None, ator: str, tipo: str | None = None) -> int:
    v = (valor or "").strip()[:2000]
    if len(v) < 3:
        raise HTTPException(400, "Evidência vazia")
    if tipo is None:
        tipo = "link" if re.match(r"^https?://", v) else "folha" if re.fullmatch(r"F\d{3}-P\d{4}-.+-D\d+", v.upper()) else "texto"
    if tipo not in EVIDENCIA_TIPOS:
        raise HTTPException(400, "Tipo de evidência inválido")
    if tipo == "folha":
        v = v.upper()
        if not con.execute("SELECT 1 FROM item WHERE codigo=?", (v,)).fetchone():
            raise HTTPException(400, f"A folha {v} não existe no painel")
    i = con.execute("INSERT INTO erro_evidencia (erro_id, tipo, valor, hipotese, autor) VALUES (?,?,?,?,?)",
                    (eid, tipo, v, (hipotese or "").strip()[:200] or None, ator)).lastrowid
    _evento(con, eid, "evidencia", ator, {"tipo": tipo, "hipotese": (hipotese or "").strip()[:200] or None})
    return i


def historico(con, e) -> list[dict]:
    ids = [str(e["id"])] + [str(r[0]) for r in con.execute("SELECT id FROM erro WHERE duplicado_de=?", (e["id"],))]
    nomes = _nomes(con)
    out = []
    tar = [f"erro:{i}" for i in ids]
    for r in con.execute(f"""SELECT id, quando, tipo, ator, detalhe, CASE WHEN entidade='tarefa' THEN substr(codigo,6) ELSE codigo END AS codigo FROM evento
                             WHERE (entidade='erro' AND codigo IN ({','.join('?' * len(ids))})) OR (entidade='tarefa' AND codigo IN ({','.join('?' * len(tar))}))
                             ORDER BY quando, id""", ids + tar):
        try:
            det = json.loads(r["detalhe"] or "{}")
        except ValueError:
            det = {}
        out.append({"quando": r["quando"], "tipo": r["tipo"], "ator": r["ator"], "ator_nome": nomes.get(r["ator"]) or r["ator"],
                    "detalhe": det, "do_duplicado": r["codigo"] != str(e["id"]) and int(r["codigo"])})
    return out


def detalhe(con, eid: int, u: dict) -> dict:
    e = _erro(con, eid)
    x = enriquecer(con, [e], u)[0]
    f = x["fase"]
    ev = evidencias(con, eid)
    nomes = _nomes(con)
    for v in ev:
        v["autor_nome"] = nomes.get(v["autor"]) or v["autor"]
    x["evidencias"] = ev
    x["historico"] = historico(con, e)
    x["duplicados"] = [dict(r) for r in con.execute("SELECT id, codigo, descricao, resolvido_em FROM erro WHERE duplicado_de=? ORDER BY id", (eid,))]
    try:
        r = con.execute("SELECT texto, atualizado_em FROM erro_rascunho WHERE erro_id=? AND usuario_id=?", (eid, u.get("id"))).fetchone()
    except Exception:  # noqa: BLE001
        r = None
    x["rascunho"] = dict(r) if r else None
    x["modelos"] = [dict(m) for m in con.execute("SELECT id, titulo, texto FROM erro_modelo WHERE ativo=1 AND categoria=? ORDER BY titulo", (e["categoria"],))]
    x["transicoes"] = [{"fase": t, "rotulo": ROTULO_FASE[t], "requisitos": requisitos(con, e, t)} for t in FASES if t in TRANSICOES.get(f, set())]
    x["precisa_revisao"] = precisa_revisao(con, e["categoria"])
    x["exige_fonte"] = e["categoria"] in TIPOS_COM_FONTE
    if e["categoria"] == "autoria_divergente":
        hip = {}
        for v in ev:
            if v["tipo"] != "justificativa":
                hip.setdefault(v["hipotese"] or "Sem hipótese indicada", []).append(v)
        x["hipoteses"] = [{"hipotese": k, "fontes": vs} for k, vs in hip.items()]
    x["previa"] = None
    if x.get("folha"):          # CAMP-PROB-REAL: a MESMA rota de imagem do resto do painel (também a folha retirada, fora do painel)
        from .problemas_rapido import fora_do_painel, url_previa
        it = con.execute("SELECT arquivo_jpg, pendencias FROM item WHERE codigo=?", (x["folha"],)).fetchone() if x.get("folha_existe") else None
        if it or fora_do_painel(x):
            x["previa"] = url_previa(x["folha"], it)
    x["enviado_revisao_nome"] = nomes.get(e["enviado_revisao_por"]) or e["enviado_revisao_por"]
    x["revisado_nome"] = nomes.get(e["revisado_por"]) or e["revisado_por"]
    x["fechado_nome"] = (nomes.get(e["fechado_por"]) or e["fechado_por"]) if e["fechado_por"] else (ATOR_SISTEMA if x.get("resolvido_pelo_sistema") else None)
    return x


# ---------------- reconhecimento (fase 3) ----------------
def conquistas_qualidade(con, u: dict) -> list[dict]:
    """Conquistas de qualidade da Central (sem pontos: os pontos são só os da Home). Tiradas do estado atual; reabriu, some.
    Os títulos são fatos verificáveis, sem apelido nem título honorífico (Rafael, 22/11/2026: "não quero que fique infantil")."""
    from .home_trabalho import eventos_validados
    eu = u.get("email") or ""
    meus = [int(x["ref"][5:]) for x in eventos_validados(con) if x["email"] == eu and x["tipo"].startswith("problema_")]
    com_fonte = 0
    if meus:
        com_fonte = con.execute(f"""SELECT COUNT(DISTINCT erro_id) FROM erro_evidencia WHERE tipo<>'justificativa' AND erro_id IN ({','.join('?' * len(meus))})""", meus).fetchone()[0]
    revisoes = con.execute("""SELECT COUNT(*) FROM erro e WHERE e.situacao='corrigido' AND e.revisado_por=? AND COALESCE(e.enviado_revisao_por,'')<>?""", (eu, eu)).fetchone()[0]
    apoio = con.execute("""SELECT COUNT(DISTINCT v.erro_id) FROM erro_evidencia v JOIN erro e ON e.id=v.erro_id
                           WHERE v.autor=? AND v.tipo<>'justificativa' AND e.situacao IN ('corrigido','fechado') AND COALESCE(e.fechado_por,'')<>?""", (eu, eu)).fetchone()[0]
    fundos_ok = con.execute("""SELECT COUNT(*) FROM fundo f WHERE f.codigo<>'F000'
                   AND EXISTS (SELECT 1 FROM erro e WHERE substr(e.codigo,1,4)=f.codigo AND e.situacao IN ('corrigido','fechado'))
                   AND NOT EXISTS (SELECT 1 FROM erro e WHERE substr(e.codigo,1,4)=f.codigo AND e.situacao IN ('aberto','em_correcao'))""").fetchone()[0]
    def cq(chave, titulo, desc, feito, meta, coletiva=False):
        return {"chave": chave, "titulo": titulo, "descricao": desc, "obtida": feito >= meta, "feito": min(feito, meta), "meta": meta, "coletiva": coletiva}
    return [cq("primeira", "Primeira resolução validada", "Um problema corrigido com a frase do que foi feito (e, quando pedida, aprovado na revisão).", len(meus), 1),
            cq("investigador", "5 problemas resolvidos com fonte ou evidência", "Problemas resolvidos por você com fonte ou evidência registrada.", com_fonte, 5),
            cq("colaborador", "3 resoluções de outras pessoas com evidência sua", "Evidência sua ajudou outra pessoa a resolver.", apoio, 3),
            cq("revisor", "5 revisões aprovadas", "Revisões aprovadas por você (de resoluções de outra pessoa).", revisoes, 5),
            cq("fundo", "Um fundo sem problemas abertos", "Marco coletivo: fundo que teve problemas e hoje não tem nenhum aberto.", fundos_ok, 1, True)]


from .home_trabalho import AVISO_RANKING  # noqa: E402 — o mesmo aviso do Ranking da equipe na Home e aqui


ROTULO_EVENTO = {"criado": "registrou", "fase": "mudou a fase", "evidencia": "adicionou evidência", "atribuido": "atribuiu", "duplicado_juntado": "juntou como duplicado",
                 "recebeu_duplicado": "recebeu um duplicado", "fechado_automatico": "fechou sozinho (o painel conferiu)", "editado": "mudou a situação", "ignorado": "fechou: não era problema",
                 "mesclado": "juntou a mensagem repetida", "desfeito": "desfez", "tarefa_atribuida": "atribuiu", "tarefa_devolvida": "devolveu (sem responsável)",
                 "reaberto_automatico": "reabriu sozinho (a folha voltou ao painel)", "problema_seguiu_folha": "seguiu a folha (código novo)",
                 "fechado_na_conferencia": "resolveu na conferência", "problema_reclassificado": "passou a aviso (aviso técnico menor)"}
# CAMP-PROB-RAPIDO: o título de cada evento na "Atividade recente" (nunca o código interno, como "Fechado_na_conferencia")
TITULO_EVENTO = {"fechado_automatico": "Resolvido pelo sistema", "evidencia": "Evidência adicionada", "criado": "Problema registrado",
                 "fechado_na_conferencia": "Resolvido na conferência", "ignorado": "Fechado: não era problema", "mesclado": "Mensagem repetida juntada",
                 "desfeito": "Ação desfeita", "reaberto_automatico": "Reaberto sozinho", "problema_seguiu_folha": "Seguiu a folha",
                 "problema_reclassificado": "Passou a aviso", "duplicado_juntado": "Juntado como duplicado", "recebeu_duplicado": "Recebeu um duplicado",
                 "editado": "Situação mudada", "atribuido": "Responsável mudado"}
ICONE_EVENTO = {"fechado_automatico": "ok", "fechado_na_conferencia": "ok", "evidencia": "lapis", "criado": "mais"}
ROTULO_RAPIDO = {"deste_projeto": "É deste projeto", "mover": "movida para outro projeto", "mesma_folha": "é a mesma folha", "diferentes": "são folhas diferentes",
                 "metadado": "dado salvo", "nao_e_problema": "não é problema"}


def atividade(con, limite: int = 12) -> list[dict]:
    """O que aconteceu por último nos problemas (do histórico `evento`): quem, o quê (frase curta + ícone), o problema (nº, código) e quando."""
    nomes = _nomes(con)
    out = []
    rows = con.execute("""SELECT quando, tipo, ator, detalhe, CASE WHEN entidade='tarefa' THEN substr(codigo,6) ELSE codigo END AS codigo FROM evento
                          WHERE entidade='erro' OR (entidade='tarefa' AND codigo LIKE 'erro:%') ORDER BY id DESC LIMIT ?""", (limite,)).fetchall()
    ids = [int(r["codigo"]) for r in rows if str(r["codigo"]).isdigit()]
    cods = {}
    if ids:
        cods = {r[0]: r[1] for r in con.execute(f"SELECT id, codigo FROM erro WHERE id IN ({','.join('?' * len(ids))})", ids)}
    for r in rows:
        try:
            det = json.loads(r["detalhe"] or "{}")
        except ValueError:
            det = {}
        txt = ROTULO_EVENTO.get(r["tipo"]) or "registrou uma mudança"
        icone, titulo = ICONE_EVENTO.get(r["tipo"], "relogio"), TITULO_EVENTO.get(r["tipo"])
        if r["tipo"] == "fase" and det.get("para") in ROTULO_FASE:
            txt = "moveu para " + ROTULO_FASE[det["para"]]
            titulo = {"resolvido": "Problema resolvido", "aguardando_revisao": "Enviado para revisão", "reaberto": "Problema reaberto",
                      "devolvido": "Devolvido pela revisão", "duplicado": "Juntado como duplicado", "invalido": "Fechado: não é problema"}.get(det["para"], "Em " + ROTULO_FASE[det["para"]].lower().replace("em ", ""))
            if det.get("rapido") in ROTULO_RAPIDO:
                txt = "resolveu na lista: " + ROTULO_RAPIDO[det["rapido"]]
            icone = "ok" if det["para"] == "resolvido" else "relogio"
        elif r["tipo"] in ("tarefa_atribuida", "tarefa_devolvida"):
            titulo, icone = ("Atribuído a " + (det.get("para") or "alguém")) if r["tipo"] == "tarefa_atribuida" else "Devolvido (sem responsável)", "pessoa"
        elif r["tipo"] == "editado" and det.get("situacao") in ("corrigido", "fechado"):
            titulo, icone = "Problema resolvido", "ok"
        eid = int(r["codigo"]) if str(r["codigo"]).isdigit() else None
        out.append({"quando": r["quando"], "ator": nomes.get(r["ator"]) or r["ator"], "texto": txt, "titulo": titulo or txt[:1].upper() + txt[1:], "tipo": r["tipo"],
                    "icone": icone, "erro_id": eid, "codigo": cods.get(eid)})
    return out


# ---------------- rotas ----------------
def _filtros(aba, q, fase, gravidade, categoria, origem, responsavel, fundo, projeto, de, ate, idade, chip) -> Filtros:
    return Filtros(aba=aba or "prioridades", q=q, fase=fase, gravidade=gravidade, categoria=categoria, origem=origem, responsavel=responsavel,
                   fundo=fundo, projeto=projeto, de=de, ate=ate, idade=idade, chip=chip)


def _fechar_sozinhos(con) -> None:
    from .rotas_operacao import _fechar_sozinhos as fs
    fs(con)


@router.get("")
def rota_listar(aba: str = "prioridades", q: str | None = None, fase: str | None = None, gravidade: str | None = None, categoria: str | None = None,
                origem: str | None = None, responsavel: str | None = None, fundo: str | None = None, projeto: str | None = None, de: str | None = None,
                ate: str | None = None, idade: str | None = None, chip: str | None = None, ordem: str = "prioridade", pagina: int = 1, por_pagina: int = 25,
                agrupar: int = 0, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        _fechar_sozinhos(con)
        return listar(con, _filtros(aba, q, fase, gravidade, categoria, origem, responsavel, fundo, projeto, de, ate, idade, chip), u, ordem, pagina, por_pagina,
                      agrupar=bool(agrupar), rapido=True)
    finally:
        con.close()


@router.get("/resumo")
def rota_resumo(aba: str = "prioridades", q: str | None = None, fase: str | None = None, gravidade: str | None = None, categoria: str | None = None,
                origem: str | None = None, responsavel: str | None = None, fundo: str | None = None, projeto: str | None = None, de: str | None = None,
                ate: str | None = None, idade: str | None = None, chip: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        _fechar_sozinhos(con)
        return resumo(con, _filtros(aba, q, fase, gravidade, categoria, origem, responsavel, fundo, projeto, de, ate, idade, chip), u)
    finally:
        con.close()


@router.get("/graficos")
def rota_graficos(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return graficos(con)
    finally:
        con.close()


@router.get("/por-fundo")
def rota_por_fundo(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    try:
        return por_fundo(con)
    finally:
        con.close()


@router.get("/progresso")
def rota_progresso(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """O progresso da Home (UM sistema de pontos: meta da semana, nível, conquistas, Ranking da equipe do mês, ligado por padrão) + as conquistas de
    qualidade da Central (sem pontos) + a atividade recente dos problemas (do histórico)."""
    from .home_trabalho import progresso as progresso_home
    con = connect()
    try:
        jogo = progresso_home(con, u)
        oculto = bool(jogo.get("oculto"))
        return {"jogo": jogo, "conquistas_qualidade": [] if oculto or u.get("papel") == "leitura" or not jogo.get("ligado") else conquistas_qualidade(con, u),
                "aviso_ranking": AVISO_RANKING, "atividade": atividade(con)}
    finally:
        con.close()


class Atribuir(BaseModel):
    ids: list[int]
    usuario_id: int | None = None      # vazio = devolver (tirar o responsável)


@router.post("/atribuir")
def rota_atribuir(d: Atribuir, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Atribuir em lote (ou um só) com a regra da Home (home_trabalho.atribuir_tarefa): operador pega para si ou devolve a sua; admin
    atribui a qualquer pessoa que edita. Tudo ou nada; só problemas abertos. Histórico: tarefa_atribuida / tarefa_devolvida."""
    from .home_trabalho import atribuir_tarefa
    ids = list(dict.fromkeys(int(i) for i in d.ids))
    if not ids:
        raise HTTPException(400, "Escolha pelo menos um problema")
    if len(ids) > 500:
        raise HTTPException(400, "No máximo 500 de uma vez")
    con = connect()
    try:
        rows = con.execute(f"SELECT id, situacao, categoria FROM erro WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
        if len(rows) != len(ids):
            raise HTTPException(404, f"{len(ids) - len(rows)} dos problemas escolhidos não existem mais: atualize a lista")
        fech = [r["id"] for r in rows if r["situacao"] not in ("aberto", "em_correcao")]
        if fech:
            raise HTTPException(409, f"{len(fech)} dos escolhidos já estão fechados: reabra antes de atribuir")
        con.execute("BEGIN IMMEDIATE")
        n = 0
        try:
            for r in rows:
                antes = con.execute("SELECT usuario_id FROM tarefa_responsavel WHERE tarefa_id=?", (f"erro:{r['id']}",)).fetchone()
                atribuir_tarefa(con, f"erro:{r['id']}", d.usuario_id, u, TITULO_TIPO.get(r["categoria"]))
                depois = con.execute("SELECT usuario_id FROM tarefa_responsavel WHERE tarefa_id=?", (f"erro:{r['id']}",)).fetchone()
                n += (antes[0] if antes else None) != (depois[0] if depois else None)
        except Exception:
            con.rollback()
            raise
        con.commit()
        return {"ok": True, "atualizados": n, "ids": ids}
    finally:
        con.close()


@router.get("/modelos")
def rota_modelos(categoria: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    try:
        w, p = "", []
        if categoria:
            w, p = " WHERE categoria=?", [categoria]
        return [dict(r) for r in con.execute(f"SELECT * FROM erro_modelo{w} ORDER BY categoria, titulo", p)]
    finally:
        con.close()


class Modelo(BaseModel):
    categoria: str | None = None
    titulo: str | None = None
    texto: str | None = None
    ativo: bool | None = None


@router.post("/modelos")
def rota_criar_modelo(d: Modelo, u: dict = Depends(auth.exige("operador"))) -> dict:
    from .rotas_operacao import CATS
    if d.categoria not in CATS:
        raise HTTPException(400, "Tipo inválido")
    if len((d.titulo or "").strip()) < 3 or len((d.texto or "").strip()) < 5:
        raise HTTPException(400, "Dê um título e o texto do modelo")
    con = connect()
    try:
        try:
            i = con.execute("INSERT INTO erro_modelo (categoria, titulo, texto, criado_por, atualizado_por) VALUES (?,?,?,?,?)",
                            (d.categoria, d.titulo.strip()[:120], d.texto.strip()[:2000], u["email"], u["email"])).lastrowid
        except Exception:  # noqa: BLE001
            raise HTTPException(409, "Já existe um modelo com esse título para este tipo")
        con.commit()
        return {"ok": True, "id": i}
    finally:
        con.close()


@router.patch("/modelos/{mid}")
def rota_editar_modelo(mid: int, d: Modelo, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM erro_modelo WHERE id=?", (mid,)).fetchone():
            raise HTTPException(404, "Modelo não existe")
        sets, vals = ["atualizado_por=?", "atualizado_em=datetime('now')"], [u["email"]]
        if d.titulo is not None:
            if len(d.titulo.strip()) < 3:
                raise HTTPException(400, "Título curto demais")
            sets.append("titulo=?"); vals.append(d.titulo.strip()[:120])
        if d.texto is not None:
            if len(d.texto.strip()) < 5:
                raise HTTPException(400, "Texto curto demais")
            sets.append("texto=?"); vals.append(d.texto.strip()[:2000])
        if d.ativo is not None:
            sets.append("ativo=?"); vals.append(int(d.ativo))
        con.execute(f"UPDATE erro_modelo SET {', '.join(sets)} WHERE id=?", (*vals, mid))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.get("/visoes")
def rota_visoes(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT id, nome, params, criado_em FROM erro_visao WHERE usuario_id=? ORDER BY nome", (u["id"],))]
    finally:
        con.close()


class Visao(BaseModel):
    nome: str
    params: str


@router.post("/visoes")
def rota_salvar_visao(d: Visao, u: dict = Depends(auth.exige("leitura"))) -> dict:
    nome = (d.nome or "").strip()[:60]
    if len(nome) < 2:
        raise HTTPException(400, "Dê um nome à visão")
    con = connect()
    try:
        con.execute("INSERT INTO erro_visao (usuario_id, nome, params) VALUES (?,?,?) ON CONFLICT(usuario_id, nome) DO UPDATE SET params=excluded.params",
                    (u["id"], nome, (d.params or "")[:1000]))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.delete("/visoes/{vid}")
def rota_apagar_visao(vid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        n = con.execute("DELETE FROM erro_visao WHERE id=? AND usuario_id=?", (vid, u["id"])).rowcount
        con.commit()
        if not n:
            raise HTTPException(404, "Visão não existe")
        return {"ok": True}
    finally:
        con.close()


@router.get("/exportar.csv")
def rota_csv(aba: str = "prioridades", q: str | None = None, fase: str | None = None, gravidade: str | None = None, categoria: str | None = None,
             origem: str | None = None, responsavel: str | None = None, fundo: str | None = None, projeto: str | None = None, de: str | None = None,
             ate: str | None = None, idade: str | None = None, chip: str | None = None, ordem: str = "prioridade", u: dict = Depends(auth.exige("leitura"))):
    """Exporta TUDO do filtro (não só a página). Quem só lê não recebe o contato do visitante que avisou pelo site (dado de pessoa)."""
    con = connect()
    try:
        f = _filtros(aba, q, fase, gravidade, categoria, origem, responsavel, fundo, projeto, de, ate, idade, chip)
        r = listar(con, f, u, ordem, 1, 200)
        itens = list(r["itens"])
        pg = 2
        while len(itens) < r["total"]:
            itens += listar(con, f, u, ordem, pg, 200)["itens"]; pg += 1
        ver_contato = u.get("papel") in ("operador", "admin", "master")
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Nº", "Título", "Severidade", "Prioridade", "Motivo da prioridade", "Fase", "Tipo", "Fundo", "Projeto", "Nome do projeto", "Onde",
                    "Descrição", "Responsável", "Origem", "Relatado por", "Aberto em", "Idade (dias)", "Conclusão", "Resolvido em"])
        for x in itens:
            rel = x.get("relatado_por") or ""
            if x.get("origem") == "site" and not ver_contato:
                rel = "(visitante do site)"
            w.writerow([x["id"], x["titulo"], x["severidade_rotulo"], (x.get("prioridade") or {}).get("nota", ""), (x.get("prioridade") or {}).get("razao", ""),
                        x["fase_rotulo"], x["tipo_rotulo"], x.get("fundo_codigo") or "", x.get("projeto_codigo") or "", x.get("projeto_titulo") or "",
                        x.get("folha") or x["codigo"], x["descricao"], x.get("responsavel_nome") or "Não atribuído", x.get("origem") or "", rel,
                        x.get("criado_em") or "", x["idade_dias"], x.get("resolucao") or "", x.get("resolvido_em") or ""])
        nome = "camp-problemas-" + datetime.now().strftime("%Y-%m-%d") + ".csv"
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nome}"'})
    finally:
        con.close()


@router.get("/{eid}")
def rota_detalhe(eid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return detalhe(con, eid, u)
    finally:
        con.close()


@router.post("/{eid}/fase")
def rota_fase(eid: int, d: MudarFase, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        out = mudar_fase(con, eid, d, u)
        con.commit()
        return out
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class NovaEvidencia(BaseModel):
    valor: str
    hipotese: str | None = None


@router.post("/{eid}/evidencias")
def rota_evidencia(eid: int, d: NovaEvidencia, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        _erro(con, eid)
        i = _add_evidencia(con, eid, d.valor, d.hipotese, u["email"])
        con.commit()
        return {"ok": True, "id": i}
    finally:
        con.close()


class Rascunho(BaseModel):
    texto: str = ""


@router.put("/{eid}/rascunho")
def rota_rascunho(eid: int, d: Rascunho, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        _erro(con, eid)
        t = (d.texto or "")[:4000]
        if t.strip():
            con.execute("""INSERT INTO erro_rascunho (erro_id, usuario_id, texto) VALUES (?,?,?)
                           ON CONFLICT(erro_id, usuario_id) DO UPDATE SET texto=excluded.texto, atualizado_em=datetime('now')""", (eid, u["id"], t))
        else:
            con.execute("DELETE FROM erro_rascunho WHERE erro_id=? AND usuario_id=?", (eid, u["id"]))
        con.commit()
        return {"ok": True, "salvo_em": con.execute("SELECT datetime('now')").fetchone()[0]}
    finally:
        con.close()
