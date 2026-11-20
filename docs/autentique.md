# Assinatura eletrônica pela Autentique (contratos de doação de acervo)

Com isto ligado, o contrato de uma doação de acervo é criado sozinho na Autentique quando você clica em **Enviar contrato para
assinatura** e anexa o PDF. O link de assinatura vai no e-mail do contrato da CAMP (TR30, pelo Sender). Quando todos assinam, a doação
passa sozinha a **Contrato assinado pelas partes**, com a data da última assinatura.

## Configurar (uma vez)

1. Crie a conta da CAMP em **autentique.com.br**. O plano grátis serve: 10 documentos por mês, com a API inclusa, e PDF de até 5 MB.
2. Na Autentique, abra o **perfil → API** e clique para gerar o token. Copie o token.
3. No painel, abra **Doações de acervo** e, no fim da tela, **Assinatura eletrônica (Autentique)**.
4. Cole o token e clique em **Testar conexão**. Deve aparecer "Conexão com a Autentique funcionando (conta …)".
5. Se alguém da CAMP também precisa assinar, ponha o e-mail em **E-mail de quem assina pela CAMP** (opcional).
6. Marque **Ligada** e clique em **Salvar**.

O token fica guardado como dado sensível: não aparece mais na tela (só "configurado"), nem no log. Para trocar, cole outro e salve.
**Apagar o token** desliga tudo.

## No dia a dia

1. Abra a doação e clique em **Enviar contrato para assinatura**.
2. Na prévia, deixe marcado **Anexar o PDF do contrato** e escolha o arquivo (só PDF, até 5 MB).
3. Confira o resto (valor, prazo, "Gerar a cobrança junto") e clique em **Enviar**.

O painel cria o documento na Autentique e manda o e-mail do contrato (TR30) com o link dela. A cobrança segue igual: sai em outro
e-mail (TR27), se a caixa estiver marcada.

- Se a Autentique recusar (token errado, acabaram os documentos do mês, arquivo grande demais, Autentique sem resposta), **nada é
  enviado** e a tela diz o motivo. Você pode colar um link de outro serviço e enviar do jeito de antes.
- Se o documento foi criado mas o e-mail não saiu (por exemplo, falta o modelo TR30 no Sender), arrume e envie de novo **com o mesmo
  PDF**: o painel reaproveita o documento e não gasta outro do mês.
- O painel confere as assinaturas sozinho a cada busca no site (de 10 em 10 minutos, `doacoes_acervo.coleta_min`). Para não esperar,
  use **Conferir assinatura agora** no detalhe da doação.
- Se a doação já está em cobrança quando todos assinam, a etapa não volta: o painel só guarda a data da assinatura.
- Se alguém recusar na Autentique, a doação mostra "Recusado na Autentique" e a etapa não muda: fale com a pessoa.

## Onde fica a assinatura

Não precisa marcar nada no PDF. A Autentique acrescenta uma **página de assinaturas** no fim (quem assinou, data e hora, código de
verificação) e o painel pede o **rodapé de autenticação em todas as páginas** (`footer: BOTTOM`), para que nenhuma página do meio
possa ser trocada.

## Quem recebe e-mail da Autentique

- **Quem doa não recebe e-mail da Autentique**: entra no documento só pelo nome, e o link vai no e-mail da CAMP (TR30). Assim a pessoa
  recebe uma mensagem só, com a cara da CAMP.
- **Quem assina pela CAMP** (se configurado) recebe o link por e-mail da própria Autentique.
- No fim, a Autentique pode mandar o documento assinado a quem tem e-mail no documento (configuração da conta na Autentique).

## Desligar

Desmarque **Ligada** e salve. A prévia volta a ter só o link colado, e o painel para de conferir assinaturas. Os documentos já criados
continuam na Autentique.
