// CAMP-FIN (24/11/2026): tela Financeiro no navegador de verdade (Playwright + Chromium). Rafael: "relatório de receitas para o contador",
// "Temos como interligar com o Mercado Pago?". Pagamentos SEMEADOS (tests/semente_financeiro.py: todas as fontes + cópia da conta do Mercado
// Pago falsa); nenhuma chamada ao site nem ao Mercado Pago.
//  [A] admin/master vê "Financeiro" em Administração (tecla 6); operador não vê, a tecla não abre e a API dá 403
//  [B] cartões: receitas, despesas, resultado (superávit), doações no período, Precisa justificar; período anterior com as setas
//  [C] Receitas: etiquetas de natureza, estorno em vermelho, rodapé com os totais, busca natural ("doações acima de 200") com as etiquetas
//      entendidas, painel lateral da linha e "Classificar como…" lembrado
//  [D] Despesas · fila "Precisa justificar": uma por vez ("1 de 3"), sugestão com o porquê (tarefa da doação), categoria pelo botão,
//      justificativa, foto do recibo (input com capture), Enter salva e vai para a próxima, Desfazer, Esc fecha, a fila diminui
//  [E] DRE: superávit em destaque, clicar numa linha abre os lançamentos, a conta do PRONAC 2613864 separada
//  [F] Exportar XLSX (receitas e DRE) baixa
//  [G] celular (390 px): sem rolagem lateral; cartões rolam de lado; a fila funciona no celular
// Uso (servidor PRÓPRIO, portas 9060–9069):
//   python3 tests/semear_banco_teste.py   (com CAMP_DB_PATH=/dev/shm/fin/n.db)
//   python3 tests/semente_financeiro.py /dev/shm/fin/n.db      (fontes de receita, conta do Mercado Pago falsa e 3 despesas a justificar)
//   (cd backend && CAMP_DB_PATH=/dev/shm/fin/n.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9061)
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9061 node tests/navegador_financeiro.js
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
  const JPG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(200, 48)]);
  try {
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const item = P.locator('#nav button[data-v="financeiro"]');
    chk(await item.isVisible() && (await item.textContent()).includes('Financeiro') && (await item.locator('kbd').textContent()) === '6', '[A] master vê "Financeiro" no menu, com a tecla 6');
    await P.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await P.keyboard.press('6');
    await P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp, null, { timeout: 15000 });
    chk(true, '[A] a tecla 6 abre a tela');
    const kp = await P.locator('#fin-kpis').innerText();
    chk(kp.includes('R$ 19.395,00') && kp.includes('Receitas (bruto)') && /Resultado · superávit/.test(kp) && kp.includes('R$ 3.530,00') && kp.includes('6 doações'), '[B] cartões: receitas, resultado (superávit) e doações no período: ' + kp.replace(/\s+/g, ' ').slice(0, 160));
    chk(/3\s*Precisa justificar/.test(kp), '[B] cartão "Precisa justificar" com 3');
    await P.click('[data-fin-passo="-1"]'); await P.waitForFunction(() => FIN.d && FIN.d.periodo.de === '2026-10-01', null, { timeout: 10000 });
    chk((await P.locator('#fin-per-txt').textContent()) === 'outubro de 2026', '[B] seta ‹ vai para outubro');
    await P.click('[data-fin-passo="1"]'); await P.waitForFunction(() => FIN.d && FIN.d.periodo.de === '2026-11-01', null, { timeout: 10000 });
    // ---------- [C] Receitas ----------
    await P.click('[data-fin-aba="receitas"]');
    chk((await P.locator('#fin-p-receitas .fin-linha').count()) === 18, '[C] 18 receitas no mês');
    await P.click('#fin-p-receitas [data-fin-nat="doacoes"]');
    chk((await P.locator('#fin-p-receitas .fin-linha').count()) === 5 && (await P.locator('#fin-p-receitas .fin-val.neg').count()) === 1, '[C] etiqueta Doações: 5 linhas, o estorno em vermelho');
    chk((await P.locator('#fin-p-receitas .fin-rodape').innerText()).includes('Bruto R$ 530,00'), '[C] rodapé com o total bruto');
    await P.click('#fin-p-receitas [data-fin-nat=""]');
    await P.fill('#fin-q', 'doações acima de 200');
    await P.waitForFunction(() => FIN.busca && FIN.busca.valor_min === 200, null, { timeout: 10000 });
    const ch = await P.locator('#fin-p-receitas .fin-busca-chips').innerText();
    chk(ch.includes('Doações') && ch.includes('acima de R$ 200,00'), '[C] busca natural: etiquetas entendidas "Doações" e "acima de R$ 200,00"');
    chk((await P.locator('#fin-p-receitas .fin-linha').count()) === 5, '[C] busca natural filtra: 5 doações acima de R$ 200 em vez de 7 (' + await P.locator('#fin-p-receitas .fin-linha').count() + ')');
    await P.click('#fin-p-receitas [data-fin-tira="valor_min"]');
    await P.click('#fin-p-receitas [data-fin-tira="natureza"]');
    await P.locator('#fin-p-receitas .fin-linha', { hasText: 'Gabi Pix' }).click();
    await P.waitForSelector('#fin-lado:not([hidden]) select[data-fin-mp="9001"]');
    chk((await P.locator('#fin-lado').innerText()).includes('Recebido direto no Mercado Pago'), '[C] painel lateral da linha com todos os campos');
    await P.selectOption('#fin-lado select[data-fin-mp="9001"]', 'patrocinios');
    await P.waitForFunction(() => FIN.d.linhas.some(x => x.mp_id === '9001' && x.natureza === 'patrocinios' && x.classificado), null, { timeout: 10000 });
    chk(true, '[C] "Classificar como…" guardado');
    await P.keyboard.press('Escape');
    chk(await P.locator('#fin-lado').isHidden(), '[C] Esc fecha o painel lateral');
    await P.evaluate(() => API('/api/financeiro/mp/9001/classificar', { method: 'POST', body: JSON.stringify({ natureza: '' }) }));
    // ---------- [D] fila Precisa justificar ----------
    await P.click('[data-fin-aba="despesas"]');
    await P.click('#fin-p-despesas [data-fin-acao="fila"]');
    await P.waitForSelector('#fin-fila:not([hidden]) #fin-f-just');
    chk((await P.locator('#fin-fila .n').textContent()) === '1 de 3', '[D] a fila mostra uma por vez: 1 de 3');
    const f1 = await P.locator('#fin-fila').innerText();
    chk(f1.includes('Transportadora Litoral') && f1.includes('320,00'), '[D] valor grande e quem recebeu');
    chk((await P.locator('#fin-fila [data-fin-fsugi]').count()) >= 1 && /ligar à doação/.test(await P.locator('#fin-fila .fin-sug').innerText()), '[D] sugestão de justificativa pela tarefa da doação ("ligar à doação"), com o porquê');
    chk((await P.getAttribute('#fin-fila input[capture]', 'accept')) === 'image/*', '[D] "Fotografar o recibo" abre a câmera no celular (accept image/*, capture)');
    await P.locator('#fin-fila [data-fin-fcat="frete"]').click();
    await P.locator('#fin-fila input[data-fin-arquivo]:not([capture])').setInputFiles({ name: 'recibo.jpg', mimeType: 'image/jpeg', buffer: JPG });
    await P.waitForSelector('#fin-fila .fin-visor img', { timeout: 10000 });
    chk(true, '[D] recibo anexado aparece no visualizador');
    await P.fill('#fin-f-just', 'Frete do acervo doado');
    await P.press('#fin-f-just', 'Enter');
    await P.waitForFunction(() => document.querySelector('#fin-fila .n')?.textContent === '2 de 3', null, { timeout: 10000 });
    chk(true, '[D] Enter salva e vai para a próxima (2 de 3)');
    chk(/Desfazer/.test(await P.locator('#toast').innerText()), '[D] aviso com Desfazer');
    await P.keyboard.press('Escape');
    await P.waitForFunction(() => document.getElementById('fin-fila').hidden && FIN.desp && FIN.desp.n_precisa === 2, null, { timeout: 10000 });
    chk(true, '[D] Esc fecha a fila e sobram 2 para justificar');
    // ---------- [E] DRE ----------
    await P.click('[data-fin-aba="dre"]');
    const dre = await P.locator('#fin-p-dre').innerText();
    chk(/\(=\) Superávit do período/.test(dre) && dre.includes('DRE gerencial, por regime de caixa') && dre.includes('PRONAC 2613864'), '[E] DRE com o superávit, o aviso de regime de caixa e a conta do projeto separada');
    await P.locator('#fin-p-dre tr[data-fin-dre="rec_doacoes"]').click();
    await P.waitForSelector('#fin-lado:not([hidden]) table');
    chk((await P.locator('#fin-lado').innerText()).includes('Doações') && (await P.locator('#fin-lado tbody tr').count()) === 5, '[E] clicar em Doações abre os 5 lançamentos');
    await P.keyboard.press('Escape');
    const [d1] = await Promise.all([P.waitForEvent('download'), P.click('#fin-p-dre a[href*="dre/exportar.xlsx"]')]);
    chk(/camp-dre-2026-11-01-a-2026-11-30\.xlsx/.test(d1.suggestedFilename()), '[F] Exportar a DRE em XLSX');
    await P.click('[data-fin-aba="receitas"]');
    const [d2] = await Promise.all([P.waitForEvent('download'), P.click('#fin-p-receitas a[href*="exportar.xlsx"]')]);
    chk(/camp-receitas-2026-11-01-a-2026-11-30\.xlsx/.test(d2.suggestedFilename()), '[F] Exportar as receitas em XLSX');
    await ctx.close();
    // ---------- [G] celular ----------
    const { ctx: cm, page: M } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w: 390, h: 844 });
    await M.evaluate(() => go('financeiro')); await M.waitForFunction(() => FIN.d && FIN.desp, null, { timeout: 15000 });
    chk(await M.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), '[G] celular: sem rolagem lateral');
    chk(await M.evaluate(() => getComputedStyle(document.getElementById('fin-kpis')).overflowX === 'auto'), '[G] cartões rolam de lado no celular');
    await M.evaluate(() => finFilaAbrir()); await M.waitForSelector('#fin-fila:not([hidden]) #fin-f-just');
    chk(await M.evaluate(() => { const r = document.querySelector('#fin-fila .caixa').getBoundingClientRect(); return r.width >= 380 && document.documentElement.scrollWidth <= window.innerWidth + 1; }), '[G] a fila ocupa a tela do celular');
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
