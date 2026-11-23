-- 246 · CAMP-BLOQUEIO (23/11/2026). Rafael, numa folha "bloqueada" com a pílula "ficha de documentação (não é obra)": "não entendi por que tá bloqueado".
-- Os modelos de decisão dos botões da própria folha ("É prancha do projeto · liberar", "É ficha · deixar fora", "Pode ir ao site · liberar",
-- "Deixar fora do site"), editáveis em Problemas › Mais ⋯ › Modelos de decisão; se alguém desativar um, o botão usa o texto padrão do código.
-- Idempotente: INSERT OR IGNORE (UNIQUE categoria+título); nada de UPDATE.
INSERT OR IGNORE INTO erro_modelo (categoria, titulo, texto, criado_por) VALUES
  ('outro', 'É prancha do projeto', 'Conferido na folha: é prancha do projeto, não ficha de documentação. O bloqueio do CAMP Vision saiu.', 'painel'),
  ('outro', 'É ficha: fica fora do site', 'Conferido na folha: é ficha de documentação, não prancha do projeto. Fica no painel e não vai ao site.', 'painel'),
  ('outro', 'Pode ir ao site', 'Conferido na folha: o motivo do bloqueio do CAMP Vision não vale mais. A folha pode ir ao site.', 'painel'),
  ('outro', 'Fica fora do site', 'Conferido na folha: o bloqueio do CAMP Vision está certo. A folha fica no painel e não vai ao site.', 'painel');
