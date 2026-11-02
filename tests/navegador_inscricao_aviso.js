// 02/11 (Rafael: "quando mudo o status dela, devia mandar um e-mail para ela avisando que status está"): na inscrição, trocar a situação
// mostra "Avisar por e-mail" (marcado), o recado e o e-mail; Salvar manda (Sender.net falso local) e diz para quem foi.
// Uso: CAMP_SENDER_URL=http://127.0.0.1:8897/v2 bash tests/rodar_um.sh tests/navegador_inscricao_aviso.js
const { execFileSync } = require('child_process');
const http = require('http');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const IID = execFileSync('python3', ['-c', `
import sqlite3,sys
con=sqlite3.connect(sys.argv[1])
con.execute("UPDATE configuracao SET valor='tok-nav' WHERE chave='sender.token'")
con.execute("UPDATE configuracao SET valor='tr10nav' WHERE chave='sender.tr10_inscricao_situacao'")
i=con.execute("INSERT INTO inscricao (site_id,tipo,curso_id,curso,nome,email,situacao) VALUES (9901,'inscricao','res','Residência em Acervos','Carla Teste','carla@exemplo.org','nova')").lastrowid
con.commit(); print(i)`, DB], { encoding: 'utf-8' }).trim();
const env = []; const srv = http.createServer((q, s) => { let b = ''; q.on('data', d => b += d); q.on('end', () => { env.push({ url: q.url, corpo: JSON.parse(b || '{}') }); s.setHeader('Content-Type', 'application/json'); s.end('{"success":true}') }) });
(async () => {
  await new Promise(r => srv.listen(8897, '127.0.0.1', r));
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#inscricoes'); await pg.reload();
  await pg.waitForSelector(`[data-ins-abrir="${IID}"]`, { timeout: 10000 });
  await pg.click(`[data-ins-abrir="${IID}"]`); await pg.waitForSelector('#ins-sit');
  chk(await pg.$eval('#ins-aviso', e => e.hidden), 'sem mudar a situação, nada de aviso');
  await pg.selectOption('#ins-sit', 'selecionada');
  await pg.waitForSelector('#ins-avisar', { timeout: 8000 }).catch(() => {});
  chk(await pg.$eval('#ins-avisar', e => e.checked).catch(() => false), 'ao trocar para selecionada, "Avisar por e-mail" aparece marcado');
  chk(/carla@exemplo.org/.test(await pg.textContent('#ins-aviso')) && /Sender\.net/.test(await pg.textContent('#ins-aviso')), 'mostra para quem vai e por onde sai');
  await pg.fill('#ins-msg', 'Começa em 10/03.');
  await pg.click('[data-ins-salvar]'); await pg.waitForTimeout(1800);
  const t = (await pg.textContent('#toast').catch(() => '')) || '';
  chk(/e-mail enviado para carla@exemplo.org/.test(t), 'Salvar manda e avisa para quem foi', t);
  const u = env[env.length - 1] || { corpo: {} };
  chk(u.url === '/v2/message/tr10nav/send' && u.corpo.to.email === 'carla@exemplo.org' && u.corpo.variables.situacao === 'Selecionada' && u.corpo.variables.mensagem === 'Começa em 10/03.', 'o e-mail TR10 leva a situação e o recado', JSON.stringify(u).slice(0, 200));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close(); srv.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
