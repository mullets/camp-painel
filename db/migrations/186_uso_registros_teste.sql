-- UX-16: registros de teste do formulário de download (QA automatizado) ficam fora das métricas de Downloads do site.
-- Regra de LEITURA (nada é apagado nem alterado): finalidade com a palavra teste/testes/test/qa OU e-mail que contém um destes trechos.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('uso.emails_teste', 'qa@,qa+,+qa@,+teste@,+test@,teste@,test@,testes@,@example.,@teste.,@test.', 'Downloads do site: trechos de e-mail (separados por vírgula) que marcam um registro como TESTE. Registros de teste ficam fora das métricas e das listas (dá para vê-los no filtro). Só letras, números e @ . + _ -', 0);
