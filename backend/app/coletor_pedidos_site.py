"""WP-AUD-01 · Coletor de pedidos do WordPress (a cada 10 minutos por padrão).

Novo protocolo: GET /wp-json/camp/v1/solicitacoes (só leitura), grava lote em
pedido_site e COMMIT no SQLite, depois POST /solicitacoes/confirmar {"ids":[...]}.
Sem ACK, o WordPress deixa o pedido pendente para reenvio. A chave site_id
garante idempotência quando uma confirmação falha; o processamento posterior
pode ser retomado de pedido_site sem consultar o site novamente.
As solicitações e correções viram entidades do painel após o armazenamento.
Falhas de rede são registradas em pedido_site_coleta e não derrubam o painel.
"""
from __future__ import annotations

import json
import logging
import re

from .log_tecnico import registrar

CODIGO = re.compile(r"^F\d{3}-P\d{4}(?:-\d{4}-S\d{2}-D\d{5,6})?$")
FINALIDADES = ("publicacao", "pesquisa", "editorial", "familia", "exposicao", "outro")


def _minutos(con) -> int:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='site.coleta_pedidos_min'").fetchone()
    v = str(r[0]).strip() if r and r[0] is not None else "10"
    return int(v) if v.isdigit() else 10


def _txt(v, maximo: int) -> str | None:
    t = " ".join(str(v or "").split())[:maximo]
    return t or None


def _codigo_conhecido(con, cod: str) -> str | None:
    """O código mais específico que o painel conhece: a folha, senão o projeto, senão o fundo."""
    cod = (cod or "").strip().upper()
    if not CODIGO.match(cod):
        return None
    if cod.count("-") == 4 and con.execute("SELECT 1 FROM item WHERE codigo=?", (cod,)).fetchone():
        return cod
    if con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod[:10],)).fetchone():
        return cod[:10]
    if con.execute("SELECT 1 FROM fundo WHERE codigo=?", (cod[:4],)).fetchone():
        return cod[:4]
    return None


def _importar_um(con, p: dict) -> tuple[str, int]:
    tipo = str(p.get("tipo") or "alta-resolucao")
    nome = _txt(p.get("nome"), 120) or "(sem nome)"
    email = _txt(p.get("email"), 200)
    inst = _txt(p.get("instituicao"), 200)
    msg = _txt(p.get("mensagem"), 2000)
    cod_bruto = (_txt(p.get("codigo"), 60) or "").upper()
    fin = str(p.get("finalidade") or "").strip().lower()
    fin = fin if fin in FINALIDADES else "outro"
    if tipo == "correcao":
        cod = _codigo_conhecido(con, cod_bruto)
        if cod:
            quem = f"{nome} ({email})" if email else nome
            eid = con.execute("""INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por)
                                 VALUES ('aviso','outro','site',?,?,?)""", (cod, msg or "Correção informada pelo site (sem texto)", quem)).lastrowid
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('erro',?,'criado','site',?)",
                        (str(eid), json.dumps({"codigo": cod, "gravidade": "aviso", "origem": "site", "via": "coleta_pedidos"}, ensure_ascii=False)))
            return "erro", eid
        msg = f"Correção informada pelo site para {cod_bruto or '(código não informado)'}: {msg or ''}".strip()   # sem código conhecido: uma pessoa precisa olhar
    elif tipo == "consulta":
        msg = f"Consulta aos originais: {cod_bruto or '(código não informado)'}" + (f". {msg}" if msg else "")
    sid = con.execute("INSERT INTO solicitacao (solicitante, email, instituicao, finalidade, detalhe, origem) VALUES (?,?,?,?,?,'site')",
                      (nome, email, inst, fin, msg)).lastrowid
    if tipo == "alta-resolucao" and CODIGO.match(cod_bruto):
        con.execute("INSERT OR IGNORE INTO solicitacao_item (solicitacao_id, codigo, formato) VALUES (?,?,'tif')", (sid, cod_bruto))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'criada','site',?)",
                (str(sid), json.dumps({"solicitante": nome, "origem": "site", "tipo": tipo, "itens": 1 if (tipo == "alta-resolucao" and CODIGO.match(cod_bruto)) else 0}, ensure_ascii=False)))
    return "solicitacao", sid


def processar_pendentes(con) -> dict:
    """Transforma o que está em pedido_site (pendente/falhou) em solicitacao ou erro. Uma falha não impede os outros."""
    novos = importadas = falhas = 0
    solicitacoes: list[int] = []
    for r in con.execute("SELECT site_id, payload FROM pedido_site WHERE situacao IN ('pendente','falhou') ORDER BY site_id").fetchall():
        try:
            con.execute("SAVEPOINT pedido")
            destino, did = _importar_um(con, json.loads(r["payload"]))
            con.execute("UPDATE pedido_site SET destino=?, destino_id=?, situacao='importado', erro=NULL, importado_em=datetime('now') WHERE site_id=?", (destino, did, r["site_id"]))
            con.execute("RELEASE pedido")
            importadas += 1
            if destino == "solicitacao":
                solicitacoes.append(did)
        except Exception as e:  # noqa: BLE001
            con.execute("ROLLBACK TO pedido"); con.execute("RELEASE pedido")
            con.execute("UPDATE pedido_site SET situacao='falhou', erro=? WHERE site_id=?", (f"{type(e).__name__}: {str(e)[:160]}", r["site_id"]))
            falhas += 1
    con.commit()
    return {"importadas": importadas, "falhas": falhas, "solicitacoes": solicitacoes}



LIMITE_LOTE = 200
MAX_LOTES = 20  # impede que a requisição manual fique indefinidamente aberta


def _buscar_lote(wp) -> list[dict]:
    """GET não marca o pedido. Se a resposta vier inválida, não confirmar nenhum ID."""
    r = wp.h.get("/wp-json/camp/v1/solicitacoes", params={"limite": LIMITE_LOTE})
    if r.status_code == 404:
        raise RuntimeError("O site ainda não tem a rota camp/v1/solicitacoes")
    if r.status_code in (401, 403):
        raise RuntimeError(f"O site recusou as credenciais ({r.status_code})")
    if r.status_code >= 400:
        raise RuntimeError(f"O site respondeu {r.status_code} ao buscar solicitações")
    dados = r.json()
    if isinstance(dados, dict):
        dados = dados.get("itens", dados.get("items"))
    if not isinstance(dados, list):
        raise RuntimeError("O site devolveu formato inválido para as solicitações")
    ids = set()
    for d in dados:
        if not isinstance(d, dict) or type(d.get("id")) is not int or d["id"] <= 0:
            raise RuntimeError("O site devolveu solicitação sem ID válido; nada foi confirmado")
        if d["id"] in ids:
            raise RuntimeError("O site devolveu IDs repetidos no mesmo lote; nada foi confirmado")
        ids.add(d["id"])
    return dados


def _confirmar_lote(wp, ids: list[int]) -> None:
    """Idempotente: o WP aceita IDs novos ou que já haviam recebido ACK."""
    r = wp.h.post("/wp-json/camp/v1/solicitacoes/confirmar", json={"ids": ids})
    if r.status_code >= 400:
        raise RuntimeError(f"Não foi possível confirmar solicitações no site (HTTP {r.status_code}); serão reenviadas")
    dados = r.json()
    if not isinstance(dados, dict):
        raise RuntimeError("O site não devolveu o resultado da confirmação; serão reenviadas")
    aceitos = set(dados.get("confirmados") or []) | set(dados.get("ja_confirmados") or [])
    if aceitos != set(ids):
        raise RuntimeError(f"Confirmação parcial do site ({len(aceitos)}/{len(ids)}); será tentada novamente")


def coletar(con=None, wp=None, avisar: bool = True) -> dict:
    """Uma volta da coleta. Só confirma remotamente DEPOIS do commit local."""
    from .db import connect
    fechar = con is None
    con = con or connect()
    out = {"lidas": 0, "novas": 0, "confirmadas": 0, "importadas": 0, "erro": None}
    try:
        try:
            wp = wp or __import__("app.wp", fromlist=["WP"]).WP()
            for _ in range(MAX_LOTES):
                dados = _buscar_lote(wp)
                if not dados:
                    break
                novos_lote = 0
                try:
                    for d in dados:
                        novos_lote += con.execute(
                            """INSERT OR IGNORE INTO pedido_site (site_id, tipo, codigo, criado_no_site, payload)
                               VALUES (?,?,?,?,?)""",
                            (d["id"], str(d.get("tipo") or ""), str(d.get("codigo") or ""),
                             str(d.get("criado_em") or ""), json.dumps(d, ensure_ascii=False)),
                        ).rowcount
                    con.commit()  # ACK só depois deste ponto
                except Exception:
                    con.rollback()
                    raise
                out["lidas"] += len(dados)
                out["novas"] += novos_lote
                _confirmar_lote(wp, [d["id"] for d in dados])
                out["confirmadas"] += len(dados)
                if len(dados) < LIMITE_LOTE:
                    break
            else:
                # Próxima rodada segue com o que ainda não foi confirmado.
                out["erro"] = f"Coleta limitada a {MAX_LOTES * LIMITE_LOTE} pedidos por rodada; continuará na próxima"
        except Exception as e:  # noqa: BLE001
            # Não confirmar remotamente é seguro: os dados locais já persistidos
            # permanecem e o WordPress enviará os IDs pendentes outra vez.
            out["erro"] = str(e)[:200]
        proc = processar_pendentes(con)
        out["importadas"] = proc["importadas"]
        if proc["falhas"] and not out["erro"]:
            out["erro"] = f"{proc['falhas']} pedido(s) não puderam ser importados (ficam para a próxima volta)"
        con.execute("INSERT INTO pedido_site_coleta (lidas, novas, importadas, erro) VALUES (?,?,?,?)",
                    (out["lidas"], out["novas"], out["importadas"], out["erro"]))
        con.commit()
        if avisar:
            from .rotas_pedidos import _avisar
            for sid in proc["solicitacoes"]:
                _avisar(sid)
        if out["erro"]:
            registrar(logging.WARNING, "coleta_pedidos_site", "Coleta de pedidos do site com problema", erro=out["erro"][:160])
    except Exception as e:  # noqa: BLE001
        out["erro"] = out["erro"] or str(e)[:200]
    finally:
        if fechar:
            con.close()
    return out


def status(con) -> dict:
    u = con.execute("SELECT quando, lidas, novas, importadas, erro FROM pedido_site_coleta ORDER BY id DESC LIMIT 1").fetchone()
    return {"minutos": _minutos(con), "ultima": dict(u) if u else None,
            "pendentes": con.execute("SELECT COUNT(*) FROM pedido_site WHERE situacao<>'importado'").fetchone()[0],
            "importados": con.execute("SELECT COUNT(*) FROM pedido_site WHERE situacao='importado'").fetchone()[0]}
