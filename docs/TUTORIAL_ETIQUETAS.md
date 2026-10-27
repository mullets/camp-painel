# Tutorial — etiquetas do material

Este guia mostra como **gerar, imprimir e colar** as etiquetas do acervo. Ele complementa o `TUTORIAL_OPERADOR.md` (do scanner até o site).
A etiqueta liga o objeto físico (pasta, caixa, tubo) ao registro no painel: quem lê o código com o celular chega direto na página certa.

> Estado em 15/10/2026. A tela de etiquetas do painel já existe e está em uso. As estações **não** abrem a tela sozinhas: o operador abre pelo painel. Nada aqui foi testado com a impressora de verdade.

---

## 1. Quando etiquetar

| Momento | O que etiquetar | Por quê |
|---|---|---|
| **Ao finalizar o lote (F10)** | A **pasta (ou o volume) do projeto** que acabou de ser escaneada | O material ainda está na mesa. O código do projeto já existe |
| **Ao guardar o material** | A **caixa**, a **gaveta** ou o **tubo** onde ele fica | Para achar depois e conferir o que está dentro |
| **Uma vez por fundo** | A etiqueta do **fundo** (caixa-mãe, estante, porta) | Identifica o acervo inteiro |
| **Quando for preciso** | A etiqueta de **folha avulsa** | Folhas soltas, plantas grandes, consulta presencial |

Regra simples: **material escaneado → etiqueta da pasta; onde ele mora → etiqueta da caixa.**

---

## 2. Como abrir a tela de etiquetas

Há dois jeitos, os dois chegam na mesma tela:

1. **Pelo menu do painel:** **Etiquetas** (atalho **T**).
2. **Pelo projeto, fundo, folha ou local:** os botões "Imprimir etiqueta" nas páginas levam direto, já com o item escolhido.

O navegador que você usa precisa estar **logado no painel**. Senão aparece a tela de login.

---

## 3. Os tipos de etiqueta

Na tela há abas, uma para cada tipo:

| Aba | Para quê | O que sai impresso | Exemplo |
|---|---|---|---|
| **Pasta de projeto** | Pasta ou volume do projeto | Sigla do fundo, número do projeto e volume | `SBU-P011.1` |
| **Folha / documento** | Folha avulsa | O código completo da folha | `F026-P0001-1968-S01-D00001` |
| **Caixa ou gaveta** | Recipiente (caixa, gaveta, mapoteca, estante) | Código do fundo e identificador do local | `F026-CX-001` |
| **Lombada de tubo** | Tubo de plantas | Código do projeto, na vertical | `F026-P0001` |
| **Fundo** | Acervo inteiro | Código do fundo, grande, com a sigla | `F026 SBU` |

Todas levam também, **sempre**: o nome do projeto, o **arquiteto** (a autoria cadastrada no projeto; se não houver, o nome do fundo), a cidade e o ano. Se faltar dado, a etiqueta mostra "sem cidade" ou "sem data". Corrija o cadastro e imprima de novo.

O código de barras é **Code 39**. Qualquer leitor comum lê.

**Formatos pequenos (UX-26):** o Code 39 é pouco denso. O painel calcula, para cada etiqueta, a largura da barra mais fina; abaixo de **0,19 mm** o leitor não lê com segurança e a etiqueta sai com um **QR** no lugar das barras, com o código **escrito** do lado. Com o código de folha mais longo (26 caracteres, ex. `F009-P0015-1973-S01-D00001`) isso acontece em **70 × 35** e na **lombada 20 × 140** (o seletor mostra "folha sai com QR"); em 100 × 50 a barra fica em ~0,22 mm e continua Code 39. Códigos curtos (projeto, caixa, fundo) continuam em Code 39 nesses formatos. A NIIMBOT já usava QR. O celular (**Ler etiqueta**) lê os dois. **Leitor só de código de barras (1D) não lê QR**: para ele, use um formato maior.
> Ainda não foi feita a prova física: imprimir cada formato e ler 3 vezes com o leitor da CAMP e com o celular.

---

## 4. Passo a passo — gerar e imprimir

### Passo 1 — O que etiquetar
1. Escolha o **fundo** e depois o **projeto**. Os dados do cadastro aparecem só para leitura (ano, cliente, endereço, localização, quantidade de documentos, embalagem). Se algum estiver errado, use **"Corrigir no projeto"**.
2. Se o projeto tem mais de um volume (por exemplo, "volume 1 de 3"), escolha o volume.
3. Escolha o **lote**: **só esta**, **todas as folhas deste projeto** ou **todas as pastas do fundo**.
4. Na aba **Caixa**, o campo **Local cadastrado** preenche o identificador e o conteúdo.

### Passo 2 — Como imprimir
1. **Formato:**

   | Formato | Tamanho | Uso |
   |---|---|---|
   | **100×50** | 100 × 50 mm | Padrão CAMP |
   | **70×35** | 70 × 35 mm | Etiqueta pequena |
   | **20×140** | 20 × 140 mm | Lombada de tubo |
   | **90×29** | 90 × 29 mm | **Brother QL-700**, rolo **DK-1201** |

2. **Papel:** impressora de etiquetas (uma por página, no tamanho exato) **ou** folha A4 com várias etiquetas.
3. **Cópias:** de 1 a 60. Na folha avulsa, as cópias viram **sequência** (D00019, D00020…).
4. **Observação:** até 30 caracteres, opcional.
5. Confira a **frase grande acima da prévia**. Ela diz exatamente o que será impresso, por exemplo: *"Etiqueta de: F023-P0011 · Residência Riviera · … · volume 1 de 1"*.
6. Clique em **Imprimir**.

### Na janela de impressão do navegador
Para a **Brother QL-700** com o rolo DK-1201, configure:

- Impressora: **Brother QL-700**
- Papel: **29 mm × 90 mm**
- Orientação: **paisagem**
- Margens: **nenhuma**
- Escala: **100%**

O painel lembra o último **formato** e o **papel** escolhidos **por pessoa**: valem em qualquer computador em que você entrar com o seu login (UX-25). A impressora em si é escolhida na janela de impressão do navegador, que lembra a última usada.

### Ao fim do lote: "Etiquetar e guardar" (UX-25)
Depois de aprovar ou publicar, o **Próximo passo** da página do projeto tem o botão **Etiquetar e guardar**. Ele abre Etiquetas já com o fundo e o projeto escolhidos: é só clicar em **Imprimir** (2 cliques a partir do projeto).
No passo **3 · Onde guardar**, o painel diz quantas folhas do projeto ainda estão sem lugar e sugere a caixa: a que já guarda o projeto ou a **próxima CX-### livre**. **Guardar nesta caixa** cria a caixa (se ainda não existe, no fundo do projeto) e coloca nela **só as folhas sem lugar**; as que já têm lugar não mudam. Depois, **Imprimir etiqueta da caixa**.

### Impressas (histórico e reimprimir)
A aba **Impressas** lista as últimas 100 etiquetas impressas: quando, qual etiqueta, formato, quantas e quem imprimiu. **Reimprimir** volta a etiqueta exatamente como saiu (projeto, folha ou caixa, material, volume, formato e papel); confira a prévia e clique em **Imprimir**.
O Painel inicial mostra, discreto, no fim de **O que fazer agora**, **"N folhas publicadas sem lugar"**: folhas que o público já vê e que ainda não têm caixa.

---

## 5. Etiquetar a caixa (onde o material mora)

1. Menu **Onde está guardado** (atalho **9**) → **Nova localização**.
2. Escolha o tipo: **caixa, gaveta, tubo, mapoteca ou estante**. O painel sugere o próximo identificador livre:

   | Tipo | Modelo |
   |---|---|
   | Caixa | `CX-001` |
   | Gaveta | `GV-01` |
   | Tubo | `TB-001` |
   | Mapoteca | `MAP-01-G01` |
   | Estante | `EST-01` |

3. Escolha o fundo. **Deixe vazio** se o recipiente é **compartilhado** entre fundos.
4. Abra o local → **Alocar folhas aqui**. Busque o projeto e marque as folhas, ou cole os códigos um por linha. Clique em **Alocar**. Alocar de novo em outro lugar **substitui** o lugar anterior.
5. Depois de alocar, clique em **Imprimir etiqueta da caixa**. A etiqueta sai como `F026-CX-001` (ou só `CX-001`, se for compartilhada).
6. **Cole a etiqueta na caixa**, na frente e visível quando ela estiver na estante.

---

## 6. Colar a etiqueta no material

> Esta seção é **boa prática geral de conservação**, não uma regra tirada do painel. Confirme com a equipe de acervo se vocês têm um padrão próprio de onde colar.

- **Pasta de projeto:** na aba ou na frente da pasta, onde dá para ler sem abrir. **Não cole sobre o carimbo original** nem sobre nenhuma inscrição do documento.
- **Nunca cole direto no documento.** Use pasta, caixa, tubo ou envelope. Etiqueta adesiva em papel antigo é dano.
- **Caixa:** frente e lateral, na altura dos olhos.
- **Tubo:** na lombada, na vertical (formato 20×140).
- **Etiqueta errada ou rasgada:** reimprima. O código não muda: o painel gera o mesmo código sempre.

---

## 7. Ler a etiqueta com o celular

Menu **Ler etiqueta / Estante** (atalho **X**). Funciona melhor no celular.

1. Toque em **Ler com a câmera** e aponte para o código de barras. O celular vibra a cada leitura. Sem câmera, digite o código e toque em **Abrir**.
2. O painel entende:
   - código de **fundo** (`F026`) → abre o fundo;
   - código de **projeto** (`F026-P0001`) → abre o projeto;
   - código de **folha** → abre a folha;
   - etiqueta de **pasta** (`SBU-P011.1`) → abre o projeto, volume 1;
   - etiqueta de **caixa** (`F026-CX-001`, ou só `CX-001`) → abre a **conferência da caixa**.
3. Se o mesmo identificador existe em mais de um fundo, o painel mostra as opções.

### Conferir uma caixa
1. Leia a etiqueta da caixa. A tela mostra o que **deveria** estar lá.
2. Leia as pastas (ou folhas) que estão dentro. Cada leitura é classificada:
   - **verde:** conferida;
   - **amarelo:** falta ler;
   - **vermelho:** é de **outro lugar** (use **Mover para cá** se for o caso);
   - **não reconhecida:** a leitura não bateu com nenhum código.
3. Clique em **Registrar conferência** para gravar no histórico.

Ler **não muda nada** no cadastro. Só **Mover para cá** muda.

---

## 8. Se algo der errado

| Sintoma | O que fazer |
|---|---|
| A etiqueta sai cortada ou com margem | Na janela de impressão: papel 29×90 mm, paisagem, **sem margens**, escala 100% |
| Sai uma etiqueta por folha A4 | Escolha **A4 com várias** em "Papel", ou a impressora de etiquetas certa |
| O celular não lê o código | Limpe a lente, afaste um pouco, evite reflexo. Se não ler, digite o código |
| "Não achei nada com o código…" | A etiqueta foi lida incompleta, ou o código não existe. Confira o código por extenso, impresso embaixo do código de barras |
| Aparece "sem cidade" ou "sem data" | Falta dado no projeto. Corrija o cadastro e imprima de novo |
| A tela abriu o login em vez das etiquetas | O navegador não está logado no painel. Faça o login e abra de novo |
| O código do fundo tem sigla errada | A sigla de 3 letras **não muda** depois de criada. Fale com o admin |
| Caixa com código repetido em dois fundos | Escolha o fundo certo na leitura. Caixas compartilhadas ficam sem fundo |

---

## 9. Checklist rápido

**Ao finalizar o lote (F10)**
- [ ] Abra o painel → **Etiquetas** (tecla **T**) e escolha o fundo e o projeto
- [ ] Confira a frase acima da prévia: projeto, arquiteto, cidade e ano
- [ ] Formato **90×29** (Brother) ou o formato da sua impressora
- [ ] Na janela de impressão: papel 29×90 mm, paisagem, sem margens, escala 100%
- [ ] Imprimir e colar na pasta, não no documento

**Ao guardar**
- [ ] A caixa existe em **Onde está guardado** e as folhas estão alocadas
- [ ] Etiqueta da caixa impressa e colada
- [ ] Leia a etiqueta da caixa no celular para confirmar que abre a conferência

---

## 10. Glossário

| Termo | Significa |
|---|---|
| **Code 39** | Tipo de código de barras usado nas etiquetas. Lê com qualquer leitor comum |
| **Volume** | Cada pasta ou parte física de um mesmo projeto ("volume 1 de 3") |
| **Local / localização** | Onde o material mora: caixa, gaveta, tubo, mapoteca ou estante |
| **Alocar** | Registrar no painel que determinadas folhas estão num determinado local |
| **Conferência** | Ler o que está dentro de uma caixa e comparar com o que o painel espera |
| **Compartilhado** | Local sem fundo, que guarda material de mais de um fundo |
| **Brother QL-700** | Impressora de etiquetas usada com o rolo DK-1201 (29 × 90 mm) |
