// CAMP-FICHA (25/11/2026). Rafael, na conferência de uma folha de estrutura cujo carimbo só tinha o escritório de cálculo ("DAPA LIMA
// OTERO ENGENHARIA LTDA. S/C." lido como Cliente; tipo lido "Detalhe / Estrutura"): "ver se outras folhas desse projeto têm algum
// escritório e já sugerir, pq essa praticamente só tem isso".
// Prova, a 1440 px, na gaveta de conferir:
//  - folha sem parceiros: "Nas outras folhas deste projeto" lista os escritórios das outras folhas (a mesma disciplina primeiro, "· N folhas"),
//    com "Usar"; o primeiro fica em cinza no nome vazio e Tab aceita (nome + disciplina);
//  - Cliente lido que parece escritório: aviso "Parece o escritório de estrutura, não o cliente" + "Mover para Escritórios parceiros";
//    o clique esvazia o Cliente, põe o escritório (com a grafia das outras folhas) e sugere o cliente das outras folhas em cinza;
//  - nada grava sem salvar; "Está certo" grava cliente vazio e o escritório.
// Uso (servidor PRÓPRIO, portas 9110–9139, banco com tests/semear_banco_teste.py + tests/semente_sugerir_escritorios.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9134 CAMP_DB_PATH=<banco> node tests/navegador_sugerir_escritorios.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9134';
const PRINTS = process.env.PRINTS || '/dev/shm';
const P = 'F023-P0011', D = n => `${P}-1959-S01-D${String(n).padStart(5, '0')}`;
const problemas = [];
const chk = (ok, msg, det) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' :: ' + det)); if (!ok) problemas.push(msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function espera(f, ms = 8000) { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await sleep(150); } return false; }
const banco = sql => execFileSync('python3', ['-c', `import sqlite3,sys,json;c=sqlite3.connect(sys.argv[1]);print(json.dumps(c.execute(sys.argv[2]).fetchall()))`, process.env.CAMP_DB_PATH, sql]).toString();
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  await pg.waitForFunction(() => window.ITENS_PJ && window.ITENS_PJ.length, null, { timeout: 15000 });
  const semToast = () => pg.addStyleTag({ content: '#toast,.toast{display:none!important}' });
  // ---------- folha 1: estrutura, só o escritório no carimbo (lido como Cliente) ----------
  await pg.evaluate(c => abrirRevisaoItem(c), D(1));
  chk(await espera(() => pg.evaluate(() => !!document.querySelector('#d-body .parc-sug'))), 'folha sem parceiros: aparece "Nas outras folhas deste projeto"');
  const s1 = await pg.evaluate(() => ({ linhas: [...document.querySelectorAll('#d-body .parc-sug-linha')].map(x => x.textContent.replace(/\s+/g, ' ').trim()), nota: (document.querySelector('#d-body .parc-sug>small') || {}).textContent || '', ph: (document.querySelector('#d-body .parc-esc') || {}).placeholder || null, aviso: (document.querySelector('#d-body .cli-escritorio') || {}).textContent || '', cli: document.getElementById('rv-cliente').value }));
  chk(s1.linhas.length === 2 && /^DAPA Lima Otero Engenharia · Estrutura · 2 folhas/.test(s1.linhas[0]) && /mesma disciplina/.test(s1.linhas[0]) && /^Eletro Projetos · Instalações elétricas · 3 folhas/.test(s1.linhas[1]), 'escritórios das outras folhas, a mesma disciplina primeiro, com quantas folhas', JSON.stringify(s1.linhas));
  chk(/esta folha parece de estrutura/.test(s1.nota), 'diz que a folha parece de estrutura', s1.nota);
  chk(/Parece o escritório de estrutura, não o cliente/.test(s1.aviso) && /2 folhas/.test(s1.aviso), 'aviso embaixo do Cliente: parece o escritório de estrutura (já em 2 folhas)', s1.aviso);
  chk(s1.cli === 'DAPA LIMA OTERO ENGENHARIA LTDA. S/C.', 'nada muda sozinho: o Cliente continua o lido', s1.cli);
  await semToast(); await sleep(300);
  const foto = async nome => { await pg.evaluate(() => document.getElementById('rv-cliente').scrollIntoView({ block: 'start' })); await sleep(250); await pg.screenshot({ path: PRINTS + '/' + nome }); };
  await foto('escritorios-sugeridos-1440.png');
  // mover
  await pg.click('#d-body [data-cli-mover]'); await sleep(300);
  const s2 = await pg.evaluate(() => { const h = document.getElementById('rv-parceiros'), c = document.getElementById('rv-cliente'); return { h: h.value, cli: c.value, ph: c.placeholder, sug: !!document.getElementById('rv-cliente-sug'), aviso: !!document.querySelector('#d-body .cli-escritorio'), box: document.querySelectorAll('#d-body .parc-sug-linha').length, alt: c.closest('.rev-campo').classList.contains('alterado') }; });
  chk(JSON.parse(s2.h).length === 1 && JSON.parse(s2.h)[0].e === 'DAPA Lima Otero Engenharia' && JSON.parse(s2.h)[0].d === 'Estrutura', '"Mover": o escritório entra como parceiro (grafia das outras folhas, Estrutura)', s2.h);
  chk(s2.cli === '' && s2.alt && !s2.aviso, '"Mover": o Cliente fica vazio (marcado como alterado) e o aviso some', JSON.stringify(s2));
  chk(s2.ph === 'Sr. Antonio Rodrigues' && s2.sug, 'Cliente vazio: o cliente das outras folhas aparece em cinza (Tab aceita)', JSON.stringify(s2));
  chk(s2.box === 0, 'com um escritório na folha, a lista de sugestões some', String(s2.box));
  await foto('escritorios-depois-de-mover-1440.png');
  chk(JSON.parse(banco(`SELECT cliente_folha, parceiros FROM item WHERE codigo='${D(1)}'`))[0][0] === 'DAPA LIMA OTERO ENGENHARIA LTDA. S/C.', 'antes de salvar, nada mudou no banco');
  await pg.evaluate(() => { const b = document.querySelector('#d-body [data-rev-item="conferida"]'); if (b) b.dataset.ok = '1'; });   // a semente não tem imagem: pula a confirmação "sem ver a imagem"
  await pg.click('#d-body [data-rev-item="conferida"]');
  // a semente não tem tipo: confirma "Conferir sem tipo documental?"
  const semTipo = pg.locator('#conf-ov button', { hasText: 'Conferir sem tipo' });
  if (await semTipo.count().catch(() => 0) || await espera(async () => (await semTipo.count()) > 0, 2500)) await semTipo.first().click();
  const gravou = await espera(() => { const r = JSON.parse(banco(`SELECT cliente_folha, parceiros FROM item WHERE codigo='${D(1)}'`))[0]; return !r[0] && /DAPA Lima Otero Engenharia/.test(r[1] || ''); });
  chk(gravou, '"Está certo" grava: Cliente vazio e o escritório parceiro', banco(`SELECT cliente_folha, parceiros FROM item WHERE codigo='${D(1)}'`));
  // ---------- folha 6: sem parceiros, cliente real: Tab no nome aceita o primeiro ----------
  await pg.evaluate(c => abrirRevisaoItem(c), D(6));
  chk(await espera(() => pg.evaluate(c => (document.getElementById('d-sub') || {}).textContent === c && !!document.querySelector('#d-body .parc-sug'), D(6))), 'folha 6: sugestões aparecem');
  const s3 = await pg.evaluate(() => ({ aviso: !!document.querySelector('#d-body .cli-escritorio'), linhas: document.querySelectorAll('#d-body .parc-sug-linha').length }));
  chk(!s3.aviso, 'cliente real (pessoa): sem aviso de escritório');
  let tem = await pg.$('#d-body .parc-esc');
  if (!tem) { await pg.click('#d-body [data-parc-add]'); await sleep(200); await pg.evaluate(() => { const r = PARC_SUG['rv-parceiros']; const bl = document.getElementById('rv-parceiros').closest('[data-parc-bloco]'); parcSugDesenhar(bl, r) }); }
  const ph = await pg.evaluate(() => { const e = document.querySelector('#d-body .parc-esc'); return e ? { ph: e.placeholder, cls: e.className } : null; });
  chk(ph && /DAPA Lima Otero Engenharia|Eletro Projetos/.test(ph.ph) && /sugerido/.test(ph.cls), 'nome vazio: o primeiro escritório em cinza', JSON.stringify(ph));
  await pg.focus('#d-body .parc-esc'); await pg.keyboard.press('Tab'); await sleep(200);
  const s4 = await pg.evaluate(() => JSON.parse(document.getElementById('rv-parceiros').value || '[]'));
  chk(s4.length === 1 && s4[0].e && s4[0].d, 'Tab no nome aceita o primeiro (nome + disciplina)', JSON.stringify(s4));
  // ---------- 390 px: o bloco cabe ----------
  chk(erros.length === 0, 'nenhum erro de JS', erros.join(' | ').slice(0, 300));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
