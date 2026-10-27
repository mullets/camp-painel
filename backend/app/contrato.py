"""Versão do contrato CAMP Vision 2 ↔ painel que ESTE painel implementa.
Fonte única do contrato: campvision-new/docs/contrato-painel.md (cópia e exemplos reais em tests/contrato/, com o commit de origem)."""
CONTRATO_PAINEL = "2.5"


def aviso_contrato(versao_cv2: str | None) -> str | None:
    """Frase para Estações quando o CV2 fala outra versão do contrato (None quando bate ou quando o CV2 não informou)."""
    if not versao_cv2 or str(versao_cv2).strip() == CONTRATO_PAINEL:
        return None
    return f"O CAMP Vision fala o contrato {str(versao_cv2).strip()}; o painel, o {CONTRATO_PAINEL}. Atualize o que estiver atrás antes de importar mais lotes."
