-- CAMP-009: o CAMP Vision pede ao painel (POST /api/campvision/reidentificar) para mover/mesclar o que entrou no projeto errado.
-- SIMULAR é sempre permitido; APLICAR só com esta configuração = 1 (nasce 0: ligar só depois de revisar o plano da F026).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('campvision.reidentificar_aplicar', '0', 'Libera o CAMP Vision a APLICAR movimentos de reidentificação (mover/mesclar). 0 = só simular (padrão); 1 = aplica', 0);
