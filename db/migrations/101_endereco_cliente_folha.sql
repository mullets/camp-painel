-- Revisão pós-CAMP Vision: endereço e cliente lidos no carimbo de CADA folha (documentos[].metadados do pacote do CV2), para o consenso do lote.
ALTER TABLE item ADD COLUMN endereco_folha TEXT;
ALTER TABLE item ADD COLUMN cliente_folha TEXT;
