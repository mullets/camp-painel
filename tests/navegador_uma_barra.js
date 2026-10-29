// 29/10 (Rafael: "a home do painel tá com 2 barras de rolagem"). Causa: o menu da esquerda, mais alto que a tela, esticava a linha
// da grade (.app): a página inteira rolava E o conteúdo (.main) rolava por dentro. Prova: em telas de várias alturas, na home e em
// Problemas, a página (html) não rola; só o conteúdo rola; o menu, se não couber, rola dentro dele; no celular o menu fica embaixo.
// Uso: bash tests/rodar_um.sh tests/navegador_uma_barra.js   (ou CAMP_BASE=http://127.0.0.1:89xx node tests/navegador_uma_barra.js)
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
(async () => {
  const br = await chromium.launch();
  const erros = [];
  for (const [w, h] of [[1400, 900], [1280, 620], [1000, 520], [390, 760]]) {
    const pg = await (await br.newContext({ viewport: { width: w, height: h } })).newPage();
    pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await pg.goto(BASE + '/');
    await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
    for (const tela of ['', '#problemas']) {
      await pg.goto(BASE + '/' + tela); await pg.reload(); await pg.waitForTimeout(1500);
      const r = await pg.evaluate(() => {
        const se = document.scrollingElement, main = document.querySelector('.main'), side = document.querySelector('.side');
        return { pagina: se.scrollHeight - innerHeight, main: main.scrollHeight - main.clientHeight, mainAlt: Math.round(main.getBoundingClientRect().height),
                 side: Math.round(side.getBoundingClientRect().bottom), sideRola: side.scrollHeight > side.clientHeight + 1, sideOy: getComputedStyle(side).overflowY };
      });
      const nome = `${w}x${h} ${tela || 'home'}`;
      chk(r.pagina <= 0, `${nome}: a página não rola (só o conteúdo)`, `sobra ${r.pagina}px`);
      chk(r.mainAlt <= h, `${nome}: o conteúdo cabe na altura da tela`, `${r.mainAlt}px`);
      chk(r.side <= h + 1, `${nome}: o menu termina dentro da tela`, `fundo em ${r.side}px`);
      if (w > 720 && r.sideRola) chk(r.sideOy === 'auto', `${nome}: menu mais alto que a tela rola dentro dele`, r.sideOy);
    }
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
