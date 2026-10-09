"""Em que PONTO do trabalho está cada lista da Fila de processamento: o que falta e quem precisa agir.

A etapa guardada (enviado, processando, revisao, rascunho, publicado, erro) é o rótulo do CAMP Vision/painel; a FASE responde "o que eu faço agora?":
  processando  o CAMP Vision ainda está lendo (enviado ou processando)             -> nada a fazer
  importar     o CAMP Vision terminou e as folhas ainda não vieram para o painel      -> Importar folhas
  conferir     há folhas importadas ainda não conferidas                            -> Conferir
  aprovar      todas conferidas, o lote ainda não foi aprovado                      -> Aprovar o lote (admin)
  publicar     lote aprovado (ou legado em rascunho) e o projeto ainda não publicado -> Publicar (admin)
  publicado    concluído
  erro         o CAMP Vision parou com erro                                          -> Ver o erro / tentar de novo
"""
from __future__ import annotations

FASES = ("erro", "importar", "conferir", "aprovar", "publicar", "processando", "publicado")
PRECISAM_DE_GENTE = ("erro", "importar", "conferir", "aprovar", "publicar")


def fase_da_lista(etapa: str, itens_total: int, itens_pendentes: int, aprovado_em: str | None) -> str:
    if etapa == "erro":
        return "erro"
    if etapa == "publicado":
        return "publicado"
    if etapa in ("enviado", "processando"):
        return "processando"
    if itens_total == 0:                           # revisao ou rascunho sem folhas importadas
        return "importar" if etapa == "revisao" else "publicar"
    if itens_pendentes > 0:
        return "conferir"
    return "publicar" if aprovado_em else "aprovar"
