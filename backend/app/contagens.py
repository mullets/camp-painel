"""UX-05: UMA fonte para os números do painel.

Antes cada rota contava do seu jeito e o mesmo dado aparecia com números diferentes (Home × Material novo × Máquinas × Relatórios × menu).
Aqui fica a definição ÚNICA de cada métrica; /api/painel, /api/pendencias, /api/filas, /api/erros/contagem, /api/estacoes e
/api/relatorios leem daqui (e devolvem o bloco "contagens", com "medido_em", para a tela dizer "atualizado há X").

- Lotes: os de pendencias.lotes() (lote não descartado, de projeto que não foi juntado nem descartado), com a fase de filas_fase.
- Problemas abertos: situação aberto/em correção. "Impedem publicar": a mesma regra do botão Publicar (publicacao.TRAVA_SQL).
- Pedidos abertos: tudo menos entregue/recusado; "esperando": aguarda resposta/orçamento.
- No site: folha/projeto/fundo com status_site='no_ar' (projeto juntado ou descartado não conta; fundo só ativo).
- Precisa de você (o número do menu e da saudação): decisões + material novo (importar + conferir) + problemas que impedem publicar.
- Estações de captura ligadas: foto/contex/universal que respondem na rede OU cujo programa deu sinal (o CAMP Vision e o QNAP não contam).
- Estado do topo: o PIOR estado entre QNAP, site, CAMP Vision, cópia do acervo e cópia de segurança (ok < atencao < critico).
"""
from __future__ import annotations

from datetime import datetime, timezone

ERROS_ABERTOS = "situacao IN ('aberto','em_correcao')"
ERROS_PEDEM_ACAO = ERROS_ABERTOS + " AND gravidade<>'aviso'"     # UX-19: o que bloqueia ou pede correção (os avisos têm aba própria)
ERROS_AVISOS = ERROS_ABERTOS + " AND gravidade='aviso'"
PEDIDOS_ABERTOS = "situacao NOT IN ('entregue','recusada')"
PEDIDOS_ESPERANDO = "situacao IN ('aguarda_resposta','aguarda_orcamento')"
PROJETO_VIVO = "mesclado_em IS NULL AND descartado_em IS NULL"
LOTE_VIVO = ("l.descartado_em IS NULL AND EXISTS (SELECT 1 FROM projeto p_ WHERE p_.codigo=l.projeto_codigo "
             "AND p_.mesclado_em IS NULL AND p_.descartado_em IS NULL)")
TIPOS_CAPTURA = ("foto", "contex", "universal")
ORDEM_NIVEL = {"ok": 0, None: 0, "atencao": 1, "critico": 2}


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _q(con, sql: str, *p) -> int:
    return con.execute(sql, p).fetchone()[0] or 0


def erros_abertos(con) -> int:
    return _q(con, f"SELECT COUNT(*) FROM erro WHERE {ERROS_ABERTOS}")


def erros_bloqueantes(con) -> int:
    from .publicacao import TRAVA_SQL
    return _q(con, f"SELECT COUNT(*) FROM erro WHERE {ERROS_ABERTOS} AND {TRAVA_SQL}")


def pedidos_abertos(con) -> int:
    return _q(con, f"SELECT COUNT(*) FROM solicitacao WHERE {PEDIDOS_ABERTOS}")


def pedidos_esperando(con) -> int:
    return _q(con, f"SELECT COUNT(*) FROM solicitacao WHERE {PEDIDOS_ESPERANDO}")


def site_divergencias(con) -> int:
    return _q(con, "SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0")


def no_site(con) -> dict:
    """Quanto do acervo já está no site: folhas, projetos e fundos (publicado / total)."""
    return {
        "folhas": {"no_ar": _q(con, "SELECT COUNT(*) FROM item WHERE status_site='no_ar'"), "total": _q(con, "SELECT COUNT(*) FROM item")},
        "projetos": {"no_ar": _q(con, f"SELECT COUNT(*) FROM projeto WHERE status_site='no_ar' AND {PROJETO_VIVO}"),
                     "total": _q(con, f"SELECT COUNT(*) FROM projeto WHERE {PROJETO_VIVO}"),
                     "sem_folhas": _q(con, "SELECT COUNT(*) FROM projeto p WHERE p.mesclado_em IS NULL AND p.descartado_em IS NULL AND p.status_site!='no_ar' "
                                           "AND NOT EXISTS (SELECT 1 FROM item i WHERE i.projeto_codigo=p.codigo)")},
        "fundos": {"no_ar": _q(con, "SELECT COUNT(*) FROM fundo WHERE ativo=1 AND status_site='no_ar'"), "total": _q(con, "SELECT COUNT(*) FROM fundo WHERE ativo=1")},
    }


def no_site_sem_teste(con) -> dict:
    """O "no site" dos Relatórios: o mesmo de no_site, SEM os projetos de teste (lote_teste=1), que o relatório não conta.
    É outra métrica (e a tela diz "sem contar projetos de teste"); fica aqui para a regra continuar num lugar só."""
    return {"folhas": _q(con, "SELECT COUNT(*) FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE p.lote_teste=0 AND i.status_site='no_ar'"),
            "projetos": _q(con, f"SELECT COUNT(*) FROM projeto WHERE lote_teste=0 AND {PROJETO_VIVO} AND status_site='no_ar'")}


def lotes_por_etapa(con) -> dict:
    """{etapa: n} dos lotes que contam (os mesmos de pendencias.lotes)."""
    out = {e: 0 for e in ("enviado", "processando", "revisao", "rascunho", "publicado", "erro")}
    for etapa, n in con.execute(f"SELECT l.etapa, COUNT(*) FROM lista_processamento l WHERE {LOTE_VIVO} GROUP BY l.etapa"):
        out[etapa] = n
    return out


def pedem_acao(con, n: dict, decisoes: list[dict], usuario_id: int | None = None) -> dict:
    """UX-19 (regra única "itens que pedem ação de você") + UX-03 (o que esta pessoa escondeu por 7 dias sai da conta dela).
    Preenche em `n`: erros_pedem_acao, erros_avisos e o bloco pedem_acao (os números do menu). O "Precisa de você" do menu, da
    saudação e da Home é pedem_acao.precisa_de_voce = decisões + material novo + problemas que impedem publicar, menos os escondidos.
    (Os lotes escondidos já saíram de material_novo em contar_pendencias.)"""
    from .publicacao import TRAVA_SQL
    n["erros_pedem_acao"] = _q(con, f"SELECT COUNT(*) FROM erro WHERE {ERROS_PEDEM_ACAO}")
    n["erros_avisos"] = n["erros_abertos"] - n["erros_pedem_acao"]
    esc_dec, esc_bloq, esc_prob = 0, 0, 0
    if usuario_id:
        from .qualidade_base import adiadas
        fora_ = adiadas(con, usuario_id)
        ids_dec = {int(k[8:]) for k in fora_ if k.startswith("decisao:") and k[8:].isdigit()}
        ids_err = [int(k[5:]) for k in fora_ if k.startswith("erro:") and k[5:].isdigit()]
        esc_dec = sum(1 for d in decisoes if d["id"] in ids_dec)
        if ids_err:
            marc = ",".join("?" * len(ids_err))
            esc_bloq = _q(con, f"SELECT COUNT(*) FROM erro WHERE id IN ({marc}) AND {ERROS_ABERTOS} AND {TRAVA_SQL}", *ids_err)
            esc_prob = _q(con, f"SELECT COUNT(*) FROM erro WHERE id IN ({marc}) AND {ERROS_PEDEM_ACAO}", *ids_err)
    n["pedem_acao"] = {"precisa_de_voce": n["decisoes"] - esc_dec + n["material_novo"] + n["erros_bloqueantes"] - esc_bloq, "decisoes": n["decisoes"],
                       "material_novo": n["material_novo"], "problemas": n["erros_pedem_acao"] - esc_prob, "pedidos": n["pedidos_abertos"],
                       "emprestimos": n["emprestimos_atrasados"]}
    return n["pedem_acao"]


def precisa_de_voce(n: dict) -> int:
    """O número do "Precisa de você": o mesmo de pedem_acao (sem ele, a soma sem escondidos)."""
    pa = n.get("pedem_acao")
    if isinstance(pa, dict) and pa.get("precisa_de_voce") is not None:
        return int(pa["precisa_de_voce"])
    return int(n.get("decisoes") or 0) + int(n.get("material_novo") or 0) + int(n.get("erros_bloqueantes") or 0)


def medir(con, *, n: dict | None = None, usuario_id: int | None = None) -> dict:
    """Todas as contagens numa resposta só. `n` = contar_pendencias já calculado (evita contar duas vezes)."""
    if n is None:
        from .pendencias import contar_pendencias
        n = contar_pendencias(con, usuario_id=usuario_id)
    out = {k: v for k, v in n.items() if not k.startswith("_")}
    ns = no_site(con)
    out.update({
        "folhas_no_site": ns["folhas"]["no_ar"], "folhas_total": ns["folhas"]["total"],
        "projetos_no_site": ns["projetos"]["no_ar"], "projetos_total": ns["projetos"]["total"],
        "fundos_no_site": ns["fundos"]["no_ar"], "fundos_total": ns["fundos"]["total"],
        **{f"{k}_no_site_sem_teste": v for k, v in no_site_sem_teste(con).items()},
        "site_divergencias": site_divergencias(con),
        "lotes_etapa": lotes_por_etapa(con),
        "precisa_de_voce": precisa_de_voce(n),
        "medido_em": agora_iso(),
    })
    return out


# ---------------- máquinas e estado do topo ----------------
def estacoes_ligadas(maquinas: list[dict]) -> dict:
    """{'total', 'ligadas', 'nomes'} das estações de captura: ligada = responde na rede OU o programa deu sinal."""
    cap = [m for m in maquinas if m.get("tipo") in TIPOS_CAPTURA]
    lig = [m for m in cap if m.get("online") is True or m.get("app_online") is True]
    return {"total": len(cap), "ligadas": len(lig), "nomes": [m.get("nome") for m in lig]}


def _pior(*niveis) -> str:
    return max((x or "ok" for x in niveis), key=lambda x: ORDEM_NIVEL.get(x, 0), default="ok")


def nivel_site(http: dict | None) -> tuple[str | None, str]:
    """(nivel, texto curto) da última medição do site: online = ok; lento (> 3 s) ou sem resposta uma vez = atencao;
    sem resposta 2 vezes seguidas = critico. Sem medição: (None, 'sem medida')."""
    if not http or not http.get("estado"):
        return None, "sem medida"
    if http.get("alerta"):
        return "critico", "sem resposta"
    e = http["estado"]
    if e == "lento":
        return "atencao", "lento"
    if e == "sem_resposta":
        return "atencao", "não respondeu uma vez"
    return "ok", "ok"


def estado_geral(con, *, qnap_montado: bool | None, site_http: dict | None, backup: dict | None, maquinas: list[dict] | None = None,
                 replica_estado: dict | None = None) -> dict:
    """O estado do topo: o PIOR entre as partes. Cada parte: {'id', 'nivel' (ok|atencao|critico|None = sem medida), 'texto'}."""
    from . import qnap_coletor, replica
    partes = []
    snap = qnap_coletor.ultima(con) or {}
    if qnap_montado is False:
        partes.append({"id": "qnap", "nivel": "critico", "texto": "QNAP desconectado"})
    else:
        niv, pct = qnap_coletor.nivel_espaco(con, snap.get("total_gb"), snap.get("livre_gb"))
        mapa = {"ok": "ok", "aviso": "atencao", "critico": "critico"}
        txt = {None: "QNAP sem medida", "ok": "QNAP ok", "aviso": "QNAP em atenção", "critico": "QNAP quase cheio"}[niv]
        partes.append({"id": "qnap", "nivel": mapa.get(niv), "texto": txt, "livre_pct": pct, "medido_em": snap.get("coletado_em")})
    sn, st = nivel_site(site_http)
    partes.append({"id": "site", "nivel": sn, "texto": f"site {st}", "ms": (site_http or {}).get("ms"), "medido_em": (site_http or {}).get("medido_em")})
    cv = next((m for m in (maquinas or []) if m.get("tipo") == "processamento"), None)
    idade = cv.get("app_heartbeat_idade_segundos") if cv else None
    if idade is not None:
        partes.append({"id": "campvision", "nivel": "critico" if idade > 3600 else ("atencao" if idade > 180 else "ok"),
                       "texto": "CAMP Vision sem sinal" if idade > 180 else "CAMP Vision ok"})
    rp = replica_estado if replica_estado is not None else replica.estado(con)   # /api/estacoes passa a leitura da sonda (sem SMB na requisição)
    if rp.get("configurada") and not rp.get("nivel"):
        partes.append({"id": "replica", "nivel": None, "texto": "cópia do acervo sem medida"})
    elif rp.get("configurada"):
        partes.append({"id": "replica", "nivel": {"ok": "ok", "aviso": "atencao", "critico": "critico"}.get(rp.get("nivel")),
                       "texto": {"ok": "cópia do acervo em dia", "aviso": "cópia do acervo atrasada"}.get(rp.get("nivel"), "cópia do acervo parada")})
    if backup is not None:                               # a mesma regra do alerta "Cópia de segurança atrasada" (alertas.avaliar)
        if not backup.get("existe"):
            partes.append({"id": "backup", "nivel": "atencao", "texto": "sem cópia de segurança"})
        elif backup.get("ok") is False:
            partes.append({"id": "backup", "nivel": "critico", "texto": "cópia de segurança falhou"})
        elif (backup.get("idade_horas") or 0) > 36:
            partes.append({"id": "backup", "nivel": "critico", "texto": "cópia de segurança atrasada"})
        else:
            partes.append({"id": "backup", "nivel": "ok", "texto": "cópia de segurança em dia"})
    nivel = _pior(*(p["nivel"] for p in partes))
    return {"nivel": nivel, "partes": partes, "medido_em": agora_iso()}
