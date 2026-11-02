"""Protocolos (02/11/2026, CAMP: "todos os formulários seriam bons ter protocolos, e no painel ter eles para ajudar"). Contrato 1.7.

Um formato só, igual ao que a pessoa recebe do site:
- registro do site que é post (pedido de alta resolução/consulta/correção, inscrição, Avise-me): CAMP-AAAA-NNNNNN
  (ano de criação no site + id do post no site com 6 dígitos);
- cadastro de download (entrada do Fluent Forms): CAMP-AAAA-DNNNNNN (o "D" evita confundir com um id de post);
- pedido registrado só no painel: CAMP-AAAA-PNNNNNN (id do painel; entrega.protocolo).
Quando o site manda o campo "protocolo" (contrato 1.7), vale o do site; site antigo: calcula-se pela mesma regra.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

_VALIDO = re.compile(r"^CAMP-\d{4}-[DP]?\d{6,9}$")
_LER = re.compile(r"^CAMP(\d{4})([DP]?)(\d{1,9})$")


def _ano(quando) -> str:
    s = str(quando or "")[:4]
    return s if s.isdigit() else str(datetime.now(timezone.utc).year)


def formatar(site_id: int, quando=None, prefixo: str = "") -> str:
    return f"CAMP-{_ano(quando)}-{prefixo}{int(site_id):06d}"


def download(origem_id: int, quando=None) -> str:
    return formatar(origem_id, quando, "D")


def do_site(valor, site_id: int, quando=None) -> str:
    """O protocolo que o site mandou (se vier no formato certo); senão, o calculado."""
    v = str(valor or "").strip().upper()
    return v if _VALIDO.match(v) else formatar(site_id, quando)


def ler(texto) -> dict | None:
    """Reconhece um protocolo digitado (com ou sem hífens/espaços, maiúsculas ou não).
    → {"tipo": "site" | "download" | "painel", "ano": "2026", "id": 412} ou None."""
    t = re.sub(r"[^0-9A-Z]", "", str(texto or "").upper())
    m = _LER.match(t)
    if not m or not m.group(3).strip("0"):
        return None
    return {"tipo": {"": "site", "D": "download", "P": "painel"}[m.group(2)], "ano": m.group(1), "id": int(m.group(3))}
