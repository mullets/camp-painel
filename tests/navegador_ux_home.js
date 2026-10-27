// Home ("Precisa de você") enxuta, no navegador de verdade (Playwright + Chromium):
//  - UX-18: o cartão "decisões" só aparece quando há decisão pendente (nunca "0 decisões — nenhuma esperando").
//  - UX-21: filas pelo papel: o operador vê "Decidir" (de admin) esmaecida e no fim, sem perder os dados; o admin e quem só lê
//    não têm nada esmaecido.
//  - UX-30 desfeito a pedido do Rafael (27/10/2026): qualidade, melhorias, % no site e visitas ao site voltam à coluna da direita,
//    abaixo de "Hoje", e o ritmo à esquerda, SEMPRE abertos (falha se voltarem a um bloco recolhido/escondido); com o GA desligado,
//    "Visitas ao site" mostra "desligado" sem chamar /api/analytics (UX-12). Configurações continua com o painel de visitas.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ag_k/home.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ag_k/home.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8951)
//   CAMP_DB_PATH=/tmp/ag_k/home.db CAMP_BASE=http://127.0.0.1:8951 node tests/navegador_ux_home.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8951', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

async function entrar(browser, email, senha, erros) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
async function abrirHome(page) {
  await page.evaluate(() => { nav('painel'); carregarPainel() });
  await page.waitForSelector('#v-painel .ini-grid #ini-tarefas', { timeout: 15000 });
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const nDec = +py("print(con.execute(\"SELECT COUNT(*) FROM decisao WHERE situacao='pendente'\").fetchone()[0])");
    chk(nDec > 0, `a semente tem decisões pendentes (${nDec})`);
    const adm = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const P = adm.page;

    // ---------- UX-18 ----------
    await abrirHome(P);
    const kDec = () => P.evaluate(() => { const b = document.querySelector('#v-painel .ini-kpi[data-ini-rota="decisoes"]'); return b ? b.textContent.replace(/\s+/g, ' ').trim() : null; });
    let k = await kDec();
    chk(!!k && new RegExp('^' + nDec + '\\s*decis').test(k), `UX-18: com ${nDec} decisões pendentes o cartão aparece: "${k}"`);
    const idsDec = py("ids=[r[0] for r in con.execute(\"SELECT id FROM decisao WHERE situacao='pendente'\")]\ncon.execute(\"UPDATE decisao SET situacao='resolvida' WHERE situacao='pendente'\")\nprint(','.join(map(str,ids)))");
    await abrirHome(P);
    k = await kDec();
    const kp = await P.evaluate(() => [...document.querySelectorAll('#v-painel .ini-kpi')].map(b => b.dataset.iniRota));
    const nKpis = await P.evaluate(() => getComputedStyle(document.querySelector('#v-painel .ini-kpis')).getPropertyValue('--n').trim());
    chk(k === null && !/nenhuma esperando/.test(await P.locator('#v-painel').innerText()), `UX-18: sem decisão pendente o cartão some (era "0 decisões — nenhuma esperando"): ${k}`);
    chk(kp.length >= 1 && !kp.includes('decisoes') && nKpis === String(kp.length), `UX-18: os outros números continuam e a grade se ajusta (${kp.join(', ')}; --n=${nKpis})`);
    py(`con.execute("UPDATE decisao SET situacao='pendente' WHERE id IN (${idsDec})")`);   // devolve a semente como estava
    // ---------- UX-21 ----------
    const grupos = pg => pg.evaluate(() => [...document.querySelectorAll('#ini-tarefas .ini-tg')].map(g => ({ id: g.dataset.iniGrupo, outro: g.classList.contains('ini-outro'), op: +getComputedStyle(g).opacity, linhas: g.querySelectorAll('.ini-task').length, txt: g.querySelector('.ini-tgh').textContent })));
    await abrirHome(P);
    const gA = await grupos(P);
    chk(gA.length > 1 && gA.every(g => !g.outro && g.op === 1), `UX-21: admin (master) executa todas as filas: nada esmaecido (${gA.map(g => g.id).join(', ')})`);
    chk(gA[0].id === 'decidir', `UX-21: para o admin, "Decidir" continua no topo (${gA[0].id})`);
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await abrirHome(op.page);
    const api = await op.page.evaluate(async () => (await (await fetch('/api/painel', { credentials: 'same-origin' })).json()).tarefas.map(g => ({ id: g.id, quem: g.quem, n: g.itens.length })));
    const gO = await grupos(op.page);
    const dO = gO.find(g => g.id === 'decidir'), meusO = gO.filter(g => !g.outro);
    chk(!!dO && dO.outro && dO.op < 1 && /quem faz é um admin/.test(dO.txt), `UX-21: operador vê "Decidir" esmaecida e com "quem faz é um admin" (${JSON.stringify(dO)})`);
    chk(gO[gO.length - 1].id === 'decidir' && meusO.length >= 1 && meusO.every(g => g.op === 1 && api.find(a => a.id === g.id).quem !== 'admin'), `UX-21: as filas do operador vêm primeiro, sem esmaecer; a de admin, no fim (${gO.map(g => g.id + (g.outro ? '*' : '')).join(', ')})`);
    chk(gO.length === api.length && gO.every(g => g.linhas === api.find(a => a.id === g.id).n), `UX-21: nenhuma fila nem linha escondida: só esmaecida (${gO.length} grupos = servidor ${api.length})`);
    const kO = await op.page.evaluate(() => { const b = document.querySelector('#v-painel .ini-kpi[data-ini-rota="decisoes"]'); return b ? { outro: b.classList.contains('ini-outro'), op: +getComputedStyle(b).opacity } : null; });
    chk(!!kO && kO.outro && kO.op < 1, `UX-21: o número de decisões (de admin) esmaecido para o operador: ${JSON.stringify(kO)}`);
    await op.ctx.close();
    const le = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await abrirHome(le.page);
    const gL = await grupos(le.page);
    chk(gL.length >= 1 && gL.every(g => !g.outro), `UX-21: quem só lê não executa nenhuma fila: nada esmaecido, vê tudo (${gL.map(g => g.id).join(', ')})`);
    await le.ctx.close();

    // ---------- UX-30 desfeito a pedido do Rafael (27/10/2026): métricas de volta à grade, sempre abertas ----------
    py(`con.execute("UPDATE configuracao SET valor='' WHERE chave IN ('ga4.propriedade','ga4.conta_servico')"); con.execute("UPDATE configuracao SET valor='0' WHERE chave='analytics.site_kit'")`);
    const chamadasGA = []; P.on('request', r => { if (/\/api\/analytics(\?|$)/.test(r.url())) chamadasGA.push(r.url()); });
    await abrirHome(P);
    await P.waitForSelector('#ini-qualidade .qb-geral', { timeout: 8000 }).catch(() => {});
    await P.waitForTimeout(1500);
    const vis = sel => P.locator(sel).first().isVisible();
    const colunas = await P.evaluate(() => [...document.querySelectorAll('#v-painel .ini-grid > .ini-col')].map(c => [...c.querySelectorAll(':scope > section > .ph h2')].map(h => h.textContent.trim())));
    chk(colunas.length === 2 && JSON.stringify(colunas[0]) === JSON.stringify(['O que fazer agora', 'O caminho do material', 'Ritmo das últimas 2 semanas']),
      `UX-30 desfeito: coluna da esquerda com o ritmo de volta depois do caminho: ${JSON.stringify(colunas[0])}`);
    chk(colunas.length === 2 && JSON.stringify(colunas[1]) === JSON.stringify(['Está tudo funcionando?', 'Hoje', 'Qualidade da base', 'Melhorias de hoje', 'Quanto do acervo já está no site', 'Visitas ao site']),
      `UX-30 desfeito: coluna da direita completa (saúde, Hoje e as métricas abaixo): ${JSON.stringify(colunas[1])}`);
    const recolhido = await P.evaluate(() => ({ det: ['ini-qualidade', 'ini-melhorias', 'ini-ritmo', 'ini-t-site', 'ini-visitas'].filter(id => { const e = document.getElementById(id); return !e || !!e.closest('details'); }), numeros: !!document.getElementById('ini-numeros') }));
    chk(!recolhido.det.length && !recolhido.numeros, `UX-30 desfeito: nenhum bloco recolhido "Números do acervo" na Home: ${JSON.stringify(recolhido)}`);
    const visiveis = [];
    for (const sel of ['#ini-qualidade .qb-geral', '#ini-melhorias', '#ini-ritmo', '#ini-t-site', '#v-painel .ini-prog', '#ini-visitas']) if (await vis(sel)) visiveis.push(sel);
    chk(visiveis.length === 6 && /Folhas/.test(await P.locator('#v-painel .ini-prog').innerText()), `UX-30 desfeito: qualidade, melhorias, ritmo, % no site e visitas visíveis sem clicar em nada: ${visiveis.join(', ')}`);
    const visT = await P.evaluate(() => ({ tag: (document.getElementById('ini-vis-tag') || {}).textContent || '', t: (document.getElementById('ini-visitas') || {}).textContent || '' }));
    chk(visT.tag === 'desligado', `Visitas ao site com o GA desligado mostra "desligado" como antes: ${JSON.stringify(visT).slice(0, 160)}`);
    chk(chamadasGA.length === 0, `UX-12: com o GA desligado a Home não chamou /api/analytics (${chamadasGA.length})`);
    await P.evaluate(() => nav('painel/qualidade')); await P.waitForTimeout(1500);
    chk(await vis('#ini-qualidade .qb-geral'), '"Ver quanto falta em cada fundo" (rota painel/qualidade) leva à qualidade da base, aberta');
    // operador (não admin) também vê as métricas abertas; o cartão de visitas é só de admin, como antes do UX-30
    const op2 = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await abrirHome(op2.page);
    const opV = await op2.page.evaluate(() => ({ q: !!document.querySelector('.ini-grid #ini-qualidade'), m: !!document.querySelector('.ini-grid #ini-melhorias'), r: !!document.querySelector('.ini-grid #ini-ritmo'), v: !!document.getElementById('ini-visitas'), det: !!document.getElementById('ini-numeros') }));
    chk(opV.q && opV.m && opV.r && !opV.v && !opV.det, `operador: métricas abertas na grade, sem o cartão de visitas (só admin): ${JSON.stringify(opV)}`);
    await op2.ctx.close();
    await P.evaluate(() => nav('config'));
    await P.waitForFunction(() => /não está ligado/.test((document.getElementById('cfg-visitas') || {}).textContent || ''), null, { timeout: 8000 }).catch(() => {});
    const cfg = await P.evaluate(() => ({ t: (document.getElementById('cfg-visitas') || {}).textContent || '', tag: (document.getElementById('cfg-vis-tag') || {}).textContent || '', bt: !!document.querySelector('#cfg-visitas [onclick^="diagnosticarAnalytics"]:not([hidden])') }));
    chk(/não está ligado/.test(cfg.t) && cfg.tag === 'desligado' && cfg.bt, `UX-30: Configurações tem "Visitas ao site" com "desligado" e "Ver como ligar": ${JSON.stringify(cfg).slice(0, 160)}`);
    await adm.ctx.close();
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
