"""Lê TUDO o que o CAMP Vision 2 grava em <pasta do projeto>/catalogacao/ (contrato 2.1) para a tela mostrar.
Só leitura: o painel nunca escreve em catalogacao/ nem no QNAP. Arquivo ausente ou fora do formato NÃO derruba nada:
vira None ('não veio do CAMP Vision') ou o texto cru com o aviso de formato mudado."""
from __future__ import annotations

import json
import re
from pathlib import Path

CAMPOS_PROJETO = ("titulo", "ano", "cidade", "uf", "cliente", "endereco")
_COLUNA = {"titulo": "titulo", "ano": "ano", "cidade": "cidade", "uf": "uf", "cliente": "cliente", "endereco": "endereco_obra"}


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return {"_ilegivel": True}


def _texto(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else None
    except OSError:
        return None


def ler_relatorio(texto: str | None) -> dict | None:
    """O relatório do lote tem 8 partes fixas: 'N. Título' e itens recuados ('nenhum' quando vazio) — nucleo/entrada.py relatorio_lote (CV2 f8c8a69)."""
    if texto is None:
        return None
    partes, atual = [], None
    for ln in texto.splitlines():
        m = re.match(r"^(\d+)\.\s+(.+?)\s*$", ln)
        if m:
            atual = {"n": int(m.group(1)), "titulo": m.group(2), "itens": []}
            partes.append(atual)
        elif atual is not None and ln.startswith("   ") and ln.strip() and ln.strip() != "nenhum":
            atual["itens"].append(ln.strip())
    out = {"texto": texto, "partes": partes, "formato_ok": len(partes) >= 6 and [p["n"] for p in partes][:6] == [1, 2, 3, 4, 5, 6], "alerta_origem": None}
    p1 = next((p for p in partes if p["n"] == 1), None)
    if p1 and p1["itens"]:
        m = re.search(r"(\d+) arquivo\(s\) na origem, (\d+) arquivado\(s\), (\d+) documento\(s\)", p1["itens"][0])
        if m:
            origem, arquivados, docs = (int(x) for x in m.groups())
            out["numeros"] = {"origem": origem, "arquivados": arquivados, "documentos": docs}
            if origem != arquivados:   # ALERTA, não bloqueio (decisão do Rafa em aberto; a troca para bloqueio fica concentrada aqui)
                out["alerta_origem"] = f"{origem} arquivo(s) na origem, mas {arquivados} arquivado(s): {origem - arquivados} não chegaram ao acervo."
    return out


def ler_orientacao(texto: str | None) -> dict | None:
    if texto is None:
        return None
    incertas: list[str] = []
    linhas = []
    for ln in texto.splitlines():
        if ":" in ln and not ln.lower().startswith("orientação aplicada"):
            rot, _, lista = ln.partition(":")
            ds = [d.strip() for d in lista.split(",") if re.fullmatch(r"D\d+", d.strip())]
            linhas.append({"rotulo": rot.strip(), "folhas": ds})
            if rot.strip().lower().startswith("incerta"):
                incertas.extend(ds)
    return {"texto": texto, "linhas": linhas, "incertas": incertas}


ROTULO_ACEITE = {"contagem_origem_igual_saida": "Contagem de origem igual à de saída", "sem_autoria_divergente": "Nenhuma folha com autoria divergente",
                 "folhas_autoria_nao_confirmada": "Folhas com autoria não confirmada (só contagem, não bloqueia)",
                 "duplicatas_marcadas": "Duplicatas marcadas (só a única vai ao site)", "orientacao_incerta_zerada": "Orientação incerta zerada ou revisada",
                 "serie_incerta_zerada": "Série incerta zerada", "sem_plausibilidade": "Nenhum campo preenchido por plausibilidade",
                 "documentacao_nao_e_obra": "Documentação não classificada como obra", "backtest_ok": "Back-test da regra ≥ 85%",
                 "exif_conferido": "EXIF conferido", "relatorio_gerado": "Relatório de fim de lote gerado"}


def ler_aceite(pasta: str | Path) -> dict | None:
    """CV2 §10 (contrato 9.4): o "aceite" do JSON de lote mais recente em catalogacao/lotes/. None = o CV2 não gravou."""
    d = Path(pasta) / "catalogacao" / "lotes"
    if not d.is_dir():
        return None
    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        j = _json(f)
        if isinstance(j, dict) and isinstance(j.get("aceite"), dict):
            return {**j["aceite"], "_arquivo": f.name}
    return None


def itens_aceite(aceite: dict | None) -> list[dict]:
    """Os itens do checklist como lista {chave, rotulo, ok, detalhe} (ok None = não informado)."""
    if not aceite:
        return []
    out = []
    for k, v in aceite.items():
        if k in ("publicavel", "pendencias") or k.startswith("_"):
            continue
        ok = v.get("ok") if isinstance(v, dict) else v if isinstance(v, bool) else None
        det = (v.get("contagem") if isinstance(v, dict) else v if isinstance(v, int) and not isinstance(v, bool) else None)   # CV2 2.4: chave só com a contagem
        it = {"chave": k, "rotulo": ROTULO_ACEITE.get(k, k.replace("_", " ").capitalize()), "ok": ok, "detalhe": det}
        if isinstance(v, dict) and ok is not True:   # UX-08: se o CAMP Vision mandou a lista (ex.: os arquivos sem EXIF conferido), a tela mostra arquivo e motivo
            from .avisos_cv import _arquivos_em
            arqs = _arquivos_em([{"exif_" + str(kk): vv for kk, vv in v.items()}])
            if arqs:
                it["arquivos"] = arqs
        out.append(it)
    return out


def _rotulo_pendencia(x) -> str | None:
    """Pendência do CV2 em texto para gente: o CV2 às vezes manda só a CHAVE ("orientacao_incerta_zerada; publicavel").
    Chave conhecida vira o rótulo; "publicavel" é a conclusão (não um motivo) e sai."""
    t = str(x.get("mensagem") or x.get("item") or x) if isinstance(x, dict) else str(x)
    t = t.strip()
    if not t or t == "publicavel":
        return None
    if t in ROTULO_ACEITE:
        return ROTULO_ACEITE[t]
    return t.replace("_", " ").capitalize() if re.fullmatch(r"[a-z0-9_]+", t) else t


def motivos_aceite(aceite: dict | None) -> list[str]:
    if not aceite:
        return []
    pend = aceite.get("pendencias")
    if isinstance(pend, list) and pend:
        out = [r for r in (_rotulo_pendencia(x) for x in pend) if r]
        if out:
            return list(dict.fromkeys(out))
    return [i["rotulo"] for i in itens_aceite(aceite) if i["ok"] is False]


# O aceite é uma FOTO do momento da leitura. Os pontos que pedem OLHO HUMANO a conferência do painel resolve (aviso de 14/10, F009-P0060):
# basta o lote aprovado OU todas as folhas do lote já conferidas. Os outros (contagem, EXIF, relatório…) só o CAMP Vision resolve.
RESOLVE_CONFERENCIA = frozenset({"orientacao_incerta_zerada", "serie_incerta_zerada", "duplicatas_marcadas", "sem_autoria_divergente"})
SO_AVISO = frozenset({"sem_autoria_divergente"})   # CAMP-046 (contrato 2.4): autoria não confirmada é aviso, nunca trava


def conferencia_do_lote(con, lote_id: int) -> dict:
    """Quanto do lote já passou por uma pessoa no painel (duplicatas não contam: não vão ao site)."""
    l = con.execute("SELECT aprovado_em FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
    tot, pend = con.execute("""SELECT COUNT(*), COALESCE(SUM(revisao='pendente'),0) FROM item
                               WHERE lote_id=? AND projeto_codigo=(SELECT projeto_codigo FROM lista_processamento WHERE id=?) AND duplicata_de IS NULL""", (lote_id, lote_id)).fetchone()
    return {"aprovado": bool(l and l[0]), "total": int(tot or 0), "pendentes": int(pend or 0)}


def avaliar_aceite(aceite: dict | None, conferencia: dict | None = None) -> dict | None:
    """A regra ÚNICA (publicação e tela): o aceite do CV2 somado ao que já foi conferido no painel.
    situacao: 'aprovado' (o CV2 aprovou ou só sobrou aviso) | 'resolvido' (reprovado só pelo que a conferência resolve, e foi conferido)
    | 'reprovado' (falta algo). Cada item ganha 'estado': ok | resolvido | aviso | falta | info. 'faltam' diz o que fazer, sem código cru."""
    if not aceite:
        return None
    cf = conferencia or {}
    conferido = bool(cf.get("aprovado")) or (cf.get("total", 0) > 0 and cf.get("pendentes", 1) == 0)
    pend = int(cf.get("pendentes") or 0)
    itens, faltam = [], []
    for i in itens_aceite(aceite):
        if i["ok"] is True:
            estado = "ok"
        elif i["ok"] is None:
            estado = "info"
        elif i["chave"] in SO_AVISO:
            estado = "aviso"
        elif i["chave"] in RESOLVE_CONFERENCIA and conferido:
            estado = "resolvido"
        elif i["chave"] in RESOLVE_CONFERENCIA and pend and cf.get("total", 0):
            # A própria folha existe no painel e ainda aguarda a pessoa:
            # a tarefa humana é conferir, nunca obedecer ao CV2.
            estado = "falta"
            faltam.append({"chave": i["chave"], "rotulo": i["rotulo"], "acao": "conferir",
                           "como": f"Conferir {pend} folha(s) pendente(s) no painel"})
        else:
            # Contagem de arquivo, EXIF e avaliação automática são alertas de
            # proveniência; não exigem reprocessar todo o lote nem impedem o
            # trabalho já validado por uma pessoa.
            estado = "aviso"
        itens.append({**i, "estado": estado})
    reprovado_cv = aceite.get("publicavel") is False
    # Mesmo que publicavel=false no JSON, isso é parecer da máquina,
    # nunca decisão arquivística do painel. Guardamos os motivos em "motivos".
    if faltam:
        situacao = "reprovado"  # SOMENTE folhas existentes ainda pedem conferência
    elif reprovado_cv:
        situacao = "resolvido" if conferido else "aviso"
    else:
        situacao = "aprovado"
    return {"situacao": situacao, "publicavel_cv": aceite.get("publicavel"), "itens": itens, "faltam": faltam,
            "motivos": motivos_aceite(aceite), "conferencia": {"conferido": conferido, "pendentes": pend, "total": int(cf.get("total") or 0)}}


# UX-37 (F026-P0030, 27/10): o CAMP Vision gravou como UF sugerida o texto quebrado de uma chamada de ferramenta do modelo
# ('<parameter name="valor">null'). O painel mostrava "sugestão: UF <parameter …>null" com o botão "Usar …" e contava 1 sugestão na
# pendência. Valor vazio, "null"/"None"/"undefined" ou com marcação (<parameter, <invoke, </…>) não é sugestão: é ignorado aqui, na
# entrada (o contrato com o CV2 não muda; pendência no campvision-new: não gravar isso).
_MARCACAO = re.compile(r"<\s*/|<\s*(parameter|invoke|function|antml|tool)\b", re.I)


def valor_sugerido_valido(v) -> bool:
    """O valor que o CAMP Vision sugeriu serve para mostrar e usar? Não: vazio, null/None/undefined, ou com marcação de ferramenta."""
    if v is None or isinstance(v, (dict, list, bool)):
        return False
    t = str(v).strip()
    return bool(t) and t.strip("\"'").lower() not in ("null", "none", "undefined", "nil", "nan") and not _MARCACAO.search(t)


def sugestoes_projeto(pacote: dict | None, projeto: dict) -> list[dict]:
    """Campos do bloco 'projeto' do pacote como SUGESTÃO. Só sugere onde o painel está vazio (ou com o título provisório 'P0001'):
    nunca propõe trocar o que uma pessoa já escreveu."""
    if not isinstance(pacote, dict) or not isinstance(pacote.get("projeto"), dict):
        return []
    bp, out = pacote["projeto"], []
    for campo in CAMPOS_PROJETO:
        sug = bp.get(campo)
        sug = str(sug).strip() if valor_sugerido_valido(sug) else ""      # UX-37: valor quebrado = sem sugestão
        atual = projeto.get(_COLUNA[campo])
        atual_txt = "" if atual in (None, 0, "0") else str(atual).strip()
        provisorio = campo == "titulo" and bool(re.fullmatch(r"P\d{4}", atual_txt))
        if sug and (not atual_txt or provisorio) and sug != atual_txt:
            out.append({"campo": campo, "sugerido": sug, "atual": atual_txt or None, "fontes": (bp.get("fontes") or {}).get(campo)})
    return out


_COD_FOLHA = re.compile(r"F\d{3}-P\d{4}-\d{4}-S\d{2}-D\d{5}")


def _codigos_em(x) -> list[str]:
    """Códigos de folha citados num item de proposta do CAMP Vision (texto, lista ou dicionário em qualquer formato)."""
    return list(dict.fromkeys(_COD_FOLHA.findall(json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x)))


def obras_na_pasta(pacote: dict | None, propostas) -> dict | None:
    """20/10 (CAMP-126, F026-P0009): "8 obras distintas pelo código de unidade — ver propostas.obras_na_pasta". Agrupa as folhas do pacote
    pelo `codigo_unidade` (campo do contrato em documentos[]) para a pessoa decidir se são partes do mesmo conjunto ou projetos diferentes.
    Só existe quando o CAMP Vision apontou (aviso de obras distintas ou propostas.obras_na_pasta com itens) e há 2+ códigos de unidade.
    Itens de obras_na_pasta que tragam códigos de folha completam os grupos (o formato do item não é fixo no contrato)."""
    pac = pacote if isinstance(pacote, dict) else {}
    lista = (propostas or {}).get("obras_na_pasta") if isinstance(propostas, dict) else None
    lista = lista if isinstance(lista, list) else []
    avisou = any(re.search(r"obras?\s+distintas|obras_na_pasta", str(a), re.I) for a in (pac.get("avisos") or []))
    if not (avisou or lista):
        return None
    grupos: dict[str, list[str]] = {}
    docs = pac.get("documentos") or pac.get("itens") or []
    for d in docs if isinstance(docs, list) else []:
        if isinstance(d, dict) and d.get("codigo"):
            u = str(d.get("codigo_unidade") or "").strip()
            if u:
                grupos.setdefault(u, []).append(str(d["codigo"]))
    for x in lista:
        if isinstance(x, dict):
            u = str(x.get("codigo_unidade") or x.get("unidade") or x.get("obra") or "").strip()
            if u:
                g = grupos.setdefault(u, [])
                g.extend(c for c in _codigos_em(x) if c not in g)
    sem = [str(d["codigo"]) for d in (docs if isinstance(docs, list) else []) if isinstance(d, dict) and d.get("codigo") and not str(d.get("codigo_unidade") or "").strip()]
    if len(grupos) < 2:
        return None
    return {"grupos": [{"unidade": u, "folhas": f} for u, f in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
            "sem_unidade": sem, "propostas": len(lista)}


# CAMP-134 (21/10): o comparacao.json REAL do CV2 (nucleo/releitura.py) é {"resumo": {...}, "documentos": {<folha>: {"mudou": {<campo>:
# {"antes", "agora", "confianca_agora"}}, "preencheu": [...], "erro": ""}}}. O painel lia cada chave do topo como se fosse uma folha
# ("resumo" e "documentos" viravam duas "folhas" com dezenas de Aceitar/Ignorar sem sentido). O formato antigo {<folha>: {<campo>:
# {"antes","agora"}}} continua aceito. Campos com nome do CV2 (titulo_prancha) e do painel (titulo) valem os dois.
CAMPO_RELEITURA_FOLHA = {"titulo_prancha": "titulo", "titulo": "titulo", "escala": "escala", "folha": "folha", "ano": "ano_folha",
                         "tipo": "tipo_documento", "endereco": "endereco_folha", "cliente": "cliente_folha"}
ROTULO_CAMPO_CV = {"titulo_prancha": "Título", "titulo": "Título", "escala": "Escala", "folha": "Nº da folha", "ano": "Ano", "tipo": "Tipo",
                   "endereco": "Endereço", "cliente": "Cliente", "data": "Data", "projeto": "Projeto", "arquiteto": "Arquiteto",
                   "escritorio": "Escritório", "cidade": "Cidade", "uf": "UF", "total_folhas": "Total de folhas", "codigo_serie": "Código de série",
                   "codigo_unidade": "Código de unidade", "revisao": "Revisão"}
_COD_FOLHA = re.compile(r"F\d{3}-P\d{4}-\d{4}-S\d{2}-D\d{5}", re.I)


def normalizar_comparacao(comp) -> dict:
    """{<código da folha>: {<campo>: {"antes", "agora"}}} a partir dos dois formatos; o que não for folha (resumo etc.) fica de fora."""
    if not isinstance(comp, dict) or comp.get("_ilegivel"):
        return {}
    docs = comp.get("documentos") if isinstance(comp.get("documentos"), dict) else comp
    out = {}
    for chave, v in docs.items():
        m = _COD_FOLHA.search(str(chave))
        if not m or not isinstance(v, dict):
            continue
        campos = v.get("mudou") if isinstance(v.get("mudou"), dict) else v
        mud = {c: {"antes": str((x or {}).get("antes") or ""), "agora": str((x or {}).get("agora") or "")}
               for c, x in campos.items() if isinstance(x, dict) and ("antes" in x or "agora" in x)}
        mud = {c: x for c, x in mud.items() if x["antes"] != x["agora"]}
        if mud:
            out.setdefault(m.group(0).upper(), {}).update(mud)
    return out


def ler_saidas(pasta: str | Path, projeto: dict, respostas: dict | None = None, conferencia: dict | None = None) -> dict:
    cat = Path(pasta) / "catalogacao"
    if not cat.is_dir():
        return {"existe": False, "motivo": "esta pasta não tem catalogacao/ (o CAMP Vision ainda não entregou)"}
    pacote = _json(cat / "pacote_tainacan.json")
    pac = pacote if isinstance(pacote, dict) and not pacote.get("_ilegivel") else None
    propostas = _json(cat / "propostas.json")
    if propostas is None and pac:
        propostas = pac.get("propostas")
    releituras = []
    rr = cat / "releituras"
    if rr.is_dir():
        for d in sorted((x for x in rr.iterdir() if x.is_dir()), reverse=True)[:10]:
            comp = _json(d / "comparacao.json")
            if comp is not None:
                norm = normalizar_comparacao(comp)
                resumo = comp.get("resumo") if isinstance(comp, dict) and isinstance(comp.get("resumo"), dict) else None
                releituras.append({"quando": d.name, "comparacao": norm,   # CAMP-134: já normalizado ({folha: {campo: {antes, agora}}})
                                   "mudancas": [{"codigo": cod, "campo": c, "rotulo": ROTULO_CAMPO_CV.get(c, c.replace("_", " ")), "antes": x["antes"],
                                                 "agora": x["agora"], "aplica": c in CAMPO_RELEITURA_FOLHA and bool(x["agora"])}
                                                for cod, cs in sorted(norm.items()) for c, x in sorted(cs.items())],
                                   "resumo": {k: resumo.get(k) for k in ("escopo", "motivo", "pedido_por", "relidos", "com_mudanca", "relido_em") if k in resumo} if resumo else None})
    return {
        "existe": True,
        "pacote_ilegivel": bool(isinstance(pacote, dict) and pacote.get("_ilegivel")),
        "avisos": (pac or {}).get("avisos") if pac else None,
        "retirados": (pac or {}).get("retirados") if pac else None,
        "propostas": propostas,
        "sugestoes": [x for x in sugestoes_projeto(pac, projeto) if f"sugestao:{x['campo']}" not in (respostas or {})],
        "respostas": respostas or {},
        "capa_sugerida": ((pac or {}).get("projeto") or {}).get("capa_sugerida") if pac else None,
        "aceite": (lambda a: {"publicavel": a.get("publicavel"), **avaliar_aceite(a, conferencia), "arquivo": a.get("_arquivo")} if a else None)(ler_aceite(pasta)),
        "execucao": (pac or {}).get("execucao") if pac else None,
        "relatorio": ler_relatorio(_texto(cat / "relatorio.txt")),
        "decisoes": _json(cat / "decisoes.json"),
        "orientacao": ler_orientacao(_texto(cat / "orientacao.txt")),
        "releituras": releituras,
        # 20/10 (CAMP-126): opcional. Grupos por código de unidade e a decisão de uma pessoa ("obras:decisao" em respostas)
        "obras": (lambda o: {**o, "decisao": (respostas or {}).get("obras:decisao")} if o else None)(obras_na_pasta(pac, propostas)),
    }
