"""Relatório completo do banco do painel em um comando. Só leitura.

    python scripts/relatorio.py            # tudo
    python scripts/relatorio.py --site     # só o espelho do site
"""
import argparse, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--site", action="store_true"); a = ap.parse_args()
from app.config import settings  # noqa: E402
con = connect()
print(f"banco: {settings.CAMP_DB_PATH}")

def bloco(titulo, sql, largura=None):
    print(f"\n### {titulo}")
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        print("  (vazio)"); return
    w = [max(len(str(c)), *(min(len(str(r[i])), largura or 60) for r in rows)) for i, c in enumerate(cols)]
    print("  " + "  ".join(str(c).ljust(w[i]) for i, c in enumerate(cols)))
    for r in rows:
        print("  " + "  ".join(str(r[i] if r[i] is not None else "")[:largura or 60].ljust(w[i]) for i in range(len(cols))))

if not a.site:
    bloco("Fundos (tabela de autoridade)", "SELECT codigo, sigla, titulo, data_inicio||'–'||COALESCE(data_fim,'') AS periodo, status_site FROM fundo ORDER BY codigo")
    bloco("Usuários", "SELECT nome, email, papel, ativo, ultimo_login FROM usuario ORDER BY papel DESC")
    bloco("Configurações", "SELECT chave, CASE WHEN sensivel THEN CASE WHEN valor<>'' THEN '(definida)' ELSE '' END ELSE valor END AS valor FROM configuracao ORDER BY chave")

bloco("Sincronizações", "SELECT id, iniciada_em, terminada_em, ok, colecoes, itens, termos, paginas, divergencias, substr(erro,1,80) AS erro FROM sincronizacao ORDER BY id DESC LIMIT 3")
bloco("Coleções do Tainacan", "SELECT id, nome, total_itens FROM wp_colecao ORDER BY total_itens DESC")
bloco("Itens por fundo detectado e situação", "SELECT COALESCE(fundo_detectado,'(sem código)') AS fundo, status, COUNT(*) AS n FROM wp_item GROUP BY 1,2 ORDER BY 1,2")
bloco("Metadados usados nos itens", "SELECT j.key AS metadado, COUNT(*) AS n, SUM(j.value<>'') AS preenchidos FROM wp_item, json_each(wp_item.metadados) j GROUP BY 1 ORDER BY 2 DESC")
bloco("Taxonomias e nº de termos", "SELECT t.nome, COUNT(x.id) AS termos FROM wp_taxonomia t LEFT JOIN wp_termo x ON x.taxonomia_id=t.id GROUP BY t.id ORDER BY 2 DESC")
bloco("Termos (primeiros 40)", "SELECT t.nome AS taxonomia, x.nome, x.slug, x.codigo_detectado FROM wp_termo x JOIN wp_taxonomia t ON t.id=x.taxonomia_id ORDER BY 1,2 LIMIT 40")
bloco("Divergências por tipo", "SELECT campo, COUNT(*) AS n FROM divergencia_site WHERE resolvida=0 GROUP BY 1 ORDER BY 2 DESC")
bloco("Divergências (primeiras 30)", "SELECT entidade, codigo, campo, valor_site FROM divergencia_site WHERE resolvida=0 ORDER BY campo, codigo LIMIT 30")
bloco("Páginas com código", "SELECT id, titulo, slug, status, codigo_detectado FROM wp_pagina WHERE codigo_detectado IS NOT NULL ORDER BY codigo_detectado LIMIT 30")
bloco("Exemplo de item completo", "SELECT id, titulo, codigo_detectado, status, metadados FROM wp_item WHERE codigo_detectado IS NOT NULL ORDER BY id LIMIT 2", largura=400)
con.close()
