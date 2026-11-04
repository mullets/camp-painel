// 03/11 (Rafael: "para colocar o analytics no nosso painel, adapte essa solução para nós" / "faça ele no dashboard") e 04/11 (especificação
// "Visitas ao site": "É na página de Dashboard"); 05/11 (plano de redesenho §12): a Home tem o RESUMO das visitas logo abaixo do gráfico de
// folhas conferidas (total, evolução e top 5, com "Ver análise completa de visitas"); a tela Visitas ao site tem o módulo completo (evolução +
// projetos mais visitados, ver todos, CSV…) e acrescenta canais, origem, cidades, aparelhos e pesquisas no Google do mesmo período.
// Os critérios de aceite estão em tests/navegador_visitas_redesenho.js e tests/navegador_redesenho_relatorios.js.
// Uso: bash tests/rodar_um.sh tests/navegador_visitas_site.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
con=sqlite3.connect(sys.argv[1])
ontem=datetime.now(ZoneInfo("America/Sao_Paulo")).date()-timedelta(days=1)
cid=con.execute("INSERT INTO visita_coleta (fonte,de,ate,linhas,por,fim) VALUES ('ga4',?,?,100,'teste',datetime('now'))",((ontem-timedelta(days=39)).isoformat(),ontem.isoformat())).lastrowid
url=con.execute("SELECT 'https://camp.arq.br/acervo/projetos/'||lower(codigo)||'-casa/' FROM projeto ORDER BY codigo LIMIT 1").fetchone()[0]
con.execute("UPDATE wp_item SET url=?, status='publish' WHERE id=(SELECT tainacan_item_id FROM projeto ORDER BY codigo LIMIT 1)",(url,))
for n in range(40):
    dia=(ontem-timedelta(days=n)).isoformat()
    con.execute("INSERT INTO visita_dia (dia,usuarios,sessoes,visualizacoes,coleta_id) VALUES (?,?,?,?,?)",(dia,10+n%7,12+n%7,30,cid))
    for tipo,valor,extra in (("canal","Organic Search",None),("origem","google / organic",None),("pagina","/acervo/arquitetos/burle-marx/","Burle Marx – CAMP"),("pagina",url[len("https://camp.arq.br"):],"Casa – CAMP"),("cidade","São Paulo, Brazil",None),("dispositivo","mobile",None)):
        con.execute("INSERT INTO visita_dimensao (dia,tipo,valor,extra,usuarios,sessoes,visualizacoes,coleta_id) VALUES (?,?,?,?,?,?,?,?)",(dia,tipo,valor,extra,5,6,15,cid))
    con.execute("INSERT INTO busca_google (dia,tipo,valor,cliques,impressoes,posicao,coleta_id) VALUES (?,?,?,?,?,?,?)",(dia,"consulta","acervo burle marx",2,20,3.5,cid))
con.execute("INSERT INTO visita_coleta (fonte,de,ate,linhas,erro,por,fim) VALUES ('search_console',?,?,0,'Search Console recusou (403): sem acesso <b>x</b>','teste',datetime('now'))",(ontem.isoformat(),ontem.isoformat()))
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {}); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#painel'); await pg.reload();
  await pg.waitForSelector('#ini-visitas .vm-rank', { timeout: 15000 }).catch(() => {});
  const h = (await pg.textContent('#ini-visitas').catch(() => '')) || '';
  chk(await pg.evaluate(() => { const r = document.getElementById('ini-ritmo'), v = document.getElementById('ini-visitas'); return !!(r && v && r.closest('section').nextElementSibling === v.closest('section')); }),
    'Home: Visitas ao site fica logo abaixo do gráfico de folhas conferidas por dia');
  chk(/Projetos mais visitados/.test(h) && /Visitas no período/.test(h) && /Média por dia/.test(h) && /Ver análise completa de visitas/.test(h) && !(await pg.$('#ini-visitas [data-vm-todos], #ini-visitas [data-vm-csv]')), 'Home: só o resumo (total e média ao lado do gráfico, top projetos e o link para a análise completa)', h.slice(0, 200));
  chk(!(await pg.$('#ini-visitas svg text')) && (await pg.$$eval('#ini-visitas polyline.lin', p => p.length)) >= 1, 'Home: gráfico de linha, sem texto dentro do SVG');
  chk(await pg.evaluate(() => [...document.querySelectorAll('#ini-visitas .vm-g-x span, #ini-visitas .vm-g-y span')].every(e => parseFloat(getComputedStyle(e).fontSize) >= 12 && parseFloat(getComputedStyle(e).fontSize) <= 14)), 'Home: rótulos do gráfico entre 12 e 14 px (não esticam)');
  chk((await pg.$$eval('#ini-visitas .vm-row', r => r.length)) === 1 && !/Burle Marx/.test(await pg.textContent('#ini-visitas .vm-rank')), 'Home: só a página de projeto no ranking (arquiteto fora)');
  await pg.click('#ini-visitas [data-vm-ir]');
  await pg.waitForFunction(() => /Cidades/.test((document.getElementById('vis-corpo') || {}).textContent || ''), null, { timeout: 10000 }).catch(() => {});
  const t = (await pg.textContent('#v-visitas').catch(() => '')) || '';
  chk((await pg.evaluate(() => location.hash)) === '#visitas', '"Ver análise completa de visitas" abre a tela Visitas ao site');
  chk(/Evolução das visitas/.test(t) && /Projetos mais visitados/.test(t) && /Média de visitas por dia/.test(t), 'tela: o módulo completo (evolução com indicadores + projetos mais visitados)');
  chk(/Google e outras buscas/.test(t) && /celular/.test(t) && /São Paulo, Brazil/.test(t) && /google \/ organic/.test(t), 'tela: canais, aparelhos, cidades e origem do período');
  chk(/acervo burle marx/.test(t) && /10%/.test(t) && /3,5/.test(t), 'tela: pesquisas no Google com taxa de clique e posição', t.slice(-400));
  await pg.selectOption('#vis-modulo [data-vm-per]', '7d'); await pg.waitForTimeout(1200);
  const n7 = await pg.evaluate(() => VM.ev.pontos.length);
  await pg.selectOption('#vis-modulo [data-vm-per]', '90d'); await pg.waitForTimeout(1200);
  const n90 = await pg.evaluate(() => ({ n: VM.ev.pontos.length, cob: VM.ev.dias_com_dados, txt: document.getElementById('vis-modulo').textContent }));
  chk(n7 === 7 && n90.n === 90 && n90.cob === 40 && /dias sem dado ficam em branco/.test(n90.txt), 'tela: trocar o período (7, 90 dias); dias fora do histórico ficam em branco, não zero', `${n7}/${JSON.stringify(n90).slice(0, 80)}`);
  chk(await pg.$eval('#vis-modulo [data-vm-per]', s => s.value) === '90d', 'o período escolhido fica marcado');
  chk(!!(await pg.$('#nav button[data-v="visitas"]')), 'item "Visitas ao site" no menu');
  await pg.setViewportSize({ width: 390, height: 800 }); await pg.waitForTimeout(300);
  chk(await pg.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'celular: sem rolagem horizontal');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
