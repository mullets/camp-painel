-- CV-01: pasta + nome original de cada versão da folha, vindo do pacote do CAMP Vision (documentos[].arquivo_origem).
-- É a chave para reler/reconciliar sem heurística (o nome sozinho repete entre pastas). Vai também para o metadado
-- "Arquivo de origem" (texto, oculto ao público) da coleção Acervo CAMP quando a folha sobe ao site.
ALTER TABLE item ADD COLUMN arquivo_origem TEXT;
