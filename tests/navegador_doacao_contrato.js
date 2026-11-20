// CAMP-DOA-CONTRATO / CAMP-DOA-AVISOS (20/11/2026): prévia do "Enviar contrato para assinatura" e o aviso de etapa, no navegador de verdade
// (Playwright + Chromium), com um SITE FALSO (nada sai de verdade). Rafael: "No painel preciso poder pôr o link do contrato pra assinatura, e
// gerar a cobrança no mercado livre quando enviar o contrato pra assinatura em e-mails separados".
//  [A] a prévia mostra para quem, o e-mail 1 (contrato TR30, com o link) e o e-mail 2 (cobrança TR27, com o valor) e "Gerar a cobrança junto"
//      marcada com R$ 1.000 ou mais; confirmar manda ao site 1º o contrato e depois a cobrança
//  [B] desmarcada: só o contrato
//  [C] ao mudar a etapa: "Avisar a pessoa por e-mail" marcada em Aguardando informações, sem caixa em Em análise; salvar manda o aviso
//  [D] dados da pessoa nunca dentro de onclick
// Uso (servidor PRÓPRIO na porta 8820; o site falso sobe aqui na 8821):
//   CAMP_DB_PATH=/dev/shm/doa/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/doa/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8820)
//   CAMP_DB_PATH=/dev/shm/doa/m.db CAMP_BASE=http://127.0.0.1:8820 node tests/navegador_doacao_contrato.js
const http = require('http');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8820', DB = process.env.CAMP_DB_PATH, PORTA_SITE = +(process.env.SITE_PORTA || 8821);
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

const ROTA = '/wp-json/camp/v1/painel/doacoes-acervo';
const REG = { id: 601, protocolo: 'CAMP-2026-000601', recebida_em: '2026-11-20T12:00:00+00:00', nome: "Maria D'Ávila <b>", email: 'maria@exemplo.com', telefone: '11 98888-7777',
  autor: 'Escritório Fulano', descricao: 'rolos', tipos_nomes: ['Plantas'], quantidade_estimativa_faixa: '51_500', local: 'Campinas/SP', fotos: [], etapa: 'aprovada', etapa_nome: 'Aprovada',
  valor: 0, contrato_link: '', notas: [], cobranca: null, pode_cobrar: false, historico: [], avisos: [], alterado_em: '2026-11-20T12:00:00+00:00' };
const site = { pedidos: [] };
const servidor = http.createServer((req, res) => {
  let corpo = '';
  req.on('data', d => { corpo += d; });
  req.on('end', () => {
    const u = new URL(req.url, 'http://x'), j = (code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
    let b = {}; try { b = corpo ? JSON.parse(corpo) : {}; } catch (_) { b = {}; }
    if (req.method === 'POST') site.pedidos.push([u.pathname, b]);
    if (u.pathname === ROTA + '/601/enviar-contrato') { Object.assign(REG, { etapa: 'contrato_enviado', etapa_nome: 'Contrato enviado para assinatura', contrato_link: b.contrato_link, valor: +b.valor || REG.valor, pode_cobrar: true }); return j(200, { ok: true, enviado: true, template: 'TR30', sender: { id: 'e30' }, registro: REG }); }
    if (u.pathname === ROTA + '/601' && req.method === 'POST') {
      if (b.acao === 'gerar_cobranca') { REG.cobranca = { id: 10, situacao: 'aberta', situacao_nome: 'Aberta', valor: REG.valor, link: 'https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=p', external_reference: 'CAMP-COB-10', pago_em: '' }; return j(200, { ok: true, registro: REG, email_cobranca: { enviado: true, template: 'TR27', sender_id: 'e27' } }); }
      if (b.etapa) Object.assign(REG, { etapa: b.etapa, etapa_nome: b.etapa });
      return j(200, Object.assign({ ok: true, registro: REG }, b.avisar ? { aviso: { enviado: true, template: 'TR31', etapa: b.etapa } } : {}));
    }
    j(404, { code: 'rest_no_route', message: 'Nenhuma rota' });
  });
});

(async () => {
  await new Promise(r => servidor.listen(PORTA_SITE, '127.0.0.1', r));
  py(`for k,v in (('wp.url','http://127.0.0.1:${PORTA_SITE}'),('wp.usuario','painel'),('wp.app_password','xxxx yyyy')):\n    con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES (?,?,?,0) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(k,v,k))\nr=json.loads(sys.argv[2])\ncon.execute("INSERT OR REPLACE INTO doacao_acervo (site_id, protocolo, recebida_em, nome, email, etapa, valor, dados) VALUES (601,?,?,?,?,?,?,?)",(r['protocolo'],'2026-11-20 12:00:00',r['nome'],r['email'],'aprovada',None,json.dumps(r)))`, JSON.stringify(REG));
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const P = await ctx.newPage();
    P.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await P.goto(BASE + '/#doacoes');
    await P.waitForSelector('#doa-lista tr[data-doa-abrir="601"]', { timeout: 15000 });
    await P.click('#doa-lista tr[data-doa-abrir="601"]');
    await P.waitForSelector('[data-doa-acao="contrato"]');
    chk((await P.locator('#drawer').textContent()).includes('Link do contrato para assinatura'), '[A] campo "Link do contrato para assinatura" no detalhe');
    // [A] prévia
    await P.fill('#doa-contrato', 'https://app.clicksign.com/sign/abc');
    await P.fill('#doa-valor', '2000');
    await P.click('[data-doa-acao="contrato"]');
    await P.waitForSelector('#conf-ov #doa-env-cob');
    const prev = await P.locator('#conf-ov').textContent();
    chk(prev.includes("Maria D'Ávila <b>") && prev.includes('maria@exemplo.com'), '[A] prévia: para quem (nome e e-mail, como texto)');
    chk(prev.includes('E-mail 1 · Contrato para assinatura') && prev.includes('https://app.clicksign.com/sign/abc') && prev.includes('E-mail 2 · Cobrança no Mercado Pago') && /R\$\s?2\.000,00/.test(prev), '[A] prévia: e-mail 1 com o link e e-mail 2 com o valor');
    chk(await P.isChecked('#doa-env-cob'), '[A] "Gerar a cobrança junto" marcada (R$ 1.000 ou mais)');
    await P.fill('#doa-env-prazo', '2030-01-10');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => !document.getElementById('conf-ov'), null, { timeout: 10000 });
    const ord = site.pedidos.map(p => p[0] + (p[1].acao ? ' ' + p[1].acao : ''));
    chk(JSON.stringify(ord) === JSON.stringify([ROTA + '/601/enviar-contrato', ROTA + '/601 gerar_cobranca']) && site.pedidos[0][1].prazo === '2030-01-10' && site.pedidos[0][1].cobranca === true, '[A] o site recebeu 1º o contrato e depois a cobrança: ' + JSON.stringify(ord));
    await P.waitForFunction(() => /TR30/.test(document.body.innerText) && /TR27/.test(document.body.innerText), null, { timeout: 10000 });
    chk(true, '[A] a tela diz que os dois e-mails saíram (TR30 e TR27)');
    // [B] desmarcada
    site.pedidos.length = 0;
    await P.waitForSelector('[data-doa-acao="contrato"]');
    await P.click('[data-doa-acao="contrato"]');
    await P.waitForSelector('#conf-ov #doa-env-cob');
    await P.uncheck('#doa-env-cob');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => !document.getElementById('conf-ov'), null, { timeout: 10000 });
    chk(site.pedidos.length === 1 && site.pedidos[0][0] === ROTA + '/601/enviar-contrato' && site.pedidos[0][1].cobranca === false, '[B] desmarcada: só o contrato');
    // [C] aviso de etapa
    await P.waitForSelector('#doa-etapa-sel');
    await P.selectOption('#doa-etapa-sel', 'em_analise');
    chk(await P.locator('#doa-avisar').count() === 0, '[C] Em análise: sem a caixa de aviso');
    await P.selectOption('#doa-etapa-sel', 'info');
    await P.waitForSelector('#doa-avisar');
    chk(await P.isChecked('#doa-avisar') && (await P.inputValue('#doa-aviso-texto')).length > 20, '[C] Aguardando informações: "Avisar a pessoa por e-mail" marcada, com o texto pronto');
    await P.fill('#doa-aviso-msg', 'Mande fotos dos rolos.');
    site.pedidos.length = 0;
    await P.click('[data-doa-acao="salvar"]');
    await P.waitForFunction(() => /avisada por e-mail/.test(document.body.innerText), null, { timeout: 10000 });
    const pa = site.pedidos.find(p => p[0] === ROTA + '/601') || [0, {}];
    chk(pa[1].etapa === 'info' && pa[1].avisar === true && pa[1].mensagem === 'Mande fotos dos rolos.' && pa[1].aviso_texto, '[C] salvar manda a etapa, avisar, o texto e a mensagem; a tela diz que a pessoa foi avisada');
    // [D] nada de dados da pessoa em onclick
    const oc = await P.evaluate(() => [...document.querySelectorAll('[onclick]')].map(e => e.getAttribute('onclick')).join(' '));
    chk(!oc.includes('maria@exemplo.com') && !oc.includes('Ávila'), '[D] nenhum dado da pessoa dentro de onclick');
  } catch (e) { chk(false, 'erro no teste: ' + e.message); }
  finally { await browser.close(); servidor.close(); }
  chk(!erros.length, 'sem erro de JavaScript na página' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
