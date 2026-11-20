// CAMP-AUTENTIQUE (20/11/2026): assinatura eletrônica pela Autentique no navegador de verdade (Playwright + Chromium), com SITE FALSO e
// AUTENTIQUE FALSA (nada sai de verdade). Rafael: "Enviar contrato para assinatura" cria o contrato na Autentique; todos assinaram → a doação
// passa a "Contrato assinado pelas partes" sozinha.
//  [A] Assinatura eletrônica (Autentique): colar o token, Testar conexão, Ligada + Salvar; o token some do campo e nunca volta à página
//  [B] prévia com "Anexar o PDF do contrato" (sem link colado, já marcada); anexar o PDF e Enviar → a Autentique recebe o PDF e o site
//      recebe o TR30 com o link de assinatura da Autentique
//  [C] o detalhe mostra a assinatura pendente; "Conferir assinatura agora" com todos assinados → o site recebe contrato_assinado + a data
//  [D] desligada: a prévia volta a ser só o link colado
//  [E] o token não aparece em nenhum lugar da página; dados da pessoa fora de onclick; sem erro de JavaScript
// Uso (servidor PRÓPRIO na 8830; o site falso e a Autentique falsa sobem aqui na 8831):
//   CAMP_DB_PATH=/dev/shm/aut/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/aut/m.db CAMP_COOKIE_SECURE=false CAMP_AUTENTIQUE_URL=http://127.0.0.1:8831/autentique python3 -m uvicorn app.main:app --port 8830)
//   CAMP_DB_PATH=/dev/shm/aut/m.db CAMP_BASE=http://127.0.0.1:8830 SITE_PORTA=8831 node tests/navegador_autentique.js
const http = require('http');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8830', DB = process.env.CAMP_DB_PATH, PORTA_SITE = +(process.env.SITE_PORTA || 8831);
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

const TK = 'tok-navegador-SEGREDO-0987654321abcdef';
const LINK_AUT = 'https://assina.ae/Nav12345';
const ROTA = '/wp-json/camp/v1/painel/doacoes-acervo';
const REG = { id: 611, protocolo: 'CAMP-2026-000611', recebida_em: '2026-11-20T12:00:00+00:00', nome: "Ana D'Ávila <i>", email: 'ana@exemplo.com', telefone: '11 9',
  autor: 'Escritório Ciclano', fotos: [], etapa: 'aprovada', etapa_nome: 'Aprovada', valor: 0, contrato_link: '', notas: [], cobranca: null, pode_cobrar: false, historico: [], avisos: [], alterado_em: '2026-11-20T12:00:00+00:00' };
const site = { pedidos: [] }, aut = { pedidos: [], assinado: false };
const servidor = http.createServer((req, res) => {
  const partes = [];
  req.on('data', d => partes.push(d));
  req.on('end', () => {
    const corpo = Buffer.concat(partes).toString('latin1');
    const u = new URL(req.url, 'http://x'), j = (code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
    if (u.pathname === '/autentique') {
      aut.pedidos.push({ auth: req.headers.authorization, corpo });
      if (req.headers.authorization !== 'Bearer ' + TK) return j(401, { message: 'Unauthenticated.' });
      if (corpo.includes('createDocument')) return j(200, { data: { createDocument: { id: 'doc-nav-1', name: 'x', signatures: [
        { public_id: 'sig-d', name: 'Ana', email: null, action: { name: 'SIGN' }, link: { short_link: LINK_AUT } }] } } });
      if (corpo.includes('me {')) return j(200, { data: { me: { name: 'CAMP Navegador', email: 'conta@camp.arq.br', subscription: { documents: 10 } } } });
      return j(200, { data: { document: { id: 'doc-nav-1', signatures: [{ public_id: 'sig-d', name: 'Ana', email: null, action: { name: 'SIGN' },
        signed: aut.assinado ? { created_at: '2026-11-21 15:00:00' } : null, rejected: null }] } } });
    }
    let b = {}; try { b = corpo ? JSON.parse(Buffer.from(corpo, 'latin1').toString('utf-8')) : {}; } catch (_) { b = {}; }
    if (req.method === 'POST') site.pedidos.push([u.pathname, b]);
    if (u.pathname === ROTA + '/611/enviar-contrato') { Object.assign(REG, { etapa: 'contrato_enviado', etapa_nome: 'Contrato enviado para assinatura', contrato_link: b.contrato_link }); return j(200, { ok: true, enviado: true, sender: { id: 'e30' }, registro: REG }); }
    if (u.pathname === ROTA + '/611' && req.method === 'POST') {
      if (b.etapa) Object.assign(REG, { etapa: b.etapa, etapa_nome: b.etapa });
      if (b.assinado_em) REG.assinado_em = b.assinado_em;
      return j(200, { ok: true, registro: REG });
    }
    j(404, { code: 'rest_no_route', message: 'Nenhuma rota' });
  });
});

(async () => {
  await new Promise(r => servidor.listen(PORTA_SITE, '127.0.0.1', r));
  py(`for k,v in (('wp.url','http://127.0.0.1:${PORTA_SITE}'),('wp.usuario','painel'),('wp.app_password','xxxx yyyy')):\n    con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES (?,?,?,0) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(k,v,k))\nr=json.loads(sys.argv[2])\ncon.execute("INSERT OR REPLACE INTO doacao_acervo (site_id, protocolo, recebida_em, nome, email, etapa, valor, dados) VALUES (611,?,?,?,?,?,?,?)",(r['protocolo'],'2026-11-20 12:00:00',r['nome'],r['email'],'aprovada',None,json.dumps(r)))`, JSON.stringify(REG));
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const P = await ctx.newPage();
    P.on('pageerror', e => erros.push('pageerror: ' + e.message));
    const respostas = [];
    P.on('response', async r => { if (r.url().includes('/api/')) { try { respostas.push(await r.text()); } catch (_) {} } });
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await P.goto(BASE + '/#doacoes');
    await P.waitForSelector('#doa-lista tr[data-doa-abrir="611"]', { timeout: 15000 });
    // [A] configuração
    chk((await P.textContent('#doa-aut-sit')).includes('desligada'), '[A] começa desligada');
    await P.click('#doa-aut > summary');
    await P.waitForFunction(() => /cole o token/.test(document.getElementById('doa-aut-token').placeholder));
    await P.fill('#doa-aut-token', TK);
    await P.click('#doa-aut-testar');
    await P.waitForFunction(() => /CAMP Navegador/.test(document.getElementById('doa-aut-res').textContent), null, { timeout: 10000 });
    chk(aut.pedidos.length === 1 && aut.pedidos[0].auth === 'Bearer ' + TK && aut.pedidos[0].corpo.includes('me {'), '[A] Testar conexão: query me com o token digitado (Bearer)');
    await P.check('#doa-aut-ligado');
    await P.click('#doa-aut-salvar');
    await P.waitForFunction(() => /ligada/.test(document.getElementById('doa-aut-sit').textContent) && !/desligada/.test(document.getElementById('doa-aut-sit').textContent), null, { timeout: 10000 });
    chk((await P.inputValue('#doa-aut-token')) === '' && (await P.getAttribute('#doa-aut-token', 'placeholder')).includes('configurado'), '[A] salvo e ligado: o campo do token fica vazio ("configurado")');
    // [B] prévia com o PDF
    await P.click('#doa-lista tr[data-doa-abrir="611"]');
    await P.waitForSelector('[data-doa-acao="contrato"]');
    await P.click('[data-doa-acao="contrato"]');
    await P.waitForSelector('#conf-ov #doa-env-pdf');
    chk(await P.isChecked('#conf-ov input[name="doa-env-modo"][value="pdf"]') && await P.isDisabled('#conf-ov input[name="doa-env-modo"][value="link"]'), '[B] sem link colado: "Anexar o PDF do contrato" marcada (link desabilitado)');
    chk((await P.textContent('#conf-ov')).includes("Ana D'Ávila <i>"), '[B] para quem, como texto');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => /Escolha o PDF/.test((document.getElementById('conf-err') || {}).textContent || ''), null, { timeout: 5000 });
    chk(site.pedidos.length === 0, '[B] sem arquivo: pede o PDF e nada sai');
    await P.setInputFiles('#doa-env-pdf', { name: 'Contrato Ana.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% teste\n%%EOF\n') });
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(() => !document.getElementById('conf-ov'), null, { timeout: 15000 });
    const cria = aut.pedidos.find(p => p.corpo.includes('createDocument'));
    chk(!!cria && cria.corpo.includes('%PDF-1.4') && /"signers": \[\{"name": "Ana D'/.test(cria.corpo) && cria.corpo.includes('"action": "SIGN"') && cria.corpo.includes('variables.file'), '[B] a Autentique recebeu o PDF (multipart) com quem doa como assinante, por nome');
    chk(site.pedidos.length === 1 && site.pedidos[0][0] === ROTA + '/611/enviar-contrato' && site.pedidos[0][1].contrato_link === LINK_AUT, '[B] o site recebeu o TR30 com o link da Autentique: ' + JSON.stringify(site.pedidos.map(p => p[1].contrato_link)));
    // [C] conferir
    await P.waitForSelector('[data-doa-acao="conferir-assinatura"]', { timeout: 10000 });
    chk((await P.locator('#drawer').textContent()).includes('Aguardando assinaturas'), '[C] detalhe: assinatura na Autentique aguardando');
    aut.assinado = true; site.pedidos.length = 0;
    await P.click('[data-doa-acao="conferir-assinatura"]');
    await P.waitForFunction(() => /Todos assinaram/.test(document.body.innerText), null, { timeout: 10000 });
    const pa = site.pedidos.find(p => p[0] === ROTA + '/611') || [0, {}];
    chk(pa[1].etapa === 'contrato_assinado' && pa[1].assinado_em === '2026-11-21', '[C] Conferir assinatura agora: o site recebe contrato_assinado com a data da assinatura');
    // [D] desligar
    await P.click('#drawer [aria-label="Fechar"], #drawer .x, #drawer [data-fechar]').catch(() => P.keyboard.press('Escape'));
    await P.evaluate(() => { document.getElementById('doa-aut').open = true; });
    await P.uncheck('#doa-aut-ligado');
    await P.click('#doa-aut-salvar');
    await P.waitForFunction(() => /desligada/.test(document.getElementById('doa-aut-sit').textContent), null, { timeout: 10000 });
    py(`con.execute("UPDATE doacao_acervo SET etapa='aprovada' WHERE site_id=611")`);
    await P.evaluate(() => carregarDoacoes());
    await P.evaluate(() => doaAbrir(611));
    await P.waitForSelector('[data-doa-acao="contrato"]');
    await P.fill('#doa-contrato', 'https://app.clicksign.com/sign/xyz');
    await P.click('[data-doa-acao="contrato"]');
    await P.waitForSelector('#conf-ov #doa-env-cob');
    chk(await P.locator('#conf-ov #doa-env-pdf').count() === 0 && (await P.textContent('#conf-ov')).includes('https://app.clicksign.com/sign/xyz'), '[D] desligada: sem PDF, só o link colado');
    await P.click('#conf-ov [data-conf="nao"]');
    // [E]
    const html = await P.content();
    chk(!html.includes(TK) && !respostas.some(t => t.includes(TK)), '[E] o token não aparece na página nem em resposta da API (' + respostas.length + ' respostas)');
    const oc = await P.evaluate(() => [...document.querySelectorAll('[onclick]')].map(e => e.getAttribute('onclick')).join(' '));
    chk(!oc.includes('ana@exemplo.com') && !oc.includes('Ávila'), '[E] nenhum dado da pessoa dentro de onclick');
  } catch (e) { chk(false, 'erro no teste: ' + e.message); }
  finally { await browser.close(); servidor.close(); }
  chk(!erros.length, 'sem erro de JavaScript na página' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
