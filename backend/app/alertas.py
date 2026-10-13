"""Alertas críticos por e-mail (cartão 151). Usa as MESMAS regras de nível da tela (P1-14): nada é recalculado aqui.
Um e-mail quando o assunto entra em crítico (no máximo 1 a cada 6 h por assunto) e um quando volta ao normal (só se o crítico foi avisado).
Envio pelo email_envio (smtp.*) para avisos.email (vários endereços separados por vírgula). Cada envio fica em alerta_envio."""
from __future__ import annotations

from datetime import datetime, timedelta

from . import email_envio

ASSUNTOS = {
    "qnap": ("QNAP quase cheio", "estacoes"),
    "campvision": ("CAMP Vision parado", "estacoes"),
    "backup": ("Cópia de segurança do painel atrasada", "estacoes"),
    "site": ("Site sem resposta", "estacoes"),
    "replica": ("Cópia do acervo parada", "estacoes"),
}
LIMITE_CRITICO = timedelta(hours=6)


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else padrao) or padrao


def avaliar(con, medir_site=None, estado_backup=None) -> dict:
    """{assunto: {'critico': bool, 'texto': frase para leigo}}. Assunto sem medida (ex.: CAMP Vision que nunca mandou heartbeat) fica de fora."""
    from . import qnap_coletor as qc
    out = {}
    snap = qc.ultima(con)
    if snap and snap.get("total_gb"):
        nivel, pct = qc.nivel_espaco(con, snap["total_gb"], snap["livre_gb"])
        out["qnap"] = {"critico": nivel == "critico", "texto": f"O QNAP está com {pct}% livre ({round(snap['livre_gb'] or 0)} GB). Libere espaço ou amplie o armazenamento antes que a digitalização pare."}
    hb = con.execute("""SELECT estacao_id, CAST((julianday('now') - julianday(atualizado_em)) * 86400 AS INTEGER) AS idade
                          FROM estacao_heartbeat WHERE app LIKE 'campvision%' OR tipo_estacao='processamento' ORDER BY atualizado_em DESC LIMIT 1""").fetchone()
    erros = con.execute("SELECT COUNT(*) FROM lista_processamento WHERE etapa='erro' AND descartado_em IS NULL").fetchone()[0]
    if hb is not None or erros:
        parado = hb is not None and hb["idade"] > 3600
        partes = []
        if parado:
            partes.append(f"O CAMP Vision não dá sinal há {hb['idade'] // 3600} h {hb['idade'] % 3600 // 60} min: confira se o computador dele está ligado.")
        if erros:
            partes.append(f"{erros} lote(s) parado(s) com erro na Fila: abra a Fila para ver o motivo.")
        out["campvision"] = {"critico": bool(parado or erros), "texto": " ".join(partes) or "O CAMP Vision está funcionando.",
                             "parado": parado, "parado_h": (hb["idade"] // 3600) if parado else None, "lotes_erro": erros}
    if estado_backup is None:
        from . import backup as bk
        estado_backup = bk.estado
    b = estado_backup()
    if b.get("existe"):
        atrasado = (b.get("idade_horas") or 0) > 36
        falhou = b.get("ok") is False
        out["backup"] = {"critico": bool(atrasado or falhou), "texto": ("A última cópia de segurança do banco do painel falhou: " + (b.get("erro") or "sem detalhe") + ".") if falhou else f"A última cópia de segurança do banco do painel tem {b.get('idade_horas')} h (o limite é 36 h)."}
    from . import replica
    rp = replica.estado(con)
    if rp["configurada"]:
        out["replica"] = {"critico": rp["nivel"] == "critico", "texto": rp["texto"]}
    url = _cfg(con, "wp.url")
    if url:
        if medir_site is None:
            from .rotas_gestao import _medir_site as medir_site
        r = medir_site(url)
        out["site"] = {"critico": bool(r.get("alerta")), "texto": "O site não respondeu em duas verificações seguidas. Confira se camp.arq.br abre; se não abrir, avise a hospedagem."}
    return out


def verificar(con, agora: datetime | None = None, enviar=None, medir_site=None, estado_backup=None) -> list[dict]:
    """Compara com o estado guardado e envia o que mudou. Devolve os registros de envio desta rodada."""
    agora = agora or datetime.utcnow()
    enviar = enviar or email_envio.enviar
    destinos = [e.strip() for e in _cfg(con, "avisos.email", "rafael@camp.arq.br").split(",") if e.strip()]
    base = _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")
    smtp = email_envio.configuracao(con)
    feitos = []
    for assunto, r in avaliar(con, medir_site=medir_site, estado_backup=estado_backup).items():
        titulo_base, tela = ASSUNTOS[assunto]
        e = con.execute("SELECT * FROM alerta_estado WHERE assunto=?", (assunto,)).fetchone()
        antes = bool(e["critico"]) if e else False
        if r["critico"] == antes:
            if e:
                con.execute("UPDATE alerta_estado SET texto=?, atualizado_em=datetime('now') WHERE assunto=?", (r["texto"], assunto))
            continue
        tipo, titulo = None, None
        if r["critico"]:
            ultimo = datetime.fromisoformat(e["ultimo_critico_em"]) if e and e["ultimo_critico_em"] else None
            if ultimo and agora - ultimo < LIMITE_CRITICO:
                tipo = "suprimido"
            else:
                tipo, titulo = "critico", f"[CAMP Painel] {titulo_base}"
        elif e and e["critico_avisado"]:
            tipo, titulo = "resolvido", f"[CAMP Painel] Resolvido: {titulo_base.lower()}"
        con.execute("""INSERT INTO alerta_estado (assunto, critico, desde, texto, critico_avisado, ultimo_critico_em) VALUES (?,?,?,?,0,NULL)
                       ON CONFLICT(assunto) DO UPDATE SET critico=excluded.critico, desde=excluded.desde, texto=excluded.texto, atualizado_em=datetime('now')""",
                    (assunto, int(r["critico"]), agora.strftime("%Y-%m-%d %H:%M:%S"), r["texto"]))
        if tipo == "suprimido":
            con.execute("INSERT INTO alerta_envio (assunto, tipo, ok, erro) VALUES (?, 'suprimido', 1, 'já avisado há menos de 6 h')", (assunto,))
            feitos.append({"assunto": assunto, "tipo": "suprimido"})
            continue
        if tipo is None:
            continue
        corpo = (r["texto"] if tipo == "critico" else f"Voltou ao normal: {titulo_base.lower()}.") + f"\n\nVer no painel: {base}/#{tela}\n\n— CAMP Painel (aviso automático)"
        for para in destinos:
            ok, erro = False, None
            if not email_envio.configurado(smtp):
                erro = "SMTP não configurado (Configurações → smtp.*)"
            else:
                try:
                    res = enviar(smtp, para, titulo, corpo)
                    ok = not (isinstance(res, dict) and res.get("erro"))
                    erro = res.get("erro") if isinstance(res, dict) else None
                except Exception as ex:  # noqa: BLE001
                    erro = str(ex)[:200]
            con.execute("INSERT INTO alerta_envio (assunto, tipo, para, titulo, ok, erro) VALUES (?,?,?,?,?,?)", (assunto, tipo, para, titulo, int(ok), erro))
            feitos.append({"assunto": assunto, "tipo": tipo, "para": para, "ok": ok, "erro": erro})
        if tipo == "critico":
            con.execute("UPDATE alerta_estado SET critico_avisado=1, ultimo_critico_em=? WHERE assunto=?", (agora.isoformat(timespec="seconds"), assunto))
        else:
            con.execute("UPDATE alerta_estado SET critico_avisado=0 WHERE assunto=?", (assunto,))
    con.commit()
    return feitos


# ---------------- Sobras #12 (d): aviso de pedido de material novo ----------------
# Assunto OPCIONAL (avisos.pedido_novo = 1 liga, 0 desliga). Não é um "crítico": sai um e-mail por pedido que chega pelo site,
# para os mesmos destinatários (avisos.email), e cada envio fica em alerta_envio com assunto 'pedido' e tipo 'novo'.
FINALIDADES = {"publicacao": "publicação", "pesquisa": "pesquisa", "editorial": "editorial", "familia": "família",
               "exposicao": "exposição", "outro": "outro"}


def avisar_pedido_novo(con, sid: int, enviar=None) -> list[dict]:
    if _cfg(con, "avisos.pedido_novo", "1").strip().lower() in ("0", "nao", "não", "false"):
        return []
    s = con.execute("SELECT * FROM solicitacao WHERE id=?", (sid,)).fetchone()
    if not s:
        return []
    enviar = enviar or email_envio.enviar
    destinos = [e.strip() for e in _cfg(con, "avisos.email", "rafael@camp.arq.br").split(",") if e.strip()]
    base = _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")
    smtp = email_envio.configuracao(con)
    itens = [f"{r['codigo']} ({r['formato']})" for r in con.execute("SELECT codigo, formato FROM solicitacao_item WHERE solicitacao_id=? ORDER BY codigo", (sid,))]
    titulo = f"[CAMP Painel] Pedido de material novo: {' '.join(str(s['solicitante']).split())[:60]}"
    corpo = ("Chegou um pedido de material pelo site.\n\n"
             f"Quem pediu: {s['solicitante']}" + (f" ({s['instituicao']})" if s["instituicao"] else "") + "\n"
             f"E-mail: {s['email'] or '—'}\n"
             f"Para quê: {FINALIDADES.get(s['finalidade'], s['finalidade'])}\n"
             f"Material: {', '.join(itens) or '—'}\n"
             + (f"\nMensagem:\n{s['detalhe']}\n" if s["detalhe"] else "")
             + f"\nVer no painel: {base}/#solicitacoes\n\n— CAMP Painel (aviso automático)")
    feitos = []
    for para in destinos:
        ok, erro = False, None
        if not email_envio.configurado(smtp):
            erro = "SMTP não configurado (Configurações → smtp.*)"
        else:
            try:
                res = enviar(smtp, para, titulo, corpo, responder_para=s["email"])
                ok = not (isinstance(res, dict) and res.get("erro"))
                erro = res.get("erro") if isinstance(res, dict) else None
            except Exception as ex:  # noqa: BLE001
                erro = str(ex)[:200]
        con.execute("INSERT INTO alerta_envio (assunto, tipo, para, titulo, ok, erro) VALUES ('pedido','novo',?,?,?,?)", (para, titulo, int(ok), erro))
        feitos.append({"assunto": "pedido", "tipo": "novo", "para": para, "ok": ok, "erro": erro})
    con.commit()
    return feitos


# ---------------- resumo do dia (cartão 151): opcional, desligado por padrão ----------------
HORA_RESUMO = 18


def numeros_do_dia(con, dia: str) -> dict:
    """Os números de um dia (AAAA-MM-DD, horário do servidor), das mesmas fontes das telas: eventos de importação,
    revisão das folhas, situação no site, pedidos e problemas. Tabela/coluna ausente conta zero (nunca derruba o envio)."""
    def q(sql: str, *a) -> int:
        try:
            return int(con.execute(sql, a).fetchone()[0] or 0)
        except Exception:  # noqa: BLE001
            return 0
    no_dia = "date({},'localtime')=?"
    return {
        "importadas": q("SELECT SUM(COALESCE(json_extract(detalhe,'$.criadas'),0)) FROM evento WHERE tipo='folhas_importadas_do_lote' AND " + no_dia.format("quando"), dia),
        "revisadas": q("SELECT COUNT(*) FROM item WHERE revisao<>'pendente' AND revisado_em IS NOT NULL AND " + no_dia.format("revisado_em"), dia),
        "publicadas": q("SELECT COUNT(*) FROM item WHERE status_site='no_ar' AND " + no_dia.format("atualizado_em"), dia),
        "projetos_publicados": q("SELECT COUNT(DISTINCT codigo) FROM evento WHERE entidade='projeto' AND tipo IN ('site_publicar','site_no_ar') AND " + no_dia.format("quando"), dia),
        "pedidos_novos": q("SELECT COUNT(*) FROM solicitacao WHERE " + no_dia.format("recebida_em"), dia),
        "problemas_novos": q("SELECT COUNT(*) FROM erro WHERE " + no_dia.format("criado_em"), dia),
        "problemas_abertos": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')"),
        "problemas_bloqueiam": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'"),
    }


def texto_resumo(n: dict, dia: str, base: str) -> tuple[str, str]:
    """(assunto, corpo) em frases simples."""
    d = f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}"
    def f(v, um, varios):
        return f"{v} {um if v == 1 else varios}"
    linhas = [
        f"Resumo do painel em {d}:",
        "",
        f"- Folhas importadas do CAMP Vision: {n['importadas']}",
        f"- Folhas revisadas: {n['revisadas']}",
        f"- Folhas publicadas no site: {n['publicadas']}" + (f" ({f(n['projetos_publicados'], 'projeto', 'projetos')})" if n["projetos_publicados"] else ""),
        f"- Pedidos novos de material: {n['pedidos_novos']}",
        f"- Problemas abertos: {n['problemas_abertos']}" + (f", {n['problemas_bloqueiam']} {'impede' if n['problemas_bloqueiam'] == 1 else 'impedem'} publicar" if n["problemas_bloqueiam"] else "")
        + (f" ({f(n['problemas_novos'], 'novo hoje', 'novos hoje')})" if n["problemas_novos"] else ""),
        "",
        f"Ver no painel: {base}/#painel",
        "",
        "— CAMP Painel (resumo automático; para não receber mais, mude alertas.resumo_diario para 0 nas Configurações)",
    ]
    return f"[CAMP Painel] Resumo do dia {d}", "\n".join(linhas)


def resumo_estado(con) -> dict:
    ligado = _cfg(con, "alertas.resumo_diario", "0").strip() == "1"
    para = _cfg(con, "alertas.resumo_email").strip() or next((e.strip() for e in _cfg(con, "avisos.email").split(",") if e.strip()), "")
    try:
        ult = con.execute("SELECT dia, para, ok, erro, enviado_em FROM resumo_diario_envio ORDER BY dia DESC LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001
        ult = None
    return {"ligado": ligado, "para": para, "hora": HORA_RESUMO, "ultimo": dict(ult) if ult else None}


def resumo_diario(con, agora: datetime | None = None, enviar=None, forcar: bool = False) -> dict:
    """Manda o resumo do dia UMA vez por dia, a partir das 18h (horário do servidor). Desligado por padrão (alertas.resumo_diario=0).
    forcar=True (botão do admin) ignora o liga/desliga, o horário e o 'já enviado hoje', mas não o destinatário nem o SMTP,
    e não fica registrado como o resumo do dia."""
    import json
    agora = agora or datetime.now()
    est = resumo_estado(con)
    if not est["ligado"] and not forcar:
        return {"enviado": False, "motivo": "desligado"}
    if agora.hour < HORA_RESUMO and not forcar:
        return {"enviado": False, "motivo": "antes das 18h"}
    dia = agora.strftime("%Y-%m-%d")
    if not forcar and con.execute("SELECT 1 FROM resumo_diario_envio WHERE dia=?", (dia,)).fetchone():
        return {"enviado": False, "motivo": "já enviado hoje"}
    para = est["para"]
    n = numeros_do_dia(con, dia)
    titulo, corpo = texto_resumo(n, dia, _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/"))
    smtp = email_envio.configuracao(con)
    ok, erro = False, None
    if not para:
        erro = "Sem destinatário (Configurações → alertas.resumo_email)"
    elif not email_envio.configurado(smtp):
        erro = "SMTP não configurado (Configurações → smtp.*)"
    else:
        try:
            res = (enviar or email_envio.enviar)(smtp, para, titulo, corpo)
            ok = not (isinstance(res, dict) and res.get("erro"))
            erro = res.get("erro") if isinstance(res, dict) else None
        except Exception as ex:  # noqa: BLE001
            erro = str(ex)[:200]
    if forcar:   # envio de conferência: não conta como o resumo do dia (o das 18h continua saindo)
        return {"enviado": ok, "para": para, "erro": erro, "numeros": n, "titulo": titulo, "corpo": corpo}
    con.execute("""INSERT INTO resumo_diario_envio (dia, para, ok, erro, conteudo) VALUES (?,?,?,?,?)
                   ON CONFLICT(dia) DO UPDATE SET para=excluded.para, ok=excluded.ok, erro=excluded.erro, conteudo=excluded.conteudo, enviado_em=datetime('now')""",
                (dia, para or None, int(ok), erro, json.dumps(n, ensure_ascii=False)))
    con.commit()
    return {"enviado": ok, "para": para, "erro": erro, "numeros": n, "titulo": titulo, "corpo": corpo}
