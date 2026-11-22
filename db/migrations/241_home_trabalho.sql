-- 241 · CAMP-HOME-UX (22/11/2026, documento do Rafael "Redesenho do painel inicial / Precisa de você").
-- (1) Responsável de cada tarefa da fila "O que fazer agora": o painel não tinha dono de tarefa. A chave é a mesma do "Agora não"
--     (decisao:3, lote:12, erro:5, pedido:2…). Quem atribui fica no Histórico (evento tarefa_atribuida / tarefa_devolvida).
-- (2) Progresso coletivo e conquistas (piloto): a meta da semana e a tabela de pontos ficam em configuração (admin ajusta);
--     o quadro da equipe nasce DESLIGADO (jogo.ranking_equipe = 0): nada de ranking individual público por padrão.
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS tarefa_responsavel (
  tarefa_id      TEXT PRIMARY KEY,                       -- a chave da linha na fila (a mesma do "Agora não")
  usuario_id     INTEGER NOT NULL REFERENCES usuario(id),
  atribuido_por  TEXT,                                   -- e-mail de quem atribuiu (ou pegou para si)
  atribuido_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tarefa_responsavel_usuario ON tarefa_responsavel(usuario_id);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('meta.semana', '100', 'Meta coletiva da semana na Home, em pontos validados (admin muda na própria Home)', 0),
 ('jogo.ligado', '1', 'Progresso da semana, nível e conquistas na Home (1 = mostra; 0 = esconde para todos)', 0),
 ('jogo.pontos', '{"folha_conferida":1,"lote_aprovado":10,"decisao_resolvida":5,"problema_resolvido":20,"problema_critico_resolvido":30}', 'Pontos por ação validada (JSON). Só contam ações que continuam valendo: desfez, o ponto some', 0),
 ('jogo.ranking_equipe', '0', 'Quadro da equipe com os pontos da semana por pessoa (0 = desligado, o padrão; 1 = mostra a quem edita)', 0);
