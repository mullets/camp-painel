"""Livro de registro do CAMP Vision 2 (ACERVOS_CAMP/_campvision/registro/AAAA-MM.jsonl): leitura INCREMENTAL para o Histórico do projeto.

O livro só cresce (nunca se reescreve linha). O painel guarda, por arquivo, a posição em bytes até a última linha COMPLETA e na
próxima leitura continua dali. Linha cortada no fim (o CV2 ainda escrevendo) fica para a próxima. Arquivo que ENCOLHEU (foi
reescrito) é lido de novo desde o começo; a chave (arquivo, byte inicial) impede duplicar. Nunca roda dentro de uma requisição:
quem chama é o coletor do QNAP, em segundo plano.
"""
from __future__ import annotations

import json
from pathlib import Path

PASTA = Path("_campvision") / "registro"
LIMITE_POR_RODADA = 2_000_000          # bytes lidos por arquivo em cada rodada (o resto fica para a seguinte)

ROTULO = {"recebido": "Recebido", "copiado": "Copiado", "conferido": "Conferido", "renomeado": "Renomeado", "lido": "Lido pelo CAMP Vision",
          "exif_gravado": "Dados gravados no arquivo", "apagado_original": "Original apagado", "erro": "Erro", "refeito": "Refeito", "legado": "Material antigo",
          "decisao": "Decisão registrada", "relido": "Lido de novo", "quarentena": "Original guardado na quarentena", "releitura_cancelada": "Releitura cancelada"}


def ler_incremental(con, raiz: Path | str) -> dict:
    """Lê o que o livro ganhou desde a última vez. Devolve {"linhas": novas, "arquivos": n}. Faz commit."""
    pasta = Path(raiz) / PASTA
    novas = arquivos = 0
    if not pasta.is_dir():
        return {"linhas": 0, "arquivos": 0}
    for arq in sorted(pasta.glob("*.jsonl")):
        try:
            tamanho = arq.stat().st_size
        except OSError:
            continue
        atual = con.execute("SELECT posicao FROM livro_posicao WHERE arquivo=?", (arq.name,)).fetchone()
        pos = atual[0] if atual else 0
        if tamanho < pos:                               # o arquivo encolheu: começa de novo (a chave única evita duplicar)
            pos = 0
        if tamanho == pos:
            continue
        try:
            with arq.open("rb") as f:
                f.seek(pos)
                bloco = f.read(min(tamanho - pos, LIMITE_POR_RODADA))
        except OSError:
            continue
        fim_ok = bloco.rfind(b"\n") + 1                 # só até a última linha completa
        if fim_ok == 0:
            continue
        cursor = pos
        for bruto in bloco[:fim_ok].split(b"\n"):
            inicio, cursor = cursor, cursor + len(bruto) + 1
            if not bruto.strip():
                continue
            try:
                j = json.loads(bruto.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(j, dict):
                continue
            det = j.get("detalhe")
            det = json.dumps(det, ensure_ascii=False) if isinstance(det, (dict, list)) else (str(det) if det not in (None, "") else None)
            novas += con.execute("""INSERT OR IGNORE INTO livro_cv (arquivo, inicio, quando, acao, projeto_codigo, documento_codigo, lote_id, operador, estacao, nome_original, detalhe)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                 (arq.name, inicio, str(j.get("quando") or "")[:40] or None, str(j.get("acao") or "")[:40] or None,
                                  (str(j.get("codigo_projeto") or "").strip().upper() or None), (str(j.get("codigo_documento") or "").strip().upper() or None),
                                  str(j.get("lote_id") or "")[:120] or None, str(j.get("operador") or "")[:120] or None, str(j.get("estacao") or "")[:80] or None,
                                  str(j.get("nome_original") or "")[:200] or None, (det or "")[:500] or None)).rowcount
        con.execute("INSERT INTO livro_posicao (arquivo, posicao, lido_em) VALUES (?,?,datetime('now')) ON CONFLICT(arquivo) DO UPDATE SET posicao=excluded.posicao, lido_em=excluded.lido_em",
                    (arq.name, pos + fim_ok))
        arquivos += 1
    con.commit()
    return {"linhas": novas, "arquivos": arquivos}


def historico(con, projeto: str, limite: int = 40) -> list[dict]:
    """As últimas linhas do livro deste projeto, da mais nova para a mais velha, com o nome da ação em português."""
    return [{"quando": r["quando"], "acao": ROTULO.get(r["acao"], r["acao"] or "Registro"), "documento": r["documento_codigo"], "operador": r["operador"],
             "estacao": r["estacao"], "detalhe": r["detalhe"]}
            for r in con.execute("SELECT * FROM livro_cv WHERE projeto_codigo=? ORDER BY quando DESC, id DESC LIMIT ?", (projeto, limite))]
