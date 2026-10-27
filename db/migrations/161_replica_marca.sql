-- UX-02: a data da última cópia VÁLIDA do acervo (a marca da sentinela lida com sucesso na réplica), para o bloco "Preservação"
-- continuar dizendo quando foi a última cópia boa mesmo se a sentinela sumir. Uma linha só (id=1). Nada aqui configura a réplica:
-- o destino (replica.raiz) e a rotina de cópia continuam pendentes de decisão do Rafael.
CREATE TABLE IF NOT EXISTS replica_marca (
  id          INTEGER PRIMARY KEY CHECK (id = 1),
  gravado_em  TEXT,
  versao      TEXT,
  visto_em    TEXT
);
-- Alerta de espaço por dias até encher (UX-02): menos de 30 dias = atenção, menos de 10 dias = crítico. INSERT OR IGNORE: um valor já
-- escolhido nas Configurações fica como está.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('qnap.dias_aviso',   '30', 'Atenção quando, no ritmo da última semana, o QNAP enche em menos que estes dias', 0),
 ('qnap.dias_critico', '10', 'Crítico quando, no ritmo da última semana, o QNAP enche em menos que estes dias', 0);
