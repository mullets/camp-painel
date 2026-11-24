// CAMP-FIN (24/11/2026): tela Financeiro no navegador de verdade (Playwright + Chromium). Rafael: "relatório de receitas para o contador",
// "Temos como interligar com o Mercado Pago?". Pagamentos SEMEADOS (tests/semente_financeiro.py: todas as fontes + cópia da conta do Mercado
// Pago falsa); nenhuma chamada ao site nem ao Mercado Pago.
//  [A] admin/master vê "Financeiro" em Administração (tecla 6); operador não vê, a tecla não abre e a API dá 403
//  [B] período (mês), "Doações recebidas no período", totais por natureza e por mês, conta com restrição separada
//  [C] filtros de natureza e origem na lista; estorno em vermelho; "a conferir no extrato"
//  [D] botões Exportar CSV e XLSX (seguem o período) baixam
//  [E] "Classificar como…" numa linha recebida direto no Mercado Pago fica lembrado
//  [F] celular (390 px): sem rolagem lateral
// Uso (servidor PRÓPRIO, portas 9060–9069):
//   python3 tests/semear_banco_teste.py   (com CAMP_DB_PATH=/dev/shm/fin/n.db)
//   python3 tests/semente_financeiro.py /dev/shm/fin/n.db
//   (cd backend && CAMP_DB_PATH=/dev/shm/fin/n.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9061)
//   CAMP_BASE=http://127.0.0.1:9061 node tests/navegador_financeiro.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9061';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, deviceScaleFactor: 1, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/previa\?/.test(url) && !/status of 40[39]|ERR_INSUFFICIENT_RESOURCES/.test(m.text())) erros.push(email + ': ' + m.text() + ' @' + url + ' #' + linhas.length); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
const pronto = P => P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && !/Carregando/.test(document.getElementById('fin-linhas').textContent), null, { timeout: 15000 });

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const item = P.locator('#nav button[data-v="financeiro"]');
    chk(await item.isVisible() && (await item.textContent()).includes('Financeiro') && (await item.locator('kbd').textContent()) === '6', '[A] master vê "Financeiro" no menu, com a tecla 6');
    await P.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await P.keyboard.press('6');
    await pronto(P);
    chk(true, '[A] a tecla 6 abre a tela');
    await P.fill('#fin-mes', '2026-11'); await P.dispatchEvent('#fin-mes', 'change');
    await P.waitForFunction(() => FIN.d && FIN.d.periodo.de === '2026-11-01', null, { timeout: 10000 });
    const doa = await P.locator('#fin-doacoes').textContent();
    chk(/Doações recebidas no período: R\$ 3\.530,00 \(6 doações\)/.test(doa), '[B] "Doações recebidas no período: R$ 3.530,00 (6 doações)" em destaque: ' + doa.slice(0, 90));
    const nat = await P.locator('#fin-nat').textContent();
    chk(/Doações \(sem restrição\)R\$ 530,00/.test(nat.replace(/\s+/g, '')) || nat.includes('R$ 530,00'), '[B] totais por natureza (Doações R$ 530,00)');
    chk(nat.includes('Patrocínios') && nat.includes('R$ 14.000,00') && nat.includes('Total') && nat.includes('R$ 19.395,00'), '[B] Patrocínios e total bruto R$ 19.395,00');
    chk((await P.locator('#fin-mes-tab').textContent()).includes('11/2026'), '[B] totais por mês');
    const ct = await P.locator('#fin-conta-tab').textContent();
    chk(ct.includes('Mercado Pago') && ct.includes('PRONAC 2613864') && ct.includes('com restrição'), '[B] conta do projeto (PRONAC 2613864) aparece separada, com restrição');
    chk((await P.locator('#fin-linhas tr').count()) === 18, '[C] 18 linhas no mês');
    await P.selectOption('#fin-f-nat', 'doacoes');
    chk((await P.locator('#fin-linhas tr').count()) === 5, '[C] filtro de natureza: Doações = 5 linhas (com o estorno)');
    chk((await P.locator('#fin-linhas tr.fin-neg').count()) === 1, '[C] estorno marcado como linha negativa');
    await P.selectOption('#fin-f-nat', ''); await P.selectOption('#fin-f-ori', 'ingresso');
    chk((await P.locator('#fin-linhas tr').count()) === 1 && (await P.locator('#fin-linhas').textContent()).includes('Fabio Visita'), '[C] filtro de origem: Ingresso');
    await P.selectOption('#fin-f-ori', 'adocao');
    chk((await P.locator('#fin-linhas').textContent()).includes('a conferir no extrato'), '[C] sem a tarifa lida: "a conferir no extrato"');
    await P.selectOption('#fin-f-ori', '');
    const csv = await P.getAttribute('#fin-csv', 'href'), xl = await P.getAttribute('#fin-xlsx', 'href');
    chk(csv.includes('mes=2026-11') && xl.includes('mes=2026-11'), '[D] exportar segue o período');
    const [dl] = await Promise.all([P.waitForEvent('download'), P.click('#fin-xlsx')]);
    chk(/camp-receitas-2026-11-01-a-2026-11-30\.xlsx/.test(dl.suggestedFilename()), '[D] Exportar XLSX baixa ' + dl.suggestedFilename());
    const [dc] = await Promise.all([P.waitForEvent('download'), P.click('#fin-csv')]);
    chk(/\.csv$/.test(dc.suggestedFilename()), '[D] Exportar CSV baixa');
    const sel = P.locator('#fin-linhas select[data-fin-mp="9001"]');
    chk(await sel.count() === 1, '[E] linha recebida direto no Mercado Pago tem "Classificar como…"');
    await sel.selectOption('patrocinios');
    await P.waitForFunction(() => FIN.d.linhas.some(x => x.mp_id === '9001' && x.natureza === 'patrocinios' && x.classificado), null, { timeout: 10000 });
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU); await P.evaluate(() => go('financeiro')); await pronto(P);
    await P.fill('#fin-mes', '2026-11'); await P.dispatchEvent('#fin-mes', 'change');
    await P.waitForFunction(() => FIN.d && FIN.d.periodo.de === '2026-11-01');
    chk(await P.evaluate(() => FIN.d.linhas.find(x => x.mp_id === '9001').natureza) === 'patrocinios' && (await P.locator('#fin-linhas').textContent()).includes('escolhida à mão'), '[E] a escolha fica lembrada depois de recarregar');
    await P.evaluate(() => API('/api/financeiro/mp/9001/classificar', { method: 'POST', body: JSON.stringify({ natureza: '' }) }));   // volta ao mapa (rodar de novo dá o mesmo resultado)
    await ctx.close();
    const { ctx: cm, page: M } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w: 390, h: 844 });
    await M.evaluate(() => go('financeiro')); await pronto(M);
    chk(await M.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), '[F] celular: sem rolagem lateral');
    await cm.close();
    const { ctx: c2, page: O } = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    chk(!(await O.locator('#nav button[data-v="financeiro"]').isVisible()), '[A] operador não vê o item no menu');
    await O.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await O.keyboard.press('6'); await O.waitForTimeout(500);
    chk(!(await O.evaluate(() => document.getElementById('v-financeiro')?.classList.contains('on'))), '[A] operador: a tecla 6 não abre');
    chk((await O.evaluate(() => fetch('/api/financeiro').then(r => r.status))) === 403, '[A] operador: API 403');
    await c2.close();
    chk(!erros.length, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    chk(false, 'exceção: ' + (e && e.stack || e));
  } finally {
    await browser.close();
  }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
