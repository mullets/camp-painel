-- CV2 §10 / contrato 9.4: o aceite do lote (catalogacao/lotes/<lote>.json -> "aceite") guardado no painel.
-- aceite.publicavel = false trava a publicação do projeto (mesma regra única de publicacao.py).
ALTER TABLE lista_processamento ADD COLUMN aceite_json TEXT;
