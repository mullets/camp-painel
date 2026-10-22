// 21/10 (Rafa: "e se eu quiser subir algo direto pelo admin na pagina de projeto?" → "sim, sobe"), no navegador de verdade:
//  - "+ Adicionar folhas" na página do projeto abre o formulário; escolher 3 arquivos (JPEG, PNG e um que não é imagem) e enviar;
//  - cada imagem vira uma folha (D90001+) com a lista do que foi; o arquivo inválido diz por quê; as folhas aparecem com imagem no projeto;
//  - nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx; a pasta das folhas enviadas também própria):
//   CAMP_DB_PATH=/tmp/en.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/en.db CAMP_FOLHAS_ENVIADAS_DIR=/tmp/en_folhas CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8968)
//   CAMP_DB_PATH=/tmp/en.db CAMP_BASE=http://127.0.0.1:8968 node tests/navegador_enviar.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8968', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0097';
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',97)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',97,'Casa enviada',1980,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
`);
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'env_'));
execFileSync('python3', ['-c', `from PIL import Image\nImage.new('RGB',(320,240),(180,40,40)).save('${dir}/fachada_sul.jpg','JPEG')\nImage.new('RGB',(240,320),(40,90,200)).save('${dir}/slide 12.png','PNG')\nopen('${dir}/notas.txt','w').write('não é imagem')`]);
const espera = async (f, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 200)); } return false; };
const um = q => py(`print((con.execute("""${q}""").fetchone() or [''])[0])`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  await pg.waitForSelector('#pd .pj-env-linha [data-enviar-folhas]', { timeout: 15000 }).catch(() => {});
  chk(!!(await pg.$('#pd .pj-env-linha [data-enviar-folhas]')), 'projeto sem folhas: o botão "+ Adicionar folhas" aparece');
  await pg.click('#pd .pj-env-linha [data-enviar-folhas]'); await pg.waitForSelector('#env-arqs', { timeout: 5000 });
  chk(await pg.$eval('#env-go', b => b.disabled), 'sem arquivo escolhido, "Enviar" fica desligado');
  await pg.setInputFiles('#env-arqs', [`${dir}/fachada_sul.jpg`, `${dir}/slide 12.png`, `${dir}/notas.txt`]);
  chk(/Enviar 3 imagens/.test(await pg.textContent('#env-go')), 'o botão diz quantas vão');
  await pg.click('#env-go');
  chk(await espera(async () => /2 folhas novas/.test(await pg.textContent('#env-res').catch(() => ''))), 'resultado: 2 folhas novas', await pg.textContent('#env-res').catch(() => ''));
  const lista = await pg.textContent('#env-lista').catch(() => '');
  chk(/fachada_sul\.jpg → F026-P0097-1980-S03-D90001/.test(lista) && /slide 12\.png → F026-P0097-1980-S03-D90002/.test(lista), 'cada imagem mostra o código que ganhou (faixa D90001+)', lista);
  chk(/notas\.txt: .*JPEG, PNG ou TIFF/.test(lista), 'o arquivo que não é imagem diz por que não foi', lista);
  chk(um(`SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND origem='manual' AND revisao='conferida'`) === '2', 'no banco: 2 folhas, conferidas, origem manual');
  chk(um(`SELECT titulo FROM item WHERE codigo='${P}-1980-S03-D90001'`) === 'fachada sul', 'título vem do nome do arquivo');
  await pg.evaluate(() => closeDrawer(true));
  await pg.waitForSelector(`#pd .thumb img.img-prev`, { timeout: 10000 }).catch(() => {});
  const carregadas = await espera(() => pg.$$eval('#pd .thumb img.img-prev', im => im.length === 2 && im.every(x => x.complete && x.naturalWidth > 0)), 10000);
  chk(carregadas, 'as 2 folhas aparecem no projeto com a imagem');
  chk(!!(await pg.$('#pd .pj-env-linha [data-enviar-folhas]')), 'com folhas, o botão continua lá para enviar mais');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); process.exit(1); });
