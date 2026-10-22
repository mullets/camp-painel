"""WP-AUD-05: auditoria SOMENTE LEITURA painel ↔ Tainacan.

Executar no servidor de homologação do painel:
  PYTHONPATH=backend python -m app.auditoria_publicacao --limite 300 --saida /tmp/camp-auditoria.json
Sem --aplicar: esta ferramenta nunca publica, renomeia, apaga ou migra registros.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


_EXPECTED = {"no_ar": "publish", "rascunho": "draft", "fora_do_ar": "private"}


def diagnosticar(painel: list[dict], itens_site: list[dict], completo: bool = False) -> dict:
    """Comparar por ID Tainacan. Nenhuma chamada à rede ou escrita de banco."""
    by_id = {int(s["id"]): s for s in itens_site if s.get("id") is not None}
    by_painel = {int(p["tainacan_item_id"]): p for p in painel if p.get("tainacan_item_id")}
    faltando, divergente, orfao, corretos = [], [], [], 0
    for id_, p in sorted(by_painel.items()):
        s = by_id.get(id_)
        if not s:
            faltando.append({"codigo": p["codigo"], "id": id_, "tipo": p["tipo"]})
            continue
        status = str(p.get("status_site") or "").strip()
        esperado = _EXPECTED.get(status)
        observado = str(s.get("status") or "").strip()
        # Não equiparar 'private' e 'draft' automaticamente: relatório para decisão editorial.
        if esperado and observado != esperado:
            divergente.append({"codigo": p["codigo"], "id": id_, "tipo": p["tipo"],
                               "painel": status, "esperado_wp": esperado, "wp": observado})
        else:
            corretos += 1
    for id_, s in sorted(by_id.items()):
        if completo and id_ not in by_painel and str(s.get("status") or "") == "publish":
            orfao.append({"id": id_, "status": "publish", "tipo": s.get("tipo", "desconhecido")})
    return {"total_painel": len(by_painel), "total_site": len(by_id), "corretos": corretos,
            "faltando_no_site": faltando, "status_divergente": divergente,
            "publicos_sem_vinculo_no_painel": orfao, "orfaos_nao_avaliados": not completo,
            "somente_leitura": True}


def executar(limite: int = 300) -> dict:
    from .config import settings
    from .wp import WP
    path = Path(settings.CAMP_DB_PATH).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Banco do painel não encontrado; nenhum dado foi modificado.")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        painel = []
        for tipo, tabela in (("projeto", "projeto"), ("documento", "item")):
            for p in con.execute(f"""SELECT codigo, tainacan_item_id, status_site FROM {tabela}
                                      WHERE tainacan_item_id IS NOT NULL ORDER BY codigo LIMIT ?""", (limite,)):
                painel.append({"codigo": p["codigo"], "tainacan_item_id": p["tainacan_item_id"],
                               "status_site": p["status_site"], "tipo": tipo})
    finally:
        con.close()
    wp = WP()
    site = []
    for tipo, colecao in (("projeto", 8007), ("documento", 8013)):
        for i, s in enumerate(wp.itens(colecao)):
            if i >= limite: break
            site.append({"id": s.get("id"), "status": s.get("status"), "tipo": tipo})
    return diagnosticar(painel, site)


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria de IDs/status do acervo CAMP (somente leitura)")
    parser.add_argument("--limite", type=int, default=300)
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args()
    if args.limite < 1 or args.limite > 20000:
        parser.error("--limite deve estar entre 1 e 20000")
    resultado = executar(args.limite)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.write_text(texto + "\n", encoding="utf-8")
    else:
        print(texto)


if __name__ == "__main__":
    main()
