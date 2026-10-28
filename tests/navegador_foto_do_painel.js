// 28/10 (Rafael: "ao entrar em um item de slide muda o modo que edito, legendo e etc, não tem as ferramentas de espelhar, girar, cortar"):
// a foto enviada pelo painel (faixa D90001+, SEM lote) abre na mesma revisão das outras folhas, com Virar/Espelhar/Recortar e os campos.
// Prova: na página do projeto, a miniatura da foto do painel abre a gaveta "Revisar folha" (não vai para #item/…), com as ferramentas de
// imagem; "Virar à direita" grava o giro; "Está certo" confere; a folha de lote continua igual; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO): CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py; uvicorn na porta 89xx; CAMP_BASE=… node tests/navegador_foto_do_painel.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8996', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH'); process.exit(2); }
const PASTA = path.join(path.dirname(DB), 'folhas_enviadas', 'F026-P0097'); fs.mkdirSync(PASTA, { recursive: true });   // a pasta das folhas enviadas (padrão: ao lado do banco)
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PASTA], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0097', FOTO = `${P}-1976-S05-D90001`, LOTE1 = `${P}-1976-S01-D00001`;
py(`
from pathlib import Path
from PIL import Image
raiz = Path(sys.argv[2])
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 97)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',97,'Residência Slides',1976,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote slides','${P}','/x/slides','revisao')").lastrowid
for cod, lote, orig in (("${LOTE1}", lid, 'campvision'), ("${FOTO}", None, 'manual')):
    jpg = raiz / (cod + ".jpg"); Image.new("RGB", (400, 300), (180, 120, 90)).save(jpg, "JPEG")
    pend = {"previa": "@jpg", "bloqueios": [], "sinais": [], "ressalvas": []}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,origem,lote_id,status_site,pendencias,revisao,arquivo_jpg) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', cod.split('-')[3], int(cod[-5:]), 'Slide', 'Slide', orig, lote, 'nao_publicado', json.dumps(pend), 'pendente', str(jpg)))
`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1400, height: 900 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  const temThumb = await pg.waitForSelector(`.thumb[data-rev-abrir="${FOTO}"]`, { timeout: 15000 }).then(() => true).catch(() => false);
  chk(temThumb, 'a miniatura da foto do painel (D90001, sem lote) abre a revisão (data-rev-abrir), não a página #item');
  if (temThumb) {
    await pg.waitForTimeout(1200);                       // a página termina de montar (cartões, ajuda) antes do clique
    await pg.click(`.thumb[data-rev-abrir="${FOTO}"]`);
    const abriu = await pg.waitForFunction(() => { const b = document.getElementById('d-body'); const t = b ? b.innerText : ''; return /Virar à esquerda/.test(t) && /Espelhar/.test(t) && /Recortar e alinhar/.test(t); }, null, { timeout: 10000 }).then(() => true).catch(() => false);
    chk(abriu, 'a revisão da foto tem Virar à esquerda/direita, Espelhar e Recortar e alinhar');
    chk(!/#item\//.test(pg.url()), 'continua na página do projeto (não foi para #item/…)', pg.url());
    const bt = await pg.$('#d-body button:has-text("Virar à direita")');
    if (bt) { await bt.click(); await pg.waitForTimeout(1500); }
    const giro = py(`print(con.execute("SELECT giro_manual FROM item WHERE codigo='${FOTO}'").fetchone()[0])`);
    chk(giro === '90', 'Virar à direita grava o giro da foto do painel', giro);
  }
  chk(await pg.$(`.thumb[data-rev-abrir="${LOTE1}"]`) !== null, 'a folha de lote continua abrindo a revisão como antes');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `${problemas.length} FALHA(S)` : 'TUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
