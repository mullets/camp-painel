-- 249 · CAMP-FIN (24/11/2026, Rafael: "Estamos recebendo bastante doação pelo Mercado Pago"; "relatório de receitas para o contador";
-- "Temos como interligar com o Mercado Pago?"): tela Financeiro (só admin e master) com o livro de receitas para o contador, no espírito
-- da ITG 2002 (R1): doações e patrocínios separados das outras receitas. A classificação final é do contador.
-- mp_pagamento: cópia SÓ LEITURA dos pagamentos da conta do Mercado Pago, buscada no site (GET /wp-json/camp/v1/painel/mp/pagamentos,
-- contrato 1.33; a chave do Mercado Pago fica no site e nunca vem ao painel), de N em N minutos (financeiro.mp_coleta_min) ou no botão
-- "Sincronizar com o Mercado Pago agora" (em segundo plano). Única pelo id do pagamento no Mercado Pago.
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS mp_pagamento (
  mp_id              TEXT PRIMARY KEY,                -- id do pagamento no Mercado Pago
  aprovado_em        TEXT,                            -- UTC, AAAA-MM-DD HH:MM:SS (date_approved)
  status             TEXT,                            -- approved | refunded | charged_back | in_mediation …
  valor              REAL,                            -- transaction_amount (bruto)
  tarifa             REAL,                            -- soma de fee_details (tarifa do Mercado Pago)
  liquido            REAL,                            -- transaction_details.net_received_amount
  estornado          REAL NOT NULL DEFAULT 0,         -- transaction_amount_refunded (estorno total ou parcial)
  estornos           TEXT,                            -- JSON [{valor, em (UTC)}] (refunds do Mercado Pago)
  meio               TEXT,                            -- payment_type_id (credit_card, bank_transfer = Pix, ticket = boleto…)
  metodo             TEXT,                            -- payment_method_id (pix, visa, master, bolbradesco…)
  external_reference TEXT,                            -- CAMP-AMIGO-n | CAMP-COB-n | CAMP-INGRESSO-… | CAMP-PAT-n | vazio (direto na conta)
  descricao          TEXT,
  pagador            TEXT,                            -- só o nome (sem CPF, sem e-mail)
  classificar        TEXT,                            -- natureza escolhida à mão ("Classificar como…"); NULL = a do mapa
  nota               TEXT,                            -- nota da equipe para o contador
  classificado_por   TEXT,
  visto_em           TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_em        TEXT
);
CREATE INDEX IF NOT EXISTS idx_mp_pagamento_aprovado ON mp_pagamento (aprovado_em);
CREATE INDEX IF NOT EXISTS idx_mp_pagamento_ref ON mp_pagamento (external_reference);
CREATE TABLE IF NOT EXISTS financeiro_estado (chave TEXT PRIMARY KEY, valor TEXT);   -- última busca, erro, período coberto
CREATE TABLE IF NOT EXISTS financeiro_nota (            -- "Notas para o contador", uma por período (de|ate)
  periodo        TEXT PRIMARY KEY,
  texto          TEXT NOT NULL DEFAULT '',
  atualizado_por TEXT,
  atualizado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS financeiro_conta (           -- contas da CAMP (hoje só o Mercado Pago; Rafael: "Em breve teremos a conta do projeto de Rouanet")
  id        INTEGER PRIMARY KEY,
  nome      TEXT NOT NULL UNIQUE,
  banco     TEXT,
  tipo      TEXT NOT NULL DEFAULT 'operacional',        -- operacional | projeto_incentivado
  restrito  INTEGER NOT NULL DEFAULT 0,                 -- 1 = recursos com restrição: relatado SEMPRE separado do operacional
  ativa     INTEGER NOT NULL DEFAULT 1,
  projeto   TEXT,                                       -- rótulo de projeto/rubrica sugerido nas despesas desta conta (texto livre; sem rubricas/SALIC ainda)
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO financeiro_conta (id, nome, banco, tipo, restrito) VALUES (1, 'Mercado Pago', 'Mercado Pago', 'operacional', 0);
-- Rafael (24/11/2026): "Em breve teremos a conta do projeto de Rouanet, que será uma conta do Banco do Brasil" — PRONAC 2613864 · "Livro Karazawa".
-- Já cadastrada, COM RESTRIÇÃO e DESATIVADA até ele ativar quando a conta abrir; dados do banco em branco (ele preenche).
INSERT OR IGNORE INTO financeiro_conta (id, nome, banco, tipo, restrito, ativa, projeto) VALUES
 (2, 'Banco do Brasil · Projeto Rouanet · PRONAC 2613864 · Livro Karazawa', NULL, 'projeto_incentivado', 1, 0, 'PRONAC 2613864 · Livro Karazawa');
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('financeiro.mp_coleta_min', '60', 'De quantos em quantos minutos o painel busca no site os pagamentos da conta do Mercado Pago para o Financeiro (0 desliga)', 0),
 ('financeiro.mp_inicio', '2026-01-01', 'Primeiro dia (AAAA-MM-DD) dos pagamentos do Mercado Pago que o Financeiro busca na primeira vez', 0),
 ('financeiro.naturezas', '{"doacao":"doacoes","direto_mp":"doacoes","doacao_acervo":"doacoes_restricao","adocao":"doacoes_restricao","amigos_anual":"contribuicoes","amigos_mensal":"contribuicoes","patrocinio":"patrocinios","ingresso":"servicos","servico":"servicos","cobranca":"outras"}', 'Financeiro: natureza (ITG 2002) de cada origem de receita, em JSON. A classificação final é do contador', 0);
