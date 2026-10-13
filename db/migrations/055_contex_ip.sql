-- #97: "IP da estação Windows do scanner Contex" (contex.ip) era o mesmo que estacao.contex1.ip e aparecia duplicado em Configurações.
-- O valor vai para estacao.contex1.ip (se ela estiver vazia) e a chave antiga sai. Nada no código lia contex.ip.
UPDATE configuracao SET valor=(SELECT valor FROM configuracao WHERE chave='contex.ip')
 WHERE chave='estacao.contex1.ip' AND (valor IS NULL OR valor='')
   AND EXISTS (SELECT 1 FROM configuracao WHERE chave='contex.ip' AND valor IS NOT NULL AND valor<>'');
DELETE FROM configuracao WHERE chave='contex.ip';
