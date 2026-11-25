// CAMP-PROJETO / CAMP-ESTANTE (25/11/2026). Rafael: "organizar automaticamente as folhas pelo nome … exportar um pdf feito em cima dos tifs
// em alta qualidade … ou um zip só com os tiffs" e "um lote de estrutura total não cabe num tubo só, então vai em vários.. preciso dizer quem
// tá em cada e quais faltam".
// Prova, a 1440 e 390 px, na página do projeto F026-P0001: "Organizar pelo nome" mostra a prévia e grava (Folha 1, 2, 3, 10, 16, 16A);
// "Escolher folhas" → "Guardar em…" tubo novo (TB-F026-P0001.1, .2), mover entre tubos, bloco "Onde estão as folhas" com cada tubo e as
// que faltam; "Escolher as que faltam"; "Exportar…" PDF de uma categoria (tarefa em segundo plano → "Baixar o PDF", arquivo PDF de verdade) e
// .zip só com os TIFF; aba Arquivos originais com "Exportar em lote" e o PDF guardado. Sem rolagem lateral; nenhum erro de JS.
// Uso (servidor PRÓPRIO, portas 9110–9139; banco: tests/semear_banco_teste.py + tests/semente_ordem_pdf.py <qnap>; CAMP_EXPORTACOES_DIR):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9135 PRINTS=<pasta> node tests/navegador_ordem_pdf_tubos.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9135';
const PRINTS = process.env.PRINTS || '/dev/shm';
const P = 'F026-P0001';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const semToast = pg => pg.addStyleTag({ content: '#toast,.toast{display:none!important}' }).catch(() => {});
const semRolagem = pg => pg.evaluate(() => { const m = document.querySelector('.main') || document.documentElement; return document.documentElement.scrollWidth <= window.innerWidth + 1 && m.scrollWidth <= m.clientWidth + 1; });
async function login(br, w) {
  const ctx = await br.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, acceptDownloads: true });
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg, erros };
}
const abrir = async pg => { await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 20000 }); await pg.waitForSelector('#pj-guardados .ph', { timeout: 15000 }); await pg.waitForTimeout(300); };
const confirmarDialogo = async pg => { await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 15000 }); };
const escolher = async (pg, cods) => {
  if (!(await pg.evaluate(() => pjEscolhendo()))) await pg.click('#pd [data-pj-escolher]');
  for (const c of cods) await pg.click(`#pd .pj-folhas .thumb[data-rev-abrir="${c}"], #pd .pj-folhas .thumb[data-nav="item/${c}"]`);
};
(async () => {
  fs.mkdirSync(PRINTS, { recursive: true });
  const br = await chromium.launch();
  for (const w of [1440, 390]) {
    const { ctx, pg, erros } = await login(br, w);
    await abrir(pg); await semToast(pg);
    const F = await pg.evaluate(() => (window.ITENS_PJ || []).filter(i => !i.duplicata_de).map(i => ({ c: i.codigo, f: i.folha })));
    const cod = nome => (F.find(x => x.f === nome) || {}).c;
    if (w === 1440) {
      // 1) Organizar pelo nome
      await pg.click('#pd [data-pj-org-nome]'); await pg.waitForSelector('#conf-ov .pjo-lista');
      const prev = await pg.$$eval('#conf-ov .pjo-lista li', L => L.map(x => x.textContent.trim()));
      chk(prev.length >= 6 && /Folha 1( |$)/.test(prev[0]) && /Folha 2( |$)/.test(prev[1]) && /Folha 16A( |$)/.test(prev[5]), `prévia na ordem pelo nome (${prev.slice(0, 6).join(' | ')})`);
      await pg.screenshot({ path: `${PRINTS}/organizar-pelo-nome-${w}.png` });
      await confirmarDialogo(pg); await pg.waitForTimeout(800);
      const ordem = await pg.evaluate(() => [...ITENS_PJ].filter(i => !i.duplicata_de).sort((a, b) => a.ordem_manual - b.ordem_manual).map(i => i.folha));
      chk(JSON.stringify(ordem) === JSON.stringify(['1', '2', '3', '10', '16', '16A']), `ordem gravada: ${ordem.join(', ')}`);
      const grade = await pg.$$eval('#pd .pj-folhas .thumb', T => T.map(t => (t.textContent.match(/Folha \d+A?/) || [''])[0]).filter(Boolean));
      chk(grade[0] === 'Folha 1' && grade[3] === 'Folha 10', `a grade mostra a ordem nova (${grade.join(', ')})`);
      // 2) Guardar em… tubos
      await escolher(pg, [cod('16'), cod('16A')]);
      await pg.click('#pj-selbar [data-pj-esc-guardar]'); await pg.waitForSelector('#conf-ov input[name="pgu-onde"]');
      chk((await pg.textContent('#conf-ov')).includes('TB-F026-P0001.1'), 'Guardar em…: oferece o tubo novo TB-F026-P0001.1');
      await pg.fill('#pgu-desc', 'estrutura 1 de 2');
      await pg.screenshot({ path: `${PRINTS}/guardar-em-${w}.png` });
      await confirmarDialogo(pg); await pg.waitForTimeout(500);
      let bloco = await pg.textContent('#pj-guardados');
      chk(/TB-F026-P0001\.1/.test(bloco) && /faltam guardar 4/i.test(bloco), 'Onde estão as folhas: TB-F026-P0001.1 e "faltam guardar 4"');
      await escolher(pg, [cod('10'), cod('3')]);
      await pg.click('#pj-selbar [data-pj-esc-guardar]'); await pg.waitForSelector('#conf-ov input[name="pgu-onde"]'); await confirmarDialogo(pg); await pg.waitForTimeout(500);
      await escolher(pg, [cod('3')]);
      await pg.click('#pj-selbar [data-pj-esc-guardar]'); await pg.waitForSelector('#conf-ov input[name="pgu-onde"]');
      await pg.check('#conf-ov input[name="pgu-onde"][value="existe"]');
      const opt = await pg.$$eval('#pgu-loc option', O => O.map(o => ({ v: o.value, t: o.textContent })));
      const tubo1 = opt.find(o => o.t.includes('TB-F026-P0001.1'));
      await pg.selectOption('#pgu-loc', tubo1 ? tubo1.v : opt[0].v);
      chk((await pg.textContent('#conf-ov')).includes('vai mudar'), 'mover: o diálogo avisa que a folha já guardada vai mudar de lugar');
      await confirmarDialogo(pg); await pg.waitForTimeout(500);
      const recs = await pg.$$eval('#pj-guardados .pgu-rec', R => R.map(r => r.querySelector('b').textContent + ':' + r.querySelectorAll('.pgu-folhas li').length));
      chk(JSON.stringify(recs) === JSON.stringify(['TB-F026-P0001.1:3', 'TB-F026-P0001.2:1']), `cada tubo com as suas folhas (${recs.join(', ')})`);
      bloco = await pg.textContent('#pj-guardados');
      chk(/Faltam guardar \(2\)/.test(bloco), 'faltam guardar 2, listadas');
      await pg.click('#pj-guardados [data-pgu-escolher-faltam]'); await pg.waitForTimeout(300);
      const n = await pg.evaluate(() => PJ_ESC.size);
      chk(n === 2 && (await pg.textContent('#pj-selbar .count')).includes('2 folhas escolhidas'), '"Escolher as que faltam" marca as 2 na grade');
      await pg.locator('#pj-guardados').scrollIntoViewIfNeeded();
      await pg.locator('#pj-guardados').screenshot({ path: `${PRINTS}/onde-estao-as-folhas-${w}.png` });
      await pg.screenshot({ path: `${PRINTS}/selecao-barra-${w}.png` });
      await pg.click('#pj-selbar [data-pj-escolher]');
      // 3) Exportar PDF de uma categoria
      await pg.click('#pd .fb-disc [data-pj-exportar]'); await pg.waitForSelector('#conf-ov #pex-cat');
      const cats = await pg.$$eval('#pex-cat option', O => O.map(o => o.value));
      chk(cats.includes('disc:Estrutura') && cats.includes('disc:Arquitetura'), `categorias por disciplina (${cats.join(', ')})`);
      await pg.selectOption('#pex-cat', 'disc:Estrutura');
      await pg.waitForFunction(() => /página/.test((document.getElementById('pex-previa') || {}).textContent || ''), null, { timeout: 8000 });
      const prv = await pg.textContent('#pex-previa');
      chk(/1 página/.test(prv) && /Fora do PDF: 1 folha/.test(prv), `estimativa: 1 página, 1 folha de fora sem TIFF (${prv.slice(0, 160)})`);
      await pg.screenshot({ path: `${PRINTS}/exportar-${w}.png` });
      await confirmarDialogo(pg);
      const lk = await pg.waitForSelector('a:has-text("Baixar o PDF")', { timeout: 30000 }).catch(() => null);
      const href = lk ? await lk.getAttribute('href') : '';
      const resp = href ? await pg.request.get(BASE + href) : null;
      const corpo = resp ? await resp.body() : Buffer.from('');
      chk(resp && resp.status() === 200 && corpo.slice(0, 5).toString() === '%PDF-' && !corpo.includes('/DCTDecode'), 'tarefa termina com "Baixar o PDF": PDF de verdade, sem JPEG');
      await pg.screenshot({ path: `${PRINTS}/exportar-pronto-${w}.png` });
      // 4) .zip do projeto inteiro
      await pg.click('#pd .fb-disc [data-pj-exportar]'); await pg.waitForSelector('#conf-ov #pex-cat');
      await pg.check('#conf-ov input[name="pex-oq"][value="todas"]'); await pg.check('#conf-ov input[name="pex-fmt"][value="zip"]');
      const [dl] = await Promise.all([pg.waitForEvent('download', { timeout: 15000 }).catch(() => null), confirmarDialogo(pg)]);
      chk(dl && /F026-P0001-TIFF.*\.zip$/.test(dl.suggestedFilename()), `.zip só com os TIFF do projeto inteiro (${dl && dl.suggestedFilename()})`);
      // 5) aba Arquivos originais: Exportar em lote + PDF guardado
      await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('[data-pj-tab="originais"]', { timeout: 20000 }); await pg.click('[data-pj-tab="originais"]');
      await pg.waitForSelector('#pj-exportar #pex-lista li', { timeout: 15000 }).catch(() => {}); await semToast(pg);
      chk((await pg.textContent('#pj-exportar')).includes('Estrutura'), 'aba Arquivos originais: "Exportar em lote" com o PDF guardado');
      await pg.locator('#pj-exportar').screenshot({ path: `${PRINTS}/exportar-em-lote-${w}.png` });
    } else {
      chk(await semRolagem(pg), '390 px: página do projeto sem rolagem lateral');
      await pg.locator('#pj-guardados').scrollIntoViewIfNeeded();
      await pg.locator('#pj-guardados').screenshot({ path: `${PRINTS}/onde-estao-as-folhas-${w}.png` });
      await escolher(pg, [F[0].c]);
      await pg.click('#pj-selbar [data-pj-esc-guardar]'); await pg.waitForSelector('#conf-ov input[name="pgu-onde"]');
      await pg.screenshot({ path: `${PRINTS}/guardar-em-${w}.png` });
      chk(await pg.evaluate(() => { const b = document.querySelector('#conf-ov .conf-box'); return b && b.scrollWidth <= b.clientWidth + 1; }), '390 px: diálogo Guardar em… sem rolagem lateral');
      await pg.click('#conf-ov [data-conf="nao"]').catch(() => pg.keyboard.press('Escape'));
      await pg.click('#pj-selbar [data-pj-esc-exportar]'); await pg.waitForSelector('#conf-ov #pex-cat'); await pg.waitForTimeout(600);
      await pg.screenshot({ path: `${PRINTS}/exportar-${w}.png` });
      chk(await pg.evaluate(() => { const b = document.querySelector('#conf-ov .conf-box'); return b && b.scrollWidth <= b.clientWidth + 1; }), '390 px: diálogo Exportar sem rolagem lateral');
      await pg.keyboard.press('Escape');
    }
    chk(erros.length === 0, `${w} px: nenhum erro de JS ${erros.join(' | ').slice(0, 200)}`);
    await ctx.close();
  }
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
