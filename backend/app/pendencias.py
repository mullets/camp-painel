"""H6b: FONTE ÚNICA dos números do Painel inicial (e dos contadores do menu). Proibido recalcular no front.
A fase de cada projeto vem de filas_fase.lote_ativo_por_projeto — a MESMA regra da Fila e do 'próximo passo' — então o número
do painel e o da Fila são iguais por construção."""
from __future__ import annotations

from .filas_fase import lote_ativo_por_projeto
from .similaridade import normalizar


def contar_pendencias(con) -> dict:
    c = {k: 0 for k in ("decisoes", "decisoes_pastas", "lotes_importar", "lotes_conferir", "folhas_conferir", "lotes_aprovar",
                         "prontos_publicar", "travados_direitos", "lotes_erro", "lotes_lendo", "publicando", "erros_bloqueantes", "pedidos_aguardando")}
    restritos = {r[0] for r in con.execute("SELECT fundo_codigo FROM direitos_fundo WHERE situacao='restrito'")}
    fundo_de = {r[0]: r[1] for r in con.execute("SELECT codigo, fundo_codigo FROM projeto WHERE mesclado_em IS NULL")}
    status = {r[0]: r[1] for r in con.execute("SELECT codigo, status_site FROM projeto")}
    for pc, d in lote_ativo_por_projeto(con).items():
        if pc not in fundo_de:                                  # projeto mesclado: não conta
            continue
        f = d["fase"]
        if f == "importar":
            c["lotes_importar"] += 1
        elif f == "conferir":
            c["lotes_conferir"] += 1; c["folhas_conferir"] += d["itens_pendentes"]
        elif f == "aprovar":
            c["lotes_aprovar"] += 1
        elif f == "publicar" and status.get(pc) != "no_ar":
            if fundo_de.get(pc) in restritos:
                c["travados_direitos"] += 1
            else:
                c["prontos_publicar"] += 1
        elif f == "erro":
            c["lotes_erro"] += 1
        elif f == "processando":
            c["lotes_lendo"] += 1
    grupos = set()
    for r in con.execute("SELECT fundo_codigo, titulo FROM decisao WHERE situacao='pendente'"):
        c["decisoes"] += 1
        grupos.add((r[0], normalizar((r[1] or "").replace("_", " "))))
    c["decisoes_pastas"] = len(grupos)
    c["publicando"] = con.execute("SELECT COUNT(*) FROM tarefa_publicacao WHERE estado='rodando'").fetchone()[0]
    c["erros_bloqueantes"] = con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'").fetchone()[0]
    c["pedidos_aguardando"] = con.execute("SELECT COUNT(*) FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento')").fetchone()[0]
    c["material_novo"] = c["lotes_importar"] + c["lotes_conferir"]                       # contador do menu (o que é de operador)
    c["esperam_admin"] = c["lotes_aprovar"] + c["prontos_publicar"]
    return c


def ritmo(con, dias: int = 14) -> dict:
    """Folhas conferidas, importadas e enviadas ao site por dia (horário de São Paulo), últimos N dias, com a média e a previsão."""
    dias = max(1, min(int(dias), 90))
    base = {r[0]: {"dia": r[0], "conferidas": 0, "importadas": 0, "publicadas": 0}
            for r in con.execute(f"WITH RECURSIVE d(n) AS (SELECT 0 UNION ALL SELECT n+1 FROM d WHERE n<{dias - 1}) SELECT date('now','-3 hours', '-' || n || ' days') FROM d")}
    for dia, n in con.execute("SELECT date(revisado_em,'-3 hours'), COUNT(*) FROM item WHERE revisado_em IS NOT NULL AND revisao IN ('conferida','corrigida') AND revisado_em >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["conferidas"] = n
    for dia, n in con.execute("SELECT date(criado_em,'-3 hours'), COUNT(*) FROM item WHERE lote_id IS NOT NULL AND criado_em >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["importadas"] = n
    for dia, n in con.execute("SELECT date(quando,'-3 hours'), COUNT(*) FROM evento WHERE tipo='site_item_criado' AND quando >= datetime('now', ?) GROUP BY 1", (f"-{dias + 1} days",)):
        if dia in base: base[dia]["publicadas"] = n
    serie = sorted(base.values(), key=lambda x: x["dia"])
    com_trabalho = [x["conferidas"] for x in serie if x["conferidas"] > 0]
    media = round(sum(com_trabalho) / len(com_trabalho), 1) if com_trabalho else 0
    falta = contar_pendencias(con)["folhas_conferir"]
    return {"dias": serie, "media_conferidas": media, "folhas_a_conferir": falta,
            "dias_para_zerar": (round(falta / media) if media else None)}
