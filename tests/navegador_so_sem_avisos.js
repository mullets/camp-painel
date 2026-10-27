// UX-11 no navegador de verdade (Playwright + Chromium): "Conferir só sem avisos (N)" na página do projeto.
// Antes (F009-P0015) o número era o total a conferir (71), com 21 folhas de orientação incerta e 8 de metadado errado no mesmo projeto.
// Prova, num lote com 7 folhas a conferir (D1, D2, D6 limpas; D3 orientação incerta; D4 metadado errado aberto; D5 retida; D7 sem título):
//  - o botão diz "Conferir só sem avisos (3)", não 7;
//  - o clique mostra o resumo "3 folhas serão marcadas como conferidas; 4 ficam para revisão manual" (com a lista) e nada muda ao cancelar;
//  - ao confirmar, só D1, D2 e D6 ficam conferidas; o aviso tem "Desfazer", que volta as 3 para "a conferir"; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ss.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ss.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8944)
//   CAMP_DB_PATH=/tmp/ss.db CAMP_BASE=http://127.0.0.1:8944 node tests/navegador_so_sem_avisos.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8944', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0097', D = n => `${P}-1976-S01-D0000${n}`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 97)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',97,'Residência Só Sem Avisos',1976,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote só sem avisos','${P}','/x/ssa','revisao')").lastrowid
for s in range(1, 8):
    cod = "${P}-1976-S01-D%05d" % s
    pend = {"bloqueios": [], "sinais": (["orientação incerta"] if s == 3 else []), "ressalvas": []}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,origem,lote_id,status_site,pendencias,revisao,retida) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "" if s == 7 else "Prancha %d" % s, 'Planta', 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente', 1 if s == 5 else 0))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por) VALUES ('corrigir','metadado','campvision',?,'ano lido diverge do projeto','CAMP Vision')", ('${D(4)}',))
`);
const rev = () => JSON.parse(py(`print(json.dumps(dict(con.execute("SELECT substr(codigo,-2), revisao FROM item WHERE projeto_codigo='${P}'").fetchall())))`));
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|Failed to load resource/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  const bt = '#pd [data-rev-lote="todas"]';
  const achou = await espera(async () => !!(await pg.$(bt)), 15000);
  chk(achou, 'a página do projeto mostra "Conferir só sem avisos"');
  await espera(async () => /\(3\)/.test(await pg.$eval(bt, b => b.textContent).catch(() => '')), 6000);
  const txt = achou ? await pg.$eval(bt, b => b.textContent.trim()) : '';
  chk(txt === 'Conferir só sem avisos (3)', 'o número do botão exclui as folhas com aviso (3 sem aviso de 7 a conferir)', txt);
  if (achou) {
    await pg.click(bt);
    await espera(async () => !!(await pg.$('#conf-ov')));
    const corpo = await pg.$eval('#conf-ov', o => o.textContent.replace(/\s+/g, ' ')).catch(() => '');
    chk(/3 folhas serão marcadas como conferidas; 4 ficam para revisão manual/.test(corpo), 'o resumo diz "3 folhas serão marcadas como conferidas; 4 ficam para revisão manual"', corpo.slice(0, 300));
    chk(['D00003', 'D00004', 'D00005', 'D00007'].every(d => corpo.includes(d)), 'o resumo lista as 4 que ficam (orientação incerta, metadado errado, retida, sem título)', corpo.slice(0, 400));
    await pg.click('#conf-ov [data-conf="nao"]');
    chk(Object.values(rev()).every(v => v === 'pendente'), 'cancelar não muda nada');
    await pg.click(bt); await espera(async () => !!(await pg.$('#conf-ov [data-conf="sim"]')));
    await pg.click('#conf-ov [data-conf="sim"]');
    await espera(async () => !!(await pg.$('[data-desfazer-todas]')), 10000);
    const r1 = rev();
    chk(['01', '02', '06'].every(k => r1[k] === 'conferida') && ['03', '04', '05', '07'].every(k => r1[k] === 'pendente'), 'só as 3 sem aviso ficam conferidas', JSON.stringify(r1));
    const des = await pg.$('[data-desfazer-todas]');
    chk(!!des, 'o aviso do resultado tem "Desfazer"');
    if (des) {
      await des.click();
      await espera(async () => Object.values(rev()).every(v => v === 'pendente'), 8000);
      chk(Object.values(rev()).every(v => v === 'pendente'), '"Desfazer" volta as 3 para "a conferir"', JSON.stringify(rev()));
    }
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
