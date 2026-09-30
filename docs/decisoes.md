# Decisões (26/09/2026)

- Painel roda na máquina `campvision`, não na DreamHost (precisa ver o QNAP).
- FastAPI + SQLite, migrável para PostgreSQL. Front em arquivo único.
- Acesso externo: Cloudflare Tunnel em painel.camp.arq.br + Cloudflare Access.
- Site fica intocado; integração só por REST (Application Password do usuário `camp`).
- Painel é a fonte da verdade; Tainacan recebe cópia como rascunho; publicação final no wp-admin.
- Dois portões: autorização por projeto + aprovação em lote.
- Modelo de dados baseado em ISAD(G)/NOBRADE e ISAAR(CPF) (aproveitado do AtoM), sem Elasticsearch/EAD nativo.
- Só fatos com fonte. Nada de biografia inferida.
- Fora do escopo: Biblioteca Ruth Verde Zein, edição de páginas no Elementor.
