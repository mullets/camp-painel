-- UX-12 (26/10, logs: GET /api/analytics levou 5,5 s e 16 s com o Google Analytics desligado): sem GA4 direto (ga4.propriedade +
-- ga4.conta_servico), o painel tentava o Site Kit do site a cada abertura do Painel. Agora "ligado" = GA4 direto preenchido OU esta
-- chave em 1. Desligado, a tela nem pergunta e a rota responde na hora "desligado" (o botão Diagnosticar continua testando o Site Kit).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('analytics.site_kit', '0', 'Visitas do site pelo Site Kit do WordPress (lento: cada leitura leva segundos). 0=desligado; 1=ligado. Com ga4.propriedade e ga4.conta_servico preenchidos o painel lê o GA4 direto e esta chave não importa.', 0);
