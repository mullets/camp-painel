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
        out["campvision"] = {"critico": bool(parado or erros), "texto": " ".join(partes) or "O CAMP Vision está funcionando."}
    if estado_backup is None:
        from . import backup as bk
        estado_backup = bk.estado
    b = estado_backup()
    if b.get("existe"):
        atrasado = (b.get("idade_horas") or 0) > 36
        falhou = b.get("ok") is False
        out["backup"] = {"critico": bool(atrasado or falhou), "texto": ("A última cópia de segurança do banco do painel falhou: " + (b.get("erro") or "sem detalhe") + ".") if falhou else f"A última cópia de segurança do banco do painel tem {b.get('idade_horas')} h (o limite é 36 h)."}
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
