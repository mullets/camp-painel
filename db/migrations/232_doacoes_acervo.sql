-- 232 · CAMP-DOA-ACERVO (20/11/2026, Rafael: "Vamos pôr a parte de doação de acervo no site! … com infos no painel administrativo, e
-- estágios."): intenções de doação de acervo recebidas pelo formulário do site (/intencao-de-doacao-de-acervo/, plugin 1.30.0,
-- contrato 1.20). O painel guarda uma cópia, buscada por GET /wp-json/camp/v1/painel/doacoes-acervo?desde=… de N em N minutos
-- (doacoes_acervo.coleta_min) ou em "Sincronizar agora"; as mudanças de etapa, notas e a cobrança vão ao site por
-- POST /painel/doacoes-acervo/{id} (o site é a fonte; a cópia volta na resposta). Fotos: só passam pelo painel (não ficam aqui).
-- Tela Doações de acervo (só admin e master: tem dados pessoais). LGPD: "apagar esta pessoa" anonimiza (etapa e valores ficam).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS doacao_acervo (
  site_id       INTEGER PRIMARY KEY,               -- ID da intenção no site (camp_doacao_acervo)
  protocolo     TEXT,                              -- CAMP-AAAA-NNNNNN
  recebida_em   TEXT,                              -- UTC, AAAA-MM-DD HH:MM:SS
  nome          TEXT,
  email         TEXT,                              -- minúsculas (LGPD: apagado no apagar pessoa)
  telefone      TEXT,
  autor         TEXT,                              -- arquiteto, escritório ou pessoa a quem o acervo pertenceu
  local         TEXT,                              -- cidade/UF onde está guardado
  faixa         TEXT,                              -- quantidade_estimativa_faixa (ate_50 | 51_500 | mais_500 | nao_sei): estimativa, nunca contagem
  etapa         TEXT,                              -- em_analise | info | visita | aprovada | nao_aprovada | contrato_enviado | contrato_assinado | cobranca | paga | recebido | arquivada
  valor         REAL,                              -- contribuição acordada no contrato (R$)
  assinado_em   TEXT,                              -- AAAA-MM-DD (as duas partes)
  dados         TEXT,                              -- JSON do registro do site (contrato 1.20), sem as fotos
  anonimizado   INTEGER NOT NULL DEFAULT 0,
  alterado_em   TEXT,
  visto_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_doacao_acervo_etapa ON doacao_acervo (etapa);
CREATE INDEX IF NOT EXISTS idx_doacao_acervo_email ON doacao_acervo (email);
CREATE TABLE IF NOT EXISTS doacao_acervo_estado (  -- estado da busca (desde, última busca, último erro, listas do site)
  chave TEXT PRIMARY KEY,
  valor TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('doacoes_acervo.coleta_min', '10', 'De quantos em quantos minutos o painel busca no site as intenções de doação de acervo (0 desliga)', 0);
