-- Entrada de acervo (proveniência física) e direitos/licença por fundo
CREATE TABLE entrada_acervo (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  fundo_codigo  TEXT NOT NULL REFERENCES fundo(codigo),
  tipo          TEXT NOT NULL CHECK (tipo IN ('doacao','comodato','deposito','compra','transferencia','outro')),
  data          TEXT,                                  -- AAAA-MM-DD
  entregue_por  TEXT,                                  -- pessoa/instituição
  contato       TEXT,
  documento     TEXT,                                  -- termo assinado: referência/caminho/URL
  conteudo      TEXT,                                  -- o que veio: caixas, tubos, gavetas...
  volumes       INTEGER,
  estado_conservacao TEXT CHECK (estado_conservacao IN (NULL,'bom','regular','ruim','critico')),
  observacoes   TEXT,
  registrado_por TEXT,
  criado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE direitos_fundo (
  fundo_codigo  TEXT PRIMARY KEY REFERENCES fundo(codigo),
  situacao      TEXT NOT NULL DEFAULT 'nao_definida' CHECK (situacao IN ('nao_definida','autorizado','restrito','nao_autorizado')),
  titular       TEXT,                                  -- quem detém os direitos (família, espólio, escritório)
  documento_autorizacao TEXT,                          -- termo/e-mail que autoriza a publicação
  data_autorizacao TEXT,
  validade      TEXT,                                  -- vazio = sem prazo
  resolucao_max TEXT NOT NULL DEFAULT 'jpg_3000' CHECK (resolucao_max IN ('tif','jpg_3000','jpg_1200')),
  credito_exigido TEXT,
  licenca       TEXT,                                  -- ex. CC BY-NC-ND, todos os direitos reservados
  restricoes    TEXT,                                  -- o que não pode (ex.: uso comercial, fotos de família)
  atualizado_por TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
-- fundos que já têm algo no ar herdam 'autorizado' provisório, para não derrubar o que está publicado; o resto fica por definir
INSERT INTO direitos_fundo (fundo_codigo, situacao, atualizado_por)
  SELECT codigo, CASE WHEN status_site='no_ar' THEN 'autorizado' ELSE 'nao_definida' END, 'migracao-010' FROM fundo;
