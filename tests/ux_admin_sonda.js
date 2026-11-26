// Sonda: em uma rota/largura, lista os elementos que alargam o .main (rolagem lateral real).
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9171';
(async () => {
  const [rota, w, h] = [process.env.ROTA || 'financeiro/projeto', +(process.env.W || 390), +(process.env.H || 844)];
  const br = await chromium.launch(); const pg = await br.newPage({ viewport: { width: w, height: h } });
  pg.on('pageerror', e => console.log('pageerror', e.message));
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', process.env.EMAIL || 'rafael@camp.arq.br'); await pg.fill('#lg-senha', process.env.SENHA || 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.goto(BASE + '/#' + rota); await pg.waitForTimeout(+(process.env.ESPERA || 2500));
  if (process.env.JS) console.log(await pg.evaluate(process.env.JS));
  const r = await pg.evaluate(() => {
    const m = document.querySelector('.main'); const out = [];
    const lim = m.getBoundingClientRect().right;
    document.querySelectorAll('.main *').forEach(el => {
      const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return;
      const b = el.getBoundingClientRect(); if (!b.width) return;
      if (b.right > lim + 1) { let a = el.parentElement, clip = false; while (a && a !== m) { const o = getComputedStyle(a).overflowX; if (o !== 'visible') { clip = true; break } a = a.parentElement }
        if (!clip) out.push((el.id ? '#' + el.id : el.tagName.toLowerCase()) + '.' + [...el.classList].join('.') + ' w=' + Math.round(b.width) + ' r=' + Math.round(b.right)); }
    });
    return { sw: m.scrollWidth, cw: m.clientWidth, out: out.slice(0, 25) };
  });
  console.log(JSON.stringify(r, null, 1));
  if (process.env.PRINT) await pg.screenshot({ path: process.env.PRINT, fullPage: false });
  await br.close();
})();
