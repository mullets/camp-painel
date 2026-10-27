"""Alertas críticos por e-mail (cartão 151). Usa as MESMAS regras de nível da tela (P1-14): nada é recalculado aqui.
Um e-mail quando o assunto entra em crítico (no máximo 1 a cada 6 h por assunto) e um quando volta ao normal (só se o crítico foi avisado).
Envio pelo email_envio (smtp.*). Cada envio fica em alerta_envio.
Cartão "Notificações": cada assunto liga/desliga em 'avisos.<assunto>.ligado' e tem a sua lista de quem recebe em
'avisos.<assunto>.email' (vazia = avisos.email). Assuntos novos: lote parado na Fila (fila_travada, um aviso para a Fila),
problema que impede publicar (bloqueio, um aviso por problema) e pedido registrado à mão no painel (pedido_painel)."""
from __future__ import annotations
from .formato import num_br   # UX-33: "11.880 GB", nunca "11880 GB"

from datetime import datetime, timedelta

from . import email_envio

ASSUNTOS = {
    "qnap": ("QNAP quase cheio", "estacoes"),
    "campvision": ("CAMP Vision parado", "estacoes"),
    "backup": ("Cópia de segurança do painel atrasada", "estacoes"),
    "site": ("Site sem resposta", "estacoes"),
    "replica": ("Cópia do acervo parada", "estacoes"),
    "fila_travada": ("Lote parado na Fila", "filas"),
    "bloqueio": ("Problema que impede publicar", "erros"),
}
LIMITE_CRITICO = timedelta(hours=6)
PADRAO_EMAIL = "rafael@camp.arq.br"

# A tela de preferências (Estações → Alertas) mostra estes assuntos, nesta ordem. 'ligado' é a chave de liga/desliga.
PREFERENCIAS = [
    {"assunto": "qnap", "nome": "QNAP quase cheio", "explica": "O armazenamento das digitalizações está ficando sem espaço.", "ligado": "avisos.qnap.ligado"},
    {"assunto": "campvision", "nome": "CAMP Vision parado", "explica": "O computador do CAMP Vision parou de dar sinal ou um lote deu erro.", "ligado": "avisos.campvision.ligado"},
    {"assunto": "backup", "nome": "Cópia de segurança atrasada", "explica": "A cópia de segurança do painel tem mais de 36 h ou falhou.", "ligado": "avisos.backup.ligado"},
    {"assunto": "site", "nome": "Site sem resposta", "explica": "O site não respondeu em duas verificações seguidas.", "ligado": "avisos.site.ligado"},
    {"assunto": "replica", "nome": "Cópia do acervo parada", "explica": "A cópia das digitalizações em outro disco parou.", "ligado": "avisos.replica.ligado"},
    {"assunto": "fila_travada", "nome": "Lote parado na Fila", "explica": "Um lote ficou na mesma etapa da Fila por mais tempo que o limite.", "ligado": "avisos.fila_travada.ligado"},
    {"assunto": "bloqueio", "nome": "Problema que impede publicar", "explica": "Foi aberto um problema grave (um e-mail para cada problema).", "ligado": "avisos.bloqueio.ligado"},
    {"assunto": "pedido", "nome": "Pedido de material pelo site", "explica": "Alguém pediu material pelo formulário do site.", "ligado": "avisos.pedido_novo"},
    {"assunto": "pedido_painel", "nome": "Pedido de material registrado no painel", "explica": "Alguém da equipe registrou um pedido à mão no painel.", "ligado": "avisos.pedido_painel.ligado"},
]
CHAVE_LIGADO = {p["assunto"]: p["ligado"] for p in PREFERENCIAS}
# O problema que impede publicar é resolvido por alguém no próprio painel: não sai um segundo e-mail de "resolvido".
SEM_RESOLVIDO = {"bloqueio"}
ETAPA_TXT = {"enviado": "esperando o CAMP Vision começar", "processando": "sendo lido pelo CAMP Vision", "revisao": "esperando a revisão das folhas"}


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else padrao) or padrao


def ligado(con, assunto: str) -> bool:
    """Desligado só quando a chave diz 0/não. Assunto sem chave fica ligado."""
    chave = CHAVE_LIGADO.get(assunto)
    return not chave or _cfg(con, chave, "1").strip().lower() not in ("0", "nao", "não", "false")


def lista_emails(texto: str) -> list[str]:
    return [e.strip() for e in (texto or "").replace(";", ",").split(",") if e.strip()]


def destinatarios(con, assunto: str) -> list[str]:
    """Quem recebe este assunto: a lista do assunto (avisos.<assunto>.email) ou, se vazia, avisos.email."""
    return lista_emails(_cfg(con, f"avisos.{assunto}.email")) or lista_emails(_cfg(con, "avisos.email", PADRAO_EMAIL))


def _minusc(t: str) -> str:
    """'Lote parado' -> 'lote parado', mas sigla fica: 'QNAP quase cheio', 'CAMP Vision parado'."""
    return t if not t or (len(t) > 1 and t[1].isupper()) else t[0].lower() + t[1:]


def horas_fila(con) -> int:
    try:
        h = int(_cfg(con, "avisos.fila_travada.horas", "24"))
    except ValueError:
        h = 24
    return h if h > 0 else 24


def _mandar(con, smtp, enviar, destinos, assunto, tipo, titulo, corpo, chave=None, responder_para=None) -> list[dict]:
    """Um e-mail por destinatário; cada tentativa fica em alerta_envio (com a chave do aviso)."""
    feitos = []
    for para in destinos:
        ok, erro = False, None
        if not email_envio.configurado(smtp):
            erro = "SMTP não configurado (Configurações → E-mail e avisos)"
        else:
            try:
                res = enviar(smtp, para, titulo, corpo, responder_para=responder_para) if responder_para else enviar(smtp, para, titulo, corpo)
                ok = not (isinstance(res, dict) and res.get("erro"))
                erro = res.get("erro") if isinstance(res, dict) else None
            except Exception as ex:  # noqa: BLE001
                erro = str(ex)[:200]
        con.execute("INSERT INTO alerta_envio (assunto, tipo, para, titulo, ok, erro, chave) VALUES (?,?,?,?,?,?,?)", (assunto, tipo, para, titulo, int(ok), erro, chave))
        feitos.append({"assunto": assunto, "tipo": tipo, "para": para, "ok": ok, "erro": erro, **({"chave": chave} if chave and chave != assunto else {})})
    return feitos


NIVEIS = ("ok", "atencao", "critico", "nao_medido")


def _nao_medido(motivo: str) -> dict:
    """UX-07: "não medido" só quando a medição falha, e sempre com o porquê."""
    return {"critico": False, "nivel": "nao_medido", "motivo": motivo, "texto": f"Não medido: {motivo}."}


def _medir_site_igual_tela(url: str) -> dict:
    """A MESMA sonda da tela Máquinas (rotas_gestao._sonda, fresca): o que o alerta mede vira a medição que a tela mostra."""
    from .rotas_gestao import _medir_site, _sonda, _valor_sonda
    return _valor_sonda(_sonda(("http", url), lambda: _medir_site(url), True), None)   # UX-12: _sonda devolve a medição em curso; aqui esperamos por ela


def avaliar(con, medir_site=None, estado_backup=None) -> dict:
    """{assunto: {'critico': bool, 'nivel': ok|atencao|critico|nao_medido, 'texto': frase para leigo, 'motivo'?}}.
    UX-07: os assuntos de máquina estão SEMPRE aqui, ligados às mesmas medições da tela (coleta do QNAP, sonda do site, sentinela da
    réplica, heartbeat do CAMP Vision, backup). 'nao_medido' só quando a medição falhou ou não existe, com o motivo.
    QNAP: a regra única de qnap_coletor.nivel_espaco (< 15% livre = atenção). Site: lento (> 3 s) ou uma falha = atenção, sem
    resposta em duas verificações seguidas = crítico. Só 'critico' manda e-mail (atenção aparece na tela e no topo)."""
    from . import qnap_coletor as qc
    out = {}
    snap = qc.ultima(con)
    if not snap:
        out["qnap"] = _nao_medido("o painel ainda não leu o QNAP (a leitura roda sozinha a cada poucos minutos)")
    elif snap.get("erro"):
        out["qnap"] = _nao_medido(f"a última leitura do QNAP falhou ({snap['erro']})")
    elif not snap.get("total_gb"):
        out["qnap"] = _nao_medido("o QNAP não está conectado a este servidor" if not snap.get("montado") else "a última leitura do QNAP não trouxe o espaço livre")
    else:
        nivel, pct = qc.nivel_espaco(con, snap["total_gb"], snap["livre_gb"])
        _, dias = qc._tendencia(con, snap["livre_gb"])
        enche = f" No ritmo desta semana, enche em cerca de {dias} {'dia' if dias == 1 else 'dias'}." if dias else ""
        d_av, d_cr = qc._num(con, "qnap.dias_aviso", 30), qc._num(con, "qnap.dias_critico", 10)
        if dias is not None and dias < d_av:              # UX-02: o alerta também vale por dias até encher (< 30 atenção, < 10 crítico)
            enche += f" Menos de {d_av:g} dias para encher já é atenção; menos de {d_cr:g}, crítico."
        n_ = {"ok": "ok", "aviso": "atencao", "critico": "critico"}[nivel]
        base = f"O QNAP está com {('%g' % pct).replace('.', ',')}% livre ({num_br(round(snap['livre_gb'] or 0), 0)} GB).{enche}"
        out["qnap"] = {"critico": nivel == "critico", "nivel": n_, "livre_pct": pct, "dias_ate_encher": dias, "medido_em": snap.get("coletado_em"),
                       "texto": base + (" Libere espaço ou amplie o armazenamento antes que a digitalização pare." if n_ != "ok" else "")}
    hb = con.execute("""SELECT estacao_id, CAST((julianday('now') - julianday(atualizado_em)) * 86400 AS INTEGER) AS idade
                          FROM estacao_heartbeat WHERE app LIKE 'campvision%' OR tipo_estacao='processamento' ORDER BY atualizado_em DESC LIMIT 1""").fetchone()
    erros = con.execute("SELECT COUNT(*) FROM lista_processamento WHERE etapa='erro' AND descartado_em IS NULL").fetchone()[0]
    from .dispensa_lote import validas                 # UX-35: lote com erro dispensado não pede e-mail (volta sozinho se o erro mudar)
    erros -= len(validas(con))
    if hb is not None or erros:
        parado = hb is not None and hb["idade"] > 3600
        partes = []
        if parado:
            partes.append(f"O CAMP Vision não dá sinal há {hb['idade'] // 3600} h {hb['idade'] % 3600 // 60} min: confira se o computador dele está ligado.")
        if erros:
            partes.append(f"{erros} lote(s) parado(s) com erro na Fila: abra a Fila para ver o motivo.")
        out["campvision"] = {"critico": bool(parado or erros), "nivel": "critico" if (parado or erros) else "ok", "texto": " ".join(partes) or "O CAMP Vision está funcionando.",
                             "parado": parado, "parado_h": (hb["idade"] // 3600) if parado else None, "lotes_erro": erros}
    else:
        out["campvision"] = _nao_medido("o CAMP Vision ainda não deu sinal ao painel")
    if estado_backup is None:
        from . import backup as bk
        estado_backup = bk.estado
    try:
        b = estado_backup()
    except Exception as e:  # noqa: BLE001
        b = {"erro_leitura": str(e)[:160]}
    if b.get("erro_leitura"):
        out["backup"] = _nao_medido(f"não consegui ler a pasta das cópias ({b['erro_leitura']})")
    elif b.get("existe"):
        atrasado = (b.get("idade_horas") or 0) > 36
        falhou = b.get("ok") is False
        out["backup"] = {"critico": bool(atrasado or falhou), "nivel": "critico" if (atrasado or falhou) else "ok",
                         "texto": ("A última cópia de segurança do banco do painel falhou: " + (b.get("erro") or "sem detalhe") + ".") if falhou else f"A última cópia de segurança do banco do painel tem {b.get('idade_horas')} h (o limite é 36 h)."}
    else:
        out["backup"] = {"critico": False, "nivel": "atencao", "texto": "Ainda não há cópia de segurança do banco do painel: peça a um admin \"Fazer backup agora\" em Máquinas."}
    from . import replica
    rp = replica.estado(con)
    if rp["configurada"]:
        out["replica"] = {"critico": rp["nivel"] == "critico", "nivel": {"ok": "ok", "aviso": "atencao"}.get(rp["nivel"], "critico"), "texto": rp["texto"]}
    else:
        out["replica"] = _nao_medido("a cópia do acervo ainda não tem destino configurado (Configurações → replica.raiz)")
    url = _cfg(con, "wp.url")
    if not url:
        out["site"] = _nao_medido("o endereço do site não está configurado (Configurações → wp.url)")
    else:
        try:
            r = (medir_site or _medir_site_igual_tela)(url) or {}
        except Exception as e:  # noqa: BLE001
            r = {"falha_medicao": str(e)[:160]}
        from .contagens import nivel_site
        if r.get("nao_medido"):
            out["site"] = _nao_medido(r["nao_medido"])
        elif r.get("falha_medicao") or not r.get("estado"):
            out["site"] = _nao_medido(f"a verificação do site não rodou ({r.get('falha_medicao') or 'sem resposta da sonda'})")
        else:
            n_, _ = nivel_site(r)
            seg = f"{r['ms'] / 1000:.1f}".replace(".", ",") + " s" if r.get("ms") is not None else None
            texto = {"critico": "O site não respondeu em duas verificações seguidas. Confira se camp.arq.br abre; se não abrir, avise a hospedagem.",
                     "atencao": (f"O site está lento: respondeu em {seg} (o normal é menos de 3 s)." if r.get("estado") == "lento"
                                 else "O site não respondeu uma vez; só vira crítico se a próxima verificação também falhar."),
                     "ok": f"O site está respondendo{' em ' + seg if seg else ''}."}[n_]
            out["site"] = {"critico": n_ == "critico", "nivel": n_, "texto": texto, "ms": r.get("ms"), "medido_em": r.get("medido_em")}
    return out


def avaliar_extras(con, agora: datetime | None = None) -> dict:
    """Os assuntos do cartão "Notificações" que seguem a mesma regra de crítico/normal:
    - 'fila_travada': algum lote está na mesma etapa (enviado, processando, revisão) há mais que avisos.fila_travada.horas;
    - 'bloqueio:<id>': cada problema aberto que impede publicar (gravidade 'bloqueia') é um aviso próprio.
    Assunto desligado fica de fora (e não mexe no estado guardado). Devolve {chave: {'assunto', 'critico', 'texto', ...}}."""
    agora = agora or datetime.utcnow()
    out = {}
    if ligado(con, "fila_travada"):
        horas = horas_fila(con)
        limite = (agora - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
        lotes = con.execute("""SELECT id, nome, projeto_codigo, etapa, COALESCE(etapa_desde, criado_em) AS desde
                                 FROM lista_processamento
                                WHERE descartado_em IS NULL AND etapa IN ('enviado','processando','revisao')
                                  AND COALESCE(etapa_desde, criado_em) < ? ORDER BY desde""", (limite,)).fetchall()
        from .dispensa_lote import validas            # UX-35: o lote dispensado não entra no aviso (hoje a etapa 'erro' já fica de fora)
        disp = validas(con)
        lotes = [l for l in lotes if l["id"] not in disp]
        partes = []
        from .pendencias import projetos_lendo_agora, LEITURA_SEM_SINAL_H
        lendo, sem_projeto = projetos_lendo_agora(con)
        for l in lotes[:10]:
            try:
                h = int((agora - datetime.fromisoformat(l["desde"])).total_seconds() // 3600)
            except (TypeError, ValueError):
                h = horas
            etapa_txt = ETAPA_TXT.get(l["etapa"], l["etapa"])
            if l["etapa"] == "processando" and h > LEITURA_SEM_SINAL_H and str(l["projeto_codigo"] or "").upper() not in lendo and not sem_projeto:
                etapa_txt = "leitura interrompida (o CAMP Vision não dá sinal deste lote; use Ler de novo na Fila)"   # UX-09: "sendo lido há 177 h" não existe
            partes.append(f"- {l['nome']} ({l['projeto_codigo']}): {etapa_txt} há {h} h")
        if len(lotes) > 10:
            partes.append(f"- e mais {len(lotes) - 10} lote(s)")
        texto = (f"{len(lotes)} lote(s) parado(s) na mesma etapa da Fila há mais de {horas} h:\n" + "\n".join(partes)
                 + "\n\nAbra a Fila e veja o que falta: se o CAMP Vision está ligado, ou se o lote espera alguém revisar.") if lotes else f"Nenhum lote parado há mais de {horas} h na Fila."
        out["fila_travada"] = {"assunto": "fila_travada", "critico": bool(lotes), "texto": texto, "lotes": [l["id"] for l in lotes]}
    if ligado(con, "bloqueio"):
        abertos = con.execute("""SELECT id, codigo, categoria, descricao, origem, relatado_por FROM erro
                                  WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia' ORDER BY id""").fetchall()
        for p in abertos:
            out[f"bloqueio:{p['id']}"] = {
                "assunto": "bloqueio", "critico": True, "titulo_base": f"Problema que impede publicar em {p['codigo']}",
                "texto": (f"Foi aberto um problema que impede publicar {p['codigo']}:\n\n{p['descricao']}\n\n"
                          + (f"Quem avisou: {p['relatado_por']}\n" if p["relatado_por"] else "")
                          + "Enquanto ele estiver aberto, esse material não pode ser publicado. Abra Problemas para corrigir ou fechar."),
                "tela": "erros"}
        # problema que deixou de estar aberto (corrigido, fechado, ignorado ou mudou de gravidade): volta ao normal
        vistos = set(out)
        for e in con.execute("SELECT assunto FROM alerta_estado WHERE assunto LIKE 'bloqueio:%' AND critico=1").fetchall():
            if e["assunto"] not in vistos:
                out[e["assunto"]] = {"assunto": "bloqueio", "critico": False, "texto": "O problema não está mais aberto."}
    return out


def verificar(con, agora: datetime | None = None, enviar=None, medir_site=None, estado_backup=None) -> list[dict]:
    """Compara com o estado guardado e envia o que mudou. Devolve os registros de envio desta rodada.
    Mesma regra para todos: um e-mail quando entra em crítico (no máximo 1 a cada 6 h por chave), um quando volta ao normal
    (só se o crítico foi avisado). Assunto desligado não é avaliado nem envia."""
    agora = agora or datetime.utcnow()
    enviar = enviar or email_envio.enviar
    base = _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")
    smtp = email_envio.configuracao(con)
    feitos = []
    rodada = {k: {**v, "assunto": k} for k, v in avaliar(con, medir_site=medir_site, estado_backup=estado_backup).items() if ligado(con, k)}
    rodada.update(avaliar_extras(con, agora))
    for chave, r in rodada.items():
        assunto = r["assunto"]
        titulo_base = r.get("titulo_base") or ASSUNTOS[assunto][0]
        tela = r.get("tela") or ASSUNTOS[assunto][1]
        e = con.execute("SELECT * FROM alerta_estado WHERE assunto=?", (chave,)).fetchone()
        antes = bool(e["critico"]) if e else False
        nivel = r.get("nivel") or ("critico" if r["critico"] else "ok")
        if nivel == "nao_medido":                       # UX-07: a medição falhou: guarda o porquê, sem e-mail e sem "resolvido"
            con.execute("""INSERT INTO alerta_estado (assunto, critico, desde, texto, critico_avisado, nivel, motivo) VALUES (?,0,?,?,0,'nao_medido',?)
                           ON CONFLICT(assunto) DO UPDATE SET texto=excluded.texto, nivel='nao_medido', motivo=excluded.motivo, atualizado_em=datetime('now')""",
                        (chave, agora.strftime("%Y-%m-%d %H:%M:%S"), r["texto"], r.get("motivo")))
            continue
        if r["critico"] == antes:
            con.execute("""INSERT INTO alerta_estado (assunto, critico, desde, texto, critico_avisado, nivel, motivo) VALUES (?,?,?,?,0,?,NULL)
                           ON CONFLICT(assunto) DO UPDATE SET texto=excluded.texto, nivel=excluded.nivel, motivo=NULL, atualizado_em=datetime('now')""",
                        (chave, int(r["critico"]), agora.strftime("%Y-%m-%d %H:%M:%S"), r["texto"], nivel))   # UX-07: antes, sem linha = "ainda não medido" para sempre
            continue
        tipo, titulo = None, None
        if r["critico"]:
            ultimo = datetime.fromisoformat(e["ultimo_critico_em"]) if e and e["ultimo_critico_em"] else None
            if ultimo and agora - ultimo < LIMITE_CRITICO:
                tipo = "suprimido"
            else:
                tipo, titulo = "critico", f"[CAMP Painel] {titulo_base}"
        elif e and e["critico_avisado"] and assunto not in SEM_RESOLVIDO:
            tipo, titulo = "resolvido", f"[CAMP Painel] Resolvido: {_minusc(titulo_base)}"
        con.execute("""INSERT INTO alerta_estado (assunto, critico, desde, texto, critico_avisado, ultimo_critico_em, nivel, motivo) VALUES (?,?,?,?,0,NULL,?,NULL)
                       ON CONFLICT(assunto) DO UPDATE SET critico=excluded.critico, desde=excluded.desde, texto=excluded.texto, nivel=excluded.nivel, motivo=NULL, atualizado_em=datetime('now')""",
                    (chave, int(r["critico"]), agora.strftime("%Y-%m-%d %H:%M:%S"), r["texto"], nivel))
        if tipo == "suprimido":
            con.execute("INSERT INTO alerta_envio (assunto, tipo, ok, erro, chave) VALUES (?, 'suprimido', 1, 'já avisado há menos de 6 h', ?)", (assunto, chave))
            feitos.append({"assunto": assunto, "tipo": "suprimido", **({"chave": chave} if chave != assunto else {})})
            continue
        if tipo is None:
            if not r["critico"]:
                con.execute("UPDATE alerta_estado SET critico_avisado=0 WHERE assunto=?", (chave,))
            continue
        corpo = (r["texto"] if tipo == "critico" else f"Voltou ao normal: {_minusc(titulo_base)}.") + f"\n\nVer no painel: {base}/#{tela}\n\n— CAMP Painel (aviso automático)"
        feitos += _mandar(con, smtp, enviar, destinatarios(con, assunto), assunto, tipo, titulo, corpo, chave=chave)
        if tipo == "critico":
            con.execute("UPDATE alerta_estado SET critico_avisado=1, ultimo_critico_em=? WHERE assunto=?", (agora.isoformat(timespec="seconds"), chave))
        else:
            con.execute("UPDATE alerta_estado SET critico_avisado=0 WHERE assunto=?", (chave,))
    con.commit()
    return feitos


# ---------------- Sobras #12 (d): aviso de pedido de material novo ----------------
# Não é um "crítico": sai um e-mail por pedido, e cada envio fica em alerta_envio com tipo 'novo' e chave 'pedido:<id>'
# (a chave impede mandar o mesmo pedido duas vezes). Pedido do site: assunto 'pedido' (liga/desliga em avisos.pedido_novo).
# Pedido registrado à mão no painel: assunto 'pedido_painel' (avisos.pedido_painel.ligado).
FINALIDADES = {"publicacao": "publicação", "pesquisa": "pesquisa", "editorial": "editorial", "familia": "família",
               "exposicao": "exposição", "outro": "outro"}


def avisar_pedido_novo(con, sid: int, enviar=None, registrado_por: str | None = None) -> list[dict]:
    """registrado_por = e-mail de quem registrou no painel (pedido feito à mão); vazio = pedido que chegou pelo site."""
    assunto = "pedido_painel" if registrado_por else "pedido"
    if not ligado(con, assunto):
        return []
    s = con.execute("SELECT * FROM solicitacao WHERE id=?", (sid,)).fetchone()
    if not s:
        return []
    chave = f"pedido:{sid}"
    if con.execute("SELECT 1 FROM alerta_envio WHERE chave=? AND tipo='novo' LIMIT 1", (chave,)).fetchone():
        return []                                     # já avisado: não repete
    enviar = enviar or email_envio.enviar
    base = _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")
    smtp = email_envio.configuracao(con)
    itens = [f"{r['codigo']} ({r['formato']})" for r in con.execute("SELECT codigo, formato FROM solicitacao_item WHERE solicitacao_id=? ORDER BY codigo", (sid,))]
    quem = " ".join(str(s["solicitante"]).split())[:60]
    if registrado_por:
        titulo = f"[CAMP Painel] Pedido de material registrado no painel: {quem}"
        abertura = f"Um pedido de material foi registrado no painel por {registrado_por}.\n\n"
    else:
        titulo = f"[CAMP Painel] Pedido de material novo: {quem}"
        abertura = "Chegou um pedido de material pelo site.\n\n"
    corpo = (abertura +
             f"Quem pediu: {s['solicitante']}" + (f" ({s['instituicao']})" if s["instituicao"] else "") + "\n"
             f"E-mail: {s['email'] or '—'}\n"
             f"Para quê: {FINALIDADES.get(s['finalidade'], s['finalidade'])}\n"
             f"Material: {', '.join(itens) or '—'}\n"
             + (f"\nMensagem:\n{s['detalhe']}\n" if s["detalhe"] else "")
             + f"\nVer no painel: {base}/#solicitacoes\n\n— CAMP Painel (aviso automático)")
    feitos = _mandar(con, smtp, enviar, destinatarios(con, assunto), assunto, "novo", titulo, corpo, chave=chave,
                     responder_para=s["email"] if email_envio.ENDERECO.match(s["email"] or "") else None)
    con.commit()
    return feitos


# ---------------- preferências: quem recebe o quê (tela Estações → Alertas) ----------------
def preferencias(con) -> dict:
    geral = lista_emails(_cfg(con, "avisos.email", PADRAO_EMAIL))
    out = []
    for p in PREFERENCIAS:
        proprio = lista_emails(_cfg(con, f"avisos.{p['assunto']}.email"))
        out.append({"assunto": p["assunto"], "nome": p["nome"], "explica": p["explica"], "ligado": ligado(con, p["assunto"]),
                    "emails": proprio, "recebem": proprio or geral, "usa_geral": not proprio})
    return {"assuntos": out, "geral": geral, "fila_horas": horas_fila(con)}


def salvar_preferencias(con, dados: dict, ator: str) -> dict:
    """dados = {'geral': [..]?, 'fila_horas': int?, 'assuntos': [{'assunto', 'ligado', 'emails': [..]}]}. Valida tudo antes de gravar.
    Levanta ValueError com a frase para a tela."""
    import json
    mud: dict[str, str] = {}

    def emails(v, onde: str) -> str:
        lst = lista_emails(",".join(v) if isinstance(v, list) else str(v or ""))
        ruins = [x for x in lst if not email_envio.ENDERECO.match(x)]
        if ruins:
            raise ValueError(f"{onde}: o endereço '{ruins[0]}' não parece um e-mail.")
        return ", ".join(dict.fromkeys(lst))
    if "geral" in dados:
        g = emails(dados["geral"], "Quem recebe quando o assunto não tem lista própria")
        if not g:
            raise ValueError("Deixe pelo menos um e-mail em 'Quem recebe quando o assunto não tem lista própria'.")
        mud["avisos.email"] = g
    if "fila_horas" in dados:
        try:
            h = int(dados["fila_horas"])
        except (TypeError, ValueError):
            h = 0
        if not 1 <= h <= 24 * 30:
            raise ValueError("O limite da Fila parada tem que ser um número de horas entre 1 e 720.")
        mud["avisos.fila_travada.horas"] = str(h)
    nomes = {p["assunto"]: p for p in PREFERENCIAS}
    for a in dados.get("assuntos") or []:
        p = nomes.get(str(a.get("assunto")))
        if not p:
            raise ValueError(f"Assunto desconhecido: {a.get('assunto')}")
        if "ligado" in a:
            mud[p["ligado"]] = "1" if a["ligado"] else "0"
        if "emails" in a:
            mud[f"avisos.{p['assunto']}.email"] = emails(a["emails"], p["nome"])
    # UX-24: o resumo do dia vira um interruptor com rótulo na aba Alertas (antes a tela mandava "mudar alertas.resumo_diario para 1").
    if isinstance(dados.get("resumo"), dict):
        rz = dados["resumo"]
        if "ligado" in rz:
            mud["alertas.resumo_diario"] = "1" if rz["ligado"] else "0"
        if "email" in rz:
            e_ = emails(rz["email"], "Quem recebe o resumo do dia")
            if "," in e_:
                raise ValueError("Quem recebe o resumo do dia: escreva um e-mail só (vazio: o primeiro da lista geral).")
            mud["alertas.resumo_email"] = e_
    for chave, valor in mud.items():
        atual = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
        if atual is None:
            con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES (?,?,?,0)", (chave, valor, "Aviso por e-mail (tela Estações → Alertas)"))
        elif (atual[0] or "") == valor:
            continue
        else:
            con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (valor, ator, chave))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config',?,'alterada',?,?)",
                    (chave, ator, json.dumps({"antes": {"valor": atual[0] if atual else None}, "depois": {"valor": valor}}, ensure_ascii=False)))
    con.commit()
    return preferencias(con)


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
        "— CAMP Painel (resumo automático; para não receber mais, desligue o Resumo do dia em Máquinas → Alertas)",
    ]
    return f"[CAMP Painel] Resumo do dia {d}", "\n".join(linhas)


def resumo_estado(con) -> dict:
    ligado = _cfg(con, "alertas.resumo_diario", "0").strip() == "1"
    para = _cfg(con, "alertas.resumo_email").strip() or next((e.strip() for e in _cfg(con, "avisos.email").split(",") if e.strip()), "")
    try:
        ult = con.execute("SELECT dia, para, ok, erro, enviado_em FROM resumo_diario_envio ORDER BY dia DESC LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001
        ult = None
    return {"ligado": ligado, "para": para, "email": _cfg(con, "alertas.resumo_email").strip(), "hora": HORA_RESUMO, "ultimo": dict(ult) if ult else None}


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
        erro = "Sem destinatário: escolha quem recebe em Máquinas → Alertas → Resumo do dia"
    elif not email_envio.configurado(smtp):
        erro = "SMTP não configurado (Configurações → E-mail e avisos)"
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
