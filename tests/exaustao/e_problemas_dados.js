// Exaustão da página do projeto, grupo E (CAMP-102 a CAMP-108): problemas e dados do projeto. Tudo pelo navegador; os lotes nascem pelo
// caminho real (estação reserva, CAMP Vision grava a pasta final e avisa: tests/fluxo_real_cv2.py e tests/exaustao/e_montar.py).
// Rodar: bash tests/rodar_exaustao.sh tests/exaustao/e_problemas_dados.js
const { execFileSync } = require('child_process');
const path = require('path');
const T = require('./_comum');
const { chk, passo, sql, um, espera, print, txt, confirmar, entrar, abrirProjeto, abrirConferir, cv2, BASE, RAIZ } = T;
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'e_montar.py'), ...a], { encoding: 'utf-8' }).trim();
// um projeto com um lote montado a partir de uma especificação (pasta final + aviso do CAMP Vision)
const lote = (nome, spec, ano = '1972', opc = {}) => {
  const P = cv2('reservar', BASE, 'F026', nome, String(ano)); cv2('processando', BASE, RAIZ, P, nome);
  const r = JSON.parse(montar('lote', BASE, RAIZ, P, JSON.stringify(spec), ...(opc.semAviso ? ['--sem-aviso'] : [])));
  return { P, D: n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`, r };
};
const docs = (n0, n1, campos = () => ({})) => Array.from({ length: n1 - n0 + 1 }, (_, i) => ({ n: n0 + i, titulo: `PLANTA ${n0 + i}`, campos: campos(n0 + i) }));
const num = s => Number(String(s || '').replace(/\D/g, '') || NaN);
const cartao = (pg, k) => txt(pg, `#pj-cards .pjc[data-pjc="${k}"]`);
const gavAberta = pg => pg.evaluate(() => { const g = document.getElementById('pj-gaveta'); if (!g || g.hidden) return null; const s = [...g.querySelectorAll('.pj-gav')].filter(x => !x.hidden); return s.length === 1 ? s[0].dataset.gav : s.map(x => x.dataset.gav).join('+') || null });
const painel = pg => pg.evaluate(() => API('/api/painel'));
const grupoTotal = (p, id) => ((p.tarefas || []).find(g => g.id === id) || {}).total || 0;

T.rodar(async () => {
  const op = await entrar('operador'), ad = await entrar('admin');

  // ---------------------------------------------------------------- CAMP-102
  passo('CAMP-102: "Problemas que impedem publicar" bate em todo lugar (5 bloqueantes + avisos de tipos diferentes)');
  const base0 = grupoTotal(await painel(op), 'problemas');
  const A = lote('CASA CONTAGEM', {
    docs: [...docs(1, 6), { n: 7, titulo: 'PLANTA 1', campos: { duplicata_de: '{P}-1972-S01-D00001', tipo_duplicata: 'quase', publicavel: false, bloqueios: ['duplicata de {P}-1972-S01-D00001'] } }, { n: 8, titulo: 'ESCALA' }],
    retirados: [{ n: 9, carimbo: 'OUTRA OBRA NOVE' }, { n: 10, carimbo: 'OUTRA OBRA DEZ' }],
    erros: [
      { arquivo: '{P}-1972-S01-D00001', categoria: 'arquivo', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'TIF corrompido — refazer a digitalização' },
      { arquivo: '{P}-1972-S01-D00002', categoria: 'metadado', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'carimbo ilegível: título e folha não lidos' },
      { arquivo: '{P}-1972-S01-D00009', categoria: 'projeto', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'D00009 com identificação para outra pasta (OUTRA OBRA NOVE) — fora da publicação até resolver' },
      { arquivo: '{P}-1972-S01-D00010', categoria: 'projeto', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'D00010 com identificação para outra pasta (OUTRA OBRA DEZ) — fora da publicação até resolver' },
      { arquivo: '', categoria: 'metadado', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'pasta sem folha de rosto: conferir o nome do projeto antes de publicar' },
      { arquivo: '{P}-1972-S01-D00003', categoria: 'orientação', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'orientação incerta — conferir na folha de contatos' },
      { arquivo: '{P}-1972-S01-D00004', categoria: 'orientação', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'espelhada? — conferir na folha de contatos' },
      { arquivo: '{P}-1972-S01-D00005', categoria: 'metadado', gravidade: 'corrigir', origem: 'CAMP Vision', detalhe: 'ano lido 1927 diverge do projeto (1972)' },
      { arquivo: '{P}-1972-S01-D00006', categoria: 'metadado', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'escala não lida' },
      { arquivo: '{P}-1972-S01-D00007', categoria: 'duplicata', gravidade: 'corrigir', origem: 'CAMP Vision', detalhe: 'quase de D00001 — só a única publica' },
      { arquivo: '{P}-1972-S01-D00008', categoria: 'metadado', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'folha sem número no carimbo' },
      { arquivo: '', categoria: 'metadado', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'sem pasta de material: série S01 deduzida (01 - Desenhos e pranchas)' },
    ] });
  chk(A.r.ok && (A.r.importacao || {}).criadas === 8, 'CAMP-102: o lote entra pelo aviso do CAMP Vision (8 folhas, 2 retiradas)', JSON.stringify(A.r).slice(0, 300));
  const bloqBanco = um("SELECT COUNT(*) FROM erro WHERE (codigo=? OR codigo LIKE ?) AND situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'", A.P, A.P + '-%');
  // 21/10 ("publicar sem travar", 4.1): problema que bloqueia numa FOLHA deixa só ela de fora; o aviso automático no projeto não trava.
  // Antes: "5 impedem publicar" (o projeto inteiro parado). Agora: nada impede, 2 folhas do painel (D00001, D00002) ficam fora.
  chk(bloqBanco === 5, 'CAMP-102: no banco, 5 avisos que o CAMP Vision marcou como bloqueio', bloqBanco);
  await abrirProjeto(op, A.P);
  const cP = await cartao(op, 'problemas');
  chk(/nenhum impede publicar/.test(cP) && /2 folhas ficam fora desta publicação/.test(cP), 'sem travar: cartão Problemas diz que nada impede publicar e que 2 folhas ficam fora', cP);
  const aba = await txt(op, '#pd [role="tab"]:has-text("Problemas")');
  chk(/Problemas \(\d+\)/.test(aba) && !/bloqueia|NaN/.test(aba), 'sem travar: a aba Problemas mostra o total, sem "bloqueiam"', aba);
  chk(await gavAberta(op) === null, 'CAMP-102 (P0): nenhuma gaveta abre sozinha', await gavAberta(op));
  await require('./_comum').abrirGaveta(op, 'problemas');
  chk(await gavAberta(op) === 'problemas', 'sem travar: "Ver quais" abre a lista das folhas que ficam fora', await gavAberta(op));
  const lis = await op.$$eval('#pj-probs li', l => l.map(x => x.textContent));
  chk(lis.length === 4 && !lis.some(t => /folha de rosto/.test(t)), 'sem travar: a lista tem só folhas (D00001, D00002 e as 2 de outra obra), sem o aviso do projeto', JSON.stringify(lis).slice(0, 300));
  await print(op, '102_lista');
  const base1 = grupoTotal(await painel(op), 'problemas');
  chk(base1 === base0, `sem travar: o Painel "Problemas que bloqueiam" não sobe com aviso automático (${base0} → ${base1})`);
  await abrirProjeto(ad, A.P);
  const cond = await ad.evaluate(c => ((window.PUB_G || {})[c] || {}).condicoes || [], A.P), cb = cond.find(c => c.id === 'bloqueios') || {}, cf = cond.find(c => c.id === 'folhas_com_bloqueio') || {};
  chk(cb.ok === true && /2 folha/.test(cf.texto || ''), 'sem travar: a publicação não trava e avisa que 2 folhas ficam fora', JSON.stringify([cb, cf]).slice(0, 300));
  // cada linha de folha do painel leva à folha certa no conferir
  await abrirProjeto(op, A.P); await require('./_comum').abrirGaveta(op, 'problemas');
  const links = await op.$$eval('#pj-probs a[href^="#conferir/"]', l => l.map(a => a.getAttribute('href')));
  chk(links.length === 2 && links.every(h => h.startsWith('#conferir/' + A.P + '/')), 'CAMP-102: folhas no painel têm link para o conferir (D00001 e D00002)', JSON.stringify(links));
  for (const h of links) {
    await abrirProjeto(op, A.P); await require('./_comum').abrirGaveta(op, 'problemas'); await op.click(`#pj-probs a[href="${h}"]`);
    const alvo = h.split('/').pop();
    chk(await espera(() => op.evaluate(() => (window.CONF || {}).atual)).then(async () => (await op.evaluate(() => CONF.atual)) === alvo), `CAMP-102: o link ${alvo.slice(-6)} abre essa folha no conferir`, await op.evaluate(() => (window.CONF || {}).atual));
  }
  await abrirProjeto(op, A.P);

  // ---------------------------------------------------------------- CAMP-103
  passo('CAMP-103: problema relatado por pessoa');
  const B = lote('CASA RELATO', { docs: docs(1, 3) });
  await abrirConferir(op, B.P, B.D(2));
  await op.click(`#cf-pane [data-relatar-folha="${B.D(2)}"]`);
  await op.waitForSelector('#m-erro.on, #m-erro.open, #m-erro:not([hidden]) #ne-desc', { timeout: 8000 }).catch(() => {});
  chk((await op.inputValue('#ne-cod').catch(() => '')) === B.D(2), 'CAMP-103: "Relatar problema" já vem com o código da folha', await op.inputValue('#ne-cod').catch(() => ''));
  await op.fill('#ne-desc', 'A prancha está rasgada no canto: precisa ver o original');
  await op.click('#m-erro .pf .btn.pri'); await op.waitForTimeout(1500);
  const eRel = sql("SELECT id, origem, gravidade, situacao FROM erro WHERE codigo=? AND descricao LIKE 'A prancha está rasgada%'", B.D(2))[0];
  chk(!!eRel && eRel[3] === 'aberto', 'CAMP-103: o problema foi registrado aberto', JSON.stringify(eRel));
  await abrirConferir(op, B.P, B.D(2));
  chk(/rasgada/.test(await txt(op, '#cf-pane')), 'CAMP-103: aparece na folha, no conferir', (await txt(op, '#cf-pane')).slice(0, 300));
  chk(/problema|rasgada/.test(await txt(op, `#cf-linhas [data-cf-folha="${B.D(2)}"]`)), 'CAMP-103: a linha da folha mostra a marca de problema (CAMP-127: com o que é o problema)', await txt(op, `#cf-linhas [data-cf-folha="${B.D(2)}"]`));
  await print(op, '103_relatado');
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op); await op.waitForTimeout(1200);
  chk(um('SELECT situacao FROM erro WHERE id=?', eRel && eRel[0]) === 'aberto', 'CAMP-103: conferir a folha NÃO fecha o problema relatado por pessoa', um('SELECT situacao FROM erro WHERE id=?', eRel && eRel[0]));
  await abrirProjeto(op, B.P);
  chk(/1 aviso|1 impede/.test(await cartao(op, 'problemas')), 'CAMP-103: continua no cartão Problemas', await cartao(op, 'problemas'));
  // resolver na tela Problemas, com descrição
  await op.evaluate(c => nav('erros/' + c), B.P); await op.waitForSelector('#err-body tr[data-err-linha]', { timeout: 15000 });
  await op.click('#err-body tr[data-err-linha] .err-oque'); await op.waitForSelector('#d-body', { timeout: 8000 }); await op.waitForTimeout(800);
  const dCorpo = await txt(op, '#d-body');
  await print(op, '103_gaveta_problema');
  const btRes = await op.$('#d-body button:has-text("Marcar como corrigido")');
  chk(!!btRes && !!(await op.$('#d-body textarea')), 'CAMP-103: a gaveta do problema pede a frase do que foi feito e tem "Marcar como corrigido"', dCorpo.slice(0, 400));
  if (btRes) {
    await op.fill('#d-body textarea', 'Original conferido no tubo: a folha está inteira, o rasgo é do papel de proteção');
    await btRes.click(); await confirmar(op); await op.waitForTimeout(1500);
    const fim = sql('SELECT situacao, resolucao FROM erro WHERE id=?', eRel[0])[0] || [];
    chk(fim[0] === 'corrigido' && /papel de proteção/.test(fim[1] || ''), 'CAMP-103: resolvido por quem resolveu, com a descrição', JSON.stringify(fim));
    const hist = sql("SELECT tipo, ator FROM evento WHERE (codigo=? OR codigo=? OR detalhe LIKE ?) ORDER BY id DESC LIMIT 5", B.D(2), String(eRel[0]), '%"' + eRel[0] + '"%');
    chk(hist.some(h => h[0] === 'editado' && /operador@/.test(h[1] || '')), 'CAMP-103: fica no histórico com quem resolveu', JSON.stringify(hist));
  }

  // ---------------------------------------------------------------- CAMP-104
  passo('CAMP-104: problema do projeto (sem folha)');
  const C = lote('CASA SEM FOLHA', { docs: docs(1, 3), erros: [
    { arquivo: '', categoria: 'metadado', gravidade: 'aviso', origem: 'CAMP Vision', detalhe: 'sem pasta de material: série S01 deduzida (01 - Desenhos e pranchas)' },
    { arquivo: 'scan solto.tif', categoria: 'metadado', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'arquivo fora do padrão na pasta do projeto: scan solto.tif' } ] });
  const eProj = sql("SELECT id, codigo, gravidade FROM erro WHERE codigo=? AND situacao='aberto' ORDER BY id", C.P);
  chk(eProj.length === 2 && eProj.every(e => e[1] === C.P), 'CAMP-104: os 2 problemas sem folha ficam no código do projeto', JSON.stringify(eProj));
  await abrirProjeto(op, C.P);
  // 21/10 ("publicar sem travar"): aviso automático no projeto (mesmo marcado "bloqueia" pelo CAMP Vision) não trava; só o de pessoa trava
  chk(/2 avisos/.test(await cartao(op, 'problemas')) && /nenhum impede publicar/.test(await cartao(op, 'problemas')), 'CAMP-104: cartão Problemas conta os dois avisos e diz que nada impede publicar', await cartao(op, 'problemas'));
  chk(!(await op.$$eval('#pj-probs li a[href^="#conferir/"]', l => l.length)), 'CAMP-104: problema do projeto nunca vira link quebrado para folha', await txt(op, '#pj-probs').catch(() => ''));
  await abrirConferir(op, C.P);
  chk(Number(await op.$eval('#cf-filtros [data-cf-filtro="problema"] b', b => b.textContent).catch(() => -1)) === 0, 'CAMP-104: no conferir, nenhuma folha fica marcada por problema do projeto');
  await op.evaluate(c => nav('erros/' + c), C.P); await op.waitForSelector('#err-body tr[data-err-linha]', { timeout: 15000 }); await op.waitForTimeout(800);
  const linhasC = await op.$$eval('#err-body tr[data-err-linha]', l => l.length);
  chk(linhasC === 2, 'CAMP-104: tela Problemas lista os 2, sem travar', linhasC);
  await op.click('#err-body tr[data-err-linha] .err-oque'); await op.waitForSelector('#d-body', { timeout: 8000 }); await op.waitForTimeout(600);
  const dC = await txt(op, '#d-body');
  chk(!/abrir a folha/i.test(dC) && /projeto/i.test(dC), 'CAMP-104: a gaveta do problema leva ao projeto (não a uma folha que não existe)', dC.slice(0, 300));
  await print(op, '104_gaveta');
  const eAberto = um("SELECT id FROM erro WHERE codigo=? AND situacao='aberto' AND descricao LIKE ?", C.P, (dC.match(/série S01 deduzida/) ? '%série S01%' : '%scan solto%'));
  await op.fill('#d-body textarea', 'Conferido: a série está certa'); await op.click('#d-body button:has-text("Marcar como corrigido")'); await confirmar(op); await op.waitForTimeout(1200);
  chk(um('SELECT situacao FROM erro WHERE id=?', eAberto) === 'corrigido', 'CAMP-104: resolver o problema do projeto funciona');
  await abrirProjeto(op, C.P);
  const cC = await cartao(op, 'problemas');
  chk(/PROBLEMAS 1\b/.test(cC) || /^PROBLEMAS 0/.test(cC) || /1 (aviso|impede)/.test(cC), 'CAMP-104: o cartão desconta o resolvido', cC);

  // ---------------------------------------------------------------- CAMP-105
  passo('CAMP-105 → P0 (21/10): nenhuma gaveta abre sozinha; a que a pessoa abre/fecha fica como ela deixou');
  const dados1978 = n => ({ ano: '1978', ano_do_projeto: '1972' });
  const X = lote('CASA SO DADOS', { docs: docs(1, 3, dados1978), ano_carimbo: 1978 });                           // só pergunta de dados
  const Y = lote('CASA DADOS E BLOQUEIO', { docs: docs(1, 3, dados1978), ano_carimbo: 1978, erros: [
    { arquivo: '{P}-1972-S01-D00001', categoria: 'arquivo', gravidade: 'bloqueia', origem: 'CAMP Vision', detalhe: 'TIF corrompido' } ] });
  const Zc = cv2('reservar', BASE, 'F026', 'CASA PARADA', '1972'); cv2('processando', BASE, RAIZ, Zc, 'CASA PARADA');
  const zr = JSON.parse(montar('erro', BASE, RAIZ, Zc, 'falta o TIF de 3 imagens: refaça a cópia', JSON.stringify([{ arquivo: '', categoria: 'metadado', gravidade: 'bloqueia', detalhe: 'lote incompleto' }])));
  chk(zr.etapa === 'erro', 'CAMP-105: o CAMP Vision avisa erro e o lote fica parado', JSON.stringify(zr));
  for (const [cod, esp, nome] of [[X.P, 'dados', 'só dados'], [Y.P, 'problemas', 'problemas + dados'], [Zc, 'folhas', 'lote parado + problema']]) {
    await op.evaluate(() => nav('painel')); await op.waitForTimeout(800); await op.evaluate(() => window.scrollTo(0, 0));
    await abrirProjeto(op, cod);
    chk(await gavAberta(op) === null, `P0: ${nome} → nenhuma gaveta abre sozinha (antes abria "${esp}")`, `${await gavAberta(op)} · ${await txt(op, '#pj-cards')}`.slice(0, 400));
    chk(await op.evaluate(() => window.scrollY) < 5, `CAMP-105: ${nome}: a página não pula para baixo`, await op.evaluate(() => window.scrollY));
  }
  await print(op, '105_parado');
  // fechar não reabre na mesma visita (mesmo quando os cartões se redesenham)
  await abrirProjeto(op, Y.P); await require('./_comum').abrirGaveta(op, 'problemas');
  await op.click('#pj-gaveta .pj-gav:not([hidden]) [data-pjc-fechar]'); await op.waitForTimeout(400);
  await op.evaluate(c => desenharCartoes(c), Y.P); await op.waitForTimeout(600);
  chk(await gavAberta(op) === null, 'CAMP-105: fechou → os cartões se redesenham e a gaveta não volta');
  // nova visita (sai pelo menu e volta, como uma pessoa faz) → abre de novo
  await op.evaluate(() => nav('painel')); await op.waitForTimeout(1200);
  await op.evaluate(c => nav('projeto/' + c), Y.P); await op.waitForSelector('#pj-cards .pjc[data-pjc="site"]', { timeout: 15000 }); await op.waitForTimeout(2000);
  chk(await gavAberta(op) === null, 'P0: nova visita ao projeto → continua fechada (nada abre sozinho)', await gavAberta(op));
  await op.goBack(); await op.waitForTimeout(800); await op.goForward(); await op.waitForTimeout(2200);
  chk(await gavAberta(op) === null, 'P0: Voltar e Avançar do navegador → continua fechada', await gavAberta(op));

  // ---------------------------------------------------------------- CAMP-106
  passo('CAMP-106: consenso e folhas divergentes (28 com 1978, 3 com 1987; endereços)');
  const end = n => n === 30 ? 'Rua A, 10.' : n === 31 ? 'Av. B, 99' : 'Rua A, 10';
  const Q = lote('CASA CONSENSO', { docs: docs(1, 31, n => ({ ano: n >= 29 ? '1987' : '1978', ano_do_projeto: '1978', endereco: end(n) })), ano_carimbo: 1978, ano_projeto: '1978' }, '1978');
  chk(um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND ano_folha=1987", Q.P) === 3, 'CAMP-106: 3 folhas chegam com 1987');
  await abrirProjeto(ad, Q.P);
  const cD = await cartao(ad, 'dados');
  chk(/pergunta/.test(cD), 'CAMP-106: cartão Dados pergunta', cD);
  if (await gavAberta(ad) !== 'dados') await ad.click('#pj-cards [data-pjc-gav="dados"]');
  await ad.waitForTimeout(600); await print(ad, '106_perguntas');
  const pjq = await ad.$$eval('#pj-gaveta .pjq[data-pjq]', l => l.map(x => x.dataset.pjq));
  chk(pjq.length === new Set(pjq).size, 'CAMP-106: uma pergunta por campo (nada repetido)', JSON.stringify(pjq));
  const ano = await txt(ad, '#pj-gaveta .pjq[data-pjq="ano"]');
  chk(/1978/.test(ano) && /1987/.test(ano) && /3 dizem/.test(ano), 'CAMP-106: ano: "1978 (28 de 31); 3 dizem 1987"', ano);
  const bAno = await ad.$('#pj-gaveta .pjq[data-pjq="ano"] [data-cs-todas]');
  chk(!!bAno && /Usar 1978 nas 3 folhas/.test(await bAno.innerText()), 'CAMP-106: botão "Usar 1978 nas 3 folhas"', bAno ? await bAno.innerText() : '(sem botão)');
  if (bAno) { await bAno.click(); await confirmar(ad); await ad.waitForTimeout(1500) }
  chk(um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND ano_folha=1978", Q.P) === 31, 'CAMP-106: as 3 divergentes viram 1978 (31 de 31)');
  chk(!(await ad.$('#pj-gaveta .pjq[data-pjq="ano"]')), 'CAMP-106: a pergunta do ano some sem recarregar', await txt(ad, '#pj-gaveta'));
  const pEnd = await txt(ad, '#pj-gaveta .pjq[data-pjq="endereco"]');
  chk(/Av\. B, 99/.test(pEnd) && !/Rua A, 10\.(?!\d)/.test(pEnd.replace('Rua A, 10 ', '')), 'CAMP-106: endereço: só "Av. B, 99" é diferença (a pontuação "Rua A, 10." não é)', pEnd);
  const bEnd = await ad.$('#pj-gaveta .pjq[data-pjq="endereco"] [data-cs-todas]');
  if (bEnd) { await bEnd.click(); await confirmar(ad); await ad.waitForTimeout(1500) }
  const bProj = await ad.$('#pj-gaveta .pjq[data-pjq="endereco"] [data-cs-proj]');
  if (bProj) { await bProj.click(); await confirmar(ad); await ad.waitForTimeout(1500) }
  const cD2 = await cartao(ad, 'dados');
  chk(/Em ordem/.test(cD2), 'CAMP-106: depois das respostas o cartão Dados fica "Em ordem"', cD2 + ' || ' + await txt(ad, '#pj-gaveta'));
  await print(ad, '106_em_ordem');
  await abrirProjeto(ad, Q.P);
  chk(/Em ordem/.test(await cartao(ad, 'dados')), 'CAMP-106: e continua "Em ordem" ao voltar ao projeto', await cartao(ad, 'dados'));
  const decQ = await ad.evaluate(c => API('/api/decisoes?situacao=pendente').then(r => (r.itens || []).filter(x => JSON.stringify(x).includes(c)).length), Q.P);
  chk(decQ === 0, 'CAMP-106: nenhuma decisão repetida na fila de Decisões', decQ);

  const R = lote('CASA ANO DUPLO', { docs: docs(1, 3, dados1978), ano_carimbo: 1978, ano_projeto: '1978' });
  const decR = () => ad.evaluate(c => API('/api/decisoes?situacao=pendente').then(r => (r.itens || []).filter(x => JSON.stringify(x).includes(c))), R.P);
  chk((await decR()).length === 1, 'CAMP-106: o CAMP Vision leu 1978 no projeto (cadastro 1972): abre a decisão "divergência" do ano', JSON.stringify(await decR()).slice(0, 300));
  await abrirProjeto(ad, R.P);
  if (await gavAberta(ad) !== 'dados') await ad.click('#pj-cards [data-pjc-gav="dados"]');
  await ad.waitForTimeout(500);
  const bR = await ad.$('#pj-gaveta .pjq[data-pjq="ano"] [data-cs-proj]');
  chk(!!bR, 'CAMP-106: Dados pergunta o mesmo ano ("Usar 1978 no projeto")', await txt(ad, '#pj-gaveta'));
  if (bR) { await bR.click(); await confirmar(ad); await ad.waitForTimeout(1500) }
  chk(um('SELECT ano FROM projeto WHERE codigo=?', R.P) === 1978, 'CAMP-106: o projeto fica com 1978');
  chk((await decR()).length === 0, 'CAMP-106: a mesma pergunta não fica esperando de novo na fila de Decisões (decisão igual fecha junto)', JSON.stringify(await decR()).slice(0, 300));

  // ---------------------------------------------------------------- CAMP-107
  passo('CAMP-107: editar nome, ano, cidade, endereço');
  const E = lote('CASA PARA EDITAR', { docs: docs(1, 2) });
  await abrirProjeto(ad, E.P);
  await ad.click('#pd .act button:has-text("Editar")'); await ad.waitForSelector('#ep-titulo', { timeout: 8000 });
  await ad.fill('#ep-titulo', 'Casa Editada da Praia'); await ad.fill('#ep-ano', '1975'); await ad.fill('#ep-cidade', 'Santos');
  if (await ad.$('#ep-endereco_obra')) await ad.fill('#ep-endereco_obra', 'Rua Nova, 5');
  await print(ad, '107_form');
  await ad.click('#drawer button:has-text("Salvar")'); await ad.waitForTimeout(2000);
  const h1 = await txt(ad, '#pd h1'), crumb = await txt(ad, '#gcrumb'), cab = await txt(ad, '#pd');
  chk(/Casa Editada da Praia/i.test(h1), 'CAMP-107: o título da página muda sem recarregar', h1);
  chk(/Casa Editada da Praia/i.test(crumb), 'CAMP-107: o caminho no topo muda', crumb);
  chk(/1975/.test(cab) && /Santos/.test(cab), 'CAMP-107: ano e cidade mudam no cabeçalho', cab.slice(0, 300));
  const pr = sql('SELECT codigo, titulo, ano, cidade FROM projeto WHERE codigo=?', E.P)[0] || [];
  chk(pr[0] === E.P && pr[1] === 'Casa Editada da Praia' && pr[2] === 1975 && pr[3] === 'Santos', 'CAMP-107: gravado, e o código do projeto não muda', JSON.stringify(pr));
  chk(um("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", E.P) === 2, 'CAMP-107: as folhas continuam no mesmo código');
  await ad.evaluate(c => nav('etiquetas/projeto/' + c), E.P); await ad.waitForTimeout(2500);
  chk(/Casa Editada da Praia/i.test(await txt(ad, '#pd')), 'CAMP-107: a etiqueta do projeto já usa o nome novo', (await txt(ad, '#pd')).slice(0, 200));
  await print(ad, '107_etiqueta');

  // ---------------------------------------------------------------- CAMP-108
  passo('CAMP-108: "projeto parecido" pendente');
  const Vp = cv2('reservar', BASE, 'F026', 'CASA DO LAGO AZUL', '1972');
  const pede = () => JSON.parse(montar('reservar_parecido', BASE, 'F026', 'Casa do Lago Azul (reenvio)'));
  const r1 = pede();
  chk(r1.pendente === true && r1.decisao_id, 'CAMP-108: a estação pede número para "Casa do Lago Azul (reenvio)" e o painel abre a decisão (CAMP Vision espera)', JSON.stringify(r1));
  await abrirProjeto(op, Vp);
  // P0 (21/10): a decisão é um item da barra "O que falta" (sem faixa repetida na página); "Ver" abre o painel lateral com a pergunta
  chk(/1 decisão pendente/.test(await txt(op, '#pj-falta')), 'CAMP-108 (P0): a barra "O que falta" tem "1 decisão pendente sobre este projeto"', await txt(op, '#pj-falta'));
  await op.click('#pj-falta li[data-pjp="decisao"] [data-pjp-ir]'); await op.waitForTimeout(1200);
  const avOp = await txt(op, '#d-body');
  chk(/parecido|é o mesmo|esperando/i.test(avOp) && /admin/i.test(avOp), 'CAMP-108: operador, na página do projeto parecido, vê a pergunta e que um admin decide', avOp.slice(0, 600));
  await print(op, '108_operador');
  await abrirProjeto(ad, Vp);
  await ad.click('#pj-falta li[data-pjp="decisao"] [data-pjp-ir]'); await ad.waitForTimeout(1200);
  const bDec = await ad.$(`#d-body [data-dec-abrir="${r1.decisao_id}"], #d-body [data-abrir="decisao:${r1.decisao_id}"]`);
  chk(!!bDec, 'CAMP-108: admin, pela barra "O que falta", tem o botão para decidir', (await txt(ad, '#d-body')).slice(0, 400));
  if (bDec) await bDec.click(); else await ad.evaluate(id => abrirDecisao(id), r1.decisao_id);
  await ad.waitForSelector(`#d-body [data-dec-acao="mesmo"][data-dec-id="${r1.decisao_id}"]`, { timeout: 8000 });
  await print(ad, '108_decisao');
  const temOpcoes = await ad.evaluate(() => ({ mesmo: !!document.querySelector('#d-body [data-dec-acao="mesmo"]'), novo: !!document.querySelector('#d-body [data-dec-acao="novo"]'), outro: !!document.querySelector('#d-body [data-dec-outro] .dec-busca') }));
  chk(temOpcoes.mesmo && temOpcoes.novo && temOpcoes.outro, 'CAMP-108: as opções: é o mesmo, escolher outro na lista, criar novo', JSON.stringify(temOpcoes));
  await ad.click(`#d-body [data-dec-acao="mesmo"][data-dec-id="${r1.decisao_id}"]`); await confirmar(ad); await ad.waitForTimeout(1500);
  const r2 = pede();
  chk(r2.codigo === Vp, 'CAMP-108: "é o mesmo" → o CAMP Vision destrava e recebe o código do projeto que já existe', JSON.stringify(r2));
  await abrirProjeto(op, Vp);
  chk(!/esperando a decisão|CAMP Vision espera/i.test(await txt(op, '#pd')), 'CAMP-108: decidido, o aviso sai da página do projeto');
  // escolher OUTRO projeto da lista
  const W1 = cv2('reservar', BASE, 'F026', 'EDIFICIO SOL NASCENTE', '1972'), W2 = cv2('reservar', BASE, 'F026', 'RESIDENCIA MANHA CLARA', '1972');
  const r3 = JSON.parse(montar('reservar_parecido', BASE, 'F026', 'Edificio Sol Nascente (reenvio)'));
  if (r3.decisao_id) {
    await ad.evaluate(id => abrirDecisao(id), r3.decisao_id); await ad.waitForSelector('#d-body [data-dec-outro] .dec-busca', { timeout: 8000 });
    await ad.fill('#d-body [data-dec-outro] .dec-busca', 'Manha Clara'); await ad.waitForSelector(`#d-body [data-dec-valor="${W2}"][data-dec-acao="mesmo"]`, { timeout: 8000 }).catch(() => {});
    const bW2 = await ad.$(`#d-body [data-dec-valor="${W2}"][data-dec-acao="mesmo"]`);
    chk(!!bW2, 'CAMP-108: "escolher outro na lista" acha o projeto pelo nome', await txt(ad, '#d-body [data-dec-outro]'));
    if (bW2) { await bW2.click(); await confirmar(ad); await ad.waitForTimeout(1500) }
    const r4 = JSON.parse(montar('reservar_parecido', BASE, 'F026', 'Edificio Sol Nascente (reenvio)'));
    chk(r4.codigo === W2, 'CAMP-108: o CAMP Vision recebe o projeto escolhido na lista', JSON.stringify(r4));
  } else chk(false, 'CAMP-108: segunda decisão (escolher outro) não abriu', JSON.stringify(r3));
  // criar novo
  const r5 = JSON.parse(montar('reservar_parecido', BASE, 'F026', 'Casa do Lago Azul II'));
  if (r5.decisao_id) {
    await ad.evaluate(id => abrirDecisao(id), r5.decisao_id); await ad.waitForSelector(`#d-body [data-dec-acao="novo"]`, { timeout: 8000 });
    await ad.click('#d-body [data-dec-acao="novo"]'); await confirmar(ad); await ad.waitForTimeout(1500);
    const r6 = JSON.parse(montar('reservar_parecido', BASE, 'F026', 'Casa do Lago Azul II'));
    chk(r6.codigo && r6.codigo !== Vp && /^F026-P\d{4}$/.test(r6.codigo), 'CAMP-108: "criar novo" → o CAMP Vision recebe um código novo', JSON.stringify(r6));
  } else chk(r5.codigo && r5.codigo !== Vp, 'CAMP-108: "Casa do Lago Azul II" não pediu decisão (nome bem diferente)', JSON.stringify(r5));
});
