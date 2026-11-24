-- 251 · CAMP-FIN inteligência (24/11/2026). Rafael: "Capriche na inteligência do sistema". Regras "Sempre classificar X como Y" (sugeridas
-- quando a mesma escolha se repete 3 vezes; nada é aplicado sem um clique), leitura de comprovante por um leitor plugável (DESLIGADA por
-- padrão; o painel não tem cliente de IA hoje), alertas e projeção. Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS financeiro_regra (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo       TEXT NOT NULL,                      -- despesa | receita
  campo      TEXT NOT NULL DEFAULT 'contraparte',-- contraparte (nome normalizado) | cnpj | palavra
  padrao     TEXT NOT NULL,
  alvo       TEXT NOT NULL,                      -- categoria (despesa) ou natureza (receita)
  ativa      INTEGER NOT NULL DEFAULT 1,
  criado_por TEXT,
  criado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (tipo, campo, padrao)
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('financeiro.leitura_comprovante', '0', 'Financeiro: ler a foto/PDF do comprovante com um leitor automático (1 liga; o arquivo é enviado ao leitor configurado). Padrão 0', 0),
 ('financeiro.leitor', '', 'Financeiro: nome do leitor de comprovantes (vazio = nenhum; o painel não tem cliente de IA hoje)', 0),
 ('financeiro.alerta_sem_comprovante_dias', '15', 'Financeiro: avisar despesas sem comprovante há mais de N dias', 0),
 ('financeiro.orcamento_projetos', '{}', 'Financeiro: orçamento por conta de projeto (JSON {conta_id: {rubrica: valor}}); vazio até o orçamento aprovado', 0);
