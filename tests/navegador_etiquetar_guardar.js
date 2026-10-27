// UX-25 · Etiquetar e guardar ao fim do lote: do dossiê do projeto publicado, "Etiquetar e guardar" abre Etiquetas já preenchida
// (fundo, projeto) com o passo 3 "Onde guardar" sugerindo a próxima CX-###; Imprimir registra no histórico "Impressas", que reimprime igual;
// o último formato e papel valem para a PESSOA (outro navegador, sem localStorage, abre no mesmo formato); o Painel inicial mostra
// "N folhas publicadas sem lugar" e o número some quando as folhas são guardadas.
// Uso (servidor PRÓPRIO, banco próprio):
//   CAMP_DB_PATH=/tmp/ag_h/n.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ag_h/n.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8948)
//   CAMP_DB_PATH=/tmp/ag_h/n.db CAMP_BASE=http://127.0.0.1:8948 node tests/navegador_etiquetar_guardar.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const { execFileSync } = require('child_process');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8948';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const DB = process.env.CAMP_DB_PATH;
if (!DB) { console.error('defina CAMP_DB_PATH (o banco do servidor de teste)'); process.exit(2); }
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
// preparo: Residência Riviera (F023-P0011) publicada com 10 folhas no site e nenhuma com lugar; já existe uma CX-004 compartilhada
execFileSync('python3', ['-c', `
import sqlite3; c = sqlite3.connect(${JSON.stringify(DB)})
c.execute("DELETE FROM item_localizacao"); c.execute("DELETE FROM etiqueta_impressao"); c.execute("DELETE FROM usuario_preferencia WHERE chave LIKE 'etiqueta.%'")
c.execute("DELETE FROM localizacao_fisica")
c.execute("UPDATE projeto SET status_site='no_ar' WHERE codigo='F023-P0011'")
c.execute("UPDATE item SET status_site='nao_publicado' WHERE status_site='no_ar'")
c.execute("UPDATE item SET status_site='no_ar' WHERE codigo IN (SELECT codigo FROM item WHERE projeto_codigo='F023-P0011' ORDER BY codigo LIMIT 10)")
c.execute("INSERT INTO localizacao_fisica (fundo_codigo, tipo, identificador) VALUES (NULL, 'caixa', 'CX-004')")
c.commit()`]);
const login = pg => pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }).then(r => r.status));
(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const ctx = await br.newContext({ viewport: { width: 1400, height: 900 } }); const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.addInitScript(() => { window.__impressoes = 0; window.print = () => { window.__impressoes++; }; document.addEventListener('change', e => console.log('chg', e.target.id, e.target.value, location.hash), true); });
  const LOG = []; pg.on('console', m => { if (/^chg/.test(m.text())) LOG.push(m.text()); }); pg.on('request', r => { if (/preferencias/.test(r.url())) LOG.push(r.method() + ' ' + (r.postData() || '')); });
  await pg.goto(BASE + '/'); await login(pg); await pg.goto(BASE + '/#painel'); await pg.reload();
  const TIT = await pg.evaluate(() => fetch('/api/projetos/F023-P0011/detalhe').then(r => r.json()).then(d => d.projeto.titulo));
  // 1) Painel inicial: contador discreto
  const sl = await pg.waitForSelector('#ini-semlugar', { timeout: 15000 }).then(e => e.textContent()).catch(() => '');
  chk(/10 folhas publicadas sem lugar/.test(sl) && /1 projeto/.test(sl), 'Painel inicial: "10 folhas publicadas sem lugar · em 1 projeto"', sl);
  // 2) dossiê do projeto publicado → "Etiquetar e guardar" (clique 1) → Etiquetas já preenchida
  await pg.goto(BASE + '/#projeto/F023-P0011');
  const bt = await pg.waitForSelector('#pj-status [data-pjs-etiquetar]', { timeout: 15000 }).catch(() => null);
  chk(!!bt, 'o Próximo passo do projeto publicado tem "Etiquetar e guardar"');
  chk(bt && !(await pg.$eval('#pj-status [data-pjs-etiquetar]', b => b.classList.contains('pri'))), '"Etiquetar e guardar" não é o botão azul (o azul continua sendo o do Próximo passo)');
  if (bt) await pg.click('#pj-status [data-pjs-etiquetar]');
  await pg.waitForFunction(() => location.hash.startsWith('#etiquetas/guardar/') && document.getElementById('l-proj').value === 'F023-P0011' && !document.getElementById('f-guardar').hidden, null, { timeout: 15000 }).catch(() => {});
  await pg.waitForFunction(() => document.getElementById('l-guardar-cx').value, null, { timeout: 8000 }).catch(() => {});
  const est = await pg.evaluate(() => ({ fundo: document.getElementById('l-fundo').value, proj: document.getElementById('l-proj').value, aba: document.querySelector('#lab-tabs .on')?.dataset.t,
    prev: (document.querySelector('.lab-preview .label') || {}).textContent || '', guardar: !document.getElementById('f-guardar').hidden, cx: document.getElementById('l-guardar-cx').value,
    sit: document.getElementById('l-guardar-sit').textContent }));
  chk(est.fundo === 'F023' && est.proj === 'F023-P0011' && est.aba === 'projeto' && /F023-P0011/.test(est.prev), 'Etiquetas abre na aba Pasta de projeto com fundo e projeto preenchidos e a prévia pronta', JSON.stringify(est).slice(0, 300));
  chk(est.guardar && est.cx === 'CX-005', 'passo 3 "Onde guardar" aparece com a sugestão da próxima caixa livre (CX-005, já existe CX-004)', est.cx);
  chk(/As 35 folhas deste projeto estão sem lugar/.test(est.sit), 'o passo 3 diz quantas folhas estão sem lugar', est.sit);
  // clique 2: Imprimir → registra no histórico
  await pg.click('#lab-imprimir'); await pg.waitForTimeout(800);
  const imp = await pg.evaluate(() => fetch('/api/etiquetas/impressas').then(r => r.json()));
  chk(await pg.evaluate(() => window.__impressoes) === 1, 'a etiqueta do projeto sai em 2 cliques a partir do dossiê (Etiquetar e guardar → Imprimir)');
  chk(imp.length === 1 && imp[0].tipo === 'projeto' && imp[0].codigo === 'F023-P0011' && imp[0].formato_mm === '100x50' && imp[0].usuario === 'Rafael', 'Imprimir registra no histórico (tipo, código, formato, quem)', JSON.stringify(imp).slice(0, 300));
  // guardar na caixa sugerida
  await pg.click('#l-guardar-bt');
  await pg.waitForFunction(() => /guardadas em CX-005/.test(document.getElementById('l-guardar-res').textContent), null, { timeout: 10000 }).catch(() => {});
  const g = await pg.evaluate(() => ({ res: document.getElementById('l-guardar-res').textContent, sit: document.getElementById('l-guardar-sit').textContent, local: document.getElementById('l-local').value,
    bt: document.getElementById('l-guardar-bt').disabled }));
  chk(g.res.includes(`35 folhas de ${TIT} guardadas em CX-005 (CX-005 foi criada)`), 'Guardar nesta caixa cria a CX-005 e guarda as 35 folhas', g.res);
  chk(/Todas as 35 folhas já têm lugar: CX-005/.test(g.sit) && g.local === 'CX-005' && g.bt, 'depois de guardar: passo 3 diz que todas têm lugar, o Local da etiqueta vira CX-005 e o botão desliga', JSON.stringify(g));
  const sl2 = await pg.evaluate(() => fetch('/api/etiquetas/sem-lugar').then(r => r.json()));
  chk(sl2.folhas === 0, 'nenhuma folha publicada sem lugar depois de guardar', JSON.stringify(sl2));
  // 3) último formato e papel por pessoa
  const putPapel = pg.waitForResponse(r => /eu\/preferencias/.test(r.url()) && r.request().method() === 'PUT' && /etiqueta\.papel/.test(r.request().postData() || ''), { timeout: 10000 }).catch(() => null);
  await pg.selectOption('#l-fmt', '70x35'); await pg.selectOption('#l-papel', 'a4'); await putPapel; await pg.waitForTimeout(300);
  const ctx2 = await br.newContext({ viewport: { width: 1400, height: 900 } }); const pg2 = await ctx2.newPage(); pg2.on('pageerror', e => erros.push(e.message));
  await pg2.goto(BASE + '/'); await login(pg2); await pg2.goto(BASE + '/#etiquetas/projeto/F023-P0011'); await pg2.reload();
  await pg2.waitForSelector('.lab-preview .label', { timeout: 15000 }).catch(() => {}); await pg2.waitForTimeout(500);
  const f2 = await pg2.evaluate(async () => [document.getElementById('l-fmt').value, document.getElementById('l-papel').value, Object.keys(localStorage).filter(k => /lab\.fmt/.test(k)).length, JSON.stringify(AJUDA_VISTAS), await fetch('/api/auth/eu/preferencias').then(r => r.text())]);
  chk(f2[0] === '70x35' && f2[1] === 'a4' && f2[2] === 0, 'outro navegador (sem nada guardado nele): abre no último formato e papel da pessoa (70 × 35, A4)', JSON.stringify(f2));
  await ctx2.close();
  // 4) aba Impressas e Reimprimir
  await pg.selectOption('#l-fmt', '100x50'); await pg.click('#lab-tabs [data-t="documento"]'); await pg.waitForTimeout(400);
  await pg.click('#lab-tabs [data-t="impressas"]');
  await pg.waitForSelector('#lab-impressas-body [data-lab-reimp]', { timeout: 10000 }).catch(() => {});
  const tab = await pg.evaluate(() => ({ vis: !document.getElementById('lab-impressas').hidden, form: document.querySelector('#v-etiquetas .lab-wrap').hidden, linha: (document.querySelector('#lab-impressas-body tr') || {}).textContent || '' }));
  chk(tab.vis && tab.form && /Pasta/.test(tab.linha) && /F023-P0011/.test(tab.linha) && tab.linha.includes(TIT) && /100 × 50/.test(tab.linha) && /Rafael/.test(tab.linha), 'aba Impressas lista o que saiu (o quê, formato, quem) no lugar do formulário', JSON.stringify(tab));
  await pg.selectOption('#l-fmt', '90x29').catch(() => {});
  await pg.click('#lab-impressas-body [data-lab-reimp]');
  await pg.waitForTimeout(1500);
  const re = await pg.evaluate(() => ({ aba: document.querySelector('#lab-tabs .on')?.dataset.t, form: !document.querySelector('#v-etiquetas .lab-wrap').hidden, proj: document.getElementById('l-proj').value, fmt: document.getElementById('l-fmt').value,
    prev: (document.querySelector('.lab-preview .label') || {}).textContent || '' }));
  chk(re.aba === 'projeto' && re.form && re.proj === 'F023-P0011' && re.fmt === '100x50' && /F023-P0011/.test(re.prev), 'Reimprimir volta a etiqueta como saiu (aba, projeto, formato) pronta para Imprimir', JSON.stringify(re).slice(0, 300));
  await pg.click('#lab-imprimir'); await pg.waitForTimeout(800);
  const imp2 = await pg.evaluate(() => fetch('/api/etiquetas/impressas').then(r => r.json()));
  chk(imp2.length === 2 && imp2[0].codigo === 'F023-P0011', 'a reimpressão também entra no histórico', String(imp2.length));
  // 5) Painel inicial: o número some
  await pg.goto(BASE + '/#painel'); await pg.waitForSelector('#ini-t-fazer', { timeout: 15000 }); await pg.waitForTimeout(1200);
  chk(!(await pg.$('#ini-semlugar')), 'Painel inicial: sem folhas publicadas sem lugar, a linha não aparece');
  chk(erros.length === 0, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  if (problemas.length && process.env.DBG) console.log(LOG.join('\n'));
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
