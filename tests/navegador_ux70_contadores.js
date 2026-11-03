// UX-70 no navegador de verdade (Playwright + Chromium): o número do menu é o da tela que ele abre, e o menu diz o que conta.
//  - Material novo: o número do menu = a aba "Precisam de você" (antes 16 × 17: o menu não contava o lote parado com erro nem os de aprovar/publicar).
//  - Problemas: o número do menu = a aba "Abertos"; o resumo diz qual é qual ("N pedem ação… Contando os avisos, são N abertos no total").
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux70.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux70.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8972)
//   CAMP_DB_PATH=/tmp/ux70.db CAMP_BASE=http://127.0.0.1:8972 node tests/navegador_ux70_contadores.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8972', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// um lote parado com erro do CAMP Vision (depende de uma pessoa, mas não é "importar/conferir") e avisos (que não pedem ação)
py(`
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, resultado) VALUES ('Lote parado UX-70','F002-P0002','/ux70','erro',?)", (json.dumps({"erro": "falha de disco/rede ao copiar"}),))
for k in range(3):
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('aviso','outro','revisao','F023-P0011',?, 'operador@camp.arq.br')", ('aviso UX-70 %d' % k,))
con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('corrigir','metadado','operador','F023-P0011','corrigir UX-70','operador@camp.arq.br')")
`);

(async () => {
  const browser = await chromium.launch(process.env.CHROME || require('fs').existsSync(CHROME) ? { executablePath: CHROME } : {});
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/previa$/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const badge = async id => +((await page.textContent('#' + id)) || '0').replace(/\D/g, '') || 0;
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.goto(BASE + '/#filas');
    await page.waitForSelector('#fila-chips [data-fila-filtro="gente"]', { timeout: 15000 }); await page.waitForTimeout(800);
    const aba = +(await page.textContent('#fila-chips [data-fila-filtro="gente"] b'));
    const menu = await badge('n-filas');
    chk(aba > 0 && menu === aba, `Material novo: menu (${menu}) = aba "Precisam de você" (${aba})`);
    chk(/Precisam de você/.test(await page.getAttribute('#nav button[data-v="filas"]', 'title') || ''), 'o menu Material novo diz o que conta (dica)');
    await page.goto(BASE + '/#erros');
    await page.waitForSelector('#err-abas [data-err-sit="pedem_acao"] b', { timeout: 15000 }); await page.waitForTimeout(800);
    const abertos = +(await page.textContent('#err-abas [data-err-sit="pedem_acao"] b')).replace(/\D/g, '');
    chk(await badge('n-err') === abertos, `Problemas: menu (${await badge('n-err')}) = aba Abertos (${abertos})`);
    chk(/Abertos/.test(await page.getAttribute('#nav button[data-v="erros"]', 'title') || ''), 'o menu Problemas diz o que conta (dica)');
    const resumo = await page.textContent('#err-diagnostico');
    chk(new RegExp(`^\\s*${abertos} pedem ação: é o número do menu Problemas`).test(resumo.replace(/^[\s\S]*?(\d+ pedem ação)/, '$1')) && /Contando os \d+ avisos, são \d+ abertos no total/.test(resumo),
        'o resumo diz qual número é o do menu e qual conta os avisos: ' + resumo.replace(/\s+/g, ' ').slice(0, 160));
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
