// 23/11 (Rafael, print do cartão da folha: "esse bug ao clicar nos 3 pontinhos"): o menu ⋯ do cartão saía cortado pela borda do cartão
// (.thumb com overflow:hidden). Prova, no navegador de verdade: com o menu aberto, cada item fica inteiro à vista e clicável (o ponto
// central e as duas pontas de cada item são o próprio item, não o cartão nem o vizinho), em tela larga e no celular.
// Uso (servidor PRÓPRIO, porta 9050–9059; banco de tests/semear_banco_teste.py):
//   (cd backend && CAMP_DB_PATH=/dev/shm/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 9051)
//   CAMP_BASE=http://127.0.0.1:9051 node tests/navegador_menu_cartao.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9051';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME }); const erros = [];
  try {
    for (const [w, h] of [[1366, 900], [390, 844]]) {
      const page = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
      page.on('pageerror', e => erros.push(e.message));
      await page.goto(BASE + '/'); await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
      await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
      await page.goto(BASE + '/#projeto/F003-P9001'); await page.waitForSelector('.thumb .mais-menu summary:visible', { timeout: 15000 }); await page.waitForTimeout(800);
      const sum = page.locator('.thumb .mais-menu summary:visible').first(); await sum.scrollIntoViewIfNeeded(); await sum.click(); await page.waitForTimeout(300);
      const r = await page.evaluate(() => { const m = document.querySelector('.thumb .mais-menu[open] .mais-lista'); if (!m) return { aberto: false };
        const itens = [...m.querySelectorAll('.btn')].map(b => { const q = b.getBoundingClientRect(), y = q.top + q.height / 2;
          const ok = [q.left + 6, q.left + q.width / 2, q.right - 6].every(x => { const el = document.elementFromPoint(x, y); return !!el && (el === b || b.contains(el)); });
          return { t: b.textContent.trim(), ok, dentro: q.left >= 0 && q.right <= innerWidth }; });
        return { aberto: true, itens }; });
      chk(r.aberto && r.itens.length >= 2 && r.itens.every(i => i.ok && i.dentro), `menu ⋯ do cartão da folha a ${w} px: cada item inteiro à vista e clicável (${JSON.stringify(r.itens || []).slice(0, 220)})`);
      await page.close();
    }
    chk(!erros.length, 'sem erro de JavaScript' + (erros.length ? ': ' + erros.slice(0, 2).join(' | ') : ''));
  } catch (e) { chk(false, 'o teste quebrou: ' + String(e && e.message || e).slice(0, 300)); }
  finally { await browser.close(); }
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
