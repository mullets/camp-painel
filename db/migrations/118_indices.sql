-- CAMP-034: índices das consultas que mais rodam (listas, filas, sincronização, erros, solicitações). Tudo IF NOT EXISTS.
CREATE INDEX IF NOT EXISTS idx_lista_proc_pasta        ON lista_processamento(pasta_qnap);
CREATE INDEX IF NOT EXISTS idx_lista_proc_projeto      ON lista_processamento(projeto_codigo);
CREATE INDEX IF NOT EXISTS idx_item_status_site        ON item(status_site);
CREATE INDEX IF NOT EXISTS idx_item_tainacan           ON item(tainacan_item_id);
CREATE INDEX IF NOT EXISTS idx_item_projeto_revisao    ON item(projeto_codigo, revisao);
CREATE INDEX IF NOT EXISTS idx_erro_codigo             ON erro(codigo);
CREATE INDEX IF NOT EXISTS idx_wp_item_colecao         ON wp_item(colecao_id);
CREATE INDEX IF NOT EXISTS idx_divergencia_resolvida   ON divergencia_site(resolvida, campo);
CREATE INDEX IF NOT EXISTS idx_solicitacao_situacao    ON solicitacao(situacao);
