"""CAMP-047 · Move as folhas que hoje são S07 (Redesenhos) para a nova série S08 (Redesenhos). S07 passa a ser só "Publicações".

O CÓDIGO da folha muda ({projeto}-{ano}-S07-D00001 → ...-S08-D00001; o D e o resto ficam). Por isso:
- tudo o que aponta para a folha acompanha (as mesmas tabelas do mover/recodificar) e o antigo fica em item.codigo_anterior;
- cada troca entra na tabela `redirecionamento` (antigo → novo, cadeias já resolvidas), que o site lê (GET /api/redirecionamentos) e que o painel
  também envia ao site (CAMP-014, redir_site.py);
- folha que JÁ está no site (tainacan_item_id) NUNCA é trocada em silêncio: só com `incluir_no_site=True` e passando pelo fluxo de redirecionamento
  (o redirecionamento fica na fila de envio e o código/série no site são atualizados; falha vira pendência e não desfaz o local);
- é um ROTEIRO: `planejar` só lê (modo simular); `aplicar` é chamado só pelo script com --aplicar. Nada roda sozinho, nem em produção.
"""
from __future__ import annotations

import json
import sqlite3

ANTIGA, NOVA = "S07", "S08"
# tabelas que guardam o código da folha por igualdade (as de prefixo/chave composta ficam com _trocar_codigo)
_EXTRAS = (("solicitacao_item", "codigo"), ("etiqueta_impressao", "codigo"), ("divergencia_site", "codigo"), ("uso_download", "material_codigo"),
           ("tarefa_publicacao", "folha_atual"))


def _novo_codigo(codigo: str) -> str:
    return codigo.replace(f"-{ANTIGA}-", f"-{NOVA}-", 1)


def planejar(con) -> dict:
    """Só lê. {'folhas': [{antigo, novo, projeto, no_site, status_site, conflito}], 'no_site': n, 'locais': n, 'conflitos': n}"""
    linhas = []
    for r in con.execute("SELECT codigo, projeto_codigo, tainacan_item_id, status_site FROM item WHERE serie_codigo=? ORDER BY codigo", (ANTIGA,)):
        novo = _novo_codigo(r["codigo"])
        conflito = novo == r["codigo"] or bool(con.execute("SELECT 1 FROM item WHERE codigo=?", (novo,)).fetchone())
        linhas.append({"antigo": r["codigo"], "novo": novo, "projeto": r["projeto_codigo"], "no_site": bool(r["tainacan_item_id"]),
                       "status_site": r["status_site"], "conflito": conflito})
    return {"folhas": linhas, "total": len(linhas), "no_site": sum(1 for x in linhas if x["no_site"]), "locais": sum(1 for x in linhas if not x["no_site"]),
            "conflitos": sum(1 for x in linhas if x["conflito"])}


def aplicar(con, ator: str, incluir_no_site: bool = False, motivo: str = "série Redesenhos passou de S07 para S08") -> dict:
    """Troca os códigos. A conexão deve ter transação aberta por quem chama (commit/rollback são dele). Devolve o que mudou e o que ficou de fora."""
    from .rotas_mesclar import _trocar_codigo
    plano = planejar(con)
    trocadas, ignoradas = [], []
    con.execute("PRAGMA defer_foreign_keys = ON")
    for f in plano["folhas"]:
        if f["conflito"]:
            ignoradas.append({**f, "motivo": "o código novo já existe"}); continue
        if f["no_site"] and not incluir_no_site:
            ignoradas.append({**f, "motivo": "já está no site: só com --incluir-no-site (passa pelo fluxo de redirecionamento)"}); continue
        a, n = f["antigo"], f["novo"]
        con.execute("UPDATE item SET codigo=?, serie_codigo=?, codigo_anterior=?, atualizado_em=datetime('now') WHERE codigo=?", (n, NOVA, a, a))
        _trocar_codigo(con, a, n)
        for tabela, coluna in _EXTRAS:
            try:
                con.execute(f"UPDATE {tabela} SET {coluna}=? WHERE {coluna}=?", (n, a))
            except sqlite3.OperationalError:
                pass
        if _tem(con, "cv_resposta"):
            con.execute("UPDATE cv_resposta SET chave=? WHERE chave=? AND tipo='retirado'", (n, a))
        con.execute("UPDATE evento SET codigo=? WHERE codigo=? AND entidade='item'", (n, a))
        # cadeias já resolvidas: quem apontava para o antigo passa a apontar para o novo
        from . import redir_site
        redir_site.registrar(con, a, n, "item", motivo, ator)
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'serie_trocada',?,?)",
                    (n, ator, json.dumps({"de": a, "para": n, "serie": f"{ANTIGA}→{NOVA}", "no_site": f["no_site"]}, ensure_ascii=False)))
        trocadas.append(f)
    return {"trocadas": trocadas, "ignoradas": ignoradas}


def _tem(con, tabela: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone())


def atualizar_site_das_trocadas(trocadas: list[dict], ator: str) -> dict:
    """Folhas que já estavam no site: manda o código e a série novos (melhor esforço; falha vira pendência, nunca desfaz o local)."""
    from .db import connect
    from . import publicador
    out = {"atualizadas": 0, "falhas": []}
    con = connect()
    try:
        try:
            wp = publicador.WP()
        except Exception as e:  # noqa: BLE001
            for f in trocadas:
                if f["no_site"]:
                    publicador._pendencia(con, "item", f["novo"], "pendente_codigo_no_site", f"código/série novos não enviados ao site: {e}")
                    out["falhas"].append(f["novo"])
            con.commit(); return out
        for f in trocadas:
            if not f["no_site"]:
                continue
            row = con.execute("SELECT tainacan_item_id FROM item WHERE codigo=?", (f["novo"],)).fetchone()
            try:
                iid = int(row[0])
                mid, _ = publicador._meta(con, publicador.COL_ACERVO, "Código do documento")
                if mid:
                    wp.definir_metadado(iid, mid, f["novo"])
                mid_s, _ = publicador._meta(con, publicador.COL_ACERVO, "Série")
                termo = publicador._termo_por_nome(con, "Séries", "Redesenhos")
                if mid_s and termo:
                    wp.definir_metadado(iid, mid_s, termo)
                out["atualizadas"] += 1
            except Exception as e:  # noqa: BLE001
                publicador._pendencia(con, "item", f["novo"], "pendente_codigo_no_site", str(e)[:200]); out["falhas"].append(f["novo"])
        con.commit()
    finally:
        con.close()
    return out
