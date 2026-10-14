-- Cartão "Notificações": novos assuntos de aviso por e-mail (fila parada, problema que impede publicar, pedido registrado no painel)
-- e quem recebe o quê. Cada assunto tem 'avisos.<assunto>.ligado' (1/0) e 'avisos.<assunto>.email' (vazio = avisos.email).
-- O pedido do site continua ligado/desligado em 'avisos.pedido_novo' (já existia).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('avisos.qnap.ligado', '1', 'Avisar por e-mail quando o QNAP fica quase cheio (1 = sim, 0 = não)', 0),
 ('avisos.campvision.ligado', '1', 'Avisar por e-mail quando o CAMP Vision para ou um lote dá erro (1 = sim, 0 = não)', 0),
 ('avisos.backup.ligado', '1', 'Avisar por e-mail quando a cópia de segurança do painel atrasa ou falha (1 = sim, 0 = não)', 0),
 ('avisos.site.ligado', '1', 'Avisar por e-mail quando o site não responde (1 = sim, 0 = não)', 0),
 ('avisos.replica.ligado', '1', 'Avisar por e-mail quando a cópia do acervo para (1 = sim, 0 = não)', 0),
 ('avisos.pedido_painel.ligado', '1', 'Avisar por e-mail quando alguém registra um pedido de material no painel (1 = sim, 0 = não)', 0),
 ('avisos.fila_travada.ligado', '1', 'Avisar por e-mail quando um lote fica parado na mesma etapa da Fila (1 = sim, 0 = não)', 0),
 ('avisos.fila_travada.horas', '24', 'Depois de quantas horas na mesma etapa um lote conta como parado na Fila', 0),
 ('avisos.bloqueio.ligado', '1', 'Avisar por e-mail cada problema aberto que impede publicar (1 = sim, 0 = não)', 0),
 ('avisos.qnap.email', '', 'Quem recebe o aviso do QNAP quase cheio (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.campvision.email', '', 'Quem recebe o aviso do CAMP Vision parado (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.backup.email', '', 'Quem recebe o aviso da cópia de segurança atrasada (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.site.email', '', 'Quem recebe o aviso do site sem resposta (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.replica.email', '', 'Quem recebe o aviso da cópia do acervo parada (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.pedido.email', '', 'Quem recebe o aviso de pedido de material vindo do site (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.pedido_painel.email', '', 'Quem recebe o aviso de pedido registrado no painel (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.fila_travada.email', '', 'Quem recebe o aviso de lote parado na Fila (vários separados por vírgula). Vazio: avisos.email', 0),
 ('avisos.bloqueio.email', '', 'Quem recebe o aviso de problema que impede publicar (vários separados por vírgula). Vazio: avisos.email', 0);

-- Desde quando o lote está na etapa atual (atualizado_em muda a cada leitura da pasta, então não serve para isso).
ALTER TABLE lista_processamento ADD COLUMN etapa_desde TEXT;
UPDATE lista_processamento SET etapa_desde = COALESCE(atualizado_em, criado_em) WHERE etapa_desde IS NULL;
CREATE TRIGGER IF NOT EXISTS lista_etapa_desde_ins AFTER INSERT ON lista_processamento WHEN NEW.etapa_desde IS NULL
BEGIN
  UPDATE lista_processamento SET etapa_desde = datetime('now') WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS lista_etapa_desde_upd AFTER UPDATE OF etapa ON lista_processamento WHEN NEW.etapa IS NOT OLD.etapa
BEGIN
  UPDATE lista_processamento SET etapa_desde = datetime('now') WHERE id = NEW.id;
END;

-- O registro de envio guarda a chave do aviso (ex.: 'pedido:12', 'bloqueio:34'): é ela que impede mandar o mesmo aviso duas vezes.
ALTER TABLE alerta_envio ADD COLUMN chave TEXT;
CREATE INDEX IF NOT EXISTS idx_alerta_envio_chave ON alerta_envio(chave);

-- Problemas que impedem publicar e já estavam abertos antes deste aviso existir: entram como "já conhecidos" (sem e-mail),
-- para a primeira verificação não mandar uma enxurrada de e-mails antigos.
INSERT OR IGNORE INTO alerta_estado (assunto, critico, desde, texto, critico_avisado)
  SELECT 'bloqueio:' || id, 1, datetime('now'), 'Já estava aberto antes do aviso por e-mail existir', 0
    FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade = 'bloqueia';
