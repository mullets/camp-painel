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
          ("projeto_divergente", "projeto divergente"))


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
    if not isinstance(docs, list):
        raise HTTPException(400, "O pacote não traz a lista de documentos")

    tipos = {n.lower(): n for (n,) in con.execute("SELECT nome FROM tipo_documento")}
    series = {r[0] for r in con.execute("SELECT codigo FROM serie")}
    existentes = {r["codigo"]: r for r in con.execute("SELECT codigo, revisao, status_site FROM item WHERE projeto_codigo=?", (proj,))}
    criados = atualizados = ignoradas = 0
    problemas: list[str] = []
    duplicatas: list[tuple] = []
    for d in docs:
        cod = str(d.get("codigo") or "")
        m = CODIGO_DOCUMENTO.match(cod)
        if not m or f"{m.group(1)}-{m.group(2)}" != proj or m.group(4) not in series:
            problemas.append(f"{cod or '(sem código)'}: código inválido, de outro projeto ou de série desconhecida")
            continue
        serie, seq = m.group(4), int(m.group(5))
        ex = existentes.get(cod)
        if ex and (ex["revisao"] != "pendente" or ex["status_site"] in ("rascunho", "no_ar")):
            ignoradas += 1                                         # já revisada por uma pessoa, ou já no site: não se mexe
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
        ano_folha = int(ano) if ano.isdigit() and 1800 <= int(ano) <= 2100 else None
        pend = {"titulo_lido": d.get("titulo_lido") or "", "bloqueios": list(d.get("bloqueios") or []), "ressalvas": list(d.get("ressalvas") or []),
                "sinais": [txt for chave, txt in SINAIS if d.get(chave)], "confianca": d.get("confianca"), "previa": d.get("preview") or "",
                "ano_do_projeto": d.get("ano_do_projeto")}
        campos = {"titulo": (d.get("titulo") or "").strip() or None, "tipo_documento": tipos.get(tipo_lido.lower()), "tipo_lido": tipo_lido or None,
                  "folha": (str(d.get("folha") or "").strip() or None), "escala": (str(d.get("escala") or "").strip() or None), "ano_folha": ano_folha,
                  "arquivo_tif": tif, "arquivo_jpg": jpg, "rotacao_aplicada": 0 if d.get("orientacao_corrigida") else _rotacao(d.get("rotacao_aplicada")), "espelhado": int(bool(d.get("espelhada")) and not d.get("orientacao_corrigida")),
                  "autoria_divergente": int(bool(d.get("autoria_divergente"))), "credito": d.get("credito") or None,
                  "status_site": "nao_publicado" if d.get("publicavel") else "bloqueado", "arquivo_origem": (str(origem or "").strip() or None), "pendencias": json.dumps(pend, ensure_ascii=False), "lote_id": lote_id}
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
    resultado = {}
    try:
        resultado = json.loads(lote["resultado"] or "{}")
    except ValueError:
        pass
    resumo = {"criadas": criados, "atualizadas": atualizados, "ignoradas_ja_revisadas": ignoradas, "retirados": retirados, "problemas": problemas, "teste": bool(pacote.get("teste"))}
    resultado["importacao"] = {**resumo, "por": ator}
    con.execute("UPDATE lista_processamento SET resultado=?, atualizado_em=datetime('now') WHERE id=?", (json.dumps(resultado, ensure_ascii=False), lote_id))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'folhas_importadas_do_lote',?,?)",
                (proj, ator, json.dumps({"lote_id": lote_id, "criadas": criados, "atualizadas": atualizados, "ignoradas": ignoradas, "retirados": len(retirados), "problemas": len(problemas)}, ensure_ascii=False)))
    return resumo
