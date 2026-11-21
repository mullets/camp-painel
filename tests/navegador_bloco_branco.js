// CAMP-VIEW (bloco branco) no navegador de verdade (Playwright + Chromium).
// Rafael (print de #item/F002-P0002-1973-S04-D00032, e antes em Ingressos): "um retângulo branco/cinza-claro grande" cobrindo a parte de baixo da
// tela, por cima do menu, da imagem e da lista.
// Causa: o .sr (texto só para leitor de tela, position:absolute) não tinha nenhum ancestral posicionado; o bloco que o contém virava a JANELA, não o
// .main (que é quem rola). Um .sr no fim de uma lista longa (legenda da tabela de Projetos/Material novo, os "cumprido/pendente" do fundo, os passos
// da doação…) fazia a janela ficar maior que a tela. Bastava a roda chegar ao fim da lista (ou um foco/scrollIntoView) para a JANELA rolar: o .app,
// de 100% de altura, subia e o fundo cinza-claro do body aparecia embaixo, como um retângulo em branco por cima de tudo.
// Prova, a 2000×1300 e 1366×768, em #item, Precisa de você, Ingressos, Doações, Projetos, Material novo e um fundo:
//  - depois de navegar, de um aviso ("Bem-vindo…"), de abrir e fechar uma janela (Relatar problema), da ajuda (?) e da roda até o fim:
//    a janela não rola (scrollHeight = altura da tela; scrollTo não mexe) e nenhum ponto da tela mostra o fundo do body;
//  - nenhum elemento fixo/absoluto opaco maior que 300×200 cobre o conteúdo (fora o cabeçalho .top);
//  - o mesmo com um .sr de propósito 3000 px abaixo, dentro da tela atual (qualquer lista longa).
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/bb/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/bb/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8900)
//   CAMP_BASE=http://127.0.0.1:8900 node tests/navegador_bloco_branco.js
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8900';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const ITEM = 'F026-P0001-1968-S01-D00001';
const ROTAS = ['item/' + ITEM, 'painel', 'ingressos', 'doacoes', 'projetos', 'filas', 'fundo/F026'];

// o que está na frente de cada ponto da tela: o body/html à mostra = "retângulo em branco"; elemento opaco fixo/absoluto grande = cobertura
async function examinar(pg) {
  return pg.evaluate(() => {
    const se = document.scrollingElement, antes = scrollY;
    window.scrollTo(0, 100000); const rolou = scrollY; window.scrollTo(0, antes);
    let fundo = 0; const pontos = [];
    for (let x = 10; x < innerWidth; x += 50) for (let y = 10; y < innerHeight; y += 50) {
      const el = document.elementFromPoint(x, y);
      if (!el || el === document.body || el === document.documentElement) { fundo++; if (pontos.length < 3) pontos.push(x + ',' + y); }
    }
    const capas = [];
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (!['fixed', 'absolute'].includes(cs.position)) continue;
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      const q = el.getBoundingClientRect();
      if (q.width < 300 || q.height < 200 || q.bottom < 0 || q.top > innerHeight || q.right < 0 || q.left > innerWidth) continue;
      const bg = cs.backgroundColor; if (/rgba\(.*,\s*0\)$/.test(bg) || bg === 'transparent') continue;
      capas.push(`${el.tagName}#${el.id}.${String(el.className).slice(0, 40)} ${[q.left, q.top, q.width, q.height].map(Math.round)}`);
    }
    return { sh: se.scrollHeight, sw: se.scrollWidth, vh: innerHeight, vw: innerWidth, y: scrollY, rolou, fundo, pontos, capas };
  });
}
const limpo = (r) => r.sh <= r.vh + 1 && r.sw <= r.vw + 1 && r.y === 0 && r.rolou === 0 && r.fundo === 0 && !r.capas.length;
const det = (r) => JSON.stringify({ scrollHeight: r.sh, altura: r.vh, janelaRola: r.rolou, fundoAMostra: r.fundo, pontos: r.pontos, capas: r.capas });

async function rodaAteOFim(pg) {
  await pg.mouse.move(pg.viewportSize().width * 0.6, pg.viewportSize().height * 0.75);
  for (let i = 0; i < 14; i++) { await pg.mouse.wheel(0, 900); await pg.waitForTimeout(40); }
  await pg.waitForTimeout(300);
}

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  for (const [w, h] of [[2000, 1300], [1366, 768]]) {
    const ctx = await br.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
    pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
    await pg.route(/exemplo\.test/, r => r.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1100"><rect width="1600" height="1100" fill="#789"/></svg>' }));
    await pg.goto(BASE + '/');
    await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
    await pg.reload(); await pg.waitForTimeout(1500);
    for (const r of ROTAS) {
      await pg.evaluate(x => { location.hash = x; }, r); await pg.waitForTimeout(1600);
      const tag = `${w}×${h} #${r}`;
      let x = await examinar(pg); chk(limpo(x), `${tag}: ao abrir, a janela não rola e nada cobre a tela`, det(x));
      await pg.evaluate(() => toast('Bem-vindo, Rafael')); await pg.waitForTimeout(400);
      if (r.startsWith('item/')) { await pg.click('#idet [data-relatar-folha]').catch(() => {}); await pg.waitForTimeout(500); await pg.keyboard.press('Escape'); await pg.waitForTimeout(400); await pg.evaluate(() => { if (window.closeModal) closeModal(); }); }
      await pg.keyboard.press('?'); await pg.waitForTimeout(500); await pg.keyboard.press('Escape'); await pg.waitForTimeout(300);
      await pg.evaluate(() => { if (document.querySelector('.main.with-drawer') && window.closeDrawer) closeDrawer(true); });
      await pg.waitForTimeout(2600);   // o aviso some
      await rodaAteOFim(pg);
      x = await examinar(pg); chk(limpo(x), `${tag}: depois do aviso, da janela, da ajuda e da roda até o fim, nenhum retângulo em branco`, det(x));
      // qualquer lista longa: um .sr 3000 px abaixo, dentro da tela atual
      await pg.evaluate(() => { const c = document.querySelector('.content.on'); if (!c) return; const d = document.createElement('div'); d.id = 'bb-longa'; d.innerHTML = '<div style="height:3000px"></div><span class="sr">fim da lista</span>'; c.appendChild(d); });
      await rodaAteOFim(pg);
      await pg.evaluate(() => { const s = document.querySelector('#bb-longa .sr'); if (s) s.scrollIntoView(); });
      await pg.waitForTimeout(200);
      x = await examinar(pg); chk(limpo(x), `${tag}: com um texto de leitor de tela no fim de uma lista longa, a janela continua parada`, det(x));
      if (!limpo(x) && w === 2000 && r.startsWith('item/') && process.env.PRINTS) await pg.screenshot({ path: path.join(process.env.PRINTS, 'bloco-branco.png') });
      await pg.evaluate(() => { document.getElementById('bb-longa')?.remove(); document.querySelector('.main').scrollTop = 0; window.scrollTo(0, 0); });
    }
    await ctx.close();
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.slice(0, 3).join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
