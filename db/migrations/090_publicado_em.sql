-- Relatórios para prestação de contas: a data em que a folha e o projeto foram publicados pela primeira vez.
-- O painel grava ao publicar (publicacao.persistir_resultado e publicador.propagar_status_fundo); despublicar não apaga.
ALTER TABLE item ADD COLUMN publicado_em TEXT;
ALTER TABLE projeto ADD COLUMN publicado_em TEXT;
-- o que já está publicado: a primeira publicação registrada no histórico (do projeto ou do fundo inteiro); sem registro, a última alteração
UPDATE projeto SET publicado_em = COALESCE(
    (SELECT MIN(e.quando) FROM evento e WHERE e.entidade='projeto' AND e.codigo=projeto.codigo AND e.tipo='site_no_ar'),
    (SELECT MIN(e.quando) FROM evento e WHERE e.entidade='fundo' AND e.codigo=projeto.fundo_codigo AND e.tipo='site_no_ar'),
    atualizado_em, criado_em)
 WHERE status_site='no_ar' AND publicado_em IS NULL;
UPDATE item SET publicado_em = COALESCE(
    (SELECT MIN(e.quando) FROM evento e WHERE e.entidade='projeto' AND e.codigo=item.projeto_codigo AND e.tipo='site_no_ar'),
    (SELECT MIN(e.quando) FROM evento e JOIN projeto p ON p.codigo=item.projeto_codigo WHERE e.entidade='fundo' AND e.codigo=p.fundo_codigo AND e.tipo='site_no_ar'),
    atualizado_em, criado_em)
 WHERE status_site='no_ar' AND publicado_em IS NULL;
CREATE INDEX IF NOT EXISTS item_criado_em ON item(criado_em);
CREATE INDEX IF NOT EXISTS item_publicado_em ON item(publicado_em);
