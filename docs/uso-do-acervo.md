# Uso do acervo: quem baixou qual material, quando e para quê (em desenho)

Pedido do Rafael em 07/10/2026. **Nada além da fase 0 está implementado.** As decisões abertas estão no fim.

## O que já existe (fontes: documentos do projeto de 30/09 e 01/10; o site não foi conferido ao vivo)
- O site tem o **"Cadastro para download de material — CAMP"** (modal das fichas, Fluent Forms): nome completo, e-mail, telefone, **uso pretendido**, universidade/empresa. As entradas ficam no WordPress; o painel **não as lê**.
- O painel já tem **Solicitações** (pedidos de alta resolução): solicitante, e-mail, instituição, finalidade (publicação, pesquisa, editorial, família, exposição, outro), formatos, condições de uso, situação. Registra o **pedido**; a **entrega** é só uma marca "entregue", sem data por arquivo nem quem entregou.
- O GA4 **não mede** download, visualizador nem clique em ficha (só `form_start` e `form_submit`).

## Distinções que o desenho respeita
- **"Pediu para baixar"** (preencheu o formulário) × **"baixou de verdade"**. O segundo só é observável se o arquivo sair por um **link individual com validade**; um endereço público de arquivo não diz quem baixou.
- O **uso** é sempre **declarado**; o painel nunca afirma o uso real.

## Estado (07/10/2026)
**Fases 0 e 1 implementadas e testadas com um WordPress de mentira; NÃO rodadas contra o site real.** Os formatos da API do Fluent Forms foram assumidos
pelo que o plugin documenta; a primeira coleta real mostra o diagnóstico (a tela diz a última coleta e o erro, se houver). Autorização: o Rafael é
administrador do site e pediu para puxar o histórico completo (07/10/2026).

## O que existe
- **Coleta** (`uso_formularios.py`, tabela `uso_download`, migração 033): lê as entradas do formulário de download pela API do WordPress. **Completa** (todo o histórico, botão
  "Puxar tudo") ou **incremental** (só as novas; para na primeira página já conhecida). Automática a cada `uso.coleta_min` minutos (padrão 60; 0 desliga). Pula lixeira e spam.
  Guarda todas as respostas (`resposta_json`) e extrai nome, e-mail, telefone, instituição, uso e **material** (do campo do formulário, de qualquer valor com código CAMP, ou do
  endereço da ficha de onde o modal foi aberto). Não guarda IP. `uso_coleta` registra o que cada coleta fez, inclusive erros.
- **Tela "Uso do acervo"** (menu Pedidos, tecla 5, só admin e master): quatro números; abas Pedidos de download, Pessoas e Materiais; filtros (texto, uso, período); detalhe com telefone e
  resposta completa; Exportar CSV (todas as linhas do filtro, fica na auditoria); Atualizar agora e Puxar tudo.
- **Apagar entradas (de verdade)**: um pedido, vários (caixinhas), todos de uma pessoa, ou todos os de um filtro (exige ao menos um filtro: não dá para apagar tudo de uma vez). A entrada some de listas, contagens
  e exportações e **todos os dados são removidos**; resta só uma marca invisível (formulário + id da entrada) para uma coleta futura NÃO trazer a entrada de volta. "Apagar só os dados pessoais" continua
  existindo (mantém o pedido nas contagens). A auditoria guarda a contagem e uma impressão curta do e-mail, nunca o endereço.
- **Exportar**: a aba atual (pedidos, pessoas ou materiais) com o filtro, ou só os pedidos selecionados. CSV com BOM, todas as linhas do filtro (não só a página). Fica na auditoria.
- **E-mail para UMA pessoa**: botão no detalhe do pedido. O destinatário vem SEMPRE do banco (nunca do que o navegador mandar), sem Cc nem Bcc; o assunto não pode ter quebra de linha (contra injeção de cabeçalho);
  corpo em quoted-printable (acentos seguros em qualquer servidor); "Responder para" = quem enviou; máximo de 30 por hora; cada envio fica registrado (histórico no detalhe). Texto padrão editável em
  Configurações (`uso.email_assunto`, `uso.email_corpo`, com {nome}, {material}, {data}). Sem SMTP configurado o botão Enviar fica desativado e sobra "Abrir no meu e-mail" (mailto).
  **Para ligar o envio:** Configurações → `smtp.host`, `smtp.porta` (587 = STARTTLS; 465 = ssl), `smtp.seguranca` (starttls | ssl | nenhuma), `smtp.usuario`, `smtp.senha` e `smtp.remetente`.
- **Menu**: "Uso do acervo" fica no fim do grupo **Acervo** (só admin e master), tecla **U** (a décima entrada do menu; dígitos só até 9).
- **LGPD**: telefone fora das listas; "Apagar dados desta pessoa" anonimiza todas as entradas do e-mail (a linha fica para as contagens e NUNCA é importada de novo); a auditoria
  guarda só uma impressão curta do e-mail. O backup do painel inclui esses dados.
- Dados de pessoas nunca vão dentro de `onclick`: só em `data-*` (os campos vêm de um formulário público).

## Fases
0. **Sondagem** (`scripts/sondar_fluentforms.py`): somente leitura, sem dados pessoais. Útil se a primeira coleta real falhar.
1. **Puxar as entradas e a tela** (pronta, ver acima).
2. **Link rastreado com validade**: cada download registrado. Formulário com uso em lista de opções (as mesmas categorias de Solicitações) + detalhe livre, e aceite com versão do texto. **Não feito.**
3. **Ligação com Solicitações e direitos**: crédito, licença e resolução máxima vigentes no dia da entrega; prazo e crédito a conferir; retorno de uso; lembretes nas tarefas do dia. **Não feito.**
- Em paralelo: eventos no GA4 (download, visualizador, clique em ficha), números agregados sem identidade. **Não feito.**
- Plano B se a API do Fluent Forms não responder como esperado: importar o CSV que o próprio plugin exporta (Entradas → Exportar). **Não feito; só se a coleta real falhar.**

## Cuidados (LGPD)
- Quem vê a lista (proposta: só administradores); texto do aceite; prazo de guarda; como apagar a pedido; telefone fora das listas.
- Quem baixa sem preencher não aparece, a menos que o formulário seja obrigatório.

## Decisões abertas (do Rafael)
1. Objetivo: **prestar contas e controlar direitos**, **entender o público**, ou os dois?
2. Depois do formulário, como a pessoa recebe o arquivo hoje (link direto, e-mail, só vê na tela)? A sondagem ajuda a responder.
3. Quem pode ver a lista? (implementado: só admin e master; confirmar)
