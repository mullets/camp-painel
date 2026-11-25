// CAMP-FICHA (25/11/2026). Rafael, na página do projeto: "gostaria de selecionar várias e colocar o escritório que fez, e que ficasse a
// separação do tipo elétrica, engenharia, fundação, desenhos etc." e "será legal também poder selecionar de várias o que é: estrutura,
// detalhe etc.". Prova, a 1440 px (e a barra a 390 px):
//  - os desenhos aparecem em grupos por disciplina (Arquitetura primeiro), com o número e o escritório; "Agrupar por disciplina" desliga/liga;
//  - "Escolher folhas": clique marca, Shift+clique marca o intervalo, a barra diz "N folhas escolhidas"; o clique não abre a folha;
//  - "Definir escritório parceiro…": prévia "Vai adicionar a N folhas (M já têm)", Aplicar grava no banco e a folha muda de grupo;
//  - "Definir tipo…": prévia com antes → depois e Aplicar grava.
// Uso (servidor PRÓPRIO, portas 9110–9139, banco com tests/semear_banco_teste.py + tests/semente_sugerir_escritorios.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9134 CAMP_DB_PATH=<banco> PRINTS=<pasta> node tests/navegador_disciplinas_lote.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9134';
const PRINTS = process.env.PRINTS || '/dev/shm';
const P = 'F023-P0011', D = n => `${P}-1959-S01-D${String(n).padStart(5, '0')}`;
const problemas = [];
const chk = (ok, msg, det) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' :: ' + det)); if (!ok) problemas.push(msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function espera(f, ms = 8000) { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await sleep(150); } return false; }
const banco = sql => JSON.parse(execFileSync('python3', ['-c', `import sqlite3,sys,json;c=sqlite3.connect(sys.argv[1]);print(json.dumps(c.execute(sys.argv[2]).fetchall()))`, process.env.CAMP_DB_PATH, sql]).toString());
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.evaluate(() => { try { localStorage.removeItem('camp.agruparDisc.rafael@camp.arq.br'); localStorage.setItem('camp.ordem_folhas', 'codigo') } catch (_) {} });
  const abrir = async () => { await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForFunction(() => window.ITENS_PJ && window.ITENS_PJ.length && document.querySelector('.pj-folhas'), null, { timeout: 15000 }); await pg.evaluate(() => { const t = document.getElementById('pj-tab-folhas'); if (t) t.click() }); await sleep(500); };
  await abrir();
  await pg.addStyleTag({ content: '#toast,.toast{display:none!important}' });
  const grupos = () => pg.evaluate(() => [...document.querySelectorAll('.pj-folhas .disc-grupo')].filter(g => !g.hidden && g.offsetParent).map(g => ({ nome: g.dataset.disc, n: +(g.querySelector('.disc-n') || {}).textContent, esc: ((g.querySelector('.disc-cab small') || {}).textContent || '') })));
  let g = await grupos();
  chk(g.length >= 3 && g[0].nome === 'Arquitetura' && g.some(x => x.nome === 'Estrutura' && /DAPA Lima Otero Engenharia/.test(x.esc)) && g.some(x => x.nome === 'Instalações elétricas'), 'desenhos em grupos por disciplina (Arquitetura primeiro), com o escritório', JSON.stringify(g));
  const resumo = await pg.evaluate(() => ([...document.querySelectorAll('.project-series .disc-resumo')].find(x => x.offsetParent) || {}).textContent || '');
  chk(/^Arquitetura \d+ · /.test(resumo), 'resumo na cabeça da série ("Arquitetura N · Estrutura N…")', resumo);
  await pg.evaluate(() => (() => { const h = [...document.querySelectorAll('.project-series-head')].find(x => x.offsetParent); h.scrollIntoView({ block: 'center' }); })()); await sleep(300);
  await pg.screenshot({ path: PRINTS + '/projeto-disciplinas-1440.png' });
  await pg.locator('[data-disc-agrupar]').locator('visible=true').first().click(); await sleep(300);
  chk((await grupos()).length === 0, '"Agrupar por disciplina" desliga: grade como antes');
  await pg.locator('[data-disc-agrupar]').locator('visible=true').first().click(); await sleep(300);
  chk((await grupos()).length >= 3, '…e liga de novo (lembrado)');
  // ---------- escolher ----------
  await pg.locator('.folhas-bar [data-pj-escolher]').locator('visible=true').first().click(); await sleep(200);
  const sel = c => `.pj-folhas .thumb[data-rev-abrir="${c}"],.pj-folhas .thumb[data-nav="item/${c}"]`;
  const clicar = (c, o) => pg.locator(sel(c)).locator('visible=true').first().click(o || {});
  await clicar(D(8)); await clicar(D(10), { modifiers: ['Shift'] }); await clicar(D(20));
  const nsel = await pg.evaluate(() => [...document.querySelectorAll('.pj-folhas .thumb.escolhida')].filter(t => t.offsetParent).length);
  const barra = await pg.evaluate(() => (document.querySelector('#pj-selbar .count') || {}).textContent || '');
  chk(nsel === 4 && /^4 folhas escolhidas$/.test(barra), 'clique + Shift+clique (intervalo) + clique: 4 folhas escolhidas', `${nsel} ${barra}`);
  chk(await pg.evaluate(() => !document.getElementById('drawer')?.classList.contains('on') && !/item\//.test(location.hash)), 'escolhendo, o clique não abre a folha');
  await pg.evaluate(() => document.getElementById('pj-selbar').scrollIntoView({ block: 'end' })); await sleep(200);
  await pg.screenshot({ path: PRINTS + '/projeto-escolher-barra-1440.png' });
  // ---------- definir escritório ----------
  const PARISI = 'Sociedade civil de engenharia José Roberto Parisi Ltd.';
  await pg.click('#pj-selbar [data-pj-esc-acao="adicionar"]');
  await pg.waitForSelector('#conf-ov #pjl-esc');
  await pg.fill('#pjl-esc', PARISI); await pg.selectOption('#pjl-dis', 'Estrutura');
  chk(await espera(() => pg.evaluate(() => /Vai adicionar a 4 folhas/.test((document.getElementById('pjl-previa') || {}).textContent || ''))), 'prévia: "Vai adicionar a 4 folhas"', await pg.evaluate(() => (document.getElementById('pjl-previa') || {}).textContent));
  await pg.screenshot({ path: PRINTS + '/projeto-definir-escritorio-1440.png' });
  chk(banco(`SELECT COUNT(*) FROM item WHERE parceiros LIKE '%Parisi%'`)[0][0] === 0, 'antes de Aplicar, nada no banco');
  await pg.click('#conf-ov [data-conf="sim"]');
  chk(await espera(() => banco(`SELECT COUNT(*) FROM item WHERE parceiros LIKE '%Parisi%'`)[0][0] === 4), 'Aplicar: as 4 folhas ganham o escritório no banco');
  await pg.waitForFunction(() => window.ITENS_PJ && document.querySelector('.pj-folhas .disc-grupo'), null, { timeout: 15000 }); await sleep(600);
  g = await grupos();
  chk(g.some(x => x.nome === 'Estrutura' && /Parisi/.test(x.esc)), 'a página volta com as folhas no grupo Estrutura, com o escritório', JSON.stringify(g));
  // ---------- definir tipo ----------
  await pg.locator('.folhas-bar [data-pj-escolher]').locator('visible=true').first().click(); await sleep(200);
  await clicar(D(11)); await clicar(D(12));
  await pg.click('#pj-selbar [data-pj-esc-tipo]');
  await pg.waitForSelector('#conf-ov input[name="pjt-tipo"]');
  await pg.check('#conf-ov input[name="pjt-modo"][value="acrescentar"]');
  await pg.check('#conf-ov input[name="pjt-tipo"][value="Detalhe"]');
  chk(await espera(() => pg.evaluate(() => /Vai mudar 2 folhas/.test((document.getElementById('pjt-previa') || {}).textContent || '') && /→/.test(document.getElementById('pjt-previa').textContent))), 'tipo: prévia "Vai mudar 2 folhas" com antes → depois', await pg.evaluate(() => (document.getElementById('pjt-previa') || {}).textContent));
  await pg.screenshot({ path: PRINTS + '/projeto-definir-tipo-1440.png' });
  await pg.click('#conf-ov [data-conf="sim"]');
  chk(await espera(() => { const r = banco(`SELECT coalesce(tipos_documento,tipo_documento) FROM item WHERE codigo IN ('${D(11)}','${D(12)}')`); return r.every(x => /Detalhe/.test(x[0] || '')); }), 'Aplicar: o tipo entra nas 2 folhas', JSON.stringify(banco(`SELECT coalesce(tipos_documento,tipo_documento) FROM item WHERE codigo IN ('${D(11)}','${D(12)}')`)));
  // ---------- 390 px: a barra cabe ----------
  await pg.setViewportSize({ width: 390, height: 844 }); await abrir();
  await pg.locator('.folhas-bar [data-pj-escolher]').locator('visible=true').first().click(); await sleep(200); await clicar(D(8));
  const lar = await pg.evaluate(() => ({ sw: document.documentElement.scrollWidth, b: document.getElementById('pj-selbar').getBoundingClientRect().right }));
  chk(lar.sw <= 392 && lar.b <= 392, '390 px: a barra de escolha cabe, sem rolagem lateral', JSON.stringify(lar));
  await pg.evaluate(() => document.getElementById('pj-selbar').scrollIntoView({ block: 'end' })); await sleep(200);
  await pg.screenshot({ path: PRINTS + '/projeto-escolher-barra-390.png' });
  chk(erros.length === 0, 'nenhum erro de JS', erros.join(' | ').slice(0, 300));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
