-- Corrige contagem (o JOIN item×erro multiplicava): subconsultas independentes
DROP VIEW IF EXISTS v_bloqueios_publicacao;
CREATE VIEW v_bloqueios_publicacao AS
  SELECT p.codigo,
         (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo AND i.autoria_divergente=1) AS itens_autoria_divergente,
         (SELECT COUNT(*) FROM erro e WHERE (e.codigo=p.codigo OR e.codigo LIKE p.codigo || '-%')
             AND e.situacao IN ('aberto','em_correcao') AND e.gravidade='bloqueia') AS erros_bloqueantes,
         CASE WHEN p.autorizado_site = 0 THEN 1 ELSE 0 END AS nao_autorizado
  FROM projeto p;
