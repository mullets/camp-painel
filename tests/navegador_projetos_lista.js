// Redesenho da tela "Projetos" (documento do Rafael, 04/11/2026, §8–13), no navegador de verdade (Playwright + Chromium).
// Critérios de aceite da §13 que cabem a Projetos ("Qual projeto quero localizar, consultar ou administrar?"):
//  [B] localizar um projeto por nome ou código rapidamente (sem acento, palavras fora de ordem, código parcial com zeros, sem hífen,
//      arquiteto, cliente) — a busca vai ao servidor (lista paginada lá)
//  [C] cartões, abas e menu da MESMA fonte (/api/projetos/resumo = contagens.py / /api/pendencias); a aba conta o que ela mostra
//  [D] filtros combinados (fundo + arquiteto + período + material + pendências), ordenação (cabeçalho e seletor, aria-sort) e paginação
//      ("Mostrando 1–25 de N", 25/50/100); voltar do projeto restaura filtros, ordenação e página; links profundos (#projetos/pronto,
//      #projetos/nao_publicado, #projetos/sem_folhas, #projetos/publicado e os números do fundo) abrem a lista limpa naquele filtro
//  [A] ações por permissão (admin, operador, leitura): "Abrir projeto" sempre; o "⋯" só com o que o papel pode; Novo projeto e a barra
//      de seleção (Publicar, Autorizar, Voltar para rascunho) só para quem pode
//  [E] sem as etapas de Material novo: nada de barra de conferência de folhas nem de progresso de importação/conferência; o único
//      indicador de andamento é "objetivos N/M" (UX-73), que diz o que mede
//  [F] o que existia continua: abas (Precisa de você, Pronto para publicar, No site, Com problema, Todos + Não publicados/Sem folhas
//      vindos de link), Novo projeto, seleção em massa (UX-20, "Marcar todos os N resultados"), Exportar visão, aviso de nome de pasta;
//      filtrar e ordenar não grava nada no banco
//  [G] teclado (F foca a busca, Enter no cabeçalho ordena, "⋯" abre e fecha), nomes acessíveis, situação em texto (não só cor)
//  [H] 390/1024/1366/1920 (e zoom 200%) sem rolagem lateral; celular em cartões; tablet sem as colunas secundárias e com a ação à vista
//  [I] miniatura só de imagem do próprio projeto (capa escolhida ou 1ª folha), loading=lazy; arquiteto só a autoria registrada
//  [P] desempenho: 3.000 projetos a mais e a lista continua com 25 linhas no DOM e respostas rápidas
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/p.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/p.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8985)
//   CAMP_DB_PATH=/tmp/x/p.db CAMP_BASE=http://127.0.0.1:8985 node tests/navegador_projetos_lista.js
const { execFileSync } = require('child_process');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8985', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
execFileSync('python3', [path.join(__dirname, 'fixtures', 'projetos_lista_semente.py'), DB, path.join(path.dirname(path.resolve(DB)), 'imagens_projetos_teste')], { stdio: 'ignore' });
const foto = () => py("print(json.dumps([con.execute('SELECT COUNT(*), MAX(atualizado_em) FROM projeto').fetchone(), con.execute('SELECT COUNT(*) FROM item').fetchone(), con.execute(\"SELECT COUNT(*) FROM evento WHERE tipo NOT IN ('login','projeto_fechado')\").fetchone()]))");

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, colorScheme: o.tema || 'light', deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?|\/api\/pedidos\/coleta$/.test(u);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
// espera a lista assentar (sem resposta pendente e com o contador escrito)
const assentar = async page => { await page.waitForTimeout(150); await page.waitForFunction(() => { const c = document.getElementById('proj-cnt'); return c && /Mostrando|Nenhum/.test(c.textContent) && !document.querySelector('#projetos-body .esq-lista,#projetos-body td.state-row'); }, null, { timeout: 15000 }); await page.waitForTimeout(450); };
async function projetos(page, rota) {
  await page.evaluate(r => { try { sessionStorage.removeItem('camp.proj.estado'); } catch (_) {} PROJ_ESTADO = { ...(typeof PROJ_PADRAO === 'undefined' ? { q: '', fundo: '', situacao: 'todos' } : PROJ_PADRAO), ordem: 'codigo' }; PROJ_PAG.pagina = 1; PROJ_PAG.por = 25; nav(r || 'projetos'); }, rota || '');
  await page.waitForFunction(() => document.querySelector('#projetos-body tr.lst-linha, #projetos-body td.empty'), null, { timeout: 15000 }).catch(() => {});
  await assentar(page).catch(() => {});
}
const linha = (page, cod) => page.locator(`#projetos-body tr[data-nav="projeto/${cod}"]`);
const codigos = page => page.$$eval('#projetos-body tr.lst-linha', l => l.map(x => x.dataset.nav.replace('projeto/', '')));
const num = t => +String(t || '').replace(/\D/g, '') || 0;
const total = async page => { const t = await page.textContent('#proj-cnt'); return /Nenhum/.test(t) ? 0 : num((t.match(/de ([\d.]+)/) || [0, '0'])[1]); };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const antes = foto();
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await projetos(P);

    // ---------------- [C] mesma fonte: cartões, abas, /api/pendencias ----------------
    chk(await P.waitForFunction(() => /\d/.test((document.querySelector('[data-proj-card="todos"] .v') || {}).textContent || ''), null, { timeout: 10000 }).then(() => true, () => false), '[C] os cartões de indicador aparecem com números');
    const pend = await P.evaluate(() => API('/api/pendencias'));
    const R = await P.evaluate(() => API('/api/projetos/resumo'));
    const C = await P.evaluate(() => { const card = k => (document.querySelector(`[data-proj-card="${k}"] .v`) || {}).textContent || '', aba = k => (document.querySelector(`#proj-chips [data-proj-sit="${k}"] b`) || {}).textContent || '';
      return { todos: card('todos'), site: card('publicado'), mat: card('com_material'), semImg: card('sem_imagem'), pend: card('com_pendencias'), aTodos: aba('todos'), aSite: aba('publicado'), aGente: aba('gente'), aPronto: aba('pronto'), aProb: aba('com_problema') }; });
    chk(num(C.todos) === pend.projetos_total && num(C.site) === pend.projetos_no_site, `[C] cartões "projetos no acervo" e "projetos no site" = contagens.py (/api/pendencias): ${C.todos}=${pend.projetos_total} · ${C.site}=${pend.projetos_no_site}`);
    chk(num(C.aTodos) === num(C.todos) && num(C.aSite) === num(C.site) && num(C.aTodos) === await total(P), `[C] aba "Todos" = cartão = "Mostrando … de N" (${C.aTodos}) e aba "No site" = cartão (${C.aSite})`);
    chk(num(C.mat) === R.com_material && num(C.semImg) === R.sem_imagem && num(C.pend) === R.com_pendencias && num(C.aGente) === R.gente && num(C.aPronto) === R.pronto && num(C.aProb) === R.com_problema,
      `[C] cartões e abas = /api/projetos/resumo (a mesma regra dos filtros): ${JSON.stringify(C)}`);
    await P.click('[data-proj-card="sem_imagem"]', { timeout: 3000 }).catch(() => {}); await assentar(P);
    chk(await total(P) === R.sem_imagem && (await P.inputValue('#proj-material')) === 'sem_imagem' && (await P.getAttribute('[data-proj-card="sem_imagem"]', 'aria-pressed')) === 'true',
      `[C] clicar no cartão "sem imagem" abre o conjunto (${await total(P)} = ${R.sem_imagem}) e liga o filtro Material`);
    await P.click('[data-proj-card="todos"]', { timeout: 3000 }).catch(() => {}); await assentar(P);
    chk((await P.inputValue('#proj-material')) === '' && await total(P) === R.todos, '[C] o cartão "projetos no acervo" limpa os filtros');

    // ---------------- [B] localizar por nome ou código ----------------
    const busca = async q => { const t0 = Date.now(); await P.fill('#proj-q', q); await P.waitForTimeout(350); await assentar(P); return { c: await codigos(P), ms: Date.now() - t0 }; };
    let b = await busca('geriatrico vila');
    chk(JSON.stringify(b.c) === '["F077-P0001"]' && b.ms < 3000, `[B] nome sem acento, palavras fora de ordem ("geriatrico vila"): ${JSON.stringify(b.c)} em ${b.ms} ms`);
    b = await busca('f077p0002');
    chk(JSON.stringify(b.c) === '["F077-P0002"]', `[B] código sem hífen ("f077p0002"): ${JSON.stringify(b.c)}`);
    b = await busca('F077-P0002');
    chk(JSON.stringify(b.c) === '["F077-P0002"]', `[B] código exato ("F077-P0002"): ${JSON.stringify(b.c)}`);
    await P.selectOption('#proj-fundo', 'F077'); await assentar(P);
    b = await busca('0002');
    chk(JSON.stringify(b.c) === '["F077-P0002"]', `[B] código parcial com zeros ("0002") dentro do fundo: ${JSON.stringify(b.c)}`);
    b = await busca('wilheim');
    chk(JSON.stringify(b.c.sort()) === '["F077-P0002","F077-P0005"]', `[B] pelo arquiteto (autoria registrada, "wilheim"): ${JSON.stringify(b.c)}`);
    b = await busca('cx039');
    chk(JSON.stringify(b.c) === '["F077-P0003"]', `[B] pela identificação original ("cx039"): ${JSON.stringify(b.c)}`);
    b = await busca('zzzz nada');
    chk(b.c.length === 0 && /Nenhum projeto com estes filtros/.test(await P.textContent('#projetos-body')) && await P.locator('#projetos-body [data-proj-limpar-vazio]').count() === 1, '[B] sem resultado: "Nenhum projeto com estes filtros." com "Limpar filtros"');
    await P.click('#projetos-body [data-proj-limpar-vazio]'); await assentar(P);
    chk((await P.inputValue('#proj-q')) === '' && (await P.inputValue('#proj-fundo')) === '' && await P.locator('#proj-limpar').isHidden(), '[D] "Limpar filtros" limpa a busca e os selects');

    // ---------------- [D] filtros combinados ----------------
    await P.selectOption('#proj-fundo', 'F077'); await assentar(P);
    const arqOps = await P.$$eval('#proj-arq option', l => l.map(o => o.textContent));
    chk(arqOps[0] === 'Todos' && arqOps.includes('Arnaldo Martino (2)') && arqOps.includes('Jorge Wilheim (2)') && /^Sem autoria registrada \(\d+\)$/.test(arqOps[arqOps.length - 1]) && !arqOps.some(o => /Fundo Lista|Burle|Barretto/.test(o)),
      `[I] filtro Arquiteto só com a autoria REGISTRADA nos projetos (o nome do fundo não vira arquiteto): ${JSON.stringify(arqOps)}`);
    await P.selectOption('#proj-arq', 'Arnaldo Martino'); await assentar(P);
    chk(JSON.stringify((await codigos(P)).sort()) === '["F077-P0001","F077-P0002"]', `[D] Fundo F077 + Arquiteto "Arnaldo Martino": ${JSON.stringify(await codigos(P))}`);
    await P.selectOption('#proj-periodo', '1960-1969'); await assentar(P);
    chk(JSON.stringify(await codigos(P)) === '["F077-P0002"]', `[D] + Período 1960–1969 (a obra de 1958–1961 entra): ${JSON.stringify(await codigos(P))}`);
    chk(await P.evaluate(() => ['proj-fundo', 'proj-arq', 'proj-periodo'].every(id => document.getElementById(id).classList.contains('ativo'))) && !(await P.locator('#proj-limpar').isHidden()), '[D] os selects ligados ficam marcados e "Limpar filtros" aparece');
    const abaFiltro = num(await P.textContent('#proj-chips [data-proj-sit="todos"] b'));
    chk(abaFiltro === 1, `[C] com filtros, a aba "Todos" conta o que ela mostra (${abaFiltro})`);
    await P.selectOption('#proj-periodo', ''); await P.selectOption('#proj-arq', ''); await assentar(P);
    await P.selectOption('#proj-material', 'sem'); await assentar(P);
    const semMat = await codigos(P);
    chk(semMat.includes('F077-P0004') && !semMat.includes('F077-P0001') && await P.evaluate(() => [...document.querySelectorAll('#projetos-body tr.lst-linha .c-pj-n')].every(td => td.textContent.trim() === '0')), `[D] Material "Sem material digitalizado": só projetos com 0 folhas (${semMat.length})`);
    await P.selectOption('#proj-material', 'sem_imagem'); await assentar(P);
    const semImg = await codigos(P);
    chk(semImg.includes('F077-P0003') && semImg.includes('F077-P0004') && !semImg.includes('F077-P0001'), `[D] Material "Sem imagem": inclui o que tem folhas sem imagem (P0003) e o sem folhas (P0004): ${semImg.length}`);
    await P.selectOption('#proj-material', ''); await P.selectOption('#proj-pend', 'com'); await assentar(P);
    chk(JSON.stringify((await codigos(P)).sort()) === '["F077-P0006","F077-P0007"]', `[D] Pendências "Com pendências": problema em aberto (P0006) e lote para conferir (P0007): ${JSON.stringify(await codigos(P))}`);
    await P.click('#proj-chips [data-proj-sit="com_problema"]'); await assentar(P);
    chk(JSON.stringify(await codigos(P)) === '["F077-P0006"]' && (await P.inputValue('#proj-pend')) === 'com', '[D] a aba soma com os filtros (Com problema + Pendências + fundo)');
    await P.click('#proj-limpar'); await assentar(P);

    // ---------------- [D] ordenação ----------------
    await P.selectOption('#proj-fundo', 'F077'); await assentar(P);
    await P.focus('th.c-pj-arq .th-ord'); await P.keyboard.press('Enter'); await assentar(P);
    const arqs = await P.$$eval('#projetos-body tr.lst-linha .c-pj-arq', l => l.map(x => x.innerText.replace(/\s+/g, ' ')));
    chk((await P.inputValue('#proj-ordem')) === 'autoria' && (await P.getAttribute('#v-projetos th.c-pj-arq', 'aria-sort')) === 'ascending' && JSON.stringify(arqs.slice(0, 3)) === '["Arnaldo Martino","Arnaldo Martino Jorge Wilheim","Jorge Wilheim"]' && arqs[4] === 'não registrada',
      `[D][G] Enter no cabeçalho "Arquiteto(s)" ordena pela autoria registrada (sem autoria no fim; aria-sort; o seletor acompanha): ${JSON.stringify(arqs.slice(0, 5))}`);
    await P.selectOption('#proj-ordem', 'ano'); await assentar(P);
    const anos = await P.$$eval('#projetos-body tr.lst-linha .c-pj-data', l => l.map(x => parseInt(x.textContent, 10) || 0));   // "1958–1961" conta pelo início
    chk((await P.getAttribute('#v-projetos th.c-pj-data', 'aria-sort')) === 'ascending' && anos.filter(Boolean).every((v, i, a) => !i || a[i - 1] <= v) && anos[0] === 1950 && anos.indexOf(0) === -1, `[D] "Data da obra" ordena do mais antigo (sem data no fim): ${anos.slice(0, 6)} · ${await P.getAttribute('#v-projetos th.c-pj-data', 'aria-sort')}`);
    await P.selectOption('#proj-ordem', 'folhas'); await assentar(P);
    const fl = await P.$$eval('#projetos-body tr.lst-linha .c-pj-n', l => l.map(x => +x.textContent.replace(/\D/g, '') || 0));
    chk(fl.every((v, i) => !i || fl[i - 1] >= v) && (await P.getAttribute('#v-projetos th.c-pj-n', 'aria-sort')) === 'descending', `[D] "Mais folhas" ordena do maior (aria-sort descending): ${fl.slice(0, 6)}`);
    await P.selectOption('#proj-ordem', 'nome'); await assentar(P);
    const nomes = await P.$$eval('#projetos-body tr.lst-linha .proj-tit', l => l.map(x => x.textContent));
    chk(nomes.every((t, i) => !i || nomes[i - 1].localeCompare(t, 'pt-BR', { sensitivity: 'base' }) <= 0) && (await P.getAttribute('#v-projetos th.c-proj', 'aria-sort')) === 'ascending', '[D] "Nome (A–Z)" ordena pelo título e o cabeçalho diz aria-sort');
    // a ordem vale para a lista INTEIRA (servidor), não só para a página
    const ultimaPg = await P.evaluate(async () => (await API('/api/projetos?fundo=F077&ordem=nome&por_pagina=25&pagina=3')).itens.map(x => x.titulo));
    chk(ultimaPg.length && nomes[nomes.length - 1].localeCompare(ultimaPg[0], 'pt-BR', { sensitivity: 'base' }) <= 0, '[D] a ordenação é da lista inteira (a página 3 continua depois da 1)');

    // ---------------- [D] paginação ----------------
    await P.selectOption('#proj-ordem', 'codigo'); await assentar(P);
    const tF = await total(P);
    let pg = (await P.textContent('#projetos-pag')).replace(/\s+/g, ' ');
    chk(new RegExp(`Mostrando 1–25 de ${tF}`).test(pg) && (await P.locator('#projetos-body tr.lst-linha').count()) === 25 && /Mostrando 1–25 de \d+ projetos/.test(await P.textContent('#proj-cnt')),
      `[D] "Mostrando 1–25 de ${tF}" (rodapé e resumo) e só 25 linhas no DOM: "${pg.slice(0, 60)}"`);
    chk(JSON.stringify(await P.$$eval('#projetos-pag select[data-pg="por"] option', l => l.map(o => o.value))) === '["25","50","100"]', '[D] itens por página: 25, 50 ou 100');
    await P.click('#projetos-pag [data-pg="prox"]'); await assentar(P);
    chk(new RegExp(`Mostrando 26–50 de ${tF}`).test(await P.textContent('#projetos-pag')), '[D] Próxima: "Mostrando 26–50"');
    await P.selectOption('#projetos-pag select[data-pg="por"]', '50'); await assentar(P);
    chk((await P.locator('#projetos-body tr.lst-linha').count()) === Math.min(50, tF) && /Mostrando 1–/.test(await P.textContent('#projetos-pag')), '[D] 50 por página volta para a página 1');
    await P.selectOption('#projetos-pag select[data-pg="por"]', '25'); await assentar(P);

    // ---------------- [D] voltar do projeto restaura ----------------
    await P.selectOption('#proj-material', 'com'); await assentar(P); await P.selectOption('#proj-ordem', 'nome'); await assentar(P);
    await P.click('#projetos-pag [data-pg="prox"]'); await assentar(P);
    const est0 = await P.evaluate(() => JSON.stringify({ f: PROJ_ESTADO.fundo, m: PROJ_ESTADO.material, o: PROJ_ESTADO.ordem, p: PROJ_PAG.pagina }));
    await P.locator('#projetos-body tr.lst-linha .proj-tit').first().click(); await P.waitForFunction(() => /^#projeto\//.test(location.hash), null, { timeout: 10000 }); await P.waitForTimeout(900);
    const crumb = await P.evaluate(() => (history.state || {}).campOrigem);
    await P.goBack(); await P.waitForFunction(() => /^#projetos/.test(location.hash), null, { timeout: 10000 }); await assentar(P);
    const est1 = await P.evaluate(() => JSON.stringify({ f: PROJ_ESTADO.fundo, m: PROJ_ESTADO.material, o: PROJ_ESTADO.ordem, p: PROJ_PAG.pagina }));
    chk(est0 === est1 && JSON.parse(est1).p === 2 && (await P.inputValue('#proj-fundo')) === 'F077' && (await P.inputValue('#proj-material')) === 'com' && /Mostrando 26–/.test(await P.textContent('#projetos-pag')),
      `[D] abrir um projeto pelo nome e voltar: fundo, material, ordenação e página voltam (${est0} → ${est1})`);
    chk(crumb === 'projetos', `[D] o nome abre o projeto pelo nav (o "← Voltar" e a trilha levam a Projetos): campOrigem=${crumb}`);
    // recarregar a página (F5) com o mesmo endereço também restaura (sessionStorage)
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await P.waitForFunction(() => document.querySelector('#projetos-body tr.lst-linha'), null, { timeout: 15000 }); await assentar(P);
    chk(await P.evaluate(() => PROJ_ESTADO.fundo === 'F077' && PROJ_ESTADO.material === 'com' && PROJ_PAG.pagina === 2), '[D] recarregar a página (F5) mantém filtros e página');

    // ---------------- [D] links profundos ----------------
    for (const [rota, aba, rot] of [['projetos/pronto', 'pronto', 'Pronto para publicar'], ['projetos/nao_publicado', 'nao_publicado', 'Não publicados'], ['projetos/sem_folhas', 'sem_folhas', 'Sem folhas'], ['projetos/publicado', 'publicado', 'No site']]) {
      await P.evaluate(r => nav(r), rota); await P.waitForTimeout(300); await assentar(P);
      const s = await P.evaluate(() => ({ sit: PROJ_ESTADO.situacao, f: PROJ_ESTADO.fundo, m: PROJ_ESTADO.material, p: PROJ_PAG.pagina, q: PROJ_ESTADO.q }));
      const ab = await P.locator(`#proj-chips [data-proj-sit="${aba}"][aria-pressed="true"]`).textContent().catch(() => '');
      const n = num((await P.locator(`#proj-chips [data-proj-sit="${aba}"] b`).textContent().catch(() => '')));
      chk(s.sit === aba && !s.f && !s.m && s.p === 1 && !s.q && ab.startsWith(rot) && n === await total(P), `[D] #${rota}: aba "${rot}" ligada (${n} = lista), os outros filtros limpos (${JSON.stringify(s)})`);
    }
    await P.evaluate(() => nav('fundo/F077')); await P.waitForSelector('#fd [data-fd-cont="com_problema"]', { timeout: 15000 });
    await P.click('#fd [data-fd-cont="com_problema"]'); await P.waitForFunction(() => location.hash === '#projetos', null, { timeout: 5000 }); await assentar(P);
    chk(await P.evaluate(() => PROJ_ESTADO.fundo === 'F077' && PROJ_ESTADO.situacao === 'com_problema' && !PROJ_ESTADO.material) && JSON.stringify(await codigos(P)) === '["F077-P0006"]', '[D] número "com problema" do fundo abre Projetos do F077 nessa aba, sem outros filtros');

    // ---------------- [E] sem as etapas de Material novo; o andamento diz o que mede ----------------
    await projetos(P, 'projetos');
    await P.fill('#proj-q', 'F077-P00'); await P.waitForTimeout(350); await assentar(P);
    const semEtapas = await P.evaluate(() => ({ prog: document.querySelectorAll('#v-projetos .prog, #v-projetos progress, #v-projetos .steps').length, txt: /Conferência|Importação|Arquivos recebidos|folhas conferidas/.test(document.getElementById('projetos-body').innerText) }));
    chk(!semEtapas.prog && !semEtapas.txt, `[E] nenhuma barra/etapa de Material novo na lista de Projetos (${JSON.stringify(semEtapas)})`);
    const selo = await P.evaluate(async () => { const r = await API('/api/projetos?q=F077-P0001'); const m = r.itens[0].metas; const s = document.querySelector('#projetos-body tr[data-nav="projeto/F077-P0001"] .mt-selo'); return { t: s && s.textContent, tit: s && s.title, m }; });
    chk(selo.t === `objetivos ${selo.m.feitas}/${selo.m.total}` && /Objetivos do projeto cumpridos: \d+ de \d+/.test(selo.tit), `[E][F] o único andamento é "objetivos N/M" (UX-73), com a dica do que mede: "${selo.t}" · "${selo.tit}"`);
    const sitLinha = (await linha(P, 'F077-P0005').locator('.c-pj-sit').innerText()).replace(/\s+/g, ' ');
    chk(/Site: rascunho/.test(sitLinha) && /Pronto para publicar|Chegando/.test(sitLinha), `[E] situação do trabalho e estado no site com nomes separados: "${sitLinha}"`);
    chk(!/Site:/.test(await linha(P, 'F077-P0002').locator('.c-pj-sit').innerText()) && /No site/.test(await linha(P, 'F077-P0002').locator('.c-pj-sit').innerText()), '[E] projeto publicado: "No site", sem repetir "Site: publicado"');

    // ---------------- [I] miniatura e arquiteto ----------------
    await P.waitForFunction(() => { const i = document.querySelector('#projetos-body tr[data-nav="projeto/F077-P0001"] .mini img'); return i && i.complete; }, null, { timeout: 10000 }).catch(() => {});
    const mi = await P.evaluate(() => { const i = document.querySelector('#projetos-body tr[data-nav="projeto/F077-P0001"] .mini img'); return i ? { src: i.getAttribute('src'), lazy: i.getAttribute('loading'), w: i.naturalWidth } : null; });
    chk(mi && mi.lazy === 'lazy' && mi.src.includes('/api/itens/F077-P0001-1972-S01-D00002/previa') && /t=120/.test(mi.src) && mi.w > 0, `[I] miniatura = a capa escolhida do próprio projeto (D00002), pequena, loading=lazy e carregada: ${JSON.stringify(mi)}`);
    chk(await linha(P, 'F077-P0003').locator('.mini img').count() === 0 && await linha(P, 'F077-P0003').locator('.mini').count() === 1, '[I] projeto com folhas sem imagem: quadro neutro, sem foto');
    const arq = await P.evaluate(() => ['F077-P0001', 'F077-P0002', 'F077-P0003'].map(c => document.querySelector(`#projetos-body tr[data-nav="projeto/${c}"] .c-pj-arq`).innerText.replace(/\s+/g, ' ')));
    chk(arq[0] === 'Arnaldo Martino' && arq[1] === 'Arnaldo Martino Jorge Wilheim' && arq[2] === 'não registrada', `[I] coluna Arquiteto(s): só a autoria registrada; sem registro, "não registrada" (nunca o fundo): ${JSON.stringify(arq)}`);
    chk((await linha(P, 'F077-P0002').locator('.c-pj-data').innerText()) === '1958–1961' && (await linha(P, 'F077-P0003').locator('.c-pj-data').innerText()) === 'sem data', '[I] coluna Data: período "1958–1961" e "sem data"');

    // ---------------- [F] o que existia continua ----------------
    chk(await P.locator('#v-projetos .hdr [data-pode="projeto.criar"]').isVisible() && (await P.textContent('#v-projetos .hdr .act')).includes('Novo projeto'), '[F] Novo projeto no cabeçalho (admin)');
    chk(await P.locator('#v-projetos [data-export-view]').isVisible(), '[F] "Exportar visão" continua, ao lado do "Mostrando…"');
    const abas = await P.$$eval('#proj-chips [data-proj-sit]', l => l.map(x => x.textContent.replace(/\s*[\d.]+$/, '').trim()));
    chk(JSON.stringify(abas) === '["Precisa de você","Pronto para publicar","No site","Com problema","Todos"]', `[F] as abas de antes, na mesma ordem: ${JSON.stringify(abas)}`);
    await linha(P, 'F077-P0001').locator('.sel-cel').click(); await linha(P, 'F077-P0002').locator('.proj-sel').check(); await P.waitForTimeout(200);
    const bulk = (await P.textContent('#proj-bulk')).replace(/\s+/g, ' ');
    chk(await P.locator('#proj-bulk').evaluate(e => e.classList.contains('on')) && /2 projetos selecionados · 7 folhas/.test(bulk) && /Publicar os 2 no site/.test(bulk) && /Autorizar/.test(bulk) && /Voltar para rascunho/.test(bulk) && /Exportar CSV/.test(bulk),
      `[F] seleção em massa (UX-20/CAMP-149): "${bulk.slice(0, 120)}"`);
    await P.click('#proj-sel-visiveis'); await P.waitForTimeout(200);
    chk(/Marcar todos os \d+ resultados/.test(await P.textContent('#proj-sel-todos-msg')), '[F] marcar a página oferece "Marcar todos os N resultados" (H12)');
    await P.evaluate(() => limparSelecaoProjetos());
    chk(await P.locator('#proj-nome-pasta').count() === 1, '[F] o lugar do aviso de nomes de pasta (UX-15/UX-67) continua no topo da tela');
    // o clique na linha (fora do nome) continua abrindo o projeto, e o checkbox não abre
    await linha(P, 'F077-P0003').locator('.c-pj-at').click(); await P.waitForFunction(() => location.hash === '#projeto/F077-P0003', null, { timeout: 8000 }).then(() => chk(true, '[F] clicar na linha abre o projeto (como antes)'), () => chk(false, '[F] clicar na linha abre o projeto'));
    await P.goBack(); await assentar(P);

    // ---------------- [A] ações por permissão (admin) ----------------
    const menu = async (page, cod) => { const s = linha(page, cod).locator('details.lista-mais > summary'); await s.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(150); const it = await linha(page, cod).locator('.mais-lista [role="menuitem"]').allTextContents(); await page.keyboard.press('Escape'); await linha(page, cod).locator('details.lista-mais').evaluate(d => d.removeAttribute('open')); return it; };
    const mAdmNao = await menu(P, 'F077-P0001'), mAdmSite = await menu(P, 'F077-P0002');
    chk(mAdmNao.includes('Publicar no site…') && mAdmNao.includes('Imprimir etiqueta da pasta') && mAdmNao.includes('Exportar (CSV)') && !mAdmNao.includes('Voltar para rascunho…'), `[A] admin, projeto não publicado: ${JSON.stringify(mAdmNao)}`);
    chk(mAdmSite.includes('Voltar para rascunho…') && !mAdmSite.includes('Publicar no site…') && await linha(P, 'F077-P0002').locator('[data-proj-acao="rascunho"].perigo-txt').count() === 1, `[A] admin, projeto publicado: "Voltar para rascunho…" em vermelho, sem Publicar: ${JSON.stringify(mAdmSite)}`);
    chk(await P.locator('#v-projetos summary[aria-label^="Mais ações: F077-P0001"]').count() === 1, '[G] o "⋯" tem nome acessível ("Mais ações: código · título") e abre/fecha pelo teclado');
    // "Voltar para rascunho…" pede a confirmação de sempre (e Cancelar não grava nada)
    await linha(P, 'F077-P0002').locator('details.lista-mais > summary').click(); await linha(P, 'F077-P0002').locator('[data-proj-acao="rascunho"]').click();
    await P.waitForSelector('#conf-ov', { timeout: 5000 }).then(() => chk(true, '[A] "Voltar para rascunho…" abre a confirmação de sempre'), () => chk(false, '[A] "Voltar para rascunho…" abre a confirmação de sempre'));
    await P.click('#conf-ov [data-conf="nao"]').catch(() => P.keyboard.press('Escape')); await P.waitForTimeout(300);
    // "Publicar no site…" mostra o plano (nada é publicado sem o segundo clique)
    await linha(P, 'F077-P0001').locator('details.lista-mais > summary').click(); await linha(P, 'F077-P0001').locator('[data-proj-acao="publicar"]').click();
    await P.waitForFunction(() => /plano do lote/.test((document.getElementById('d-sub') || {}).textContent || ''), null, { timeout: 8000 }).then(() => chk(true, '[A] "Publicar no site…" abre o plano (o mesmo da publicação em lote), sem publicar'), () => chk(false, '[A] "Publicar no site…" abre o plano'));
    await P.evaluate(() => closeDrawer && closeDrawer(true)).catch(() => {});
    // nada foi gravado por filtrar, ordenar, paginar, abrir menus e cancelar
    const depois = foto();
    chk(depois === antes, `[F] filtrar, ordenar, paginar e abrir menus não gravou nada no banco (${antes} → ${depois})`);

    // ---------------- [G] teclado e nomes ----------------
    await P.evaluate(() => document.activeElement && document.activeElement.blur()); await P.keyboard.press('f');
    chk(await P.evaluate(() => document.activeElement && document.activeElement.id === 'proj-q'), '[G] tecla F foca a busca');
    chk(await P.evaluate(() => [...document.querySelectorAll('#v-projetos button, #v-projetos select, #v-projetos input, #v-projetos summary, #v-projetos a')].filter(e => e.offsetParent).every(e => (e.getAttribute('aria-label') || e.textContent || e.title || (e.labels && e.labels[0] && e.labels[0].textContent) || '').trim())), '[G] todo controle à vista tem nome acessível');
    chk(await P.evaluate(() => [...document.querySelectorAll('#projetos-body tr.lst-linha')].every(r => { const t = r.querySelector('.tag.sit'); return t && t.textContent.trim().length > 3; })), '[G] toda linha tem a situação em texto (não só cor)');
    chk(await P.evaluate(() => [...document.querySelectorAll('#projetos-body tr.lst-linha a.btn')].every(a => /^Abrir projeto F\d{3}-P\d{4}$/.test(a.getAttribute('aria-label')) && a.textContent === 'Abrir projeto')), '[A][G] toda linha tem "Abrir projeto" (link, com o código no nome acessível)');
    await P.click('[data-proj-dens="comp"]'); await P.waitForTimeout(200);
    chk(await P.evaluate(() => document.getElementById('v-projetos').classList.contains('dens-comp') && getComputedStyle(document.querySelector('#projetos-body .mini')).display === 'none' && LISTA_MEM.get('projetos.dens') === 'comp'), '[D] densidade Compacta: sem miniatura e lembrada');
    await P.click('[data-proj-dens="conf"]');
    await ctx.close();

    // ---------------- [A] operador e leitura ----------------
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await projetos(op.page); await op.page.fill('#proj-q', 'F077-P000'); await op.page.waitForTimeout(350); await assentar(op.page);
    const mOp = await menu(op.page, 'F077-P0002');
    chk(!mOp.includes('Voltar para rascunho…') && !mOp.includes('Autorizar para o site…') && mOp.includes('Exportar (CSV)') && !(await op.page.locator('#v-projetos .hdr [data-pode="projeto.criar"]').isVisible()),
      `[A] operador: sem Voltar para rascunho, Autorizar e Novo projeto (admin): ${JSON.stringify(mOp)}`);
    await op.ctx.close();
    const lei = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await projetos(lei.page); await lei.page.fill('#proj-q', 'F077-P000'); await lei.page.waitForTimeout(350); await assentar(lei.page);
    const mLe = await menu(lei.page, 'F077-P0001');
    chk(JSON.stringify(mLe) === '["Imprimir etiqueta da pasta","Exportar (CSV)"]' && await lei.page.locator('#projetos-body a.btn').first().isVisible(), `[A] quem só lê: "Abrir projeto" e o "⋯" só com Imprimir etiqueta e Exportar: ${JSON.stringify(mLe)}`);
    await lei.page.locator('#projetos-body .proj-sel').first().check(); await lei.page.waitForTimeout(200);
    chk(!(await lei.page.locator('#proj-bulk-pub').isVisible()) && !(await lei.page.locator('#proj-bulk [data-pode="projetos.lote"]').first().isVisible()), '[A] quem só lê: a barra de seleção não oferece Publicar, Autorizar nem Voltar para rascunho');
    await lei.ctx.close();

    // ---------------- [H] 390 / zoom 200% / 1024 / 1366 / 1920 ----------------
    for (const [w, nome] of [[390, 'celular'], [683, 'zoom 200% (1366 px)'], [1024, 'tablet'], [1366, 'notebook'], [1920, 'monitor']]) {
      const m = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w, h: 900 });
      await projetos(m.page);
      const g = await m.page.evaluate(() => {
        const rows = [...document.querySelectorAll('#projetos-body tr.lst-linha')].slice(0, 8), sobre = [];
        rows.forEach(r => { const cs = [...r.children].filter(c => c.offsetParent && c.getBoundingClientRect().width); for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) { const a = cs[i].getBoundingClientRect(), b = cs[j].getBoundingClientRect(); if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) sobre.push(r.dataset.nav); } });
        const vis = s => { const e = document.querySelector('#projetos-body tr.lst-linha ' + s); return !!e && getComputedStyle(e).display !== 'none'; };
        const tw = document.querySelector('#v-projetos .lista-tw'), tab = document.querySelector('#v-projetos .proj-tab');
        return { sw: document.documentElement.scrollWidth, iw: window.innerWidth, mainSw: document.querySelector('.main').scrollWidth, mainW: document.querySelector('.main').clientWidth, tab: tab.scrollWidth <= tw.clientWidth + 1,
          thead: getComputedStyle(document.querySelector('.proj-tab thead')).display, fundo: vis('.c-pj-fundo'), cod: vis('.c-pj-cod'), arq: vis('.c-pj-arq'), sit: vis('.c-pj-sit'),
          acao: rows.every(r => { const a = r.querySelector('.c-acao a.btn'); return a && a.offsetParent && a.getBoundingClientRect().right <= window.innerWidth; }), codigo: rows.every(r => [...r.querySelectorAll('.code')].some(c => c.offsetParent)), sobre };
      });
      chk(g.sw <= g.iw + 1 && g.mainSw <= g.mainW + 1 && g.tab, `[H] ${nome}: sem rolagem lateral (${g.sw}/${g.iw}, main ${g.mainSw}/${g.mainW}, tabela cabe: ${g.tab})`);
      chk(!g.sobre.length, `[H] ${nome}: nenhuma célula por cima de outra ${JSON.stringify(g.sobre)}`);
      chk(g.acao && g.codigo && g.sit, `[H] ${nome}: "Abrir projeto", o código e a situação de toda linha continuam à vista`);
      if (w < 721) chk(g.thead === 'none', `[H] ${nome}: as linhas viram cartões (sem cabeçalho de tabela)`);
      if (w === 1024) chk(g.thead !== 'none' && !g.fundo && g.arq, `[H] ${nome}: tabela, sem as colunas secundárias (Fundo e Data vão para baixo do nome), com Arquiteto e ação`);
      if (w === 1920) chk(g.fundo && g.cod && g.arq, `[H] ${nome}: todas as colunas`);
      if (w === 1366) { const fx = await m.page.evaluate(async () => { document.querySelectorAll('#projetos-body tr.lst-linha')[14].scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 400)); return { th: Math.round(document.querySelector('.proj-tab thead th').getBoundingClientRect().top), top: Math.round(document.querySelector('.top').getBoundingClientRect().bottom) }; });
        chk(Math.abs(fx.th - fx.top) <= 2, `[D] ${nome}: o cabeçalho da tabela fica fixo logo abaixo do topo durante a rolagem (${JSON.stringify(fx)})`); }
      await m.ctx.close();
    }

    // ---------------- [P] desempenho com milhares de projetos ----------------
    py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F078','Fundo Volume Projetos','FVP',1)")
for n in range(1, 3001):
    P = 'F078-P%04d' % n
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F078',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,status_site) VALUES (?,'F078',?,?,?,?)", (P, n, 'Projeto volume %d' % n, 1940 + n % 50, 'no_ar' if n % 3 else 'nao_publicado'))
`);
    const v = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const t0 = Date.now(); await projetos(v.page); const tTela = Date.now() - t0;
    const perf = await v.page.evaluate(async () => { const t = async u => { const a = performance.now(); const r = await (await fetch(u)).json(); return [Math.round(performance.now() - a), r]; };
      const [l, r] = await t('/api/projetos?por_pagina=25'), [s] = await t('/api/projetos/resumo'), [q, rq] = await t('/api/projetos?q=volume%202999&por_pagina=25'), [f] = await t('/api/projetos/filtros');
      return { l, total: r.total, s, q, achou: rq.itens.map(x => x.codigo), f, dom: document.querySelectorAll('#projetos-body tr.lst-linha').length }; });
    chk(perf.total > 3000 && perf.dom === 25 && perf.l < 3000 && perf.s < 4000 && perf.q < 3000 && perf.f < 3000 && JSON.stringify(perf.achou) === '["F078-P2999"]',
      `[P] ${perf.total} projetos: 25 linhas no DOM; lista ${perf.l} ms, contagens ${perf.s} ms, busca ${perf.q} ms (${perf.achou}), opções ${perf.f} ms; tela pronta em ${tTela} ms`);
    await v.ctx.close();
    py("con.execute(\"DELETE FROM projeto WHERE codigo LIKE 'F078-%'\")\ncon.execute(\"DELETE FROM numero_p WHERE fundo_codigo='F078'\")");
  } catch (e) { chk(false, 'o teste quebrou: ' + (e.stack || e.message)); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
