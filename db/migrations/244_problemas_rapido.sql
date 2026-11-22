-- 244 · CAMP-PROB-RAPIDO (22/11/2026). Rafael: "Decisões simples e rápidas podem ser clicks aí mesmo para resolver, não?"
-- Os modelos de decisão que as ações rápidas da tela Problemas usam como conclusão (editáveis em Problemas › Mais ⋯ › Modelos de decisão;
-- se alguém desativar um, a ação usa o texto padrão do código). Os de "Movida para o projeto certo", "Marcada como cópia", "Não é repetida"
-- e "Dado corrigido" já vieram na 242. Idempotente: INSERT OR IGNORE (UNIQUE categoria+título); nada de UPDATE.
INSERT OR IGNORE INTO erro_modelo (categoria, titulo, texto, criado_por) VALUES
  ('projeto_errado', 'É deste projeto', 'Conferido: a folha é deste projeto; o aviso de projeto divergente saiu da folha.', 'painel');
