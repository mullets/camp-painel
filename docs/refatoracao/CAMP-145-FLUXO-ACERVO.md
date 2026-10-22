# CAMP-145 — Refatoração dos fluxos de acervo com UI/UX coerente

**Estado:** plano de execução e contrato de regressão. **Nenhuma automação operacional é habilitada por este documento.**  
**Base auditada:** main em `d8552bb` (22/10/2026).  
**Branch de trabalho:** `refactor/camp145-acervo-sem-mudar-visual`.

## 1. Objetivo e princípio

O painel é a **fonte da verdade do acervo**: localização e arquivos no QNAP, identidade arquivística, revisões e o que está efetivamente publicado no WordPress/Tainacan. O usuário cuida de **um acervo**, não de dois cadastros.

**Fluxo-alvo (CAMP-145):** duas decisões na estação (F9 escolher/criar projeto e F10 terminar), processamento e importação automáticos, revisão humana SOMENTE dos avisos, uma ação de publicar; correções no painel propagadas ao site sem entrar no wp-admin.

**Diretriz de UI/UX (22/10/2026, decisão posterior):** melhorar a experiência interna quando houver ganho demonstrável, mantendo identidade visual, linguagem, tokens, componentes, tipografia e hierarquia coerentes com a CAMP. É permitido ajustar disposição, densidade, hierarquia, estados, navegação e interações; mudanças devem ser deliberadas, demonstradas por prints antes/depois, testadas em desktop/mobile e claro/escuro, e revisadas por acessibilidade. Não redesenhar a marca nem criar um segundo design system. Nenhuma alteração de `frontend/index.html` nesta primeira etapa.

## 2. Caminho canônico

```text
ESTAÇÃO (Windows/Mac)
  F9 buscar/criar projeto → digitalizar → F10 finalizar
                │
                ▼
QNAP (originais preservados / lote pronto)
                │
                ▼
CAMP Vision 2 (OCR, título, ano, orientação, duplicatas, ressalvas)
                │  aviso; se o aviso falhar, coletor reconcilia
                ▼
PAINEL (importação idempotente e rastreada)
                ├─ sem aviso → conferida automaticamente + evento
                └─ com aviso → pessoa confere só a folha necessária
                                │
                                ▼
                     PRONTO PARA PUBLICAR
                                │
                         1 ação autorizada
                                ▼
WORDPRESS/TAINACAN (dossiê, folhas elegíveis, arquiteto)
                                │
                                ▼
PAINEL (espelho, confirmação, pendências e reenvio)
```

As etapas relativas a F9/F10, OCR, arquivos de contrato e site envolvem os outros repositórios; não alterar a interface entre eles sem versionar os contratos em `docs/CONTRATO_UNICO.md` e `tests/contrato/`.

## 3. Contrato de experiência que NÃO se perde

1. A estação lembra os últimos dados pertinentes; não exige caminho do NAS, código digitado nem nova pergunta ao finalizar.
2. O número do fundo/projeto vem sempre da autoridade do painel; nunca do nome de pasta; jamais é reutilizado. Reidentificar cria redirecionamento.
3. Importação não duplica folhas, decisões, lotes, eventos ou publicações em caso de reenvio/reinício.
4. Uma folha sem alerta vai para conferida com **origem automática e trilha de auditoria**; aviso nunca é descartado silenciosamente.
5. O operador recebe primeira folha com aviso e motivo legível; sempre a mesma contagem em Fila, Projetos, detalhe e Precisa de você.
6. Os cinco estados para pessoas são: **Chegando → Para conferir → Pronto para publicar → No site**; **Com problema** informa o motivo e a solução.
7. A ação única de publicação deve aprovar e autorizar de acordo com a permissão configurada, enviar apenas folhas elegíveis e publicar o arquiteto quando necessário.
8. Folha retida, duplicata ou com bloqueio individual fica fora; os demais itens elegíveis publicam. O projeto inteiro só deve ser impedido pelos quatro motivos do CAMP-145: **restrição de direitos registrada, projeto sem título, bloqueio humano no projeto, lote de teste**. A elegibilidade e autorização devem ser conferidas novamente no servidor, nunca só na tela.
9. Toda alteração local de metadado/imagem já publicada precisa ser entregue ao site, auditada, reconciliada e repetida com segurança se falhar.
10. A pessoa não precisa entrar no WordPress para executar trabalho do acervo.

**Nota de integridade:** "Desfazer" uma publicação exige operação compensatória real no WordPress e verificação do estado final; não é possível desfazer visualização ou download já ocorrido. Nunca mostrar sucesso de desfazer por um timer local. Nenhuma publicação pública deve ignorar restrição registrada.

## 4. Estado do código em 22/10/2026

| Responsabilidade | Local atual | Diagnóstico |
| --- | --- | --- |
| Selecionar estágio/lote ativo | `filas_fase.py`, `rotas_revisao.py` | Regra duplicada (primeira extração desta branch) |
| Importar lote sem pessoa | `importar_sozinho.py` | Implementado, config `importacao.automatica=0` |
| Conferir sem aviso | `rotas_revisao.py` | Implementado, config `revisao.conferir_so_avisos=0` |
| Publicar em 1 passo | `publicacao_guiada.py`, `rotas_publicar_tudo.py` | Implementado, config `publicacao.publicar_um_passo=0` |
| Propagar correção ao site | `alteracoes_site.py`, `publicador.py` | Envio imediato habilitado por padrão, com falhas silenciosas e reenvio manual possível |
| Decidir elegibilidade | `publicacao.py` | Preservar restrições, crédito de autoria não confirmada e a regra de folha individual |
| Atualizar o espelho do WP | `sincronizador.py` | Reconciliar sem sobrescrever arbitrariamente a autoridade local |
| Acompanhar progresso de publicação | `rotas_publicar_tudo.py` | Há tarefa durável no banco; execução ainda depende de thread no processo |
| Interface | `frontend/index.html` (~1,2 MB) | Preservar pixels; separar JS/CSS só com baseline e testes comparativos |
| Fluxos de estação | outros repositórios | Escopo transversal, exige compatibilidade com versões antigas |

**Importante:** a existência no código não comprova configuração de produção, integração real nem garantia de entrega. Não ligar flags por migração ou por refatoração.

## 5. Sequência de refatoração

### Fase 0 — Congelar o comportamento observável
- Registrar respostas e eventos dos endpoints, dados reais *anonimizados* e fixtures de lotes normais, problemáticos, incompletos e reiniciados.
- Tirar screenshots determinísticos de desktop e celular, claro/escuro, todos os estados críticos: Fila, Projetos, Fundo, Projeto, Folha, Publicação, Máquinas, configurações e erros. Aprovar diferenças intencionais de UX e barrar as acidentais.
- Comparar DOM, texto, estilos computados, foco, teclado e capturas pixel a pixel no mesmo ambiente. O teste `p16_estilos_iguais.js` já captura seis telas; **não substitui** screenshots ou uma auditoria de interação.
- Congelar rotas, payloads, permissões e contratos das cinco aplicações.

### Fase 1 — Núcleo da situação do acervo
- Um seletor determinístico para o lote ativo; o mais recente pendente prevalece, mesmo se houver um lote mais novo já publicado.
- Uma única política das cinco situações, consumida sem divergência por Fila, projeto e resumo.
- Testes com lote vazio, sem folhas, pendente, aprovado, publicado, com erro e descartado.
- **Primeira entrega desta branch:** unificação da escolha de lote entre Fila e detalhe, sem mudança na API e sem tocar no HTML/CSS.

### Fase 2 — Entrada, importação, conferência
- Job reconciliador de QNAP, nunca varredura SMB em requisição.
- Evento de lote recebido, com identificador idempotente, reprocessamento seguro e diagnóstico de pacote ausente/corrompido.
- Centralizar classificação de alertas: duplicata, autoria, ressalva, bloqueio, espelho e falhas ilegíveis.
- Conferir folhas limpas transacionalmente após importação, com ator automático e histórico; qualquer sinal incerto exige humano.
- Testes de 48 folhas/3 avisos, 0 avisos, 48 avisos, dupla entrega, reinício e interrupção.

### Fase 3 — Publicação
- Plano somente leitura e motor de execução separado da API e da UI.
- Máquina de estados durável por projeto; eventos com chave idempotente; retry com backoff e observabilidade.
- Ações sobre WP/Tainacan devem ser repetíveis sem duplicar o dossiê nem as folhas.
- Pré-condições revalidadas antes e durante o envio: os quatro bloqueios globais, as exclusões de folha, papéis e restrições humanas.
- Progresso verdadeiro `N de total`, conclusão confirmada no WordPress e compensação explícita de despublicação; sem `sucesso` prematuro.
- Publicar vários projetos usa a MESMA rotina por projeto; falha de um não deve derrubar os outros.

### Fase 4 — Sincronização permanente e reconciliação
- Criar fila durável (outbox) para metadados e imagens alterados, não depender de uma thread ou de editar de novo.
- Registrar campo, versão, tentativas, erro, carimbo de confirmação e correspondência local/WP.
- Backoff, idempotência, recuperação depois de queda, sinalização de divergência e reenvio sem abrir WP.
- Comparar acervo local, índices do painel, espelho e WordPress. Não apagar originais ou reescrever autoria automaticamente.
- Verificar integridade do NAS, presença de TIFF/DNG/JPG, hashes conhecidos, réplica e estado da publicação. Preservar material arquivístico.

### Fase 5 — Refatorar a interface e aperfeiçoar UI/UX sem romper a identidade
- Extrair serviços de domínio, casos de uso, adaptadores QNAP/CV2/WP e persistência. Rotas são finas.
- Só modularizar `index.html` depois do baseline: preservar contratos, tokens, acessibilidade, ordem de carregamento e comportamento. Substituir scripts gradualmente e comparar.
- Melhorias de UI/UX são permitidas: hierarquia de informação, filtros, busca, tarefas, estados de sincronização, revisão e responsividade; sem criar uma segunda identidade visual. Registrar antes/depois, rationale, teste de regressão e critério de aceite.
- O trabalho de interface está planejado nos tickets REF-021 a REF-029 e REF-031 do quadro CAMP Acervos — Painel de administração.

### Fase 6 — Homologação e implantação
- `python3 -m unittest tests/test_fluxo_acervo.py` + `python tests/teste_backend.py --rapido` + suíte completa + `python scripts/check_ui.py`.
- `bash tests/rodar_auditoria.sh`, `bash tests/rodar_fluxo_real.sh` e exaustão com WordPress falso e cenários de queda de rede.
- Testar contrato com estação Windows, Mac, CV2 e `camp-wordpress`, inclusive clientes em versão anterior.
- Auditoria visual aprovada **sem diferenças inesperadas** (mudanças intencionais têm aprovação documentada) e backup restaurável verificado **antes** de qualquer merge.
- Somente o responsável autoriza PR/merge; `main` tem atualização de produção. Não executar scripts de deploy, tocar no QNAP real nem ativar flags nesta branch.

## 6. Critérios de conclusão

- F9 e F10 são as únicas decisões da estação no caminho feliz.
- 48 folhas, 3 com avisos: no máximo 3 conferências humanas, com histórico para as outras 45.
- Publicação individual e em lote usam o mesmo motor e as mesmas regras de direitos.
- Quando WordPress falha, a operação aparece como pendente e volta automaticamente até ser confirmada.
- Edição de metadados/imagem publicada propaga e reconcilia, sem divergência silenciosa.
- QNAP continua com os originais; sem perda de metadados, identidade, arquivo ou audit trail.
- 0 regressões visuais inesperadas; mudanças de UX aprovadas, consistentes e documentadas antes/depois.
- Sem mudanças de contrato inesperadas, sem migração destrutiva, sem alteração em produção.

**Esta branch inicia a Fase 1. As Fases 0 (baseline completo) e 2–6 são trabalho futuro, não estão concluídas por criar este documento.**

## 7. Gestão no Trello (22/10/2026)

- Quadro reutilizado: https://trello.com/b/uoFbT5xV/camp-acervos-painel-de-administra%C3%A7%C3%A3o (novo quadro bloqueado pelo limite do workspace; cartões antigos preservados).
- Tickets REF-000 a REF-039; REF-011 em implementação, demais planejados.
- Trabalho já especificado nos tickets CAMP-145 a CAMP-160 continua como dependência/histórico, não foi reaberto automaticamente.
- Alterações visuais de UI/UX devem seguir REF-002, REF-028 e REF-034.

