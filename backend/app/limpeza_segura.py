"""REF-041: a limpeza geral não pode declarar resolvida uma falha ainda aberta.

Somente alertas informativos, não bloqueantes e comprovadamente resolvidos pelo
estado da folha (ou aviso menor já sem ação) entram na prévia de limpeza.
"""
from __future__ import annotations


NAO_MASSIFICAR = {"duplicata", "autoria_divergente", "projeto_errado", "arquivo_corrompido", "codigo"}


def candidatos_seguros(con) -> list[dict]:
    from . import problemas
    rows = con.execute("""SELECT * FROM erro WHERE situacao IN ('aberto','em_correcao')
                           AND origem IN ('campvision','revisao')""").fetchall()
    if not rows:
        return []
    ctx = problemas.contexto(con, rows)
    seguros = []
    for e in rows:
        # Falha bloqueante nunca é encerrada por limpeza de avisos.
        if e["gravidade"] == "bloqueia" or e["categoria"] in NAO_MASSIFICAR:
            continue
        resolucao = problemas.explicar(e, ctx).get("resolvido_sozinho")
        if not resolucao or not resolucao.get("seguro") or resolucao.get("mover_para"):
            continue
        seguros.append({"id": e["id"], "codigo": e["codigo"], "categoria": e["categoria"],
                        "gravidade": e["gravidade"], "motivo": resolucao["motivo"]})
    return seguros
