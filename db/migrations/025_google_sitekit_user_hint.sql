-- Torna explícita a relação entre o usuário técnico do painel e o Site Kit.
UPDATE configuracao
   SET descricao='Usuário WordPress usado pelo painel; este mesmo usuário precisa estar conectado ao Google/Site Kit'
 WHERE chave='wp.usuario';
