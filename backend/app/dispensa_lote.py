"""UX-35: "Dispensar este lote" — lote parado com erro do CAMP Vision que ninguém consegue resolver.

Exemplo real: "O CAMP Vision conferiu o EXIF de só 6 de 48 arquivos" e o "Ler de novo" não reescreve o status.json (defeito conhecido
do CAMP Vision): o lote fica em 'erro' para sempre, no "Precisa de você", nas contagens e no alerta por e-mail.

- Vale para TODOS os usuários (o "Agora não" da tarefa_adiada é só de quem clicou e volta em 7 dias).
- Não apaga nada, não toca no QNAP, não muda a etapa nem o status.json: só a linha em lote_dispensado (autor, data, motivo opcional).
- Volta sozinho: a dispensa guarda a ASSINATURA do erro (etapa + desde quando está nela + mensagem do CAMP Vision). Se o CAMP Vision
  reler e a etapa ou a mensagem mudarem, a assinatura não bate mais e a dispensa deixa de valer (o lote volta a aparecer).
- Só lê o banco (nunca o QNAP).

UX-39: também o lote em "Leitura interrompida" (UX-09: etapa 'processando' há mais de 2 h sem sinal do CAMP Vision deste projeto), que
o "Ler de novo" não destrava quando o defeito é do CAMP Vision. A assinatura é etapa + etapa_desde + "leitura_interrompida": se o CAMP
Vision reescrever o status (o lote sai de 'processando' ou etapa_desde muda), a dispensa deixa de valer. Enquanto o CAMP Vision disser que
está lendo o projeto, o lote não está interrompido e a dispensa não se aplica (ele aparece como "sendo lido").
"""
from __future__ import annotations

import hashlib
import json
import sqlite3


def _mensagem_cv(status_json, resultado) -> str:
    from .rotas_operacao import _erro_cv_bruto
    t, _ = _erro_cv_bruto({"status_json": status_json, "resultado": resultado})
    return " ".join((t or "").split())


def assinatura(etapa, etapa_desde, status_json, resultado) -> str:
    base = json.dumps([etapa or "", etapa_desde or "", _mensagem_cv(status_json, resultado)], ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


LEITURA_INTERROMPIDA = "leitura_interrompida"


def assinatura_do_lote(l) -> str:
    if l["etapa"] == "processando":            # UX-39: a "mensagem" da leitura interrompida é o próprio estado
        base = json.dumps([l["etapa"], l["etapa_desde"] or "", LEITURA_INTERROMPIDA], ensure_ascii=False)
        return hashlib.sha1(base.encode("utf-8")).hexdigest()
    return assinatura(l["etapa"], l["etapa_desde"], l["status_json"], l["resultado"])


def estado_dispensavel(l, lendo=None, con=None) -> str | None:
    """'erro' (UX-35), 'leitura_interrompida' (UX-39) ou None (o lote não pode ser dispensado agora)."""
    if l["etapa"] == "erro":
        return "erro"
    if l["etapa"] == "processando":
        from .pendencias import marcar_parado, projetos_lendo_agora
        if lendo is None:
            lendo = projetos_lendo_agora(con)
        d = {"etapa": l["etapa"], "etapa_desde": l["etapa_desde"], "criado_em": l["criado_em"], "projeto_codigo": l["projeto_codigo"]}
        if marcar_parado(d, lendo)["leitura_interrompida"]:
            return LEITURA_INTERROMPIDA
    return None


def validas(con) -> dict:
    """{lote_id: {por, em, motivo, estado}} das dispensas que ainda valem: lote em 'erro' (UX-35) ou em leitura interrompida (UX-39)
    com a MESMA assinatura de quando foi dispensado."""
    try:
        rows = con.execute("""SELECT d.lote_id, d.assinatura, d.por, d.em, d.motivo, l.etapa, l.etapa_desde, l.status_json, l.resultado,
                                     l.criado_em, l.projeto_codigo
                                FROM lote_dispensado d JOIN lista_processamento l ON l.id=d.lote_id
                               WHERE l.descartado_em IS NULL""").fetchall()
    except sqlite3.OperationalError:          # banco sem a migração 191: nada dispensado
        return {}
    out, lendo = {}, None
    for r in rows:
        if r["etapa"] == "processando" and lendo is None:
            from .pendencias import projetos_lendo_agora
            lendo = projetos_lendo_agora(con)
        est = estado_dispensavel(r, lendo)
        if est and assinatura_do_lote(r) == r["assinatura"]:
            out[r["lote_id"]] = {"por": r["por"], "em": r["em"], "motivo": r["motivo"], "estado": est}
    return out
