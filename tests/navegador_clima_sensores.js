// CAMP-CLIMA (24/11/2026): janela "Sensores do clima" (admin), aberta pela pílula do clima, no navegador de verdade (Playwright + Chromium).
// Rafael: "adicionei outros sensores de temperatura na sala, e vamos tirar aqueles 2 que já existiam."
// Leituras semeadas direto no banco; SEM credenciais da Tuya (o "Buscar sensores agora" só registra que faltam: nenhuma chamada à Tuya).
//  [A] a pílula mostra a média só dos sensores em uso (o que não aparece mais na Tuya há mais de 24 h já fica fora)
//  [B] "Gerenciar sensores" (admin) abre a janela com todos os sensores, o texto de ajuda, "novo" e "não aparece mais na Tuya"
//  [C] renomear: vale no banco e no painel da pílula
//  [D] desligar "Usar no clima": a média da pílula muda
//  [E] "Remover da lista": esconde (ativo=0 + removido), as leituras ficam; vai para "Removidos da lista"
//  [F] "Buscar sensores agora" roda a busca e mostra o resultado (aqui: faltam as credenciais)
//  [G] operador não vê "Gerenciar sensores"; celular (390 px) sem rolagem lateral
// Uso (servidor PRÓPRIO, porta 9120):
//   CAMP_DB_PATH=/dev/shm/cs/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/cs/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9120)
//   CAMP_DB_PATH=/dev/shm/cs/m.db CAMP_BASE=http://127.0.0.1:9120 [PRINTS=pasta] node tests/navegador_clima_sensores.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9120', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const um = q => py(`print(json.dumps(con.execute(sys.argv[2]).fetchone()))`, q);
const foto = async (page, nome) => { if (PRINTS) { fs.mkdirSync(PRINTS, { recursive: true }); await page.screenshot({ path: `${PRINTS}/${nome}.png` }); } };

async function entrar(browser, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 800 }, deviceScaleFactor: 1, isMobile: !!o.movel, hasTouch: !!o.movel });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/api\/itens\/[^/]+\/previa\b/.test(url)) o.erros.push(m.text() + ' ' + url); });
  page.on('pageerror', e => o.erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', o.email || 'rafael@camp.arq.br'); await page.fill('#lg-senha', o.senha || 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await page.waitForTimeout(1200);
  return { ctx, page };
}
const pilula = async P => (await P.locator('#clima-topo summary.clima-btn').textContent()).replace(/\s+/g, ' ');
const esperaPilula = async (P, txt) => { for (let i = 0; i < 30; i++) { if ((await pilula(P)).includes(txt)) return true; await P.waitForTimeout(200); } return false; };

(async () => {
  py(`con.execute("DELETE FROM clima_leitura")
con.execute("DELETE FROM clima_sensor")
con.execute("DELETE FROM clima_coleta")
con.execute("UPDATE configuracao SET valor='' WHERE chave IN ('clima.tuya_access_id','clima.tuya_access_secret','clima.sensores')")
con.execute("UPDATE configuracao SET valor='10' WHERE chave='clima.coleta_min'")
con.execute("INSERT INTO clima_coleta (sensores, erro, quando) VALUES (2, NULL, datetime('now','-10 minutes'))")
con.execute("""INSERT INTO clima_sensor (id, nome, nome_tuya, visto_em, criado_em) VALUES
 ('devA','Sala antiga 1','Sala antiga 1',datetime('now','-10 minutes'),datetime('now','-20 days')),
 ('devB','Sala antiga 2','Sala antiga 2',datetime('now','-10 minutes'),datetime('now','-20 days')),
 ('devN','Sala do acervo A','Sala do acervo A',datetime('now','-10 minutes'),datetime('now','-1 hours')),
 ('devS','Sensor sumido','Sensor sumido',datetime('now','-30 hours'),datetime('now','-30 days'))""")
for sid, t, u, idade in (('devA',22.0,50.0,'-10 minutes'),('devB',24.0,56.0,'-10 minutes'),('devN',23.0,53.0,'-10 minutes'),('devS',30.0,70.0,'-2 hours'),('devS',30.0,70.0,'-30 hours')):
    con.execute("INSERT INTO clima_leitura (sensor_id, temperatura_c, umidade_pct, lido_em) VALUES (?,?,?,datetime('now', ?))", (sid, t, u, idade))`);
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, page: P } = await entrar(browser, { erros });
    // [A]
    chk(await esperaPilula(P, '23,0°'), `[A] pílula: média dos 3 sensores em uso (23,0°); o que não aparece mais na Tuya há 30 h fica fora (${await pilula(P)})`);
    // [B]
    await P.locator('#clima-topo summary.clima-btn').click();
    const ger = P.locator('#clima-gerenciar');
    chk(await ger.isVisible() && (await ger.textContent()).trim() === 'Gerenciar sensores', '[B] o painel do clima tem "Gerenciar sensores" para o admin');
    await ger.click();
    const M = P.locator('#m-clima-sensores');
    await P.waitForSelector('#m-clima-sensores .csen-item');
    chk(await M.isVisible() && !(await P.locator('#clima-topo .clima-painel').isVisible()), '[B] abre a janela "Sensores do clima" (e fecha o painel da pílula)');
    const tm = (await M.textContent()).replace(/\s+/g, ' ');
    chk(tm.includes('Para trocar sensores: adicione os novos no app da Tuya/Smart Life (a mesma conta ligada ao painel), clique em Buscar sensores agora e desligue os antigos aqui.'), '[B] texto de ajuda para trocar sensores');
    chk(await M.locator('.csen-item').count() === 4, '[B] lista os 4 sensores conhecidos');
    const it = id => M.locator(`.csen-item[data-sensor="${id}"]`);
    const tA = (await it('devA').textContent()).replace(/\s+/g, ' ');
    chk(tA.includes('Na Tuya: Sala antiga 1') && tA.includes('online') && tA.includes('22,0° · 50% · há 10 min') && await it('devA').locator('[data-csen-ativo]').isChecked(), `[B] nome na Tuya, online, última leitura e "Usar no clima" ligado (${tA})`);
    chk(await it('devN').locator('.tag', { hasText: 'novo' }).count() === 1 && await it('devA').locator('.tag', { hasText: 'novo' }).count() === 0, '[B] o sensor achado há 1 h tem a etiqueta "novo"; os antigos não');
    const tS = (await it('devS').textContent()).replace(/\s+/g, ' ');
    chk(tS.includes('não aparece mais na Tuya') && !/\bonline\b/.test(tS) && tS.includes('fora da média') && await it('devS').locator('[data-csen-remover]').isVisible(), `[B] o sumido há 30 h: "não aparece mais na Tuya", fora da média, com "Remover da lista" (${tS})`);
    chk(await it('devA').locator('[data-csen-remover]').count() === 0, '[B] "Remover da lista" só no sensor que não aparece mais na Tuya');
    await foto(P, 'sensores-1366');
    // [C] renomear
    await it('devA').locator('[data-csen-nome]').fill('Reserva técnica');
    await it('devA').locator('[data-csen-nome]').press('Enter');
    let nome = ''; for (let i = 0; i < 20; i++) { nome = JSON.parse(um("SELECT nome FROM clima_sensor WHERE id='devA'"))[0]; if (nome === 'Reserva técnica') break; await P.waitForTimeout(200); }
    chk(nome === 'Reserva técnica' && JSON.parse(um("SELECT nome_tuya FROM clima_sensor WHERE id='devA'"))[0] === 'Sala antiga 1', `[C] renomear grava o nome no painel; o da Tuya fica (${nome})`);
    await P.waitForTimeout(400);
    chk(await P.locator('#clima-topo .clima-salas', { hasText: 'Reserva técnica' }).count() === 1, '[C] o nome novo aparece nas salas da pílula');
    // [D] desligar "Usar no clima": a média muda
    await it('devB').locator('[data-csen-ativo]').uncheck();
    chk(await esperaPilula(P, '22,5°'), `[D] "Usar no clima" desligado: a média da pílula muda de 23,0° para 22,5° (${await pilula(P)})`);
    chk(JSON.parse(um("SELECT ativo FROM clima_sensor WHERE id='devB'"))[0] === 0 && !(await it('devB').locator('[data-csen-ativo]').isChecked()), '[D] gravado no banco e a caixa continua desligada depois de reler');
    // [E] Remover da lista
    const nS = JSON.parse(um("SELECT COUNT(*) FROM clima_leitura WHERE sensor_id='devS'"))[0];
    await it('devS').locator('[data-csen-remover]').click();
    await P.waitForSelector('#conf-ov');
    chk((await P.locator('#conf-ov').textContent()).includes('as leituras antigas continuam guardadas'), '[E] a confirmação diz que nada é apagado');
    await P.locator('#conf-ov [data-conf="sim"]').click();
    let rem = null; for (let i = 0; i < 20; i++) { rem = JSON.parse(um("SELECT ativo, removido FROM clima_sensor WHERE id='devS'")); if (rem[1] === 1) break; await P.waitForTimeout(200); }
    chk(rem[0] === 0 && rem[1] === 1, `[E] Remover da lista: ativo=0 e removido=1 (${rem})`);
    chk(JSON.parse(um("SELECT COUNT(*) FROM clima_leitura WHERE sensor_id='devS'"))[0] === nS && nS === 2, '[E] as leituras do sensor removido ficam guardadas');
    await P.waitForTimeout(400);
    chk(await M.locator('.csen-lista[aria-label="Sensores"] .csen-item[data-sensor="devS"]').count() === 0 && await M.locator('.csen-removidos').count() === 1
      && (await M.locator('.csen-removidos summary').textContent()).includes('Removidos da lista (1)'), '[E] sai da lista e vai para "Removidos da lista (1)"');
    // [F] Buscar sensores agora
    await M.locator('#csen-buscar').click();
    let st = ''; for (let i = 0; i < 30; i++) { st = await M.locator('#csen-coleta').textContent(); if (/credenciais/.test(st)) break; await P.waitForTimeout(300); }
    chk(/credenciais/.test(st), `[F] "Buscar sensores agora" roda a busca e mostra o resultado (${st})`);
    await foto(P, 'sensores-1366-depois');
    await P.keyboard.press('Escape');
    chk(!(await M.isVisible()), 'Esc fecha a janela');
    await ctx.close();
    // [G] operador não vê; celular
    const { ctx: cO, page: O } = await entrar(browser, { erros, email: 'operador@camp.arq.br', senha: 'senha-operador-123' });
    await O.locator('#clima-topo summary.clima-btn').click();
    chk(await O.locator('#clima-topo .clima-painel').isVisible() && await O.locator('#clima-gerenciar').count() === 0, '[G] operador abre o painel do clima, mas sem "Gerenciar sensores"');
    await cO.close();
    const { ctx: cM, page: C } = await entrar(browser, { erros, w: 390, h: 844, movel: true });
    await C.locator('#clima-topo summary.clima-btn').tap();
    await C.locator('#clima-gerenciar').tap();
    await C.waitForSelector('#m-clima-sensores .csen-item');
    const cabe = await C.evaluate(() => { const b = document.querySelector('#m-clima-sensores .box'); const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && b.scrollWidth <= b.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth; });
    chk(cabe, '[G] 390 px: a janela cabe na tela, sem rolagem lateral');
    await foto(C, 'sensores-390');
    await cM.close();
    chk(!erros.length, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    chk(false, 'exceção: ' + (e && e.stack || e));
  } finally {
    await browser.close();
  }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
