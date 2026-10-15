-- CAMP-024: desligar o legado com segurança. Cada peça do legado tem uma chave `legado.*` (1 = ainda aceita, padrão) e um contador de uso
-- (`legado_uso`) para provar que ninguém mais depende dela ANTES de desligar. Desligar é por configuração (e testável com simular), nunca por apagar código.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('legado.status_antigos',   '1', 'Aceita os status antigos do CV2 (campvision_concluido, pronto_campvision2) como "pronto". 0 = trata como status desconhecido (aviso)', 0),
 ('legado.nomes_de_teste',   '1', 'Ignora lote cuja PASTA se chama asd / sei la (além de teste). 0 = só vale "teste": true no info_projeto.json (ou a pasta chamada teste)', 0),
 ('legado.fundos_json',      '1', 'Serve GET /api/fundos.json para estações antigas. 0 = responde 410 com mensagem (estações novas usam /api/estacoes/contexto)', 0);
CREATE TABLE IF NOT EXISTS legado_uso (
  chave        TEXT PRIMARY KEY,
  vezes        INTEGER NOT NULL DEFAULT 0,
  primeira_em  TEXT NOT NULL DEFAULT (datetime('now')),
  ultima_em    TEXT NOT NULL DEFAULT (datetime('now')),
  ultimo_detalhe TEXT
);
