// UX-60 (parte do painel) no navegador de verdade (Playwright + Chromium): em "Qualidade do CAMP Vision", quantas folhas ficaram sem leitura
// porque a resposta do modelo veio quebrada (o CAMP Vision avisa por campo: "valor descartado: resposta do modelo quebrada (cidade)"),
// uma folha contando uma vez, e o link de cada uma para a conferência dela.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux60.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux60.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8972)
//   CAMP_DB_PATH=/tmp/ux60.db CAMP_BASE=http://127.0.0.1:8972 node tests/navegador_ux60_quebrada.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8972', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

const P = 'F023-P0011', F2 = P + '-1959-S01-D00002';
py(`
RQ = "valor descartado: resposta do modelo quebrada"
for campo in ("cidade", "uf, resto de marcação tirado"):
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('aviso','metadado','campvision','${F2}',?,'CAMP Vision')", ("%s (%s)" % (RQ, campo),))
con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('aviso','metadado','campvision','${P}-1959-S01-D00099',?,'CAMP Vision')", (RQ + " (ano)",))
`);

(async () => {
  const browser = await chromium.launch(process.env.CHROME || require('fs').existsSync(CHROME) ? { executablePath: CHROME } : {});
  const erros = [];
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/\/api\/auth\/eu$|favicon/.test(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.goto(BASE + '/#qualidade');
    await page.waitForSelector('#qc-quebrada', { timeout: 15000 });
    const t = (await page.textContent('#qc-quebrada')).replace(/\s+/g, ' ');
    chk(/Folhas sem leitura por resposta quebrada/.test(t) && /2 folhas ficaram sem leitura em 1 projeto/.test(t), 'o quadro conta 2 folhas (a com 2 campos quebrados conta uma vez): "' + t.slice(0, 120) + '"');
    chk(/cidade, uf/.test(t), 'a folha mostra os campos juntos (cidade, uf)');
    chk(await page.getAttribute(`#qc-quebrada a[href="#conferir/${P}/${F2}"]`, 'href') !== null, 'a folha do painel leva à conferência dela');
    chk(await page.getAttribute(`#qc-quebrada a[href="#projeto/${P}"]`, 'href') !== null && /fora do painel/.test(t), 'a folha fora do painel leva ao projeto e diz "fora do painel"');
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300);
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular, sem rolagem lateral');
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
