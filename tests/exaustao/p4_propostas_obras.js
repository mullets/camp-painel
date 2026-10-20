// CAMP-125 e CAMP-126 (20/10, página do projeto F026-P0009 CRASA). Pelo caminho real (estação reserva, CAMP Vision grava a pasta e avisa;
// tests/exaustao/p4_montar.py) e clicando como uma pessoa:
//  CAMP-125: a sugestão "UF: SP" tem "Usar" à vista (no cartão Dados, sem abrir nada) e grava SP com 1 clique; as 31 propostas aparecem como
//            "31 propostas sem resposta" e se resolvem rápido: tabela (folha, o que é, proposta, hoje), A/R no teclado seguindo para a próxima,
//            "Aceitar as N onde hoje está vazio", "Recusar as restantes"; nada que alguém escreveu é trocado; o contador some no zero; < 1 minuto.
//  CAMP-126: o aviso "8 obras distintas… propostas.obras_na_pasta" vira decisão sem jargão: 8 grupos por código de unidade com miniaturas e nº de
//            folhas; o cartão Dados diz "1 decisão pendente"; "São partes do mesmo conjunto" fecha com 1 clique e fica no Histórico;
//            "Separar em outro projeto…" (admin) abre o Mover folhas com o grupo já marcado e move para um projeto do mesmo fundo.
// Rodar: EXAUSTAO_PORTA=8974 bash tests/rodar_exaustao.sh tests/exaustao/p4_propostas_obras.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (P) => execFileSync('python3', [path.join(__dirname, 'p4_montar.py'), 'pronto', T.BASE, T.RAIZ, P], { encoding: 'utf-8' });
const novoProjeto = (nome) => { const P = T.cv2('reservar', T.BASE, 'F026', nome, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, nome); montar(P); return P };
const abrirLotes = async (pg, P) => { await T.abrirProjeto(pg, P); if (!(await pg.isVisible('.pj-gav[data-gav="folhas"]'))) await pg.click(`#pj-cards [data-pjc-gav="folhas"]`); await pg.waitForSelector('#pj-cv .cv-resumo', { timeout: 15000 }) };

T.rodar(async () => {
  T.passo('preparo: dois lotes como o da CRASA, pelo caminho real');
  const PA = novoProjeto('CRASA STO ANDRE'), PB = novoProjeto('CONJUNTO OUTRO'), PC = T.cv2('reservar', T.BASE, 'F026', 'EDIFICIO SEPARADO', '1972');
  T.chk(T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PA) === 34, `o aviso do CAMP Vision trouxe as 34 folhas de ${PA}`);
  const op = await T.entrar('operador');

  T.passo('CAMP-125: sugestão "UF: SP" à vista e com 1 clique');
  await T.abrirProjeto(op, PA);
  const ufBt = `#pj-cards .pjc[data-pjc="dados"] [data-cv-resp="sugestao"][data-chave="uf"]`;
  T.chk(await T.espera(() => op.isVisible(ufBt)), 'CAMP-125: o cartão Dados mostra "Usar UF SP" sem abrir nada', await T.txt(op, '#pj-cards .pjc[data-pjc="dados"]'));
  await T.print(op, 'dados_sugestao_uf');
  if (await op.$(ufBt)) await op.click(ufBt);
  T.chk(await T.espera(() => T.um('SELECT uf FROM projeto WHERE codigo=?', PA) === 'SP'), 'CAMP-125: 1 clique e a UF do projeto vira SP', T.um('SELECT uf FROM projeto WHERE codigo=?', PA));
  T.chk(await T.espera(async () => !(await op.$(ufBt))), 'CAMP-125: a sugestão some depois de usada');

  T.passo('CAMP-125: 31 propostas resolvidas rápido, sem trocar nada escrito');
  await abrirLotes(op, PA);
  const resumo = await T.txt(op, '#pj-cv .cv-resumo');
  T.chk(/31 propostas sem resposta/.test(resumo), 'CAMP-125: o resumo diz "31 propostas sem resposta" (8 obras + 23 da tabela)', resumo);
  const t0 = Date.now(), antes = JSON.stringify(T.sql('SELECT codigo, titulo, ano_folha, pendencias, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo', PA));
  await op.click('#pj-cv [data-cv-abrir="propostas"]').catch(() => {});
  const nLinhas = await op.$$eval('#pj-cv .cvp-tab tr[data-cvp]', l => l.length).catch(() => 0);
  T.chk(nLinhas === 23, `CAMP-125: as propostas viram uma tabela (folha, o que é, proposta, hoje): ${nLinhas} linhas`);
  T.chk(/Folha.*O que é.*Proposta do CAMP Vision.*Hoje/.test(await T.txt(op, '#pj-cv .cvp-tab thead')), 'CAMP-125: colunas folha, o que é, proposta e hoje');
  await T.print(op, 'propostas_tabela');
  // teclado: A na primeira, R na seguinte, o foco segue sozinho
  const l1 = await op.$eval('#pj-cv .cvp-tab tr[data-cvp]', t => t.dataset.cvp);
  await op.focus(`#pj-cv tr[data-cvp="${l1}"]`); await op.keyboard.press('a');
  T.chk(await T.espera(() => T.um("SELECT acao FROM cv_resposta WHERE tipo='proposta' AND chave=?", l1) === 'aceitar'), 'CAMP-125: tecla A aceita a proposta da linha');
  const l2 = await op.evaluate(() => (document.activeElement && document.activeElement.dataset) ? document.activeElement.dataset.cvp : null);
  T.chk(!!l2 && l2 !== l1, 'CAMP-125: depois de responder, o foco vai para a próxima proposta sem resposta', String(l2));
  if (l2) { await op.keyboard.press('r'); T.chk(await T.espera(() => T.um("SELECT acao FROM cv_resposta WHERE tipo='proposta' AND chave=?", l2) === 'recusar'), 'CAMP-125: tecla R recusa') }
  // em lote
  const vazBt = '#pj-cv [data-cvp-lote="vazias"]';
  const nVaz = +((await T.txt(op, vazBt)).match(/Aceitar as (\d+) onde hoje está vazio/) || [0, -1])[1];
  T.chk(nVaz === 13, `CAMP-125: botão "Aceitar as 13 onde hoje está vazio" (15 vazias menos as 2 já respondidas no teclado): ${nVaz}`, await T.txt(op, '#pj-cv .cvp-lote'));
  await op.click(vazBt);
  await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE tipo='proposta' AND projeto_codigo=?", PA) >= 15);
  const vazAceitas = T.sql("SELECT chave FROM cv_resposta WHERE tipo='proposta' AND acao='aceitar' AND projeto_codigo=?", PA).length;
  T.chk(vazAceitas === 14, `CAMP-125: aceitou só as vazias (13 do botão + 1 da tecla A; as 8 com código já escrito ficam): ${vazAceitas}`);
  await op.click('#pj-cv [data-cvp-lote="resto"]'); await T.confirmar(op);
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE tipo='proposta' AND projeto_codigo=?", PA) === 23), '"Recusar as restantes" responde o resto (23 de 23 na tabela)');
  T.chk(T.sql("SELECT chave FROM cv_resposta WHERE tipo='proposta' AND acao='aceitar' AND projeto_codigo=? AND chave LIKE 'sem_codigo_de_unidade:%'", PA).every(r => +r[0].split(':')[1] < 15),
    'CAMP-125: nenhuma proposta com "hoje" preenchido foi aceita sem um clique explícito nela');
  T.chk(JSON.stringify(T.sql('SELECT codigo, titulo, ano_folha, pendencias, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo', PA)) === antes, 'CAMP-125: responder não mexeu em nenhuma folha (só registra)');
  const rs1 = await T.txt(op, '#pj-cv .cv-resumo');
  T.chk(!/propostas? sem resposta/.test(rs1) && /decidir: obras distintas na pasta/.test(rs1), 'CAMP-125: com a tabela toda respondida, o resumo não diz mais "propostas sem resposta": só falta decidir as obras', rs1.slice(-160));
  await T.print(op, 'propostas_respondidas');

  T.passo('CAMP-126: "8 obras distintas" vira uma decisão sem jargão');
  const cartaoDados = await T.txt(op, '#pj-cards .pjc[data-pjc="dados"]');
  T.chk(/1 decisão pendente/.test(cartaoDados), 'CAMP-126: o cartão Dados diz "1 decisão pendente" (não "Em ordem")', cartaoDados);
  const corpo = await op.evaluate(() => document.getElementById('pd').innerText);
  T.chk(!/obras_na_pasta|propostas\.|sem_codigo_de_unidade|codigo_unidade/.test(corpo), 'CAMP-126: nenhum nome de campo interno aparece na tela', (corpo.match(/.{30}(obras_na_pasta|propostas\.|codigo_unidade).{30}/) || [''])[0]);
  const ob = await T.txt(op, '#pj-cv [data-cv-obras]');
  T.chk(/8 códigos de unidade diferentes/.test(ob) && /mesmo conjunto/.test(ob), 'CAMP-126: o texto explica (8 códigos de unidade; mesmo conjunto ou projetos diferentes)', ob.slice(0, 200));
  const grupos = await op.$$eval('#pj-cv [data-cv-obra]', l => l.map(g => [g.dataset.cvObra, g.querySelectorAll('img').length, g.innerText]));
  T.chk(grupos.length === 8 && grupos.every(g => g[1] === 3 && /3 folhas/.test(g[2])), 'CAMP-126: 8 grupos, cada um com o código de unidade, as miniaturas e o nº de folhas', JSON.stringify(grupos.map(g => [g[0], g[1]])));
  T.chk(await T.imgOk(op, '#pj-cv [data-cv-obra] img'), 'CAMP-126: as miniaturas dos grupos carregam');
  T.chk(!(await op.$('#pj-cv [data-obras-separar]')), 'CAMP-126: o operador não vê "Separar" (mover é de admin); vê o aviso para pedir a um admin', ob.slice(-120));
  await T.print(op, 'obras_decisao');
  await op.click('#pj-cv [data-obras-decidir="mesmo_conjunto"]');
  T.chk(await T.espera(() => T.um("SELECT valor FROM cv_resposta WHERE chave='obras:decisao' AND projeto_codigo=?", PA) === 'mesmo_conjunto'), 'CAMP-126: "São partes do mesmo conjunto" decide com 1 clique');
  T.chk(await T.espera(async () => /✔ As folhas são partes do mesmo conjunto/.test(await T.txt(op, '#pj-cv [data-cv-obras]'))), 'CAMP-126: o aviso sai e fica a marca da decisão');
  T.chk(await T.espera(async () => !/decisão pendente/.test(await T.txt(op, '#pj-cards .pjc[data-pjc="dados"]'))), 'CAMP-126: o cartão Dados deixa de dizer "decisão pendente"', await T.txt(op, '#pj-cards .pjc[data-pjc="dados"]'));
  const seg = (Date.now() - t0) / 1000;
  T.chk(seg < 60, `CAMP-125: as 31 propostas (23 da tabela + as 8 obras numa decisão) resolvidas em ${seg.toFixed(1)} s (menos de 1 minuto)`);
  const rs = await T.txt(op, '#pj-cv .cv-resumo');
  T.chk(!/propostas? sem resposta/.test(rs) && !(await op.$('#cv-sec-propostas')), 'CAMP-125: o contador some no zero (nem no resumo nem a seção)', rs);
  T.chk(T.um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='cv_obras_mesmo_conjunto'", PA) === 1, 'CAMP-126: a decisão fica no Histórico do projeto (evento)');
  await op.evaluate(c => showProjeto(c, 'historico'), PA); await op.waitForTimeout(1500);
  T.chk(/obras distintas: são partes do mesmo conjunto/.test(await T.txt(op, '#pd')), 'CAMP-126: o Histórico mostra "obras distintas: são partes do mesmo conjunto"');

  T.passo('CAMP-126: "Separar em outro projeto…" (admin) abre o Mover folhas com o grupo marcado');
  const ad = await T.entrar('admin');
  await abrirLotes(ad, PB);
  T.chk(/1 decisão pendente/.test(await T.txt(ad, '#pj-cards .pjc[data-pjc="dados"]')), 'CAMP-126: no outro projeto, o cartão Dados também diz "1 decisão pendente"');
  await ad.click('#pj-cards [data-obras-abrir]');
  T.chk(await T.espera(() => ad.isVisible('#d-body [data-cv-obras="pendente"]')), 'CAMP-126: "Decidir" no cartão Dados abre a decisão das obras');
  await ad.click('#d-body [data-obras-separar="BL-C"]');
  T.chk(await T.espera(async () => /Mover folhas/.test(await T.txt(ad, '#d-title'))), 'CAMP-126: abre o Mover folhas');
  const marcadas = await ad.$$eval('#d-body .mx-it:checked', l => l.map(c => c.value.slice(-6)));
  T.chk(marcadas.join(',') === 'D00007,D00008,D00009', 'CAMP-126: o grupo da unidade BL-C já vem marcado (D7, D8, D9) e só ele', marcadas.join(','));
  T.chk(/BL-C/.test(await ad.inputValue('#mx-motivo')), 'CAMP-126: o motivo já vem preenchido com a unidade');
  await T.print(ad, 'separar_mover');
  await ad.fill('#mx-dest', PC); await ad.check('#mx-ok'); await ad.click('#mx-go'); await T.confirmar(ad);
  T.chk(await T.espera(() => T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PC) === 3, 15000), `CAMP-126: as 3 folhas foram para ${PC} (mesmo fundo)`, T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PC));
  T.chk(T.sql('SELECT codigo_anterior FROM item WHERE projeto_codigo=? ORDER BY codigo', PC).map(r => (r[0] || '').slice(-6)).join(',') === 'D00007,D00008,D00009',
    'CAMP-126: cada folha movida guarda o código antigo (o antigo continua levando a ela)');
  T.chk(T.um("SELECT valor FROM cv_resposta WHERE chave='obras:decisao' AND projeto_codigo=?", PB) === 'separar', 'CAMP-126: a decisão "separar em projetos" fica registrada');
  const r = await ad.evaluate(async (P) => { const x = await fetch('/api/itens/mover', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ itens: [P + '-1972-S01-D00010'], destino: 'F003-P0001', simular: true }) }); return [x.status, JSON.stringify(await x.json())] }, PB);
  T.chk(r[0] >= 400 && /fundo/i.test(String(r[1])), 'CAMP-126: separar para projeto de OUTRO fundo é recusado (fundos não se misturam)', JSON.stringify(r));
});
