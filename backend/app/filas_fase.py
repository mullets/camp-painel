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


def importado_sem_folhas(resultado) -> bool:
    """23/10 ("clico em Importar, dá 0 folhas importadas e o lote volta para o fim da lista"): o pacote JÁ foi importado e não trouxe
    folha nova para este lote (todas retiradas pelo CAMP Vision, ou já estavam no projeto). Importar de novo não muda nada: não é trabalho.
    Uma decisão "lote colide" ainda esperando continua pedindo gente (vai em Decidir)."""
    if isinstance(resultado, str):
        import json
        try:
            resultado = json.loads(resultado or "{}")
        except ValueError:
            return False
    imp = (resultado or {}).get("importacao") if isinstance(resultado, dict) else None
    return isinstance(imp, dict) and not imp.get("esperando_decisao")


def fase_da_lista(etapa: str, itens_total: int, itens_pendentes: int, aprovado_em: str | None, resultado=None) -> str:
    if etapa == "erro":
        return "erro"
    if etapa == "publicado":
        return "publicado"
    if etapa in ("enviado", "processando"):
        return "processando"
    if itens_total == 0:                           # revisao ou rascunho sem folhas importadas
        if etapa == "revisao" and importado_sem_folhas(resultado):
            return "publicado"                     # concluído: importado, nada novo (o projeto mostra o lote anterior, o que tem folhas)
        return "importar" if etapa == "revisao" else "publicar"
    if itens_pendentes > 0:
        return "conferir"
    return "publicar" if aprovado_em else "aprovar"


def _preferir_lote(atual: dict | None, candidato: dict) -> dict:
    """Escolhe o primeiro lote NÃO publicado, respeitando a ordem do mais novo ao mais antigo.

    Se todos estão publicados, mantém o mais recente. Sem efeitos colaterais.
    A Fila e o detalhe do projeto devem usar esta mesma política (CAMP-145).
    """
    if atual is None:
        return candidato
    if atual["fase"] == "publicado" and candidato["fase"] != "publicado":
        return candidato
    # Uma leitura nova do CV2 sem folhas não pode esconder um lote anterior
    # que JÁ tem documentos conferidos. F009-P0092: 41 folhas conferidas
    # e lote mais recente vazio resultavam em botões Importar/Aprovar inúteis.
    if (atual["fase"] in ("importar", "erro", "processando") and not atual.get("itens_total")
            and candidato["fase"] not in ("publicado", "processando", "erro")
            and candidato.get("itens_total", 0) > 0):
        return candidato
    return atual


def escolher_lote_ativo(lotes: list[dict]) -> dict | None:
    """Escolhe o lote que precisa de atenção; recebe os lotes do mais recente ao mais antigo."""
    escolhido = None
    for lote in lotes:
        escolhido = _preferir_lote(escolhido, lote)
    return escolhido


def lote_ativo_por_projeto(con) -> dict:
    """Para cada projeto com lista, a lista que ainda pede algo (a mais recente que não está publicada) ou, se todas estão publicadas, a mais recente.
    {projeto: {"fase", "itens_pendentes", "itens_total", "lote_id"}}. A MESMA regra do 'próximo passo' do projeto e da Fila."""
    por_projeto: dict = {}
    for l in con.execute("""SELECT l.id, l.projeto_codigo AS pc, l.etapa, l.aprovado_em, l.resultado,
                                   (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo) AS it,
                                   (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo AND i.revisao='pendente') AS pen
                            FROM lista_processamento l WHERE l.descartado_em IS NULL ORDER BY l.id DESC"""):
        d = {"fase": fase_da_lista(l["etapa"], l["it"], l["pen"], l["aprovado_em"], l["resultado"]), "itens_pendentes": l["pen"], "itens_total": l["it"], "lote_id": l["id"]}
        por_projeto[l["pc"]] = _preferir_lote(por_projeto.get(l["pc"]), d)
    return por_projeto
