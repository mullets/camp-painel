-- 255 · CAMP-FIN (24/11/2026). Rafael (print de Financeiro → Receitas): "isso é despesa… presta atenção". A busca de pagamentos do Mercado Pago
-- (/v1/payments/search, pelo site) traz também os pagamentos FEITOS pela CAMP (ex.: "Anthropic* claude sub", pago com o saldo), e o painel
-- tratava todos como recebidos. O site (plugin 1.44.0, contrato 1.35, OPCIONAL) passa a dizer a direção de cada pagamento; o painel transforma
-- as saídas em despesa (fila Precisa justificar) e guarda a escolha manual "Isto é uma saída (despesa)" / "Isto é uma entrada".
-- Idempotente: ADD COLUMN de coluna que já existe é pulado (db.executar_script_idempotente); CREATE ... IF NOT EXISTS. Nenhum UPDATE/DELETE.
ALTER TABLE mp_pagamento ADD COLUMN direcao TEXT;        -- entrada | saida (site 1.44.0); NULL = site antigo (o painel usa a heurística)
ALTER TABLE mp_pagamento ADD COLUMN contraparte TEXT;    -- saída: quem recebeu (vendedor ou descrição na fatura), como o site mandou
ALTER TABLE mp_pagamento ADD COLUMN debitado REAL;       -- saída: o que saiu da conta (total pago, com as tarifas)
CREATE TABLE IF NOT EXISTS financeiro_direcao (          -- escolha manual da direção de um pagamento do Mercado Pago (lembrada; vence o site)
  mp_id     TEXT PRIMARY KEY,
  direcao   TEXT NOT NULL,                               -- entrada | saida
  dados     TEXT,                                        -- JSON: cópia da linha (data, valor, meio, descrição) para virar despesa mesmo sem mp_pagamento
  por       TEXT,
  em        TEXT NOT NULL DEFAULT (datetime('now'))
);
