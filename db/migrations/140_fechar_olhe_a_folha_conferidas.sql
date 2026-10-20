-- 20/10 (print da F026-P0009: "se eu resolvo um problema ele tem que sair da lista"). Os avisos do CAMP Vision que só pedem "olhe esta
-- folha" (série incerta, orientação incerta, espelhada, "conferir na folha de contatos") não fechavam quando a pessoa conferia a folha:
-- a categoria vinha fora da lista do painel ('outro'). A partir de agora fecham ao conferir (rotas_revisao.resolver_ao_conferir).
-- Esta migração aplica a MESMA regra às folhas que uma pessoa JÁ conferiu antes da correção. Só avisos do CAMP Vision, nunca os que
-- impedem publicar, nunca os relatados por pessoas, nunca de folha ainda a conferir. Idempotente (o que fecha não volta a casar).
INSERT INTO evento (entidade, codigo, tipo, ator, detalhe)
SELECT 'erro', CAST(e.id AS TEXT), 'fechado_na_conferencia', 'migração 140',
       json_object('codigo', e.codigo, 'motivo', 'a folha já tinha sido conferida no painel')
FROM erro e
WHERE e.origem = 'campvision' AND e.situacao IN ('aberto', 'em_correcao') AND e.gravidade <> 'bloqueia'
  AND (e.categoria IN ('orientacao', 'espelhado')
       OR (e.categoria = 'outro' AND (e.descricao LIKE '%série incerta%' OR e.descricao LIKE '%serie incerta%'
                                      OR e.descricao LIKE '%orientação incerta%' OR e.descricao LIKE '%orientacao incerta%'
                                      OR e.descricao LIKE '%espelhad%' OR e.descricao LIKE '%conferir na folha de contatos%')))
  AND e.codigo IN (SELECT codigo FROM item WHERE revisao IN ('conferida', 'corrigida'));

UPDATE erro SET situacao = 'corrigido', resolvido_em = datetime('now'),
       resolucao = 'Resolvido na conferência: a folha já tinha sido conferida no painel (correção de 20/10: este aviso do CAMP Vision não fechava ao conferir).'
WHERE origem = 'campvision' AND situacao IN ('aberto', 'em_correcao') AND gravidade <> 'bloqueia'
  AND (categoria IN ('orientacao', 'espelhado')
       OR (categoria = 'outro' AND (descricao LIKE '%série incerta%' OR descricao LIKE '%serie incerta%'
                                    OR descricao LIKE '%orientação incerta%' OR descricao LIKE '%orientacao incerta%'
                                    OR descricao LIKE '%espelhad%' OR descricao LIKE '%conferir na folha de contatos%')))
  AND codigo IN (SELECT codigo FROM item WHERE revisao IN ('conferida', 'corrigida'));
