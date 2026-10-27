"""UX-33: números para pessoas em pt-BR (vírgula decimal, ponto de milhar). O mesmo que fmtNum/fmtTamanho do index.html."""
from __future__ import annotations


def num_br(v, casas: int = 1) -> str:
    """1548.1 -> '1.548,1'; 30.73 (casas=1) -> '30,7'; 12 -> '12' (sem zeros à direita)."""
    if v is None:
        return "—"
    t = f"{float(v):,.{casas}f}"
    if casas:
        t = t.rstrip("0").rstrip(".")
    return t.replace(",", "\0").replace(".", ",").replace("\0", ".")


def tamanho_br(v, unidade: str, casas: int = 1) -> str:
    return f"{num_br(v, casas)} {unidade}"
