-- P0002: folhas e projetos marcados como publicados (status_site='no_ar') mas SEM registro no site (sem tainacan_item_id).
-- O status é velho: corrige de uma vez para 'nao_publicado', com um evento 'status_site_corrigido' por folha/projeto (ator 'migração').
-- A rota de mover folhas já faz o mesmo caso a caso (rotas_mesclar._status_velho).

-- 1) Folhas: primeiro o evento (para saber quais eram), depois a correção.
INSERT INTO evento (entidade, codigo, tipo, ator, detalhe)
SELECT 'item', codigo, 'status_site_corrigido', 'migração',
       '{"de": "no_ar", "para": "nao_publicado", "motivo": "sem registro no site"}'
FROM item WHERE status_site = 'no_ar' AND tainacan_item_id IS NULL;

UPDATE item SET status_site = 'nao_publicado', atualizado_em = datetime('now')
WHERE status_site = 'no_ar' AND tainacan_item_id IS NULL;

-- 2) Projetos: sem registro próprio no site E sem nenhuma folha com registro no site.
INSERT INTO evento (entidade, codigo, tipo, ator, detalhe)
SELECT 'projeto', p.codigo, 'status_site_corrigido', 'migração',
       '{"de": "no_ar", "para": "nao_publicado", "motivo": "sem registro no site (nem do projeto nem de folha)"}'
FROM projeto p
WHERE p.status_site = 'no_ar' AND p.tainacan_item_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM item i WHERE i.projeto_codigo = p.codigo AND i.tainacan_item_id IS NOT NULL);

UPDATE projeto SET status_site = 'nao_publicado', atualizado_em = datetime('now')
WHERE status_site = 'no_ar' AND tainacan_item_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM item i WHERE i.projeto_codigo = projeto.codigo AND i.tainacan_item_id IS NOT NULL);
