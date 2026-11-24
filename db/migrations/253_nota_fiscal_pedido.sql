-- 253 · CAMP-FIN pedir nota fiscal ao fornecedor (24/11/2026). Rafael: "preparar para criar cobrança de nota fiscal para algum fornecedor".
-- Numa despesa sem comprovante, o admin pede a nota ao fornecedor (e-mail pelo SMTP do painel, ou texto copiado / WhatsApp que ele mesmo
-- manda). A despesa fica "nota pedida em dd/mm" até o comprovante chegar; depois de N dias (notas.lembrete_dias) vira tarefa baixa na Home.
-- Os dados da CAMP para a nota (tomador) nascem VAZIOS: o painel pede uma vez e nunca inventa. Idempotente.
ALTER TABLE despesa ADD COLUMN nota_pedida_em TEXT;      -- UTC do último pedido; volta a NULL quando o comprovante é anexado
CREATE TABLE IF NOT EXISTS nota_pedido (                 -- cada pedido de nota fiscal (e cada "Pedir de novo")
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  despesa_id  INTEGER NOT NULL,
  canal       TEXT NOT NULL,                             -- email (SMTP do painel) | copiado | whatsapp (quem pediu mandou por conta própria)
  situacao    TEXT NOT NULL,                             -- enviado | falhou | registrado
  para        TEXT,                                      -- e-mail do fornecedor (LGPD: apagar pessoa limpa)
  whatsapp    TEXT,                                      -- só dígitos (LGPD: apagar pessoa limpa)
  assunto     TEXT,
  descricao   TEXT,                                      -- a descrição pedida para a nota (volta no Pedir de novo)
  texto       TEXT,
  pronac      INTEGER NOT NULL DEFAULT 0,                -- o texto levou a identificação do projeto PRONAC
  erro        TEXT,
  criado_por  TEXT,
  criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_nota_pedido_despesa ON nota_pedido (despesa_id);
CREATE TABLE IF NOT EXISTS fornecedor_contato (          -- memória do contato de cada fornecedor (só admin); apagar pessoa apaga a linha
  chave         TEXT PRIMARY KEY,                        -- nome da contraparte em minúsculas, espaços juntados
  contraparte   TEXT,
  email         TEXT,
  whatsapp      TEXT,
  atualizado_por TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('faturamento.razao_social', '', 'Financeiro · nota fiscal: razão social da CAMP (tomador da nota)', 0),
 ('faturamento.cnpj', '', 'Financeiro · nota fiscal: CNPJ da CAMP', 0),
 ('faturamento.inscricao_municipal', '', 'Financeiro · nota fiscal: inscrição municipal da CAMP (se houver)', 0),
 ('faturamento.endereco', '', 'Financeiro · nota fiscal: endereço da CAMP', 0),
 ('faturamento.email_notas', '', 'Financeiro · nota fiscal: e-mail da CAMP que recebe as notas (ex.: financeiro@ ou contato@)', 0),
 ('notas.lembrete_dias', '7', 'Financeiro · nota fiscal: dias depois do pedido para lembrar na Home que a nota não chegou', 0);
