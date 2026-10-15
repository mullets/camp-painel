# Tutorial do operador — do scanner até o site

Este guia acompanha **uma caixa de material** desde o scanner até a página pública em camp.arq.br.
Ele é para quem opera as estações e o painel. Para o detalhe técnico, veja `COMO_FUNCIONA.md` e `CONTRATO_UNICO.md`.

> Estado em 15/10/2026. Algumas partes novas (aviso das estações ao painel, série S08 e imagens públicas de até 1.920 px) ainda precisam ser confirmadas na prática. Onde isso importa, o texto avisa.

---

## 1. O caminho em uma tela

```
 ESTAÇÃO (Windows ou Mac)          QNAP                CAMP Vision 2            PAINEL                   SITE
 ┌───────────────────────┐   ┌───────────────┐   ┌────────────────────┐   ┌──────────────────┐   ┌────────────────┐
 │ F9  abre o projeto    │   │ 100 - Scanners│   │ lê o carimbo,      │   │ Decisões         │   │ rascunho       │
 │ escaneia              │──▶│ (entrada)     │──▶│ organiza, dá o     │──▶│ Fila → Importar  │──▶│ (só a equipe   │
 │ F10 finaliza          │   │               │   │ código, EXIF       │   │ Conferir → Aprovar│  │  vê)           │
 │ F12 envia ao QNAP     │   │ ACERVOS_CAMP  │   │ grava em ACERVOS   │   │ Publicar         │   │ publicado      │
 └───────────────────────┘   └───────────────┘   └────────────────────┘   └──────────────────┘   │ (todos veem)   │
        você                    automático            automático               você / admin       └────────────────┘
```

Quem faz o quê:

| Etapa | Quem | Onde |
|---|---|---|
| Escanear, F9, F10, F12 | **Operador da estação** | Windows (Contex) ou Mac (VueScan) |
| Copiar para o QNAP, ler, organizar, catalogar | **Automático** (CAMP Vision 2) | Servidor |
| Responder perguntas, importar, conferir folhas | **Operador** | Painel |
| Aprovar o lote, autorizar, publicar | **Admin** | Painel |
| Aparecer na página pública | **Automático** depois de publicar | Site |

**Regra de ouro:** o que vale é o arquivo no QNAP. O painel só mostra e organiza. Nunca renomeie nem apague nada direto no QNAP.

---

## 2. Antes de começar

- A estação precisa enxergar o **painel** (`http://192.168.15.60:8000`). É ele que dá o número do projeto (P0001, P0002…). Sem painel você captura, mas **não cria projeto novo**.
- O **QNAP** precisa estar conectado. No Mac, sem QNAP o F10 para com erro, de propósito.
- Cada fundo já deve existir no painel (Fundos → Novo fundo). A lista de fundos da estação vem do painel.
- Os **direitos do fundo** precisam estar como *Autorizado* no painel (fundo → "Direitos e licença"). **Sem isso nada é publicado.** Isso é com o admin.

---

## 3. Na estação Windows (scanner Contex)

Abra o atalho **Sistema Digitalizacao CAMP** na Área de Trabalho. O programa se atualiza sozinho pelo GitHub (quando há versão nova, em até 5 minutos). Não abra nem feche no meio de um lote.

### 3.1 F9 — abrir o projeto
1. Aperte **F9**.
2. Escolha o **fundo**.
3. Diga **quem está operando**.
4. No campo **Projeto**:
   - **➕ Projeto novo:** digite nome, cidade, ano e a identificação original (ex.: `CX039`, `Tubo 07`). O número é reservado no painel.
   - **Projeto que já existe:** digite para procurar. A numeração das pranchas continua do ponto em que parou.
5. O painel pode **perguntar** se o projeto é parecido com outro. Nesse caso o lote espera uma decisão do admin (veja 5.1). Não crie o projeto de novo.

### 3.2 Escanear
Escaneie pelo NextImage normalmente. Os TIFs vão para a pasta local do projeto.

### 3.3 F10 — finalizar
Aperte **F10**. O sistema confere duplicatas, dá o código CAMP, converte para JPG e confere TIF × JPG. O lote fica esperando na pasta local. Se aparecer erro de "estado inconsistente", há TIF sem JPG (ou o contrário): chame o responsável técnico.

**Etiquetas:** ao terminar o F10, imprima a etiqueta da pasta do projeto e cole no material. Abra o painel → menu **Etiquetas** (tecla **T**) e escolha o fundo e o projeto. Passo a passo em `TUTORIAL_ETIQUETAS.md`.

### 3.4 F12 — enviar ao QNAP
Aperte **F12** (ou deixe o backup automático, se estiver ligado). O sistema copia para o QNAP, confere e **só então** apaga a cópia local. No fim ele grava, nesta ordem: informações do projeto → manifesto → **status** (último arquivo; é o sinal de "terminei" para o CAMP Vision).

**Pronto para sair da estação:** a mensagem final de sucesso e a pasta local sumindo. Não desligue antes disso.

Código dos arquivos: `F023-P0001-1982-S01-D00001.tif`. Nesta estação a série é sempre **S01 — Desenhos e pranchas**.

---

## 4. Na estação Mac (VueScan: negativos, slides, fotos)

O VueScan salva TIF + JPG em *Imagens (~/Pictures)*. Cada par é movido para a pasta do **material** escolhido na hora.

| Comando | O que faz |
|---|---|
| **Novo lote (F9 / ⌘N)** | Carrega os fundos do painel, mostra último e próximo P, escolhe projeto novo ou existente e o **material** (Fotografia, Negativo ou Slide) |
| *(scans chegando)* | Cada par vai para a pasta do material atual |
| **Finalizar (F10 / ⌘F)** | Checa duplicatas, dá o código continuando o D do projeto, confere TIF × JPG |
| **Backup QNAP (F12 / ⌘B)** | Copia para o QNAP **mesclando** (nunca sobrescreve), confere e só então apaga a cópia local |

- Você pode **trocar o material a qualquer hora** em "Material escaneando agora". Os próximos scans vão para a pasta nova.
- Material → série: **Fotografia = S03**, **Negativo = S04**, **Slide = S05**.
- Os botões da janela sempre funcionam. As teclas F9/F10/F12 só com a janela em foco (no teclado do Mac, talvez com **fn**).
- Projeto que o **Windows ou o painel já criaram:** o Mac só cria a pasta do material escaneado. Não cria as outras pastas do fundo.

---

## 5. O que acontece sozinho (você só acompanha)

1. O **CAMP Vision 2** vê o lote novo em `100 - Scanners` quando o arquivo de status aparece. Ele espera os arquivos terminarem de copiar (arquivos `.copiando` são ignorados) e confere com o manifesto.
2. Ele lê o carimbo de cada folha, organiza por série, grava os metadados e copia para `ACERVOS_CAMP`.
3. Ele **avisa o painel**, que mostra o lote na **Fila**.
4. Cada estação também avisa o painel quando termina o F10 ("capturado") e o F12 ("enviado"). Se o painel estiver fora, o aviso fica numa fila local e é reenviado depois. **Isso nunca trava o operador.**

O tempo depende do tamanho do lote. Se o lote não aparecer em **mais de 1 hora** depois do F12, o painel o lista em "Lotes enviados pela estação e ainda sem processar" (veja 8).

### 5.1 Decisões (admin) — quando o painel pergunta
Menu **Decisões** (tecla 2). Aparecem perguntas antes de qualquer projeto ser criado ou mexido:

| Pergunta | O que fazer |
|---|---|
| **Este projeto já existe no fundo?** | Compare os nomes e as capas. Escolha **"É o mesmo"** (as folhas entram no projeto existente) ou **novo** |
| **O lote traz folhas com números que o projeto já usa** | Adicionar ao fim, ignorar ou substituir |
| **O CAMP Vision leu ano/cidade/cliente diferente do cadastro** | Escolha o valor certo |
| **Mesmo nome em outro fundo** | Diga se é o mesmo ou diferente (só anota) |

Enquanto a decisão está pendente, o CAMP Vision espera. Depois de resolvida, ele segue em até 2 minutos.

---

## 6. No painel — importar, conferir, aprovar

### 6.1 Importar (operador)
Menu **Material novo** (tecla 3, também chamado de Fila). A aba **"Precisam de você"** mostra cada lote com **um** botão do próximo passo.

1. Lote em fase **importar** → botão **Importar folhas**. Com vários lotes, use **Importar todas (N)**.
2. O painel cria uma folha (item) por documento, com o código que o CAMP Vision deu.

### 6.2 Conferir folha a folha (operador)
Lote em fase **conferir** → botão **Conferir folhas**. A primeira folha pendente abre.

- Compare a **imagem** com o que o CAMP Vision leu: título, tipo de documento, número da folha, escala, ano, endereço, cliente.
- Está certo? **"Está certo"** (tecla **Enter**). A folha vira *conferida* e a próxima abre sozinha.
- Precisa corrigir? Edite o campo e **"Salvar correção"**.
- **Girar / espelhar:** se a imagem está virada, use os botões de girar ou espelhar. A folha de contatos (botão no projeto) ajuda a ver tudo de uma vez.
- **Duplicata:** marque como duplicata em vez de conferir.
- **Não publicar esta folha:** use **Reter** (com motivo). A folha fica no painel e nunca vai ao site.
- **Atalhos em lote:** existe um botão que confere sozinho só as folhas **sem nenhum problema apontado** (o painel diz quantas conferiu e quantas ainda precisam de olho humano). E existe **"Aprovar todas"**, que marca todas as pendentes. Use o segundo só depois de olhar o lote. Os nomes dos botões podem variar um pouco na tela.

Folha que já está no site não se confere de novo no painel: o painel responde que ela já foi publicada.

### 6.3 Folhas com aviso
Algumas folhas trazem aviso. Elas **não impedem** a publicação:

- **Autoria não confirmada:** o carimbo traz um nome diferente do titular do fundo (coautoria, consultoria, terceiros). A folha **continua no lote e pode ser publicada**. No site ela aparece com "Autoria não confirmada", nunca com o nome lido como fato.
- **Orientação incerta / série incerta:** confira a imagem.
- Folha de **outra obra** (projeto divergente), **capa ou sem identificação** é tirada do lote ("retirados"). Confira essa lista e devolva a folha se foi engano.

### 6.4 Aprovar o lote (admin)
Quando não restar nenhuma pendente: **Aprovar lote**. Isso trava o lote contra mudanças. Para mexer de novo, o admin usa **Reabrir** (só se o lote ainda não foi ao site).

---

## 7. Publicar no site (admin)

### 7.1 O que precisa estar pronto
O painel **Publicação**, na página do projeto, mostra cada condição, com o botão que resolve:

1. **Direitos do fundo autorizados.** Sem isso nada é publicado.
2. **Projeto autorizado.** Autorizar **não publica sozinho**.
3. **Sem erros que bloqueiam.** Autoria divergente **não** bloqueia mais.
4. **Aceite do lote no CAMP Vision**, quando existir.
5. **Não é lote de teste.**
6. **Folhas conferidas e lote aprovado.**
7. **Existe no site** (dossiê e folhas enviados como rascunho).

### 7.2 Publicar com um clique
No projeto, botão **Publicar**. O painel faz, em segundo plano e com progresso na tela: **dossiê → folhas como rascunho → autorizar → publicar**. A tela mostra antes o **plano** do que será feito. Se algo só uma pessoa resolve (por exemplo, direitos do fundo), o botão fica desligado com o motivo.

- Para vários projetos de um fundo: na página do fundo, **Publicar** para todos os projetos prontos (só admin master). Para vários lotes de uma vez, o painel também tem publicação em lote com a mesma sequência.
- **Estados:** *Não publicado* (só no painel) → *Rascunho* (no site, só a equipe vê) → *Publicado* (qualquer visitante vê) → *Despublicado* (retirado de propósito). Despublicar o que já está publicado exige admin master.

### 7.3 Fundo e arquiteto
Antes do primeiro projeto de um fundo ir ao ar:

1. Fundos → **Novo fundo** (código F0xx e sigla de 3 letras não mudam depois).
2. Escreva a **história e a procedência**, **só com a fonte citada**.
3. Vincule o **arquiteto** (nome na forma autorizada, datas, grafias de carimbo).
4. Preencha **biografia e foto** no painel. O botão **Enviar fundo ao site** cria ou atualiza a página do arquiteto no site com o que está preenchido. Campo vazio no painel **não** apaga nada no site.
5. A página do arquiteto só aparece depois de pelo menos um projeto dele estar **publicado**.

---

## 8. O que o visitante vê no site

- **Projetos:** `camp.arq.br/acervo/projetos/…` e **documentos:** `…/acervo/documentos/…`. As listas têm **24 por página**, com paginação (anterior/próxima), e funcionam sem JavaScript.
- **Imagem pública:** no máximo **1.920 px** no lado maior, sem marca d'água. O **zoom** e o **"Baixar para consulta"** usam só essa imagem.
- **Alta resolução:** o visitante pede pelo botão **"Solicitar alta resolução"**. O pedido chega ao painel (menu **Pedidos de material**) e a equipe entrega o original. O arquivo TIF nunca é público.
- **Correções:** o visitante também pode reportar um erro numa folha. Isso vira um **problema** no painel (menu **Problemas**).
- **Privacidade:** a política publicada tem o CNPJ, o encarregado e o prazo de 24 meses. Dados pessoais de pedidos são anonimizados depois desse prazo (rotina do site e do painel; ainda em modo de teste até o admin ligar).

**Conferir depois de publicar:** abra **Ver página pública** no projeto e confira título, imagem, zoom e a lista de folhas.

---

## 9. Se algo não anda

| Sintoma | O que significa | O que fazer |
|---|---|---|
| F9 diz que o painel está fora | Sem rede ou painel desligado | Veja a rede. Você captura, mas não cria projeto novo. Chame o responsável técnico |
| F9 mostra "o painel exige token" | A estação está sem o token certo | Chame o responsável técnico. Não é "servidor desatualizado" |
| F10 para com "estado inconsistente" | TIF e JPG não batem | Não force. Chame o responsável técnico |
| F10 (Mac) para por falta de QNAP | QNAP desconectado | Reconecte o QNAP e tente de novo. O sistema nunca assume o D em silêncio |
| F12 não termina | Cópia ou conferência falhou | **Não apague a pasta local.** Chame o responsável técnico |
| O lote não aparece na Fila depois de uma hora | CAMP Vision não pegou | Veja em **Material novo** → "Procurar no QNAP agora". Admin vê também a tela **Máquinas e site** |
| O lote está parado numa **Decisão** | O painel perguntou algo | Admin resolve em **Decisões** |
| O lote fica esperando e o painel avisa "lote incompleto" | Chegaram menos arquivos que o manifesto declarou | Confira se a cópia terminou. Reenvie com F12 |
| "O CAMP Vision está parado" na tela **Máquinas e site** | Serviço do servidor parou | Admin chama o responsável técnico |
| Erro `410 descartado` na estação | O admin descartou esse pedido de projeto | A mensagem diz o motivo. Fale com o admin |
| Aviso de divergência: "enviou N arquivos, chegaram M folhas" | A contagem da estação difere das folhas entregues | Confira se algum arquivo ficou de fora. É só aviso |
| **Publicar** está desligado | Falta uma condição | Leia o motivo no painel **Publicação**; cada item tem o botão que resolve |
| Folha já está no site e não deixa editar | Já foi publicada | Admin despublica ou usa a edição da folha publicada |

**Quando chamar o responsável técnico:** qualquer erro que mencione QNAP, token, manifesto, backup ou "estado inconsistente"; o lote parado por mais de uma hora; ou a tela de Estações mostrando uma máquina com erro.

---

## 10. O que NUNCA fazer

- Renomear, mover ou apagar arquivos **direto no QNAP**.
- Apagar a pasta local da estação **antes** do F12 terminar.
- Criar de novo um projeto que o painel disse que "já existe": use a decisão **"É o mesmo"**.
- Reusar ou inventar número de projeto. O painel é a única fonte do P e do D.
- Publicar biografia sem fonte citada.
- Fechar o programa no meio do F10 ou do F12.
- Mexer no `config.json` ou em arquivos da pasta do sistema na estação. Edições locais somem na próxima atualização automática.
- Escrever "no ar", "fora do ar" ou "tirar do ar": use **publicado**, **rascunho** e **despublicado** (vocabulário do painel).

---

## 11. Checklist rápido de uma caixa

**Estação**
- [ ] Painel e QNAP conectados
- [ ] F9: fundo, operador, projeto (novo ou existente), identificação original
- [ ] Escanear tudo
- [ ] F10 sem erro
- [ ] Etiqueta da pasta impressa e colada (`TUTORIAL_ETIQUETAS.md`)
- [ ] F12 até a pasta local sumir

**Painel (operador)**
- [ ] Decisões respondidas (admin), se houver
- [ ] Material novo → **Importar folhas**
- [ ] **Conferir** cada folha: certo, corrigir, girar, reter ou duplicata
- [ ] Olhar a lista de **retirados**

**Painel (admin)**
- [ ] Direitos do fundo autorizados
- [ ] **Aprovar lote**
- [ ] **Publicar** (e conferir o plano antes)

**Site**
- [ ] **Ver página pública**: título, imagens, zoom, lista de folhas
- [ ] Página do arquiteto no ar, se for o primeiro projeto do fundo

---

## 12. Glossário

| Termo | Significa |
|---|---|
| **Fundo (F0xx)** | O acervo de um arquiteto ou escritório |
| **Projeto (P000x)** | Uma obra dentro do fundo. O número é sequencial por fundo e **nunca é reaproveitado** |
| **Série (S01–S08, S99)** | Tipo de material: S01 Desenhos e pranchas · S02 Documentos textuais · S03 Fotografias · S04 Negativos · S05 Slides · S06 Materiais e especificações · S07 Publicações · S08 Redesenhos · S99 Não identificado |
| **Folha / documento (D00001)** | Cada imagem. Código completo: `F023-P0001-1982-S01-D00001` |
| **Lote** | O que uma estação envia de uma vez |
| **QNAP** | O armazenamento em rede. `100 - Scanners` é a entrada; `ACERVOS_CAMP` é o acervo |
| **CAMP Vision 2** | O programa que lê os carimbos e organiza os lotes |
| **Manifesto** | Lista de arquivos do lote com tamanho e SHA-256, para conferir a cópia |
| **Dossiê** | A página do projeto no site (sem as folhas) |
| **Rascunho** | Está no site, mas só a equipe logada vê |
| **Publicado** | Visível para qualquer visitante |
| **Retida** | Folha que fica só no painel e nunca vai ao site |
