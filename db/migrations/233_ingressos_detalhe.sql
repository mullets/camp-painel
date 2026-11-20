-- 233 · CAMP-INGRESSOS detalhe (20/11/2026, Rafael: "Na parte de ingressos, pedidos: saber quem pagou meia, quem é Amigo etc. E abrir
-- a data para listar as pessoas, e se precisar reenviar o ingresso ou a cobrança"). Contrato 1.22 (site plugin 1.31.0), tudo OPCIONAL:
-- o site antigo não manda estes campos e o painel calcula os tipos com pessoas/meias/desconto (meias = contrato 1.21).
-- O histórico dos reenvios pelo painel fica na tabela evento (entidade 'ingresso', sem nome nem e-mail do comprador).
-- Idempotente: ALTER TABLE ... ADD COLUMN de coluna que já existe é pulado pelo aplicador de migrações.
ALTER TABLE ingresso ADD COLUMN meias INTEGER NOT NULL DEFAULT 0;   -- quantos dos `pessoas` são meia-entrada (1.21)
ALTER TABLE ingresso ADD COLUMN tipos TEXT;                          -- JSON [{tipo, nome, qtd, valor, pct?, categoria?}] vindo do site (1.22)
ALTER TABLE ingresso ADD COLUMN link_pagamento TEXT;                 -- link do Mercado Pago ainda aberto (só compra não paga; 1.22)
ALTER TABLE ingresso ADD COLUMN link_pagamento_ate TEXT;             -- UTC, até quando o link vale
ALTER TABLE ingresso ADD COLUMN historico TEXT;                      -- JSON [texto] (log do ingresso no site; sem dados do comprador)
ALTER TABLE ingresso ADD COLUMN aviso_equipe TEXT;                   -- JSON [{quando, momento, para, ok, erro}]: avisos à equipe por wp_mail (sem Sender; 1.22)
