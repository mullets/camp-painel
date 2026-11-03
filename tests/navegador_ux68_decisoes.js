// UX-68 (P2): "Decisões" com dois sentidos. A página Decisões dizia "0 esperando resposta" e o projeto F001-P0033 "Dados do projeto —
// 2 decisões pendentes": o cartão contava as diferenças entre o carimbo das folhas e o cadastro (calculadas, resolvidas no próprio projeto).
// Agora: no cartão elas são "a confirmar"; "decisão pendente" no projeto é só o que está na fila de Decisões (a mesma conta do menu),
// e a diferença que já virou decisão registrada não conta duas vezes. Playwright + Chromium, servidor PRÓPRIO (porta 8971).
// Uso:
//   CAMP_DB_PATH=/tmp/ux68.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux68.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8971)
//   CAMP_DB_PATH=/tmp/ux68.db CAMP_BASE=http://127.0.0.1:8971 node tests/navegador_ux68_decisoes.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8971', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F003-P9681';
py(`
con.execute("UPDATE decisao SET situacao='resolvida' WHERE situacao='pendente'")   # o banco semeado pode ter decisões: começa do zero
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9681)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano) VALUES ('${P}', 'F003', 9681, 'Teatro Municipal', 1975)")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('${P} - Teatro', '${P}', '/nao/existe/ux68', 'revisao')").lastrowid
for k in range(1, 4):
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, ano_folha) VALUES (?,?,?,?,?,?,'campvision',?,'conferida',1978)",
                ('${P}-1978-S01-D%05d' % k, '${P}', 'S01', k, 'Planta %d' % k, 'Planta', lid))
print(lid)
`);
const lote = py(`print(con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo='${P}'").fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa|\/miniatura|folhas-qnap\/arquivo|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const abrir = async () => { await page.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P);
    await page.waitForFunction(() => window.SL && SL.consenso && SL.cv && document.querySelector('#pj-cards .pjc[data-pjc="dados"]') && !/…/.test(document.querySelector('#pj-cards .pjc[data-pjc="dados"] .pjc-v').textContent), null, { timeout: 15000 });
    await page.waitForTimeout(1200) };
  const cartao = () => page.$eval('#pj-cards .pjc[data-pjc="dados"]', c => c.innerText.replace(/\s+/g, ' ').trim());
  const menuDec = async () => { await page.evaluate(() => atualizarPendencias()); await page.waitForTimeout(600); return page.$eval('#n-dec', e => e.hidden ? '' : e.textContent.trim()).catch(() => '') };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }

    // (1) só a diferença do carimbo (ano 1978 nas folhas × 1975 no cadastro), nenhuma decisão na fila
    await abrir();
    const c1 = await cartao(), m1 = await menuDec();
    chk(/1 a confirmar/.test(c1) && !/decis/i.test(c1), '(1) cartão Dados: "1 a confirmar", sem a palavra decisão: "' + c1 + '"');
    chk(m1 === '', '(1) o menu Decisões não tem número (nenhuma decisão na fila): "' + m1 + '"');
    const pend1 = await page.evaluate(() => JSON.stringify((pendenciasProjeto(window.PJ_D) || []).map(x => x.texto)));
    chk(/Confirmar 1 dado do projeto/.test(pend1) && !/decis/i.test(pend1), '(1) "O que falta": "Confirmar 1 dado do projeto", sem decisão: ' + pend1);

    // (2) o CAMP Vision registrou a mesma divergência do ano na fila de Decisões
    py(`
import json
ctx = {"projeto_codigo": "${P}", "projeto_titulo": "Teatro Municipal", "lote_id": ${lote}, "campo": "ano", "valor_cadastro": "1975", "valor_cv": "1978",
       "candidatos": [{"valor": "1975", "fontes": ["cadastro do painel"]}, {"valor": "1978", "fontes": ["CAMP Vision"]}]}
con.execute("INSERT INTO decisao (tipo, chave, fundo_codigo, titulo, contexto, origem) VALUES ('divergencia', 'divergencia:${P}:ano:1978', 'F003', 'Teatro Municipal', ?, 'campvision')", (json.dumps(ctx),))
`);
    await abrir();
    const c2 = await cartao(), m2 = await menuDec();
    chk(/1 decisão pendente/.test(c2) && /fila de Decisões/.test(c2) && !/a confirmar/.test(c2), '(2) a diferença que virou decisão conta UMA vez, como decisão: "' + c2 + '"');
    chk(m2 === '1', '(2) o menu Decisões diz 1, o mesmo número do projeto: "' + m2 + '"');
    const pend2 = await page.evaluate(() => JSON.stringify((pendenciasProjeto(window.PJ_D) || []).map(x => x.texto)));
    chk(/1 decisão pendente sobre este projeto/.test(pend2) && !/Confirmar 1 dado/.test(pend2), '(2) "O que falta": só "1 decisão pendente sobre este projeto": ' + pend2);
  } catch (e) { problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
