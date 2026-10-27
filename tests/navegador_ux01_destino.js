// UX-01 (26/10, P0) no navegador de verdade: lote cuja pasta não parece do projeto fica em "Verificar destino".
// Prova: na Fila o lote suspeito não tem "Importar folhas" e sim "Verificar destino" (etiqueta âmbar com o porquê); "Importar todas (N)"
// não conta os suspeitos e diz quantos ficaram para verificar; a tela mostra Pasta | Projeto lado a lado e a sugestão do mesmo fundo;
// o botão principal só acende depois da escolha; sem justificativa não grava; "É deste projeto" grava no Histórico e o lote volta a ter
// "Importar folhas"; no projeto, o Próximo passo também mostra "Verificar destino"; no celular não há rolagem lateral; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux01.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux01.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8941)
//   CAMP_DB_PATH=/tmp/ux01.db CAMP_BASE=http://127.0.0.1:8941 node tests/navegador_ux01_destino.js
const { execFileSync } = require('child_process');
const path = require('path'), os = require('os'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8941', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// fundo F071 com 4 projetos; 2 lotes do CAMP Vision suspeitos (Marambaia em "Cia. Sto Amaro"; "P0001" em "Casa X") e 2 compatíveis
const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'ux01_nav_'));
const fix = fs.readFileSync(path.join(__dirname, 'fixtures/campvision/lote_normal/catalogacao/pacote_tainacan.json'), 'utf-8');
const pasta = P => { const d = path.join(raiz, P); fs.mkdirSync(path.join(d, 'catalogacao'), { recursive: true }); fs.writeFileSync(path.join(d, 'catalogacao/pacote_tainacan.json'), fix.split('F026-P0001').join(P).split('F026').join('F071')); return d; };
const lotes = [['F071-P0010', 'Edifício Marambaia - 1970-1971 (37 folhas)'], ['F071-P0030', 'P0001'], ['F071-P0002', 'RESIDENCIA TARUMA (3 folhas)'], ['F071-P0003', 'Edifício São Luís']];
py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F071','Fundo Destino','FDE',1)")
for n, t in ((10, 'Cia. Sto Amaro'), (95, 'Edifício Marambaia'), (30, 'Casa X'), (2, 'Residência Tarumã'), (3, 'Edifício São Luís')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F071',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,'F071',?,?,1972)", ('F071-P%04d' % n, n, t))
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F071-%' AND NOT EXISTS (SELECT 1 FROM item i WHERE i.lote_id=lista_processamento.id)")   # rodar de novo no mesmo banco
for P, nome, d in json.loads(sys.argv[2]):
    con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, resultado) VALUES (?,?,?,'revisao','{\\"origem\\": \\"campvision2\\"}')", (nome, P, d))
`, JSON.stringify(lotes.map(([P, n]) => [P, n, pasta(P)])));
const idDe = P => +py(`print(con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", (sys.argv[2],)).fetchone()[0])`, P);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?/.test(u);   // miniatura sem JPG no QNAP de teste: 404 esperado
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url()) && !/\/destino$/.test(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const linha = P => page.locator('#filas-body tr').filter({ hasText: P });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'operador@camp.arq.br'); await page.fill('#lg-senha', 'senha-operador-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { FILA_FILTRO = 'todas'; nav('filas'); });
    await page.waitForSelector('#filas-body tr[data-fase="importar"]', { timeout: 15000 }); await page.evaluate(() => { FILA_FILTRO = 'todas'; desenharFilas(); }); await page.waitForTimeout(300);

    const lm = linha('F071-P0010');
    chk((await lm.locator('[data-destino-lote]').count()) === 1 && (await lm.locator('[data-fila-acao="importar"]').count()) === 0, 'Fila: o lote suspeito tem "Verificar destino" no lugar de "Importar folhas"');
    chk(/verificar destino/.test(await lm.textContent()) && /Marambaia/.test(await lm.textContent()) && /Cia\. Sto Amaro/.test(await lm.textContent()), 'Fila: etiqueta "verificar destino" com o porquê (pasta × projeto)');
    chk((await linha('F071-P0030').locator('[data-destino-lote]').count()) === 1, 'Fila: a pasta só com o código ("P0001") também é Verificar destino');
    chk((await linha('F071-P0002').locator('[data-fila-acao="importar"]').count()) === 1 && (await linha('F071-P0003').locator('[data-fila-acao="importar"]').count()) === 1, 'Fila: os lotes com nome compatível (caixa, acento, contagem) importam sem passo extra');
    const resumo = await page.textContent('#fila-resumo');
    const nImp = await page.evaluate(() => FILAS_SRV.filter(l => l.fase === 'importar' && !l.destino_suspeito).length);
    chk(new RegExp(`Importar todas \\(${nImp}\\)`).test(resumo) && /2 lotes para verificar destino/.test(resumo), `"Importar todas (N)" não conta os suspeitos e diz quantos ficaram para verificar: "${resumo.replace(/\s+/g, ' ').trim()}"`);

    // ---- a tela Verificar destino ----
    await lm.locator('[data-destino-lote]').click();
    await page.waitForSelector('#d-body .dec-cartoes', { timeout: 10000 });
    const corpo = await page.textContent('#d-body');
    chk(/Pasta/.test(corpo) && /Edifício Marambaia - 1970-1971/.test(corpo) && /Projeto/.test(corpo) && /Cia\. Sto Amaro/.test(corpo), 'a tela mostra Pasta | Projeto lado a lado');
    chk((await page.locator('#d-body input[name="vd-esc"][value="mover:F071-P0095"]').count()) === 1 && /Mover para F071-P0095 \(sugerido\)/.test(corpo), 'a sugestão do mesmo fundo aparece: "Mover para F071-P0095 (sugerido)"');
    chk((await page.locator('#d-body input[name="vd-esc"][value="decisao"]').count()) === 1, 'a terceira opção é "Criar decisão"');
    chk(await page.isDisabled('#vd-ok'), 'o botão principal fica apagado antes da escolha');
    await page.check('#d-body input[name="vd-esc"][value="confirmar"]');
    chk(!(await page.isDisabled('#vd-ok')) && /é deste projeto/i.test(await page.textContent('#vd-ok')), 'escolher "É deste projeto" acende o botão com o que ele faz');
    await page.click('#vd-ok'); await page.waitForTimeout(400);
    chk(/justificativa/i.test(await page.textContent('#vd-res')), 'sem justificativa não grava (a tela pede)');
    await page.fill('#vd-just', 'Conferi o carimbo: é a Cia. Santo Amaro');
    await page.click('#vd-ok');
    await page.waitForFunction(() => { const b = document.querySelector('#vd-ok'); return !b || !b.offsetParent || !document.querySelector('.main.with-drawer'); }, null, { timeout: 10000 }); await page.waitForTimeout(800);
    const L = idDe('F071-P0010');
    const ev = py(`r = con.execute("SELECT ator, detalhe FROM evento WHERE entidade='projeto' AND codigo='F071-P0010' AND tipo='destino_confirmado'").fetchone()\nprint(json.dumps(list(r) if r else None))`);
    chk(/operador@camp\.arq\.br/.test(ev) && /carimbo/.test(ev), 'a confirmação fica no Histórico com o autor e a justificativa: ' + ev.slice(0, 120));
    await page.evaluate(() => { FILA_FILTRO = 'todas'; carregarFilas(); }); await page.waitForTimeout(800);
    chk((await linha('F071-P0010').locator('[data-fila-acao="importar"]').count()) === 1, 'depois da confirmação, o lote volta a ter "Importar folhas" (lote ' + L + ')');

    // ---- no projeto: o Próximo passo também diz Verificar destino ----
    await page.evaluate(() => nav('projeto/F071-P0030'));
    await page.waitForSelector('#v-projeto [data-destino-lote]', { timeout: 15000 });
    chk((await page.locator('#v-projeto [data-pp="importar"]').count()) === 0, 'na página do projeto com a pasta "P0001": nenhum botão Importar, e o botão "Verificar destino"');

    // ---- celular ----
    await page.setViewportSize({ width: 390, height: 800 });
    await page.locator('#v-projeto [data-destino-lote]').first().click(); await page.waitForSelector('#d-body .dec-cartoes', { timeout: 10000 }); await page.waitForTimeout(300);
    const lateral = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    chk(lateral <= 1, 'no celular a tela Verificar destino não tem rolagem lateral (' + lateral + ' px)');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  fs.rmSync(raiz, { recursive: true, force: true });
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
