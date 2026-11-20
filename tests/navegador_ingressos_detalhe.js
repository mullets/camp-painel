// CAMP-INGRESSOS detalhe (20/11/2026): tela Ingressos no navegador de verdade (Playwright + Chromium), com um SITE FALSO (nenhuma chamada
// real ao site, ao Sender nem ao Mercado Pago). Rafael: "Na parte de ingressos, pedidos: saber quem pagou meia, quem é Amigo etc. E abrir a
// data para listar as pessoas, e se precisar reenviar o ingresso ou a cobrança."
//  [A] tecla Z abre Ingressos; "Sincronizar agora" busca no site falso
//  [B] Por mês: tipos de cada compra (meias, Amigo com desconto) e o selo "Amigo" de quem está no cadastro de Amigos
//  [C] Por data: o dia com as turmas e as contas; abrir a turma mostra a lista de presença; filtros tipo/Amigo e busca
//  [D] Reenviar ingresso sem o template TR23 no site: "não enviado" com o template que falta, sem wp-admin
//  [E] Reenviar cobrança: link novo do Mercado Pago; fica no Histórico do pedido
//  [F] seleção em lote + Reenviar ingresso pede confirmação e diz quantos foram e quantos não
//  [G] CSV da lista segue os filtros; Imprimir usa a versão de impressão
//  [H] celular (390 px) sem rolagem lateral; [I] operador não vê nem chama a API
//  [M] abas acessíveis (clique, setas, aria-selected, alvo ≥ 40 px), turma clicável abre a lista e NADA cobre as linhas da lista
//      (elementFromPoint no meio de cada linha devolve a própria linha; Rafael 20/11: "não dá para clicar"); ações no menu ⋯
//  [P] um ingresso por pessoa (contrato 1.24, 20/11/2026: "Nome e e-mail para enviar o ingresso dessa pessoa. E envia todos os ingressos
//      separados para quem comprou também"): a lista tem uma linha por pessoa (compra antiga = "comprador + N"), motivo da meia,
//      "Reenviar ingresso (a esta pessoa)", "Reenviar ao comprador" e "Reenviar todos ao comprador"
// Uso (servidor PRÓPRIO na porta 8796; o site falso sobe aqui na 8797):
//   CAMP_DB_PATH=/dev/shm/ig/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/ig/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8796)
//   CAMP_DB_PATH=/dev/shm/ig/m.db CAMP_BASE=http://127.0.0.1:8796 CHROME=/opt/pw-browsers/chromium node tests/navegador_ingressos_detalhe.js
const http = require('http');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8796', DB = process.env.CAMP_DB_PATH, PORTA_SITE = +(process.env.SITE_PORTA || 8797);
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------------- site falso (contratos 1.18/1.21/1.22) ----------------
const ROTA = '/wp-json/camp/v1/painel/ingressos';
const sp = new Date(Date.now() + 3 * 864e5).toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });   // AAAA-MM-DD daqui a 3 dias
const agora = new Date().toISOString();
const base = { casa: 'JM', visita: 'Visita guiada à Residência João Marino', data: sp, hora: '10:00', telefone: '11 98888-0000', entraram: 0, preco: 120, pagamentos: [], modo: 'producao',
  criado_em: agora, confirmado_em: agora, alterado_em: agora, amigo_id: 0, desconto: null, meias: 0, link_pagamento: '', link_pagamento_ate: '', historico: ['compra criada'] };
const site = {
  itens: {
    701: { ...base, id: 701, ref: 'CAMP-INGRESSO-JM-701', nome: 'Ana Meia', email: 'ana@exemplo.com', pessoas: 3, meias: 2, total: 240, situacao: 'pago', codigo: 'AAAA0701',
      tipos: [{ tipo: 'inteira', nome: 'Inteira', qtd: 1, valor: 120 }, { tipo: 'meia', nome: 'Meia-entrada', qtd: 2, valor: 60 }],
      ingressos: [{ n: 1, nome: 'Ana Meia', email: 'ana@exemplo.com', tipo: 'inteira', motivo: '', codigo: 'A1A10001', link: '', entrou: false, eh_comprador: true, envios: [] },   // contrato 1.24
        { n: 2, nome: 'Bia Professora', email: 'bia@exemplo.com', tipo: 'meia', motivo: 'professor', codigo: 'B2B20002', link: '', entrou: true, eh_comprador: false, envios: [] },
        { n: 3, nome: 'Caio Estudante', email: '', tipo: 'meia', motivo: 'estudante', codigo: 'C3C30003', link: '', entrou: false, eh_comprador: false, envios: [] }] },
    702: { ...base, id: 702, ref: 'CAMP-INGRESSO-JM-702', nome: 'Bruno Amigo', email: 'bruno@exemplo.com', pessoas: 2, total: 216, situacao: 'pago', codigo: 'BBBB0702', amigo_id: 9,
      desconto: { categoria: 'amigo', pct: 20, qtd: 1, valor: 96, via: 'codigo' } },
    703: { ...base, id: 703, ref: 'CAMP-INGRESSO-JM-703', nome: 'Clara Pendente', email: 'clara@exemplo.com', pessoas: 1, total: 120, situacao: 'reservado', codigo: 'CCCC0703',
      link_pagamento: 'https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=703', link_pagamento_ate: agora,
      aviso_equipe: [{ quando: agora, momento: 'pedido', para: 'equipe@camp.arq.br', ok: true, erro: '' }] },
    704: { ...base, id: 704, hora: '13:00', ref: 'CAMP-INGRESSO-JM-704', nome: 'Diego Cadastro', email: 'diego@exemplo.com', pessoas: 1, total: 120, situacao: 'pago', codigo: 'DDDD0704' },
  },
  pedidos: [],
};
const servidor = http.createServer((req, res) => {
  let corpo = '';
  req.on('data', d => { corpo += d; });
  req.on('end', () => {
    const u = new URL(req.url, 'http://x'), j = (code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
    let b = {}; try { b = corpo ? JSON.parse(corpo) : {}; } catch (_) { b = {}; }
    site.pedidos.push(req.method + ' ' + u.pathname + ' ' + JSON.stringify(b));
    if (u.pathname === ROTA && req.method === 'GET') {
      return j(200, { itens: Object.values(site.itens), turmas: ['10:00', '13:00', '15:00'].map(h => ({ chave: `${sp}|${h}`, data: sp, hora: h, vagas: 15, ocupadas: 0, livres: h === '10:00' ? 9 : 14 })),
        config: { preco: 120, vagas: 15, email_ingressos: '', email_ingressos_destino: 'equipe@camp.arq.br', aviso_recusado: false, aviso_teste: null }, agora: new Date().toISOString() });
    }
    if (u.pathname === ROTA + '/aviso-teste' && req.method === 'POST') return j(200, { ok: false, para: 'equipe@camp.arq.br', erro: 'Could not instantiate mail function.', em: new Date().toISOString() });
    const m = u.pathname.match(/^\/wp-json\/camp\/v1\/painel\/ingressos\/(\d+)\/(reenviar|cobranca)$/);
    if (m && req.method === 'POST' && site.itens[m[1]]) {
      const r = site.itens[m[1]];
      if (m[2] === 'reenviar' && b.pessoa) return j(200, { ok: true, enviado: true, enviados: 1, destino: b.para, template: 'TR23', sender: { id: 'em-p' }, registro: r });
      if (m[2] === 'reenviar') return j(409, { code: 'camp_sender_sem_template', message: 'Falta o template TR23 (Ingresso da visita) do Sender no site. Nada foi enviado.', data: { status: 409, template: 'TR23' } });
      if (r.situacao === 'pago') return j(409, { code: 'camp_ing_pago', message: 'já paga', data: { status: 409 } });
      r.link_pagamento = 'https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=703-novo'; r.historico = [...r.historico, 'novo link de pagamento pedido pelo painel'];
      return j(200, { ok: true, enviado: true, novo_link: true, template: 'TR29', modelo: 'ingresso_cobranca', sender: { id: 'em-9', status: 'enviado' }, registro: r });
    }
    j(404, { code: 'rest_no_route', message: 'Nenhuma rota' });
  });
});

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  // 409 do reenvio sem template é esperado (a tela mostra a mensagem); /api/auth/eu antes do login também
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/api\/ingressos\/\d+\/(reenviar|cobranca)$|\/api\/ingressos/.test(url) && !/status of 40[39]/.test(m.text())) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}

(async () => {
  await new Promise(r => servidor.listen(PORTA_SITE, '127.0.0.1', r));
  py(`for k,v in (('wp.url','http://127.0.0.1:${PORTA_SITE}'),('wp.usuario','painel'),('wp.app_password','xxxx yyyy'),('ingressos.coleta_min','0')):\n    con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES (?,?,?,0) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(k,v,k))\ncon.execute("INSERT INTO amigo (tipo, nome, email, categoria, situacao, validade) VALUES ('amigo','Diego','diego@exemplo.com','guardiao','pago',date('now','+60 days'))")\ncon.execute("INSERT INTO amigo (tipo, nome, email, categoria, situacao, validade) VALUES ('amigo','Bruno','bruno@exemplo.com','amigo','pendente',NULL)")`);
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    // ---------------- [A] ----------------
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await P.locator('body').click({ position: { x: 5, y: 5 } }).catch(() => {});
    await P.keyboard.press('z');
    await P.waitForFunction(() => document.getElementById('v-ingressos')?.classList.contains('on'), null, { timeout: 10000 });
    await P.click('#ig-sinc');
    const temPessoas = () => P.waitForFunction(() => [...document.querySelectorAll('#ig-turmas tr[data-ig-abrir]')].some(r => /\b3\/15\b|\b5\/15\b/.test(r.textContent)), null, { timeout: 15000 });
    await temPessoas().catch(async () => {
      // o mês pode ser outro (a data fica 3 dias à frente): escolhe o mês da visita
      await P.selectOption('#ig-mes', sp.slice(0, 7)); await temPessoas();
    });
    const menu = async (linha) => { await linha.locator('.ig-menu > summary').first().click(); };
    chk(true, '[A] tecla Z abre Ingressos e "Sincronizar agora" traz as compras do site');

    // ---------------- [A2] avisos à equipe (sem Sender) ----------------
    chk((await P.locator('#ig-avisos-res').textContent()).includes('equipe@camp.arq.br'), '[A2] a faixa "Avisos à equipe" diz para quem vão (fechada)');
    await P.click('.ig-avisos-box > summary');
    chk((await P.locator('#ig-avisos').textContent()).includes('equipe@camp.arq.br') && /contato@camp\.arq\.br/.test(await P.locator('#ig-avisos').textContent()), '[A2] aberta: quem recebe e o padrão (e-mail de solicitações do site, senão contato@camp.arq.br)');
    await P.click('#ig-av-teste');
    await P.waitForFunction(() => /não saiu/.test(document.getElementById('ig-av-res')?.textContent || ''), null, { timeout: 10000 });
    chk(/mail function/.test(await P.locator('#ig-av-res').textContent()), '[A2] Mandar aviso de teste mostra que o e-mail do site falhou e o motivo');

    // ---------------- [B] ----------------
    const s10 = P.locator('#ig-turmas tr[data-ig-abrir$="|10:00"]');
    chk(/5\/15/.test(await s10.textContent()) && /2 inteiras · 2 meias-entradas · 1 Amigo com desconto/.test(await s10.textContent()) && (await s10.locator('.tag.a').count()) === 1, '[B] por mês: a turma 10h com ocupação 5/15, tipos e quem aguarda pagamento');
    chk((await P.locator('#ig-turmas tr.ig-vazia').count()) === 1, '[B] turma sem ninguém fica mais apagada');
    chk((await P.locator('#ig-kpis .ig-kpi').count()) === 5 && (await P.locator('#ig-kpis').textContent()).includes('2 meias-entradas') && /Pix|pago pelos visitantes/.test(await P.locator('#ig-kpis').textContent()), '[B] resumo do mês: 5 números numa linha (por tipo em etiquetas)');
    chk(new Set(await P.$$eval('#ig-kpis .ig-kpi', l => l.map(e => Math.round(e.getBoundingClientRect().top)))).size === 1, '[B] os 5 números ficam na mesma linha (1366 px)');
    // ---------------- [M] ----------------
    const abas = await P.$$eval('#ig-abas [role="tab"]', l => l.map(b => [b.getAttribute('aria-selected'), Math.round(b.getBoundingClientRect().height), b.getAttribute('aria-controls')]));
    chk(abas.length === 2 && abas.every(a => a[1] >= 40) && abas[0][0] === 'true' && abas[0][2] === 'ig-aba-mes', '[M] abas com aria-selected, aria-controls e alvo ≥ 40 px (' + JSON.stringify(abas) + ')');
    await P.focus('#ig-tab-mes'); await P.keyboard.press('ArrowRight');
    chk(await P.evaluate(() => !document.getElementById('ig-aba-datas').hidden && document.getElementById('ig-aba-mes').hidden && document.activeElement.id === 'ig-tab-datas' && document.getElementById('ig-tab-datas').getAttribute('aria-selected') === 'true'), '[M] seta para a direita troca de aba (e o foco vai junto)');
    await P.keyboard.press('Home');
    chk(await P.evaluate(() => !document.getElementById('ig-aba-mes').hidden && document.getElementById('ig-tab-mes').tabIndex === 0 && document.getElementById('ig-tab-datas').tabIndex === -1), '[M] Home volta para "Por mês"');
    await P.click('#ig-tab-datas'); await P.waitForSelector('#ig-datas .ig-turma-btn');
    chk(await P.evaluate(() => !document.getElementById('ig-aba-datas').hidden), '[M] clique na aba "Por data" mostra as datas');
    await P.click('#ig-tab-mes');
    chk(await P.evaluate(() => !document.getElementById('ig-aba-mes').hidden), '[M] clique na aba "Por mês" volta');
    await s10.click();
    await P.waitForFunction(() => /— 5 pessoas/.test(document.querySelector('#ig-lista h2')?.textContent || ''), null, { timeout: 10000 });
    chk(true, '[M] clicar na linha da turma abre a lista de presença ("… · 10:00 — 5 pessoas")');
    const cobre = async () => P.$$eval('#ig-lista tbody tr', l => l.map(tr => { tr.scrollIntoView({ block: 'center' }); const b = tr.getBoundingClientRect(); const out = []; for (const fx of [0.1, 0.5, 0.9]) { const h = document.elementFromPoint(b.left + b.width * fx, b.top + b.height / 2); if (!h || !tr.contains(h)) out.push((tr.textContent || '').trim().slice(0, 20) + ' coberto por ' + (h ? h.tagName + '.' + h.className : 'nada')); } return out.join('; '); }).filter(Boolean));
    let cob = await cobre();
    chk(!cob.length, '[M] nada cobre as linhas da lista de presença (1366)' + (cob.length ? ': ' + cob.join(' | ') : ''));
    const linhaDiego0 = P.locator('#ig-lista tr', { hasText: 'Bruno Amigo' });
    chk((await linhaDiego0.textContent()).includes('Amigo · pagamento pendente'), '[M] Amigo com pagamento pendente aparece assim (não "Amigo (pendente)")');
    const ana = P.locator('#ig-lista tr[data-ig-linha="701-1"]');
    await menu(ana);
    chk(await ana.locator('.ig-menu-l [data-ig-reenviar]').isVisible() && await ana.locator('.ig-menu-l [data-ig-detalhe]').isVisible(), '[M] ações no menu ⋯ (abre ao clicar)');
    await P.locator('#ig-lista h2').click();
    chk(!(await ana.locator('.ig-menu-l [data-ig-reenviar]').isVisible()), '[M] clicar fora fecha o menu ⋯');
    if (process.env.PRINTS) await P.screenshot({ path: process.env.PRINTS + '/ing-ui-depois-1366.png' });
    await P.click('#ig-l-fechar');
    // turma das 13h (Diego, Amigo do cadastro)
    await P.click('#ig-turmas tr[data-ig-abrir$="|13:00"]');
    await P.waitForFunction(() => /Diego Cadastro/.test(document.getElementById('ig-lista').textContent), null, { timeout: 10000 });
    const linhaDiego = P.locator('#ig-lista tr', { hasText: 'Diego Cadastro' });
    chk((await linhaDiego.locator('.tag.g', { hasText: 'Amigo' }).count()) === 1 && (await linhaDiego.textContent()).includes('Guardião'), '[B] selo "Amigo" (Guardião) de quem está no cadastro de Amigos, mesmo sem desconto');
    await P.click('#ig-l-fechar');

    // ---------------- [C] ----------------
    await P.click('#ig-abas [data-ig-aba="datas"]');
    await P.waitForFunction(() => document.querySelector('#ig-datas .ig-turma-btn'), null, { timeout: 10000 });
    const dia = await P.locator('#ig-datas .ig-dia').first().textContent();
    chk(/6 pessoas/.test(dia) && /aguardando pagamento/.test(dia), '[C] por data: o dia com pessoas, tipos e quem aguarda pagamento');
    const t10 = P.locator('#ig-datas .ig-turma-btn', { hasText: '10:00' });
    chk(/pagos 5 · gratuitos 0 · pendentes 1/.test(await t10.textContent()) && /9 de 15 vagas livres/.test(await t10.textContent()), '[C] turma 10h: pagos, pendentes e vagas livres');
    await t10.click();
    await P.waitForFunction(() => /Lista de presença/.test(document.getElementById('ig-lista').textContent) && document.querySelectorAll('#ig-lista tbody tr').length === 5, null, { timeout: 10000 });
    chk(true, '[C] abrir a turma mostra a lista de presença (uma linha por pessoa: 3 da Ana + 2 compras antigas)');
    await P.selectOption('#ig-l-tipo', 'meia');
    await P.waitForFunction(() => document.querySelectorAll('#ig-lista tbody tr').length === 2 && /Bia Professora/.test(document.querySelector('#ig-lista tbody').textContent) && /comprou: Ana Meia/.test(document.querySelector('#ig-lista tbody').textContent), null, { timeout: 10000 });
    chk(true, '[C] filtro por tipo (meia-entrada) deixa só as pessoas com meia');
    await P.selectOption('#ig-l-tipo', '');
    await P.waitForFunction(() => document.querySelectorAll('#ig-lista tbody tr').length === 5, null, { timeout: 10000 });
    await P.fill('#ig-l-q', 'CCCC0703');
    await P.waitForFunction(() => document.querySelectorAll('#ig-lista tbody tr').length === 1 && /Clara Pendente/.test(document.querySelector('#ig-lista tbody').textContent), null, { timeout: 10000 });
    chk(true, '[C] busca pelo código do ingresso');
    await P.fill('#ig-l-q', '');
    await P.waitForFunction(() => document.querySelectorAll('#ig-lista tbody tr').length === 5, null, { timeout: 10000 });

    // ---------------- [D] ----------------
    await menu(P.locator('#ig-lista tr[data-ig-linha="701-1"]')); await P.locator('#ig-lista tr[data-ig-linha="701-1"] [data-ig-reenviar]').click();
    await P.waitForFunction(() => /não enviado/.test(document.getElementById('ig-l-msg')?.textContent || ''), null, { timeout: 10000 });
    const msg = await P.locator('#ig-l-msg').textContent();
    chk(/falta o template TR23 \(Ingresso da visita\)/.test(msg) && !/wp-admin/.test(await P.evaluate(() => document.body.innerText)), '[D] sem o template TR23: "não enviado" com o template que falta, sem wp-admin');
    chk(site.pedidos.some(x => x.startsWith('POST ' + ROTA + '/701/reenviar {"so_sender":true}')), '[D] pediu ao site o reenvio só pelo Sender');

    // ---------------- [P] um ingresso por pessoa ----------------
    const bia = P.locator('#ig-lista tr', { hasText: 'Bia Professora' }), caio = P.locator('#ig-lista tr', { hasText: 'Caio Estudante' });
    chk(/Professor\(a\)/.test(await bia.textContent()) && /bia@exemplo\.com/.test(await bia.textContent()) && /B2B20002/.test(await bia.textContent()) && /sim/.test(await bia.locator('td.ig-num').textContent()),
      '[P] linha da pessoa: nome, e-mail, motivo da meia, código do ingresso e entrada');
    chk(/sem e-mail: só o comprador recebe/.test(await caio.textContent()) && (await caio.locator('[data-para="pessoa"]').count()) === 0 && (await caio.locator('[data-para="comprador"]').count()) === 1,
      '[P] pessoa sem e-mail: só "Reenviar ao comprador"');
    chk((await P.locator('#ig-lista tr', { hasText: 'Bruno Amigo' }).textContent()).includes('+ 1'), '[P] compra antiga: uma linha "comprador + N"');
    await menu(bia); await bia.locator('[data-para="pessoa"]').click();
    await P.waitForFunction(() => /Ingresso 2 reenviado à pessoa/.test(document.getElementById('ig-l-msg')?.textContent || ''), null, { timeout: 10000 });
    chk(site.pedidos.some(x => x === 'POST ' + ROTA + '/701/reenviar {"so_sender":true,"pessoa":2,"para":"pessoa"}'), '[P] Reenviar ingresso (a esta pessoa) pede ao site só o ingresso 2, à pessoa');
    await menu(P.locator('#ig-lista tr', { hasText: 'Caio Estudante' })); await P.locator('#ig-lista tr', { hasText: 'Caio Estudante' }).locator('[data-para="comprador"]').click();
    await P.waitForFunction(() => /Ingresso 3 reenviado ao comprador/.test(document.getElementById('ig-l-msg')?.textContent || ''), null, { timeout: 10000 });
    chk(site.pedidos.some(x => x === 'POST ' + ROTA + '/701/reenviar {"so_sender":true,"pessoa":3,"para":"comprador"}'), '[P] Reenviar ao comprador (o ingresso de quem não deixou e-mail)');
    chk((await P.locator('#ig-lista [data-ig-reenviar="701"]').textContent()).includes('Reenviar todos ao comprador'), '[P] por pedido: "Reenviar todos ao comprador"');

    // ---------------- [E] ----------------
    await menu(P.locator('#ig-lista tr', { hasText: 'Clara Pendente' })); await P.locator('#ig-lista tr', { hasText: 'Clara Pendente' }).locator('[data-ig-cobrar]').click();
    await P.waitForFunction(() => /link novo/.test(document.getElementById('ig-l-msg')?.textContent || ''), null, { timeout: 10000 });
    chk(site.pedidos.some(x => x.startsWith('POST ' + ROTA + '/703/cobranca')), '[E] Reenviar cobrança chamou o site e avisa do link novo do Mercado Pago');
    await menu(P.locator('#ig-lista tr', { hasText: 'Clara Pendente' })); await P.locator('#ig-lista tr', { hasText: 'Clara Pendente' }).locator('[data-ig-detalhe]').click();
    await P.waitForFunction(() => /cobrança reenviada/.test(document.getElementById('d-body')?.textContent || ''), null, { timeout: 10000 });
    chk((await P.locator('#d-body').textContent()).includes('novo link de pagamento pedido pelo painel'), '[E] Histórico: o que o painel fez e o histórico do site');
    chk(/Aviso à equipe \(pedido novo\): enviado/.test(await P.locator('#d-body').textContent()), '[E] detalhe: aviso à equipe enviado (quando e para quem)');
    await P.evaluate(() => closeDrawer(true));

    // ---------------- [F] ----------------
    await P.check('#ig-lista tr:has-text("Ana Meia") [data-ig-sel]');
    await P.check('#ig-lista tr:has-text("Bruno Amigo") [data-ig-sel]');
    chk(await P.locator('#ig-l-bulk.on').isVisible() && /2 selecionadas/.test(await P.locator('#ig-l-bulk').textContent()), '[F] a barra de seleção mostra 2 selecionadas');
    await P.click('#ig-l-bulk [data-ig-lote="ingresso"]');
    await P.waitForSelector('#conf-ov [data-conf="sim"]');
    chk(/2 compras/.test(await P.locator('#conf-ov').textContent()), '[F] confirmação diz quantas compras');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => /0 enviados · 2 não enviados/.test(document.getElementById('ig-l-msg')?.textContent || ''), null, { timeout: 10000 });
    chk(true, '[F] lote: diz quantos foram e quantos não (com o motivo)');

    // ---------------- [G] ----------------
    await P.selectOption('#ig-l-sit', 'valem');
    await P.waitForFunction(() => document.querySelectorAll('#ig-lista tbody tr').length === 4, null, { timeout: 10000 });
    const href = await P.getAttribute('#ig-l-csv', 'href');
    chk(href.includes('situacao=valem') && href.includes('turma=' + encodeURIComponent(sp + '|10:00')), '[G] CSV da lista segue a turma e os filtros');
    const csv = await P.evaluate(h => fetch(h).then(r => r.text()), href);
    chk(csv.includes('Presença') && csv.includes('Ana Meia') && !csv.includes('Clara Pendente'), '[G] CSV: lista de presença com a coluna Presença');
    await P.evaluate(() => { window.__imprimiu = 0; window.print = () => { window.__imprimiu = document.body.classList.contains('imprime-ig') ? 1 : -1; }; });
    await P.click('#ig-l-imprimir');
    chk((await P.evaluate(() => window.__imprimiu)) === 1, '[G] Imprimir usa a versão de impressão da lista');

    // ---------------- [H] ----------------
    await P.setViewportSize({ width: 390, height: 800 });
    await P.waitForTimeout(500);
    const lat = await P.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    chk(lat <= 1, `[H] celular sem rolagem lateral (${lat}px)`);
    await P.emulateMedia({ colorScheme: 'dark' });
    chk(await P.evaluate(() => getComputedStyle(document.querySelector('#ig-lista tbody tr')).display === 'flex'), '[H] celular: a lista vira cartões');
    cob = await cobre();
    chk(!cob.length, '[H] celular: nada cobre as linhas (cartões)' + (cob.length ? ': ' + cob.join(' | ') : ''));
    await P.evaluate(() => window.scrollTo(0, 0)); if (process.env.PRINTS) await P.screenshot({ path: process.env.PRINTS + '/ing-ui-depois-390.png' });
    await P.emulateMedia({ colorScheme: 'light' });
    await ctx.close();

    // ---------------- [I] ----------------
    const { ctx: c2, page: O } = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    chk(!(await O.locator('#nav button[data-v="ingressos"]').isVisible()), '[I] operador não vê Ingressos no menu');
    const sts = await O.evaluate(async d => Promise.all([fetch('/api/ingressos/datas'), fetch('/api/ingressos/lista?turma=' + d), fetch('/api/ingressos/701/cobranca', { method: 'POST' })].map(p => p.then(r => r.status))), sp);
    chk(sts.every(s => s === 403), '[I] operador: datas, lista e cobrança dão 403 (' + sts.join(',') + ')');
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
