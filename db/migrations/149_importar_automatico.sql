-- CAMP-151 (22/10/2026, decidido pelo Rafa): importar sozinho quando o CAMP Vision termina o lote. Quem importa é o coletor em segundo
-- plano (nunca dentro de uma requisição), a cada coleta do QNAP. Comportamento novo: entra DESLIGADO e é ligado quando o Rafa mandar.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('importacao.automatica', '0', 'Importar sozinho as folhas do lote que o CAMP Vision terminou (em segundo plano, a cada coleta do QNAP). 1 = sim, 0 = não (alguém clica "Importar folhas")', 0);
