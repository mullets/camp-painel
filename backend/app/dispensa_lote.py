"""UX-35: "Dispensar este lote" — lote parado com erro do CAMP Vision que ninguém consegue resolver.

Exemplo real: "O CAMP Vision conferiu o EXIF de só 6 de 48 arquivos" e o "Ler de novo" não reescreve o status.json (defeito conhecido
do CAMP Vision): o lote fica em 'erro' para sempre, no "Precisa de você", nas contagens e no alerta por e-mail.

- Vale para TODOS os usuários (o "Agora não" da tarefa_adiada é só de quem clicou e volta em 7 dias).
- Não apaga nada, não toca no QNAP, não muda a etapa nem o status.json: só a linha em lote_dispensado (autor, data, motivo opcional).
- Volta sozinho: a dispensa guarda a ASSINATURA do erro (etapa + desde quando está nela + mensagem do CAMP Vision). Se o CAMP Vision
  reler e a etapa ou a mensagem mudarem, a assinatura não bate mais e a dispensa deixa de valer (o lote volta a aparecer).
- Só lê o banco (nunca o QNAP).
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


def assinatura_do_lote(l) -> str:
    return assinatura(l["etapa"], l["etapa_desde"], l["status_json"], l["resultado"])


def validas(con) -> dict:
    """{lote_id: {por, em, motivo}} das dispensas que ainda valem (lote em 'erro' com a MESMA assinatura de quando foi dispensado)."""
    try:
        rows = con.execute("""SELECT d.lote_id, d.assinatura, d.por, d.em, d.motivo, l.etapa, l.etapa_desde, l.status_json, l.resultado
                                FROM lote_dispensado d JOIN lista_processamento l ON l.id=d.lote_id
                               WHERE l.descartado_em IS NULL""").fetchall()
    except sqlite3.OperationalError:          # banco sem a migração 191: nada dispensado
        return {}
    out = {}
    for r in rows:
        if r["etapa"] == "erro" and assinatura_do_lote(r) == r["assinatura"]:
            out[r["lote_id"]] = {"por": r["por"], "em": r["em"], "motivo": r["motivo"]}
    return out
