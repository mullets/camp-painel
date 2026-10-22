"""REF-040: um evento por importação efetiva, não por clique/reenvio do mesmo pacote.

Importação e confronto dos documentos continuam acontecendo normalmente. Somente
o histórico deixa de registrar atividades fictícias, sem apagar eventos antigos.
"""
from __future__ import annotations

import hashlib
import json


def registrar_importacao(con, projeto: str, ator: str, lote_id: int, contagens: dict, documentos: list) -> bool:
    """Retorna True somente se gravou evento novo. Não faz commit."""
    novas = int(contagens.get("criadas") or 0)
    atualizadas = int(contagens.get("atualizadas") or 0)
    corrigidas = int(contagens.get("recodificadas") or 0)
    colisoes = int(contagens.get("colisoes") or 0)
    problemas_novos = int(contagens.get("problemas_registrados") or 0)
    # 0 folhas novas + 0 alterações + 0 problemas novos NÃO é importação.
    if not (novas or atualizadas or corrigidas or colisoes or problemas_novos):
        return False
    digest = hashlib.sha256(
        json.dumps(documentos, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:20]
    detalhe = {
        "lote_id": lote_id,
        "criadas": novas,
        "atualizadas": atualizadas,
        "ignoradas": int(contagens.get("ignoradas") or 0),
        "retirados": int(contagens.get("retirados") or 0),
        "problemas": int(contagens.get("problemas") or 0),
        "pacote_sha": digest,
    }
    # Uma releitura que NÃO mudou o pacote pode atualizar folhas ainda pendentes
    # tecnicamente. Isso não significa que houve N importações novas no histórico.
    for (bruto,) in con.execute(
        """SELECT detalhe FROM evento
            WHERE entidade='projeto' AND codigo=? AND tipo='folhas_importadas_do_lote'
            ORDER BY id DESC LIMIT 100""", (projeto,)
    ):
        try:
            antigo = json.loads(bruto or "{}")
        except (ValueError, TypeError):
            continue
        if antigo.get("lote_id") != lote_id:
            continue
        if antigo.get("pacote_sha") == digest and all(
            antigo.get(campo) == detalhe[campo]
            for campo in ("criadas", "atualizadas", "ignoradas", "retirados", "problemas")
        ):
            return False
        break
    con.execute(
        """INSERT INTO evento (entidade, codigo, tipo, ator, detalhe)
           VALUES ('projeto',?,'folhas_importadas_do_lote',?,?)""",
        (projeto, ator, json.dumps(detalhe, ensure_ascii=False)),
    )
    return True
