// UX-39 no navegador: "Dispensar este lote" também para a Leitura interrompida. O item do print do Rafael no Precisa de você:
// "Leitura interrompida: Residência Sr. Luiz Marcelo Sales · lote de 19/10 · F009-P0092 · o CAMP Vision começou a ler e não dá sinal deste
// lote há mais de 2 h · parado há 8 dias · releitura pedida agora: esperando o CAMP Vision", com "Ignorar ▾" e "Ver na Fila"
// ("já mandei umas 10x ler novamente e nada muda").
// Prova: o Ignorar ▾ desse item tem "Dispensar este lote (para todos)"; confirmação com motivo opcional; o item some; o toast tem "Desfazer"
// (que traz de volta); em Material novo a linha da leitura interrompida tem "Dispensar este lote" secundário (depois de "Ler de novo", ou
// sozinho quando a releitura já foi pedida); o lote dispensado sai de "Precisam de você" e fica em "Todas" com o chip "dispensado", sem
// "parado há", com "Voltar a mostrar"; o leitor não vê os botões; o Histórico diz "leitura interrompida"; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta exclusiva, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux39/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux39/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8996)
//   CAMP_DB_PATH=/tmp/ux39/x.db CAMP_BASE=http://127.0.0.1:8996 node tests/navegador_ux39_dispensar_interrompida.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8996', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

py(`
for f, n, t in (("F009", 92, "Residência Sr. Luiz Marcelo Sales"), ("F016", 31, "Casa Ux Trinta e Um")):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (f, n))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,?,?,?,1978)", ("%s-P%04d" % (f, n), f, n, t))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, criado_em, etapa_desde) VALUES ('L-sales','F009-P0092','/tmp/ux39-nao-existe-a','processando','2026-10-19 12:00:00', datetime('now','-8 days'))")
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, criado_em, etapa_desde) VALUES ('L-ux31','F016-P0031','/tmp/ux39-nao-existe-b','processando','2026-10-20 12:00:00', datetime('now','-3 days'))")
con.execute("INSERT INTO pedido_releitura (projeto_codigo, pedido_por) VALUES ('F009-P0092','operador@camp.arq.br')")
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
const SALES = '#filas-body tr[data-nav="projeto/F009-P0092"]', UX31 = '#filas-body tr[data-nav="projeto/F016-P0031"]';
const ITEM = 'Leitura interrompida: Residência Sr. Luiz Marcelo Sales';
async function filas(page, filtro) {
  await page.evaluate(f => { if (rotaAtual().startsWith('filas')) { FILA_FILTRO = f; carregarFilas(); } else nav('filas/' + f); }, filtro);
  await page.waitForFunction(() => Array.isArray(FILAS_SRV) && FILAS_SRV.length && document.querySelector('#filas-body tr'), null, { timeout: 15000 });
  await page.waitForTimeout(500);
}
async function home(page) {
  await page.evaluate(() => nav('painel'));
  await page.waitForSelector('#ini-tarefas .ini-task', { timeout: 15000 }); await page.waitForTimeout(500);
}
const chipN = async (page, k) => +(await page.locator(`#fila-chips [data-fila-filtro="${k}"] b`).first().textContent());
const so = t => String(t || '').replace(/\s+/g, ' ');

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    // Precisa de você (Home): o item do print
    await home(op);
    const task = op.locator('#ini-tarefas .ini-task', { hasText: ITEM }).first();
    const tt = so(await task.textContent());
    chk(await task.count() === 1 && /não dá sinal deste lote há mais de 2 h/.test(tt) && /parado há 8 dias/.test(tt) && /releitura pedida agora: esperando o CAMP Vision/.test(tt) && /Ver na Fila/.test(tt),
      'Home: o item do print aparece ("parado há 8 dias", "releitura pedida agora", "Ver na Fila"): "' + tt.slice(0, 260) + '"');
    await task.locator('summary', { hasText: 'Ignorar' }).click();
    const opc = task.locator('[data-ini-dispensar]');
    chk(await opc.count() === 1 && (await opc.textContent()) === 'Dispensar este lote (para todos)', 'Ignorar ▾: "Dispensar este lote (para todos)"');
    await opc.click();
    await op.waitForSelector('#conf-ov', { timeout: 5000 });
    const conf = so(await op.textContent('#conf-ov'));
    chk(/Dispensar este lote\?/.test(conf) && /F009-P0092 · lote de 19\/10/.test(conf) && /para todo mundo\. Nada é apagado/.test(conf) && await op.locator('#conf-motivo').count() === 1,
      'confirmação curta: alvo, efeito e motivo opcional: "' + conf.slice(0, 260) + '"');
    await op.fill('#conf-motivo', 'já mandei ler de novo umas 10x e nada muda');
    await op.click('#conf-ov [data-conf="sim"]');
    await op.waitForFunction(t => !((document.getElementById('ini-tarefas') || {}).textContent || '').includes(t), ITEM, { timeout: 10000 });
    chk(true, 'Home: o item some depois de dispensar pelo Ignorar ▾');
    const toastTxt = await op.textContent('#toast');
    chk(/Lote dispensado/.test(toastTxt) && (await op.locator('#toast .toast-acao').textContent()) === 'Desfazer', 'toast com "Desfazer": "' + toastTxt + '"');
    await op.click('#toast .toast-acao');
    await op.waitForFunction(t => ((document.getElementById('ini-tarefas') || {}).textContent || '').includes(t), ITEM, { timeout: 10000 });
    chk(true, '"Desfazer" traz o item de volta ao Precisa de você');

    // Material novo: a linha da leitura interrompida
    await filas(op, 'gente');
    const n0 = await chipN(op, 'gente');
    const ls = op.locator(SALES), bs = await ls.locator('td.fila-acao button').allTextContents();
    chk(await ls.count() === 1 && /leitura interrompida/.test(so(await ls.textContent())) && JSON.stringify(bs) === '["Dispensar este lote"]' && await ls.locator('button.pri').count() === 0,
      'Material novo: com a releitura já pedida, a linha tem só "Dispensar este lote" (secundário): ' + JSON.stringify(bs));
    const lu = op.locator(UX31), bu = await lu.locator('td.fila-acao button').allTextContents();
    chk(JSON.stringify(bu) === '["Ler de novo","Dispensar este lote"]' && (await lu.locator('button.pri').allTextContents()).join() === 'Ler de novo',
      'Material novo: sem releitura pedida, "Ler de novo" (azul) e depois "Dispensar este lote" (secundário): ' + JSON.stringify(bu));
    await ls.locator('button[data-fila-dispensar]').click();
    await op.waitForSelector('#conf-ov', { timeout: 5000 }); await op.fill('#conf-motivo', 'já mandei ler de novo umas 10x e nada muda'); await op.click('#conf-ov [data-conf="sim"]');
    await op.waitForFunction(() => !document.querySelector('#filas-body tr[data-nav="projeto/F009-P0092"]'), null, { timeout: 10000 });
    await op.waitForTimeout(400);
    chk(await chipN(op, 'gente') === n0 - 1, `o lote sai de "Precisam de você": chip de ${n0} para ${await chipN(op, 'gente')}`);
    await filas(op, 'todas');
    const lt = op.locator(SALES), tlt = so(await lt.textContent());
    chk(await lt.count() === 1 && await lt.locator('[data-fila-dispensado]').count() === 1, 'em "Todas" o lote continua, com o chip "dispensado"');
    chk(/umas 10x/.test(await lt.locator('[data-fila-dispensado]').getAttribute('title') || ''), 'o chip diz quem, quando e o motivo no tooltip');
    chk(!/parado há/.test(tlt) && await lt.locator('.tag.a').count() === 0, 'sem o "parado há" no lote dispensado: "' + tlt.slice(0, 200) + '"');
    chk(JSON.stringify(await lt.locator('td.fila-acao button').allTextContents()) === '["Voltar a mostrar"]' && await lt.locator('button.pri').count() === 0, 'em "Todas": só "Voltar a mostrar", secundário');
    await home(op);
    chk(!(await op.textContent('#ini-tarefas')).includes(ITEM), 'Home: o lote dispensado não volta ao Precisa de você');
    const fr = await op.evaluate(() => [fraseEvento({ tipo: 'lote_dispensado', entidade: 'projeto', codigo: 'F009-P0092', ator: 'operador@camp.arq.br' }),
      resumoDetalhe(JSON.stringify({ identificador: 'lote de 19/10', estado: 'leitura_interrompida', erro_cv: null, motivo: 'umas 10x' }), 'lote_dispensado')]);
    chk(fr[0] === 'Operador dispensou um lote parado no CAMP Vision do projeto F009-P0092 (sai das listas para todos)' && fr[1] === 'Lote de 19/10 · leitura interrompida (motivo: umas 10x)',
      'Histórico: frase e detalhe em português: ' + JSON.stringify(fr));

    // leitor: não vê os botões
    const lei = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await filas(lei, 'todas');
    chk(await lei.locator('#filas-body [data-fila-dispensar], #filas-body [data-fila-mostrar]').count() === 0 && await lei.locator(SALES).count() === 1, 'leitor: vê o lote em Todas, sem "Dispensar" nem "Voltar a mostrar"');

    // Voltar a mostrar
    await filas(op, 'todas');
    await op.locator(SALES).locator('button[data-fila-mostrar]').click();
    await op.waitForFunction(() => { const r = document.querySelector('#filas-body tr[data-nav="projeto/F009-P0092"]'); return r && !r.querySelector('[data-fila-dispensado]'); }, null, { timeout: 10000 });
    chk(/voltou/.test(await op.textContent('#toast')) && await op.locator('#toast .toast-acao').count() === 1, '"Voltar a mostrar": o lote perde o chip e o toast tem "Desfazer"');
    await filas(op, 'gente');
    chk(await op.locator(SALES).count() === 1, 'de volta em "Precisam de você"');
    chk(!erros.length, 'nenhum erro no console: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e.stack || e.message)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
