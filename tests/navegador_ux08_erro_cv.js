// UX-08 no navegador: o erro do CAMP Vision na Fila (Material novo) em linguagem de gente.
// Prova: lote parado só por aviso [Minor] do exiftool diz "4 imagens têm o nome do autor longo demais no EXIF; ele foi cortado. Não impede publicar."
// e guarda a mensagem crua em "Ver detalhes técnicos" (fechado); "EXIF conferido em 6 de 48" diz quantos faltaram e, quando o CAMP Vision manda a
// lista, mostra os arquivos com o motivo; cada linha com erro tem UM botão azul, "Ler de novo esta pasta", e o "Tentar de novo" é secundário e
// explica no tooltip quando usar; a gaveta do projeto parado usa o mesmo texto e o mesmo rótulo; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta exclusiva, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux08/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux08/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8949)
//   CAMP_DB_PATH=/tmp/ux08/x.db CAMP_BASE=http://127.0.0.1:8949 node tests/navegador_ux08_erro_cv.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8949', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

py(`
minor = "; ".join("F002-P0001-1975-S01-D0000%d.tif Warning: [Minor] IPTC:By-line exceeds length limit (truncated)" % i for i in range(1, 5))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, resultado) VALUES ('L-minor','F002-P0001','/tmp/ux08-nao-existe-a','erro',?)", (json.dumps({"erro": minor}),))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, status_json) VALUES ('L-exif','F002-P0002','/tmp/ux08-nao-existe-b','erro',?)",
            (json.dumps({"status": "erro", "mensagem": "EXIF conferido em 46 de 48 arquivos", "exif_faltando": [{"arquivo": "F002-P0002-1977-S01-D00007.tif", "motivo": "arquivo travado pela estação"}, "F002-P0002-1977-S01-D00009.tif"]}),))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { FILA_FILTRO = 'todas'; nav('filas'); });
    await page.waitForSelector('#filas-body tr[data-nav="projeto/F002-P0001"]', { timeout: 15000 }); await page.waitForTimeout(400);

    const lm = page.locator('#filas-body tr[data-nav="projeto/F002-P0001"]');
    const tm = await lm.textContent();
    chk(/4 imagens têm o nome do autor longo demais no EXIF; ele foi cortado\. Não impede publicar\./.test(tm), 'Fila: aviso [Minor] em linguagem de gente, contando as imagens: "' + tm.replace(/\s+/g, ' ').slice(0, 220) + '"');
    const det = lm.locator('details.ux08-tecnico');
    chk(await det.count() === 1 && /Ver detalhes técnicos/.test(await det.locator('summary').textContent()) && !(await det.evaluate(d => d.open)) && /IPTC:By-line exceeds length limit/.test(await det.textContent()), 'Fila: a mensagem crua do exiftool fica em "Ver detalhes técnicos", fechado');
    await det.locator('summary').click(); await page.waitForTimeout(300);
    chk(await det.evaluate(d => d.open) && /^#?filas/.test(await page.evaluate(() => location.hash.replace(/^#/, ''))), 'clicar em "Ver detalhes técnicos" abre o texto e não leva para o projeto (a linha inteira abre o projeto)');
    const azuis = await lm.locator('button.pri').allTextContents();
    chk(azuis.length === 1 && azuis[0] === 'Ler de novo esta pasta', 'Fila: UM botão azul, com o efeito no rótulo: ' + JSON.stringify(azuis));
    const tentar = lm.locator('button[data-fila-acao="retomar"]');
    chk(await tentar.count() === 1 && !/\bpri\b/.test(await tentar.getAttribute('class')) && /Use só quando o erro foi passageiro/.test(await tentar.getAttribute('title') || ''), '"Tentar de novo" é secundário e o tooltip diz quando usar');
    chk(/inteira de novo/.test(await lm.locator('button.pri').getAttribute('title') || ''), '"Ler de novo esta pasta" explica no tooltip o que faz');

    const le = page.locator('#filas-body tr[data-nav="projeto/F002-P0002"]');
    const te = await le.textContent();
    chk(/de só 46 de 48 arquivos; 2 ficaram sem conferir\./.test(te), 'Fila: "EXIF conferido em 46 de 48" diz quantos faltaram: "' + te.replace(/\s+/g, ' ').slice(0, 200) + '"');
    const arq = le.locator('details.ux08-arquivos');
    chk(await arq.count() === 1 && /F002-P0002-1977-S01-D00007\.tif — arquivo travado pela estação/.test(await arq.textContent()) && /D00009\.tif/.test(await arq.textContent()), 'Fila: a lista dos arquivos que faltaram, com o motivo');

    // a gaveta do projeto parado: o mesmo texto, um só "Ler de novo esta pasta"
    await page.evaluate(() => nav('projeto/F002-P0001'));
    await page.waitForSelector('#pj-status [data-pjc-gav="folhas"]', { timeout: 15000 });
    await page.click('#pj-status [data-pjc-gav="folhas"]');
    await page.waitForSelector('#pj-gav-erro .aviso-bloqueio', { timeout: 10000 });
    const g = await page.textContent('#pj-gav-erro');
    chk(/4 imagens têm o nome do autor longo demais no EXIF/.test(g) && /Peça para ler de novo esta pasta/.test(g) && !/Ele disse: “F002/.test(g), 'gaveta: o mesmo texto para gente, sem a mensagem crua solta: "' + g.replace(/\s+/g, ' ').slice(0, 260) + '"');
    const rl = await page.locator('#pd [data-releitura-projeto]').allTextContents();
    chk(rl.length === 1 && rl[0] === 'Ler de novo esta pasta', 'gaveta: um só "Ler de novo esta pasta" na página: ' + JSON.stringify(rl));
    chk(!erros.length, 'nenhum erro no console: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e.stack || e.message)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
