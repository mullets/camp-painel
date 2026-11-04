// Menu lateral (redesenho Material novo §2–3 + pedido do Rafael de 04/11/2026), no navegador de verdade (Playwright + Chromium):
//  - "Menu lateral em azul-marinho escuro, independente da área principal clara" (também no tema claro); item ativo com fundo azul e contraste forte.
//  - "quero clicar no logo e ir pra home do sistema sempre" / "eh o LOGO e CAMP do lado. nao acervos": a marca do topo é o logo + "CAMP",
//    um link acessível ("CAMP — ir para a página inicial") que leva a #painel de qualquer tela, no menu aberto, recolhido e na gaveta do celular.
//  - "arruma os numeros do lado dos itens, ta mal diagramado": as pílulas de TODOS os itens com contador ficam na mesma coluna (mesmo `right`,
//    ±1 px), com a mesma altura, sem encostar no rótulo, em 1366 e 1920 px, tema claro e escuro.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/x/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/m.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8984)
//   CAMP_BASE=http://127.0.0.1:8984 node tests/navegador_menu_camp.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8984';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const lum = c => { const m = String(c).match(/\d+(\.\d+)?/g) || [255, 255, 255]; const [r, g, b] = m.slice(0, 3).map(x => { x = +x / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };

async function entrar(browser, w, tema, erros) {
  const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: tema });
  const page = await ctx.newPage();
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await page.addInitScript(() => { try { localStorage.setItem('camp.side', '0'); } catch (_) {} });   // menu aberto também no notebook
  await page.goto(BASE + '/');
  await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    for (const tema of ['light', 'dark']) for (const w of [1366, 1920]) {
      const { ctx, page } = await entrar(browser, w, tema, erros);
      await page.evaluate(() => nav('filas')); await page.waitForTimeout(1200);
      // os contadores de todos os itens aparecem com números de verdade (incl. um grande, para provar que cabe)
      await page.evaluate(() => { const pr = (id, n, r) => { const el = document.getElementById(id); if (el) { el.textContent = fmtN(n); el.hidden = false; el.classList.toggle('r', !!r); } };
        pr('n-gente', 16); pr('n-filas', 17); pr('n-err', 1234); pr('n-dec', 2, true); pr('n-sol', 5); pr('n-ins', 3); });
      await page.waitForTimeout(200);
      const m = await page.evaluate(() => {
        const side = document.querySelector('.side'), on = document.querySelector('#nav button.on');
        const pills = [...document.querySelectorAll('#nav button .n:not([hidden])')].filter(n => n.offsetParent).map(n => {
          const b = n.closest('button'), r = n.getBoundingClientRect(), rg = document.createRange();
          const txt = [...b.childNodes].filter(x => x.nodeType === 3 && x.textContent.trim());
          let tr = 0; txt.forEach(t => { rg.selectNodeContents(t); const q = rg.getBoundingClientRect(); tr = Math.max(tr, q.right); });
          return { item: b.dataset.v, right: Math.round(r.right * 10) / 10, h: Math.round(r.height), left: r.left, txtRight: tr, btnTop: b.getBoundingClientRect().top, top: r.top, bottom: r.bottom, bBottom: b.getBoundingClientRect().bottom };
        });
        const brand = document.getElementById('brand-home');
        return { sideBg: getComputedStyle(side).backgroundColor, mainBg: getComputedStyle(document.body).backgroundColor, onBg: on ? getComputedStyle(on).backgroundColor : '', onInk: on ? getComputedStyle(on).color : '',
                 pills, brand: brand ? { tag: brand.tagName, aria: brand.getAttribute('aria-label'), txt: brand.textContent.trim() } : null, topoTxt: document.querySelector('.side').innerText.split('\n').slice(0, 2).join(' ') };
      });
      const tag = `${w} px, tema ${tema === 'light' ? 'claro' : 'escuro'}`;
      chk(lum(m.sideBg) < 0.03 && (tema === 'dark' || lum(m.mainBg) > 0.6), `${tag}: menu azul-marinho escuro (${m.sideBg}) e área principal ${tema === 'light' ? 'clara' : 'escura'} (${m.mainBg})`);
      const [r, g, b] = (m.onBg.match(/\d+/g) || []).map(Number);
      chk(b > r + 60 && b > 120 && lum(m.onInk) > 0.8, `${tag}: item ativo com fundo azul (${m.onBg}) e texto claro (${m.onInk})`);
      chk(!!m.brand && m.brand.tag === 'A' && m.brand.aria === 'CAMP — ir para a página inicial' && m.brand.txt === 'CAMP' && !/Acervos|administração interna/i.test(m.topoTxt), `${tag}: a marca do menu é o logo + "CAMP" (link "CAMP — ir para a página inicial"): ${JSON.stringify(m.brand)} / "${m.topoTxt}"`);
      const rights = m.pills.map(p => p.right), hs = m.pills.map(p => p.h);
      chk(m.pills.length >= 5 && Math.max(...rights) - Math.min(...rights) <= 1, `${tag}: as ${m.pills.length} pílulas na mesma coluna (right ${[...new Set(rights)].join(', ')})`);
      chk(new Set(hs).size === 1, `${tag}: as pílulas têm a mesma altura (${[...new Set(hs)].join(', ')})`);
      chk(m.pills.every(p => p.left - p.txtRight >= 6 && p.top >= p.btnTop && p.bottom <= p.bBottom + 0.5), `${tag}: nenhuma pílula encosta no rótulo nem sai do item: ${JSON.stringify(m.pills.map(p => [p.item, Math.round(p.left - p.txtRight)]))}`);
      if (w === 1366 && tema === 'light') {
        // logo leva à Home de qualquer tela, com o menu aberto e recolhido
        await page.click('#brand-home'); await page.waitForTimeout(600);
        chk((await page.evaluate(() => location.hash)) === '#painel', 'clicar no logo (menu aberto) vai para #painel');
        await page.evaluate(() => nav('projetos')); await page.waitForTimeout(500);
        await page.click('#collapse'); await page.waitForTimeout(300);
        const rec = await page.evaluate(() => { const n = document.querySelector('#n-filas'), r = n.getBoundingClientRect(), s = n.closest('button').querySelector('svg').getBoundingClientRect(); return { col: document.querySelector('.app').classList.contains('collapsed'), w: r.width, cobre: r.left < s.right - 4 && r.top < s.bottom - 4 && r.right > s.left + 4 }; });
        chk(rec.col && rec.w <= 12 && !rec.cobre, 'menu recolhido: o contador vira selo pequeno no canto do ícone, sem cobri-lo: ' + JSON.stringify(rec));
        await page.click('#brand-home'); await page.waitForTimeout(600);
        chk((await page.evaluate(() => location.hash)) === '#painel', 'clicar no logo (menu recolhido) vai para #painel');
        await page.click('#collapse'); await page.waitForTimeout(200);
      }
      await ctx.close();
    }
    // celular: a gaveta fecha e vai para a Home
    const { ctx, page } = await entrar(browser, 390, 'light', erros);
    await page.evaluate(() => nav('erros')); await page.waitForTimeout(600);
    await page.click('#nav-gaveta'); await page.waitForTimeout(400);
    await page.click('#brand-home'); await page.waitForTimeout(700);
    chk((await page.evaluate(() => location.hash)) === '#painel' && !(await page.evaluate(() => document.body.classList.contains('nav-aberto'))), 'celular: o logo na gaveta fecha a gaveta e vai para #painel');
    await ctx.close();
  } catch (e) { chk(false, 'o teste quebrou: ' + (e.stack || e.message)); }
  chk(!erros.length, 'nenhum erro de página' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
