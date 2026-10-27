"""Fila de decisões: o painel verifica antes de agir e, na dúvida, PERGUNTA.

Tipos (cada um com a sua pergunta e as suas opções; ver TIPOS):
- projeto_parecido: este projeto já existe no fundo? é o mesmo?            (mesmo | novo)
- lote_colide: o lote traz folhas com números que o projeto já usa           (adicionar_ao_fim | ignorar | substituir)
- divergencia: o CAMP Vision leu ano/cidade/cliente diferente do cadastro   (escolher, com o valor escolhido)
- projeto_outro_fundo: há projeto com o mesmo nome em OUTRO fundo            (mesmo | diferente)
- lote_destino: a pasta do lote não parece ser do projeto (UX-01)           (deste_projeto | outro_projeto, com o código)
"""
from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException

from .projetos_novos import criar_projeto
from .similaridade import normalizar


def chave_efetiva(chave_reserva: str, fundo: str, titulo: str) -> str:
    """A chave da estação; sem ela, uma derivada do fundo + nome, para o mesmo pedido repetido cair na MESMA decisão."""
    return chave_reserva or "auto-" + hashlib.sha1(f"{fundo}|{normalizar(titulo)}".encode()).hexdigest()[:16]


def da_chave(con, chave: str):
    d = con.execute("SELECT * FROM decisao WHERE chave=?", (chave,)).fetchone()
    if d:
        return d
    return con.execute("SELECT d.* FROM decisao_chave dc JOIN decisao d ON d.id=dc.decisao_id WHERE dc.chave=?", (chave,)).fetchone()


def pergunta_ligada(con, chave: str) -> bool:
    """26/10: a pergunta por NOME parecido no F9 da estação ('decisoes.parecido_estacao') fica desligada por padrão (configuração)."""
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    except Exception:  # noqa: BLE001  (banco sem a migração 152: desligada)
        return False
    return bool(r) and str(r[0]).strip() == "1"


def abrir_projeto_parecido(con, chave: str, fundo: str, titulo: str, pedido: dict, parecidos: list[dict], origem: str) -> int:
    """Abre (ou devolve, se a chave já tem) a decisão 'é o mesmo projeto?'. NÃO faz commit."""
    ja = da_chave(con, chave)
    if ja:
        return ja["id"]
    # A MESMA pergunta (mesmo fundo + mesmo nome normalizado + mesma estação) já está pendente: não abre outra, só registra a chave nova
    estacao = (pedido or {}).get("estacao") or (pedido or {}).get("estacao_id")
    alvo = normalizar(titulo)
    for d in con.execute("SELECT id, titulo, contexto FROM decisao WHERE situacao='pendente' AND tipo='projeto_parecido' AND fundo_codigo=?", (fundo,)).fetchall():
        if normalizar(d["titulo"]) != alvo:
            continue
        try:
            est_d = (json.loads(d["contexto"]).get("pedido") or {}).get("estacao")
        except ValueError:
            est_d = None
        if estacao and est_d and estacao != est_d:
            continue
        con.execute("INSERT OR IGNORE INTO decisao_chave (chave, decisao_id) VALUES (?,?)", (chave, d["id"]))
        return d["id"]
    return con.execute("INSERT INTO decisao (tipo, chave, fundo_codigo, titulo, contexto, origem) VALUES ('projeto_parecido',?,?,?,?,?)",
                       (chave, fundo, titulo, json.dumps({"pedido": pedido, "candidatos": parecidos}, ensure_ascii=False), origem)).lastrowid


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def resolver(con, did: int, acao: str, projeto_codigo: str | None, ator: str, valor: str | None = None) -> dict:
    """Resolve uma decisão de QUALQUER tipo e aplica a escolha. NÃO faz commit."""
    d = con.execute("SELECT * FROM decisao WHERE id=?", (did,)).fetchone()
    if not d:
        raise HTTPException(404, "Decisão não existe")
    if d["situacao"] != "pendente":
        raise HTTPException(409, "Esta decisão já foi resolvida")
    tipo = d["tipo"] or "projeto_parecido"
    if tipo not in TIPOS:
        raise HTTPException(400, f"Tipo de decisão desconhecido: {tipo}")
    if acao == "descartar":                           # lote de teste, pedido repetido…: encerra sem criar nem mudar nada
        con.execute("UPDATE decisao SET situacao='resolvida', escolha='descartar', resolvida_em=datetime('now'), resolvida_por=? WHERE id=?", (ator, did))
        _evento(con, "decisao", str(did), "decisao_descartada", ator, {"tipo": tipo, "titulo": d["titulo"], "motivo": (valor or "")[:300] or None})
        return {"ok": True, "acao": "descartar", "projeto_codigo": None}
    if acao not in TIPOS[tipo]["opcoes"]:
        raise HTTPException(400, f"Escolha inválida para esta decisão: use {', '.join(TIPOS[tipo]['opcoes'])}")
    if tipo != "projeto_parecido":
        return _resolver_generico(con, d, acao, valor, ator)
    if acao not in ("mesmo", "novo"):
        raise HTTPException(400, "acao deve ser 'mesmo' ou 'novo'")
    pedido = json.loads(d["contexto"]).get("pedido", {})
    if acao == "mesmo":
        if not projeto_codigo:
            raise HTTPException(400, "Escolha o projeto existente")
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=? AND fundo_codigo=?", (projeto_codigo, d["fundo_codigo"])).fetchone():
            raise HTTPException(400, "O projeto escolhido não existe neste fundo")
        codigo = projeto_codigo
        _evento(con, "projeto", codigo, "material_adicionado_ao_existente", ator,
                {"decisao_id": did, "titulo_recebido": d["titulo"], "origem": d["origem"], "identificacao_original": pedido.get("identificacao_original")})
    else:
        real = None if d["chave"].startswith("auto-") else d["chave"]
        novo = criar_projeto(con, d["fundo_codigo"], d["titulo"], pedido.get("ano"), pedido.get("cidade"), pedido.get("identificacao_original"), ator,
                             {"titulo": d["titulo"], "origem": d["origem"] if d["origem"] == "estacao" else "painel", "identificacao_original": pedido.get("identificacao_original"),
                              "operador": pedido.get("operador"), "chave_reserva": real, "decisao_id": did,
                              "proximo_p_local": pedido.get("proximo_p_local")}, reservado_por=None)
        codigo = novo["codigo"]
    con.execute("UPDATE decisao SET situacao='resolvida', resolucao=?, escolha=?, projeto_codigo=?, resolvida_em=datetime('now'), resolvida_por=? WHERE id=?",
                (acao, acao, codigo, ator, did))
    _evento(con, "decisao", str(did), "decisao_resolvida", ator, {"acao": acao, "projeto": codigo, "titulo": d["titulo"]})
    return {"ok": True, "acao": acao, "projeto_codigo": codigo}


# ---------------------------------------------------------------- vários tipos
TIPOS = {
    "projeto_parecido": {"rotulo": "Projeto parecido", "opcoes": ("mesmo", "novo")},
    "lote_colide": {"rotulo": "Lote com números repetidos", "opcoes": ("adicionar_ao_fim", "ignorar", "substituir")},
    "divergencia": {"rotulo": "Dado diferente do cadastro", "opcoes": ("escolher",)},
    "projeto_outro_fundo": {"rotulo": "Mesmo nome em outro fundo", "opcoes": ("mesmo", "diferente")},
    "lote_destino": {"rotulo": "Verificar destino do lote", "opcoes": ("deste_projeto", "outro_projeto")},
}
CAMPOS_DIVERGENCIA = {"ano": "ano", "cidade": "cidade", "cliente": "cliente"}
ROTULO_CAMPO = {"ano": "o ano", "cidade": "a cidade", "cliente": "o cliente"}


def contexto(d) -> dict:
    try:
        return json.loads(d["contexto"] or "{}")
    except (ValueError, TypeError):
        return {}


def pergunta(d, ctx: dict | None = None) -> str:
    """A pergunta de cada tipo em português simples (lista de Decisões, Painel, tarefas)."""
    ctx = contexto(d) if ctx is None else ctx
    tipo = d["tipo"] or "projeto_parecido"
    if tipo == "lote_colide":
        n = len(ctx.get("colisoes") or [])
        return f"O lote “{ctx.get('lote_nome') or d['titulo']}” traz {n} folha{'s' if n != 1 else ''} com número que {ctx.get('projeto_codigo')} já usa. O que fazer?"
    if tipo == "divergencia":
        return f"{ctx.get('projeto_codigo')}: o CAMP Vision leu {ROTULO_CAMPO.get(ctx.get('campo'), ctx.get('campo'))} “{ctx.get('valor_cv')}”, e o cadastro diz “{ctx.get('valor_cadastro')}”. Qual vale?"
    if tipo == "projeto_outro_fundo":
        o = ctx.get("outro") or {}
        return f"Já existe “{o.get('titulo')}” no fundo {o.get('fundo_codigo')} ({o.get('codigo')}). É o mesmo que {ctx.get('projeto_codigo')}?"
    if tipo == "lote_destino":
        return f"A pasta “{ctx.get('lote_nome') or d['titulo']}” é mesmo do projeto {ctx.get('projeto_codigo')} (“{ctx.get('projeto_titulo') or ''}”)?"
    c = (ctx.get("candidatos") or [{}])[0]
    return f"“{d['titulo']}” é o mesmo projeto que “{c.get('titulo')}”?" if c.get("titulo") else f"“{d['titulo']}”: projeto novo ou um que já existe?"


def abrir(con, tipo: str, chave: str, fundo: str, titulo: str, ctx: dict, origem: str = "painel") -> tuple[int, bool]:
    """Abre uma decisão de um tipo novo (idempotente pela chave). Devolve (id, criada_agora). NÃO faz commit."""
    ja = da_chave(con, chave)
    if ja:
        return ja["id"], False
    did = con.execute("INSERT INTO decisao (tipo, chave, fundo_codigo, titulo, contexto, origem) VALUES (?,?,?,?,?,?)",
                      (tipo, chave, fundo, titulo, json.dumps(ctx, ensure_ascii=False), origem)).lastrowid
    _evento(con, "decisao", str(did), "decisao_aberta", origem, {"tipo": tipo, "titulo": titulo, "projeto": ctx.get("projeto_codigo")})
    return did, True


def _resolver_generico(con, d, acao: str, valor: str | None, ator: str) -> dict:
    ctx, did, tipo = contexto(d), d["id"], d["tipo"]
    proj = ctx.get("projeto_codigo")
    resultado: dict = {}
    if tipo == "lote_colide":
        from .importador_lote import aplicar_colisao
        resultado = aplicar_colisao(con, d, ctx, acao, ator)
        ctx["resultado"] = resultado
    elif tipo == "divergencia":
        resultado = _aplicar_divergencia(con, ctx, valor, ator, did)
        ctx["resultado"] = resultado
    elif tipo == "projeto_outro_fundo":
        outro = (ctx.get("outro") or {}).get("codigo")
        for a, b in ((proj, outro), (outro, proj)):
            if a:
                _evento(con, "projeto", a, "mesmo_projeto_em_outro_fundo" if acao == "mesmo" else "projeto_diferente_em_outro_fundo", ator,
                        {"decisao_id": did, "outro": b})
        resultado = {"mensagem": f"Anotado: {proj} e {outro} são {'o mesmo projeto' if acao == 'mesmo' else 'projetos diferentes'}."}
    elif tipo == "lote_destino":
        from .destino_lote import resolver_decisao
        resultado = resolver_decisao(con, d, ctx, acao, valor, ator)
        ctx["resultado"] = resultado
    con.execute("""UPDATE decisao SET situacao='resolvida', escolha=?, escolha_valor=?, projeto_codigo=?, contexto=?,
                   resolvida_em=datetime('now'), resolvida_por=? WHERE id=?""",
                (acao, valor, proj, json.dumps(ctx, ensure_ascii=False), ator, did))
    _evento(con, "decisao", str(did), "decisao_resolvida", ator, {"tipo": tipo, "acao": acao, "valor": valor, "projeto": proj, "titulo": d["titulo"]})
    return {"ok": True, "tipo": tipo, "acao": acao, "valor": valor, "projeto_codigo": proj, **resultado}


# ---------------- divergência: o CV2 diz um ano/cidade/cliente diferente do cadastro
def _norm_valor(campo: str, v) -> str:
    if v in (None, "", 0, "0"):
        return ""
    if campo == "ano":
        t = str(v).strip()[:4]
        return t if t.isdigit() else ""
    return normalizar(str(v))


def candidatos_divergencia(campo: str, atual, bloco: dict, documentos: list | None) -> list[dict]:
    """Os valores possíveis, cada um com de onde veio: cadastro, o CAMP Vision e as fontes que ele consultou (pasta, carimbo...)."""
    vistos: dict[str, dict] = {}

    def soma(v, fonte):
        n = _norm_valor(campo, v)
        if not n:
            return
        c = vistos.setdefault(n, {"valor": str(v).strip()[:4] if campo == "ano" else str(v).strip(), "fontes": []})
        if fonte not in c["fontes"]:
            c["fontes"].append(fonte)
    soma(atual, "cadastro do painel")
    soma(bloco.get(campo), "CAMP Vision")
    fontes = (bloco.get("fontes") or {}).get(campo) or {}
    if isinstance(fontes, dict):
        for nome, v in fontes.items():
            soma(v, {"pasta": "nome da pasta", "info_projeto": "ficha do projeto", "carimbo": "carimbo das folhas"}.get(nome, str(nome)))
    if campo == "ano" and isinstance(documentos, list):
        for c in vistos.values():
            c["folhas"] = sum(1 for x in documentos if isinstance(x, dict) and _norm_valor("ano", x.get("ano")) == _norm_valor("ano", c["valor"]))
    return list(vistos.values())


def abrir_divergencias(con, projeto_codigo: str, pacote: dict, lote_id: int | None = None) -> list[int]:
    """Depois de importar um lote: para cada campo (ano, cidade, cliente) em que o CV2 diz algo DIFERENTE do que já está
    no cadastro, abre a decisão 'divergencia' com os candidatos. Campo vazio no painel não é divergência (é sugestão, ver saidas_cv)."""
    bloco = pacote.get("projeto") if isinstance(pacote, dict) else None
    p = con.execute("SELECT codigo, fundo_codigo, titulo, ano, cidade, cliente FROM projeto WHERE codigo=?", (projeto_codigo,)).fetchone()
    if not isinstance(bloco, dict) or not p:
        return []
    docs = pacote.get("documentos") if isinstance(pacote.get("documentos"), list) else pacote.get("itens")
    abertas = []
    for campo, coluna in CAMPOS_DIVERGENCIA.items():
        cv, atual = _norm_valor(campo, bloco.get(campo)), _norm_valor(campo, p[coluna])
        if not cv or not atual or cv == atual:
            continue
        ctx = {"projeto_codigo": p["codigo"], "projeto_titulo": p["titulo"], "lote_id": lote_id, "campo": campo,
               "valor_cadastro": str(p[coluna]), "valor_cv": str(bloco.get(campo)).strip(),
               "candidatos": candidatos_divergencia(campo, p[coluna], bloco, docs)}
        did, nova = abrir(con, "divergencia", f"divergencia:{p['codigo']}:{campo}:{cv}", p["fundo_codigo"], p["titulo"], ctx, "campvision")
        if nova:
            abertas.append(did)
    return abertas


def fechar_divergencias_respondidas(con, projeto_codigo: str, ator: str) -> list[int]:
    """Exaustão CAMP-106 (decisões iguais): a decisão 'divergencia' (o CAMP Vision leu ano/cidade/cliente diferente do cadastro) e a pergunta da
    aba Dados ("Usar 1978 no projeto") são a MESMA pergunta. Quando o cadastro passa a dizer o que o CAMP Vision leu, a decisão já foi respondida:
    fecha sozinha, com registro, em vez de ficar esperando de novo na fila. NÃO faz commit."""
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (projeto_codigo,)).fetchone()
    if not p:
        return []
    fechadas = []
    for d in con.execute("SELECT id, contexto FROM decisao WHERE situacao='pendente' AND tipo='divergencia' AND contexto LIKE ?", (f'%"{projeto_codigo}"%',)).fetchall():
        ctx = contexto(d)
        campo = ctx.get("campo")
        if ctx.get("projeto_codigo") != projeto_codigo or campo not in CAMPOS_DIVERGENCIA:
            continue
        atual = _norm_valor(campo, p[CAMPOS_DIVERGENCIA[campo]])
        if atual and atual == _norm_valor(campo, ctx.get("valor_cv")):
            con.execute("UPDATE decisao SET situacao='resolvida', escolha='escolher', escolha_valor=?, projeto_codigo=?, resolvida_em=datetime('now'), resolvida_por=? WHERE id=?",
                        (str(p[CAMPOS_DIVERGENCIA[campo]]), projeto_codigo, ator, d["id"]))
            _evento(con, "decisao", str(d["id"]), "decisao_resolvida", ator, {"acao": "escolher", "valor": p[CAMPOS_DIVERGENCIA[campo]],
                                                                              "motivo": "o cadastro do projeto já diz o que o CAMP Vision leu"})
            fechadas.append(d["id"])
    return fechadas


def _aplicar_divergencia(con, ctx: dict, valor: str | None, ator: str, did: int) -> dict:
    campo, proj = ctx.get("campo"), ctx.get("projeto_codigo")
    if campo not in CAMPOS_DIVERGENCIA:
        raise HTTPException(400, "Campo inválido")
    validos = {_norm_valor(campo, c.get("valor")): c.get("valor") for c in ctx.get("candidatos") or []}
    n = _norm_valor(campo, valor)
    if not n or n not in validos:
        raise HTTPException(400, "Escolha um dos valores mostrados")
    escolhido = validos[n]
    atual = con.execute(f"SELECT {CAMPOS_DIVERGENCIA[campo]} FROM projeto WHERE codigo=?", (proj,)).fetchone()
    if atual is None:
        raise HTTPException(404, "O projeto não existe mais")
    if _norm_valor(campo, atual[0]) == n:
        return {"mudou": False, "mensagem": f"O cadastro de {proj} continua com {ROTULO_CAMPO[campo]} “{atual[0]}”."}
    novo = int(escolhido) if campo == "ano" else escolhido
    con.execute(f"UPDATE projeto SET {CAMPOS_DIVERGENCIA[campo]}=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, proj))
    _evento(con, "projeto", proj, "dado_escolhido_na_divergencia", ator, {"decisao_id": did, "campo": campo, "antes": atual[0], "depois": novo})
    return {"mudou": True, "mensagem": f"{proj}: {ROTULO_CAMPO[campo]} passou de “{atual[0]}” para “{novo}”."}


# ---------------- projeto com o mesmo nome em outro fundo
def abrir_outro_fundo(con, projeto_codigo: str, outros: list[dict], origem: str = "campvision", lote_id: int | None = None) -> list[int]:
    p = con.execute("SELECT codigo, fundo_codigo, titulo, ano, cidade FROM projeto WHERE codigo=?", (projeto_codigo,)).fetchone()
    if not p:
        return []
    ids = []
    for o in outros:
        par = sorted([p["codigo"], o["codigo"]])
        ctx = {"projeto_codigo": p["codigo"], "projeto_titulo": p["titulo"], "ano": p["ano"] or None, "cidade": p["cidade"], "lote_id": lote_id, "outro": o}
        did, nova = abrir(con, "projeto_outro_fundo", f"outro_fundo:{par[0]}:{par[1]}", p["fundo_codigo"], p["titulo"], ctx, origem)
        if nova:
            ids.append(did)
    return ids
