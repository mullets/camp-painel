# Uso do acervo: quem baixou qual material, quando e para quê (em desenho)

Pedido do Rafael em 07/10/2026. **Nada além da fase 0 está implementado.** As decisões abertas estão no fim.

## O que já existe (fontes: documentos do projeto de 30/09 e 01/10; o site não foi conferido ao vivo)
- O site tem o **"Cadastro para download de material — CAMP"** (modal das fichas, Fluent Forms): nome completo, e-mail, telefone, **uso pretendido**, universidade/empresa. As entradas ficam no WordPress; o painel **não as lê**.
- O painel já tem **Solicitações** (pedidos de alta resolução): solicitante, e-mail, instituição, finalidade (publicação, pesquisa, editorial, família, exposição, outro), formatos, condições de uso, situação. Registra o **pedido**; a **entrega** é só uma marca "entregue", sem data por arquivo nem quem entregou.
- O GA4 **não mede** download, visualizador nem clique em ficha (só `form_start` e `form_submit`).

## Distinções que o desenho respeita
- **"Pediu para baixar"** (preencheu o formulário) × **"baixou de verdade"**. O segundo só é observável se o arquivo sair por um **link individual com validade**; um endereço público de arquivo não diz quem baixou.
- O **uso** é sempre **declarado**; o painel nunca afirma o uso real.

## Fases
0. **Sondagem (pronta)**: `scripts/sondar_fluentforms.py` (somente leitura, sem dados pessoais) diz se o formulário registra **qual material**, o que a pessoa recebe ao enviar, quantas entradas existem e como está o "uso pretendido".
1. **O painel puxa as entradas do formulário** (como já puxa o site; não exige expor o painel) e cria a tela **"Uso do acervo"**: lista (dia, pessoa, e-mail, instituição, material, formato, uso), visão por pessoa (agrupada por e-mail), visão por material (mais baixados e quem baixou), filtros, CSV, e a seção "Quem baixou" na ficha de folha, projeto e fundo.
2. **Link rastreado com validade**: cada download fica registrado (data, arquivo, pedido). Formulário com **uso em lista de opções** (as mesmas categorias de Solicitações) + detalhe livre, e aceite com versão do texto.
3. **Ligação com Solicitações e direitos**: gravar, no dia da entrega, o crédito exigido, a licença e a resolução máxima vigentes do fundo; prazo e crédito a conferir; retorno de uso (onde foi publicado); lembretes nas tarefas do dia.
- Em paralelo: eventos no GA4 (download, abertura do visualizador, clique em ficha) para números agregados, sem identidade.

## Cuidados (LGPD)
- Quem vê a lista (proposta: só administradores); texto do aceite; prazo de guarda; como apagar a pedido; telefone fora das listas.
- Quem baixa sem preencher não aparece, a menos que o formulário seja obrigatório.

## Decisões abertas (do Rafael)
1. Objetivo: **prestar contas e controlar direitos**, **entender o público**, ou os dois?
2. Depois do formulário, como a pessoa recebe o arquivo hoje (link direto, e-mail, só vê na tela)? A sondagem ajuda a responder.
3. Quem pode ver a lista?
