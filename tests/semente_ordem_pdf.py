#!/usr/bin/env python3
"""Semente do teste de navegador da ordem pelo nome, do PDF dos TIFF e dos tubos (CAMP-PROJETO/ESTANTE, 25/11/2026). Nunca usar em produção.
Uso (depois de tests/semear_banco_teste.py): CAMP_DB_PATH=<banco> python tests/semente_ordem_pdf.py <pasta do QNAP falso>
Dá nomes de folha fora de ordem às folhas de F026-P0001 (10, 2, 16A, 16, 1, 3: a tela mostra "Folha 10"…), marca duas como Estrutura, grava TIFF falsos (a 3ª
fica sem TIFF) e aponta qnap.prontos_raiz para a pasta. Exportações vão para <pasta>/exportacoes_pdf (CAMP_EXPORTACOES_DIR no servidor)."""
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from PIL import Image  # noqa: E402

from app.db import connect  # noqa: E402

qnap = pathlib.Path(sys.argv[1]).resolve()
P = "F026-P0001"
c = connect()
folhas = [r[0] for r in c.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (P,))]
rel = f"F026/01 - Projetos/{P} - Casa Taruma/TIF"
(qnap / rel).mkdir(parents=True, exist_ok=True)
nomes = ["10", "2", "16A", "16", "1", "3"]
for n, cod in enumerate(folhas):
    tif = None
    if n != 2:
        Image.new("RGB", (640 + n * 10, 420), (30 + n * 20, 40, 50)).save(qnap / rel / f"{cod}.tif", "TIFF", dpi=(400, 400))
        tif = f"{rel}/{cod}.tif"
    c.execute("UPDATE item SET arquivo_tif=?, folha=?, tipo_documento=?, ordem_manual=NULL WHERE codigo=?",
              (tif, nomes[n % len(nomes)], "Estrutura" if n in (2, 3) else "Planta", cod))
c.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (str(qnap),))
c.commit()
print(len(folhas))
