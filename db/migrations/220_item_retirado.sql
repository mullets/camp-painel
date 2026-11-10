-- CAMP-DUP (10/11/2026): "Não quero que fique cópias!" (Rafael). As cópias de uma prancha (TIFF/DNG/JPG LIMPO/"para internet") saem do
-- painel por scripts/retirar_copias.py (simula por padrão). A folha retirada vira uma LÁPIDE aqui (a linha inteira em JSON, com o que
-- dependia dela), para o desfazer voltar tudo e para o número D NUNCA ser reusado (o maior D do projeto conta as lápides) nem a
-- importação/releitura do CAMP Vision trazer a folha de volta. Nenhum arquivo do QNAP é apagado.
CREATE TABLE IF NOT EXISTS item_retirado (
  codigo          TEXT PRIMARY KEY,
  projeto_codigo  TEXT NOT NULL,
  sequencial      INTEGER,
  md5             TEXT,
  arquivo_origem  TEXT,
  fica            TEXT,                 -- a folha que ficou no lugar (a JPG original)
  motivo          TEXT,
  linha           TEXT NOT NULL,        -- a linha de `item` inteira (JSON)
  dependentes     TEXT,                 -- linhas apagadas junto (revisão, problemas, localização…) e referências reapontadas (JSON)
  site            TEXT,                 -- se saiu do site: {site_id, estava, redir_antes} (JSON)
  plano           TEXT,
  retirado_por    TEXT,
  retirado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_item_retirado_projeto ON item_retirado (projeto_codigo, sequencial);
