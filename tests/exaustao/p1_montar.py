#!/usr/bin/env python3
"""Cenários de CAMP-122 (P1), CAMP-128 (P7) e CAMP-131 (P10): o caso real da F026-P0009 CRASA, pelo caminho de verdade.

  crasa   BASE RAIZ DB NOME  -> estação reserva; CAMP Vision lê 34 folhas e avisa (o painel importa); a equipe confere (22 corrigidas, 9 conferidas,
                                3 retidas) e aprova [pré-condição no banco]; o CAMP Vision grava status.json "erro" com SÓ o aviso [Minor] do exiftool
                                da D00034 e avisa (caminho real); depois a publicação [pré-condição no banco, com a mesma regra da publicação guiada:
                                só lote em revisão/rascunho aprovado vira "publicado"]. Imprime o código.
  legado  BASE RAIZ DB NOME  -> igual, mas o lote fica em 'erro' no banco como estava em produção ANTES desta correção (para provar a cura).
  erro_vazio BASE RAIZ NOME  -> erro de verdade sem nada importado (sem pacote): "Error: …" → continua vermelho.
  erro_com_folhas BASE RAIZ DB NOME -> lote importado e depois erro de verdade → vermelho, mas sem "Nada foi importado".
  releitura BASE RAIZ DB P   -> o CAMP Vision atende os pedidos de releitura abertos do projeto (iniciado → grava releituras/<quando>/comparacao.json
                                → concluido), como o CV2 faz.
Nada toca o QNAP ou o site reais (RAIZ é temporária; BASE é o painel de teste).
"""
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fluxo_real_cv2 import doc, http, pasta_do, prancha  # noqa: E402

AVISO = "{P}-1978-S01-D00034.tif Warning: [Minor] IPTC:By-line exceeds length limit (truncated)"


def _get(base, rota):
    with urllib.request.urlopen(base + rota, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def _status(p: Path, codigo, st, motivo=""):
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": st, "status_em": "2026-10-20T15:00:00-03:00", "motivo": motivo,
                                               "versao_cv2": "2026-10-13-01", "fase": "organizado_v2"}, ensure_ascii=False), encoding="utf-8")


def _lote(base, raiz, nome, n=34, ano="1978", pacote=True):
    P = http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": "F026", "titulo": nome, "ano": int(ano), "cidade": "Santo André",
                                                       "identificacao_original": "P - " + nome, "operador": "Beatriz", "confirmar_novo": True})["codigo"]
    p = pasta_do(raiz, P, nome)
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "info_projeto.json").write_text(json.dumps({"codigo": P, "nome": nome, "fundo_codigo": "F026", "ano": ano, "folhas_esperadas": n, "estacao": "scanner-a3",
                                                     "operador": "Beatriz", "teste": False}, ensure_ascii=False), encoding="utf-8")
    _status(p, P, "processando")
    http(base, "/api/campvision/aviso", {"codigo": P, "pasta": str(p.relative_to(raiz)), "status": "processando"})
    if not pacote:
        return P, p
    prev = Path(raiz) / "_campvision" / "preview" / P
    prev.mkdir(parents=True, exist_ok=True)
    jpg = p / "01 - Desenhos e pranchas" / "JPG"
    jpg.mkdir(parents=True, exist_ok=True)
    rel = str(p.relative_to(raiz))
    docs = []
    for i in range(1, n + 1):
        cod = f"{P}-{ano}-S01-D{i:05d}"
        im = prancha(f"PLANTA {i}", [nome[:22], "Arq. Fulano", ano], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=70)
        im.save(prev / f"{cod}.jpg", "JPEG", quality=60)
        d = doc(nome, P, i, rel, ano=ano, ano_do_projeto=ano)
        d["codigo"] = cod
        d["preview"] = d["arquivo"] = f"_campvision/preview/{P}/{cod}.jpg"
        d["arquivos"] = [f"{rel}/01 - Desenhos e pranchas/JPG/{cod}.jpg"]
        docs.append(d)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps({"versao": 2, "projeto_codigo": P, "projeto_nome": nome, "fundo_codigo": "F026",
                                                                       "projeto": {"codigo": P, "titulo": nome, "ano": ano}, "documentos": docs, "itens": docs,
                                                                       "retirados": [], "propostas": {}, "avisos": []}, ensure_ascii=False), encoding="utf-8")
    _status(p, P, "pronto")
    r = http(base, "/api/campvision/aviso", {"codigo": P, "pasta": rel, "status": "pronto"})
    assert (r.get("importacao") or {}).get("criadas") == n, r
    return P, p


def _equipe(db, P):
    """Pré-condição (a equipe já trabalhou): 22 corrigidas, 9 conferidas, 3 retidas, lote aprovado."""
    c = sqlite3.connect(db)
    its = [r[0] for r in c.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY codigo", (P,))]
    for i, cod in enumerate(its, 1):
        if i in (29, 30, 32):
            c.execute("UPDATE item SET retida=1, retida_motivo=?, retida_por='rafael@camp.arq.br', revisao='conferida', revisado_por='beatriz' WHERE codigo=?",
                      ("em branco" if i != 32 else "duplicata de D00033", cod))
        elif i <= 22:
            c.execute("UPDATE item SET titulo=?, revisao='corrigida', revisado_por='beatriz', revisado_em=datetime('now') WHERE codigo=?", (f"Planta corrigida {i}", cod))
        else:
            c.execute("UPDATE item SET revisao='conferida', revisado_por='beatriz', revisado_em=datetime('now') WHERE codigo=?", (cod,))
    c.execute("UPDATE lista_processamento SET aprovado_em=datetime('now'), aprovado_por='rafael@camp.arq.br' WHERE projeto_codigo=?", (P,))
    c.commit(); c.close()


def _publicar(db, P):
    """Pré-condição (já publicado): a MESMA regra da publicação guiada para o lote (só revisão/rascunho aprovado vira 'publicado')."""
    c = sqlite3.connect(db)
    c.execute("UPDATE projeto SET status_site='no_ar' WHERE codigo=?", (P,))
    c.execute("UPDATE item SET status_site='no_ar', publicado_em=datetime('now') WHERE projeto_codigo=? AND COALESCE(retida,0)=0", (P,))
    c.execute("UPDATE lista_processamento SET etapa='publicado' WHERE projeto_codigo=? AND aprovado_em IS NOT NULL AND etapa IN ('revisao','rascunho')", (P,))
    c.commit(); c.close()


def crasa(base, raiz, db, nome, legado=False):
    P, p = _lote(base, raiz, nome)
    _equipe(db, P)
    _status(p, P, "erro", AVISO.format(P=P))            # o CAMP Vision releu e o exiftool reclamou do By-line da D00034
    http(base, "/api/campvision/aviso", {"codigo": P, "pasta": str(p.relative_to(raiz)), "status": "erro"})
    if legado:                                            # como estava em produção antes desta correção: o lote em 'erro'
        c = sqlite3.connect(db)
        c.execute("UPDATE lista_processamento SET etapa='erro' WHERE projeto_codigo=?", (P,))
        c.execute("DELETE FROM erro WHERE chave LIKE 'campvision:aviso-menor:%' AND codigo LIKE ?", (P + "%",))
        c.commit(); c.close()
    _publicar(db, P)
    print(P)


def erro_vazio(base, raiz, nome):
    P, p = _lote(base, raiz, nome, pacote=False)
    _status(p, P, "erro", "Error: o modelo de leitura não respondeu (timeout)")
    http(base, "/api/campvision/aviso", {"codigo": P, "pasta": str(p.relative_to(raiz)), "status": "erro"})
    print(P)


def erro_com_folhas(base, raiz, db, nome):
    P, p = _lote(base, raiz, nome, n=4)
    _status(p, P, "erro", "Error: o modelo de leitura não respondeu (timeout)")
    http(base, "/api/campvision/aviso", {"codigo": P, "pasta": str(p.relative_to(raiz)), "status": "erro"})
    print(P)


def releitura(base, raiz, db, P):
    """O CV2 atende o que está pedido para o projeto: comparacao.json da releitura com o que mudou, depois concluído (ok)."""
    c = sqlite3.connect(db)
    pedidos = c.execute("SELECT id, item_codigo FROM pedido_releitura WHERE projeto_codigo=? AND estado='pedido'", (P,)).fetchall()
    c.close()
    p = pasta_do(raiz, P)
    quando = "20261020-160000"
    d = p / "catalogacao" / "releituras" / quando
    d.mkdir(parents=True, exist_ok=True)
    comp = {}
    for pid, item in pedidos:
        alvo = item or f"{P}-1978-S01-D00034"
        # CAMP-134: o formato REAL do CV2 (campvision-new nucleo/releitura.py): nome de campo do CV2 (titulo_prancha) e campos que não são da folha
        comp[alvo] = {"mudou": {"titulo_prancha": {"antes": "PLANTA 34", "agora": "PLANTA DE COBERTURA", "confianca_agora": 0.9},
                                "escala": {"antes": "1:50", "agora": "1:100", "confianca_agora": 0.8},
                                "codigo_unidade": {"antes": "", "agora": "BL-A", "confianca_agora": 0.7}},
                      "preencheu": ["codigo_unidade"], "erro": ""}
    resumo = {"projeto_codigo": P, "escopo": "folha", "motivo": "teste", "pedido_por": "op@camp.arq.br", "relido_em": "2026-10-20T16:00:00-03:00",
              "documentos": list(comp), "relidos": len(comp), "com_mudanca": len(comp), "campos_preenchidos": 1, "falhas": [], "custo_usd": 0.01,
              "regravados": len(comp), "recodificadas": {}, "pasta": "x"}
    (d / "comparacao.json").write_text(json.dumps({"resumo": resumo, "documentos": comp}, ensure_ascii=False, indent=1), encoding="utf-8")
    for pid, _ in pedidos:
        http(base, f"/api/estacoes/pedidos-releitura/{pid}/iniciado", {"estacao": "campvision2"})
        http(base, f"/api/estacoes/pedidos-releitura/{pid}/concluido", {"ok": True, "mensagem": "relida", "relidos": 1, "com_mudanca": 1, "escopo": "folha"})
    print(json.dumps({"pedidos": len(pedidos), "comparacao": list(comp)}))


def muitas(raiz, P):
    """CAMP-134: o caso do print de 21/10 — 6 releituras do projeto inteiro (formato real do CV2). A mais recente muda o título de 12 folhas
    (D00001-D00012) e a escala de 5 (D00013-D00017); as 5 antigas mudavam o título das mesmas folhas para outra coisa (ficam no histórico);
    todas mudam o código de unidade de 30 folhas (não é campo da folha: só informação)."""
    p = pasta_do(raiz, P)
    for k in range(6):
        quando = f"2026102{k}-10{k}000"
        docs = {}
        for n in range(1, 31):
            cod = f"{P}-1978-S01-D{n:05d}"
            mud = {"codigo_unidade": {"antes": "", "agora": f"BL-{k}", "confianca_agora": 0.6}}
            if n <= 12:
                mud["titulo_prancha"] = {"antes": f"PLANTA {n}", "agora": (f"PRANCHA {n:02d} — RELIDA" if k == 5 else f"VERSAO ANTIGA {k} {n}"), "confianca_agora": 0.9}
            elif n <= 17 and k == 5:
                mud["escala"] = {"antes": "1:50", "agora": "1:200", "confianca_agora": 0.8}
            docs[cod] = {"mudou": mud, "preencheu": ["codigo_unidade"], "erro": ""}
        d = p / "catalogacao" / "releituras" / quando
        d.mkdir(parents=True, exist_ok=True)
        resumo = {"projeto_codigo": P, "escopo": "projeto", "motivo": "teste", "pedido_por": "op@camp.arq.br", "relidos": 34, "com_mudanca": 30, "documentos": list(docs)}
        (d / "comparacao.json").write_text(json.dumps({"resumo": resumo, "documentos": docs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"releituras": 6}))


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    {"crasa": lambda: crasa(*a), "legado": lambda: crasa(*a, legado=True), "erro_vazio": lambda: erro_vazio(*a),
     "erro_com_folhas": lambda: erro_com_folhas(*a), "releitura": lambda: releitura(*a), "muitas": lambda: muitas(*a)}[cmd]()
