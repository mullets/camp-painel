"""CAMP-050 · LGPD no painel: guarda de 24 meses dos dados pessoais e "apagar esta pessoa".

Rotina diária (main._lgpd_periodica) com lgpd.modo = simular (PADRÃO: só conta e registra) ou aplicar (anonimiza). Cobre:
  uso_download (formulário de download), solicitacao + solicitacao_item (pedidos), erro.relatado_por (relatos do site) e os eventos desses pedidos.
Anonimizar = nome/e-mail/telefone/instituição (e o texto livre do pedido) saem; ficam as contagens (uso, material, datas, itens).
Não é apagado: pedido com valor/orçamento (obrigação fiscal/contábil) — fica contado em `mantidas_obrigacao_legal`.
"Apagar dados desta pessoa" também chama o site (POST /wp-json/camp/v1/painel/pessoa/apagar); falha do site NÃO desfaz o local: fica em
lgpd_pendente_site e a rotina repete. Logs e eventos levam só QUANTIDADES (nunca nome ou e-mail)."""
from __future__ import annotations

import json
import logging
from datetime import date

REMOVIDO = "(removido)"
CHAVES_PESSOAIS = ("solicitante", "nome", "email", "e_mail", "telefone", "instituicao")


def _cfg(con, chave: str, padrao: str) -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return ((r[0] if r else None) or padrao).strip()


def modo(con) -> str:
    return "aplicar" if _cfg(con, "lgpd.modo", "simular").lower() == "aplicar" else "simular"


def meses(con) -> int:
    v = _cfg(con, "lgpd.meses", "24")
    return int(v) if v.isdigit() and int(v) > 0 else 24


def _corte(con) -> str:
    return con.execute("SELECT datetime('now', ?)", (f"-{meses(con)} months",)).fetchone()[0]


def _eventos_de_pedidos(con, ids: list[int]) -> list[int]:
    out = []
    for k in range(0, len(ids), 500):
        parte = [str(i) for i in ids[k:k + 500]]
        out += [r[0] for r in con.execute(f"SELECT id FROM evento WHERE entidade='solicitacao' AND codigo IN ({','.join('?' * len(parte))}) AND detalhe IS NOT NULL", parte)]
    return out


def _limpar_evento(con, eid: int) -> int:
    r = con.execute("SELECT detalhe FROM evento WHERE id=?", (eid,)).fetchone()
    try:
        d = json.loads(r[0] or "null")
    except (ValueError, TypeError):
        d = None
    if not isinstance(d, dict) or not any(k in d for k in CHAVES_PESSOAIS):
        return 0
    for k in CHAVES_PESSOAIS:
        d.pop(k, None)
    d["anonimizado"] = True
    con.execute("UPDATE evento SET detalhe=? WHERE id=?", (json.dumps(d, ensure_ascii=False), eid))
    return 1


def _anonimizar_pedidos(con, ids: list[int]) -> tuple[int, int]:
    """(pedidos, eventos) anonimizados."""
    n = ev = 0
    for k in range(0, len(ids), 500):
        parte = ids[k:k + 500]
        n += con.execute(f"""UPDATE solicitacao SET solicitante=?, email=NULL, instituicao=NULL, detalhe=NULL, anonimizada=1
                              WHERE anonimizada=0 AND id IN ({','.join('?' * len(parte))})""", [REMOVIDO, *parte]).rowcount
    for eid in _eventos_de_pedidos(con, ids):
        ev += _limpar_evento(con, eid)
    return n, ev


def contar_e_aplicar(con, aplicar: bool) -> dict:
    """Só QUANTIDADES. Com aplicar=False nada é gravado."""
    corte = _corte(con)
    uso = [r[0] for r in con.execute("SELECT id FROM uso_download WHERE anonimizada=0 AND apagada=0 AND recebida_em IS NOT NULL AND recebida_em < ?", (corte,))]
    ped = [r[0] for r in con.execute("SELECT id FROM solicitacao WHERE anonimizada=0 AND valor IS NULL AND recebida_em < ?", (corte,))]
    mantidas = con.execute("SELECT COUNT(*) FROM solicitacao WHERE anonimizada=0 AND valor IS NOT NULL AND recebida_em < ?", (corte,)).fetchone()[0]
    erros = [r[0] for r in con.execute("""SELECT id FROM erro WHERE origem='site' AND relatado_por IS NOT NULL AND relatado_por<>? AND criado_em < ?""", (REMOVIDO, corte))]
    out = {"uso_download": len(uso), "solicitacao": len(ped), "erro_relatado_por": len(erros), "mantidas_obrigacao_legal": mantidas, "eventos": 0, "meses": meses(con)}
    out["eventos"] = sum(1 for e in _eventos_de_pedidos(con, ped) if _tem_pessoal(con, e))
    if aplicar:
        for k in range(0, len(uso), 500):
            parte = uso[k:k + 500]
            con.execute(f"""UPDATE uso_download SET nome=?, email=NULL, telefone=NULL, instituicao=NULL, resposta_json=NULL, anonimizada=1
                             WHERE id IN ({','.join('?' * len(parte))})""", [REMOVIDO, *parte])
        _, ev = _anonimizar_pedidos(con, ped)
        out["eventos"] = ev
        for k in range(0, len(erros), 500):
            parte = erros[k:k + 500]
            con.execute(f"UPDATE erro SET relatado_por=? WHERE id IN ({','.join('?' * len(parte))})", [REMOVIDO, *parte])
    return out


def _tem_pessoal(con, eid: int) -> bool:
    r = con.execute("SELECT detalhe FROM evento WHERE id=?", (eid,)).fetchone()
    try:
        d = json.loads(r[0] or "null")
    except (ValueError, TypeError):
        return False
    return isinstance(d, dict) and any(k in d for k in CHAVES_PESSOAIS)


def rodar(con, ator: str = "rotina") -> dict:
    """Uma execução da rotina: respeita lgpd.modo. Grava evento e log só com quantidades."""
    m = modo(con)
    r = contar_e_aplicar(con, m == "aplicar")
    r["modo"] = m
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lgpd','lgpd','lgpd_retencao',?,?)", (ator, json.dumps(r, ensure_ascii=False)))
    con.execute("UPDATE configuracao SET valor=? WHERE chave='lgpd.ultima_execucao'", (date.today().isoformat(),))
    con.commit()
    try:
        from .log_tecnico import registrar
        registrar(logging.INFO, "lgpd_retencao", f"LGPD ({m}): {r['uso_download']} downloads, {r['solicitacao']} pedidos, {r['erro_relatado_por']} relatos", **{k: v for k, v in r.items() if isinstance(v, int)})
    except Exception:  # noqa: BLE001
        pass
    return r


def precisa_rodar_hoje(con) -> bool:
    return _cfg(con, "lgpd.ultima_execucao", "") != date.today().isoformat()


# ---------------- apagar UMA pessoa ----------------
def apagar_pessoa_local(con, email: str) -> dict:
    """Apaga/anonimiza esta pessoa nas cópias do painel. Só quantidades."""
    em = email.strip().lower()
    from . import uso_formularios
    ids = [r[0] for r in con.execute("SELECT id FROM uso_download WHERE apagada=0 AND lower(email)=?", (em,))]
    uso = uso_formularios.apagar_ids(con, ids) if ids else 0
    ped = [r[0] for r in con.execute("SELECT id FROM solicitacao WHERE anonimizada=0 AND lower(email)=?", (em,))]
    n_ped, n_ev = _anonimizar_pedidos(con, ped) if ped else (0, 0)
    erros = con.execute("UPDATE erro SET relatado_por=? WHERE origem='site' AND relatado_por IS NOT NULL AND relatado_por<>? AND lower(relatado_por) LIKE ?",
                        (REMOVIDO, REMOVIDO, f"%{em}%")).rowcount
    con.commit()
    return {"uso_download": uso, "solicitacao": n_ped, "eventos": n_ev, "erro_relatado_por": erros}


def chamar_site(con, email: str) -> dict:
    """Pede ao site para apagar a pessoa. Falha NÃO levanta: registra em lgpd_pendente_site (o e-mail fica ali só até o site responder) e devolve {ok:False,...}."""
    try:
        from .wp import WP
        r = WP().apagar_pessoa(email)
        con.execute("DELETE FROM lgpd_pendente_site WHERE lower(email)=lower(?)", (email.strip(),))
        con.commit()
        return {"ok": True, "contagens": r}
    except Exception as e:  # noqa: BLE001
        erro = str(e)[:200].replace(email, "…") if email else str(e)[:200]
        row = con.execute("SELECT id FROM lgpd_pendente_site WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
        if row:
            con.execute("UPDATE lgpd_pendente_site SET tentativas=tentativas+1, ultimo_erro=?, ultima_em=datetime('now') WHERE id=?", (erro, row[0]))
        else:
            con.execute("INSERT INTO lgpd_pendente_site (email, tentativas, ultimo_erro, ultima_em) VALUES (?,1,?,datetime('now'))", (email.strip().lower(), erro))
        con.commit()
        return {"ok": False, "erro": erro, "repetira": True}


def repetir_pendentes(con) -> dict:
    feitas = falhas = 0
    for r in con.execute("SELECT email FROM lgpd_pendente_site ORDER BY id").fetchall():
        if chamar_site(con, r[0])["ok"]:
            feitas += 1
        else:
            falhas += 1
    return {"repetidas_ok": feitas, "ainda_pendentes": falhas}


def apagar_pessoa(con, email: str, ator: str) -> dict:
    """Local + site. O local nunca é desfeito pela falha do site."""
    local = apagar_pessoa_local(con, email)
    site = chamar_site(con, email)
    import hashlib
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lgpd','lgpd','lgpd_pessoa_apagada',?,?)",
                (ator, json.dumps({**local, "site_ok": site["ok"], "email_hash": hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]}, ensure_ascii=False)))
    con.commit()
    return {"local": local, "site": site}


def resumo(con) -> dict:
    corte_cont = contar_e_aplicar(con, False)
    pend = con.execute("SELECT COUNT(*) FROM lgpd_pendente_site").fetchone()[0]
    ult = con.execute("SELECT quando, detalhe FROM evento WHERE tipo='lgpd_retencao' ORDER BY id DESC LIMIT 1").fetchone()
    return {"modo": modo(con), "meses": meses(con), "ultima_execucao": _cfg(con, "lgpd.ultima_execucao", "") or None, "a_anonimizar": corte_cont,
            "pendentes_no_site": pend, "ultimo_registro": ({"em": ult[0], **(json.loads(ult[1]) if ult[1] else {})} if ult else None)}
