// UX-31 no navegador: "F0xx-P000x" deixa de ficar solto no cabeçalho (vira parte do placeholder da busca) e a caixa
// "Como funciona esta página" chega RECOLHIDA nas outras páginas depois do primeiro "Entendi" (por pessoa, guardado no servidor).
// Prova: sem o <span class="hint"> no topo; placeholder com o exemplo do código; 1ª página com a caixa inteira; "Entendi" grava a
// preferência; a próxima página mostra só a linha "ⓘ Como funciona esta página" (fechada, sem o "Entendi" visível) e abre no clique;
// depois do F5 continua recolhida; o "?" traz a caixa inteira; "Entendi" ali some com ela de vez; outra pessoa ainda vê a caixa inteira.
// Uso (servidor PRÓPRIO numa porta exclusiva):
//   CAMP_DB_PATH=/tmp/ux31/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux31/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8949)
//   CAMP_DB_PATH=/tmp/ux31/x.db CAMP_BASE=http://127.0.0.1:8949 node tests/navegador_ux31_ajuda.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8949';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const entrar = async (email, senha) => {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } }), page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
    page.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU && AJUDA_VISTAS !== null, null, { timeout: 15000 });
    return page;
  };
  const ir = async (page, rota) => { await page.evaluate(r => nav(r), rota); await page.waitForTimeout(900); };
  const caixa = (page, k) => page.evaluate(k => { const b = document.querySelector(`#v-${k} > .ajuda-caixa`); if (!b) return null;
    const f = b.querySelector('[data-ajuda-fechar]'); return { tag: b.tagName, recolhida: b.classList.contains('ajuda-recolhida'), aberta: b.tagName !== 'DETAILS' || b.open,
      entendiVisivel: !!(f && (f.checkVisibility ? f.checkVisibility() : f.offsetParent)), altura: b.getBoundingClientRect().height, txt: b.innerText.replace(/\s+/g, ' ').slice(0, 80) }; }, k);
  try {
    const page = await entrar('operador@camp.arq.br', 'senha-operador-123');

    // ---- "F0xx-P000x" não fica solto no cabeçalho ----
    const top = await page.evaluate(() => ({ hint: !!document.querySelector('.top .search .hint'), ph: document.getElementById('q').placeholder,
      solto: [...document.querySelectorAll('.top *')].some(e => !e.children.length && /F0xx-P000x/.test(e.textContent)) }));
    chk(!top.hint && !top.solto && /F0xx-P000x/.test(top.ph), 'busca: o exemplo "F0xx-P000x" está no placeholder e não solto no cabeçalho: ' + JSON.stringify(top));

    // ---- 1ª página: caixa inteira; Entendi grava no servidor ----
    await ir(page, 'painel');
    let c = await caixa(page, 'painel');
    chk(c && !c.recolhida && c.entendiVisivel, '1ª vez: a caixa "Como funciona esta página" vem inteira, com "Entendi": ' + JSON.stringify(c));
    await page.click('#v-painel [data-ajuda-fechar="painel"]'); await page.waitForTimeout(800);
    chk(!(await caixa(page, 'painel')), '"Entendi" fecha a caixa');

    // ---- as outras páginas chegam recolhidas ----
    await ir(page, 'filas');
    c = await caixa(page, 'filas');
    chk(c && c.recolhida && !c.aberta && !c.entendiVisivel && c.altura < 60 && /Como funciona esta página/.test(c.txt), 'depois do 1º "Entendi", a próxima página mostra só a linha recolhida: ' + JSON.stringify(c));
    await page.click('#v-filas > .ajuda-recolhida > summary'); await page.waitForTimeout(300);
    c = await caixa(page, 'filas');
    chk(c && c.aberta && c.entendiVisivel && /Para que serve/.test(await page.innerText('#v-filas > .ajuda-caixa')), 'clicar na linha abre o texto com o "Entendi"');

    await page.reload(); await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU && AJUDA_VISTAS !== null, null, { timeout: 15000 });
    await ir(page, 'projetos');
    c = await caixa(page, 'projetos');
    chk(c && c.recolhida && !c.aberta, 'depois do F5 (preferência no servidor), as páginas ainda não vistas continuam recolhidas: ' + JSON.stringify(c));
    await ir(page, 'painel');
    chk(!(await caixa(page, 'painel')), 'a página em que deu "Entendi" segue sem a caixa depois do F5');

    // ---- "?" traz a caixa inteira; Entendi ali some de vez ----
    await ir(page, 'filas');
    await page.evaluate(() => reabrirAjuda()); await page.waitForTimeout(400);
    c = await caixa(page, 'filas');
    chk(c && !c.recolhida && c.entendiVisivel, 'o "?" troca a linha recolhida pela caixa inteira: ' + JSON.stringify(c));
    await page.click('#v-filas [data-ajuda-fechar="filas"]'); await page.waitForTimeout(800);
    await ir(page, 'projetos'); await ir(page, 'filas');
    chk(!(await caixa(page, 'filas')), '"Entendi" na caixa da Fila: some de vez');
    const pf = await page.evaluate(async () => (await fetch('/api/auth/eu/preferencias')).json());
    chk(!!pf['ajuda.painel'] && !!pf['ajuda.filas'], 'as preferências ficam no servidor, por pessoa: ' + JSON.stringify(pf));

    // ---- outra pessoa: caixa inteira ----
    const ad = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
    await ir(ad, 'filas');
    c = await caixa(ad, 'filas');
    chk(c && !c.recolhida, 'outra pessoa (que nunca deu "Entendi") vê a caixa inteira: ' + JSON.stringify(c));
    chk(!erros.length, 'nenhum erro no console: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e.stack || e.message)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
