-- 250 · CAMP-FIN despesas (24/11/2026). Rafael: "E o que gastamos? Porque já comprei coisas por Pix e débito que seria bom justificar." e
-- "Só usamos a Mercado Pago!". As saídas da conta do Mercado Pago vêm do relatório de liberações (pelo site, contrato 1.33: a chave fica lá),
-- buscado em segundo plano desde financeiro.mp_inicio; extrato OFX de outra conta (ex.: a do projeto Rouanet no Banco do Brasil) e
-- lançamento à mão (dinheiro). Cada despesa: categoria, justificativa e comprovante (pasta ao lado do banco, nunca no repositório).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS despesa (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  conta_id       INTEGER NOT NULL DEFAULT 1,            -- financeiro_conta.id
  data           TEXT NOT NULL,                         -- AAAA-MM-DD (São Paulo)
  valor          REAL NOT NULL,                         -- R$, positivo (saída)
  meio           TEXT,                                  -- pix | debito | credito | boleto | dinheiro | tarifa | saldo | transferencia | outro
  contraparte    TEXT,                                  -- o nome como está no extrato
  descricao      TEXT,                                  -- texto do extrato (descrição/memo)
  origem         TEXT NOT NULL DEFAULT 'manual',        -- mp | ofx | manual
  chave          TEXT NOT NULL UNIQUE,                  -- mp:<id>… | ofx:<conta>:<FITID> | ofx:<conta>:h:<hash> | manual:<aleatório>
  tipo           TEXT NOT NULL DEFAULT 'despesa',       -- despesa | transferencia_propria (não é despesa)
  categoria      TEXT,                                  -- chave de despesas.categorias (NULL = precisa justificar)
  justificativa  TEXT,                                  -- o que foi comprado e por quê
  projeto        TEXT,                                  -- projeto/rubrica (texto livre; sem rubricas/SALIC ainda)
  restrito       INTEGER NOT NULL DEFAULT 0,            -- paga com dinheiro de doação com restrição
  vinculo_tipo   TEXT,                                  -- doacao | patrocinio | evento | projeto
  vinculo_ref    TEXT,                                  -- id da doação/patrocínio, nome do evento, código do projeto
  tarefa_id      INTEGER,                               -- doacao_tarefa.id (ex.: "Cotar frete")
  mp_ref         TEXT,                                  -- SOURCE_ID do Mercado Pago
  criado_por     TEXT,
  criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_por   TEXT,
  alterado_em    TEXT,
  apagado_em     TEXT,                                  -- só some da lista; o motivo fica
  apagado_por    TEXT,
  apagado_motivo TEXT
);
CREATE INDEX IF NOT EXISTS idx_despesa_data ON despesa (data);
CREATE INDEX IF NOT EXISTS idx_despesa_conta ON despesa (conta_id, data);
CREATE TABLE IF NOT EXISTS despesa_anexo (               -- comprovantes (nota fiscal, recibo): o arquivo fica em despesas_comprovantes/<id>/
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  despesa_id INTEGER NOT NULL,
  nome       TEXT NOT NULL,
  arquivo    TEXT NOT NULL,
  mime       TEXT,
  tamanho    INTEGER,
  sha256     TEXT,
  criado_por TEXT,
  criado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_despesa_anexo ON despesa_anexo (despesa_id);
CREATE TABLE IF NOT EXISTS mp_relatorio (                -- relatórios de liberações pedidos ao Mercado Pago (um por mês)
  periodo    TEXT PRIMARY KEY,                           -- AAAA-MM
  de         TEXT NOT NULL,
  ate        TEXT NOT NULL,
  pedido_em  TEXT,                                       -- UTC
  arquivo    TEXT,
  baixado_em TEXT,                                       -- UTC
  linhas     INTEGER,
  erro       TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('despesas.categorias', '{"materiais":"Materiais de conservação e acondicionamento","frete":"Frete e transporte","servicos":"Serviços de terceiros","pessoal":"Pessoal e estagiários","tecnologia":"Tecnologia e software","tarifas":"Tarifas bancárias e do Mercado Pago","eventos":"Eventos e visitas","manutencao":"Manutenção do espaço","impostos":"Impostos e taxas","outras":"Outras despesas"}', 'Financeiro: categorias de despesa (JSON chave → nome)', 0),
 ('despesas.mp_relatorio', '1', 'Financeiro: buscar as saídas da conta do Mercado Pago pelo relatório de liberações (1 liga, 0 desliga)', 0);
