// 01/11/2026 (Rafael: "aprovar pelo sistema e já enviar o que ele pediu pelo próprio sistema", com o Sender.net): na tela Pedidos de alta
// resolução, "Ver o que entregar" → "Aprovar e enviar por e-mail" mostra o que vai (arquivos do QNAP), o que fica de fora e o texto;
// "Enviar um teste para mim" manda para quem está logado sem mudar o pedido; "Aprovar e enviar" chama o Sender.net (aqui, um falso local),
// o pedido fica entregue e o link público baixa o arquivo.
// Uso: CAMP_SENDER_URL=http://127.0.0.1:8898/v2 bash tests/rodar_um.sh tests/navegador_entrega_email.js
const { execFileSync } = require('child_process');
const http = require('http'), fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH'); process.exit(2); }
const RAIZ = fs.mkdtempSync(path.join(os.tmpdir(), 'entrega_nav_'));
const P = 'F026-P0098', F1 = `${P}-1970-S01-D00001`;
const SID = execFileSync('python3', ['-c', `
import sqlite3,sys,os
from PIL import Image
con=sqlite3.connect(sys.argv[1]); raiz=sys.argv[2]
os.makedirs(raiz+'/TIF',exist_ok=True); Image.new('RGB',(300,200),(1,2,3)).save(raiz+'/TIF/${F1}.tif','TIFF')
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'",(raiz,))
con.execute("UPDATE configuracao SET valor='tok-nav' WHERE chave='sender.token'")
con.execute("UPDATE configuracao SET valor='camp42' WHERE chave='sender.campanha_entrega'")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 98)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES ('${P}','F026',98,'Casa do pedido',1970)")
con.execute("INSERT OR REPLACE INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,origem,arquivo_tif) VALUES ('${F1}','${P}','S01',1,'Planta térrea','campvision','TIF/${F1}.tif')")
sid=con.execute("INSERT INTO solicitacao (solicitante,email,finalidade,origem) VALUES ('Beatriz Teste','bia@exemplo.org','pesquisa','site')").lastrowid
con.execute("INSERT INTO solicitacao_item (solicitacao_id,codigo,formato) VALUES (?,?,'tif')",(sid,'${F1}'))
con.execute("INSERT INTO solicitacao_item (solicitacao_id,codigo,formato) VALUES (?,?,'pdf')",(sid,'${P}'))
con.commit(); print(sid)`, DB, RAIZ], { encoding: 'utf-8' }).trim();
const enviados = [];
const sender = http.createServer((req, res) => { let b = ''; req.on('data', d => b += d); req.on('end', () => { enviados.push({ url: req.url, auth: req.headers.authorization, corpo: JSON.parse(b || '{}') }); res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data: { emailId: 'x1' } })) }) });
(async () => {
  await new Promise(r => sender.listen(8898, '127.0.0.1', r));
  const br = await chromium.launch();
  const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#solicitacoes'); await pg.reload(); await pg.waitForTimeout(1200);
  await pg.evaluate(id => abrirSolicitacao(id), +SID); await pg.waitForTimeout(800);
  await pg.click(`[data-sol-pacote="${SID}"]`); await pg.waitForSelector(`[data-sol-envio="${SID}"]`, { timeout: 8000 });
  await pg.click(`[data-sol-envio="${SID}"]`); await pg.waitForSelector(`[data-se-enviar="${SID}"]`, { timeout: 8000 });
  const box = await pg.textContent('#sol-pacote');
  chk(box.includes('bia@exemplo.org') && box.includes(F1), 'a prévia mostra o destinatário e o arquivo achado no QNAP', box.slice(0, 200));
  chk(/Fica de fora/.test(box) && box.includes(P), 'o PDF do projeto aparece em "Fica de fora"');
  chk(!box.includes(RAIZ), 'a prévia não mostra o caminho do QNAP');
  await pg.fill('#se-msg', 'Uso só para a pesquisa.');
  await pg.click(`[data-se-teste="${SID}"]`); await pg.waitForTimeout(1500);
  chk(enviados.length === 1 && enviados[0].corpo.to.email === 'rafael@camp.arq.br' && enviados[0].url === '/v2/message/camp42/send', 'teste vai para quem está logado, pela rota do Sender.net', JSON.stringify(enviados[0] || {}).slice(0, 200));
  await pg.waitForSelector(`[data-se-enviar="${SID}"]`, { timeout: 8000 });
  await pg.fill('#se-msg', 'Uso só para a pesquisa.');
  await pg.click(`[data-se-enviar="${SID}"]`);
  await pg.waitForSelector('.modal.open button.pri, .modal[open] button.pri, #m-confirmar button.pri', { timeout: 5000 }).catch(() => {});
  const botao = await pg.$('text=Aprovar e enviar >> nth=-1'); if (botao) await botao.click();
  await pg.waitForTimeout(2000);
  const ult = enviados[enviados.length - 1] || { corpo: {} };
  chk(enviados.length === 2 && ult.corpo.to && ult.corpo.to.email === 'bia@exemplo.org' && ult.auth === 'Bearer tok-nav', 'aprovar e enviar manda para quem pediu, com o token do Sender', JSON.stringify(ult).slice(0, 200));
  chk(ult.corpo.variables && ult.corpo.variables.mensagem === 'Uso só para a pesquisa.' && ult.corpo.variables.nome === 'Beatriz', 'o recado e o nome vão como variáveis do layout');
  const sit = execFileSync('python3', ['-c', 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("SELECT situacao FROM solicitacao WHERE id=?",(int(sys.argv[2]),)).fetchone()[0])', DB, SID], { encoding: 'utf-8' }).trim();
  chk(sit === 'entregue', 'o pedido fica entregue', sit);
  const link = (ult.corpo.variables || {}).link_pagina || '';
  chk((ult.corpo.variables || {}).link === link + '/tudo.zip', 'o link principal do e-mail é o .zip de tudo');
  const rel = link.replace(/^https?:\/\/[^/]+/, '');
  const pub = await (await br.newContext()).newPage();
  const r1 = await pub.goto(BASE + rel);
  chk(r1.status() === 200 && (await pub.textContent('body')).includes(F1), 'o link público abre a página com o arquivo, sem login', `${r1.status()} ${rel}`);
  const r2 = await pub.request.get(BASE + rel + '/1');
  chk(r2.status() === 200 && (await r2.body()).length === fs.statSync(`${RAIZ}/TIF/${F1}.tif`).size, 'o arquivo baixa inteiro');
  const z = await pub.request.get(BASE + rel + '/tudo.zip');
  const zb = await z.body();
  chk(z.status() === 200 && zb.slice(0, 2).toString() === 'PK' && zb.includes(Buffer.from(`${P}/${F1}.tif`)), 'o link do .zip baixa um zip com o arquivo na pasta do projeto', `${z.status()} ${zb.length}`);
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close(); sender.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
