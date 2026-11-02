-- Protocolos (02/11/2026, CAMP: "todos os formulários seriam bons ter protocolos, e no painel ter eles para ajudar"; contrato 1.7).
-- A inscrição guarda o protocolo que o site mandou (vazio = site antigo; o painel calcula pela mesma regra, app/protocolo.py).
-- Pedidos usam o payload guardado em pedido_site e downloads são calculados; nada a guardar. Idempotente.
ALTER TABLE inscricao ADD COLUMN protocolo TEXT;
