-- 21/10/2026 (Rafa: "pq demora tanto pra subir um projeto?" — 24 folhas em 21 min, ~54 s por folha): o painel manda ao site várias folhas
-- ao mesmo tempo. Cada folha continua com os seus pedidos em ordem; só folhas DIFERENTES vão juntas. 1 = uma de cada vez (como antes).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('site.envio_paralelo', '3', 'Quantas folhas o painel envia ao site ao mesmo tempo ao publicar (1 a 6). 1 = uma de cada vez, como antes. Baixe se o site reclamar de excesso de pedidos', 0);
