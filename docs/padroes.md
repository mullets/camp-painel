# Padrões do projeto — decididos; seguir, não refazer

Este é o registro único do que já foi decidido. Antes de mexer em algo daqui, leia a seção. Só se muda um padrão quando o Rafael pedir.

## 1. Infraestrutura (fatos)
- **Painel**: servidor Ubuntu `camp@camp`, `192.168.15.60:8000`, serviço `camp-painel`, repositório `~/camp-painel`. Atualiza com `./atualizar.sh` (faz backup antes).
- **QNAP TS-932PX**: `192.168.15.30`. **O nome que o Mac mostra é `Server-Camp`** (mesma máquina). Compartilhamento `Backup Servidor CAMP`; usuário do painel `camp-panel`; montado neste servidor em `/mnt/qnap/acervos` (raiz do compartilhamento). Ver `qnap.md`.
  - **ENTRADA** (`qnap.entrada_captura`): `Arquivos/100 - Scanners`. Os scanners gravam aqui e o CAMP Vision 2 lê. O painel não lê lotes daqui.
  - **PRONTO** (`qnap.prontos_raiz`): `Fundos e Escritorios/ACERVOS_CAMP`, no padrão `<Fundo>/01 - Projetos/<Fxxx-Pxxxx - Nome>/<série>`. O CAMP Vision 2 grava aqui e **o painel lê os lotes só daqui**.
- **CAMP Vision 2** (repositório oficial `github.com/mullets/campvision-new`; o `campvision2` é o app antigo): roda num Ubuntu dedicado (`.40`). O **contrato** com o painel (arquivos, valores de `status`, heartbeat, token, reserva de projeto) está em `campvision.md`; quem mexer em um lado confere o outro.
- **Uso do acervo (quem pediu para baixar o quê)**: fases 0 e 1 prontas (coleta do formulário de download do site, tela só para admin/master, CSV, apagar pessoa); ver `uso-do-acervo.md`. "Pediu para baixar" é diferente de "baixou de verdade"; o uso é sempre o declarado. Dados de pessoas nunca dentro de `onclick` (só `data-*`). A coleta automática tem `uso.coleta_min` (a semente de teste a desliga, como a do QNAP: teste não depende de relógio).
- **Informações do QNAP no painel** (espaço, tendência, último material, entrada bruta, paradas, lotes prontos, resposta) vêm do **coletor em segundo plano** (`qnap_coletor.py`, a cada 10 min, limite de 25 s, histórico de 90 dias). **Nunca varrer o QNAP dentro de uma requisição**: por SMB é lento e, com a montagem presa, trava o painel. A tela só lê o guardado (`GET /api/qnap`; admin pede `POST /api/qnap/coletar`). Configurações: `qnap.coleta_min`, `qnap.dias_parado`.
- Mudanças que alteram o site `camp.arq.br` (publicar, despublicar, escrever no Tainacan) só depois das 21h.

## 2. Vocabulário de publicação → `vocabulario.md`
Não publicado · Rascunho · Publicado · Despublicado; ações Publicar · Voltar para rascunho · Despublicar. Lint em `scripts/check_ui.py` e auditoria do texto visível.

## 3. Atalhos de teclado (UMA tabela: `NAV_ATALHOS` no `index.html`)
Ela gera as teclas, os rótulos do menu, a ajuda e a dica do painel. **Regra: dígitos 1–9 = as nove primeiras entradas do menu, NA ORDEM em que aparecem; da décima em diante, letras (hoje: U Uso do acervo, que fica no fim do grupo Acervo, e E, A, C no grupo Sistema).**
| Tecla | Tela | Tecla | Tela |
|---|---|---|---|
| 1 | Painel | 7 | Projetos |
| 2 | Filas de processamento | 8 | Localização |
| 3 | Solicitações | 9 | Etiquetas |
| 4 | Erros relatados | E | Estações e site |
| 5 | Fundos | U | Uso do acervo (admin; último do grupo Acervo) |
| 6 | Arquitetos | E | Estações e site |
|  |  | A | Auditoria (admin) |
|  |  | C | Configurações (admin) |
Fixas: `⌘/Ctrl+K` busca · `⌘/Ctrl+B` barra lateral · `F` foca o filtro da tela · `?` ajuda · `Esc` fecha. Item novo no menu = nova linha na tabela (o `check_ui` reprova se esquecer ou fora de ordem, e `tests/auditoria_atalhos.js` aperta TODAS as teclas da tabela).

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

## 9. O painel verifica antes de agir e, na dúvida, PERGUNTA (Decisões)
Regra de projeto (pedido do Rafael, 08/10/2026): o painel não obedece cegamente. Antes de criar ou mudar algo que pode duplicar ou contradizer o que já existe, ele **confere** e, havendo dúvida, **abre uma decisão** para uma pessoa em vez de escolher sozinho.
- **Fila única:** tabela `decisao` (tipo, chave, fundo, pedido e candidatos em JSON, situação, resolução, projeto resultante). Aparece no "Precisa de atenção" (topo) e conta nas pendências do "Por onde começar". Ler: operador; decidir: admin.
- **Nunca decide sozinho** que dois projetos são o mesmo. Mostra a **nota e os motivos** (nome, identificação original, ano, cidade) e os dois caminhos: "é o mesmo: adicionar a este" ou "é outro: criar novo". Decisão resolvida fica só para leitura.
- **Idempotente:** a mesma `chave_reserva` volta sempre à mesma decisão; depois de decidida, devolve sempre o mesmo projeto.
- **Hoje:** `projeto_parecido` (reserva da estação e "Novo projeto" à mão). Motor em `similaridade.py` (puro e testado: palavras genéricas, nome contido, erro de OCR; número ou letra de designação distingue projetos). Novas verificações entram na mesma fila (ver o cartão "Mais inteligência").
- **Teste:** toda verificação nova precisa de caso que DEVE pedir decisão e caso parecido que NÃO deve (falso alarme também é defeito).
