// 03/11 (Rafael: "para colocar o analytics no nosso painel, adapte essa solução para nós" / "faça ele no dashboard"): a Home mostra o
// resumo de 28 dias do histórico guardado, e a tela "Visitas ao site" mostra tudo (períodos, canais, páginas, pesquisas no Google).
// Uso: bash tests/rodar_um.sh tests/navegador_visitas_site.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys
con=sqlite3.connect(sys.argv[1])
cid=con.execute("INSERT INTO visita_coleta (fonte,de,ate,linhas,por,fim) VALUES ('ga4',date('now','-40 days'),date('now','-1 day'),100,'teste',datetime('now'))").lastrowid
for n in range(1,41):
    dia=con.execute("SELECT date('now',?)",(f"-{n} days",)).fetchone()[0]
    con.execute("INSERT INTO visita_dia (dia,usuarios,sessoes,visualizacoes,coleta_id) VALUES (?,?,?,?,?)",(dia,10+n%7,12+n%7,30,cid))
    for tipo,valor,extra in (("canal","Organic Search",None),("origem","google / organic",None),("pagina","/acervo/arquitetos/burle-marx/","Burle Marx – CAMP"),("cidade","São Paulo, Brazil",None),("dispositivo","mobile",None)):
        con.execute("INSERT INTO visita_dimensao (dia,tipo,valor,extra,usuarios,sessoes,visualizacoes,coleta_id) VALUES (?,?,?,?,?,?,?,?)",(dia,tipo,valor,extra,5,6,15,cid))
    con.execute("INSERT INTO busca_google (dia,tipo,valor,cliques,impressoes,posicao,coleta_id) VALUES (?,?,?,?,?,?,?)",(dia,"consulta","acervo burle marx",2,20,3.5,cid))
con.execute("INSERT INTO visita_coleta (fonte,de,ate,linhas,erro,por,fim) VALUES ('search_console',date('now','-5 days'),date('now','-1 day'),0,'Search Console recusou (403): sem acesso <b>x</b>','teste',datetime('now'))")
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#painel'); await pg.reload();
  await pg.waitForSelector('#ini-visitas .vis-barras', { timeout: 10000 }).catch(() => {});
  const h = (await pg.textContent('#ini-visitas').catch(() => '')) || '';
  chk(/nos últimos 28 dias/.test(h) && !!(await pg.$('#ini-visitas .vis-barras')), 'Home: resumo de 28 dias do histórico, com o gráfico por dia', h.slice(0, 200));
  chk(/Organic Search/.test(h) && /acervo burle marx/.test(h), 'Home: de onde chegam e o que buscaram no Google', h.slice(0, 300));
  chk(await pg.$$eval('#ini-visitas .vis-barras rect', r => r.length) === 28, 'Home: 28 barras (uma por dia)');
  await pg.click('#ini-visitas button:has-text("Ver tudo")');
  await pg.waitForSelector('#v-visitas.on .hoje-kpis, #v-visitas .hoje-kpis', { timeout: 10000 }).catch(() => {});
  const t = (await pg.textContent('#vis-corpo').catch(() => '')) || '';
  chk((await pg.evaluate(() => location.hash)) === '#visitas', '"Ver tudo" abre a tela Visitas ao site');
  chk(/Visitas/.test(t) && /Páginas vistas/.test(t) && /Cliques no Google/.test(t), 'tela: números do período', t.slice(0, 200));
  chk(/Burle Marx – CAMP/.test(t) && /celular/.test(t) && /São Paulo, Brazil/.test(t) && /google \/ organic/.test(t), 'tela: páginas (com título), aparelhos, cidades e origem');
  chk(/acervo burle marx/.test(t) && /10%/.test(t) && /3,5/.test(t), 'tela: pesquisas no Google com taxa de clique e posição', t.slice(-400));
  chk(/a última busca falhou/.test(t) && !(await pg.$('#vis-corpo b:text-is("x")')), 'tela: mostra a falha da última busca (texto escapado)');
  const n28 = await pg.$$eval('#vis-corpo .vis-barras rect', r => r.length);
  await pg.click('[data-vis-per="7d"]'); await pg.waitForTimeout(800);
  const n7 = await pg.$$eval('#vis-corpo .vis-barras rect', r => r.length);
  await pg.click('[data-vis-per="90d"]'); await pg.waitForTimeout(800);
  const n90 = await pg.$$eval('#vis-corpo .vis-barras rect', r => r.length);
  chk(n28 === 28 && n7 === 7 && n90 === 40, 'tela: trocar o período (7, 28, 90 dias)', `${n7}/${n28}/${n90}`);
  chk(await pg.$eval('[data-vis-per="90d"]', b => b.classList.contains('on')), 'o período escolhido fica marcado');
  chk(!!(await pg.$('#nav button[data-v="visitas"]')), 'item "Visitas ao site" no menu');
  await pg.setViewportSize({ width: 390, height: 800 }); await pg.waitForTimeout(300);
  chk(await pg.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'celular: sem rolagem horizontal');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
