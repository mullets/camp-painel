// UX-12 (26/10, logs técnicos): a tela consultava /api/tarefas a cada 20 s, /api/estacoes a cada 30 s e, na página do projeto,
// a marca a cada 12 s; e o Painel chamava /api/analytics (5–16 s) mesmo com o Google Analytics desligado.
// Prova no navegador de verdade (Playwright + Chromium), contando as requisições:
//  - no Painel (GA desligado no banco sintético) /api/analytics NÃO é chamado;
//  - parado no Painel por 62 s: no máximo 1 requisição periódica a cada 30 s (só /api/novidades);
//  - parado na página de um projeto por 62 s: idem (a marca do projeto vem junto em /api/novidades);
//  - nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux12.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux12.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8945)
//   CAMP_DB_PATH=/tmp/ux12.db CAMP_BASE=http://127.0.0.1:8945 node tests/navegador_ux12_polling.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8945', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
// GA desligado de verdade (o padrão): sem GA4 direto e sem Site Kit
py(`con.execute("UPDATE configuracao SET valor='' WHERE chave IN ('ga4.propriedade','ga4.conta_servico')"); con.execute("UPDATE configuracao SET valor='0' WHERE chave='analytics.site_kit'")`);
const PROJ = py(`print(con.execute("SELECT codigo FROM projeto WHERE mesclado_em IS NULL ORDER BY codigo LIMIT 1").fetchone()[0])`);
const PERIODICAS = /\/api\/(tarefas(\?|$)|estacoes(\?|$)|novidades|projetos\/[^/]+\/marca|analytics(\?|$))/;

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], reqs = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('request', r => { const u = r.url().replace(BASE, ''); if (u.startsWith('/api/')) reqs.push({ t: Date.now(), u }); });
  const contar = (desde, re) => reqs.filter(x => x.t >= desde && re.test(x.u)).map(x => x.u.split('?')[0]);
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('painel'));
    await page.waitForSelector('#ini-visitas', { timeout: 15000 }); await page.waitForTimeout(4000);
    const an = contar(0, /\/api\/analytics(\?|$)/);
    chk(an.length === 0, `Painel com o GA desligado: /api/analytics não é chamado (${an.length} chamada(s))`);
    const vis = await page.evaluate(() => (document.getElementById('ini-visitas') || {}).textContent || '');
    chk(/não está ligado/.test(vis), 'o cartão de visitas diz que o Google Analytics não está ligado: ' + vis.slice(0, 80));
    const nos = await page.evaluate(() => document.getElementsByTagName('*').length);
    linhas.push(`info  nós no DOM com o Painel aberto: ${nos}`);

    let t0 = Date.now(); await page.waitForTimeout(62000);
    let p = contar(t0, PERIODICAS);
    chk(p.length <= 2 && p.every(u => u === '/api/novidades'), `parado no Painel 62 s: no máximo 2 consultas periódicas, só /api/novidades (${p.length}: ${p.join(', ')})`);

    await page.evaluate(c => nav('projeto/' + c), PROJ);
    await page.waitForTimeout(3000);
    t0 = Date.now(); await page.waitForTimeout(62000);
    p = contar(t0, PERIODICAS);
    chk(p.length <= 2 && p.every(u => u === '/api/novidades'), `parado no projeto ${PROJ} 62 s: no máximo 2 consultas periódicas, só /api/novidades (${p.length}: ${p.join(', ')})`);
    const comMarca = reqs.filter(x => x.t >= t0 && /\/api\/novidades\?.*projeto=/.test(x.u)).length;
    chk(comMarca >= 1, `na página do projeto a consulta periódica leva a marca (projeto=${PROJ})`);
    chk(erros.length === 0, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  } catch (e) {
    chk(false, 'o teste quebrou: ' + (e && e.stack || e));
  } finally {
    await browser.close();
    console.log(linhas.join('\n'));
    console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
    process.exit(problemas.length ? 1 : 0);
  }
})();
