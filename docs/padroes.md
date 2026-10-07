# Padrões do projeto — decididos; seguir, não refazer

Este é o registro único do que já foi decidido. Antes de mexer em algo daqui, leia a seção. Só se muda um padrão quando o Rafael pedir.

## 1. Infraestrutura (fatos)
- **Painel**: servidor Ubuntu `camp@camp`, `192.168.15.60:8000`, serviço `camp-painel`, repositório `~/camp-painel`. Atualiza com `./atualizar.sh` (faz backup antes).
- **QNAP TS-932PX**: `192.168.15.30`. **O nome que o Mac mostra é `Server-Camp`** (mesma máquina; `smb://Server-Camp._smb._tcp.local` é o caminho do Mac depois de montar e logar).
  Compartilhamento `Backup Servidor CAMP`; material pronto em `Arquivos/100 - Scanners`; usuário do painel `camp-panel`.
  Neste servidor: `/mnt/qnap/acervos` (raiz do compartilhamento); `qnap.prontos_raiz` = `/mnt/qnap/acervos/Arquivos/100 - Scanners`. Ver `qnap.md`.
- **Informações do QNAP no painel** (espaço, tendência, último material, entrada bruta, paradas, lotes prontos, resposta) vêm do **coletor em segundo plano** (`qnap_coletor.py`, a cada 10 min, limite de 25 s, histórico de 90 dias). **Nunca varrer o QNAP dentro de uma requisição**: por SMB é lento e, com a montagem presa, trava o painel. A tela só lê o guardado (`GET /api/qnap`; admin pede `POST /api/qnap/coletar`). Configurações: `qnap.coleta_min`, `qnap.dias_parado`.
- A pasta de ENTRADA das estações (`qnap.entrada_captura`) só é configurada quando o Rafael confirmar o caminho.
- Mudanças que alteram o site `camp.arq.br` (publicar, despublicar, escrever no Tainacan) só depois das 21h.

## 2. Vocabulário de publicação → `vocabulario.md`
Não publicado · Rascunho · Publicado · Despublicado; ações Publicar · Voltar para rascunho · Despublicar. Lint em `scripts/check_ui.py` e auditoria do texto visível.

## 3. Atalhos de teclado (UMA tabela: `NAV_ATALHOS` no `index.html`)
Ela gera as teclas, os rótulos do menu, a ajuda e a dica do painel. **Regra: dígitos 1–9 = as nove primeiras entradas do menu, NA ORDEM em que aparecem; o grupo Sistema usa letras.**
| Tecla | Tela | Tecla | Tela |
|---|---|---|---|
| 1 | Painel | 7 | Projetos |
| 2 | Filas de processamento | 8 | Localização |
| 3 | Solicitações | 9 | Etiquetas |
| 4 | Erros relatados | E | Estações e site |
| 5 | Fundos | A | Auditoria (admin) |
| 6 | Arquitetos | C | Configurações (admin) |
Fixas: `⌘/Ctrl+K` busca · `⌘/Ctrl+B` barra lateral · `F` foca o filtro da tela · `?` ajuda · `Esc` fecha. Item novo no menu = nova linha na tabela (o `check_ui` reprova se esquecer ou fora de ordem).

## 4. Listas e paginação
- Listas grandes de verdade (Projetos, Auditoria): paginação **no servidor** (`pagina`/`por_pagina`), "Mostrando X–Y de N", seletor de tamanho.
- Demais listas: paginador genérico (`ativarPaginacao`), aparece acima de 50 linhas; grades de folhas usam "Mostrar mais".
- **Exportar sempre exporta TUDO** do filtro atual, nunca só a página na tela.

## 5. Publicação
- Uma regra só (`publicacao.condicoes_projeto`) para projeto, lote e fundo inteiro; o painel mostra o checklist antes de clicar e o erro fica na tela.
- O painel **não publica arquiteto** no site: o "Status" do arquiteto é marcador interno; foto, biografia e ativar são feitos no WordPress. Guia: `como-publicar.md`.

## 6. Usuários
Papéis: master > admin > operador > leitura. Conta nova entra com senha temporária e é obrigada a trocar (a troca recusa a mesma senha e padrões óbvios). Foto de perfil fica no banco.

## 7. Como o trabalho é feito (vale para quem for mexer, inclusive o Claude)
1. Ler este arquivo e o que já existe antes de propor algo. **Não renomear, recriar nem trocar o que está decidido** sem pedido.
2. Toda mudança tem teste. Pacote: `tests/teste_backend.py` + `bash tests/rodar_auditoria.sh` (telas, funções, atalhos, XSS; passa de 5 min: rode por etapas, ex. `bash tests/rodar_auditoria.sh novas`, `... xss`) + `python3 scripts/check_ui.py`. Teste isolado: `bash tests/rodar_um.sh tests/ARQUIVO.js`.
3. Só envia ao `main` com tudo verde; o commit explica o problema, a causa e o que foi provado. Depois atualiza o Trello e marca como feito o que está concluído.
4. Não afirmar o que não foi testado; dizer o que ficou sem teste.
