-- CAMP-150 (22/10/2026, decidido pelo Rafa): conferir só as folhas com aviso. Ao importar, a folha SEM nenhum aviso (bloqueio, duplicata,
-- autoria, espelho a confirmar, sinal do CAMP Vision ou problema aberto: a regra do "Aprovar todas", CAMP-094) entra conferida sozinha,
-- com o registro no histórico. Comportamento novo: entra DESLIGADO e é ligado em Configurações quando o Rafa mandar.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('revisao.conferir_so_avisos', '0', 'Conferir só as folhas com aviso: ao importar, a folha sem nenhum aviso entra conferida sozinha (fica no histórico). 1 = sim, 0 = não (todas esperam alguém conferir)', 0);
