-- 252 · CAMP-FIN aluguel, pessoal e contas fixas (24/11/2026). Rafael: "Aluguel, funcionário?". Categorias novas (as antigas e os dados
-- de antes ficam como estão), a lista de contas fixas (compromissos que se repetem: aluguel, salário, INSS, internet…) e o elo de cada mês
-- com a saída do Mercado Pago que a pagou (confirmado por uma pessoa). Salário é dado sensível: só admin e master; o nome da pessoa sai na
-- exclusão LGPD e os valores ficam. Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE, json_insert (não troca chave que já existe).
CREATE TABLE IF NOT EXISTS conta_fixa (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  nome          TEXT NOT NULL,                       -- "Aluguel da sede", "Salário · <pessoa>", "INSS", "Internet"
  categoria     TEXT NOT NULL,                       -- chave de despesas.categorias
  valor         REAL NOT NULL,                       -- valor esperado (ou o mínimo da faixa)
  valor_max     REAL,                                -- faixa: de valor até valor_max (NULL = valor fixo, ± 5%)
  dia           INTEGER NOT NULL DEFAULT 5,          -- dia do vencimento (1–31; mês curto = último dia)
  periodicidade TEXT NOT NULL DEFAULT 'mensal',      -- mensal | anual | decimo_terceiro (13º, em dezembro)
  mes_anual     INTEGER,                             -- anual: mês do vencimento (1–12)
  pista         TEXT,                                -- o nome ou o CNPJ que aparece na descrição do Mercado Pago
  pessoa_nome   TEXT,                                -- pessoal: nome da pessoa (só admin e master veem; sai na exclusão LGPD)
  pessoa_email  TEXT,                                -- pessoal: e-mail, só para achar a pessoa na exclusão LGPD
  conta_id      INTEGER NOT NULL DEFAULT 1,          -- financeiro_conta.id
  inicio        TEXT NOT NULL,                       -- AAAA-MM-DD
  fim           TEXT,                                -- AAAA-MM-DD (NULL = sem fim)
  ativa         INTEGER NOT NULL DEFAULT 1,
  criado_por    TEXT,
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_por  TEXT,
  alterado_em   TEXT,
  apagado_em    TEXT,
  apagado_por   TEXT
);
CREATE TABLE IF NOT EXISTS conta_fixa_pagamento (        -- o mês da conta fixa e a despesa que o pagou (confirmado por uma pessoa)
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  conta_fixa_id  INTEGER NOT NULL,
  competencia    TEXT NOT NULL,                          -- AAAA-MM do vencimento
  despesa_id     INTEGER NOT NULL UNIQUE,
  confirmado_por TEXT,
  confirmado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (conta_fixa_id, competencia)
);
CREATE INDEX IF NOT EXISTS idx_cfp_conta ON conta_fixa_pagamento (conta_fixa_id, competencia);
UPDATE configuracao SET valor = json_insert(valor,
    '$.aluguel', 'Aluguel e condomínio',
    '$.consumo', 'Contas de consumo (luz, água, internet, telefone)',
    '$.salarios', 'Salários',
    '$.encargos', 'Encargos (INSS, FGTS, férias, 13º)',
    '$.bolsas', 'Bolsas e estágio',
    '$.autonomos', 'Autônomos e RPA')
  WHERE chave = 'despesas.categorias' AND json_valid(valor);
UPDATE configuracao SET valor = json_set(valor, '$.servicos', 'Serviços de terceiros (PJ)')
  WHERE chave = 'despesas.categorias' AND json_valid(valor) AND json_extract(valor, '$.servicos') = 'Serviços de terceiros';
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('contas_fixas.tolerancia', '5', 'Financeiro · contas fixas: diferença de valor aceita ao casar com a saída do Mercado Pago (%)', 0),
 ('contas_fixas.atraso_dias', '3', 'Financeiro · contas fixas: dias depois do vencimento para a conta ficar atrasada (alerta na Home do admin)', 0);
