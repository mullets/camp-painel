"""Importa o pacote do CAMP Vision (catalogacao/pacote_tainacan.json, versão 2) para as folhas (itens) do painel, EM REVISÃO.

Regras:
- só entra o que está em `documentos`; `retirados` (autoria divergente, retirada por decisão) NÃO entra, e é contado no resultado;
- nada que uma pessoa já revisou é sobrescrito, nem o que já foi para o site; reimportar só atualiza folhas ainda pendentes;
- o tipo lido só vira tipo do painel se existir no vocabulário (o lido fica guardado em `tipo_lido`);
- tudo o que o CAMP Vision disse de problemático (bloqueios, ressalvas, orientação/série incerta) vai para `pendencias`, para a pessoa ver ao revisar.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException

CODIGO_DOCUMENTO = re.compile(r"^(F\d{3})-(P\d{4})-(\d{4})-(S0[1-6])-D(\d{4,6})$")
SINAIS = (("orientacao_incerta", "orientação incerta"), ("serie_incerta", "série incerta"), ("fora_do_periodo", "fora do período de atuação do fundo"),
          ("projeto_divergente", "projeto divergente"), ("sem_identificacao", "sem identificação (pasta com várias obras)"))


def ler_pacote(pasta: Path) -> dict | None:
    arq = pasta / "catalogacao" / "pacote_tainacan.json"
    if not arq.is_file():
        return None
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(400, f"O pacote do CAMP Vision está ilegível: {e}")
    if not isinstance(dados, dict):
        raise HTTPException(400, "O pacote do CAMP Vision não tem o formato esperado")
    return dados


def _rotacao(v) -> int:
    try:
        r = int(v or 0) % 360
    except (TypeError, ValueError):
        return 0
    return -90 if r == 270 else r


def _categoria_retirado(r: dict, motivos: list[str]) -> str:
    txt = " ".join(motivos).lower()
    if r.get("autoria_divergente") or "autoria" in txt:
        return "autoria_divergente"
    if r.get("projeto_divergente") or "projeto divergente" in txt:
        return "projeto_errado"
    if r.get("duplicata_de") or "duplicata" in txt:
        return "duplicata"
    return "outro"


def registrar_problemas(con, proj: str, pacote: dict, recusadas: list[str], lote_id: int) -> int:
    """Cartão 13: cada folha que o CAMP Vision RETIROU do lote (e cada uma que o painel recusou ao importar) vira um problema
    com origem automática ('campvision'). A `chave` evita duplicar ao reimportar e não reabre o que alguém já resolveu.
    A gravidade é 'corrigir': a folha retirada não vai ao site, então não há por que travar o projeto inteiro. Devolve quantos entraram."""
    devolvidas = {r[0] for r in con.execute("SELECT chave FROM cv_resposta WHERE lote_id=? AND tipo='retirado' AND acao='devolver'", (lote_id,))}
    novos = 0
    for r in pacote.get("retirados") or []:
        if not isinstance(r, dict):
            continue
        cod = str(r.get("codigo") or "").strip()
        if not cod or cod in devolvidas:
            continue
        motivos = [str(b) for b in (r.get("bloqueios") or []) if b] or ([str(r["motivo"])] if r.get("motivo") else [])
        quem = f" (decisão de {r['retirado_por']})" if r.get("retirado_por") else ""
        descricao = "O CAMP Vision retirou esta folha do lote" + quem + (": " + "; ".join(motivos) if motivos else "") + ". Ela não entrou na revisão."
        novos += con.execute("""INSERT OR IGNORE INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, chave)
                                VALUES ('corrigir', ?, 'campvision', ?, ?, 'CAMP Vision', ?)""",
                             (_categoria_retirado(r, motivos), cod if CODIGO_DOCUMENTO.match(cod) else proj, descricao, f"campvision:retirado:{cod}")).rowcount
    for texto in recusadas:
        cod = texto.split(":", 1)[0].strip()
        novos += con.execute("""INSERT OR IGNORE INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, chave)
                                VALUES ('corrigir', 'codigo', 'campvision', ?, ?, 'CAMP Vision', ?)""",
                             (proj, f"Folha do lote que não entrou no painel: {texto}.", f"campvision:recusada:{proj}:{cod}")).rowcount
    return novos


def _primeiro(doc: dict, md: dict, chaves: tuple) -> str | None:
    """O primeiro valor não vazio entre as chaves, no documento do pacote e depois nos metadados lidos do carimbo."""
    for fonte in (doc, md):
        for k in chaves:
            v = fonte.get(k)
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v).strip()[:300]
    return None


def _recodificar_por_releitura(con, antigo: str, novo: str, serie: str, ator: str) -> None:
    """Dá à folha `antigo` o código `novo` (outra série, mesmo D). Copia a linha com o código novo, passa as referências e apaga a
    antiga: nunca deixa chave estrangeira quebrada, mesmo sem transação com checagem adiada."""
    from .rotas_mesclar import _trocar_codigo
    cols = [r[1] for r in con.execute("PRAGMA table_info(item)")]
    outras = [c for c in cols if c not in ("codigo", "serie_codigo", "codigo_anterior", "sequencial")]
    seq = con.execute("SELECT sequencial FROM item WHERE codigo=?", (antigo,)).fetchone()[0]
    con.execute("UPDATE item SET sequencial=? WHERE codigo=?", (-1000000 - seq, antigo))      # libera o D (único no projeto) até apagar a antiga
    con.execute(f"INSERT INTO item (codigo, serie_codigo, codigo_anterior, sequencial, {', '.join(outras)}) SELECT ?, ?, ?, ?, {', '.join(outras)} FROM item WHERE codigo=?",
                (novo, serie, antigo, seq, antigo))
    _trocar_codigo(con, antigo, novo)
    con.execute("DELETE FROM item WHERE codigo=?", (antigo,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_recodificada_releitura',?,?)",
                (novo, ator, json.dumps({"de": antigo, "para": novo, "motivo": "a nova leitura do CAMP Vision mudou a série"}, ensure_ascii=False)))


def _atualizar_arquivos(con, cod: str, d: dict) -> None:
    """Só os arquivos (TIF, JPG, origem) e a prévia da leitura nova; título, giro, revisão e o resto que a pessoa fez ficam."""
    arqs = [str(a) for a in (d.get("arquivos") or [])]
    tif = next((a for a in arqs if a.lower().endswith((".tif", ".tiff"))), None)
    jpg = next((a for a in arqs if a.lower().endswith((".jpg", ".jpeg"))), None)
    if not (tif or jpg):
        return
    row = con.execute("SELECT pendencias FROM item WHERE codigo=?", (cod,)).fetchone()
    try:
        pend = json.loads(row["pendencias"] or "{}") if row else {}
    except ValueError:
        pend = {}
    if d.get("preview"):
        pend["previa"] = d.get("preview")
    con.execute("UPDATE item SET arquivo_tif=COALESCE(?, arquivo_tif), arquivo_jpg=COALESCE(?, arquivo_jpg), pendencias=?, atualizado_em=datetime('now') WHERE codigo=?",
                (tif, jpg, json.dumps(pend, ensure_ascii=False), cod))


def importar_lote(con, lote_id: int, ator: str) -> dict:
    """NÃO faz commit (quem chama controla a transação)."""
    lote = con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
    if not lote:
        raise HTTPException(404, "Lote não existe")
    pasta = Path(lote["pasta_qnap"] or "")
    if not pasta.is_dir():
        raise HTTPException(400, "A pasta do lote não está acessível (o QNAP está montado?)")
    pacote = ler_pacote(pasta)
    if pacote is None:
        raise HTTPException(400, "O CAMP Vision ainda não gravou o pacote deste lote (catalogacao/pacote_tainacan.json)")
    proj = lote["projeto_codigo"]
    if pacote.get("projeto_codigo") != proj:
        raise HTTPException(400, f"O pacote é do projeto {pacote.get('projeto_codigo')}, e o lote é de {proj}")
    docs = pacote.get("documentos") if isinstance(pacote.get("documentos"), list) else pacote.get("itens")
    # folha que o CAMP Vision RETIROU e um admin DEVOLVEU à revisão (cartão 148): entra como as outras, pendente de conferência
    if isinstance(docs, list) and isinstance(pacote.get("retirados"), list):
        devolvidas = {r[0] for r in con.execute("SELECT chave FROM cv_resposta WHERE lote_id=? AND tipo='retirado' AND acao='devolver'", (lote_id,))}
        docs = docs + [r for r in pacote["retirados"] if isinstance(r, dict) and r.get("codigo") in devolvidas]
    if not isinstance(docs, list):
        raise HTTPException(400, "O pacote não traz a lista de documentos")

    tipos = {n.lower(): n for (n,) in con.execute("SELECT nome FROM tipo_documento")}
    series = {r[0] for r in con.execute("SELECT codigo FROM serie")}
    existentes = {r["codigo"]: r for r in con.execute("SELECT codigo, revisao, status_site FROM item WHERE projeto_codigo=?", (proj,))}
    criados = atualizados = ignoradas = 0
    problemas: list[str] = []
    duplicatas: list[tuple] = []
    cobertas = colisoes_decididas(con, lote_id)            # folhas que já têm uma decisão "lote_colide" (pendente ou resolvida)
    novas_colisoes: list[dict] = []
    esperando = puladas_colisao = 0
    recodificadas: list[dict] = []
    for d in docs:
        cod = str(d.get("codigo") or "")
        m = CODIGO_DOCUMENTO.match(cod)
        if not m or f"{m.group(1)}-{m.group(2)}" != proj or m.group(4) not in series:
            problemas.append(f"{cod or '(sem código)'}: código inválido, de outro projeto ou de série desconhecida")
            continue
        serie, seq = m.group(4), int(m.group(5))
        cob = cobertas.get(cod)
        if cob:
            if cob["situacao"] == "pendente":
                esperando += 1                                 # a pessoa ainda não escolheu: a folha espera
                continue
            novo_cod = (cob.get("renumeradas") or {}).get(cod)
            if cob["escolha"] == "ignorar" or cod in (cob.get("mantidas") or []) or (cob["escolha"] == "adicionar_ao_fim" and not novo_cod):
                puladas_colisao += 1
                continue
            if novo_cod:                                       # "adicionar ao fim": a folha entra com o número novo
                cod = novo_cod
                m = CODIGO_DOCUMENTO.match(cod)
                serie, seq = m.group(4), int(m.group(5))
                if cod not in existentes:
                    ex_ = con.execute("SELECT codigo, revisao, status_site FROM item WHERE codigo=?", (cod,)).fetchone()
                    if ex_:
                        existentes[cod] = ex_
        else:
            col = colisao(con, proj, seq, lote_id, lote["pasta_qnap"])
            if col:
                novas_colisoes.append({"codigo": cod, "serie": serie, "d": seq, "existente": col["codigo"], "existente_serie": col["serie_codigo"],
                                       "existente_lote": col["lote_id"], "existente_revisao": col["revisao"], "existente_status": col["status_site"],
                                       "existente_titulo": col["titulo"], "titulo": (d.get("titulo") or "").strip() or None})
                continue
        if cod not in existentes:
            velha = con.execute("SELECT codigo, lote_id, status_site, tainacan_item_id FROM item WHERE projeto_codigo=? AND sequencial=? AND codigo<>?",
                                (proj, seq, cod)).fetchone()
            if velha and velha["lote_id"] == lote_id and not velha["tainacan_item_id"] and velha["status_site"] not in ("rascunho", "no_ar"):
                # A releitura do MESMO lote mudou a série desta folha (aviso de 14/10: F009-P0060, S01 → S03): a folha que o painel
                # já tinha passa a ter o código novo (com histórico, revisão, localização e problemas) em vez de travar a leitura nova.
                _recodificar_por_releitura(con, velha["codigo"], cod, serie, ator)
                existentes.pop(velha["codigo"], None)
                existentes[cod] = con.execute("SELECT codigo, revisao, status_site FROM item WHERE codigo=?", (cod,)).fetchone()
                recodificadas.append({"de": velha["codigo"], "para": cod})
        ex = existentes.get(cod)
        if ex and (ex["revisao"] != "pendente" or ex["status_site"] in ("rascunho", "no_ar")):
            ignoradas += 1                                         # já revisada por uma pessoa, ou já no site: não se mexe no que a pessoa fez…
            if ex["status_site"] not in ("rascunho", "no_ar"):     # …mas os CAMINHOS dos arquivos são da máquina: a releitura pode ter movido/renomeado
                _atualizar_arquivos(con, cod, d)                    # (aviso de 14/10: D00001 conferida apontava para o JPG S01 que não existe mais)
            continue
        outro = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND sequencial=? AND codigo<>?", (proj, seq, cod)).fetchone()
        if outro:
            problemas.append(f"{cod}: o número D{seq:05d} já é de {outro[0]}")
            continue
        tipo_lido = str(d.get("tipo_de_desenho") or d.get("tipo") or "").strip()
        arqs = [str(a) for a in (d.get("arquivos") or [])]
        tif = next((a for a in arqs if a.lower().endswith((".tif", ".tiff"))), None)
        jpg = next((a for a in arqs if a.lower().endswith((".jpg", ".jpeg"))), None)
        origem = d.get("arquivo_origem")
        if isinstance(origem, list):
            origem = " | ".join(str(o.get("arquivo_origem") if isinstance(o, dict) else o) for o in origem if o)
        ano = str(d.get("ano") or "").strip()
        md = d.get("metadados") if isinstance(d.get("metadados"), dict) else {}
        endereco_lido = _primeiro(d, md, ("endereco", "endereço", "endereco_obra", "local"))     # o que o carimbo DESTA folha diz (consenso do lote)
        cliente_lido = _primeiro(d, md, ("cliente", "proprietario", "proprietário"))
        ano_folha = int(ano) if ano.isdigit() and 1800 <= int(ano) <= 2100 else None
        pend = {"titulo_lido": d.get("titulo_lido") or "", "bloqueios": list(d.get("bloqueios") or []), "ressalvas": list(d.get("ressalvas") or []),
                "sinais": [txt for chave, txt in SINAIS if d.get(chave)], "confianca": d.get("confianca"), "previa": d.get("preview") or "",
                "ano_do_projeto": d.get("ano_do_projeto")}
        campos = {"titulo": (d.get("titulo") or "").strip() or None, "tipo_documento": tipos.get(tipo_lido.lower()), "tipo_lido": tipo_lido or None,
                  "folha": (str(d.get("folha") or "").strip() or None), "escala": (str(d.get("escala") or "").strip() or None), "ano_folha": ano_folha,
                  "arquivo_tif": tif, "arquivo_jpg": jpg, "rotacao_aplicada": 0 if d.get("orientacao_corrigida") else _rotacao(d.get("rotacao_aplicada")), "espelhado": int(bool(d.get("espelhada")) and not d.get("orientacao_corrigida")),
                  "autoria_divergente": int(bool(d.get("autoria_divergente"))), "credito": d.get("credito") or None,
                  "status_site": "nao_publicado" if d.get("publicavel") else "bloqueado", "arquivo_origem": (str(origem or "").strip() or None), "pendencias": json.dumps(pend, ensure_ascii=False), "lote_id": lote_id,
                  "endereco_folha": endereco_lido, "cliente_folha": cliente_lido,
                  "versao_cv2": (str(d.get("versao_cv2") or "").strip() or None), "versao_prompt": (str(d.get("versao_prompt") or "").strip() or None), "modelo_cv": (str(d.get("modelo") or "").strip() or None)}
        # O que o CARIMBO diz (contrato 2.2, auditoria F026 T1): sem isso não dá para auditar pelo painel.
        carimbo = d.get("carimbo") if isinstance(d.get("carimbo"), dict) else {}
        meta = d.get("metadados") if isinstance(d.get("metadados"), dict) else {}
        campos["projeto_carimbo"] = (str(carimbo.get("obra") or meta.get("projeto") or "").strip() or None)
        campos["escritorio_carimbo"] = (str(carimbo.get("escritorio") or meta.get("escritorio") or "").strip() or None)
        campos["autor_carimbo"] = (str(carimbo.get("arquiteto") or meta.get("arquiteto") or "").strip() or None)
        lido = {k_: campos[k_] for k_ in ("titulo", "tipo_documento", "folha", "escala", "ano_folha")}   # o que o CV2 LEU (cartão 152)
        lido.update({"carimbo": carimbo or None, "leitura": d.get("lido") if isinstance(d.get("lido"), dict) else meta or None,
                     "transcricao_integral": (d.get("lido") or {}).get("transcricao_integral") if isinstance(d.get("lido"), dict) else d.get("transcricao_integral"),
                     "versao_cv2": campos["versao_cv2"], "versao_prompt": campos["versao_prompt"], "modelo_cv": campos["modelo_cv"]})
        campos["lido_json"] = json.dumps(lido, ensure_ascii=False)
        if ex:
            con.execute("UPDATE item SET " + ", ".join(f"{k}=?" for k in campos) + ", atualizado_em=datetime('now') WHERE codigo=?", (*campos.values(), cod))
            atualizados += 1
        else:
            con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, " + ", ".join(campos) + ") VALUES (?,?,?,?,'campvision'," + ",".join("?" * len(campos)) + ")",
                        (cod, proj, serie, seq, *campos.values()))
            criados += 1
        if d.get("duplicata_de"):
            duplicatas.append((cod, str(d["duplicata_de"]), d.get("tipo_duplicata")))
    for cod, de, tipo in duplicatas:                               # depois de todas existirem (a referência é de item para item)
        if de != cod and con.execute("SELECT 1 FROM item WHERE codigo=?", (de,)).fetchone():
            con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata=? WHERE codigo=?", (de, {"quase": "perceptual"}.get(tipo, tipo) if {"quase": "perceptual"}.get(tipo, tipo) in ("exata", "perceptual", "mesma_folha") else None, cod))
    retirados = [{"codigo": r.get("codigo"), "bloqueios": r.get("bloqueios") or []} for r in (pacote.get("retirados") or []) if isinstance(r, dict)]
    registrados = registrar_problemas(con, proj, pacote, problemas, lote_id)
    resultado = {}
    try:
        resultado = json.loads(lote["resultado"] or "{}")
    except ValueError:
        pass
    resumo = {"criadas": criados, "atualizadas": atualizados, "ignoradas_ja_revisadas": ignoradas, "retirados": retirados, "problemas": problemas,
              "problemas_registrados": registrados, "teste": bool(pacote.get("teste"))}
    if recodificadas:
        resumo["recodificadas_pela_releitura"] = recodificadas
    if novas_colisoes:                                         # "Mais inteligência" (1): o lote repete números que o projeto já usa → pergunta
        resumo["decisao_colisao"] = abrir_colisao(con, lote, proj, novas_colisoes, docs)
    if novas_colisoes or esperando:
        resumo["esperando_decisao"] = len(novas_colisoes) + esperando
    if puladas_colisao:
        resumo["puladas_por_decisao"] = puladas_colisao
    from .decisoes import abrir_divergencias
    div = abrir_divergencias(con, proj, pacote, lote_id)   # (6) o CV2 leu ano/cidade/cliente diferente do cadastro
    if div:
        resumo["divergencias"] = div
    resultado["importacao"] = {**resumo, "por": ator}
    if isinstance(pacote.get("execucao"), dict):                 # custo, tempo e versão do lote (cartão 152)
        con.execute("UPDATE lista_processamento SET execucao_json=? WHERE id=?", (json.dumps(pacote["execucao"], ensure_ascii=False), lote_id))
    from .saidas_cv import ler_aceite
    aceite = ler_aceite(pasta)   # CV2 §10: o aceite do lote fica no painel e vira condição de publicar
    con.execute("UPDATE lista_processamento SET resultado=?, aceite_json=?, atualizado_em=datetime('now') WHERE id=?",
                (json.dumps(resultado, ensure_ascii=False), json.dumps(aceite, ensure_ascii=False) if aceite else None, lote_id))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'folhas_importadas_do_lote',?,?)",
                (proj, ator, json.dumps({"lote_id": lote_id, "criadas": criados, "atualizadas": atualizados, "ignoradas": ignoradas, "retirados": len(retirados), "problemas": len(problemas)}, ensure_ascii=False)))
    return resumo



# ---------------------------------------------------------------- "Mais inteligência" (1): lote que colide com folhas que o projeto já tem
def colisao(con, proj: str, seq: int, lote_id: int, pasta: str | None):
    """A folha do projeto que já usa este número D e veio de OUTRO lote (ou do site, ou à mão). A mesma pasta registrada de novo não conta."""
    return con.execute("""SELECT i.codigo, i.serie_codigo, i.lote_id, i.revisao, i.status_site, i.titulo FROM item i
                           LEFT JOIN lista_processamento l ON l.id=i.lote_id
                          WHERE i.projeto_codigo=? AND i.sequencial=? AND (i.lote_id IS NULL OR i.lote_id<>?)
                            AND (l.pasta_qnap IS NULL OR l.pasta_qnap<>COALESCE(?, ''))""", (proj, seq, lote_id, pasta)).fetchone()


def colisoes_decididas(con, lote_id: int) -> dict:
    """{codigo_do_pacote: {situacao, escolha, renumeradas, mantidas}} de todas as decisões 'lote_colide' deste lote."""
    out = {}
    for d in con.execute("SELECT situacao, escolha, contexto FROM decisao WHERE tipo='lote_colide' AND chave LIKE ? ORDER BY id", (f"lote_colide:{lote_id}:%",)):
        try:
            ctx = json.loads(d["contexto"] or "{}")
        except ValueError:
            continue
        info = {"situacao": d["situacao"], "escolha": d["escolha"], "renumeradas": ctx.get("renumeradas") or {}, "mantidas": (ctx.get("resultado") or {}).get("mantidas") or []}
        for c in ctx.get("colisoes") or []:
            out[c["codigo"]] = info
    return out


def abrir_colisao(con, lote, proj: str, colisoes: list[dict], docs: list) -> int:
    from .decisoes import abrir
    n = con.execute("SELECT COUNT(*) FROM decisao WHERE tipo='lote_colide' AND chave LIKE ?", (f"lote_colide:{lote['id']}:%",)).fetchone()[0]
    p = con.execute("SELECT fundo_codigo, titulo FROM projeto WHERE codigo=?", (proj,)).fetchone()
    folhas = con.execute("SELECT COUNT(*), COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=?", (proj,)).fetchone()
    ctx = {"lote_id": lote["id"], "lote_nome": lote["nome"], "pasta": lote["pasta_qnap"], "projeto_codigo": proj, "projeto_titulo": p["titulo"] if p else None,
           "folhas_no_projeto": folhas[0], "maior_d": folhas[1], "folhas_no_lote": len(docs), "colisoes": colisoes}
    did, _ = abrir(con, "lote_colide", f"lote_colide:{lote['id']}:{n + 1}", p["fundo_codigo"] if p else proj[:4], lote["nome"] or proj, ctx, "campvision")
    return did


def aplicar_colisao(con, d, ctx: dict, acao: str, ator: str) -> dict:
    """Aplica a escolha da pessoa às folhas que colidiram. NÃO faz commit.
    adicionar_ao_fim: cada folha repetida ganha o próximo número livre do projeto (depois do maior D do projeto e do lote);
    ignorar: as repetidas não entram (as que já estão no projeto ficam como estão);
    substituir: a folha do lote toma o lugar da que já existe, menos as que já estão no site (essas ficam e são listadas)."""
    lote_id, proj = ctx["lote_id"], ctx["projeto_codigo"]
    colisoes = ctx.get("colisoes") or []
    out: dict = {}
    if acao == "adicionar_ao_fim":
        pacote_max = 0
        lote = con.execute("SELECT pasta_qnap FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        try:
            pac = ler_pacote(Path(lote["pasta_qnap"] or "")) if lote and Path(lote["pasta_qnap"] or "").is_dir() else None
        except HTTPException:
            pac = None
        for x in ((pac or {}).get("documentos") or []):
            mm = CODIGO_DOCUMENTO.match(str(x.get("codigo") or "")) if isinstance(x, dict) else None
            if mm:
                pacote_max = max(pacote_max, int(mm.group(5)))
        prox = max(con.execute("SELECT COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=?", (proj,)).fetchone()[0], pacote_max) + 1
        ren = {}
        for c in colisoes:
            mm = CODIGO_DOCUMENTO.match(c["codigo"])
            ren[c["codigo"]] = f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}-{mm.group(4)}-D{prox:0{max(5, len(mm.group(5)))}d}"
            prox += 1
        ctx["renumeradas"] = ren
        out = {"renumeradas": ren, "mensagem": f"{len(ren)} folha(s) entram no fim, com número novo (a partir de {next(iter(ren.values()), '')[-6:]})."}
    elif acao == "ignorar":
        out = {"mensagem": f"As {len(colisoes)} folha(s) repetidas do lote não entram; as que já estavam no projeto ficam como estão."}
    else:
        mantidas, trocadas = [], []
        for c in colisoes:
            ex = con.execute("SELECT codigo, status_site FROM item WHERE codigo=?", (c["existente"],)).fetchone()
            if not ex:
                trocadas.append(c["codigo"]); continue
            if ex["status_site"] in ("rascunho", "no_ar"):
                mantidas.append(c["codigo"]); continue
            if ex["codigo"] == c["codigo"]:                       # mesmo código: a folha passa a ser deste lote e volta a pedir conferência
                con.execute("UPDATE item SET lote_id=?, revisao='pendente', revisado_por=NULL, revisado_em=NULL, atualizado_em=datetime('now') WHERE codigo=?", (lote_id, ex["codigo"]))
                trocadas.append(c["codigo"]); continue
            con.execute("SAVEPOINT troca")
            try:
                con.execute("UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL WHERE duplicata_de=?", (ex["codigo"],))
                con.execute("DELETE FROM item WHERE codigo=?", (ex["codigo"],))
                con.execute("RELEASE troca")
                con.execute("INSERT OR IGNORE INTO redirecionamento (codigo_antigo, codigo_novo, entidade, motivo) VALUES (?,?,'item',?)",
                            (ex["codigo"], c["codigo"], f"substituída pela folha do lote {lote_id} (decisão {d['id']})"))
                trocadas.append(c["codigo"])
            except Exception:  # noqa: BLE001 - a folha antiga está ligada a outra coisa (localização, pedido...): fica
                con.execute("ROLLBACK TO troca"); con.execute("RELEASE troca")
                mantidas.append(c["codigo"])
        out = {"trocadas": trocadas, "mantidas": mantidas,
               "mensagem": f"{len(trocadas)} folha(s) substituídas" + (f"; {len(mantidas)} ficaram como estavam (já estão no site ou ligadas a outra coisa)" if mantidas else "") + "."}
    ctx["resultado"] = out
    con.execute("UPDATE decisao SET situacao='resolvida', escolha=?, contexto=? WHERE id=?", (acao, json.dumps(ctx, ensure_ascii=False), d["id"]))
    if acao != "ignorar":                                          # traz as folhas agora (se a pasta estiver acessível e o lote não aprovado)
        lote = con.execute("SELECT aprovado_em FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        if lote and not lote["aprovado_em"]:
            try:
                r = importar_lote(con, lote_id, f"decisao-{ator}")
                out["importacao"] = {k: r.get(k) for k in ("criadas", "atualizadas")}
            except HTTPException as e:
                out["importacao"] = {"erro": e.detail, "aviso": "A escolha fica guardada e vale na próxima importação deste lote."}
    return out
