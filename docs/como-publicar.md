# Como publicar no painel

O painel mostra isto também dentro das telas: o quadro **"Como publicar este fundo"** (página do fundo), **"Como publicar este arquiteto"**
(formulário do arquiteto), o painel **"Publicação"** (página do projeto) e o botão **?**. Cada quadro marca o que já está feito e o que falta, com o botão que resolve.
Vocabulário: ver `vocabulario.md` (Não publicado · Rascunho · Publicado · Despublicado).

## Publicar um FUNDO
1. **Reservar o fundo** — Fundos → "Novo fundo". O código (F0xx) e a sigla de 3 letras não mudam depois.
2. **Escrever a história e a procedência** — fundo → Editar. Só entra história com a fonte citada.
3. **Vincular o arquiteto ou produtor** — no fundo, "Agentes (proveniência)" → Vincular.
4. **Definir os direitos** — no fundo, "Direitos e licença" → Editar: situação *Autorizado*, titular e o documento do termo. **Sem isso nada é publicado.**
5. **Autorizar cada projeto** — em cada projeto, painel "Publicação" → *Autorizar publicação*. Autorizar não publica sozinho.
6. **Enviar as folhas ao site** — no projeto, *Enviar folhas ao site* (ficam como rascunho); *Importar folhas só no site* se elas vieram do site.
7. **Publicar** — no projeto: painel "Publicação" → *Publicar*. Ou, no fundo, *Publicar* para todos os projetos prontos (só admin master).
8. **Conferir** — *Ver página pública* no projeto. Publicar deixa o projeto visível no site na hora.

## Publicar um ARQUITETO
**O painel não publica arquiteto no site.** O campo "Status" do arquiteto é só um marcador interno. O arquiteto aparece no site quando
algum fundo dele tem projeto publicado **e** ele está ativo no plugin do WordPress.
1. **Cadastrar o arquiteto** — Arquitetos → Novo agente: nome na forma autorizada (como aparece no site), datas de existência, grafias de carimbo.
2. **Biografia, com fonte** — abrir o arquiteto → Editar.
3. **Vincular ao fundo** — o arquiteto precisa de pelo menos um fundo.
4. **Publicar projetos do fundo** — sem projeto publicado ele não aparece.
5. **Completar no WordPress** — wp-admin → CAMP Acervo → Arquitetos: enviar a foto, escrever a biografia e **ativar**. O painel não faz esta parte.
6. **Conferir** — a página fica em `/acervo/arquitetos/NOME/`; o painel mostra se a encontrou no espelho do site.

> A regra do arquiteto (visibilidade e ativação no plugin) vem da documentação do plugin da CAMP; confira no wp-admin se algo diferente acontecer.

## Enviar fundo ao site (CAMP-015)
Na página do fundo, em "Como aparece no site", o botão **Enviar fundo ao site** cria/atualiza o termo da taxonomia e a página-hub do arquiteto com o que está **preenchido** no painel: texto do fundo (procedência, entrada, acesso...), biografia, fontes da biografia e foto do arquiteto titular. Campo vazio no painel não vai (o site ignora vazio; texto escrito à mão no WordPress não é sobrescrito). Para **apagar** um campo no site o painel manda o valor especial `"__limpar__"` (apagar a biografia, remover a foto, esvaziar a biografia no editor).
O fundo mostra se a página do arquiteto está **pública** no site (lido do espelho) e a divergência painel × site (o que mudou no painel desde o último envio; o painel não consegue ler o hub no site). O plano de publicação do projeto avisa, sem bloquear, quando o fundo não tem página pública do arquiteto.
