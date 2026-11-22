-- 241 · CAMP-PROB-UX (22/11/2026). Rafael: redesenho da tela Problemas ("Central de Problemas", documento de produto 1.0).
-- Fluxo de trabalho, responsável, evidências, revisão, modelos de decisão, visões salvas, rascunho e reconhecimento (pontos) dos problemas.
-- Tudo ADITIVO: colunas novas opcionais e tabelas novas. A coluna `situacao` (aberto · em_correcao · corrigido · fechado · ignorado) continua
-- sendo a regra de quem já lê (menu, Precisa de você, publicação, relatórios); a `fase` só detalha o trabalho e é sempre compatível com ela
-- (ver backend/app/central_problemas.py, FASE_SITUACAO). Problema antigo fica com fase NULL e a fase é deduzida da situação.
-- Idempotente: ADD COLUMN repetido é ignorado por executar_script_idempotente; CREATE ... IF NOT EXISTS; INSERT OR IGNORE. Nada de UPDATE.
ALTER TABLE erro ADD COLUMN fase TEXT;                 -- novo · triagem · em_analise · aguardando_informacao · aguardando_revisao · devolvido · reaberto · resolvido · duplicado · invalido (NULL = deduzida da situação)
ALTER TABLE erro ADD COLUMN responsavel TEXT;          -- e-mail de quem está com o problema (NULL = não atribuído)
ALTER TABLE erro ADD COLUMN responsavel_em TEXT;
ALTER TABLE erro ADD COLUMN duplicado_de INTEGER;      -- problema que ficou (o duplicado guarda a referência; nada é apagado)
ALTER TABLE erro ADD COLUMN enviado_revisao_por TEXT;  -- quem mandou para revisão (a revisão por outra pessoa compara com quem aprova)
ALTER TABLE erro ADD COLUMN enviado_revisao_em TEXT;
ALTER TABLE erro ADD COLUMN revisado_por TEXT;
ALTER TABLE erro ADD COLUMN revisado_em TEXT;
ALTER TABLE erro ADD COLUMN motivo_pendencia TEXT;     -- por que está suspenso (aguardando informação) ou devolvido
ALTER TABLE erro ADD COLUMN fase_em TEXT;              -- quando a fase mudou pela última vez

-- evidências e fontes (texto, link, folha do acervo). Nunca inventadas: quem registra fica gravado.
CREATE TABLE IF NOT EXISTS erro_evidencia (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  erro_id    INTEGER NOT NULL,
  tipo       TEXT NOT NULL DEFAULT 'texto',            -- texto · link · folha
  valor      TEXT NOT NULL,
  hipotese   TEXT,                                     -- conflito de autoria: a qual hipótese esta fonte se refere (ex.: "Aflalo & Gasperini")
  autor      TEXT NOT NULL,
  criado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  origem_erro_id INTEGER                               -- veio de um duplicado juntado a este (preserva de onde veio)
);
CREATE INDEX IF NOT EXISTS idx_erro_evidencia_erro ON erro_evidencia(erro_id);

-- modelos de decisão por tipo (categoria), editáveis pela equipe
CREATE TABLE IF NOT EXISTS erro_modelo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  categoria  TEXT NOT NULL,
  titulo     TEXT NOT NULL,
  texto      TEXT NOT NULL,
  ativo      INTEGER NOT NULL DEFAULT 1,
  criado_por TEXT,
  atualizado_por TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (categoria, titulo)
);
INSERT OR IGNORE INTO erro_modelo (categoria, titulo, texto, criado_por) VALUES
  ('orientacao', 'Folha girada', 'A folha foi girada no painel e agora está em pé.', 'painel'),
  ('espelhado', 'Folha espelhada', 'A folha foi espelhada no painel e o texto agora se lê normalmente.', 'painel'),
  ('duplicata', 'Marcada como cópia', 'A folha foi marcada como cópia da original; só a original vai ao site.', 'painel'),
  ('duplicata', 'Não é repetida', 'Conferido lado a lado: as folhas são diferentes.', 'painel'),
  ('projeto_errado', 'Movida para o projeto certo', 'A folha foi movida para o projeto certo (mesmo fundo).', 'painel'),
  ('autoria_divergente', 'Autoria registrada com fonte', 'Autoria registrada conforme a fonte anexada.', 'painel'),
  ('metadado', 'Dado corrigido', 'O dado foi corrigido conforme o documento.', 'painel'),
  ('credito', 'Crédito corrigido com fonte', 'O crédito foi corrigido conforme a fonte anexada.', 'painel');

-- visões salvas (filtros recorrentes), por pessoa
CREATE TABLE IF NOT EXISTS erro_visao (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL,
  nome       TEXT NOT NULL,
  params     TEXT NOT NULL,                            -- a parte de filtros do endereço (aba=...&q=...)
  criado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (usuario_id, nome)
);

-- rascunho do parecer (salvo sozinho enquanto a pessoa escreve), por pessoa e problema
CREATE TABLE IF NOT EXISTS erro_rascunho (
  erro_id    INTEGER NOT NULL,
  usuario_id INTEGER NOT NULL,
  texto      TEXT NOT NULL,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (erro_id, usuario_id)
);

-- reconhecimento: pontos SÓ de resolução validada (pesos por complexidade); reabrir estorna (revertido_em). Nunca vale para avaliar desempenho.
CREATE TABLE IF NOT EXISTS erro_ponto (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  erro_id     INTEGER NOT NULL,
  pessoa      TEXT NOT NULL,                           -- e-mail
  pontos      INTEGER NOT NULL,
  motivo      TEXT NOT NULL,                           -- resolucao · revisao
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  revertido_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_erro_ponto_pessoa ON erro_ponto(pessoa);
CREATE INDEX IF NOT EXISTS idx_erro_ponto_erro ON erro_ponto(erro_id);

-- preferência de cada pessoa: esconder o próprio progresso e conquistas
CREATE TABLE IF NOT EXISTS erro_progresso_pref (
  usuario_id INTEGER PRIMARY KEY,
  ocultar    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_erro_situacao ON erro(situacao);

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('problemas.revisao_outra_pessoa', '0', 'Problemas: tipos sensíveis (autoria, crédito, folha de outro projeto) só são resolvidos depois da revisão de OUTRA pessoa. 0 = desligado (padrão), 1 = ligado', 0),
  ('problemas.tipos_revisao', 'autoria_divergente,credito,projeto_errado', 'Problemas: tipos que pedem revisão por outra pessoa quando ela está ligada (separados por vírgula)', 0),
  ('problemas.ranking_equipe', '0', 'Problemas: mostrar o ranking da equipe no mês. 0 = desligado (padrão). Nunca usar para avaliar desempenho de ninguém', 0),
  ('problemas.meta_semana', '0', 'Problemas: meta coletiva de resoluções validadas por semana (0 = sem meta; a tela só mostra quantas foram resolvidas)', 0);
