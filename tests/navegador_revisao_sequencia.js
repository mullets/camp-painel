// CAMP-FICHA (25/11/2026). Rafael: "quando eu salvo algo que é de outra categoria ele vai pra última folha.. não deveria, devia ficar onde eu
// tô lá e só enviar aquele e já ir pra próxima anterior ou posterior..".
// Grade agrupada por disciplina (Arquitetura: D1, D2, D5, D6 · Estrutura: D3, D4); todas conferidas menos a D4. Abre a revisão da D2 (no
// meio de Arquitetura), muda o tipo para Estrutura e salva: tem de ir para a D5 (a vizinha na ordem que a pessoa via), não para a D4 (a única
// pendente). Na D5, "←" volta para a D2 (a sequência não reordenou com a mudança de categoria). Corrigir a última (D6 → D3? não: a última da
// sequência é a D4; testamos a D6 → vai para a D3, a seguinte na grade). Ao fechar e reabrir, vale a grade nova.
// Uso (servidor PRÓPRIO, portas 9110–9139; banco: tests/semear_banco_teste.py + tests/semente_revisao_sequencia.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9136 PRINTS=<pasta> node tests/navegador_revisao_sequencia.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9136';
const PRINTS = process.env.PRINTS || '/dev/shm';
const P = 'F026-P0001', D = n => `${P}-1968-S01-D0000${n}`;
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
(async () => {
  fs.mkdirSync(PRINTS, { recursive: true });
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.evaluate(() => { try { localStorage.setItem('camp.ordem_folhas', 'codigo'); localStorage.removeItem('camp.ordem_folhas.F026-P0001'); } catch (_) {} });
  await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 20000 }); await pg.waitForTimeout(400);
  const grade = await pg.$$eval('#pd .pj-folhas .thumb', T => T.map(t => (t.dataset.revAbrir || '').split('-').pop()));
  chk(JSON.stringify(grade) === JSON.stringify(['D00001', 'D00002', 'D00005', 'D00006', 'D00003', 'D00004']), `grade agrupada por disciplina (${grade.join(' ')})`);
  const aberta = () => pg.evaluate(() => revAberta());
  const esperarAberta = cod => pg.waitForFunction(c => revAberta() === c && !window._REV_SALVANDO && document.querySelector('#d-body [data-rev-item="conferida"]:not([disabled])'), cod, { timeout: 15000 });
  await pg.evaluate(c => abrirRevisaoItem(c), D(2)); await esperarAberta(D(2));
  // muda o tipo da D2: Planta → Estrutura (outra categoria) e salva
  await pg.evaluate(() => { const box = document.querySelectorAll('[data-tipos-para="rv-tipo"] input[type="checkbox"]'); box.forEach(i => { if (i.value === 'Planta' && i.checked) i.click(); }); box.forEach(i => { if (i.value === 'Estrutura' && !i.checked) i.click(); }); });
  await pg.click('#d-body [data-rev-item="conferida"]');
  await pg.waitForFunction(c => revAberta() && revAberta() !== c, D(2), { timeout: 15000 }).catch(() => {});
  await pg.waitForTimeout(600);
  chk((await aberta()) === D(5), `salvar a D2 com outra categoria vai para a vizinha D5 (abriu ${await aberta()})`);
  const tipoD2 = await pg.evaluate(c => (ITENS_PJ.find(x => x.codigo === c) || {}).tipo_documento, D(2));
  chk(/Estrutura/.test(tipoD2 || ''), `a D2 foi salva como Estrutura (${tipoD2})`);
  await esperarAberta(D(5)).catch(() => {});
  await pg.keyboard.press('ArrowLeft'); await pg.waitForTimeout(800);
  chk((await aberta()) === D(2), `na D5, "←" volta para a D2: a sequência não reordenou (abriu ${await aberta()})`);
  await esperarAberta(D(2)).catch(() => {});
  await pg.keyboard.press('ArrowRight'); await pg.waitForTimeout(800);
  await pg.keyboard.press('ArrowRight'); await pg.waitForTimeout(800);
  chk((await aberta()) === D(6), `"→" segue a grade de quando abriu: D2 → D5 → D6 (abriu ${await aberta()})`);
  await esperarAberta(D(6)).catch(() => {});
  await pg.click('#d-body [data-rev-item="conferida"]'); await pg.waitForTimeout(900);
  chk((await aberta()) === D(3), `"Está certo" na D6 (já conferida) vai para a seguinte na grade, a D3 (abriu ${await aberta()})`);
  await pg.screenshot({ path: `${PRINTS}/revisao-sequencia-1440.png` });
  await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(2500);
  const grade2 = await pg.$$eval('#pd .pj-folhas .thumb', T => T.map(t => (t.dataset.revAbrir || '').split('-').pop()));
  chk(grade2.indexOf('D00002') > grade2.indexOf('D00006'), `ao fechar, a grade reagrupa (a D2 foi para Estrutura): ${grade2.join(' ')}`);
  chk(erros.length === 0, 'nenhum erro de JS ' + erros.join(' | ').slice(0, 200));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
