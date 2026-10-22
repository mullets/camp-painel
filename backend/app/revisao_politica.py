"""Política de conferência do acervo: uma folha duvidosa exige olhar humano.

Não acessa QNAP, WordPress ou banco. A tela manual e a conferência automática
usam a mesma decisão para não liberar uma folha por um caminho diferente.
"""
from __future__ import annotations

import json
from collections.abc import Mapping


def motivo_para_conferir(folha: Mapping, problema_aberto: bool = False) -> str | None:
    """Retorna o primeiro motivo para revisão humana, ou None para folha limpa.

    O JSON de leitura do CAMP Vision pode ser incompleto ou corrompido: nesses
    casos nunca se interpreta a ausência de campos como ausência de avisos.
    """
    bruto = folha.get("pendencias") or "{}"
    try:
        dados = json.loads(bruto) if isinstance(bruto, str) else bruto
    except (ValueError, TypeError):
        return "pendências ilegíveis"
    if not isinstance(dados, dict):
        return "pendências ilegíveis"
    if folha.get("status_site") == "bloqueado" or dados.get("bloqueios"):
        return "bloqueada"
    if folha.get("duplicata_de"):
        return "duplicata"
    if folha.get("autoria_divergente"):
        return "autoria"
    if folha.get("espelhado") and folha.get("espelho_manual") is None:
        return "espelhada?"
    if dados.get("sinais") or dados.get("ressalvas"):
        return "aviso do CAMP Vision"
    if not str(folha.get("titulo") or "").strip():
        return "sem título"
    if problema_aberto:
        return "problema aberto"
    return None
