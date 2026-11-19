-- 231 · CAMP-COB (19/11/2026, Rafael: "Quero poder no admin criar uma cobrança de alguém que vai doar acervo, ex. 2 mil reais, criar a
-- cobrança para pagar com o Mercado Pago, e quero poder saber no extrato o que era."): cobranças avulsas pelo Mercado Pago.
-- O painel grava a cobrança e pede o link ao site (POST /wp-json/camp/v1/painel/cobrancas, contrato 1.19, idempotente por ref_painel);
-- a situação volta pela busca GET /painel/cobrancas?desde=… de N em N minutos (cobrancas.coleta_min) ou em "Sincronizar agora".
-- Guarda o que aparece no Mercado Pago (título do item, external_reference CAMP-COB-n, statement_descriptor e o id do pagamento) para
-- conferir com o extrato. Tela Cobranças avulsas (só admin e master: tem dados pessoais). Histórico na tabela evento
-- (entidade 'cobranca_avulsa', sem nome nem e-mail de quem paga). LGPD: "apagar esta pessoa" anonimiza (os valores ficam).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS cobranca_avulsa (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  ref_painel           TEXT UNIQUE,                     -- painel-cob-<id>: chave de idempotência no site
  site_id              INTEGER UNIQUE,                  -- ID do registro no site (camp_cobranca)
  nome                 TEXT,
  email                TEXT,                            -- minúsculas (LGPD: apagado no apagar pessoa)
  telefone             TEXT,
  valor                REAL NOT NULL,                   -- valor cobrado (R$)
  finalidade           TEXT NOT NULL,                   -- doacao_acervo | doacao | patrocinio | servico | outro
  descricao            TEXT NOT NULL,                   -- o que é (vai para o título e a descrição do item no Mercado Pago)
  vence                TEXT,                            -- AAAA-MM-DD (opcional; o link expira no fim do dia)
  vinculo_tipo         TEXT,                            -- fundo | projeto (opcional)
  vinculo_codigo       TEXT,                            -- F014 ou F014-P0004
  situacao             TEXT NOT NULL DEFAULT 'sem_link',-- aberta | em_analise | paga | vencida | cancelada | recusada | estornada | sem_link
  link                 TEXT,                            -- link do Mercado Pago (Checkout Pro)
  preferencia_id       TEXT,
  external_reference   TEXT,                            -- CAMP-COB-<id do site>: aparece no relatório do Mercado Pago
  mp_titulo            TEXT,                            -- título do item no Mercado Pago ("CAMP · Finalidade · descrição curta")
  statement_descriptor TEXT,                            -- o que sai na fatura do cartão (ex.: CAMP DOACAO)
  modo                 TEXT,                            -- teste | producao (do Mercado Pago, quando o link foi criado)
  mp_pagamento_id      TEXT,                            -- id do pagamento aprovado no Mercado Pago
  pago_em              TEXT,                            -- UTC
  valor_pago           REAL,
  valor_liquido        REAL,                            -- líquido recebido (quando o Mercado Pago informa)
  tarifa               REAL,
  meio                 TEXT,                            -- pix | credit_card | …
  pagamentos           TEXT,                            -- JSON: todas as tentativas lidas no Mercado Pago
  historico_site       TEXT,                            -- JSON: registro técnico do site (sem dados pessoais)
  email_enviado_em     TEXT,
  erro                 TEXT,                            -- último motivo de não ter link (site/Mercado Pago)
  criado_por           TEXT,
  criado_por_nome      TEXT,
  criado_em            TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_em          TEXT,
  cancelada_em         TEXT,
  anonimizado          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cobranca_avulsa_email ON cobranca_avulsa (email);
CREATE INDEX IF NOT EXISTS idx_cobranca_avulsa_criado ON cobranca_avulsa (criado_em);
CREATE TABLE IF NOT EXISTS cobranca_avulsa_estado (     -- estado da busca (desde, última busca, último erro, Mercado Pago ligado)
  chave TEXT PRIMARY KEY,
  valor TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('cobrancas.coleta_min', '10', 'De quantos em quantos minutos o painel busca no site a situação das cobranças avulsas do Mercado Pago (0 desliga)', 0);
