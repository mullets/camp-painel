-- Cartão 151: resumo do dia por e-mail às 18h (opcional, DESLIGADO por padrão).
-- Uma linha por dia em resumo_diario_envio: é o que impede mandar duas vezes no mesmo dia.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('alertas.resumo_diario', '0', 'Resumo do dia por e-mail às 18h: folhas importadas, revisadas e publicadas, pedidos novos e problemas abertos (1 liga, 0 desliga)', 0),
 ('alertas.resumo_email', '', 'Quem recebe o resumo do dia (um endereço). Vazio: vai para o primeiro endereço de avisos.email', 0);
CREATE TABLE IF NOT EXISTS resumo_diario_envio (
  dia         TEXT PRIMARY KEY,                -- AAAA-MM-DD, no horário do servidor
  para        TEXT,
  ok          INTEGER NOT NULL DEFAULT 0,
  erro        TEXT,
  conteudo    TEXT,                            -- os números enviados (JSON)
  enviado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
