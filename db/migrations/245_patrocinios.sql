-- 245 · CAMP-PAT-EMPRESA (23/11/2026, Rafael: "na parte de patrocínio por empresa, vamos fazer tudo pelo site? mesmo fluxo da doação de
-- acervo, no painel mesma coisa só que de patrocínios de empresa"): propostas de patrocínio das cotas do Programa 2027, enviadas pelo
-- site (/patrocinio-e-apoio/cotas/, plugin 1.40.0, contrato 1.31). O painel guarda uma cópia, buscada por GET
-- /wp-json/camp/v1/painel/patrocinios?desde=… de N em N minutos (patrocinios.coleta_min) ou em "Sincronizar agora"; etapas, notas e
-- novo link de pagamento vão ao site por POST /painel/patrocinios/{id}. Manual de marca e logos só passam pelo painel (não ficam aqui).
-- Tela Patrocínios (só admin e master: tem dados pessoais). LGPD: "apagar esta pessoa" anonimiza o responsável (empresa e valores ficam).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS patrocinio (
  site_id      INTEGER PRIMARY KEY,               -- ID da proposta no site (camp_patrocinio_emp)
  protocolo    TEXT,
  recebida_em  TEXT,                              -- UTC
  cota         TEXT,                              -- parceiro | mantenedor | institucional | master
  modalidade   TEXT,                              -- anual (à vista) | mensal (12 meses, assinatura)
  empresa      TEXT,                              -- nome da marca
  razao_social TEXT,
  cnpj         TEXT,
  nome         TEXT,                              -- responsável (LGPD: apagado no apagar pessoa)
  email        TEXT,
  telefone     TEXT,
  etapa        TEXT,
  valor_anual  REAL,
  valor_pago   REAL,
  meses_pagos  INTEGER NOT NULL DEFAULT 0,
  dados        TEXT,                              -- JSON do registro do site (contrato 1.31)
  anonimizado  INTEGER NOT NULL DEFAULT 0,
  alterado_em  TEXT,
  visto_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_patrocinio_etapa ON patrocinio (etapa);
CREATE INDEX IF NOT EXISTS idx_patrocinio_email ON patrocinio (email);
CREATE TABLE IF NOT EXISTS patrocinio_estado (chave TEXT PRIMARY KEY, valor TEXT);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('patrocinios.coleta_min', '10', 'De quantos em quantos minutos o painel busca no site as propostas de patrocínio de empresas (0 desliga)', 0);
