#!/usr/bin/env python3
"""Semente do teste de navegador dos arquivos originais e da cobrança no envio (CAMP-ENTREGA, 25/11/2026). Nunca usar em produção.
Uso (depois de tests/semear_banco_teste.py): CAMP_DB_PATH=<banco> python tests/semente_originais.py <pasta do QNAP falso>
Grava TIFF/JPG falsos para as folhas de F026-P0001, aponta qnap.prontos_raiz para a pasta, deixa o envio "configurado" com valores de
mentira (o teste NUNCA clica em Aprovar e enviar) e cria um link de entrega com cobrança aberta (token fixo, impresso) para a página
"Aguardando pagamento"."""
import hashlib
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from PIL import Image  # noqa: E402

from app.db import connect  # noqa: E402
from app import entrega  # noqa: E402

qnap = pathlib.Path(sys.argv[1]).resolve()
P = "F026-P0001"
c = connect()
folhas = [r[0] for r in c.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (P,))]
rel = f"F026/01 - Projetos/{P} - Casa Taruma/TIF"
(qnap / rel).mkdir(parents=True, exist_ok=True)
for n, cod in enumerate(folhas):
    tif = None
    if n != 2:                                   # a 3ª folha fica sem TIFF registrado
        Image.new("RGB", (300, 200), (30 + n * 20, 40, 50)).save(qnap / rel / f"{cod}.tif", "TIFF")
        tif = f"{rel}/{cod}.tif"
    jpg = None
    if n in (0, 1):
        Image.new("RGB", (300, 200), (90, 40 + n * 20, 50)).save(qnap / rel / f"{cod}.jpg", "JPEG")
        jpg = f"{rel}/{cod}.jpg"
    c.execute("UPDATE item SET arquivo_tif=?, arquivo_jpg=? WHERE codigo=?", (tif, jpg, cod))
for k, v in (("qnap.prontos_raiz", str(qnap)), ("painel.url", "http://127.0.0.1"), ("sender.token", "tok-de-teste"), ("sender.campanha_entrega", "TR09teste"),
             ("entrega.canal", "sender"), ("wp.app_password", "senha de teste"), ("entrega.preco_comercial_folha", "150")):
    c.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES (?,?)", (k, v))
sid = c.execute("INSERT INTO solicitacao (solicitante, email, finalidade, origem, situacao) VALUES ('Carla Lima','carla@editora.exemplo','publicacao','email','entregue')").lastrowid
c.executemany("INSERT INTO solicitacao_item (solicitacao_id, codigo, formato) VALUES (?,?,'tif')", [(sid, f) for f in folhas[:2]])
cid = c.execute("""INSERT INTO cobranca_avulsa (nome, email, valor, finalidade, descricao, situacao, link, external_reference, ref_painel, criado_por, solicitacao_id)
                   VALUES ('Carla Lima','carla@editora.exemplo',300,'servico','Uso de imagens do acervo · pedido teste','aberta','https://mp.exemplo/pagar/1',
                   'CAMP-COB-1','painel-cob-teste',1,?)""", (sid,)).lastrowid
TOKEN = "tokenDeTesteDaPaginaAguardandoPagamento0123"
arqs = [{"n": i + 1, "codigo": f, "titulo": "", "formato": "tif", "resolucao": "TIFF", "nome": f"{f}.tif", "caminho": str(qnap / rel / f"{f}.tif"), "tamanho": 1000}
        for i, f in enumerate(folhas[:2])]
import json  # noqa: E402
c.execute("""INSERT INTO entrega_link (solicitacao_id, token_hash, arquivos, para, canal, teste, criado_por, expira_em, cobranca_id, liberar_apos_pagamento, uso_comercial)
             VALUES (?,?,?,?,?,0,'rafael@camp.arq.br',?,?,1,1)""",
          (sid, hashlib.sha256(TOKEN.encode()).hexdigest(), json.dumps(arqs), "carla@editora.exemplo", "sender", entrega.calcular_expira_em(14), cid))
c.execute("UPDATE solicitacao SET cobranca_modo='com', cobranca_motivo='comercial', cobranca_justificativa='Uso comercial (livro à venda)', cobranca_id=?, valor=300 WHERE id=?", (cid, sid))
c.commit()
print(TOKEN)
