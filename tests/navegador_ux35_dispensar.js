// UX-35 no navegador: "Dispensar este lote" — os dois lotes parados com erro do CAMP Vision dos prints do Rafael (F026-P0009 CRASA, lote de 08/10,
// "67 de 68"; F016-P0024 Fazenda Fernando Millan, lote de 14/10, "6 de 48"), "parado há 7 dias".
// Prova: o botão é secundário, ao lado de "Tentar de novo" (um só azul); a confirmação diz o efeito; o lote sai de "Precisam de você" e do resumo
// "com problema"; o toast tem "Desfazer" (que traz o lote de volta); em "Todas" fica com o chip "dispensado", sem "parado há", e o botão
// "Voltar a mostrar"; no Precisa de você (Home) o Ignorar ▾ tem "Dispensar este lote (para todos)" e o item some; o leitor não vê nenhum
// dos botões; o Histórico tem a frase em português; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta exclusiva, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux35/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux35/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8980)
//   CAMP_DB_PATH=/tmp/ux35/x.db CAMP_BASE=http://127.0.0.1:8980 node tests/navegador_ux35_dispensar.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8980', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

py(`
for f, n, t in (("F026", 9, "CRASA, Sto. André"), ("F016", 24, "Fazenda Fernando Millan")):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (f, n))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,?,?,?,1978)", ("%s-P%04d" % (f, n), f, n, t))
st = lambda a, b: json.dumps({"status": "erro", "mensagem": "Aceite reprovado: EXIF conferido em %d de %d arquivos" % (a, b)})
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, status_json, criado_em) VALUES ('L-crasa','F026-P0009','/tmp/ux35-nao-existe-a','erro',?,'2026-10-08 12:00:00')", (st(67, 68),))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, status_json, criado_em) VALUES ('L-millan','F016-P0024','/tmp/ux35-nao-existe-b','erro',?,'2026-10-14 12:00:00')", (st(6, 48),))
con.execute("UPDATE lista_processamento SET etapa_desde=datetime('now','-7 days') WHERE projeto_codigo IN ('F026-P0009','F016-P0024')")
`);

async function entrar(browser, email, senha, erros) {
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return page;
}
const MILLAN = '#filas-body tr[data-nav="projeto/F016-P0024"]', CRASA = '#filas-body tr[data-nav="projeto/F026-P0009"]';
async function filas(page, filtro) {
  await page.evaluate(f => { if (rotaAtual().startsWith('filas')) { FILA_FILTRO = f; carregarFilas(); } else nav('filas/' + f); }, filtro);
  await page.waitForFunction(() => Array.isArray(FILAS_SRV) && FILAS_SRV.length && document.querySelector('#filas-body tr'), null, { timeout: 15000 });
  await page.waitForTimeout(500);
}
const chipN = async (page, k) => +(await page.locator(`#fila-chips [data-fila-filtro="${k}"] b`).first().textContent());

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await filas(op, 'gente');
    const n0 = await chipN(op, 'gente'), r0 = await op.textContent('#fila-resumo');
    chk(await op.locator(MILLAN).count() === 1 && await op.locator(CRASA).count() === 1, 'Precisam de você: os dois lotes com erro aparecem (como nos prints)');
    chk(/2 com problema/.test(r0), 'resumo antes: "2 com problema": "' + r0.replace(/\s+/g, ' ').slice(0, 120) + '"');
    const lm = op.locator(MILLAN);
    const bt = lm.locator('button[data-fila-dispensar]');
    chk(await bt.count() === 1 && (await bt.textContent()) === 'Dispensar este lote' && !/\bpri\b/.test(await bt.getAttribute('class')), '"Dispensar este lote" é secundário');
    const azuis = await lm.locator('button.pri').allTextContents();
    chk(azuis.length === 1 && azuis[0] === 'Ler de novo esta pasta', 'continua UM só azul na linha: ' + JSON.stringify(azuis));
    const ordem = await lm.locator('td.fila-acao button').allTextContents();
    chk(ordem.indexOf('Dispensar este lote') === ordem.indexOf('Tentar de novo') + 1, 'fica ao lado de "Tentar de novo": ' + JSON.stringify(ordem));

    await bt.click();
    await op.waitForSelector('#conf-ov', { timeout: 5000 });
    const conf = await op.textContent('#conf-ov');
    chk(/Dispensar este lote\?/.test(conf) && /O lote sai das listas e das contagens para todo mundo\. Nada é apagado; se o CAMP Vision ler a pasta de novo e o resultado mudar, ele volta\./.test(conf) && /F016-P0024 · lote de 14\/10/.test(conf),
      'confirmação curta diz o alvo e o efeito: "' + conf.replace(/\s+/g, ' ').slice(0, 260) + '"');
    await op.fill('#conf-motivo', 'o CAMP Vision não reescreve o status.json');
    await op.click('#conf-ov [data-conf="sim"]');
    await op.waitForFunction(() => !document.querySelector('#filas-body tr[data-nav="projeto/F016-P0024"]'), null, { timeout: 10000 });
    chk(true, 'o lote some de "Precisam de você" (para todos: a lista vem do servidor)');
    const toastTxt = await op.textContent('#toast');
    chk(/Lote dispensado/.test(toastTxt) && await op.locator('#toast .toast-acao').count() === 1 && (await op.locator('#toast .toast-acao').textContent()) === 'Desfazer', 'toast com "Desfazer": "' + toastTxt + '"');
    await op.waitForTimeout(400);
    chk(await chipN(op, 'gente') === n0 - 1, `chip "Precisam de você" desce de ${n0} para ${n0 - 1}: ${await chipN(op, 'gente')}`);
    chk(/1 com problema/.test(await op.textContent('#fila-resumo')), 'resumo depois: "1 com problema"');
    await op.click('#toast .toast-acao');
    await op.waitForSelector(MILLAN, { timeout: 10000 });
    chk(true, '"Desfazer" traz o lote de volta para a lista');
    await op.waitForTimeout(400);
    await op.locator(MILLAN).locator('button[data-fila-dispensar]').click();
    await op.waitForSelector('#conf-ov', { timeout: 5000 }); await op.fill('#conf-motivo', 'o CAMP Vision não reescreve o status.json'); await op.click('#conf-ov [data-conf="sim"]');
    await op.waitForFunction(() => !document.querySelector('#filas-body tr[data-nav="projeto/F016-P0024"]'), null, { timeout: 10000 });

    await filas(op, 'chegando');
    chk(await op.locator(MILLAN).count() === 0, 'não aparece em "Chegando"');
    await filas(op, 'todas');
    const lt = op.locator(MILLAN), tt = (await lt.textContent()).replace(/\s+/g, ' ');
    chk(await lt.count() === 1 && await lt.locator('[data-fila-dispensado]').count() === 1 && /dispensado/.test(tt), 'em "Todas" o lote continua, com o chip "dispensado"');
    chk(/o CAMP Vision não reescreve o status\.json/.test(await lt.locator('[data-fila-dispensado]').getAttribute('title') || ''), 'o chip diz quem, quando e o motivo no tooltip');
    chk(!/parado há/.test(tt) && await lt.locator('.tag.a').count() === 0, 'sem o "parado há" (UX-09) no lote dispensado: "' + tt.slice(0, 200) + '"');
    chk(await lt.locator('button[data-fila-mostrar]').count() === 1 && await lt.locator('button[data-fila-dispensar]').count() === 0 && await lt.locator('button.pri').count() === 0, 'em "Todas": só "Voltar a mostrar", secundário');
    chk(/parado há/.test((await op.locator(CRASA).textContent()).replace(/\s+/g, ' ')), 'o outro lote (não dispensado) continua com "parado há"');

    // Precisa de você (Home): o Ignorar ▾ do lote com erro tem "Dispensar este lote (para todos)"
    await op.evaluate(() => nav('painel'));
    await op.waitForSelector('#ini-tarefas [data-ini-grupo="problemas"]', { timeout: 15000 }); await op.waitForTimeout(400);
    const prob = (await op.textContent('#ini-tarefas [data-ini-grupo="problemas"]')).replace(/\s+/g, ' ');
    chk(/CRASA/.test(prob) && !/Fazenda Fernando Millan/.test(prob), 'Home: o lote dispensado saiu do "Com problema"; o outro continua: "' + prob.slice(0, 200) + '"');
    const task = op.locator('#ini-tarefas [data-ini-grupo="problemas"] .ini-task', { hasText: 'CRASA' });
    await task.locator('summary', { hasText: 'Ignorar' }).click();
    const opc = task.locator('[data-ini-dispensar]');
    chk(await opc.count() === 1 && (await opc.textContent()) === 'Dispensar este lote (para todos)', 'Ignorar ▾: "Dispensar este lote (para todos)"');
    await opc.click();
    await op.waitForSelector('#conf-ov', { timeout: 5000 }); await op.click('#conf-ov [data-conf="sim"]');
    await op.waitForFunction(() => !/CRASA/.test((document.getElementById('ini-tarefas') || {}).textContent || ''), null, { timeout: 10000 });
    chk(true, 'Home: o item some depois de dispensar pelo Ignorar ▾');
    chk(await op.evaluate(() => fraseEvento({ tipo: 'lote_dispensado', entidade: 'projeto', codigo: 'F016-P0024', ator: 'operador@camp.arq.br' })) === 'Operador dispensou um lote com erro do CAMP Vision do projeto F016-P0024 (sai das listas para todos)',
      'Histórico: frase em português: "' + await op.evaluate(() => fraseEvento({ tipo: 'lote_dispensado', entidade: 'projeto', codigo: 'F016-P0024', ator: 'operador@camp.arq.br' })) + '"');

    // leitor: não vê os botões
    const lei = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await filas(lei, 'todas');
    chk(await lei.locator('#filas-body [data-fila-dispensar], #filas-body [data-fila-mostrar]').count() === 0 && await lei.locator(MILLAN).count() === 1, 'leitor: vê o lote em Todas, sem "Dispensar" nem "Voltar a mostrar"');

    // Voltar a mostrar
    await filas(op, 'todas');
    await op.locator(MILLAN).locator('button[data-fila-mostrar]').click();
    await op.waitForFunction(() => { const r = document.querySelector('#filas-body tr[data-nav="projeto/F016-P0024"]'); return r && !r.querySelector('[data-fila-dispensado]'); }, null, { timeout: 10000 });
    chk(/voltou/.test(await op.textContent('#toast')) && await op.locator('#toast .toast-acao').count() === 1, '"Voltar a mostrar": o lote perde o chip e o toast tem "Desfazer"');
    await filas(op, 'gente');
    chk(await op.locator(MILLAN).count() === 1 && await op.locator(CRASA).count() === 0, 'de volta em "Precisam de você" (o CRASA continua dispensado)');
    chk(!erros.length, 'nenhum erro no console: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e.stack || e.message)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
