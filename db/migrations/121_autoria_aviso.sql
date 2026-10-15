-- CAMP-046 (contrato 2.4): autoria divergente deixa de bloquear a publicação e vira aviso.
-- 1) a view de bloqueios não conta mais erro de autoria como bloqueante (a coluna itens_autoria_divergente continua, só informativa);
-- 2) erros de autoria já abertos como 'bloqueia' passam a 'corrigir' (a folha segue visível na lista de Erros relatados).
DROP VIEW IF EXISTS v_bloqueios_publicacao;
CREATE VIEW v_bloqueios_publicacao AS
  SELECT p.codigo,
         (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo AND i.autoria_divergente=1) AS itens_autoria_divergente,
         (SELECT COUNT(*) FROM erro e WHERE (e.codigo=p.codigo OR e.codigo LIKE p.codigo || '-%')
             AND e.situacao IN ('aberto','em_correcao') AND e.gravidade='bloqueia' AND e.categoria<>'autoria_divergente') AS erros_bloqueantes,
         CASE WHEN p.autorizado_site = 0 THEN 1 ELSE 0 END AS nao_autorizado
  FROM projeto p;
UPDATE erro SET gravidade='corrigir' WHERE categoria='autoria_divergente' AND gravidade='bloqueia';
