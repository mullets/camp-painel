// Funções comuns dos testes de exaustão da página do projeto (CAMP-072 a CAMP-121). Rodar sempre por tests/rodar_exaustao.sh,
// que dá a cada arquivo um banco novo, um QNAP falso (FLUXO_RAIZ) e o painel com o site FALSO. Não edite para um grupo só:
// o que for de um grupo fica no arquivo do grupo.
const { execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE, DB = process.env.CAMP_DB_PATH, RAIZ = process.env.FLUXO_RAIZ, SAIDA = process.env.SAIDA || '/tmp/exaustao';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
if (!BASE || !DB || !RAIZ) { console.error('use tests/rodar_exaustao.sh'); process.exit(2); }
fs.mkdirSync(SAIDA, { recursive: true });
const USUARIOS = { leitura: ['leitor@camp.arq.br', 'senha-leitor-1234'], operador: ['operador@camp.arq.br', 'senha-operador-123'], admin: ['rafael@camp.arq.br', 'senha-bem-longa-123'] };
const linhas = [], problemas = [];
// chk(ok, 'CAMP-0xx: o que se espera', detalhe)
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + String(det).slice(0, 500))); if (!ok) problemas.push(msg); return !!ok };
const passo = t => linhas.push('\n== ' + t);
// estação + CAMP Vision de verdade (tests/fluxo_real_cv2.py): reservar, processando, pronto [--sem-aviso]
const cv2 = (...a) => execFileSync('python3', [path.join(__dirname, '..', 'fluxo_real_cv2.py'), ...a], { encoding: 'utf-8' }).trim();
const sql = (q, ...a) => JSON.parse(execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\nr=con.execute(sys.argv[2],sys.argv[3:]).fetchall()\ncon.commit()\nprint(json.dumps(r))', DB, q, ...a], { encoding: 'utf-8' }));
const um = (q, ...a) => (sql(q, ...a)[0] || [])[0];
const espera = async (f, ms = 12000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true } catch (_) {} await new Promise(r => setTimeout(r, 250)); } return false; };
let nPrint = 0;
const print = async (pg, nome) => { nPrint++; await pg.screenshot({ path: path.join(SAIDA, `${String(nPrint).padStart(2, '0')}_${nome}.png`) }).catch(() => {}) };
const txt = async (pg, s) => ((await pg.$(s)) ? (await pg.innerText(s)).replace(/\s+/g, ' ').trim() : '');
const confirmar = async pg => { if (await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 2500 }).then(() => true, () => false)) { await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 }).catch(() => {}) } };
const imgOk = (pg, sel) => espera(() => pg.$eval(sel, i => i.complete && i.naturalWidth > 0));
// um lote completo pelo caminho real; devolve {P, D(n)}
const loteReal = (nome = 'RESIDENCIA EXAUSTAO', fundo = 'F026', opc = {}) => {
  const P = cv2('reservar', BASE, fundo, nome, '1972'); cv2('processando', BASE, RAIZ, P, nome);
  if (!opc.soProcessando) cv2('pronto', BASE, RAIZ, P, ...(opc.semAviso ? ['--sem-aviso'] : []));
  return { P, D: n => `${P}-1972-S01-D${String(n).padStart(5, '0')}` };
};
let BR = null; const errosJs = [], http5 = [];
const navegador = async () => (BR = BR || await chromium.launch({ executablePath: CHROME }));
// entrar('operador', {viewport}) → página logada pela tela de login
const entrar = async (papel = 'operador', opc = {}) => {
  const [email, senha] = USUARIOS[papel] || papel;
  const ctx = await (await navegador()).newContext({ viewport: opc.viewport || { width: 1440, height: 900 } }), pg = await ctx.newPage();
  pg.on('pageerror', e => errosJs.push(`${email}: ${e.message}`));
  pg.on('response', r => { if (r.status() >= 500) http5.push(`${email}: ${r.status()} ${r.url().replace(BASE, '')}`) });
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return pg;
};
const abrirProjeto = async (pg, P) => { await pg.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P); await pg.waitForSelector('#pj-cards .pjc[data-pjc="site"]', { timeout: 15000 }); await pg.waitForTimeout(1500) };
// P0 (Trello 21/10): nenhuma gaveta abre sozinha; a pessoa abre pelo cartão (folhas = "Detalhes dos lotes", problemas, dados)
const abrirGaveta = async (pg, k) => { const v = await pg.evaluate(k => { const g = document.querySelector(`.pj-gav[data-gav="${k}"]`); return !!(g && g.checkVisibility && g.checkVisibility()) }, k); if (!v) { await pg.click(`#pj-cards [data-pjc-gav="${k}"]`); await pg.waitForTimeout(1500) } };
const abrirConferir = async (pg, P, folha) => { await pg.evaluate(r => nav(r), 'conferir/' + P + (folha ? '/' + folha : '')); await pg.waitForSelector('#cf-pane', { timeout: 15000 }); await pg.waitForTimeout(800) };
// fim: grava relatorio.txt e sai com 1 se houver FALHA
const fim = async () => {
  chk(!errosJs.length, 'nenhum erro de JavaScript', errosJs.join(' | ')); chk(!http5.length, 'nenhuma resposta 500 do painel', http5.join(' | '));
  if (BR) await BR.close();
  const rel = linhas.join('\n') + (problemas.length ? `\n\n${problemas.length} FALHA(S)` : '\n\nTUDO OK');
  fs.writeFileSync(path.join(SAIDA, 'relatorio.txt'), rel + '\n'); console.log(rel); process.exit(problemas.length ? 1 : 0);
};
const rodar = f => f().then(fim).catch(async e => { console.error(e); chk(false, 'o teste quebrou: ' + e.message); await fim() });
module.exports = { BASE, DB, RAIZ, SAIDA, chk, passo, cv2, sql, um, espera, print, txt, confirmar, imgOk, loteReal, entrar, abrirProjeto, abrirGaveta, abrirConferir, rodar, linhas, problemas };
