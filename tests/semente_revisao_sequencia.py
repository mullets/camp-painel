#!/usr/bin/env python3
"""Semente do teste de navegador da sequência congelada na revisão (CAMP-FICHA, 25/11/2026). Nunca usar em produção.
Uso (depois de tests/semear_banco_teste.py): CAMP_DB_PATH=<banco> python tests/semente_revisao_sequencia.py
F026-P0001 vira um lote em revisão: D1, D2, D5, D6 Planta (Arquitetura) e D3, D4 Estrutura, para a grade agrupar por disciplina
(Arquitetura: D1, D2, D5, D6 · Estrutura: D3, D4). Todas conferidas, menos a D4 (a única pendente, "lá no fim" da ordem do código)."""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from app.db import connect  # noqa: E402

P = "F026-P0001"
c = connect()
lid = c.execute("""INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, folhas_esperadas, folhas_encontradas, etapa)
                   VALUES ('Lote de teste da sequência', ?, '/dev/shm/sem-qnap/F026-P0001', 6, 6, 'revisao')""", (P,)).lastrowid
folhas = [r[0] for r in c.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (P,))]
for n, cod in enumerate(folhas):
    c.execute("UPDATE item SET lote_id=?, revisao=?, tipo_documento=?, folha=?, parceiros=NULL, ordem_manual=NULL WHERE codigo=?",
              (lid, "pendente" if n == 3 else "conferida", "Estrutura" if n in (2, 3) else "Planta", str(n + 1), cod))
c.commit()
print(" ".join(folhas))
