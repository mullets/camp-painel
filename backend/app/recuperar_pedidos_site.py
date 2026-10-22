"""WP-AUD-01 — resgatar pedidos historicamente marcados pela coleta antiga.

Somente leitura por padrão:
  PYTHONPATH=backend python -m app.recuperar_pedidos_site --paginas 100
Após revisar o relatório, o operador pode rodar --aplicar. Insere apenas IDs
ainda AUSENTES em pedido_site; não reenvia e-mails e não gera duplicatas.
É necessário ter a rota /solicitacoes?todas=1&pagina=N do WordPress 1.5.89+.
"""
from __future__ import annotations

import argparse
import json


def recuperar(con, wp, aplicar: bool = False, paginas: int = 100) -> dict:
    """Histórico privado com Application Password. Simulação não escreve no banco."""
    total = 0
    faltantes = []
    inseridos = 0
    concluido = False
    for pag in range(1, paginas + 1):
        r = wp.h.get("/wp-json/camp/v1/solicitacoes",
                     params={"todas": 1, "pagina": pag, "limite": 200})
        if r.status_code >= 400:
            raise RuntimeError(f"Falha ao consultar histórico de pedidos (HTTP {r.status_code}), página {pag}")
        dados = r.json()
        if not isinstance(dados, list):
            raise RuntimeError("Resposta histórica inválida; nenhuma alteração efetuada nesta página")
        ids = [p.get("id") for p in dados if isinstance(p, dict)]
        if len(ids) != len(dados) or any(type(x) is not int or x <= 0 for x in ids):
            raise RuntimeError("Histórico com IDs inválidos; interrompido sem prosseguir")
        if len(set(ids)) != len(ids):
            raise RuntimeError("Histórico com IDs repetidos na mesma página")
        total += len(dados)
        salvar = []
        for p in dados:
            if not con.execute("SELECT 1 FROM pedido_site WHERE site_id=?", (p["id"],)).fetchone():
                faltantes.append(int(p["id"]))
                salvar.append(p)
        if aplicar:
            try:
                for p in salvar:
                    inseridos += con.execute(
                        """INSERT OR IGNORE INTO pedido_site
                           (site_id, tipo, codigo, criado_no_site, payload) VALUES (?,?,?,?,?)""",
                        (int(p["id"]), str(p.get("tipo") or ""), str(p.get("codigo") or ""),
                         str(p.get("criado_em") or ""), json.dumps(p, ensure_ascii=False)),
                    ).rowcount
                con.commit()
            except Exception:
                con.rollback()
                raise
        if len(dados) < 200:
            concluido = True
            break
    return {"simulado": not aplicar, "analisados": total,
            "faltantes_ids": faltantes, "faltantes_total": len(faltantes),
            "inseridos": inseridos, "varredura_completa": concluido}


def main() -> None:
    from .db import connect
    from .wp import WP
    parser = argparse.ArgumentParser(description="Recuperar pedidos legados sem duplicação")
    parser.add_argument("--paginas", type=int, default=100)
    parser.add_argument("--aplicar", action="store_true", help="Grava somente IDs ausentes no painel")
    args = parser.parse_args()
    if args.paginas < 1 or args.paginas > 10000:
        parser.error("paginas deve estar entre 1 e 10000")
    con = connect()
    try:
        resultado = recuperar(con, WP(), aplicar=args.aplicar, paginas=args.paginas)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
