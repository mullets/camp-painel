// CAMP-HOME-CLIMA (21/11/2026): o clima das salas na barra do topo, no navegador de verdade (Playwright + Chromium), com leituras semeadas
// direto no banco (nenhuma chamada à Tuya). Rafael: "na home do painel colocar as temperaturas que estão em clima também, modo simpático de
// aparecer, talvez lá em cima onde fica o status das coisas" e depois "um resumo, não individual, uma média de todos sensores".
//  [A] sem sensor: não aparece nada
//  [B] a pílula mostra a MÉDIA dos sensores ("23,1° · 58%") com a cor do PIOR sensor (âmbar: uma sala fora da faixa)
//  [C] o painel que abre tem a frase, quantos sensores entram na média, as salas e o link para o Clima do acervo
//  [D] todos sem leitura recente (mais de 3 h): cinza, "sem leitura há 4 h"
//  [E] desligado (clima.coleta_min = 0): some
//  [F] celular (390 px): só o ícone e a temperatura média, sem rolagem lateral; tocar abre o painel dentro da tela
// Uso (servidor PRÓPRIO na porta 8890):
//   CAMP_DB_PATH=/dev/shm/hc/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/hc/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8890)
//   CAMP_DB_PATH=/dev/shm/hc/m.db CAMP_BASE=http://127.0.0.1:8890 [PRINTS=pasta] node tests/navegador_clima_topo.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8890', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const coleta = m => py(`con.execute("UPDATE configuracao SET valor=? WHERE chave='clima.coleta_min'", (sys.argv[2],))`, String(m));
const leituras = (lista, idade) => py(`for sid, t, u in json.loads(sys.argv[2]):\n    con.execute("INSERT INTO clima_leitura (sensor_id, temperatura_c, umidade_pct, lido_em) VALUES (?,?,?,datetime('now', ?))", (sid, t, u, sys.argv[3]))`, JSON.stringify(lista), idade || '-5 minutes');
const foto = async (page, nome) => { if (PRINTS) { fs.mkdirSync(PRINTS, { recursive: true }); await page.screenshot({ path: `${PRINTS}/${nome}.png` }); } };

async function entrar(browser, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 800 }, deviceScaleFactor: 1, colorScheme: o.escuro ? 'dark' : 'light', isMobile: !!o.movel, hasTouch: !!o.movel });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$/.test(url)) o.erros.push(m.text()); });
  page.on('pageerror', e => o.erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await page.waitForTimeout(1200);
  return { ctx, page };
}
const reler = page => page.evaluate(() => atualizarClimaTopo());

(async () => {
  py(`con.execute("DELETE FROM clima_leitura")\ncon.execute("DELETE FROM clima_sensor")`);
  coleta(10);
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    // ---------------- [A] sem sensor ----------------
    const { ctx, page: P } = await entrar(browser, { erros });
    chk(await P.evaluate(() => typeof atualizarClimaTopo === 'function'), '[A] a barra do topo lê o clima (atualizarClimaTopo existe)');
    chk(await P.locator('#clima-topo').count() === 1 && !(await P.locator('#clima-topo').isVisible()), '[A] ligado mas sem sensor: nada na barra');

    // ---------------- [B] média + pior nível ----------------
    py(`con.execute("INSERT INTO clima_sensor (id, nome, nome_tuya) VALUES ('devA','Arquivo','Arquivo'), ('devB','Servidor','Servidor')")`);
    leituras([['devA', 22.0, 50.0], ['devB', 24.2, 66.0]]);
    await reler(P);
    const pil = P.locator('#clima-topo summary.clima-btn');
    chk(await pil.isVisible(), '[B] a pílula do clima aparece na barra do topo');
    const txt = (await pil.textContent()).replace(/\s+/g, ' ');
    chk(txt.includes('23,1°') && txt.includes('58%') && !txt.includes('Arquivo'), `[B] mostra a média dos sensores (23,1° · 58%), não cada sala (${txt})`);
    chk(await pil.evaluate(e => e.classList.contains('aviso')), '[B] cor do PIOR sensor: âmbar (Servidor fora da faixa)');
    const rot = await pil.getAttribute('aria-label');
    chk(/média de 2 sensores/.test(rot) && /23,1 °C/.test(rot) && /Servidor: umidade um pouco alta \(66%\)/.test(rot), `[B] aria-label com o texto inteiro (${rot})`);
    const lado = await P.evaluate(() => { const c = document.getElementById('clima-topo').getBoundingClientRect(), w = document.querySelector('.top .who').getBoundingClientRect(); return Math.abs(c.top - w.top) < 30; });
    chk(lado, '[B] fica na mesma linha do estado dos sistemas e do menu da pessoa');
    await foto(P, 'clima-1366-claro');

    // ---------------- [C] painel ----------------
    await pil.click();
    const pn = P.locator('#clima-topo .clima-painel');
    chk(await pn.isVisible(), '[C] clicar abre o painel do clima');
    const tp = (await pn.textContent()).replace(/\s+/g, ' ');
    chk(tp.includes('Servidor: umidade um pouco alta (66%)'), '[C] frase simpática com a sala que pede atenção');
    chk(/Média de 2 sensores/.test(tp), '[C] diz quantos sensores entram na média');
    chk(await P.locator('#clima-topo .clima-salas li').count() === 2 && tp.includes('Arquivo') && tp.includes('22,0° · 50%'), '[C] lista as salas (pequena)');
    chk(tp.includes('Faixa desejada: 18 a 24 °C · 40 a 60 % de umidade'), '[C] mostra a faixa desejada (mesmo texto do Clima do acervo)');
    chk(await P.locator('#clima-topo a[href="/clima"]').isVisible(), '[C] link "Abrir Clima do acervo"');
    await foto(P, 'clima-1366-claro-aberto');
    await P.locator('#v-painel').click({ position: { x: 10, y: 300 } }).catch(() => {});
    chk(!(await pn.isVisible()), '[C] clicar fora fecha o painel');

    // ---------------- [D] sem leitura recente ----------------
    py(`con.execute("UPDATE clima_leitura SET lido_em=datetime('now','-4 hours')")`);
    await reler(P);
    chk(await pil.evaluate(e => e.classList.contains('sem')), '[D] todos sem leitura recente: pílula cinza');
    const corIco = await P.evaluate(() => { const i = document.querySelector('#clima-topo .clima-ico'), t = document.createElement('span'); t.style.color = 'var(--ink3)'; document.body.append(t); const r = [getComputedStyle(i).color, getComputedStyle(t).color]; t.remove(); return r; });
    chk(corIco[0] === corIco[1], `[D] o ícone usa o cinza do painel (${corIco.join(' = ')})`);
    chk(/sem leitura há 4 h/.test(await pil.textContent()), '[D] "sem leitura há 4 h" na pílula');

    // ---------------- [E] desligado ----------------
    coleta(0); await reler(P);
    chk(!(await P.locator('#clima-topo').isVisible()), '[E] clima desligado: some da barra');
    coleta(10); leituras([['devA', 22.0, 50.0], ['devB', 24.2, 66.0]]);
    await reler(P);
    await ctx.close();

    // ---------------- escuro 1366 ----------------
    const { ctx: cE, page: E } = await entrar(browser, { erros, escuro: true });
    chk(await E.locator('#clima-topo summary.clima-btn').isVisible(), '[B] modo escuro: a pílula aparece');
    await foto(E, 'clima-1366-escuro');
    await E.locator('#clima-topo summary.clima-btn').click(); await foto(E, 'clima-1366-escuro-aberto');
    await cE.close();

    // ---------------- [F] celular ----------------
    for (const escuro of [false, true]) {
      const { ctx: cM, page: M } = await entrar(browser, { erros, w: 390, h: 844, movel: true, escuro });
      const pm = M.locator('#clima-topo summary.clima-btn');
      chk(await pm.isVisible(), `[F] 390 px${escuro ? ' escuro' : ''}: a pílula aparece`);
      chk(!(await M.locator('#clima-topo .clima-umid').isVisible()) && /23,1°/.test(await pm.textContent()), `[F] 390 px${escuro ? ' escuro' : ''}: só o ícone e a temperatura média`);
      const sem = await M.evaluate(() => { const b = document.querySelector('#clima-topo summary').getBoundingClientRect(); return document.documentElement.scrollWidth <= innerWidth && b.right <= innerWidth && b.left >= 0; });
      chk(sem, `[F] 390 px${escuro ? ' escuro' : ''}: sem rolagem lateral, pílula dentro da tela`);
      await foto(M, `clima-390-${escuro ? 'escuro' : 'claro'}`);
      await pm.tap();
      const dentro = await M.evaluate(() => { const p = document.querySelector('#clima-topo .clima-painel'); if (!p || !p.checkVisibility()) return false; const r = p.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && document.documentElement.scrollWidth <= innerWidth; });
      chk(dentro, `[F] 390 px${escuro ? ' escuro' : ''}: tocar abre o painel inteiro dentro da tela`);
      await foto(M, `clima-390-${escuro ? 'escuro' : 'claro'}-aberto`);
      await cM.close();
    }
    chk(!erros.length, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    chk(false, 'exceção: ' + (e && e.stack || e));
  } finally {
    await browser.close();
  }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
