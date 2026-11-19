// CAMP-COB (19/11/2026): tela Cobranças avulsas no navegador de verdade (Playwright + Chromium), com um SITE FALSO (nenhuma chamada real
// ao site nem ao Mercado Pago). Rafael: "Quero poder no admin criar uma cobrança de alguém que vai doar acervo, ex. 2 mil reais, criar a
// cobrança para pagar com o Mercado Pago, e quero poder saber no extrato o que era."
//  [A] admin/master vê o item no menu (tecla R); operador não vê o item e a tecla não abre
//  [B] Nova cobrança: prévia do que aparece no Mercado Pago (título e fatura do cartão), cria e mostra o link, Copiar link/WhatsApp
//  [C] "No extrato do Mercado Pago": referência CAMP-COB-n, fatura do cartão e (depois de paga) o id do pagamento
//  [D] Enviar por e-mail sem o template TR27 no site: "não enviado" com o template que falta; nada de wp-admin na tela
//  [E] Cancelar pede confirmação e a situação vira Cancelada; a lista e o CSV (link) seguem os filtros
//  [F] celular (390 px): sem rolagem lateral
// Uso (servidor PRÓPRIO na porta 8792; o site falso sobe aqui na 8793):
//   CAMP_DB_PATH=/dev/shm/cob/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/cob/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8792)
//   CAMP_DB_PATH=/dev/shm/cob/m.db CAMP_BASE=http://127.0.0.1:8792 CHROME=/opt/pw-browsers/chromium node tests/navegador_cobranca_avulsa.js
const http = require('http');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8792', DB = process.env.CAMP_DB_PATH, PORTA_SITE = +(process.env.SITE_PORTA || 8793);
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {        // aceita a pasta (/opt/pw-browsers/chromium) ou o executável
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------------- site falso (contrato 1.19) ----------------
const ROTA = '/wp-json/camp/v1/painel/cobrancas';
const site = { regs: {}, emails: 0, prox: 801, pedidos: [] };
function reg(id, c) {
  const curta = String(c.descricao || '').split('\n')[0];
  const fins = { doacao_acervo: ['Doação de acervo — tratamento/digitalização', 'CAMP DOACAO ACERVO'], doacao: ['Doação', 'CAMP DOACAO'], patrocinio: ['Patrocínio', 'CAMP PATROCINIO'], servico: ['Serviço', 'CAMP SERVICO'], outro: ['Outro', 'CAMP'] };
  const f = fins[c.finalidade] || fins.outro;
  return { id, ref_painel: c.ref_painel, external_reference: 'CAMP-COB-' + id, protocolo: 'CAMP-COB-' + id, nome: c.nome, email: c.email, telefone: c.telefone || '', valor: +c.valor,
    finalidade: c.finalidade, finalidade_nome: f[0], descricao: c.descricao, vence: c.vence || '', vinculo: c.vinculo || '', situacao: 'aberta',
    link: 'https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=pref-' + id, preferencia_id: 'pref-' + id, modo: 'producao', teste: false,
    mp: { titulo: ('CAMP · ' + f[0] + ' · ' + curta).slice(0, 256), statement_descriptor: f[1], external_reference: 'CAMP-COB-' + id },
    pagamento: null, pagamentos: [], historico: ['2026-11-19 20:00 UTC · criada pelo painel'], criado_em: new Date().toISOString(), cancelada_em: '', alterado_em: new Date().toISOString() };
}
const servidor = http.createServer((req, res) => {
  let corpo = '';
  req.on('data', d => { corpo += d; });
  req.on('end', () => {
    const u = new URL(req.url, 'http://x'), j = (code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
    let b = {}; try { b = corpo ? JSON.parse(corpo) : {}; } catch (_) { b = {}; }
    site.pedidos.push(req.method + ' ' + u.pathname);
    if (u.pathname === ROTA && req.method === 'POST') {
      const ja = Object.values(site.regs).find(r => r.ref_painel === b.ref_painel);
      if (ja) return j(200, { ok: true, criado: false, id: ja.id, link: ja.link, external_reference: ja.external_reference, registro: ja });
      const id = site.prox++; site.regs[id] = reg(id, b);
      return j(200, { ok: true, criado: true, id, link: site.regs[id].link, external_reference: 'CAMP-COB-' + id, registro: site.regs[id] });
    }
    if (u.pathname === ROTA && req.method === 'GET') return j(200, { itens: Object.values(site.regs), mp_ativo: true, modo: 'producao', agora: new Date().toISOString() });
    let m = u.pathname.match(/^\/wp-json\/camp\/v1\/painel\/cobrancas\/(\d+)(\/email)?$/);
    if (m && req.method === 'POST' && site.regs[m[1]]) {
      const r = site.regs[m[1]];
      if (m[2]) { site.emails++; return j(409, { code: 'camp_sender_sem_template', message: 'Falta o template TR27 (Cobrança avulsa) do Sender no site: cole o ID em wp-admin → Apoios → Mercado Pago. Nada foi enviado.', data: { status: 409, template: 'TR27' } }); }
      if (b.acao === 'cancelar') { r.situacao = 'cancelada'; r.cancelada_em = new Date().toISOString(); r.historico.push('cancelada pelo painel'); return j(200, { ok: true, acao: 'cancelar', mp_expirou: true, registro: r }); }
      if (b.acao === 'consultar') return j(200, { ok: true, acao: 'consultar', registro: r });
      return j(200, { ok: true, acao: b.acao, registro: r });
    }
    j(404, { code: 'rest_no_route', message: 'Nenhuma rota' });
  });
});

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, deviceScaleFactor: 1 });
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await ctx.newPage();
  // 409 do e-mail sem template é esperado (a tela mostra a mensagem); /api/auth/eu antes do login também
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/api\/cobrancas\/\d+\/email$|\/api\/cobrancas$/.test(url) && !/status of 409/.test(m.text())) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}

(async () => {
  await new Promise(r => servidor.listen(PORTA_SITE, '127.0.0.1', r));
  py(`for k,v in (('wp.url','http://127.0.0.1:${PORTA_SITE}'),('wp.usuario','painel'),('wp.app_password','xxxx yyyy')):\n    con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES (?,?,?,0) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(k,v,k))\ncon.execute("INSERT OR IGNORE INTO fundo (codigo, titulo) VALUES ('F014','Fundo do Teste de Cobrança')")`);
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    // ---------------- [A] menu e tecla ----------------
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const item = P.locator('#nav button[data-v="cobrancas"]');
    chk(await item.isVisible() && (await item.textContent()).includes('Cobranças avulsas') && (await item.locator('kbd').textContent()) === 'R', '[A] master vê "Cobranças avulsas" no menu, com a tecla R');
    await P.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await P.keyboard.press('r');
    await P.waitForFunction(() => document.getElementById('v-cobrancas')?.classList.contains('on') && !/Carregando/.test(document.getElementById('cob-lista').textContent), null, { timeout: 10000 });
    chk(true, '[A] a tecla R abre a tela');
    chk(/Nenhuma cobrança avulsa/.test(await P.locator('#cob-lista').textContent()), '[A] lista vazia explica o que fazer');

    // ---------------- [B] nova cobrança ----------------
    await P.click('#cob-nova');
    await P.waitForSelector('#cob-n-nome');
    await P.fill('#cob-n-nome', 'Maria Doadora Silva');
    await P.fill('#cob-n-email', 'maria@exemplo.com');
    await P.fill('#cob-n-tel', '(11) 99999-0000');
    await P.fill('#cob-n-valor', '2000');
    await P.selectOption('#cob-n-fin', 'doacao_acervo');
    await P.fill('#cob-n-desc', 'Tratamento do acervo de Fulano – 1ª parcela');
    await P.fill('#cob-n-vinc', 'F014 · Fundo do Teste de Cobrança');
    const previa = await P.locator('#cob-n-previa').textContent();
    chk(previa.includes('CAMP · Doação de acervo — tratamento/digitalização · Tratamento do acervo de Fulano – 1ª parcela') && previa.includes('CAMP DOACAO ACERVO'), '[B] prévia mostra o título e a fatura do cartão como no Mercado Pago');
    await P.click('[data-cob-acao="criar"]');
    await P.waitForSelector('#cob-link', { timeout: 15000 });
    chk((await P.inputValue('#cob-link')).startsWith('https://www.mercadopago.com.br/'), '[B] criou e mostra o link do Mercado Pago');
    const ped = site.pedidos.filter(x => x === 'POST ' + ROTA).length;
    chk(ped === 1, '[B] pediu ao site uma vez (POST /painel/cobrancas)');
    await P.click('[data-cob-acao="copiar-link"]');
    const cop = await P.evaluate(() => navigator.clipboard.readText().catch(() => ''));
    chk(cop.startsWith('https://www.mercadopago.com.br/'), '[B] Copiar link copia o link');
    await P.click('[data-cob-acao="copiar-texto"]');
    const txt = await P.evaluate(() => navigator.clipboard.readText().catch(() => ''));
    chk(/R\$ 2\.000,00/.test(txt) && txt.includes('mercadopago.com.br') && txt.includes('CAMP-COB-801'), '[B] texto para WhatsApp com valor, link e referência');
    const wa = await P.locator('#drawer a[href^="https://wa.me/"]').getAttribute('href');
    chk(wa && wa.startsWith('https://wa.me/5511999990000?text='), '[B] Abrir no WhatsApp leva o telefone e o texto');

    // ---------------- [C] extrato ----------------
    const det = await P.locator('#drawer .cob-det').textContent();
    chk(det.includes('No extrato do Mercado Pago') && det.includes('CAMP-COB-801') && det.includes('CAMP DOACAO ACERVO') && det.includes('Título do item'), '[C] detalhe mostra referência, fatura do cartão e título do item');

    // ---------------- [D] e-mail sem template ----------------
    await P.click('[data-cob-acao="email"]');
    await P.waitForFunction(() => /não enviado/.test(document.body.innerText), null, { timeout: 10000 });
    const corpo = await P.evaluate(() => document.body.innerText);
    chk(/não enviado: falta o template TR27 \(Cobrança avulsa\)/.test(corpo) && !/wp-admin/.test(corpo), '[D] sem o template TR27: "não enviado" com o template que falta, sem wp-admin');
    chk(site.emails === 1, '[D] pediu ao site pela rota /email (Sender)');

    // ---------------- [E] cancelar, lista e CSV ----------------
    await P.waitForSelector('[data-cob-acao="cancelar"]');
    await P.click('[data-cob-acao="cancelar"]');
    await P.waitForSelector('#conf-ov [data-conf="sim"]');
    chk((await P.locator('#conf-ov').textContent()).includes('CAMP-COB-801'), '[E] a confirmação diz qual cobrança');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => /Cancelada/.test(document.querySelector('#drawer .cob-det')?.textContent || ''), null, { timeout: 10000 });
    chk(!(await P.locator('#cob-link').count()), '[E] cancelada: some o link');
    await P.waitForFunction(() => /Cancelada/.test(document.getElementById('cob-lista').textContent), null, { timeout: 10000 });
    chk((await P.locator('#cob-lista tr[data-cob-abrir]').count()) === 1, '[E] a lista mostra a cobrança');
    await P.selectOption('#cob-sit', 'paga');
    await P.waitForFunction(() => /Nenhuma cobrança/.test(document.getElementById('cob-lista').textContent), null, { timeout: 10000 });
    chk((await P.getAttribute('#cob-csv', 'href')).includes('situacao=paga'), '[E] filtro de situação vale na lista e no CSV');
    const csv = await P.evaluate(() => fetch('/api/cobrancas/exportar.csv').then(r => r.text()));
    chk(csv.includes('external_reference') && csv.includes('statement_descriptor') && csv.includes('CAMP-COB-801'), '[E] CSV com as colunas do extrato');

    // ---------------- [F] celular ----------------
    await P.setViewportSize({ width: 390, height: 800 });
    await P.selectOption('#cob-sit', '');
    await P.waitForTimeout(600);
    const lat = await P.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    chk(lat <= 1, `[F] celular sem rolagem lateral (${lat}px)`);
    await ctx.close();

    // ---------------- [A] operador ----------------
    const { ctx: c2, page: O } = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    chk(!(await O.locator('#nav button[data-v="cobrancas"]').isVisible()), '[A] operador não vê o item no menu');
    await O.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await O.keyboard.press('r');
    await O.waitForTimeout(500);
    chk(!(await O.evaluate(() => document.getElementById('v-cobrancas')?.classList.contains('on'))), '[A] operador: a tecla R não abre');
    chk((await O.evaluate(() => fetch('/api/cobrancas').then(r => r.status))) === 403, '[A] operador: API 403');
    await c2.close();
    chk(!erros.length, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    chk(false, 'exceção: ' + (e && e.stack || e));
  } finally {
    await browser.close();
    servidor.close();
  }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
