-- 263 · CAMP-FICHA (25/11/2026). Decisão do Rafael: "falta elétrica, hidráulica, paisagismo.." (e fundação, que ele já tinha pedido como
-- separação). Entram os tipos de documento "Elétrica", "Hidráulica", "Paisagismo" e "Fundação". No agrupamento por disciplina contam
-- como Instalações elétricas, Instalações hidráulicas, Paisagismo e Fundações. Só acrescenta ao vocabulário (idempotente): nenhuma folha
-- muda sozinha; na conferência o painel SUGERE o tipo pelo tipo lido/título do CAMP Vision ("Usar sugestão"), nunca aplica.
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Elétrica');
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Hidráulica');
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Paisagismo');
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Fundação');
