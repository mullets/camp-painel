// CAMP-FIN contas fixas (24/11/2026): Financeiro → Contas fixas no navegador de verdade (Playwright + Chromium). Rafael: "Aluguel, funcionário?".
// Saídas do Mercado Pago SEMEADAS (tests/semente_financeiro.py --contas-fixas); nenhuma chamada ao site nem ao Mercado Pago.
//  [A] aba Contas fixas vazia com "Novo compromisso"; criar o aluguel (pista, valor, dia) e o salário (a pessoa só aparece em categoria de pessoal)
//  [B] grade jan–dez: aluguel pago em outubro e novembro (falta confirmar), a vencer em dezembro; salário atrasado em outubro e pago em novembro;
//      totais Comprometido e Pago; "Este mês" na aba e na Visão geral
//  [C] fila Precisa justificar: "Parece Aluguel da sede (novembro/2026)" com o porquê; um clique ("Confirmar: Aluguel da sede · novembro/2026")
//      grava categoria e justificativa e o mês fica confirmado
//  [D] sugestão do detector de recorrentes: "Transformar em conta fixa" abre o formulário preenchido
//  [E] DRE com a linha Ocupação e "Aluguel e condomínio" logo abaixo; [F] exportação com "agrupar pessoal" (padrão ligado, sem nomes)
//  [G] Home do admin: alerta de conta atrasada sem o nome da pessoa; [H] celular sem rolagem lateral; [I] operador: 403
// Uso (servidor PRÓPRIO, portas 9070–9079):
//   CAMP_DB_PATH=/dev/shm/cfn/n.db python3 tests/semear_banco_teste.py
//   python3 tests/semente_financeiro.py /dev/shm/cfn/n.db --contas-fixas
//   (cd backend && CAMP_DB_PATH=/dev/shm/cfn/n.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9071)
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9071 CAMP_PRINTS=/caminho/das/capturas node tests/navegador_contas_fixas.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9071';
const PRINTS = process.env.CAMP_PRINTS || '';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const foto = async (P, nome, sel) => { if (!PRINTS) return; fs.mkdirSync(PRINTS, { recursive: true }); await (sel ? P.locator(sel).screenshot({ path: `${PRINTS}/${nome}.png` }) : P.screenshot({ path: `${PRINTS}/${nome}.png`, fullPage: false })); };

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, deviceScaleFactor: 1, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/previa\?/.test(url) && !/status of 40[39]|ERR_INSUFFICIENT_RESOURCES/.test(m.text())) erros.push(email + ': ' + m.text() + ' @' + url); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
const cel = (P, nome, mes) => P.evaluate(([n, m]) => { const tr = [...document.querySelectorAll('#fin-cf-grade tbody tr')].find(t => t.querySelector('.fin-cf-nome') && t.querySelector('.fin-cf-nome').firstChild.textContent === n);
  const c = tr && tr.children[m] && tr.children[m].querySelector('.fin-cf-cel'); return c ? c.className.replace('fin-cf-cel', '').trim() : (tr ? 'vazio' : 'sem linha'); }, [nome, mes]);

async function criar(P, campos) {
  await P.click('#fin-p-fixas [data-fin-acao="cf-novo"]');
  await P.waitForSelector('#fin-lado:not([hidden]) #fin-cf-nome');
  await P.fill('#fin-cf-nome', campos.nome);
  await P.selectOption('#fin-cf-cat', campos.categoria);
  await P.fill('#fin-cf-valor', campos.valor);
  await P.fill('#fin-cf-dia', String(campos.dia));
  await P.fill('#fin-cf-pista', campos.pista);
  await P.fill('#fin-cf-ini', campos.inicio);
  if (campos.pessoa) { await P.fill('#fin-cf-pnome', campos.pessoa); await P.fill('#fin-cf-pemail', campos.email); }
  if (campos.antes) await campos.antes();
  await P.click('[data-fin-acao="cf-salvar"]');
  await P.waitForFunction(n => document.getElementById('fin-lado').hidden && FIN.cf && FIN.cf.contas.some(x => x.nome === n) && document.getElementById('fin-cf-grade'), campos.nome, { timeout: 15000 });
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await P.evaluate(() => go('financeiro/contas-fixas'));
    await P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.cf && !document.getElementById('fin-p-fixas').hidden, null, { timeout: 15000 });
    const vazio = await P.locator('#fin-p-fixas').innerText();
    chk(vazio.includes('Nenhuma conta fixa ainda.') && vazio.includes('Novo compromisso') && (await P.locator('#fin-abas [data-fin-aba="fixas"]').getAttribute('aria-selected')) === 'true', '[A] a rota abre a aba Contas fixas, vazia, com "Novo compromisso"');
    // ---------- [A] criar ----------
    await criar(P, { nome: 'Aluguel da sede', categoria: 'aluguel', valor: '3.000,00', dia: 5, pista: 'Imobiliária Sol', inicio: '2026-10-01',
      antes: async () => chk(await P.locator('#fin-cf-pessoa').isHidden(), '[A] aluguel: sem os campos da pessoa') });
    await criar(P, { nome: 'Salário · Ana Souza', categoria: 'salarios', valor: '2.500,00', dia: 5, pista: 'Ana Souza', inicio: '2026-10-01', pessoa: 'Ana Souza', email: 'ana@exemplo.com',
      antes: async () => chk(await P.locator('#fin-cf-pessoa').isVisible() && (await P.locator('#fin-cf-pessoa').innerText()).includes('Salário é dado sensível'), '[A] salário: os campos da pessoa aparecem, com o aviso de dado sensível') });
    await criar(P, { nome: 'INSS', categoria: 'encargos', valor: '700', dia: 20, pista: 'INSS', inicio: '2026-11-01' });
    chk(true, '[A] três contas fixas criadas pelo formulário (aluguel, salário, INSS)');
    // ---------- [B] grade ----------
    chk(await cel(P, 'Aluguel da sede', 10) === 'pago conf' && await cel(P, 'Aluguel da sede', 11) === 'pago conf' && await cel(P, 'Aluguel da sede', 12) === 'a_vencer' && await cel(P, 'Aluguel da sede', 9) === 'vazio',
      '[B] aluguel: pago em out e nov (falta confirmar), a vencer em dez, nada antes do começo');
    chk(await cel(P, 'Salário · Ana Souza', 10) === 'atrasado' && await cel(P, 'Salário · Ana Souza', 11) === 'pago conf', '[B] salário: atrasado em outubro (sem a saída), pago em novembro');
    chk(await cel(P, 'INSS', 11) === 'atrasado', '[B] INSS: dia 20 + 3 dias passou (hoje 24/11) = atrasado');
    const grade = await P.locator('#fin-p-fixas').innerText();
    chk(grade.includes('Comprometido') && grade.includes('Pago') && grade.includes('6.200,00') && grade.includes('5.500,00'), '[B] linhas Comprometido (R$ 6.200) e Pago (R$ 5.500) em novembro');
    chk(grade.includes('Este mês: 2 contas fixas pagas de 3 · R$ 700,00 a pagar'), '[B] "Este mês: 2 contas fixas pagas de 3 · R$ 700,00 a pagar"');
    await foto(P, '1-contas-fixas-grade', '#fin-p-fixas');
    await P.click('#fin-cf-grade button.fin-cf-cel.pago >> nth=0');
    await P.waitForSelector('#fin-lado:not([hidden]) #fin-d-cat');
    chk((await P.locator('#fin-lado-tit').innerText()).includes('IMOBILIARIA SOL'), '[B] clicar no ✓ abre a despesa que pagou');
    await P.keyboard.press('Escape');
    await P.click('[data-fin-aba="geral"]');
    chk((await P.locator('#fin-cf-este').innerText()).includes('Este mês: 2 contas fixas pagas de 3 · R$ 700,00 a pagar'), '[B] Visão geral: a linha "Este mês" das contas fixas');
    await foto(P, '2-visao-geral-este-mes', '#fin-cf-este');
    // ---------- [C] fila ----------
    await P.evaluate(() => finFilaAbrir()); await P.waitForSelector('#fin-fila:not([hidden]) #fin-f-just');
    for (let i = 0; i < 8 && !(await P.locator('#fin-fila-cf').count() && (await P.locator('#fin-fila-cf').innerText()).includes('Aluguel da sede (novembro/2026)')); i++) {
      await P.click('[data-fin-acao="fila-pular"]'); await P.waitForTimeout(300);
    }
    const ban = await P.locator('#fin-fila-cf').innerText().catch(() => '');
    chk(ban.includes('Parece Aluguel da sede (novembro/2026)') && ban.includes('Por quê: “Imobiliária Sol” na descrição do Mercado Pago') && ban.includes('Confirmar: Aluguel da sede · novembro/2026'), '[C] fila: "Parece Aluguel da sede (novembro/2026)" com o porquê e o botão de um clique');
    chk((await P.locator('#fin-f-just').inputValue()) === 'Aluguel da sede · novembro/2026' && (await P.locator('#fin-fila [data-fin-fcat="aluguel"]').getAttribute('aria-pressed')) === 'true', '[C] categoria e justificativa já preenchidas');
    await foto(P, '3-fila-confirmar-conta-fixa', '#fin-fila .caixa');
    const did = await P.evaluate(() => FIN.fila.x.id);
    await P.click('[data-fin-acao="fila-cf"]');
    await P.waitForFunction(id => !FIN.fila || FIN.fila.x.id !== id || FIN.fila.i >= FIN.fila.ls.length, did, { timeout: 10000 });
    const dj = await P.evaluate(id => fetch('/api/financeiro/despesas/' + id).then(r => r.json()), did);
    chk(dj.categoria === 'aluguel' && dj.justificativa === 'Aluguel da sede · novembro/2026', '[C] um clique gravou a categoria e a justificativa');
    await P.keyboard.press('Escape');
    await P.waitForFunction(() => document.getElementById('fin-fila').hidden && FIN.cf, null, { timeout: 10000 });
    await P.click('[data-fin-aba="fixas"]'); await P.waitForTimeout(400);
    chk(await cel(P, 'Aluguel da sede', 11) === 'pago', '[C] na grade o aluguel de novembro fica pago e confirmado (sem o tracejado)');
    // ---------- [D] sugestão ----------
    const sg = P.locator('#fin-p-fixas [data-fin-cf-sug]').first();
    chk((await P.locator('#fin-p-fixas').innerText()).includes('Parece um pagamento mensal: transformar em conta fixa?') && await sg.isVisible(), '[D] sugestão do detector de recorrentes (hospedagem)');
    await sg.click(); await P.waitForSelector('#fin-lado:not([hidden]) #fin-cf-nome');
    chk((await P.inputValue('#fin-cf-pista')) === 'Hospedagem Web Ltda' && (await P.inputValue('#fin-cf-dia')) === '12' && (await P.inputValue('#fin-cf-valor')) === '89,9', '[D] "Transformar em conta fixa" abre o formulário preenchido (pista, dia, valor)');
    await P.keyboard.press('Escape');
    // ---------- [E] DRE ----------
    await P.click('[data-fin-aba="dre"]');
    const dre = await P.locator('#fin-p-dre').innerText();
    chk(dre.includes('Ocupação (aluguel, condomínio e contas de consumo)') && dre.includes('Aluguel e condomínio') && dre.includes('Pessoal (salários, encargos, bolsas e estágio, autônomos e RPA)'), '[E] DRE: Ocupação com "Aluguel e condomínio" abaixo, e Pessoal');
    await foto(P, '4-dre-ocupacao-pessoal', '#fin-p-dre .fin-card');
    // ---------- [F] exportação ----------
    await P.click('[data-fin-aba="despesas"]');
    chk(await P.locator('#fin-agrupar').isChecked() && /agrupar_pessoal=1/.test(await P.getAttribute('#fin-p-despesas a[data-fin-exp="csv"]', 'href')), '[F] "agrupar pessoal" ligado por padrão');
    await P.evaluate(() => fetch('/api/financeiro/contas-fixas/' + FIN.cf.contas.find(x => x.nome.startsWith('Salário')).id + '/confirmar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ despesa_id: FIN.desp.itens.find(x => x.contraparte === 'ANA SOUZA').id, competencia: '2026-11' }) }));
    const csv1 = await P.evaluate(h => fetch(h).then(r => r.text()), await P.getAttribute('#fin-p-despesas a[data-fin-exp="csv"]', 'href'));
    await P.uncheck('#fin-agrupar');
    const h0 = await P.getAttribute('#fin-p-despesas a[data-fin-exp="csv"]', 'href');
    const csv0 = await P.evaluate(h => fetch(h).then(r => r.text()), h0);
    chk(!csv1.includes('ANA SOUZA') && csv1.includes('Pessoal agrupado: total sem nomes') && /agrupar_pessoal=0/.test(h0) && csv0.includes('ANA SOUZA'), '[F] CSV agrupado sem o nome; desmarcado, com as linhas');
    const [dl] = await Promise.all([P.waitForEvent('download'), P.click('#fin-p-despesas a[data-fin-exp="xlsx"]')]);
    chk(/camp-receitas-2026-11-01-a-2026-11-30\.xlsx/.test(dl.suggestedFilename()), '[F] XLSX baixa');
    // ---------- [G] Home ----------
    await P.evaluate(() => go('painel'));
    const hj = await P.evaluate(() => fetch('/api/painel').then(r => r.text()));
    chk(hj.includes('"2 contas fixas atrasadas"') && hj.includes('Encargos (INSS, FGTS, férias, 13º), Salários') && !hj.includes('Ana Souza') && hj.includes('financeiro/contas-fixas'),
      '[G] Home do admin: "2 contas fixas atrasadas" pela categoria, sem o nome da pessoa, levando às contas fixas');
    const it = P.locator('#v-painel :text("2 contas fixas atrasadas")').first();
    await P.waitForTimeout(1500);
    if (await it.count()) { await it.scrollIntoViewIfNeeded(); chk(!(await P.evaluate(() => document.getElementById('v-painel').innerText)).includes('Ana Souza'), '[G] a Home mostra o alerta sem o nome'); }
    if (await it.count()) await foto(P, '5-home-alerta');
    await ctx.close();
    // ---------- [H] celular ----------
    const { ctx: cm, page: M } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w: 390, h: 844 });
    await M.evaluate(() => go('financeiro/contas-fixas')); await M.waitForFunction(() => FIN.cf && document.getElementById('fin-cf-grade'), null, { timeout: 15000 });
    chk(await M.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && getComputedStyle(document.querySelector('.fin-cf-wrap')).overflowX === 'auto'), '[H] celular: sem rolagem lateral da página; a grade rola dentro do cartão');
    await foto(M, '6-celular-contas-fixas');
    await cm.close();
    // ---------- [I] operador ----------
    const { ctx: c2, page: O } = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    chk((await O.evaluate(() => fetch('/api/financeiro/contas-fixas').then(r => r.status))) === 403, '[I] operador: API das contas fixas 403');
    await O.evaluate(() => go('painel')); await O.waitForTimeout(1500);
    chk(!(await O.evaluate(() => document.body.innerText)).includes('Ana Souza') && !(await O.evaluate(() => document.body.innerText)).includes('contas fixas atrasadas'), '[I] operador: a Home sem o alerta e sem nomes');
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
