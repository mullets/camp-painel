"""UX-43 (27/10): "Verificar destino" resolvido pelo painel, sem ninguém clicar — mover o lote para o projeto certo ou criar o projeto.

O Rafael, olhando Material novo com vários lotes em "Verificar destino" (UX-01): "quero que você verifique destino sozinho.. crie a pasta sozinho..".
Para cada lote do CAMP Vision em "Verificar destino" (a pasta não parece do projeto, destino_lote.avaliar), o painel decide:

(a) mover — um projeto do MESMO fundo combina claramente com a pasta: nota ≥ 0,8 e ≥ 0,15 acima do segundo
    ("Edifício Marambaia - 1970-1971" no lote de F026-P0010 → F026-P0095 "Marambaia");
(b) criar — nenhum projeto do fundo chega a 0,5: cria o projeto no mesmo fundo com o PRÓXIMO P do contador do painel (nunca reusa
    número: projetos_novos.criar_projeto) e o título vem do nome da pasta limpo pelas regras do UX-15 (sugerir_titulo/titulo_tecnico);
    o ano sai da pasta ("1970-1971" → 1970, até 1971). O projeto fica marcado origem='automatico' (quadro "Projetos criados pelo painel");
(c) pessoa — pasta só com código ("P0001"), empate entre dois projetos, nota entre 0,5 e 0,8, nome que não serve de título:
    continua "Verificar destino" com o motivo.

O que "mover" quer dizer aqui: a pasta e o pacote no QNAP têm o código ANTIGO e quem renomeia/move arquivo no QNAP é o CAMP Vision
(`vigia.py --reidentificar <projeto antigo>`; o painel nunca mexe no QNAP). O caminho que já existia para "este lote é de outro projeto"
(decisão lote_destino resolvida como outro_projeto) só ANOTAVA o projeto certo e deixava o lote sem importar até o CAMP Vision
reidentificar a pasta. O automático faz o mesmo, sozinho: anota (tabela destino_auto + Histórico do lote e dos dois projetos), o lote
fica "movendo para F0xx-P0yyy (o CAMP Vision vai reorganizar a pasta)" e não importa no projeto antigo; o CAMP Vision acha a lista em
GET /api/campvision/destinos (rota nova, só leitura; CONTRATO_UNICO 1.3) com o comando a rodar. Conclui quando o material aparece no
projeto novo (lote novo vindo de outra pasta, criado depois) ou quando o próprio lote passa para lá (/api/campvision/reidentificar).

Segurança (CLAUDE.md: destrutivo atrás de flag ou simular):
- configuração destino.automatico = desligado | simular (PADRÃO: calcula e MOSTRA, não muda nada) | aplicar (o coletor aplica sozinho);
- aplica só em segundo plano (laço do coletor, ou a tarefa do botão "Aplicar estas N decisões" do admin), nunca dentro da requisição;
- cada lote é SIMULADO antes (SAVEPOINT + conferência + ROLLBACK) e só é aplicado se a simulação sair limpa; no máximo 10 por rodada;
- nunca o mesmo lote duas vezes (destino_auto.lote_id é UNIQUE, mesmo depois do Desfazer);
- só lote do CAMP Vision, sem folhas, em 'revisao', não aprovado/descartado, que não é complemento e sem decisão humana (confirmação ou
  decisão lote_destino aberta);
- Desfazer enquanto o CAMP Vision não reorganizou: o lote volta a "Verificar destino" para uma pessoa; o projeto criado (sem material)
  é descartado — o número P continua gasto, nunca é reusado.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import auth
from .db import connect
from .rede import exigir_estacao
from .similaridade import LIMIAR_PASTA, cidade_sem_caixa_alta, limpar_nome_de_pasta, sugerir_titulo, titulo_tecnico, tokens_de_pasta

router = APIRouter(prefix="/api", tags=["destino-automatico"])

ATOR = "painel (automático)"
CFG = "destino.automatico"
MODOS = ("desligado", "simular", "aplicar")
TETO = 10                      # lotes por rodada
NOTA_MOVER = 0.8               # (a) o candidato precisa de pelo menos isto...
FOLGA = 0.15                   # ... e desta folga sobre o segundo
NOTA_CRIAR = LIMIAR_PASTA      # (b) nenhum candidato chega a isto (0,5)
EVENTO = "destino_automatico"


def modo(con) -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (CFG,)).fetchone()
    v = str(r[0] if r else "").strip().lower()
    return v if v in MODOS else "simular"          # valor estranho = o mais seguro que ainda mostra algo


# ---------------- título do projeto novo a partir do nome da pasta ----------------
_ANOS = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
_ENCIAL = re.compile(r"ê(ncia(?:l|is))\b", re.I)    # "Residêncial" → "Residencial" (nenhuma palavra em -êncial tem acento)


def titulo_da_pasta(pasta: str | None) -> dict | None:
    """{titulo, ano, ano_fim} para o projeto novo, ou None quando o que sobra do nome não serve de título (técnico, curto, só código)."""
    nome = str(pasta or "")
    anos = [int(a) for a in _ANOS.findall(nome)]
    t = limpar_nome_de_pasta(nome)
    t = sugerir_titulo(t) or t                         # UX-15: tira prefixo de pasta ("T099_", "01 - ")
    t = " ".join(re.sub(r"\(\s*\)", " ", t).split()).strip(" -–—.,;")
    t = _ENCIAL.sub(lambda m: ("E" if m.group(0)[0].isupper() else "e") + m.group(1), t)
    t = cidade_sem_caixa_alta(t) or t                  # "RESIDENCIA X" → "Residencia X"
    if len(t) < 3 or titulo_tecnico(t) or not tokens_de_pasta(t):
        return None
    ano = anos[0] if anos else None
    fim = anos[1] if len(anos) > 1 and anos[1] > anos[0] else None
    return {"titulo": t[:200], "ano": ano, "ano_fim": fim}


# ---------------- a decisão de um lote ----------------
def _lotes_candidatos(con) -> list:
    """Lotes que PODEM entrar no automático (a avaliação do nome vem depois): do CAMP Vision, sem folhas, em 'revisao', abertos,
    projeto ativo, e que o painel ainda não decidiu."""
    return con.execute("""SELECT l.* FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo
                           WHERE l.descartado_em IS NULL AND l.aprovado_em IS NULL AND l.etapa='revisao'
                             AND p.mesclado_em IS NULL AND p.descartado_em IS NULL
                             AND NOT EXISTS (SELECT 1 FROM item i WHERE i.lote_id=l.id)
                             AND NOT EXISTS (SELECT 1 FROM destino_auto d WHERE d.lote_id=l.id)
                           ORDER BY l.id""").fetchall()


def _pct(n) -> str:
    return f"{round((n or 0) * 100)}%"


def _nota_auto(pasta: str, q) -> float | None:
    """A nota do UX-01 (destino_lote.nota), mas palavra FRACA sozinha não decide: "Prédio de Apartamentos com Garagem" × "Edifício
    Residencial com Garagem" dá 1,0 no UX-01 (todas as palavras do nome menor estão no outro), e só têm "garagem" em comum. Para o
    painel decidir sozinho, a pasta e o projeto precisam ter pelo menos uma palavra forte em comum; senão a nota conta como 0."""
    from .similaridade import _FRACAS_PASTA, _mesma_palavra, compatibilidade_pasta
    a = [w for w in tokens_de_pasta(pasta) if w not in _FRACAS_PASTA]
    melhor = None
    for texto in (q["titulo"], q["identificacao_original"]):
        n = compatibilidade_pasta(pasta, texto)
        if n is None:
            continue
        if not any(_mesma_palavra(x, y) for x in a for y in tokens_de_pasta(texto) if y not in _FRACAS_PASTA):
            n = 0.0
        melhor = n if melhor is None else max(melhor, n)
    return melhor


def classificar(con, l, extras: list[dict] | None = None) -> dict | None:
    """O que o painel faria com o lote: {acao: mover|criar|pessoa, para, para_titulo, titulo, ano, nota, segunda, motivo, ...}.
    None = o lote não é do automático (não está em "Verificar destino", ou uma pessoa já decidiu). Não grava nada.
    `extras` = projetos que o painel vai criar antes deste lote na mesma rodada (a prévia não cria nada de verdade)."""
    from .destino_lote import _contexto, avaliar, nome_da_pasta
    from .filas_fase import importado_sem_folhas
    ctx = _contexto(l)
    if ctx.get("complemento") or importado_sem_folhas(ctx):
        return None
    a = avaliar(con, l, completo=False)
    if not a["aplica"] or not a["suspeito"] or a["liberado"] or a["confirmado"] or a["decisao"] or a.get("automatico"):
        return None
    p = con.execute("SELECT codigo, titulo, fundo_codigo FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
    pasta = nome_da_pasta(l)
    out = {"lote_id": l["id"], "projeto": p["codigo"], "projeto_titulo": p["titulo"], "fundo": p["fundo_codigo"], "nome_pasta": pasta,
           "acao": "pessoa", "para": None, "para_titulo": None, "para_previsto": False, "titulo": None, "ano": None, "ano_fim": None,
           "nota": None, "segunda": None, "motivo": None}
    if a["so_codigo"]:
        out["motivo"] = f"a pasta só tem o código (“{pasta}”): não há nome para comparar"
        return out
    if a["nota"] is None:
        out["motivo"] = f"o projeto {p['codigo']} não tem nome para comparar com a pasta"
        return out
    cands = []
    for q in con.execute("""SELECT codigo, titulo, identificacao_original FROM projeto
                             WHERE fundo_codigo=? AND codigo<>? AND mesclado_em IS NULL AND descartado_em IS NULL""", (p["fundo_codigo"], p["codigo"])):
        n = _nota_auto(pasta, q)
        if n is not None:
            cands.append({"codigo": q["codigo"], "titulo": q["titulo"], "nota": n, "previsto": False})
    for q in extras or []:
        n = _nota_auto(pasta, q)
        if n is not None:
            cands.append({"codigo": q["codigo"], "titulo": q["titulo"], "nota": n, "previsto": True})
    cands.sort(key=lambda x: (-x["nota"], x["codigo"]))
    best = cands[0] if cands else None
    seg = cands[1]["nota"] if len(cands) > 1 else 0.0
    out["segunda"] = seg
    if best and best["nota"] >= NOTA_MOVER and best["nota"] - seg >= FOLGA:
        out.update(acao="mover", para=best["codigo"], para_titulo=best["titulo"], para_previsto=best["previsto"], nota=best["nota"],
                   motivo=f"o nome da pasta é {_pct(best['nota'])} parecido com {best['codigo']} (“{best['titulo']}”)"
                          + (f"; o segundo mais parecido tem {_pct(seg)}" if len(cands) > 1 else ""))
        return out
    if not best or best["nota"] < NOTA_CRIAR:
        t = titulo_da_pasta(pasta)
        out["nota"] = best["nota"] if best else 0.0
        if not t:
            out["motivo"] = f"nenhum projeto do fundo combina com a pasta e o nome dela (“{pasta}”) não serve de título"
            return out
        out.update(acao="criar", titulo=t["titulo"], ano=t["ano"], ano_fim=t["ano_fim"],
                   motivo="nenhum projeto do fundo combina com a pasta" + (f" (o mais parecido, {best['codigo']}, tem {_pct(best['nota'])})" if best else ""))
        return out
    out["nota"] = best["nota"]
    if best["nota"] >= NOTA_MOVER:
        out["motivo"] = f"dois projetos combinam com a pasta: {best['codigo']} ({_pct(best['nota'])}) e {cands[1]['codigo']} ({_pct(seg)})"
    else:
        out["motivo"] = (f"o projeto mais parecido, {best['codigo']} (“{best['titulo']}”), tem {_pct(best['nota'])}: "
                         f"entre {_pct(NOTA_CRIAR)} e {_pct(NOTA_MOVER)} uma pessoa confere")
    out["candidatos"] = [{k: c[k] for k in ("codigo", "titulo", "nota")} for c in cands[:3]]
    return out


def planejar(con) -> list[dict]:
    """A prévia: o que o painel faria AGORA com cada lote em "Verificar destino" (em ordem, como a rodada faria). Não grava nada.
    O código de um projeto a criar é o PREVISTO (próximo P do fundo, contando os que a mesma rodada criaria antes)."""
    from .projetos_novos import proximo_numero
    extras: dict[str, list[dict]] = {}
    proximos: dict[str, int] = {}
    out = []
    for l in _lotes_candidatos(con):
        pfundo = con.execute("SELECT fundo_codigo FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
        fundo = pfundo[0] if pfundo else None
        pl = classificar(con, l, extras.get(fundo))
        if not pl:
            continue
        if pl["acao"] == "criar":
            n = proximos.get(fundo) or proximo_numero(con, fundo)
            proximos[fundo] = n + 1
            pl["para"], pl["para_titulo"], pl["para_previsto"] = f"{fundo}-P{n:04d}", pl["titulo"], True
            extras.setdefault(fundo, []).append({"codigo": pl["para"], "titulo": pl["titulo"], "identificacao_original": pl["nome_pasta"]})
        out.append(pl)
    return out


# ---------------- aplicar (só em segundo plano) ----------------
def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, str(codigo), tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def _aplicar_um(con, l, pl: dict, por: str) -> dict:
    """Grava UMA decisão (transação aberta por quem chama; sem commit). Cria o projeto se for o caso."""
    from .projetos_novos import criar_projeto
    para, titulo = pl["para"], None
    if pl["acao"] == "criar":
        novo = criar_projeto(con, pl["fundo"], pl["titulo"], pl["ano"], None, pl["nome_pasta"], ATOR,
                             {"origem": "automatico", "lote_id": l["id"], "nome_pasta": pl["nome_pasta"], "de": l["projeto_codigo"]})
        para, titulo = novo["codigo"], pl["titulo"]
        con.execute("UPDATE projeto SET origem='automatico', ano_fim=? WHERE codigo=?", (pl.get("ano_fim"), para))
    elif pl.get("para_previsto"):
        raise HTTPException(409, "o projeto de destino ainda não existe")
    con.execute("""INSERT INTO destino_auto (lote_id, acao, projeto_antigo, projeto_novo, titulo_criado, nota, segunda, nome_pasta, pasta_qnap, aplicado_por)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (l["id"], pl["acao"], l["projeto_codigo"], para, titulo, pl.get("nota"), pl.get("segunda"), pl["nome_pasta"], l["pasta_qnap"], por))
    det = {"lote_id": l["id"], "projeto": l["projeto_codigo"], "para": para, "acao": pl["acao"], "nota": pl.get("nota"),
           "nome_pasta": pl["nome_pasta"], "motivo": pl.get("motivo"), **({"titulo": titulo} if titulo else {}),
           **({"aplicado_por": por} if por != ATOR else {})}
    _evento(con, "lista", l["id"], EVENTO, ATOR, det)
    _evento(con, "projeto", l["projeto_codigo"], EVENTO, ATOR, det)
    _evento(con, "projeto", para, EVENTO, ATOR, det)
    return {"lote_id": l["id"], "acao": pl["acao"], "de": l["projeto_codigo"], "para": para, "titulo": titulo or pl.get("para_titulo"), "nota": pl.get("nota")}


def _conferir(con, l, pl: dict, r: dict, ultimo_evento: int) -> list[str]:
    """A simulação saiu limpa? (dentro do SAVEPOINT, depois de _aplicar_um)."""
    from .destino_lote import avaliar
    erros = []
    if con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (l["id"],)).fetchone():
        erros.append("o lote ganhou folhas")
    d = con.execute("SELECT fundo_codigo, mesclado_em, descartado_em FROM projeto WHERE codigo=?", (r["para"],)).fetchone()
    if not d or d["fundo_codigo"] != pl["fundo"] or d["mesclado_em"] or d["descartado_em"] or r["para"] == l["projeto_codigo"]:
        erros.append(f"o destino {r['para']} não é um projeto ativo do fundo {pl['fundo']}")
    if pl["acao"] == "criar":
        if con.execute("SELECT 1 FROM evento WHERE codigo=? AND id<=? LIMIT 1", (r["para"], ultimo_evento)).fetchone():
            erros.append(f"o código {r['para']} já foi usado antes")
        try:
            if con.execute("SELECT 1 FROM wp_item WHERE codigo_detectado LIKE ? LIMIT 1", (r["para"] + "%",)).fetchone():
                erros.append(f"o código {r['para']} já existe no site")
        except Exception:  # noqa: BLE001 - banco sem o espelho do site
            pass
    a = avaliar(con, l, completo=False)
    if a["liberado"] or not a.get("automatico"):
        erros.append("o lote não ficou parado esperando o CAMP Vision")
    return erros


def _mesmo_plano(pl: dict, esperado: dict | None) -> bool:
    if not esperado:
        return True
    if pl["acao"] != esperado.get("acao"):
        return False
    if pl["acao"] == "criar":
        return pl.get("titulo") == esperado.get("titulo")
    return pl.get("para") == esperado.get("para") or (bool(esperado.get("para_previsto")) and pl.get("para_titulo") == esperado.get("para_titulo"))


def aplicar_lote(lote_id: int, por: str = ATOR, esperado: dict | None = None) -> dict:
    """Simula o lote (tudo, numa SAVEPOINT desfeita no fim), confere, e só então aplica. Uma transação por lote. Nunca levanta."""
    con = connect()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        l = con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        ok_lote = l and con.execute("SELECT 1 FROM destino_auto WHERE lote_id=?", (lote_id,)).fetchone() is None \
            and any(x["id"] == lote_id for x in _lotes_candidatos(con))
        pl = classificar(con, l) if ok_lote else None
        if not pl or pl["acao"] == "pessoa":
            con.execute("ROLLBACK")
            return {"lote_id": lote_id, "resultado": "pessoa" if pl else "fora", "motivo": (pl or {}).get("motivo") or "o lote não está mais em Verificar destino"}
        if not _mesmo_plano(pl, esperado):
            con.execute("ROLLBACK")
            return {"lote_id": lote_id, "resultado": "mudou", "motivo": "o que o painel faria mudou desde a prévia: veja de novo"}
        ultimo = con.execute("SELECT COALESCE(MAX(id),0) FROM evento").fetchone()[0]
        con.execute("SAVEPOINT simular")
        try:
            r = _aplicar_um(con, l, pl, por)
            erros = _conferir(con, l, pl, r, ultimo)
        except HTTPException as e:
            erros = [str(e.detail)]
        except Exception as e:  # noqa: BLE001
            erros = [f"erro inesperado: {str(e)[:160]}"]
        con.execute("ROLLBACK TO simular")
        con.execute("RELEASE simular")
        if erros:
            con.execute("ROLLBACK")
            return {"lote_id": lote_id, "resultado": "nao_aplicado", "motivo": "; ".join(erros)}
        r = _aplicar_um(con, l, pl, por)
        con.execute("COMMIT")
        return {**r, "resultado": "aplicado"}
    except Exception as e:  # noqa: BLE001 - nunca derruba o laço do coletor
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        return {"lote_id": lote_id, "resultado": "nao_aplicado", "motivo": f"erro inesperado: {str(e)[:160]}"}
    finally:
        con.close()


def _concluido(con, r) -> bool:
    """O CAMP Vision já reorganizou? O lote passou para o projeto novo (reidentificar), foi descartado, ou chegou ao projeto novo
    um lote de OUTRA pasta criado depois da decisão."""
    l = con.execute("SELECT projeto_codigo, descartado_em FROM lista_processamento WHERE id=?", (r["lote_id"],)).fetchone()
    if not l or l["projeto_codigo"] == r["projeto_novo"] or l["descartado_em"]:
        return True
    return con.execute("""SELECT 1 FROM lista_processamento WHERE projeto_codigo=? AND id<>? AND COALESCE(pasta_qnap,'')<>COALESCE(?,'')
                           AND criado_em>=? LIMIT 1""", (r["projeto_novo"], r["lote_id"], r["pasta_qnap"], r["em"])).fetchone() is not None


def estado(con, r) -> str:
    return "concluido" if r["estado"] == "movendo" and _concluido(con, r) else r["estado"]


def atualizar_concluidos(con) -> int:
    """Grava 'concluido' no que o CAMP Vision já reorganizou (sem commit). Só lê o banco."""
    n = 0
    for r in con.execute("SELECT * FROM destino_auto WHERE estado='movendo'").fetchall():
        if _concluido(con, r):
            con.execute("UPDATE destino_auto SET estado='concluido', concluido_em=datetime('now') WHERE id=?", (r["id"],))
            _evento(con, "lista", r["lote_id"], EVENTO + "_concluido", ATOR, {"lote_id": r["lote_id"], "projeto": r["projeto_antigo"], "para": r["projeto_novo"]})
            n += 1
    return n


def do_lote(con, lote_id: int) -> dict | None:
    """A decisão automática ainda valendo para o lote (movendo ou concluído), para o "Verificar destino" e a Fila. None = nenhuma."""
    try:
        r = con.execute("SELECT * FROM destino_auto WHERE lote_id=? AND estado<>'desfeito'", (lote_id,)).fetchone()
    except Exception:  # noqa: BLE001 - banco antes da migração 197
        return None
    if not r:
        return None
    t = con.execute("SELECT titulo FROM projeto WHERE codigo=?", (r["projeto_novo"],)).fetchone()
    return {"id": r["id"], "acao": r["acao"], "para": r["projeto_novo"], "para_titulo": t[0] if t else r["titulo_criado"], "criado": r["acao"] == "criar",
            "nota": r["nota"], "em": r["em"], "estado": estado(con, r)}


def rodada(teto: int = TETO, por: str = ATOR, lotes: list[int] | None = None, forcar: bool = False, progresso=None) -> dict:
    """Uma passada. Sem `forcar` só aplica com destino.automatico = aplicar (o laço do coletor); `forcar` = o admin apertou
    "Aplicar estas N decisões" (vale em simular). Nunca levanta."""
    out = {"aplicados": [], "pessoa": [], "nao_aplicados": [], "concluidos": 0}
    con = connect()
    try:
        out["concluidos"] = atualizar_concluidos(con)
        con.commit()
        m = out["modo"] = modo(con)
        if m == "desligado" or (m != "aplicar" and not forcar):
            return out
        plano = {p["lote_id"]: p for p in planejar(con)}
        ids = [i for i in (lotes if lotes is not None else list(plano)) if i in plano and plano[i]["acao"] != "pessoa"]
        out["pessoa"] = [{"lote_id": i, "resultado": "pessoa", "motivo": plano[i]["motivo"]}
                         for i in (lotes if lotes is not None else list(plano)) if i in plano and plano[i]["acao"] == "pessoa"]
    finally:
        con.close()
    if progresso:
        progresso.total(min(len(ids), teto))
    for lid in ids:
        if len(out["aplicados"]) >= teto:
            break
        r = aplicar_lote(lid, por, plano[lid] if lotes is not None else None)
        {"aplicado": out["aplicados"], "pessoa": out["pessoa"], "fora": out["pessoa"]}.get(r["resultado"], out["nao_aplicados"]).append(r)
        if progresso:
            progresso.feita(1, f"lote {lid}: {r.get('para') or r.get('motivo')}")
    a = len(out["aplicados"])
    out["mensagem"] = (f"{a} lote(s) com destino resolvido pelo painel" if a else "Nenhum lote mudou") + \
        (f"; {len(out['nao_aplicados'])} não aplicado(s): a simulação não saiu limpa" if out["nao_aplicados"] else "")
    return out


def desfazer(con, did: int, por: str) -> dict:
    """Volta o lote para "Verificar destino" (uma pessoa decide; o painel não decide de novo). Projeto criado e ainda vazio é descartado:
    o número P continua gasto. Só enquanto o CAMP Vision não reorganizou a pasta e o lote não tem folhas. Sem commit."""
    r = con.execute("SELECT * FROM destino_auto WHERE id=?", (did,)).fetchone()
    if not r:
        raise HTTPException(404, "Esta decisão do painel não existe")
    if r["estado"] == "desfeito":
        raise HTTPException(409, "Esta decisão já foi desfeita.")
    if estado(con, r) == "concluido":
        raise HTTPException(409, f"O CAMP Vision já reorganizou a pasta em {r['projeto_novo']}: não dá mais para desfazer aqui. Se estiver errado, mova o lote pelo projeto.")
    if con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (r["lote_id"],)).fetchone():
        raise HTTPException(409, "O lote já tem folhas: não dá mais para desfazer.")
    descartado = None
    if r["acao"] == "criar":
        p = con.execute("SELECT codigo, origem, descartado_em, mesclado_em, tainacan_item_id, wp_page_id FROM projeto WHERE codigo=?", (r["projeto_novo"],)).fetchone()
        if p and not p["descartado_em"] and not p["mesclado_em"]:
            if p["tainacan_item_id"] or p["wp_page_id"] or con.execute("SELECT 1 FROM item WHERE projeto_codigo=? LIMIT 1", (p["codigo"],)).fetchone() \
                    or con.execute("SELECT 1 FROM lista_processamento WHERE projeto_codigo=? LIMIT 1", (p["codigo"],)).fetchone():
                raise HTTPException(409, f"O projeto {p['codigo']} criado pelo painel já tem material: não dá mais para desfazer.")
            mot = f"criado pelo painel para o lote {r['lote_id']} e desfeito"
            con.execute("UPDATE projeto SET descartado_em=datetime('now'), descartado_por=?, descartado_motivo=?, atualizado_em=datetime('now') WHERE codigo=?",
                        (por, mot, p["codigo"]))
            _evento(con, "projeto", p["codigo"], "projeto_descartado", por, {"motivo": mot, "lotes": [], "folhas": []})
            descartado = p["codigo"]
    con.execute("UPDATE destino_auto SET estado='desfeito', desfeito_em=datetime('now'), desfeito_por=? WHERE id=?", (por, did))
    det = {"lote_id": r["lote_id"], "projeto": r["projeto_antigo"], "para": r["projeto_novo"], "acao": r["acao"], "nome_pasta": r["nome_pasta"],
           **({"descartado": descartado} if descartado else {})}
    _evento(con, "lista", r["lote_id"], EVENTO + "_desfeito", por, det)
    _evento(con, "projeto", r["projeto_antigo"], EVENTO + "_desfeito", por, det)
    _evento(con, "projeto", r["projeto_novo"], EVENTO + "_desfeito", por, det)
    return {"ok": True, "lote_id": r["lote_id"], "descartado": descartado,
            "mensagem": f"Desfeito: o lote voltou para Verificar destino em {r['projeto_antigo']} (uma pessoa decide)."
                        + (f" O projeto {descartado} foi descartado; o número não é reusado." if descartado else "")}


# ---------------- rotas ----------------
@router.get("/destino-automatico")
def ver(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Modo, prévia (o que o painel faria agora), o que ele já fez (com Desfazer) e os projetos que ele criou. Só lê o banco."""
    con = connect()
    try:
        acoes = []
        for r in con.execute("""SELECT d.*, l.nome AS lote_nome, pa.titulo AS antigo_titulo, pn.titulo AS novo_titulo FROM destino_auto d
                                  LEFT JOIN lista_processamento l ON l.id=d.lote_id LEFT JOIN projeto pa ON pa.codigo=d.projeto_antigo
                                  LEFT JOIN projeto pn ON pn.codigo=d.projeto_novo ORDER BY d.id DESC LIMIT 100""").fetchall():
            e = estado(con, r)
            acoes.append({"id": r["id"], "lote_id": r["lote_id"], "lote_nome": r["lote_nome"], "nome_pasta": r["nome_pasta"], "acao": r["acao"],
                          "de": r["projeto_antigo"], "de_titulo": r["antigo_titulo"], "para": r["projeto_novo"], "para_titulo": r["novo_titulo"],
                          "nota": r["nota"], "autor": r["autor"], "aplicado_por": r["aplicado_por"], "em": r["em"], "estado": e,
                          "desfeito_por": r["desfeito_por"], "desfeito_em": r["desfeito_em"],
                          "pode_desfazer": e == "movendo" and not con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (r["lote_id"],)).fetchone()})
        criados = [dict(x) for x in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.criado_em, d.titulo_criado, d.lote_id, d.nome_pasta,
                                                          (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                                                     FROM projeto p LEFT JOIN destino_auto d ON d.projeto_novo=p.codigo AND d.acao='criar'
                                                    WHERE p.origem='automatico' AND p.descartado_em IS NULL AND p.mesclado_em IS NULL
                                                    ORDER BY p.criado_em DESC, p.codigo DESC""")]
        for c in criados:
            c["titulo_revisado"] = bool(c["titulo_criado"]) and c["titulo"] != c["titulo_criado"]
        return {"modo": modo(con), "teto": TETO, "previa": planejar(con), "acoes": acoes, "criados": criados,
                "regra": {"mover": NOTA_MOVER, "folga": FOLGA, "criar": NOTA_CRIAR}, "pode_aplicar": u["papel"] in ("admin", "master")}
    finally:
        con.close()


class Modo(BaseModel):
    modo: str


@router.post("/destino-automatico/modo")
def mudar_modo(d: Modo, u: dict = Depends(auth.exige("admin"))) -> dict:
    m = (d.modo or "").strip().lower()
    if m not in MODOS:
        raise HTTPException(400, "modo deve ser desligado, simular ou aplicar")
    con = connect()
    try:
        antes = modo(con)
        if not con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (m, u["email"], CFG)).rowcount:
            raise HTTPException(503, "A configuração destino.automatico não existe neste banco (falta a migração 197).")
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config',?,'alterada',?,?)",
                    (CFG, u["email"], json.dumps({"antes": {"valor": antes}, "depois": {"valor": m}}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    txt = {"desligado": "Desligado: o painel não calcula nem aplica nada.", "simular": "Simular: o painel mostra o que faria e não muda nada.",
           "aplicar": f"Aplicar: o painel resolve sozinho, em segundo plano, até {TETO} lotes por vez (simulando cada um antes)."}[m]
    return {"ok": True, "modo": m, "mensagem": txt}


class Aplicar(BaseModel):
    lotes: list[int] = []


@router.post("/destino-automatico/aplicar")
def aplicar(d: Aplicar, u: dict = Depends(auth.exige("admin"))):
    """"Aplicar estas N decisões" (admin): os lotes da prévia, em segundo plano (tarefa), simulando cada um antes. 202 {tarefa_id}."""
    from . import tarefas
    con = connect()
    try:
        if modo(con) == "desligado":
            raise HTTPException(409, "Verificar destino pelo painel está desligado.")
        previa = {p["lote_id"]: p for p in planejar(con)}
    finally:
        con.close()
    ids = [i for i in dict.fromkeys(d.lotes or []) if i in previa and previa[i]["acao"] != "pessoa"][:TETO]
    if not ids:
        raise HTTPException(409, "Nenhuma decisão da prévia para aplicar (ela mudou?). Veja de novo.")

    def rodar(p):
        return rodada(teto=TETO, por=u["email"], lotes=ids, forcar=True, progresso=p)
    return tarefas.iniciar("destino_automatico", "destino", u, rodar, "Verificar destino pelo painel")


@router.post("/destino-automatico/{did}/desfazer")
def desfazer_rota(did: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = desfazer(con, did, u["email"])
        con.commit()
        return r
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@router.get("/campvision/destinos")
def destinos_para_o_cv(request: Request) -> dict:
    """Para o CAMP Vision (rede local ou X-Camp-Token; só leitura): as pastas que o painel decidiu que são de outro projeto e que o
    CAMP Vision ainda precisa reorganizar. Campo/rota novos (CONTRATO_UNICO 1.3): o CAMP Vision antigo não chama e nada quebra."""
    exigir_estacao(request)
    con = connect()
    try:
        out = []
        for r in con.execute("SELECT * FROM destino_auto WHERE estado='movendo' ORDER BY id").fetchall():
            if _concluido(con, r):
                continue
            t = con.execute("SELECT titulo FROM projeto WHERE codigo=?", (r["projeto_novo"],)).fetchone()
            out.append({"id": r["id"], "lote_id": r["lote_id"], "pasta": r["pasta_qnap"], "nome_pasta": r["nome_pasta"], "de": r["projeto_antigo"],
                        "para": r["projeto_novo"], "para_titulo": t[0] if t else r["titulo_criado"], "criado": r["acao"] == "criar",
                        "desde": r["em"], "comando": f"vigia.py --reidentificar {r['projeto_antigo']}"})
        return {"destinos": out}
    finally:
        con.close()
