-- Decisões 01/10/2026: Heck -> F031 CHH, Major Botkowski -> F032 MBO, "João Valente / Sandra Valente" (site) -> F012
INSERT OR IGNORE INTO fundo (codigo, sigla, titulo, credito_padrao) VALUES
 ('F031','CHH','Carlos Henrique Heck','Acervo Carlos Henrique Heck/CAMP - Casa da Arquitetura Moderna Paulista'),
 ('F032','MBO','Major Botkowski','Acervo Major Botkowski/CAMP - Casa da Arquitetura Moderna Paulista');
INSERT OR IGNORE INTO agente (tipo, forma_autorizada) VALUES ('pessoa','Carlos Henrique Heck'),('pessoa','Major Botkowski');
INSERT OR IGNORE INTO agente_forma_variante (agente_id, forma, contexto)
  SELECT id, 'CARLOS HENRIQUE HECK', 'carimbo' FROM agente WHERE forma_autorizada='Carlos Henrique Heck';
INSERT OR IGNORE INTO agente_forma_variante (agente_id, forma, contexto)
  SELECT id, 'MAJOR BOTKOWSKI', 'carimbo' FROM agente WHERE forma_autorizada='Major Botkowski';
INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel)
  SELECT 'F031', id, 'produtor' FROM agente WHERE forma_autorizada='Carlos Henrique Heck';
INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel)
  SELECT 'F032', id, 'produtor' FROM agente WHERE forma_autorizada='Major Botkowski';
UPDATE fundo_termo_site SET fundo_codigo='F031', observacao='decidido 01/10/2026' WHERE nome_site='Carlos Henrique Heck';
UPDATE fundo_termo_site SET fundo_codigo='F032', observacao='decidido 01/10/2026' WHERE nome_site='Major Botkowski';
UPDATE fundo_termo_site SET fundo_codigo='F012', observacao='site mantém um termo só; F027 reservado para Sandra Valente se separarem' WHERE nome_site='João Valente / Sandra Valente';
INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo','F031','criado','decisao-rafael','Carlos Henrique Heck · CHH'),('fundo','F032','criado','decisao-rafael','Major Botkowski · MBO');

-- definições de metadados das coleções (nome -> id), para o painel escrever no Tainacan
CREATE TABLE IF NOT EXISTS wp_metadado (
  id INTEGER PRIMARY KEY, colecao_id INTEGER, nome TEXT, tipo TEXT, taxonomia_id INTEGER, json TEXT,
  visto_em TEXT NOT NULL DEFAULT (datetime('now'))
);
