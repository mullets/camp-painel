// UX-07 no navegador de verdade (Playwright + Chromium): Máquinas › Alertas por e-mail mostra o nível das MESMAS medições da tela.
// Prova: com o QNAP em 12% livre, "QNAP quase cheio" aparece em "atenção" (antes: "ainda não medido"); a cópia do acervo sem destino
// aparece "não medido" COM o motivo; "Verificar agora" mede o site (fora do ar) e a linha "Site sem resposta" passa a "atenção";
// a segunda verificação seguida deixa "crítico". Nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux07.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux07.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8942)
//   CAMP_DB_PATH=/tmp/ux07.db CAMP_BASE=http://127.0.0.1:8942 node tests/navegador_alertas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8942', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || undefined;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
py(`
con.execute("DELETE FROM qnap_snapshot")   # sem a série da semana: o nível vem só dos 12% (UX-02: o ritmo também conta)
con.execute("INSERT INTO qnap_snapshot (montado, total_gb, livre_gb, entrada_bruta, prontos) VALUES (1, 1000, 120, 3, 4)")
con.execute("UPDATE configuracao SET valor='http://127.0.0.1:9' WHERE chave='wp.url'")
con.execute("UPDATE configuracao SET valor='' WHERE chave='smtp.host'")
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
  const linha = k => page.evaluate(k_ => { const li = document.querySelector(`#al-lista li[data-alerta="${k_}"]`); return li ? { nivel: li.dataset.nivel, txt: li.textContent.replace(/\s+/g, ' ').trim() } : null; }, k);
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('estacoes/alertas'));   // UX-24: a aba Alertas
    await page.waitForSelector('#al-lista li[data-alerta="qnap"]', { timeout: 30000 });
    const q = await linha('qnap');
    chk(q && q.nivel === 'atencao' && /atenção/.test(q.txt) && /12% livre/.test(q.txt) && !/ainda não medido/.test(q.txt), '"QNAP quase cheio" com 12% livre: atenção, com o número da tela: ' + JSON.stringify(q));
    const r = await linha('replica');
    chk(r && r.nivel === 'nao_medido' && /não medido/.test(r.txt) && /replica\.raiz/.test(r.txt), '"Cópia do acervo parada" sem destino: "não medido" COM o motivo: ' + JSON.stringify(r));
    await page.click('#al-verificar');
    await page.waitForFunction(() => { const li = document.querySelector('#al-lista li[data-alerta="site"]'); return li && li.dataset.nivel === 'atencao'; }, null, { timeout: 30000 });
    const s1 = await linha('site');
    chk(s1.nivel === 'atencao' && /não respondeu uma vez/.test(s1.txt), '"Verificar agora" com o site fora do ar: "Site sem resposta" em atenção (1 falha): ' + JSON.stringify(s1));
    await page.click('#al-verificar');
    await page.waitForFunction(() => { const li = document.querySelector('#al-lista li[data-alerta="site"]'); return li && li.dataset.nivel === 'critico'; }, null, { timeout: 30000 });
    const s2 = await linha('site');
    chk(s2.nivel === 'critico' && /crítico/.test(s2.txt) && /duas verificações seguidas/.test(s2.txt), 'a segunda verificação seguida sem resposta: crítico: ' + JSON.stringify(s2));
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do servidor' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
