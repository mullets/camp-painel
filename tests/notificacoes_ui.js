// Checagens de tela (Playwright, Chromium de verdade) do cartão "Notificações": Estações → Alertas → "Quem recebe cada aviso".
// Fora do servidor de teste nada sai (fontes externas viram CSS vazio).
// Uso (servidor PRÓPRIO, nunca a porta 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8890)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8890 node tests/notificacoes_ui.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8890', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [], ERROS = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const cfg = k => py(`r=con.execute("SELECT valor FROM configuracao WHERE chave=?",("${k}",)).fetchone();print(r[0] if r else '')`);

async function abrir(ctx, email, senha) {
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() !== 'error') return; const u = (m.location() || {}).url || '';
    if (/Failed to load resource/.test(m.text()) && /\/api\/alertas\/preferencias/.test(u) && page.__esperaErro) return;   // o 400 de propósito (e-mail inválido)
    ERROS.push(email + ': ' + m.text() + (u ? ' @ ' + u : '')) });
  page.on('pageerror', e => ERROS.push(email + ' pageerror: ' + e.message));
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email, senha } });
  chk(r.ok(), 'login ' + email);
  return page;
}

(async () => {
  py(`con.execute("UPDATE configuracao SET valor='rafael@camp.arq.br' WHERE chave='avisos.email'")
con.execute("UPDATE configuracao SET valor='1' WHERE chave LIKE 'avisos.%.ligado' OR chave='avisos.pedido_novo'")
con.execute("UPDATE configuracao SET valor='' WHERE chave LIKE 'avisos.%.email'")
con.execute("UPDATE configuracao SET valor='24' WHERE chave='avisos.fila_travada.horas'")`);   // estado inicial: pode rodar de novo no mesmo banco
  const browser = await chromium.launch({ executablePath: CHROME });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  const page = await abrir(ctx, 'rafael@camp.arq.br', 'senha-bem-longa-123');

  await page.goto(BASE + '/#estacoes');
  await page.waitForSelector('#avpref-painel #avp-lista li', { timeout: 20000 });
  const itens = await page.$$eval('#avp-lista li[data-avp]', l => l.map(x => x.dataset.avp));
  chk(itens.length === 9 && ['fila_travada', 'bloqueio', 'pedido_painel', 'pedido', 'qnap'].every(a => itens.includes(a)), 'a tela lista os 9 assuntos: ' + itens.join(','));
  const txt = await page.textContent('#avpref-painel');
  chk(/Quem recebe cada aviso/.test(txt) && /WhatsApp e Trello: aguardando decisão/.test(txt), 'título e a nota "WhatsApp e Trello: aguardando decisão"');
  chk(/Lote parado na Fila/.test(txt) && /Problema que impede publicar/.test(txt) && /Pedido de material registrado no painel/.test(txt), 'os assuntos novos aparecem com nome para leigo');
  chk(await page.$eval('#avp-geral', e => e.value) === 'rafael@camp.arq.br' && await page.$eval('#avp-horas', e => e.value) === '24', 'lista geral e o limite de 24 h vêm preenchidos');
  chk(await page.$eval('#avp-lista li[data-avp="qnap"] [data-avp-emails]', e => e.placeholder.includes('lista geral')), 'campo vazio explica que vai para a lista geral');
  chk(await page.$$eval('#avp-lista [data-avp-liga]', l => l.every(c => c.checked && c.getAttribute('aria-label'))), 'todos ligados por padrão, com rótulo para leitor de tela');

  // desliga um, troca a lista de outro e o limite de horas
  await page.uncheck('#avp-lista li[data-avp="bloqueio"] [data-avp-liga]');
  chk(await page.$eval('#avp-lista li[data-avp="bloqueio"]', e => e.classList.contains('av-off')), 'desmarcar deixa a linha apagada na hora');
  await page.fill('#avp-lista li[data-avp="fila_travada"] [data-avp-emails]', 'fila@camp.arq.br, ti@camp.arq.br');
  await page.fill('#avp-horas', '12');
  await page.click('#avp-salvar');
  await page.waitForFunction(() => /Preferências de aviso salvas/.test(document.body.innerText), null, { timeout: 10000 });
  await page.waitForTimeout(500);
  chk(cfg('avisos.bloqueio.ligado') === '0' && cfg('avisos.fila_travada.email') === 'fila@camp.arq.br, ti@camp.arq.br' && cfg('avisos.fila_travada.horas') === '12', 'salvar grava no banco (desligado, lista própria e 12 h)');
  chk(await page.$eval('#avp-lista li[data-avp="bloqueio"] [data-avp-liga]', c => !c.checked) && await page.$eval('#avp-horas', e => e.value) === '12', 'depois de salvar a tela mostra o que ficou gravado');

  // e-mail inválido: recusado com frase clara e nada muda
  page.__esperaErro = true;
  await page.fill('#avp-lista li[data-avp="qnap"] [data-avp-emails]', 'isso não é email');
  await page.click('#avp-salvar');
  await page.waitForFunction(() => /não parece um e-mail/.test(document.body.innerText), null, { timeout: 10000 });
  chk(cfg('avisos.qnap.email') === '', 'e-mail inválido: aparece "não parece um e-mail" e nada é gravado');
  page.__esperaErro = false;

  // celular: sem rolagem lateral
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular (390 px) a tela não rola para o lado');
  await page.screenshot({ path: (process.env.SHOT_DIR || '/tmp') + '/notificacoes_celular.png', fullPage: false });

  // operador: não vê a tela de preferências e a rota recusa
  const ctxOp = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctxOp.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  const pOp = await abrir(ctxOp, 'operador@camp.arq.br', 'senha-operador-123');
  await pOp.goto(BASE + '/#estacoes'); await pOp.waitForTimeout(3000);
  chk(await pOp.$('#avpref-painel') === null, 'operador não vê "Quem recebe cada aviso"');
  const g = await ctxOp.request.get(BASE + '/api/alertas/preferencias'), w = await ctxOp.request.put(BASE + '/api/alertas/preferencias', { data: { assuntos: [{ assunto: 'qnap', ligado: false }] } });
  chk(g.status() === 403 && w.status() === 403 && cfg('avisos.qnap.ligado') === '1', 'operador: ler e gravar dão 403');

  chk(ERROS.length === 0, 'nenhum erro no console: ' + ERROS.join(' | ').slice(0, 600));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
