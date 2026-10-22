"""Tipo da folha com mais de um valor (19/10/2026): uma prancha pode ser planta, corte e elevação ao mesmo tempo.

Guardado na mesma coluna `item.tipo_documento`, separado por "; " (como a autoria do projeto): "Planta; Corte; Elevação/Fachada".
Um tipo só continua igual ao que já existia (nenhuma migração de dados)."""
from __future__ import annotations

import re

SEP = "; "


def separar(valor) -> list[str]:
    """'Planta; Corte' -> ['Planta', 'Corte'] (sem vazios nem repetidos, na ordem dada)."""
    if isinstance(valor, (list, tuple)):
        partes = [str(x) for x in valor]
    else:
        partes = re.split(r"\s*;\s*", str(valor or ""))
    out: list[str] = []
    for p in partes:
        p = p.strip()
        if p and p.lower() not in {x.lower() for x in out}:
            out.append(p)
    return out


def juntar(tipos) -> str | None:
    t = separar(tipos)
    return SEP.join(t) if t else None
