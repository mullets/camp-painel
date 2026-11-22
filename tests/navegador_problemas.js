// Tela de Problemas no navegador de verdade (Playwright + Chromium), depois de "a pasta de problemas tá confusa" (19/10).
// Prova: lista agrupada por projeto com o NOME e a contagem; o "talvez resolvido" num grupo separado no topo; o que se resolveu
// sozinho (folha retirada já devolvida) não aparece aberto; filtros (gravidade, tipo, origem, busca pelo nome) e "Só este projeto"
// (#erros/<projeto>); cada linha diz o que fazer e tem UM botão que resolve; devolver uma folha retirada pelo detalhe fecha o
// problema e a lista volta no MESMO lugar; resolver o grupo inteiro em lote (com frase obrigatória) e Desfazer; o botão
// "Abrir a folha para girar" abre a revisão da folha no projeto e o Voltar traz a lista de volta; no celular não há rolagem lateral;
// nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/prob.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/prob.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8931)
//   CAMP_DB_PATH=/tmp/prob.db CAMP_BASE=http://127.0.0.1:8931 node tests/navegador_problemas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8931', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// 6 folhas retiradas pelo CAMP Vision no F003-P9001 (uma já devolvida por um admin), 2 recusadas; problemas da revisão no F023-P0011
// (D00005 virada, D00009 de outro projeto); uma folha que não existe mais (vai para "Podem já estar resolvidos").
py(`
lid = con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo='F003-P9001'").fetchone()[0]
def erro(g, cat, o, cod, d, ch=None, dias=1):
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por,chave,criado_em) VALUES (?,?,?,?,?,?,?,datetime('now',?))", (g, cat, o, cod, d, 'CAMP Vision' if o == 'campvision' else 'operador@camp.arq.br', ch, '-%d days' % dias))
for n, mot in ((10, 'duplicata exata'), (11, 'carimbo de outro escritório'), (12, 'imagem ilegível'), (13, 'folha em branco'), (14, 'folha em branco'), (15, 'duplicata')):
    cod = 'F003-P9001-1972-S01-D%05d' % n
    erro('corrigir', 'outro', 'campvision', cod, 'O CAMP Vision retirou esta folha do lote: %s. Ela não entrou na revisão.' % mot, 'campvision:retirado:' + cod, 3)
for n in (20, 21):
    erro('corrigir', 'codigo', 'campvision', 'F003-P9001', 'Folha do lote que não entrou no painel: F003-P9001-1972-S01-D%05d: código repetido.' % n, 'campvision:recusada:F003-P9001:F003-P9001-1972-S01-D%05d' % n, 3)
erro('corrigir', 'outro', 'campvision', 'F003-P9001-1972-S01-D00099', 'O CAMP Vision retirou esta folha do lote: confiança baixa.', 'campvision:retirado:F003-P9001-1972-S01-D00099', 5)
con.execute("INSERT INTO cv_resposta (lote_id, projeto_codigo, tipo, chave, acao, motivo, por) VALUES (?,?,?,?,?,?,?)", (lid, 'F003-P9001', 'retirado', 'F003-P9001-1972-S01-D00099', 'devolver', 'está boa', 'rafael@camp.arq.br'))
erro('bloqueia', 'orientacao', 'revisao', 'F023-P0011-1959-S01-D00005', 'Folha de cabeça para baixo', None, 2)
erro('bloqueia', 'projeto_errado', 'operador', 'F023-P0011-1959-S01-D00009', 'Folha de Araruama dentro deste projeto', None, 12)
erro('aviso', 'credito', 'site', 'F023-P0011-1959-S01-D00002', 'Visitante informa: a fotógrafa é outra', None, 20)
erro('aviso', 'outro', 'revisao', 'F026-P0001-1968-S01-D00077', 'Folha com mancha', None, 40)
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);   // 20/10 (CAMP-069): miniatura de folha sem imagem: 404 esperado (a tela mostra "Sem imagem")
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const api = (url, opt = {}) => page.evaluate(async ([u, o]) => { const r = await fetch(u, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...o }); return { status: r.status, json: await r.json().catch(() => null) }; }, [url, opt]);
  // CAMP-PROB-UX (22/11/2026): a lista virou a Central de Problemas (linhas compactas, painel ao lado). As provas de antes continuam,
  // na tela nova: o que se resolveu sozinho não aparece; "Podem já estar resolvidos" é um filtro rápido; filtros, busca e "Só este projeto";
  // a ação que resolve fica no painel; devolver a folha retirada fecha o problema e a lista fica no lugar; resolver em lote com frase e
  // Desfazer; "Abrir a folha para girar" leva à revisão e o Voltar traz a lista; operador vê o que é de admin desabilitado.
  const linha = t => page.locator('#err-body [data-err-linha]').filter({ hasText: t });
  const recarregou = async () => { await page.waitForTimeout(300); await page.waitForFunction(() => document.getElementById('err-body').getAttribute('aria-busy') === 'false' && document.querySelector('#err-body [data-err-linha], #err-body .estado-vazio'), null, { timeout: 10000 }); await page.waitForTimeout(400); };
  const abrirFiltros = async () => { if (await page.isHidden('#cp-filtros-mais')) await page.click('#cp-filtros-btn'); };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { try { localStorage.removeItem('camp.lista.erros.central'); } catch (_) {} nav('erros/~aba=todos&por=100'); });
    await page.waitForSelector('#err-body [data-err-linha]', { timeout: 15000 }); await recarregou();

    // ---- contexto (fundo › projeto › folha) com o NOME do projeto; o resolvido sozinho não aparece; o "talvez" num filtro rápido ----
    const lp = linha('D00011');
    chk(/Projeto de teste da revisão 9001/.test(await lp.textContent()) && /F003 · P9001/.test(await lp.textContent()), 'cada linha mostra o NOME do projeto e o código (fundo › projeto › folha)');
    chk(/Residência Riviera/.test(await linha('D00005').textContent()) && /Crítico/.test(await linha('D00005').textContent()), 'linha do F023-P0011 com o nome e a severidade "Crítico"');
    chk(!(await page.$('#err-body [data-err-folha="F003-P9001-1972-S01-D00099"]')), 'a retirada que um admin já devolveu não aparece entre os abertos (fechou sozinha)');
    const d99 = (await api('/api/erros?situacao=todos&q=D00099')).json[0];
    chk(d99 && d99.situacao === 'corrigido' && /^Resolvido sozinho: Um admin devolveu/.test(d99.resolucao || ''), '... e ficou registrada como "Resolvido sozinho" com o porquê');
    const d77 = (await api('/api/problemas?aba=concluidos&q=D00077')).json.itens[0];
    chk(d77 && d77.resolvido_pelo_sistema && /não existe mais/.test(d77.resolucao || '') && (await page.$('[data-cp-chip="talvez"]')), 'a folha que não existe mais fecha sozinha ("pelo sistema", em Concluídos); o que só TALVEZ está resolvido tem o filtro "Podem já estar resolvidos"');
    await linha('D00005').locator('.cp-cta').click(); await page.waitForSelector('#d-body .cp-ident');
    chk(/Abra a folha e use Virar/.test(await page.textContent('#d-body')) && (await page.locator('#d-body button.err-acao').count()) === 1 && /Abrir a folha para girar/.test(await page.textContent('#d-body button.err-acao')), 'o painel diz o que fazer e tem UM botão que resolve ("Abrir a folha para girar")');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);

    // ---- filtros e busca ----
    await abrirFiltros(); await page.selectOption('#err-orig', 'site'); await recarregou();
    chk((await page.locator('#err-body [data-err-linha]').count()) === 1 && /fotógrafa/.test(await page.textContent('#err-body')), 'filtro de origem "Visitante do site": só o problema do visitante');
    chk(!(await page.isHidden('[data-err-limpar-tudo]')), '"Limpar filtros" aparece quando há filtro');
    await page.selectOption('#err-orig', ''); await recarregou(); await page.selectOption('#err-grav', 'bloqueia'); await recarregou();
    chk((await page.locator('#err-body [data-err-linha]').count()) === 2, 'filtro de severidade "Crítico (bloqueia)": os 2 que bloqueiam');
    await page.click('[data-err-limpar-tudo]'); await recarregou();
    await page.fill('#err-q', 'riviera'); await page.waitForTimeout(700); await recarregou();
    const riv = await page.$$eval('#err-body [data-err-linha]', ls => ls.map(l => l.textContent));
    chk(riv.length >= 1 && riv.every(t => /Residência Riviera/.test(t)), 'busca pelo NOME do projeto ("riviera") mostra só esse projeto');
    await page.fill('#err-q', ''); await page.waitForTimeout(700); await recarregou();
    await page.evaluate(() => nav('erros/F023-P0011')); await recarregou();
    const so = await page.$$eval('#err-body [data-err-linha]', ls => ls.map(l => l.textContent));
    chk(so.length >= 1 && so.every(t => /F023 · P0011/.test(t)) && /Projeto: F023-P0011/.test(await page.textContent('#err-filtro-ativo')) && /projeto=F023-P0011/.test(await page.evaluate(() => location.hash)), '"Só este projeto" (#erros/F023-P0011) mostra só ele, com o chip do filtro');
    await page.click('[data-cp-tirar="projeto"]'); await recarregou();

    // ---- devolver uma folha retirada pelo painel: o problema fecha e a lista fica no mesmo lugar ----
    const l11 = linha('D00014');
    await l11.locator('.cp-cta').click();
    await page.waitForSelector('#err-dev-mot', { timeout: 8000 });
    const antes = await page.evaluate(() => mainEl.scrollTop);
    const dtxt = await page.textContent('#d-body');
    chk(/Folha retirada pelo CAMP Vision/.test(await page.textContent('#d-title')) && /Qual é o problema\?/.test(dtxt) && /O que precisa ser decidido\?/.test(dtxt) && /Projeto de teste da revisão 9001/.test(dtxt) && /A retirada está certa/.test(dtxt), 'painel: título claro, qual é o problema, o que decidir, o projeto (com link) e as duas saídas');
    await page.click('[data-err-devolver]'); await page.waitForTimeout(300);
    chk(/Explique por que/.test(await page.textContent('#toast')), 'devolver sem motivo pede a explicação');
    await page.fill('#err-dev-mot', 'a folha está boa'); await page.click('[data-err-devolver]');
    await page.waitForFunction(() => /devolvida à revisão/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await recarregou(); await page.waitForTimeout(300);
    chk(!(await page.$('#err-body [data-err-folha="F003-P9001-1972-S01-D00014"]')), 'a folha devolvida sai da lista de abertos (o problema fechou)');
    const depois = await page.evaluate(() => mainEl.scrollTop);
    chk(Math.abs(depois - antes) < 60, `depois de resolver, a lista fica no MESMO lugar (rolagem ${antes} -> ${depois})`);

    // ---- resolver vários em lote, com frase obrigatória, e Desfazer ----
    await page.fill('#err-q', 'F003-P9001'); await page.waitForTimeout(700); await recarregou();
    const n9001 = await page.locator('#err-body .err-sel').count();
    await page.locator('#err-body .err-sel').first().check(); await page.click('[data-cp-sel-pagina]');
    chk(await page.isVisible('#err-bulk') && new RegExp(n9001 + ' selecionados').test(await page.textContent('#err-bulk-n')), `"Selecionar os desta página" marca os ${n9001} abertos do projeto e mostra a barra`);
    await page.click('#err-bulk [data-err-lote="corrigido"]');
    chk(/Escreva em uma frase/.test(await page.textContent('#err-bulk-err')), 'em lote, "Marcar como corrigido" sem a frase pede a explicação');
    await page.fill('#err-bulk-res', 'retiradas conferidas: estavam certas');
    await page.click('#err-bulk [data-err-lote="corrigido"]');
    await page.waitForSelector('#conf-ov', { timeout: 5000 }); await page.click('#conf-ov [data-conf="sim"]');   // UX-20: a prévia antes de fechar vários
    await page.waitForFunction(n => new RegExp(n + ' problemas marcados como corrigidos').test(document.getElementById('toast').textContent), n9001, { timeout: 8000 }); await recarregou();
    chk((await page.locator('#err-body [data-err-linha]').count()) === 0 && !(await page.isVisible('#err-bulk')), 'os escolhidos fecham de uma vez e saem dos abertos');
    const fechados = (await api('/api/erros?situacao=corrigido&projeto=F003-P9001')).json.filter(x => x.resolucao === 'retiradas conferidas: estavam certas');
    chk(fechados.length === n9001, `no servidor: ${n9001} corrigidos com a mesma frase (${fechados.length})`);
    await page.click('#toast button'); await page.waitForFunction(() => /Desfeito/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await recarregou();
    chk((await page.locator('#err-body [data-err-linha]').count()) === n9001, '"Desfazer" reabre todos');
    await page.fill('#err-q', ''); await page.waitForTimeout(700); await recarregou();

    // ---- a ação leva ao lugar certo e o Voltar traz a lista ----
    await linha('D00005').locator('.cp-cta').click(); await page.waitForSelector('#d-body button.err-acao');
    await page.click('#d-body button.err-acao');
    await page.waitForFunction(() => location.hash === '#projeto/F023-P0011', null, { timeout: 8000 });
    await page.waitForFunction(() => (document.getElementById('d-title') || {}).textContent === 'Revisar folha' && /D00005/.test((document.getElementById('d-sub') || {}).textContent || ''), null, { timeout: 15000 });
    chk(true, '"Abrir a folha para girar" abre o projeto e a revisão da folha D00005 (com os botões de virar)');
    await page.evaluate(() => closeDrawer(true)); await page.goBack(); await page.waitForFunction(() => /^#erros/.test(location.hash), null, { timeout: 8000 }); await recarregou();
    chk(!!(await page.$('#err-body [data-err-folha="F023-P0011-1959-S01-D00005"]')), 'o Voltar do navegador traz a lista de Problemas de novo');

    // ---- operador: o que é de admin aparece desabilitado com "peça a um admin" ----
    const ctxOp = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const op = await ctxOp.newPage();
    op.on('pageerror', e => erros.push('pageerror (operador): ' + e.message));
    await op.goto(BASE + '/'); await op.fill('#lg-email', 'operador@camp.arq.br'); await op.fill('#lg-senha', 'senha-operador-123'); await op.press('#lg-senha', 'Enter');
    await op.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await op.evaluate(() => nav('erros/~aba=todos&por=100')); await op.waitForSelector('#err-body [data-err-linha]', { timeout: 15000 });
    await op.locator('#err-body [data-err-linha]').filter({ hasText: 'D00009' }).locator('.cp-cta').click(); await op.waitForSelector('#d-body .cp-ident');
    const mv = op.locator('#d-body button.err-acao');
    chk(await mv.isDisabled() && /peça a um admin/.test(await op.textContent('#d-body')), 'operador: "Mover para o projeto certo" desabilitado, com "peça a um admin"');
    await ctxOp.close();

    // ---- celular ----
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(600);
    const lateral = await page.evaluate(() => mainEl.scrollWidth - mainEl.clientWidth);
    chk(lateral <= 1, 'no celular a lista cabe na largura (sem rolagem lateral: ' + lateral + 'px)');
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
