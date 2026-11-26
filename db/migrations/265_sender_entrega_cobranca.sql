-- 265 · CAMP-ENTREGA (26/11/2026). Rafael (quiz da revisão de usabilidade): "Layout próprio no Sender" para o e-mail de entrega com cobrança.
-- Vazio (padrão): o e-mail com cobrança sai como antes, pelo TR09 (sender.campanha_entrega) com a cobrança dentro de {{mensagem}}.
-- Preenchido: o e-mail com cobrança sai por este modelo, com {{cobranca}}, {{valor}}, {{link_pagamento}}, {{justificativa}}, {{liberacao}}.
-- Idempotente: INSERT OR IGNORE nunca troca um valor já preenchido.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('sender.campanha_entrega_cobranca', '', 'ID do e-mail transacional do Sender.net para a entrega COM cobrança (layout próprio; vazio = usa o TR09 com a cobrança no texto)', 0);
