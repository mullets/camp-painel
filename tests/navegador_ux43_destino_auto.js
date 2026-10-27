// UX-43 (27/10) no navegador de verdade: "Verificar destino" resolvido pelo painel.
// Prova: em simular (padrão) cada lote em "Verificar destino" diz "O painel faria: mover para … / criar … / deixar para uma pessoa" e NADA muda;
// o operador vê a prévia mas não tem "Aplicar" nem o interruptor; a tela Verificar destino mostra "O painel faria"; o admin aperta
// "Aplicar estas N decisões" (confirma, roda como tarefa) e o lote passa a "movendo" (o projeto criado aparece em "Projetos criados pelo painel");
// "Desfazer" volta o lote para Verificar destino; o interruptor passa o modo para "Aplicar sozinho"; nenhum erro no console; celular sem rolagem lateral.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux43.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux43.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8991)
//   CAMP_DB_PATH=/tmp/ux43.db CAMP_BASE=http://127.0.0.1:8991 node tests/navegador_ux43_destino_auto.js
const { execFileSync } = require('child_process');
const path = require('path'), os = require('os'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8991', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// fundo F074: Marambaia caiu em "Cia. Sto Amaro" (o painel moveria para F074-P0095), "Edifício Residêncial com Garagem" caiu em "Clube Ipê"
// (nenhum projeto combina: o painel criaria o projeto) e "P0001" (só o código: fica para uma pessoa)
const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'ux43_nav_'));
const fix = fs.readFileSync(path.join(__dirname, 'fixtures/campvision/lote_normal/catalogacao/pacote_tainacan.json'), 'utf-8');
const pasta = P => { const d = path.join(raiz, P); fs.mkdirSync(path.join(d, 'catalogacao'), { recursive: true }); fs.writeFileSync(path.join(d, 'catalogacao/pacote_tainacan.json'), fix.split('F026-P0001').join(P).split('F026').join('F074')); return d; };
const lotes = [['F074-P0010', 'Edifício Marambaia - 1970-1971 (37 folhas)'], ['F074-P0006', 'Edifício Residêncial com Garagem'], ['F074-P0030', 'P0001']];
py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F074','Fundo Destino Auto','FDA',1)")
for n, t in ((10, 'Cia. Sto Amaro'), (95, 'Edifício Marambaia'), (6, 'Clube Ipê'), (30, 'Casa X')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F074',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,'F074',?,?,1972)", ('F074-P%04d' % n, n, t))
for P, nome, d in json.loads(sys.argv[2]):
    con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, resultado) VALUES (?,?,?,'revisao','{\\"origem\\": \\"campvision2\\"}')", (nome, P, d))
`, JSON.stringify(lotes.map(([P, n]) => [P, n, pasta(P)])));
const idDe = P => +py(`print(con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", (sys.argv[2],)).fetchone()[0])`, P);
const foto = () => py(`print(json.dumps([con.execute("SELECT COUNT(*) FROM projeto").fetchone()[0], con.execute("SELECT COUNT(*) FROM destino_auto").fetchone()[0], [r[0] for r in con.execute("SELECT projeto_codigo FROM lista_processamento ORDER BY id")]]))`);
const proximo = +py(`print(max(r[0] for r in con.execute("SELECT numero FROM numero_p WHERE fundo_codigo='F074'")) + 1)`);
const novo = 'F074-P' + String(proximo).padStart(4, '0');

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?/.test(u);
  const abrir = async (email, senha) => {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
    page.on('pageerror', e => erros.push('pageerror: ' + e.message));
    page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { FILA_FILTRO = 'todas'; nav('filas'); });
    await page.waitForSelector('#filas-body tr[data-fase="importar"]', { timeout: 15000 }); await page.evaluate(() => { FILA_FILTRO = 'todas'; desenharFilas(); });
    await page.waitForSelector('#da-painel', { timeout: 15000 }); await page.waitForTimeout(300);
    return page;
  };
  try {
    const antes = foto();
    // ---------------- operador, simular ----------------
    const op = await abrir('operador@camp.arq.br', 'senha-operador-123');
    const linha = (page, P) => page.locator('#filas-body tr').filter({ hasText: P });
    const tM = await linha(op, 'F074-P0010').textContent(), tG = await linha(op, 'F074-P0006').textContent();
    chk(/O painel faria: mover para F074-P0095 “Edifício Marambaia”/.test(tM), 'Fila (simular): o lote Marambaia diz "O painel faria: mover para F074-P0095"');
    chk(new RegExp(`O painel faria: criar ${novo} “Edifício Residencial com Garagem”`).test(tG), `Fila (simular): o lote "Residêncial com Garagem" diz "O painel faria: criar ${novo} “Edifício Residencial com Garagem”"`);
    chk(/O painel faria: deixar para uma pessoa: a pasta só tem o código/.test(await linha(op, 'F074-P0030').textContent()), 'Fila (simular): "P0001" fica para uma pessoa, com o motivo');
    const quadro = await op.textContent('#da-painel');
    chk(/Verificar destino pelo painel/.test(quadro) && /Modo: Simular/.test(quadro) && /O painel faria \(\d+\)/.test(quadro), 'quadro "Verificar destino pelo painel" com o modo Simular e a prévia');
    chk((await op.locator('#da-painel [data-da-aplicar]').count()) === 0 && (await op.locator('#da-painel [data-da-modo]').count()) === 0, 'o operador vê a prévia mas não tem "Aplicar" nem o interruptor');
    await linha(op, 'F074-P0010').locator('[data-destino-lote]').click();
    await op.waitForSelector('#d-body .dec-cartoes', { timeout: 10000 });
    chk(/O painel faria: mover para F074-P0095/.test(await op.textContent('#d-body')) && /simulação: nada mudou/.test(await op.textContent('#d-body')), 'a tela Verificar destino mostra "O painel faria" (simulação: nada mudou)');
    chk(foto() === antes, 'simular não mudou nada no banco');
    await op.context().close();

    // ---------------- admin: Aplicar estas N decisões ----------------
    const ad = await abrir('rafael@camp.arq.br', 'senha-bem-longa-123');
    const bt = ad.locator('#da-painel [data-da-aplicar]');
    chk((await bt.count()) === 1 && /Aplicar estas \d+ decis(ão|ões)/.test(await bt.textContent()), 'o admin tem "Aplicar estas N decisões": ' + ((await bt.count()) ? (await bt.textContent()) : '—'));
    await bt.click();
    await ad.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    await ad.click('#conf-ov [data-conf="sim"]');
    const L = idDe('F074-P0010');
    let feito = false;
    for (let i = 0; i < 40 && !feito; i++) { await ad.waitForTimeout(500); feito = py(`print(con.execute("SELECT COUNT(*) FROM destino_auto WHERE lote_id=?", (int(sys.argv[2]),)).fetchone()[0])`, String(L)) === '1'; }
    chk(feito, 'Aplicar: o painel gravou a decisão do lote Marambaia (tarefa em segundo plano)');
    chk(py(`print(con.execute("SELECT titulo || '|' || origem FROM projeto WHERE codigo=?", (sys.argv[2],)).fetchone()[0])`, novo) === 'Edifício Residencial com Garagem|automatico', `Aplicar: o painel criou ${novo} “Edifício Residencial com Garagem” (origem automatico)`);
    chk(py(`print(con.execute("SELECT projeto_codigo FROM lista_processamento WHERE id=?", (int(sys.argv[2]),)).fetchone()[0])`, String(L)) === 'F074-P0010', 'o lote continua no projeto antigo até o CAMP Vision reorganizar a pasta');
    await ad.evaluate(() => { FILA_FILTRO = 'todas'; carregarFilas(); }); await ad.waitForTimeout(1200);
    const tM2 = await linha(ad, 'F074-P0010').textContent();
    chk(/movendo/.test(tM2) && /movendo para F074-P0095/.test(tM2) && /CAMP Vision vai reorganizar a pasta/.test(tM2), 'Fila: o lote fica "movendo para F074-P0095 … o CAMP Vision vai reorganizar a pasta"');
    const q2 = await ad.textContent('#da-painel');
    chk(/O que o painel fez \(\d+\)/.test(q2) && /Projetos criados pelo painel \(1\)/.test(q2) && /revise o título/.test(q2), 'o quadro mostra "O que o painel fez" e "Projetos criados pelo painel (1)" com "revise o título"');
    // ---------------- Desfazer ----------------
    await ad.locator('#da-painel details.da-feitas > summary').click();
    const linhaG = ad.locator('#da-painel .da-feitas li').filter({ hasText: novo });
    await linhaG.locator('[data-da-desfazer]').click();
    await ad.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    await ad.click('#conf-ov [data-conf="sim"]'); await ad.waitForTimeout(1500);
    const G = idDe('F074-P0006');
    chk(py(`print(con.execute("SELECT estado FROM destino_auto WHERE lote_id=?", (int(sys.argv[2]),)).fetchone()[0])`, String(G)) === 'desfeito'
        && py(`print(con.execute("SELECT descartado_em IS NOT NULL FROM projeto WHERE codigo=?", (sys.argv[2],)).fetchone()[0])`, novo) === '1', `Desfazer: a decisão fica desfeita e o projeto criado (vazio) ${novo} é descartado`);
    await ad.evaluate(() => { FILA_FILTRO = 'todas'; carregarFilas(); }); await ad.waitForTimeout(1200);
    const tG2 = await linha(ad, 'F074-P0006').textContent();
    chk(/verificar destino/.test(tG2) && !/O painel faria/.test(tG2), 'depois do Desfazer o lote volta a "verificar destino" para uma pessoa (o painel não decide de novo)');
    // ---------------- interruptor ----------------
    await ad.click('#da-painel [data-da-modo="aplicar"]');
    await ad.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    await ad.click('#conf-ov [data-conf="sim"]'); await ad.waitForTimeout(1200);
    chk(py(`print(con.execute("SELECT valor FROM configuracao WHERE chave='destino.automatico'").fetchone()[0])`) === 'aplicar' && /Modo: Aplicar sozinho/.test(await ad.textContent('#da-painel')), 'o interruptor passa o modo para "Aplicar sozinho" (com confirmação)');
    await ad.click('#da-painel [data-da-modo="simular"]'); await ad.waitForTimeout(1000);
    chk(py(`print(con.execute("SELECT valor FROM configuracao WHERE chave='destino.automatico'").fetchone()[0])`) === 'simular', '... e volta para Simular');
    // ---------------- celular ----------------
    await ad.setViewportSize({ width: 390, height: 800 }); await ad.waitForTimeout(400);
    const lateral = await ad.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    chk(lateral <= 1, 'no celular o quadro não cria rolagem lateral (' + lateral + ' px)');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  fs.rmSync(raiz, { recursive: true, force: true });
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
