-- CAMP Acervos — modelo de dados do painel de administração
-- SQLite (compatível com PostgreSQL trocando AUTOINCREMENT por GENERATED/serial)
--
-- Princípios adotados do AtoM / normas do ICA:
--   ISAD(G) / NOBRADE  -> hierarquia fundo > série > dossiê (projeto) > item,
--                          com as 7 áreas de descrição mapeadas nos campos
--   ISAAR(CPF)         -> registros de autoridade (agente) separados do fundo,
--                          com formas variantes, datas de existência e relações
--   Proveniência       -> ligação fundo<->agente com papel e período
--   Códigos imutáveis  -> nunca sobrescrever; recodificar cria redirecionamento
--   Só fatos           -> campos de história/biografia exigem fonte

PRAGMA foreign_keys = ON;

-- =====================================================================
-- 1. AUTORIDADE: fundos, séries, agentes
-- =====================================================================

-- ISAD(G) nível "fundo". codigo é a chave natural e não muda nunca.
CREATE TABLE fundo (
  codigo              TEXT PRIMARY KEY CHECK (codigo GLOB 'F[0-9][0-9][0-9]'),
  sigla               TEXT UNIQUE CHECK (sigla IS NULL OR length(sigla) = 3),   -- vai para o nome dos arquivos
  titulo              TEXT NOT NULL,                       -- 3.1.2 Título
  data_inicio         INTEGER,                             -- 3.1.3 Datas extremas (ano)
  data_fim            INTEGER,
  nivel_descricao     TEXT NOT NULL DEFAULT 'fundo',       -- 3.1.4 (fundo | coleção)
  dimensao_suporte    TEXT,                                -- 3.1.5 ex. "1.240 pranchas, 3 caixas"
  historia_arquivistica TEXT,                              -- 3.2.3 só fatos; exige fonte
  procedencia         TEXT,                                -- 3.2.4 como/quando chegou à CAMP
  condicoes_acesso    TEXT,                                -- 3.4.1
  condicoes_reproducao TEXT,                               -- 3.4.2 licença / crédito padrão
  fonte_historia      TEXT,                                -- referência da história acima
  credito_padrao      TEXT NOT NULL DEFAULT 'Acervo {agente}/CAMP - Casa da Arquitetura Moderna Paulista',
  status_site         TEXT NOT NULL DEFAULT 'nao_publicado'
                      CHECK (status_site IN ('nao_publicado','rascunho','no_ar','fora_do_ar')),
  motivo_fora_do_ar   TEXT,                                -- ex. pedido da família
  tainacan_term_id    INTEGER,                             -- termo na taxonomia de fundos
  tainacan_collection_id INTEGER,                          -- coleção, se uma por fundo
  wp_page_id          INTEGER,                             -- página do fundo no site
  ativo               INTEGER NOT NULL DEFAULT 1,
  criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Séries documentais (vocabulário fechado)
CREATE TABLE serie (
  codigo   TEXT PRIMARY KEY CHECK (codigo GLOB 'S[0-9][0-9]'),
  nome     TEXT NOT NULL,
  pasta    TEXT NOT NULL   -- pasta padrão dentro do projeto
);
INSERT INTO serie VALUES
 ('S01','Desenhos e pranchas','06 - Desenhos e pranchas'),
 ('S02','Documentos textuais','07 - Documentos textuais'),
 ('S03','Fotografias','03 - Fotografias'),
 ('S04','Negativos','04 - Negativos'),
 ('S05','Slides','05 - Slides'),
 ('S06','Materiais e especificações','08 - Materiais e especificações');

-- ISAAR(CPF): registro de autoridade. Pessoa, escritório (entidade coletiva) ou família.
CREATE TABLE agente (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo                TEXT NOT NULL CHECK (tipo IN ('pessoa','entidade_coletiva','familia')),
  forma_autorizada    TEXT NOT NULL UNIQUE,                -- 5.1.2 nome como aparece no site
  existencia_inicio   INTEGER,                             -- 5.2.1 datas de existência (ano)
  existencia_fim      INTEGER,
  historia            TEXT,                                -- 5.2.2 só fatos verificáveis
  fonte_historia      TEXT,                                -- 5.4.3 fontes; obrigatória se historia não for nula
  lugares             TEXT,                                -- 5.2.3 cidades de atuação
  status_site         TEXT NOT NULL DEFAULT 'nao_publicado'
                      CHECK (status_site IN ('nao_publicado','rascunho','no_ar','fora_do_ar')),
  tainacan_term_id    INTEGER,                             -- termo na taxonomia de arquitetos
  criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (historia IS NULL OR fonte_historia IS NOT NULL)
);

-- 5.1.5 Outras formas do nome: as grafias de carimbo que o CAMP Vision reconhece
CREATE TABLE agente_forma_variante (
  agente_id  INTEGER NOT NULL REFERENCES agente(id) ON DELETE CASCADE,
  forma      TEXT NOT NULL,                                -- ex. "J. BARRETTO ARQ. ASSOC."
  contexto   TEXT,                                         -- ex. "carimbo 1982-1990"
  PRIMARY KEY (agente_id, forma)
);

-- 5.3 Relações entre agentes (sócio, sucessor, colaborador...)
CREATE TABLE agente_relacao (
  agente_id      INTEGER NOT NULL REFERENCES agente(id) ON DELETE CASCADE,
  relacionado_id INTEGER NOT NULL REFERENCES agente(id) ON DELETE CASCADE,
  tipo           TEXT NOT NULL CHECK (tipo IN ('socio','antecessor','sucessor','colaborador','familiar','empregador')),
  inicio         INTEGER,
  fim            INTEGER,
  descricao      TEXT,                                     -- ex. "Segnini Barretto Arquitetos S/C"
  PRIMARY KEY (agente_id, relacionado_id, tipo)
);

-- Proveniência: quem produziu / é titular de cada fundo, e quando.
-- Um agente em vários fundos (Joaquim Barretto em F002 e F014) é um só registro.
CREATE TABLE fundo_agente (
  fundo_codigo TEXT NOT NULL REFERENCES fundo(codigo),
  agente_id    INTEGER NOT NULL REFERENCES agente(id),
  papel        TEXT NOT NULL CHECK (papel IN ('produtor','titular','colaborador','custodiador')),
  inicio       INTEGER,
  fim          INTEGER,
  PRIMARY KEY (fundo_codigo, agente_id, papel)
);

-- =====================================================================
-- 2. DESCRIÇÃO: projetos (dossiês) e itens
-- =====================================================================

-- Número P reservado é irreversível, mesmo que o projeto seja descartado.
CREATE TABLE numero_p (
  fundo_codigo TEXT NOT NULL REFERENCES fundo(codigo),
  numero       INTEGER NOT NULL,
  reservado_em TEXT NOT NULL DEFAULT (datetime('now')),
  reservado_por INTEGER,                                   -- usuario.id
  PRIMARY KEY (fundo_codigo, numero)
);

-- ISAD(G) nível "dossiê": o projeto arquitetônico. codigo = F0xx-P000x
CREATE TABLE projeto (
  codigo              TEXT PRIMARY KEY,                    -- F014-P0004
  fundo_codigo        TEXT NOT NULL REFERENCES fundo(codigo),
  numero              INTEGER NOT NULL,
  titulo              TEXT NOT NULL,                       -- 3.1.2 nome do projeto
  ano                 INTEGER NOT NULL DEFAULT 0,          -- 3.1.3 ano do PROJETO (0 = sem data)
  ano_fim             INTEGER,                             -- para 1982–83
  cidade              TEXT,
  endereco_obra       TEXT,
  identificacao_original TEXT,                           -- referência física/legada: CX039, Tubo 07, Pasta 03...
  cliente             TEXT,                                -- só se lido no documento
  tipologia           TEXT,                                -- residencial, institucional...
  ambito_conteudo     TEXT,                                -- 3.3.1 resumo do que há no dossiê
  pasta_qnap          TEXT,                                -- /mnt/qnap/acervos/F014 - JBR/P0004 - ...
  contagem_esperada   INTEGER,                             -- folhas contadas fisicamente
  lote_teste          INTEGER NOT NULL DEFAULT 0,          -- não entra em inventário nem site
  autorizado_site     INTEGER NOT NULL DEFAULT 0,          -- portão 1 (flag manual)
  status_site         TEXT NOT NULL DEFAULT 'nao_publicado'
                      CHECK (status_site IN ('nao_publicado','bloqueado','em_revisao','rascunho','no_ar','fora_do_ar')),
  wp_page_id          INTEGER,                             -- página do dossiê
  tainacan_item_id    INTEGER,
  criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (fundo_codigo, numero) REFERENCES numero_p(fundo_codigo, numero),
  UNIQUE (fundo_codigo, numero)
);

-- Vocabulário de tipo de documento (o mesmo do CAMP Vision)
CREATE TABLE tipo_documento (
  nome TEXT PRIMARY KEY
);
INSERT INTO tipo_documento VALUES ('Planta'),('Corte'),('Elevação'),('Detalhe'),('Estrutura'),
 ('Croqui'),('Perspectiva'),('Levantamento'),('Mobiliário'),('Documento'),('Fotografia'),('Negativo'),('Slide');

-- ISAD(G) nível "item": a prancha, foto ou documento. codigo = F0xx-P000x-AAAA-S0x-DNNNNN
CREATE TABLE item (
  codigo              TEXT PRIMARY KEY,
  projeto_codigo      TEXT NOT NULL REFERENCES projeto(codigo),
  serie_codigo        TEXT NOT NULL REFERENCES serie(codigo),
  sequencial          INTEGER NOT NULL,                    -- D, contínuo dentro do projeto
  titulo              TEXT,                                -- título do carimbo
  tipo_documento      TEXT REFERENCES tipo_documento(nome),
  folha               TEXT,                                -- "03/12"
  escala              TEXT,
  ano_folha           INTEGER,                             -- data da folha (pode divergir do projeto)
  dimensoes           TEXT,                                -- 3.1.5 ex. "A0, 841x1189 mm"
  suporte             TEXT,                                -- papel vegetal, cópia heliográfica...
  -- leituras brutas do carimbo, separadas do valor consolidado (lição do CV2)
  projeto_carimbo     TEXT,
  escritorio_carimbo  TEXT,
  autor_carimbo       TEXT,
  -- arquivos
  arquivo_tif         TEXT,
  arquivo_jpg         TEXT,
  md5                 TEXT,
  phash               TEXT,
  rotacao_aplicada    INTEGER NOT NULL DEFAULT 0,          -- -90 / 90 / 180
  espelhado           INTEGER NOT NULL DEFAULT 0,          -- digitalizado pelo verso
  -- controle de qualidade
  duplicata_de        TEXT REFERENCES item(codigo),
  tipo_duplicata      TEXT CHECK (tipo_duplicata IN (NULL,'exata','perceptual','mesma_folha')),
  autoria_divergente  INTEGER NOT NULL DEFAULT 0,          -- bloqueia publicação
  outlier_campos      TEXT,                                -- JSON: ["ano","endereco"]
  -- publicação
  credito             TEXT,                                -- gerado do credito_padrao do fundo
  status_site         TEXT NOT NULL DEFAULT 'nao_publicado'
                      CHECK (status_site IN ('nao_publicado','bloqueado','rascunho','no_ar','fora_do_ar')),
  tainacan_item_id    INTEGER,
  origem              TEXT NOT NULL DEFAULT 'campvision' CHECK (origem IN ('campvision','manual','importado')),
  criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (projeto_codigo, sequencial)
);

-- Autoria por item (autor, fotógrafo, desenhista). Fonte humana obrigatória para fotógrafo.
CREATE TABLE item_agente (
  item_codigo TEXT NOT NULL REFERENCES item(codigo) ON DELETE CASCADE,
  agente_id   INTEGER NOT NULL REFERENCES agente(id),
  papel       TEXT NOT NULL CHECK (papel IN ('autor','fotografo','desenhista','coautor')),
  fonte       TEXT,                                        -- "carimbo" | "informado por ..." 
  PRIMARY KEY (item_codigo, agente_id, papel)
);

-- Recodificação: nunca apaga o código antigo; gera 301 no site.
CREATE TABLE redirecionamento (
  codigo_antigo TEXT PRIMARY KEY,
  codigo_novo   TEXT NOT NULL,
  entidade      TEXT NOT NULL CHECK (entidade IN ('fundo','projeto','item')),
  motivo        TEXT NOT NULL,
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  aplicado_no_site INTEGER NOT NULL DEFAULT 0
);

-- =====================================================================
-- 3. OPERAÇÃO: filas, pedidos, erros, etiquetas
-- =====================================================================

CREATE TABLE usuario (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  nome   TEXT NOT NULL,
  email  TEXT UNIQUE,
  papel  TEXT NOT NULL CHECK (papel IN ('admin','operador','leitura')),
  ativo  INTEGER NOT NULL DEFAULT 1
);

-- Lista para o CAMP Vision processar. Espelha status.json do QNAP.
CREATE TABLE lista_processamento (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  nome              TEXT NOT NULL,
  projeto_codigo    TEXT NOT NULL REFERENCES projeto(codigo),
  pasta_qnap        TEXT NOT NULL,
  folhas_esperadas  INTEGER,
  folhas_encontradas INTEGER,
  etapa             TEXT NOT NULL DEFAULT 'enviado'
                    CHECK (etapa IN ('enviado','processando','revisao','rascunho','publicado','erro')),
  status_json       TEXT,                                  -- último valor lido do QNAP
  resultado         TEXT,                                  -- JSON: caminho do CSV, contatos.jpg, métricas
  criado_por        INTEGER REFERENCES usuario(id),
  criado_em         TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pedido de material em alta resolução
CREATE TABLE solicitacao (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitante     TEXT NOT NULL,
  email           TEXT,
  instituicao     TEXT,
  finalidade      TEXT NOT NULL CHECK (finalidade IN ('publicacao','pesquisa','editorial','familia','exposicao','outro')),
  detalhe         TEXT,
  origem          TEXT NOT NULL DEFAULT 'site' CHECK (origem IN ('site','email','presencial')),
  situacao        TEXT NOT NULL DEFAULT 'aguarda_resposta'
                  CHECK (situacao IN ('aguarda_resposta','aguarda_orcamento','aguarda_credito','em_preparacao','entregue','recusada')),
  condicoes_uso   TEXT,                                    -- crédito exigido, prazo, licença
  valor           REAL,
  recebida_em     TEXT NOT NULL DEFAULT (datetime('now')),
  entregue_em     TEXT,
  responsavel     INTEGER REFERENCES usuario(id)
);

CREATE TABLE solicitacao_item (
  solicitacao_id INTEGER NOT NULL REFERENCES solicitacao(id) ON DELETE CASCADE,
  codigo         TEXT NOT NULL,                            -- item ou projeto
  formato        TEXT NOT NULL CHECK (formato IN ('tif','jpg_3000','jpg_original','pdf')),
  entregue       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (solicitacao_id, codigo, formato)
);

-- Erro / problema relatado no material
CREATE TABLE erro (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  gravidade     TEXT NOT NULL CHECK (gravidade IN ('bloqueia','corrigir','aviso')),
  categoria     TEXT NOT NULL CHECK (categoria IN ('autoria_divergente','projeto_errado','duplicata','orientacao',
                                                    'espelhado','codigo','metadado','credito','arquivo_corrompido','outro')),
  origem        TEXT NOT NULL CHECK (origem IN ('campvision','revisao','site','operador')),
  codigo        TEXT NOT NULL,                             -- fundo, projeto ou item afetado
  descricao     TEXT NOT NULL,
  situacao      TEXT NOT NULL DEFAULT 'aberto' CHECK (situacao IN ('aberto','em_correcao','corrigido','fechado','ignorado')),
  resolucao     TEXT,
  relatado_por  TEXT,                                      -- nome/e-mail se veio do site
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  resolvido_em  TEXT
);

-- Impressões de etiqueta (rastreabilidade do que já está etiquetado)
CREATE TABLE etiqueta_impressao (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo        TEXT NOT NULL CHECK (tipo IN ('projeto','documento','caixa','tubo','fundo')),
  codigo      TEXT NOT NULL,
  quantidade  INTEGER NOT NULL DEFAULT 1,
  formato_mm  TEXT NOT NULL DEFAULT '100x50',
  impressa_em TEXT NOT NULL DEFAULT (datetime('now')),
  usuario_id  INTEGER REFERENCES usuario(id)
);

-- Localização física (caixa, gaveta, tubo) — opcional, útil com as etiquetas
CREATE TABLE localizacao_fisica (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  fundo_codigo TEXT REFERENCES fundo(codigo),
  tipo        TEXT NOT NULL CHECK (tipo IN ('caixa','gaveta','tubo','mapoteca','estante')),
  identificador TEXT NOT NULL,                             -- "CX07", "MAP-02-G3"
  descricao   TEXT
);
CREATE TABLE item_localizacao (
  item_codigo    TEXT NOT NULL REFERENCES item(codigo),
  localizacao_id INTEGER NOT NULL REFERENCES localizacao_fisica(id),
  PRIMARY KEY (item_codigo)
);

-- =====================================================================
-- 4. HISTÓRICO E SINCRONIZAÇÃO
-- =====================================================================

-- Todo evento relevante em qualquer entidade (alimenta o "Histórico" do painel lateral)
CREATE TABLE evento (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade    TEXT NOT NULL,                               -- fundo | projeto | item | lista | solicitacao | erro | agente
  codigo      TEXT NOT NULL,                               -- chave da entidade
  tipo        TEXT NOT NULL,                               -- criado | editado | etapa | publicado | sincronizado | ...
  ator        TEXT NOT NULL,                               -- usuário ou 'campvision' | 'qnap' | 'site'
  detalhe     TEXT,                                        -- JSON com antes/depois
  quando      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX evento_codigo ON evento(entidade, codigo, quando);

-- Divergências encontradas entre painel e site (checagem periódica)
CREATE TABLE divergencia_site (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade    TEXT NOT NULL,
  codigo      TEXT NOT NULL,
  campo       TEXT NOT NULL,
  valor_painel TEXT,
  valor_site   TEXT,
  detectada_em TEXT NOT NULL DEFAULT (datetime('now')),
  resolvida    INTEGER NOT NULL DEFAULT 0
);

-- Heartbeat dos apps das estações de captura.
CREATE TABLE estacao_heartbeat (
  estacao_id       TEXT PRIMARY KEY,
  tipo_estacao     TEXT NOT NULL,
  app              TEXT NOT NULL,
  versao           TEXT,
  hostname         TEXT,
  ip_local         TEXT,
  estado           TEXT NOT NULL DEFAULT 'ocioso',
  fundo_codigo     TEXT,
  projeto_codigo   TEXT,
  operador         TEXT,
  ultimo_erro      TEXT,
  recebido_de_ip   TEXT,
  atualizado_em    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_estacao_heartbeat_atualizado ON estacao_heartbeat(atualizado_em);

-- =====================================================================
-- 5. VISÕES DE APOIO
-- =====================================================================

-- Próximo código de fundo livre
CREATE VIEW v_proximo_fundo AS
  SELECT printf('F%03d', COALESCE(MAX(CAST(substr(codigo,2) AS INTEGER)),0)+1) AS codigo FROM fundo;

-- Próximo P livre por fundo (respeita reservas nunca usadas)
CREATE VIEW v_proximo_p AS
  SELECT f.codigo AS fundo_codigo,
         printf('P%04d', COALESCE(MAX(n.numero),0)+1) AS proximo
  FROM fundo f LEFT JOIN numero_p n ON n.fundo_codigo = f.codigo
  GROUP BY f.codigo;

-- Projetos que não podem ir ao site e por quê
CREATE VIEW v_bloqueios_publicacao AS
  SELECT p.codigo,
         (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo AND i.autoria_divergente=1) AS itens_autoria_divergente,
         (SELECT COUNT(*) FROM erro e WHERE (e.codigo=p.codigo OR e.codigo LIKE p.codigo || '-%')
             AND e.situacao IN ('aberto','em_correcao') AND e.gravidade='bloqueia') AS erros_bloqueantes,
         CASE WHEN p.autorizado_site = 0 THEN 1 ELSE 0 END AS nao_autorizado
  FROM projeto p;

-- Export fundos.json para a estação Contex (nome + prefixo)
CREATE VIEW v_fundos_json AS
  SELECT json_group_array(json_object('codigo', codigo, 'prefixo', sigla, 'nome', titulo)) AS fundos
  FROM fundo WHERE ativo = 1 AND sigla IS NOT NULL;
