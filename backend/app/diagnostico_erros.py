"""REF-041: retrato não destrutivo da fila de problemas.

Não altera banco, não usa QNAP e não reclassifica um alerta importante como
resolvido. Destina-se a investigar bases que acumulam centenas de alertas.
"""
from __future__ import annotations


def diagnosticar(con, limite: int = 15) -> dict:
    where = "situacao IN ('aberto','em_correcao')"
    total = con.execute(f"SELECT COUNT(*) FROM erro WHERE {where}").fetchone()[0]
    linhas = con.execute(f"""SELECT origem, gravidade, categoria, COUNT(*) AS quantidade
                              FROM erro WHERE {where}
                             GROUP BY origem, gravidade, categoria
                             ORDER BY quantidade DESC, origem, categoria""").fetchall()
    projetos = con.execute(f"""SELECT substr(codigo,1,10) AS projeto, COUNT(*) AS quantidade
                                FROM erro WHERE {where} AND codigo LIKE 'F___-P____%'
                            GROUP BY substr(codigo,1,10)
                            ORDER BY quantidade DESC, projeto LIMIT ?""", (limite,)).fetchall()
    repetidos = con.execute(f"""SELECT origem, codigo, descricao, COUNT(*) AS quantidade
                                 FROM erro WHERE {where}
                             GROUP BY origem, codigo, descricao
                               HAVING COUNT(*)>1
                             ORDER BY quantidade DESC LIMIT ?""", (limite,)).fetchall()
    simples = con.execute(f"""SELECT
        SUM(CASE WHEN gravidade='bloqueia' THEN 1 ELSE 0 END) AS bloqueantes,
        SUM(CASE WHEN gravidade='aviso' THEN 1 ELSE 0 END) AS informativos,
        SUM(CASE WHEN chave LIKE 'campvision:aviso-menor:%' THEN 1 ELSE 0 END) AS avisos_exiftool,
        SUM(CASE WHEN origem IN ('campvision','revisao') THEN 1 ELSE 0 END) AS origem_automatica
        FROM erro WHERE {where}""").fetchone()
    return {
        "abertos": total,
        "bloqueantes": simples[0] or 0,
        "avisos": simples[1] or 0,
        "avisos_menores_exiftool": simples[2] or 0,
        "automaticos": simples[3] or 0,
        "por_tipo": [dict(x) for x in linhas],
        "projetos_com_mais_alertas": [dict(x) for x in projetos],
        "repeticoes_exatas": [dict(x) for x in repetidos],
        "nota": "Diagnóstico somente leitura: nenhuma ocorrência foi apagada ou encerrada."
    }
