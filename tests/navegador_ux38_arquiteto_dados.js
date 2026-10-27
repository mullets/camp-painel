// UX-38 (Rafa, print do F013 "João Xavier": "já devia me jogar na página dele para pôr o que falta de dados"), no navegador de verdade, com o site FALSO:
//  - fundo com direitos autorizados, arquiteto vinculado SEM datas, biografia e retrato, 0 projetos; o site ainda sem a página do arquiteto;
//  - no quadro "Página do arquiteto no site" a ação principal é "Completar os dados do arquiteto"; "Publicar" continua, mas não é o botão azul;
//  - "Completar" abre a edição do arquiteto com os campos que faltam destacados e o cursor no primeiro;
//  - na edição do arquiteto, o bloco "O que falta para a página no site" e "Voltar ao fundo F013";
//  - publicar sem a página no site: o erro NÃO diz mais "espere um minuto" e traz o botão que resolve.
// Uso (servidor PRÓPRIO numa porta 89xx, com o site falso e sem a página "joao-xavier"):
//   CAMP_DB_PATH=/tmp/ux38.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux38.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 WP_FALSO_SEM_PAGINA=joao-xavier python3 ../tests/servidor_wp_falso.py 8990)
//   CAMP_DB_PATH=/tmp/ux38.db CAMP_BASE=http://127.0.0.1:8990 node tests/navegador_ux38_arquiteto_dados.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8990', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
// o fundo do print: publicado no site (termo), direitos autorizados, arquiteto vinculado sem datas/biografia/retrato, 0 projetos
const AID = py(`
if not con.execute("SELECT 1 FROM fundo WHERE codigo='F013'").fetchone():
    con.execute("INSERT INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F013','João Xavier','JXA',1)")
con.execute("UPDATE fundo SET titulo='João Xavier', data_inicio=1958, data_fim=2021, tainacan_term_id=913 WHERE codigo='F013'")
con.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES ('F013','autorizado','Família','Termo 1')")
r = con.execute("SELECT id FROM agente WHERE forma_autorizada='João Xavier'").fetchone()
aid = r[0] if r else con.execute("INSERT INTO agente (forma_autorizada,tipo) VALUES ('João Xavier','pessoa')").lastrowid
con.execute("UPDATE agente SET tipo='pessoa', existencia_inicio=NULL, existencia_fim=NULL, historia=NULL, fonte_historia=NULL WHERE id=?", (aid,))
con.execute("DELETE FROM agente_retrato WHERE agente_id=?", (aid,))
con.execute("DELETE FROM fundo_agente WHERE fundo_codigo='F013'")
con.execute("INSERT INTO fundo_agente (fundo_codigo,agente_id,papel) VALUES ('F013',?,'produtor')", (aid,))
con.execute("DELETE FROM projeto WHERE fundo_codigo='F013'")
con.execute("DELETE FROM wp_pagina WHERE url LIKE '%/acervo/arquitetos/%'")
print(aid)
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#fundo/F013'); await pg.reload();
  await pg.waitForSelector('#fd-arq .arq-linha', { timeout: 15000 }).catch(() => {});
  await espera(async () => !!(await pg.$('#fd-arq [data-arq-publicar]')) && /Falta|projeto publicado/.test(await pg.textContent('#fd-arq').catch(() => '')));   // a tela do fundo desenha em duas vezes
  await pg.waitForTimeout(800);   // espera a segunda pintura da tela do fundo
  await espera(async () => (await pg.$$('#fd-arq .btn.pri')).length > 0);
  const t0 = await pg.textContent('#fd-arq').catch(() => '');
  const pri = await pg.$$eval('#fd-arq .btn.pri', bs => bs.map(b => (b.dataset.arqCompletar ? 'completar:' : '') + b.textContent.trim()));
  chk(pri.length === 1 && pri[0] === 'completar:Completar os dados do arquiteto', 'fundo: a ação principal (azul) é "Completar os dados do arquiteto"', JSON.stringify(pri));
  const pub = await pg.$('#fd-arq [data-arq-publicar="F013"]');
  chk(!!pub && !(await pub.evaluate(b => b.classList.contains('pri') || b.disabled)), '"Publicar a página do arquiteto" continua (é permitido), mas não é o botão azul');
  chk(/Falta para a página ficar boa: biografia, fonte da biografia, retrato/.test(t0), 'o quadro diz o que falta (biografia, fonte da biografia, retrato)', t0.slice(0, 300));
  chk(/ainda não tem projeto publicado/.test(t0) && !/nem os projetos já publicados/.test(t0), 'sem projeto publicado: diz a verdade (a página só aparece com o primeiro projeto publicado)', t0.slice(0, 300));

  // publicar sem a página no site: o erro diz a verdade e traz o botão que resolve
  await pg.waitForTimeout(800); await pg.click('#fd-arq [data-arq-publicar="F013"]'); await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
  await pg.click('#conf-ov [data-conf="sim"]');
  await espera(async () => ((await pg.textContent('#conf-err').catch(() => '')) || '').length > 10);
  const terr = await pg.textContent('#conf-err').catch(() => '');
  chk(!/espere um minuto/i.test(terr) && /não criou a página/.test(terr), 'o erro não manda mais "esperar um minuto"; diz que o site não criou a página', terr.slice(0, 300));
  const bErr = await pg.$('#conf-err [data-arq-completar]');
  chk(!!bErr && /Completar os dados do arquiteto/.test(await bErr.textContent()), 'o erro vem com o botão "Completar os dados do arquiteto"');
  chk(!!(await pg.$('#conf-err [data-conf-fechar]:not([data-arq-completar])')), 'e com "Ver os projetos"', (await pg.innerHTML('#conf-err').catch(() => '')).slice(0, 300));
  if (bErr) await pg.click('#conf-err [data-arq-completar]');
  chk(await espera(async () => !(await pg.$('#conf-ov'))), 'o botão fecha a confirmação');
  // a edição do arquiteto, já no que falta
  chk(await espera(async () => !!(await pg.$('#d-body #ea-hist')) && (await pg.$$('#d-body .realce')).length >= 4), 'abre a edição do arquiteto com os campos que faltam destacados');
  const real = await pg.$$eval('#d-body .realce', xs => xs.map(x => x.dataset.falta));
  chk(['datas', 'historia', 'fonte_historia', 'retrato'].every(c => real.includes(c)), 'destacados: datas, biografia, fonte e retrato', JSON.stringify(real));
  chk(await espera(async () => (await pg.evaluate(() => document.activeElement && document.activeElement.id)) === 'ea-ini'), 'o cursor vai para o primeiro campo que falta (datas: Início)', await pg.evaluate(() => document.activeElement && document.activeElement.id));
  chk(await pg.evaluate(() => { const r = document.getElementById('ea-ini').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }), 'o primeiro campo que falta está à vista');
  const tb = await pg.textContent('#d-body .arq-falta').catch(() => '');
  chk(/O que falta para a página no site/.test(tb) && /Datas de nascimento e morte/.test(tb) && /Biografia/.test(tb) && /Fonte da biografia/.test(tb) && /Retrato/.test(tb),
    'na página do arquiteto: o bloco "O que falta para a página no site" com os itens', tb.slice(0, 300));
  chk(/fica só no painel/.test(tb), 'as datas dizem que ficam só no painel (o site não recebe)');
  const pubAg = await pg.$('#d-body .arq-site [data-arq-publicar="F013"]');
  chk(!pubAg || !(await pubAg.evaluate(b => b.classList.contains('pri'))), 'na página do arquiteto, "Publicar" também não é azul enquanto falta dado');
  const volta = await pg.$('#d-body .arq-falta [data-arq-voltar="F013"]');
  chk(!!volta && /Voltar ao fundo F013/.test(await volta.textContent()), 'o bloco tem "Voltar ao fundo F013"');
  if (volta) {
    await volta.click();
    chk(await espera(async () => (await pg.evaluate(() => location.hash)) === '#fundo/F013' && !(await pg.evaluate(() => document.querySelector('.main').classList.contains('with-drawer')))), 'voltar ao fundo fecha a edição e mostra o fundo');
  }
  // com tudo preenchido, Publicar volta a ser o botão azul
  py(`con.execute("UPDATE agente SET historia='Arquiteto paulista.', fonte_historia='Entrevista, 2020', existencia_inicio=1930, existencia_fim=2021 WHERE id=${+AID}")
con.execute("INSERT OR REPLACE INTO agente_retrato (agente_id, imagem, tipo) VALUES (${+AID}, x'00', 'image/jpeg')")`);
  await pg.goto(BASE + '/#fundo/F013'); await pg.reload(); await pg.waitForSelector('#fd-arq .arq-linha', { timeout: 15000 }).catch(() => {});
  chk(await espera(async () => !!(await pg.$('#fd-arq .btn.pri[data-arq-publicar="F013"]')) && !(await pg.$('#fd-arq [data-arq-completar]'))), 'com os dados completos, "Publicar a página do arquiteto" volta a ser o botão azul');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); process.exit(1); });
