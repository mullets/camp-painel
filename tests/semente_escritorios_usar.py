#!/usr/bin/env python3
"""Semente do teste "usar os 3 escritórios" e nomes parecidos (CAMP-FICHA, 25/11/2026). Nunca usar em produção.
Uso (depois de tests/semear_banco_teste.py e tests/semente_revisao_sequencia.py): CAMP_DB_PATH=<banco> python tests/semente_escritorios_usar.py
As outras folhas de F026-P0001 têm 3 escritórios de estrutura (Parisi, DAFRA- LIMA OTERO, IMPER) ; a
D00004 não tem escritório e o Cliente lido é "DAPA LIMA OTERO ENGENHARIA LTDA. S/C." (o escritório, lido como cliente)."""
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from app.db import connect  # noqa: E402

P = "F026-P0001"
PAR = "Sociedade civil de engenharia José Roberto Parisi Ltd."
DAF = "DAFRA- LIMA OTERO ENGENHARIA LTDA. S/C."
DAP = "DAPA LIMA OTERO ENGENHARIA LTDA. S/C."
IMP = "IMPER INCORPORAÇÕES E ADMINISTRAÇÃO PREDIAL S/A"
c = connect()
F = [r[0] for r in c.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (P,))]
par = {0: [PAR, DAF], 1: [PAR, DAF], 2: [IMP, PAR], 5: [PAR]}
for n, cod in enumerate(F):
    lista = [{"escritorio": e, "disciplina": "Estrutura"} for e in par.get(n, [])]
    c.execute("UPDATE item SET parceiros=?, tipo_documento='Estrutura' WHERE codigo=?", (json.dumps(lista, ensure_ascii=False) if lista else None, cod))
c.execute("UPDATE item SET cliente_folha=?, tipo_lido='Detalhe / Estrutura', revisao='pendente' WHERE codigo=?", (DAP, F[3]))
c.commit()
print(F[3])
