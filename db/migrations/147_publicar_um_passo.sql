-- CAMP-148 (22/10/2026, decidido pelo Rafa): "Publicar no site" único — com o lote conferido, o mesmo clique aprova o lote,
-- autoriza e publica; o operador também pode. Comportamento novo: entra DESLIGADO e é ligado em Configurações quando o Rafa mandar.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('publicacao.publicar_um_passo', '0', 'Publicar no site em um passo: com as folhas conferidas, "Publicar" aprova o lote junto (sem o passo "Aprovar o lote") e o operador também publica. 1 = sim, 0 = não (como antes: um admin aprova e publica)', 0);
