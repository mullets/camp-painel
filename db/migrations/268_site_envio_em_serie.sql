-- 268 · CAMP-SITE-CARGA (26/11/2026). Site fora do ar: o plano tem 3 processos PHP e o painel mandava várias edições de fichas ao mesmo tempo.
-- Toda escrita ao site passa por um portão único (backend/app/portao_site.py): uma de cada vez, com pausa, e disjuntor em 5xx/429/tempo esgotado.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('site.envio_pausa_ms', '5000', 'Pausa mínima entre dois envios ao site, em milissegundos (o site tem 3 processos PHP).', 0),
  ('site.backoff_inicio_s', '120', 'Site respondeu 5xx/429 ou não respondeu: primeira pausa dos envios, em segundos (dobra a cada falha).', 0),
  ('site.backoff_max_s', '1800', 'Pausa máxima dos envios ao site depois de falhas seguidas, em segundos.', 0),
  ('site.envio_lote', '25', 'Folhas por envio quando a rota do site aceita várias de uma vez (disciplina das folhas).', 0),
  ('site.envios_pausados', '0', '1 = envios ao site pausados à mão (Máquinas: Pausar envios ao site); leituras seguem.', 0);
