// UX-64 (b) no navegador de verdade (Playwright + Chromium): em Problemas, a mesma folha aparecia 2–3 vezes (ex.: F001-P0007 D00025 como
// "bloqueia", "corrigir — fora do painel" e "autoria divergente"). Agora é UMA linha por folha com os motivos juntos, e cada motivo mantém a
// própria caixa de seleção, o "O que fazer" e o botão que resolve. E (a): o problema de folha RETIRADA pelo CAMP Vision fica só no da retirada.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux64.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux64.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8972)
//   CAMP_DB_PATH=/tmp/ux64.db CAMP_BASE=http://127.0.0.1:8972 node tests/navegador_ux64_problemas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8972', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

const P = 'F023-P0011', F3 = P + '-1959-S01-D00003', F4 = P + '-1959-S01-D00004', F90 = P + '-1959-S01-D00090';
py(`
def erro(g, cat, o, cod, d, ch=None):
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por,chave) VALUES (?,?,?,?,?,?,?)", (g, cat, o, cod, d, 'CAMP Vision' if o == 'campvision' else 'operador@camp.arq.br', ch))
erro('bloqueia', 'orientacao', 'revisao', '${F3}', 'Folha de cabeça para baixo')
erro('corrigir', 'metadado', 'operador', '${F3}', 'Título da folha 3 incompleto')
erro('corrigir', 'credito', 'operador', '${F4}', 'Crédito da folha 4 faltando')
erro('corrigir', 'autoria_divergente', 'campvision', '${F90}', 'O CAMP Vision retirou esta folha do lote: autoria divergente. Ela não entrou na revisão.', 'campvision:retirado:${F90}')
erro('bloqueia', 'outro', 'campvision', '${F90}', 'título ilegível na folha 90', 'campvision:erros:ux64nav')
`);

(async () => {
  const browser = await chromium.launch(process.env.CHROME || require('fs').existsSync(CHROME) ? { executablePath: CHROME } : {});
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/previa$/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.goto(BASE + '/#erros/' + P);
    await page.waitForSelector(`#err-body tr[data-err-folha="${F3}"]`, { timeout: 15000 });
    const linhasF3 = await page.locator(`#err-body tr[data-err-linha]`).filter({ has: page.locator(`.code[title="${F3}"]`) }).count();
    chk(linhasF3 === 1, `a folha D00003 com 2 problemas aparece em UMA linha (${linhasF3})`);
    const l3 = page.locator(`#err-body tr[data-err-folha="${F3}"]`);
    chk(await l3.locator('.err-motivo').count() === 2 && /2 motivos/.test(await l3.textContent()), 'a linha junta os 2 motivos e diz "2 motivos"');
    chk(/bloqueia/.test(await l3.locator('td').nth(1).textContent()), 'a gravidade da linha é a mais séria (bloqueia)');
    chk(await l3.locator('.err-motivo .err-sel').count() === 2, 'cada motivo tem a própria caixa de seleção');
    chk(await l3.locator('.err-motivo button.err-acao').count() === 2 && /girar/i.test(await l3.locator('.err-motivo').first().textContent()), 'cada motivo tem o próprio botão que resolve ("Abrir a folha para girar" no da rotação)');
    chk(await l3.locator('.err-motivo .err-fazer').count() === 2, 'cada motivo tem o "O que fazer"');
    await l3.locator('.err-motivo .err-sel').first().check();
    chk(/1 selecionado/.test(await page.textContent('#err-bulk-n')), 'marcar um motivo seleciona só aquele problema');
    chk(await page.locator(`#err-body tr[data-err-linha]`).filter({ has: page.locator(`.code[title="${F4}"]`) }).count() === 1
        && !(await page.$(`#err-body tr[data-err-folha="${F4}"]`)), 'folha com um problema só continua a linha de sempre');
    // (a) a folha retirada: só o problema da retirada (o bloqueio do erros.json fechou sozinho; nada de "não existe mais")
    const l90 = page.locator(`#err-body tr[data-err-linha]`).filter({ has: page.locator(`.code[title="${F90}"]`) });
    chk(await l90.count() === 1 && /fora do painel/.test(await l90.first().textContent()) && !/não existe mais/.test(await l90.first().textContent())
        && !/título ilegível/.test(await page.textContent('#err-body')), 'folha retirada: fica só o problema da retirada (o outro fechou sozinho)');
    // no celular, sem rolagem lateral
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300);
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular, a lista não cria rolagem lateral');
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
