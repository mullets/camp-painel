"""UX-01 (26/10, P0): a pasta que o CAMP Vision trouxe é MESMO deste projeto? Antes de importar, o painel confere.

Visto no acervo: "Edifício Marambaia (37 folhas)" caiu em F026-P0010 "Cia. Sto Amaro"; "P0001" (só o código) caiu em dois projetos.
Importar levava as folhas ao projeto errado (e dali ao site, com a proveniência errada).

Regra (motor em similaridade.compatibilidade_pasta):
- nota do nome da pasta × título do projeto (e × identificação original dele) abaixo de 0,5 = "Verificar destino";
- pasta só com código/número ("P0001", "F026-P0030") também é "Verificar destino" (não há nome para comparar);
- vale para o lote que o CAMP Vision trouxe (resultado.origem = campvision2) e que ainda NÃO tem folhas no painel. Lista aberta à mão
  ("Nova lista") é de uma pessoa que escolheu o projeto; lote já importado antes desta regra não volta a ser travado.
O lote suspeito não importa (nem pelo botão, nem por "Importar todas", nem sozinho) até uma pessoa escolher:
- "É deste projeto" (com justificativa): fica no Histórico do lote e do projeto (evento destino_confirmado) e o lote importa;
- "Mover para <sugerido>" ou "Criar decisão": abre a decisão lote_destino (admin decide). Mover a pasta de verdade depende de o CAMP Vision
  reidentificar os arquivos (a pasta e o pacote têm o código antigo): o painel não move nada sozinho.
"""
from __future__ import annotations

import json
from pathlib import Path

from .similaridade import LIMIAR_PASTA, compatibilidade_pasta, limpar_nome_de_pasta, tokens_de_pasta

EVENTO_OK = "destino_confirmado"
TIPO_DECISAO = "lote_destino"
PREFIXO_MOTIVO = "Verificar destino"


def chave_decisao(lote_id: int) -> str:
    return f"{TIPO_DECISAO}:{lote_id}"


def _contexto(l) -> dict:
    try:
        r = json.loads(l["resultado"] or "{}")
        return r if isinstance(r, dict) else {}
    except (ValueError, TypeError, IndexError, KeyError):
        return {}


def aplica(con, l) -> bool:
    """A regra vale para este lote? Só o que o CAMP Vision trouxe e que ainda não tem folha no painel."""
    if (_contexto(l).get("origem") or "") != "campvision2":
        return False
    return not con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (l["id"],)).fetchone()


def nome_da_pasta(l) -> str:
    return (l["nome"] or "").strip() or Path(l["pasta_qnap"] or "").name


def nota(pasta: str, projeto) -> float | None:
    """A melhor nota entre o título e a identificação original (o nome da pasta de onde o projeto nasceu)."""
    notas = [n for n in (compatibilidade_pasta(pasta, projeto["titulo"]), compatibilidade_pasta(pasta, projeto["identificacao_original"])) if n is not None]
    return max(notas) if notas else None


def confirmacao(con, l) -> dict | None:
    """Uma pessoa já disse "é deste projeto" para ESTA pasta neste projeto (vale para o lote de complemento da mesma pasta)."""
    r = con.execute("""SELECT e.ator, e.quando, e.detalhe FROM evento e
                        WHERE e.entidade='lista' AND e.tipo=? AND json_valid(e.detalhe) AND json_extract(e.detalhe, '$.projeto')=?
                          AND e.codigo IN (SELECT CAST(id AS TEXT) FROM lista_processamento WHERE pasta_qnap=? AND projeto_codigo=?)
                        ORDER BY e.id DESC LIMIT 1""", (EVENTO_OK, l["projeto_codigo"], l["pasta_qnap"], l["projeto_codigo"])).fetchone()
    if not r:
        return None
    d = json.loads(r["detalhe"])
    return {"por": r["ator"], "em": r["quando"], "justificativa": d.get("justificativa"), "decisao_id": d.get("decisao_id")}


def decisao(con, lote_id: int) -> dict | None:
    r = con.execute("SELECT id, situacao, escolha, escolha_valor FROM decisao WHERE chave=?", (chave_decisao(lote_id),)).fetchone()
    return dict(r) if r else None


def sugestoes(con, l, fundo: str, pasta: str, minha: float | None, limite: int = 3) -> list[dict]:
    """Outros projetos do MESMO fundo cujo nome combina com a pasta (do mais para o menos parecido)."""
    out = []
    for p in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.identificacao_original,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                              FROM projeto p WHERE p.fundo_codigo=? AND p.codigo<>? AND p.mesclado_em IS NULL AND p.descartado_em IS NULL""",
                         (fundo, l["projeto_codigo"])):
        n = nota(pasta, p)
        if n is not None and n >= LIMIAR_PASTA and n > (minha or 0):
            out.append({"codigo": p["codigo"], "titulo": p["titulo"], "ano": p["ano"] or None, "cidade": p["cidade"], "folhas": p["folhas"], "nota": n})
    out.sort(key=lambda x: (-x["nota"], x["codigo"]))
    return out[:limite]


def avaliar(con, l, pacote: dict | None = None, completo: bool = True) -> dict:
    """{suspeito, liberado, nome_pasta, projeto, nota, so_codigo, motivo, sugestoes, confirmado, decisao, amostra}.
    suspeito = o nome não combina; liberado = pode importar (não suspeito, ou uma pessoa confirmou). Não grava nada."""
    p = con.execute("SELECT codigo, titulo, fundo_codigo, identificacao_original FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
    pasta = nome_da_pasta(l)
    out = {"aplica": aplica(con, l), "nome_pasta": pasta, "nome_limpo": limpar_nome_de_pasta(pasta),
           "projeto": {"codigo": l["projeto_codigo"], "titulo": p["titulo"] if p else None}, "nota": None, "so_codigo": False,
           "suspeito": False, "liberado": True, "motivo": None, "sugestoes": [], "confirmado": None, "decisao": None, "amostra": []}
    if not out["aplica"] or not p:
        return out
    n = nota(pasta, p)
    out["nota"] = n
    out["so_codigo"] = not tokens_de_pasta(pasta)
    if out["so_codigo"]:
        out["motivo"] = f"a pasta só tem o código (“{pasta}”), sem nome para comparar com o projeto {p['codigo']} (“{p['titulo']}”)"
    elif n is None:
        out["motivo"] = f"o projeto {p['codigo']} não tem nome para comparar com a pasta (“{pasta}”)"
    elif n < LIMIAR_PASTA:
        out["motivo"] = f"o nome da pasta (“{out['nome_limpo'] or pasta}”) não parece o do projeto {p['codigo']} (“{p['titulo']}”)"
    out["suspeito"] = bool(out["motivo"])
    if not out["suspeito"]:
        return out
    out["confirmado"] = confirmacao(con, l)
    out["decisao"] = decisao(con, l["id"])
    dec = out["decisao"] or {}
    out["liberado"] = bool(out["confirmado"])
    if not out["liberado"] and dec.get("situacao") == "resolvida" and dec.get("escolha") == "outro_projeto":
        out["motivo"] += f"; decidido (decisão {dec['id']}): a pasta é de {dec.get('escolha_valor')}. O CAMP Vision precisa reidentificar a pasta antes"
    if completo:
        out["sugestoes"] = sugestoes(con, l, p["fundo_codigo"], pasta, n)
        docs = (pacote or {}).get("documentos") if isinstance((pacote or {}).get("documentos"), list) else (pacote or {}).get("itens")
        out["amostra"] = [str(d.get("codigo")) for d in (docs or []) if isinstance(d, dict) and d.get("codigo")][:3]
    return out


def bloqueio(con, l) -> str | None:
    """A frase do porquê o lote não importa (None = pode importar). A MESMA para o botão, "Importar todas" e a importação automática."""
    a = avaliar(con, l, completo=False)
    if a["liberado"]:
        return None
    dec = a["decisao"] or {}
    extra = f" Está em Decisões (decisão {dec['id']})." if dec.get("situacao") == "pendente" else " Escolha \"É deste projeto\" ou crie uma decisão."
    return f"{PREFIXO_MOTIVO}: {a['motivo']}.{'' if dec.get('escolha') == 'outro_projeto' else extra}"


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def confirmar(con, l, ator: str, justificativa: str, decisao_id: int | None = None) -> None:
    """"É deste projeto": grava no Histórico do lote e do projeto (quem, quando, por quê). NÃO faz commit."""
    det = {"lote_id": l["id"], "projeto": l["projeto_codigo"], "nome_pasta": nome_da_pasta(l), "justificativa": justificativa,
           **({"decisao_id": decisao_id} if decisao_id else {})}
    _evento(con, "lista", str(l["id"]), EVENTO_OK, ator, det)
    _evento(con, "projeto", l["projeto_codigo"], EVENTO_OK, ator, det)


def abrir_decisao(con, l, ator: str, justificativa: str, destino: str | None) -> int:
    """"Mover para <sugerido>" / "Criar decisão": a pergunta vai para Decisões (admin decide). NÃO faz commit."""
    from . import decisoes
    a = avaliar(con, l)
    p = con.execute("SELECT fundo_codigo, titulo FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
    ctx = {"lote_id": l["id"], "lote_nome": nome_da_pasta(l), "projeto_codigo": l["projeto_codigo"], "projeto_titulo": p["titulo"],
           "motivo": a["motivo"], "sugestoes": a["sugestoes"], "amostra": a["amostra"], "pedido_por": ator, "justificativa": justificativa,
           **({"outro": {"codigo": destino}} if destino else {})}
    did, _ = decisoes.abrir(con, TIPO_DECISAO, chave_decisao(l["id"]), p["fundo_codigo"], nome_da_pasta(l), ctx, "painel")
    det = {"lote_id": l["id"], "projeto": l["projeto_codigo"], "nome_pasta": nome_da_pasta(l), "justificativa": justificativa, "decisao_id": did,
           **({"destino_sugerido": destino} if destino else {})}
    _evento(con, "lista", str(l["id"]), "destino_em_decisao", ator, det)
    _evento(con, "projeto", l["projeto_codigo"], "destino_em_decisao", ator, det)
    return did


def resolver_decisao(con, d, ctx: dict, acao: str, valor: str | None, ator: str) -> dict:
    """Decisão lote_destino resolvida (admin): deste_projeto = libera a importação; outro_projeto = anota o projeto certo
    (o lote continua sem importar: o CAMP Vision reidentifica a pasta). NÃO faz commit."""
    from fastapi import HTTPException
    l = con.execute("SELECT * FROM lista_processamento WHERE id=?", (ctx.get("lote_id"),)).fetchone()
    if not l:
        raise HTTPException(404, "O lote desta decisão não existe mais")
    if acao == "deste_projeto":
        confirmar(con, l, ator, f"Decisão {d['id']}" + (f": {valor}" if valor else ""), d["id"])
        return {"mensagem": f"Anotado: a pasta é de {l['projeto_codigo']}. O lote já pode ser importado."}
    destino = (valor or "").strip().upper()
    if not destino or destino == l["projeto_codigo"]:
        raise HTTPException(400, "Escolha o projeto certo (outro projeto do mesmo fundo)")
    if not con.execute("SELECT 1 FROM projeto WHERE codigo=? AND fundo_codigo=?", (destino, d["fundo_codigo"])).fetchone():
        raise HTTPException(400, "O projeto escolhido não existe neste fundo")
    det = {"lote_id": l["id"], "projeto": l["projeto_codigo"], "para": destino, "nome_pasta": nome_da_pasta(l), "decisao_id": d["id"]}
    _evento(con, "lista", str(l["id"]), "destino_outro_projeto", ator, det)
    _evento(con, "projeto", l["projeto_codigo"], "destino_outro_projeto", ator, det)
    _evento(con, "projeto", destino, "destino_outro_projeto", ator, det)
    return {"mensagem": f"Anotado: a pasta é de {destino}. O lote não importa em {l['projeto_codigo']}; peça ao CAMP Vision para reidentificar a pasta."}
