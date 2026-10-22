-- REF-006: implantação progressiva. A fila é gravada, mas NÃO reenvia
-- automaticamente até a homologação e ativação expressa.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('site.reenvio_persistente', '0', 'REF-006: trabalhador de retentativa SQLite para correções do WordPress. 0=desligado; 1=ligado após homologação.', 0);
