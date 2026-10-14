-- Decisão de 14/10 (Rafael): fundos não se misturam. Fecha as perguntas pendentes "mesmo nome em outro fundo" e as que
-- nasceram de pasta do sistema ("01 - Arquivo Arquivístico (TIFF)", "03 - Fotografias", "JPG"…). Nada é criado nem apagado.
UPDATE decisao SET situacao='resolvida', escolha='descartar', resolvida_em=datetime('now'), resolvida_por='painel (regra de 14/10)'
 WHERE situacao='pendente' AND (
       tipo='projeto_outro_fundo'
    OR titulo LIKE '%Arquivo Arquiv%' OR titulo LIKE '%Arquivo de acesso%'
    OR titulo LIKE '__ - Fotografias%' OR titulo LIKE '__ - Desenhos%' OR titulo LIKE '__ - Documentos%' OR titulo LIKE '__ - Textos%'
    OR titulo LIKE '%Em identifica%'
    OR UPPER(titulo) IN ('JPG','JPEG','TIF','TIFF','PNG','PDF','FOTOGRAFIAS','FOTOS','DESENHOS','DESENHOS E PRANCHAS','DOCUMENTOS','ORIGINAIS'));
