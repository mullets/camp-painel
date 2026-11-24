-- 254 · CAMP-ROUANET (24/11/2026). Orçamento do projeto incentivado (Lei Rouanet) PRONAC 2613864, "Edição do livro Arquitetura Moderna
-- Paulista: Acervo Karazawa", na conta já cadastrada na 249 (id 2, Banco do Brasil, com restrição, desativada até a conta abrir).
-- Rafael: "A CAMP emitirá nota para cobrar o projeto de Rouanet do livro, porque além de prestar serviço pro projeto vamos cobrar pelo uso
-- do escritório etc." Tabelas: dados do projeto, itens do orçamento (planilha orçamentária do SALIC, valores SOLICITADOS; cópia em
-- docs/rouanet/pronac-2613864-orcamento-solicitado.csv; o valor aprovado começa igual ao solicitado e o admin atualiza), plano mensal das
-- notas da CAMP e as notas da CAMP para o projeto (planejada → emitida → paga). A despesa ganha o item do orçamento e o número da nota fiscal.
-- Nada é enviado à prefeitura (a NFS-e é emitida fora do painel). Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE, ADD COLUMN ignorado se já existe.
CREATE TABLE IF NOT EXISTS projeto_incentivado (
  conta_id         INTEGER PRIMARY KEY,                 -- financeiro_conta.id (tipo projeto_incentivado)
  pronac           TEXT,
  titulo           TEXT,
  aprovado_em      TEXT,                                -- quando o admin confirmou os valores aprovados (NULL = ainda os solicitados)
  aprovado_por     TEXT,
  inicio           TEXT,                                -- AAAA-MM: primeiro mês da execução (para o plano das notas)
  fim              TEXT,                                -- AAAA-MM: último mês da execução
  tomador_nome     TEXT,                                -- tomador da nota da CAMP (o projeto); o admin preenche
  tomador_doc      TEXT,                                -- CNPJ do tomador
  tomador_endereco TEXT,
  tomador_email    TEXT,
  alterado_por     TEXT,
  alterado_em      TEXT
);
INSERT OR IGNORE INTO projeto_incentivado (conta_id, pronac, titulo) VALUES (2, '2613864', 'Edição do livro Arquitetura Moderna Paulista: Acervo Karazawa');
CREATE TABLE IF NOT EXISTS orcamento_item (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  conta_id         INTEGER NOT NULL,
  item             INTEGER NOT NULL,                    -- número do item na planilha do SALIC
  produto          TEXT NOT NULL,
  etapa            TEXT NOT NULL,
  uf               TEXT,
  municipio        TEXT,
  descricao        TEXT NOT NULL,
  unidade          TEXT,
  dias             REAL,
  qtde             REAL,
  ocorrencias      REAL,
  valor_unitario   REAL,
  valor_solicitado REAL NOT NULL DEFAULT 0,
  valor_aprovado   REAL NOT NULL DEFAULT 0,             -- começa igual ao solicitado; o admin atualiza com a planilha aprovada
  ordem            INTEGER NOT NULL DEFAULT 0,          -- a ordem da planilha (produto → etapa → município)
  fora_planilha    INTEGER NOT NULL DEFAULT 0,          -- 1 = saiu da planilha importada depois (valor aprovado zerado; as despesas ficam)
  alterado_por     TEXT,
  alterado_em      TEXT,
  UNIQUE (conta_id, item)
);
CREATE TABLE IF NOT EXISTS orcamento_plano (            -- plano mensal das notas da CAMP: item, mês, valor (o admin define uma vez)
  conta_id INTEGER NOT NULL,
  item     INTEGER NOT NULL,
  mes      TEXT NOT NULL,                               -- AAAA-MM (competência)
  valor    REAL NOT NULL,
  PRIMARY KEY (conta_id, item, mes)
);
CREATE TABLE IF NOT EXISTS nota_camp (                  -- notas que a CAMP emite para o projeto
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  conta_id       INTEGER NOT NULL,
  competencia    TEXT NOT NULL,                         -- AAAA-MM
  itens          TEXT NOT NULL,                         -- JSON [{"item": 27, "valor": 1065.68}]
  descricao      TEXT NOT NULL,
  valor          REAL NOT NULL,
  situacao       TEXT NOT NULL DEFAULT 'planejada',     -- planejada | emitida | paga | cancelada
  nf_numero      TEXT,
  nf_data        TEXT,                                  -- AAAA-MM-DD
  nf_nome        TEXT,                                  -- PDF da nota (pasta notas_camp/ ao lado do banco)
  nf_arquivo     TEXT,
  despesa_id     INTEGER,                               -- o débito na conta do projeto (despesa.id)
  receita_mp     TEXT,                                  -- o crédito na conta da CAMP, se veio pelo Mercado Pago (mp_pagamento.mp_id)
  receita_conta  INTEGER,                               -- conta da CAMP que recebeu (financeiro_conta.id)
  pago_em        TEXT,                                  -- AAAA-MM-DD
  motivo         TEXT,                                  -- de cancelar
  criado_por     TEXT,
  criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_por   TEXT,
  alterado_em    TEXT
);
CREATE INDEX IF NOT EXISTS idx_nota_camp ON nota_camp (conta_id, competencia);
ALTER TABLE despesa ADD COLUMN orcamento_item INTEGER;   -- número do item do orçamento (conta de projeto)
ALTER TABLE despesa ADD COLUMN nf_numero TEXT;           -- número da nota fiscal (prestação de contas)
-- os dados da CAMP (razão social, CNPJ, inscrição municipal, endereço, e-mail) são os faturamento.* da 253
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('financeiro.nfse_servico', '', 'Nota fiscal da CAMP para o projeto: código do serviço (lista da LC 116 / código municipal); confirme com o contador', 0),
 ('financeiro.nfse_iss', '', 'Nota fiscal da CAMP para o projeto: alíquota do ISS (%); confirme com o contador', 0),
 ('financeiro.projeto_conta_camp', '1', 'Conta da CAMP que recebe o pagamento das notas da CAMP para o projeto (financeiro_conta.id)', 0);
INSERT OR IGNORE INTO orcamento_item (conta_id, item, produto, etapa, uf, municipio, descricao, unidade, dias, qtde, ocorrencias, valor_unitario, valor_solicitado, valor_aprovado, ordem) VALUES
 (2, 1, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Agente educativo(a): Palestrante', 'Cachê', 0, 3, 1, 800.00, 2400.00, 2400.00, 1),
 (2, 3, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Diárias: Hospedagem sem alimentação', 'Dia', 0, 3, 2, 230.00, 1380.00, 1380.00, 2),
 (2, 4, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Passagens Aéreas', 'Unidade', 0, 6, 1, 300.00, 1800.00, 1800.00, 3),
 (2, 5, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Registro Videográfico', 'Serviço', 0, 1, 1, 1500.00, 1500.00, 1500.00, 4),
 (2, 2, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'São Paulo', 'Agente educativo(a): Palestrante', 'Cachê', 0, 3, 1, 800.00, 2400.00, 2400.00, 5),
 (2, 6, 'Seminário/Simpósio/Encontro/Congresso/Palestra/Vernissage', 'Produção / Execução', 'SP', 'São Paulo', 'Registro Videográfico', 'Serviço', 0, 1, 1, 1500.00, 1500.00, 1500.00, 6),
 (2, 7, 'Livro', 'Pré-Produção / Preparação', 'SP', 'São Paulo', 'Coordenação Editorial', 'Mês', 0, 1, 5, 2600.00, 13000.00, 13000.00, 7),
 (2, 8, 'Livro', 'Pré-Produção / Preparação', 'SP', 'São Paulo', 'Digitalização', 'Unidade', 0, 100, 1, 30.00, 3000.00, 3000.00, 8),
 (2, 9, 'Livro', 'Pré-Produção / Preparação', 'SP', 'São Paulo', 'Direitos autorais', 'Verba', 0, 1, 1, 3000.00, 3000.00, 3000.00, 9),
 (2, 10, 'Livro', 'Pré-Produção / Preparação', 'SP', 'São Paulo', 'Produção de texto', 'Serviço', 0, 1, 1, 9000.00, 9000.00, 9000.00, 10),
 (2, 11, 'Livro', 'Pré-Produção / Preparação', 'SP', 'São Paulo', 'Projeto gráfico', 'Serviço', 0, 1, 1, 6000.00, 6000.00, 6000.00, 11),
 (2, 12, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Correios', 'Unidade', 0, 150, 1, 30.00, 4500.00, 4500.00, 12),
 (2, 13, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Diagramação', 'Unidade', 0, 240, 1, 25.00, 6000.00, 6000.00, 13),
 (2, 14, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Ficha Catalográfica e ISBN', 'Verba', 0, 1, 1, 400.00, 400.00, 400.00, 14),
 (2, 15, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Frete rodoviário', 'Verba', 0, 1, 1, 2000.00, 2000.00, 2000.00, 15),
 (2, 16, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Impressão', 'Unidade', 0, 2000, 1, 25.54, 51080.00, 51080.00, 16),
 (2, 17, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Obra: Livro Digital', 'Serviço', 0, 1, 1, 6500.00, 6500.00, 6500.00, 17),
 (2, 18, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Revisão de texto', 'Serviço', 0, 1, 1, 2400.00, 2400.00, 2400.00, 18),
 (2, 19, 'Livro', 'Produção / Execução', 'SP', 'São Paulo', 'Tratamento de imagens', 'Unidade', 0, 250, 1, 15.00, 3750.00, 3750.00, 19),
 (2, 20, 'Livro', 'Assessoria Contábil e Jurídica', 'SP', 'São Paulo', 'Contador(a)', 'Mês', 0, 1, 10, 400.00, 4000.00, 4000.00, 20),
 (2, 21, 'Livro', 'Recolhimentos', 'SP', 'São Paulo', 'Recolhimentos: INSS (Instituto Nacional do Seguro Social)', 'Verba', 0, 1, 1, 3400.00, 3400.00, 3400.00, 21),
 (2, 22, 'Contrapartidas Sociais', 'Produção / Execução', 'SP', 'São Paulo', 'Agente educativo(a): Arte educador(a)', 'Serviço', 0, 1, 2, 800.00, 1600.00, 1600.00, 22),
 (2, 25, 'Contrapartidas Sociais', 'Produção / Execução', 'SP', 'São Paulo', 'Material de apoio pedagógico: Cartilha', 'Unidade', 0, 100, 1, 5.00, 500.00, 500.00, 23),
 (2, 23, 'Contrapartidas Sociais', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Agente educativo(a): Arte educador(a)', 'Serviço', 0, 1, 2, 800.00, 1600.00, 1600.00, 24),
 (2, 24, 'Contrapartidas Sociais', 'Produção / Execução', 'SP', 'Presidente Prudente', 'Material de apoio pedagógico: Cartilha', 'Unidade', 0, 100, 1, 5.00, 500.00, 500.00, 25),
 (2, 26, 'Administração do Projeto', 'Custos Vinculados', 'SP', 'Presidente Prudente', 'Custos de acessibilidade, comunicação e divulgação acessíveis', 'Projeto', 1, 1, 1, 13321.00, 13321.00, 13321.00, 26),
 (2, 27, 'Administração do Projeto', 'Custos Vinculados', 'SP', 'Presidente Prudente', 'Custos de Administração', 'Projeto', 1, 1, 1, 10656.80, 10656.80, 10656.80, 27),
 (2, 28, 'Administração do Projeto', 'Captação de Recursos', 'SP', 'Presidente Prudente', 'Remuneração para captação de recursos', 'Projeto', 1, 1, 1, 6287.51, 6287.51, 6287.51, 28);
