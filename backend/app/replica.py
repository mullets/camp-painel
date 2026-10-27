"""Cópia do acervo (cartão 149): a data da última réplica do ACERVOS_CAMP, lida da sentinela que o CAMP Vision grava em
ACERVOS_CAMP/_campvision/sentinela.json ({"gravado_em": ISO, "versao": ...}, nucleo/quarentena.py do CV2) — conforme ela aparece NA RÉPLICA.
Verde abaixo de 36 h, amarelo até 72 h, vermelho acima disso ou sem sentinela. É a ÚNICA regra (Estações e alerta por e-mail usam esta)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SENTINELA = Path("_campvision") / "sentinela.json"


def estado(con, agora: datetime | None = None) -> dict:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='replica.raiz'").fetchone()
    return estado_de((r[0] if r else "") or "", agora)


def estado_de(raiz: str, agora: datetime | None = None) -> dict:
    """A mesma regra, a partir do caminho (sem banco): a tela Máquinas a roda como sonda em segundo plano (lê arquivo no QNAP)."""
    if not raiz.strip():
        return {"configurada": False, "nivel": None, "texto": "Ainda não há réplica do acervo configurada (Configurações → replica.raiz)."}
    agora = agora or datetime.now(timezone.utc)
    try:
        dados = json.loads((Path(raiz) / SENTINELA).read_text(encoding="utf-8"))
        em = datetime.fromisoformat(dados["gravado_em"])
        if em.tzinfo is None:
            em = em.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return {"configurada": True, "raiz": raiz, "nivel": "critico", "gravado_em": None, "idade_horas": None,
                "texto": "Não encontrei a marca da última cópia na réplica do acervo (sentinela). A cópia pode ter parado: confira a réplica no QNAP."}
    horas = round((agora - em).total_seconds() / 3600, 1)
    nivel = "ok" if horas < 36 else ("aviso" if horas <= 72 else "critico")
    texto = {"ok": f"A réplica do acervo está em dia: última cópia há {horas} h.",
             "aviso": f"A réplica do acervo está atrasada: última cópia há {horas} h (o esperado é menos de 36 h).",
             "critico": f"A réplica do acervo parou: última cópia há {horas} h. O acervo está com uma cópia só; confira a réplica no QNAP."}[nivel]
    return {"configurada": True, "raiz": raiz, "nivel": nivel, "gravado_em": em.isoformat(timespec="seconds"), "idade_horas": horas, "versao": dados.get("versao"), "texto": texto}
