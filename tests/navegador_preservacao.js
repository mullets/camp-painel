// UX-02 (parte de código) no navegador de verdade (Playwright + Chromium). Sem réplica configurada (o destino é decisão do Rafael):
// o bloco "Preservação" aparece no TOPO de Máquinas, vermelho, com "Suas imagens têm só uma cópia" e quando o QNAP enche; o ponto do
// topo fica vermelho; a Home diz a mesma frase. No celular, sem rolagem lateral. Nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux02.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux02.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8942)
//   CAMP_DB_PATH=/tmp/ux02.db CAMP_BASE=http://127.0.0.1:8942 node tests/navegador_preservacao.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8942', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || undefined;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
py(`
import tempfile, os
raiz = tempfile.mkdtemp(); os.mkdir(os.path.join(raiz, "ACERVOS_CAMP"))     # QNAP "conectado": o vermelho do topo vem SÓ da falta de réplica
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.raiz'", (raiz,))
con.execute("UPDATE configuracao SET valor='' WHERE chave='replica.raiz'")
`);

(async () => {
  const browser = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/api\/analytics/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('estacoes'));
    await page.waitForSelector('#preservacao', { timeout: 30000 });
    const pv = await page.evaluate(() => { const b = document.getElementById('preservacao'), body = document.getElementById('est-body'); return { nivel: b.dataset.nivel, txt: b.textContent.replace(/\s+/g, ' '), primeiro: body.firstElementChild === b }; });
    chk(pv.primeiro, 'o bloco "Preservação" é o PRIMEIRO de Máquinas');
    chk(pv.nivel === 'critico' && /Suas imagens têm só uma cópia/.test(pv.txt) && /só uma cópia/.test(pv.txt), 'sem réplica: vermelho, "Suas imagens têm só uma cópia": ' + pv.txt.slice(0, 160));
    chk(/Última cópia válida/.test(pv.txt) && /Espaço no QNAP/.test(pv.txt), 'o bloco diz a última cópia válida e o espaço do QNAP');
    await page.waitForFunction(() => !!document.querySelector('#machine-status .ms-ponto'), null, { timeout: 20000 });
    const ponto = await page.getAttribute('#machine-status .ms-ponto', 'class');
    chk(/\bcrit\b/.test(ponto), 'sem réplica, o ponto do topo fica vermelho: "' + ponto + '"');
    await page.evaluate(() => nav('painel'));
    await page.waitForFunction(() => /Suas imagens têm só uma cópia/.test((document.getElementById('ini-saude') || {}).textContent || ''), null, { timeout: 20000 }).catch(() => {});
    chk(/Suas imagens têm só uma cópia/.test(await page.textContent('#ini-saude')), 'a Home ("Está tudo funcionando?") diz a mesma frase');
    await page.setViewportSize({ width: 390, height: 800 }); await page.evaluate(() => nav('estacoes')); await page.waitForSelector('#preservacao', { timeout: 30000 }); await page.waitForTimeout(500);
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'celular: Máquinas sem rolagem lateral');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do servidor' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
