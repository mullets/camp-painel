-- O status do projeto espelha SÓ o site (nao_publicado, rascunho, no_ar, fora_do_ar). "Bloqueado" nunca foi estado do site: era um erro bloqueante aberto,
-- que se descobre pela tabela de erros. Devolve ao status de verdade os projetos que ficaram marcados 'bloqueado', olhando o dossiê no espelho do site.
UPDATE projeto SET status_site = COALESCE(
  (SELECT CASE w.status WHEN 'publish' THEN 'no_ar' WHEN 'draft' THEN 'rascunho' WHEN 'pending' THEN 'rascunho' WHEN 'private' THEN 'fora_do_ar' ELSE NULL END
     FROM wp_item w WHERE w.id = projeto.tainacan_item_id), 'nao_publicado')
WHERE status_site = 'bloqueado';
