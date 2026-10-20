// CAMP-127 (P6) e CAMP-129 (P8) do quadro do painel (20/10, F026-P0009 CRASA): problemas por tipo e resolvidos em lote; grade de folhas com
// retidas em grupo próprio, ordem por nº de folha, "nº repetido" e "sem nº". Lote pelo caminho real (tests/exaustao/p6_montar.py).
// Rodar: EXAUSTAO_PORTA=8975 bash tests/rodar_exaustao.sh tests/exaustao/p6_problemas_grade.js
const { execFileSync } = require('child_process');
const path = require('path');
const T = require('./_comum');
const montar = () => execFileSync('python3', [path.join(__dirname, 'p6_montar.py'), 'montar', T.BASE, T.RAIZ], { encoding: 'utf-8' }).trim();

T.rodar(async () => {
  const P = montar(), D = n => `${P}-1978-S01-D${String(n).padStart(5, '0')}`, AUT = [23, 25, 26, 27, 28];
  T.chk(/^F026-P\d{4}$/.test(P), `cenário F026-P0009: lote de 34 folhas importado pelo aviso do CAMP Vision (${P})`);
  const op = await T.entrar('operador');
  // o que a equipe já tinha feito: o calculista como parceiro de estrutura nas 5 folhas e 3 folhas retidas
  const api = (url, metodo, corpo) => op.evaluate(async ([u, m, c]) => { const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(c) }); return [r.status, await r.text()] }, [url, metodo, corpo]);
  for (const n of AUT) { const r = await api(`/api/itens/${D(n)}`, 'PATCH', { parceiros: [{ escritorio: 'AC Vasconcelos', disciplina: 'Estrutura' }] }); if (r[0] !== 200) T.chk(false, 'cenário: parceiro na ' + D(n), r.join(' ')) }
  for (const [n, m] of [[29, 'em branco'], [30, 'em branco (cinza)'], [32, 'duplicata de D00033']]) { const r = await api(`/api/itens/${D(n)}/retencao`, 'POST', { retida: true, motivo: m }); if (r[0] !== 200) T.chk(false, 'cenário: reter ' + D(n), r.join(' ')) }

  // ------------------------------------------------------------- CAMP-127 (P6)
  T.passo('CAMP-127 (P6): problemas por tipo, em lote; "Com problema" vira chips por tipo');
  await T.abrirProjeto(op, P);
  const chips = await op.$$eval('.folhas-bar .fb-tipos [data-fl-f^="t-"]', l => l.map(b => ({ f: b.dataset.flF, t: b.textContent.trim(), bloq: b.classList.contains('chip-bloq') })));
  T.chk(chips.length >= 3, 'CAMP-127: a barra das folhas tem chips por tipo de problema', JSON.stringify(chips));
  const chAut = chips.find(c => c.f === 't-autoria');
  T.chk(chAut && /autoria não confirmada \(5\)/.test(chAut.t), 'CAMP-127: chip "autoria não confirmada (5)"', JSON.stringify(chips));
  T.chk(chips.some(c => /\(20\)/.test(c.t) && c.f.startsWith('t-erro-')), 'CAMP-127: chip do aviso de dado lido com as 20 folhas', JSON.stringify(chips));
  await T.print(op, 'p6_chips');
  await op.click('.folhas-bar [data-fl-f="t-autoria"]'); await op.waitForTimeout(400);
  const vis = await op.$$eval('.project-series .thumb', l => l.filter(t => !t.hidden && t.offsetParent).map(t => (t.dataset.revAbrir || '').slice(-6)));
  T.chk(vis.length === 5 && AUT.every(n => vis.includes('D000' + n)), 'CAMP-127: o chip "autoria" filtra exatamente as 5 folhas (antes "Com problema" pegava quase todas)', vis.join(','));
  await op.click('.folhas-bar [data-fl-f=""]'); await op.waitForTimeout(300);
  const selo1 = await T.txt(op, `.thumb[data-rev-abrir="${D(1)}"] .cap-avisos`), selo23 = await T.txt(op, `.thumb[data-rev-abrir="${D(23)}"] .cap-avisos`);
  T.chk(selo1 && !/^problema$|(^|\s)\d* ?problemas?(\s|$)/.test(selo1), 'CAMP-127: o selo da miniatura diz o tipo do problema, não só "problema"', selo1);
  T.chk(/autoria não confirmada/.test(selo23), 'CAMP-127: a folha do calculista mostra "autoria não confirmada" no selo', selo23);
  const nPag = Number((await T.txt(op, '.folhas-bar [data-fl-f="problema"]')).replace(/\D/g, ''));
  // mesma regra no conferir: "Com problema" e os chips têm os mesmos números (o lote todo é do conferir)
  await T.abrirConferir(op, P);
  const nConf = Number(await op.$eval('#cf-filtros [data-cf-filtro="problema"] b', b => b.textContent).catch(() => -1));
  const chipsConf = await op.$$eval('#cf-filtros [data-cf-filtro^="t-"]', l => l.map(b => b.dataset.cfFiltro + ' ' + b.textContent.replace(/\s+/g, ' ').trim()));
  T.chk(nPag === nConf && nPag > 0, `CAMP-127: "Com problema" é o mesmo na página e no conferir (${nPag} × ${nConf})`);
  T.chk(chipsConf.length === chips.length && chips.every(c => chipsConf.some(x => x === c.f + ' ' + c.t.replace(/ \((\d+)\)$/, ' $1'))), 'CAMP-127: os chips do conferir são os mesmos da página (tipos e números)', JSON.stringify({ chips, chipsConf }));
  await op.click('#cf-filtros [data-cf-filtro="t-autoria"]'); await op.waitForTimeout(300);
  const lin = await op.$$eval('#cf-linhas .cf-linha', l => l.map(x => x.textContent));   // a folha aberta fica na lista mesmo fora do filtro
  T.chk(lin.filter(t => /autoria/.test(t)).length === 5 && lin.length <= 6, 'CAMP-127: no conferir o chip "autoria" também filtra as 5', lin.length + ' linhas');
  // aba Problemas por tipo (cartão Problemas → "Ver por tipo")
  await T.abrirProjeto(op, P);
  const cProb = await T.txt(op, '#pj-cards .pjc[data-pjc="problemas"]');
  T.chk(/autoria não confirmada 5/.test(cProb) && /nenhum impede publicar/.test(cProb), 'CAMP-127: o cartão Problemas mostra os tipos mais comuns e que nenhum impede publicar', cProb);
  await op.click('#pj-cards [data-pjc-aba="erros"]');
  const temTipos = await op.waitForSelector('#pj-prob-tipos', { timeout: 10000 }).then(() => true, () => false);
  T.chk(temTipos, 'CAMP-127: "Ver por tipo" abre os problemas agrupados por tipo');
  const tx = await T.txt(op, '#pj-prob-tipos');
  T.chk(/Impedem publicar Nada impede publicar\./i.test(tx) && /Avisos — não impedem publicar/i.test(tx), 'CAMP-127: o que impede publicar vem separado dos avisos ("Nada impede publicar")', tx.slice(0, 300));
  const gAut = await T.txt(op, '#pj-prob-tipos [data-pt-tipo="autoria"]');
  T.chk(/autoria não confirmada 5/.test(gAut) && /Confirmar: AC Vasconcelos, parceiro \(estrutura\)/.test(gAut), 'CAMP-127: o grupo "autoria" (5) tem "Confirmar: AC Vasconcelos, parceiro (estrutura)"', gAut);
  await T.print(op, 'p6_por_tipo');
  await op.click('#pj-prob-tipos [data-pt-tipo="autoria"] [data-autoria-parceiro]'); await T.confirmar(op);
  T.chk(await T.espera(() => T.um(`SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND autoria_divergente=1`, P) === 0), 'CAMP-127: 1 clique — as 5 folhas ficam com a autoria confirmada');
  T.chk(T.um(`SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND categoria='autoria_divergente' AND situacao IN ('aberto','em_correcao')`, P + '%') === 0, 'CAMP-127: os problemas de autoria das 5 fecham');
  T.chk(T.sql(`SELECT parceiros FROM item WHERE codigo IN (${AUT.map(() => '?').join(',')})`, ...AUT.map(D)).every(r => /AC Vasconcelos/.test(r[0])), 'CAMP-127: o calculista continua como parceiro (estrutura) nas 5');
  T.chk(T.um(`SELECT COUNT(*) FROM evento WHERE tipo='autoria_parceiro' AND codigo LIKE ?`, P + '%') === 5, 'CAMP-127: cada folha ganhou o registro no histórico');
  await op.waitForSelector('#pj-cards .pjc[data-pjc="problemas"]', { timeout: 10000 }).catch(() => {});
  await op.waitForTimeout(800);
  const cProb2 = await T.txt(op, '#pj-cards .pjc[data-pjc="problemas"]');
  T.chk(!/autoria não confirmada/.test(cProb2) && !(await op.$('.folhas-bar [data-fl-f="t-autoria"]')), 'CAMP-127: o contador desce — "autoria" some do cartão e dos chips', cProb2);
  await T.print(op, 'p6_depois');
  // leitura vê os grupos, mas sem ação em lote
  const le = await T.entrar('leitura'); await T.abrirProjeto(le, P); await le.evaluate(c => showProjeto(c, 'erros'), P);
  await le.waitForSelector('#pj-prob-tipos', { timeout: 10000 }).catch(() => {});
  T.chk(!!(await le.$('#pj-prob-tipos')) && !(await le.$('#pj-prob-tipos [data-autoria-parceiro], #pj-prob-tipos [data-autoria-fundo]')), 'CAMP-127: leitura vê os tipos, sem os botões de resolver');
  await le.context().close();
  // ------------------------------------------------------------- CAMP-129 (P8)
  T.passo('CAMP-129 (P8): grade de folhas — retidas em grupo próprio, ordem por nº, "nº repetido" e "sem nº"');
  await op.evaluate(() => { try { localStorage.removeItem('camp.ordem_folhas') } catch (_) {} });
  await T.abrirProjeto(op, P); await op.evaluate(c => showProjeto(c, 'itens'), P); await op.waitForSelector('.folhas-bar', { timeout: 15000 });
  const ret = await op.$eval('[data-retidas]', s => ({ h: s.querySelector('h3').textContent, n: s.querySelector('.project-series-head span').textContent, cods: [...s.querySelectorAll('.thumb')].map(t => (t.dataset.revAbrir || '').slice(-6)), txt: s.innerText })).catch(() => null);
  T.chk(ret && /Retidas — não vão ao site/.test(ret.h) && ret.n === '3' && ret.cods.join(',') === 'D00029,D00030,D00032', 'CAMP-129: as 3 retidas ficam num grupo próprio no fim ("Retidas — não vão ao site (3)")', JSON.stringify(ret));
  T.chk(ret && /em branco/.test(ret.txt) && /em branco \(cinza\)/.test(ret.txt) && /duplicata de D00033/.test(ret.txt), 'CAMP-129: cada retida mostra o motivo', ret && ret.txt);
  const foraDoGrupo = await op.$$eval('.project-series:not([data-retidas]) .thumb', l => l.map(t => (t.dataset.revAbrir || '').slice(-6)));
  T.chk(!foraDoGrupo.some(c => ['D00029', 'D00030', 'D00032'].includes(c)) && foraDoGrupo.length === 31, 'CAMP-129: as retidas não aparecem misturadas às outras', foraDoGrupo.length + '');
  const rep33 = await T.txt(op, `.thumb[data-rev-abrir="${D(33)}"] .cap-p8`), rep32 = await T.txt(op, `.thumb[data-rev-abrir="${D(32)}"] .cap-p8`);
  T.chk(/nº repetido/.test(rep33) && /D00032/.test(rep33) && /nº repetido/.test(rep32) && /D00033/.test(rep32), 'CAMP-129: as duas "Planta · folha 306" têm o selo "nº repetido" com o link para a outra', rep33 + ' | ' + rep32);
  const sn = await op.$$eval('.thumb', l => l.filter(t => t.querySelector('.semnum')).map(t => (t.dataset.revAbrir || '').slice(-6)));
  T.chk(sn.join(',') === 'D00022,D00031', 'CAMP-129: as folhas sem nº (D00022 e D00031) têm o selo "sem nº"', sn.join(','));
  const bSn = await T.txt(op, '.folhas-bar [data-fl-f="semnum"]');
  T.chk(/Sem nº \(2\)/.test(bSn), 'CAMP-129: filtro "Sem nº (2)" na barra', bSn);
  await op.click('.folhas-bar [data-fl-f="semnum"]'); await op.waitForTimeout(300);
  const visSn = await op.$$eval('.project-series .thumb', l => l.filter(t => !t.hidden && t.offsetParent).map(t => (t.dataset.revAbrir || '').slice(-6)));
  T.chk(visSn.join(',') === 'D00022,D00031', 'CAMP-129: o filtro "Sem nº" mostra só as 2', visSn.join(','));
  await op.click('.folhas-bar [data-fl-f=""]'); await op.waitForTimeout(200);
  const gen = await op.$eval(`.thumb[data-rev-abrir="${D(1)}"] .cap`, c => ({ gen: !!c.querySelector('.cap-gen'), num: (c.querySelector('.cap-num') || {}).textContent || '', cor: getComputedStyle(c.querySelector('.cap-gen') || c).fontWeight }));
  T.chk(gen.gen && /folha 5/.test(gen.num) && Number(gen.cor) < 600, 'CAMP-129: "Desenhos e pranchas" fica apagado e o nº da folha vem em destaque', JSON.stringify(gen));
  const ordCod = await op.$$eval('.project-series:not([data-retidas]) .thumb', l => l.slice(0, 6).map(t => t.querySelector('.cap-num') ? t.querySelector('.cap-num').textContent.replace('folha ', '') : '-'));
  T.chk(ordCod.join(',') === '5,6,315,316,317,318', 'cenário: na ordem por código os nºs saem fora de ordem (5, 6, 315…)', ordCod.join(','));
  await T.print(op, 'p8_codigo');
  await op.selectOption('.folhas-bar [data-fl-ordem]', 'folha'); await op.waitForTimeout(500);
  const seq = await op.$$eval('.project-series .thumb', l => l.map(t => ({ c: (t.dataset.revAbrir || '').slice(-6), n: t.querySelector('.cap-num') ? t.querySelector('.cap-num').textContent.replace('folha ', '') : '' })));
  const i32 = seq.findIndex(x => x.c === 'D00032'), i33 = seq.findIndex(x => x.c === 'D00033');
  T.chk(i32 >= 0 && Math.abs(i32 - i33) === 1, 'CAMP-129: ordenar por nº de folha deixa as duas "306" lado a lado (a retida entra na sequência, com o selo)', seq.map(x => x.n || x.c).join(','));
  const nums = seq.map(x => parseInt(x.n, 10)).filter(n => !Number.isNaN(n));
  T.chk(nums.every((n, i) => i === 0 || nums[i - 1] <= n) && seq.slice(-2).map(x => x.c).join(',') === 'D00022,D00031', 'CAMP-129: em ordem crescente de nº (02, 03, 03, 04…), as sem nº no fim', seq.map(x => x.n || x.c).join(','));
  T.chk(/retida/.test(await T.txt(op, `.thumb[data-rev-abrir="${D(32)}"]`)), 'CAMP-129: na sequência, a retida continua marcada como retida');
  await T.print(op, 'p8_por_numero');
  await op.reload(); await op.waitForSelector('.folhas-bar [data-fl-ordem]', { timeout: 15000 });
  T.chk(await op.$eval('.folhas-bar [data-fl-ordem]', s => s.value) === 'folha', 'CAMP-129: a ordem escolhida fica guardada ao recarregar');
  await op.selectOption('.folhas-bar [data-fl-ordem]', 'tipo'); await op.waitForTimeout(400);
  const porTipo = await op.$$eval('.project-series:not([data-retidas]) .thumb', l => l.map(t => (t.querySelector('.cap b') || {}).textContent || ''));
  T.chk(porTipo[0] === 'Detalhe' && porTipo.indexOf('Estrutura') > 0 && !!(await op.$('[data-retidas]')), 'CAMP-129: ordem por tipo agrupa os tipos (Detalhe, Estrutura, Planta…) e as retidas voltam ao grupo próprio', porTipo.slice(0, 8).join(','));
  await op.selectOption('.folhas-bar [data-fl-ordem]', 'codigo');
});
