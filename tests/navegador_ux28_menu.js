// UX-28 · menu pela ordem do trabalho (Playwright, Chromium de verdade). Servidor PRÓPRIO, nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8953)
//   CAMP_BASE=http://127.0.0.1:8953 node tests/navegador_ux28_menu.js
// Confere: ordem dos grupos (Topo · Acervo · Público · Acompanhamento · Administração · Ajuda); as filas do dia à vista sem abrir o "Mais";
// nome do menu = título de cada página; as teclas de antes continuam iguais; trilha do projeto por onde se entrou (Projetos × Fundos).
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8953';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };
// as teclas de ANTES do UX-28 (nenhuma pode mudar)
const TECLAS = { painel: '1', projetos: '2', fundos: '3', solicitacoes: '4', estacoes: '5', decisoes: 'D', filas: 'N', erros: 'P', arquitetos: 'I', localizacao: 'W', estante: 'X', etiquetas: 'T', emprestimos: 'O', relatorios: 'L', uso: 'U', auditoria: 'A', qualidade: 'Q', config: 'C', caminho: 'M', glossario: 'G' };
const visiveis = pg => pg.$$eval('#nav > button, #nav > .grp', es => es.filter(e => e.offsetParent !== null).map(e => e.classList.contains('grp') ? '#' + e.textContent.trim() : (e.dataset.v || e.id)));
const entrar = async (b, email, senha) => {
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email, senha } });
  chk(r.ok(), 'login ' + email);
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(m.text()) });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/#painel');
  await page.evaluate(() => { try { localStorage.removeItem('camp.nav.mais') } catch (_) {} });
  await page.reload(); await page.waitForTimeout(1500);
  return page;
};
const tecla = async (pg, k) => { await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur()); await pg.keyboard.press(k); await pg.waitForTimeout(350); return pg.evaluate(() => rotaAtual().split('/')[0]) };
(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  const page = await entrar(b, 'rafael@camp.arq.br', 'senha-bem-longa-123');

  // 1) com o "Mais" fechado: o topo (filas do dia) e os destinos, pela ordem do trabalho
  const v0 = await visiveis(page);
  chk(v0.join(',') === 'painel,filas,erros,decisoes,projetos,nav-busca,#Acervo,fundos,arquitetos,#Público,solicitacoes,#Administração,estacoes,nav-mais-pc',
      '"Mais" fechado: Topo (Precisa de você · Material novo · Problemas · Decisões · Projetos · Busca) · Acervo · Público · Administração: ' + v0.join(','));
  chk(['filas', 'erros', 'decisoes'].every(v => v0.includes(v)), 'as filas do dia (Material novo, Problemas, Decisões) à vista sem abrir o "Mais"');

  // 2) com o "Mais" aberto: todos os grupos, na ordem pedida
  await page.click('#nav-mais-pc'); await page.waitForTimeout(200);
  const v1 = await visiveis(page);
  chk(v1.join(',') === 'painel,filas,erros,decisoes,projetos,nav-busca,#Acervo,fundos,arquitetos,localizacao,estante,etiquetas,emprestimos,#Público,solicitacoes,uso,#Acompanhamento,relatorios,auditoria,qualidade,#Administração,estacoes,config,#Ajuda,caminho,glossario,nav-mais-pc',
      '"Mais" aberto: Acervo · Público · Acompanhamento · Administração · Ajuda, cada um com os seus itens: ' + v1.join(','));
  await page.click('#nav-mais-pc');

  // 3) nome do menu = título da página (h1, topo e trilha)
  const nomeMenu = v => page.$eval(`#nav button[data-v="${v}"]`, e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim());
  const pares = [];
  for (const v of Object.keys(TECLAS)) {
    await page.evaluate(v => go(v), v); await page.waitForTimeout(v === 'painel' ? 900 : 500);
    const menu = await nomeMenu(v);
    const h1 = v === 'painel' ? null : await page.$eval(`#v-${v} .hdr h1`, e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim()).catch(() => '(sem h1)');
    const topo = (await page.textContent('#where')).trim(), trilha = await page.$eval('#gcrumb b:last-of-type', e => e.textContent.trim()).catch(() => '');
    const ok = (h1 === null || h1 === menu) && topo === menu && trilha === menu;
    pares.push(`${v}: menu "${menu}" · h1 "${h1}" · topo "${topo}" · trilha "${trilha}"`);
    chk(ok, `nome do menu = título da página em "${v}" (menu "${menu}", h1 "${h1}", topo "${topo}", trilha "${trilha}")`);
  }
  chk(await nomeMenu('fundos') === 'Fundos' && await nomeMenu('arquitetos') === 'Arquitetos', 'Fundos e Arquitetos são itens separados');
  chk(await nomeMenu('solicitacoes') === 'Pedidos de alta resolução' && await nomeMenu('uso') === 'Downloads', '"Pedidos de alta resolução" e "Downloads" no lugar dos nomes parecidos');
  chk(await nomeMenu('painel') === 'Precisa de você', 'a Home continua "Precisa de você" (decisão registrada; não renomeada para "Hoje")');
  await page.evaluate(() => go('arquitetos')); await page.waitForTimeout(400);
  chk(/Acervo/.test(await page.textContent('#gcrumb')), 'a trilha mostra o grupo do menu (Acervo / Arquitetos)');

  // 4) as teclas de antes, com o "Mais" fechado
  await page.evaluate(() => { navSecAbrir(false, true); go('painel') }); await page.waitForTimeout(700);
  const kbd = await page.$$eval('#nav button[data-v]', bs => Object.fromEntries(bs.map(x => [x.dataset.v, (x.querySelector('kbd') || {}).textContent || null])));
  chk(JSON.stringify(kbd) === JSON.stringify(Object.fromEntries(Object.keys(kbd).map(v => [v, TECLAS[v]]))), 'o menu anuncia as mesmas teclas de antes: ' + JSON.stringify(kbd));
  const errTecla = [];
  for (const [v, k] of Object.entries(TECLAS)) { await page.evaluate(() => go('glossario')); await page.waitForTimeout(200); const r = await tecla(page, k.toLowerCase()); if (v === 'glossario' ? r !== 'glossario' : r !== v) errTecla.push(`${k}→${r} (esperado ${v})`) }
  chk(!errTecla.length, 'cada tecla abre a mesma tela de antes' + (errTecla.length ? ': ' + errTecla.join(', ') : ''));

  // 5) Busca no topo do menu = a busca do ⌘K
  await page.click('#nav-busca'); await page.waitForTimeout(200);
  chk(await page.evaluate(() => document.activeElement && document.activeElement.id) === 'q', '"Busca" no menu foca o campo de busca');
  await page.keyboard.press('Escape');

  // 6) trilha do projeto respeita por onde se entrou
  await page.evaluate(() => go('projetos'));
  await page.waitForSelector('#v-projetos [data-nav^="projeto/"]', { timeout: 15000 });
  const alvo = await page.$eval('#v-projetos [data-nav^="projeto/"]', e => e.dataset.nav);
  await page.click(`#v-projetos [data-nav="${alvo}"]`); await page.waitForTimeout(1500);
  const t1 = (await page.textContent('#gcrumb')).trim();
  chk(/^\s*\/?\s*Projetos\s*\//.test(t1.replace(/^[^A-Za-zÀ-ú]*/, '')) && !/Fundos/.test(t1), `entrando por Projetos, a trilha é "Projetos / projeto" ("${t1}")`);
  const voltar1 = await page.$eval('#where button', e => e.getAttribute('onclick')).catch(() => '');
  chk(/'projetos'/.test(voltar1), '"Voltar" (sem histórico) cai em Projetos: ' + voltar1);
  const fundo = alvo.split('/')[1].slice(0, 4);
  await page.evaluate(f => nav('fundo/' + f), fundo); await page.waitForTimeout(1200);
  await page.evaluate(a => nav(a), alvo); await page.waitForTimeout(1500);
  const t2 = (await page.textContent('#gcrumb')).trim();
  chk(/Fundos/.test(t2) && t2.includes(fundo) && !/Projetos/.test(t2), `entrando por Fundos, a trilha é "Fundos / ${fundo} / projeto" ("${t2}")`);
  await page.goBack(); await page.waitForTimeout(800); await page.goForward(); await page.waitForTimeout(1500);
  chk(/Fundos/.test((await page.textContent('#gcrumb'))), 'voltar e avançar no navegador mantém a trilha de quem entrou por Fundos');
  await page.evaluate(() => go('projetos')); await page.waitForTimeout(800);
  await page.evaluate(a => nav(a), alvo); await page.waitForTimeout(1200);
  const folha = await page.$eval('#pd [data-nav^="item/"]', e => e.dataset.nav).catch(() => null);
  if (folha) { await page.evaluate(a => nav(a), folha); await page.waitForTimeout(1200); const t3 = (await page.textContent('#gcrumb')).trim(); chk(/Projetos/.test(t3) && !/Fundos/.test(t3) && /folha/.test(t3), `a folha herda a entrada por Projetos ("${t3}")`) }
  else linhas.push('(sem folha no projeto escolhido: pulei a trilha da folha)');

  // 7) operador: o grupo Administração some com os itens dele
  const op = await entrar(b, 'operador@camp.arq.br', 'senha-operador-123');
  const vo = await visiveis(op);
  chk(!vo.includes('#Administração') && !vo.includes('estacoes') && vo.includes('solicitacoes') && vo.includes('filas'), 'operador: sem o grupo Administração; com Pedidos de alta resolução e as filas: ' + vo.join(','));

  chk(erros.length === 0, 'sem erro no console' + (erros.length ? ': ' + erros.join(' | ') : ''));
  await b.close();
  console.log(pares.join('\n')); console.log(linhas.join('\n')); console.log(prob.length ? `${prob.length} FALHA(S)` : 'TUDO OK');
  process.exit(prob.length ? 1 : 0);
})().catch(e => { console.log('ERRO no teste:', e.message); console.log(linhas.join('\n')); process.exit(2) });
