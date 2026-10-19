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
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
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
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const api = (url, opt = {}) => page.evaluate(async ([u, o]) => { const r = await fetch(u, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...o }); return { status: r.status, json: await r.json().catch(() => null) }; }, [url, opt]);
  const grupo = k => `#err-body tr.err-gr[data-err-gr="${k}"]`;
  const linhasDo = k => page.locator(`#err-body tr[data-err-grupo="${k}"]`);
  const recarregou = async () => { await page.waitForTimeout(300); await page.waitForFunction(() => document.querySelector('#err-body tr.err-gr, #err-body td.empty'), null, { timeout: 10000 }); await page.waitForTimeout(400); };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { try { localStorage.removeItem('camp.lista.erros.filtros'); localStorage.removeItem('camp.lista.erros.aba'); } catch (_) {} nav('erros'); });
    await page.waitForSelector(grupo('F003-P9001'), { timeout: 15000 }); await page.waitForTimeout(500);

    // ---- agrupado por projeto, com o nome e a contagem; "talvez" separado no topo; o resolvido sozinho não aparece ----
    const gtxt = await page.textContent(grupo('F003-P9001'));
    chk(/Projeto de teste da revisão 9001/.test(gtxt) && /F003-P9001/.test(gtxt) && /8 problemas/.test(gtxt) && /6 folhas retiradas pelo CAMP Vision/.test(gtxt) && /2 folhas recusadas/.test(gtxt), 'grupo do projeto com o NOME, o código e quantos problemas de cada tipo: "' + gtxt.replace(/\s+/g, ' ').trim().slice(0, 160) + '"');
    chk(/Residência Riviera/.test(await page.textContent(grupo('F023-P0011'))) && /bloqueiam a publicação/.test(await page.textContent(grupo('F023-P0011'))), 'grupo F023-P0011 com o nome e "2 bloqueiam a publicação"');
    const primeiro = await page.getAttribute('#err-body tr.err-gr', 'data-err-gr');
    chk(primeiro === '~talvez' && /D00077/.test(await linhasDo('~talvez').first().textContent()) && /não existe mais/.test(await page.textContent(grupo('~talvez') + ' ~ tr')), 'a folha que não existe mais fica em "Podem já estar resolvidos", no topo, separada');
    chk(!(await page.$('#err-body tr[data-err-linha] .code[title="F003-P9001-1972-S01-D00099"]')), 'a retirada que um admin já devolveu não aparece entre os abertos (fechou sozinha)');
    const d99 = (await api('/api/erros?situacao=todos&q=D00099')).json[0];
    chk(d99 && d99.situacao === 'corrigido' && /^Resolvido sozinho: Um admin devolveu/.test(d99.resolucao || ''), '... e ficou registrada como "Resolvido sozinho" com o porquê');
    const riv = linhasDo('F023-P0011').filter({ hasText: 'D00005' });
    chk(/O que fazer: Abra a folha e use Virar/.test(await riv.textContent()) && (await riv.locator('button.err-acao').count()) === 1 && /Abrir a folha para girar/.test(await riv.locator('button.err-acao').textContent()), 'cada linha diz o que fazer e tem UM botão que resolve ("Abrir a folha para girar")');
    chk(!(await page.$('#v-erros thead th.sortable')), 'a tabela agrupada não tem colunas de ordenar (quebrariam os grupos)');

    // ---- filtros e busca ----
    await page.selectOption('#err-orig', 'site'); await recarregou();
    chk((await page.locator('#err-body tr[data-err-linha]').count()) === 1 && /fotógrafa/.test(await page.textContent('#err-body')), 'filtro de origem "Visitante do site": só o problema do visitante');
    chk(!(await page.isHidden('#err-limpar')), '"Limpar filtros" aparece quando há filtro');
    await page.selectOption('#err-orig', ''); await page.selectOption('#err-grav', 'bloqueia'); await recarregou();
    chk((await page.locator('#err-body tr[data-err-linha]').count()) === 2, 'filtro de gravidade "Bloqueia": os 2 que bloqueiam');
    await page.click('#err-limpar'); await recarregou();
    await page.fill('#err-q', 'riviera'); await page.waitForTimeout(700); await recarregou();
    chk((await page.locator('#err-body tr.err-gr').count()) === 1 && !!(await page.$(grupo('F023-P0011'))), 'busca pelo NOME do projeto ("riviera") mostra só esse projeto');
    await page.click('#err-limpar'); await recarregou();
    await page.click(grupo('F023-P0011') + ' [data-err-so-proj]'); await page.waitForFunction(() => location.hash === '#erros/F023-P0011'); await recarregou();
    chk((await page.locator('#err-body tr.err-gr').count()) === 1 && /F023-P0011/.test(await page.textContent('#err-proj-filtro')), '"Só este projeto" vai para #erros/F023-P0011 e mostra só ele');
    await page.click('[data-err-tirar-proj]'); await page.waitForFunction(() => location.hash === '#erros'); await recarregou();

    // ---- devolver uma folha retirada pelo detalhe: o problema fecha e a lista fica no mesmo lugar ----
    await page.setViewportSize({ width: 1366, height: 560 });   // a lista mais comprida que a tela: o fim dela não limita a rolagem
    const l11 = page.locator('#err-body tr[data-err-linha]').filter({ hasText: 'D00014' });
    await l11.scrollIntoViewIfNeeded();
    const antes = await page.evaluate(() => { const r = [...document.querySelectorAll('#err-body tr[data-err-linha]')].find(x => /D00014/.test(x.textContent)); mainEl.scrollTop += r.getBoundingClientRect().top - 200;
      const prox = r.nextElementSibling; return { top: r.getBoundingClientRect().top, prox: prox && prox.dataset.errLinha, scroll: mainEl.scrollTop }; });
    chk(/Devolver à revisão/.test(await l11.locator('button.err-acao').textContent()), 'folha retirada: o botão da linha é "Devolver à revisão"');
    await l11.locator('button.err-acao').click();
    await page.waitForSelector('#err-dev-mot', { timeout: 8000 });
    const dtxt = await page.textContent('#d-body');
    chk(/Folha retirada pelo CAMP Vision/.test(await page.textContent('#d-title')) && /O que aconteceu/.test(dtxt) && /O que fazer/.test(dtxt) && /Projeto de teste da revisão 9001/.test(dtxt) && /A retirada está certa/.test(dtxt), 'detalhe: título claro, o que aconteceu, o que fazer, o projeto (com link) e as duas saídas');
    await page.click('[data-err-devolver]'); await page.waitForTimeout(300);
    chk(/Explique por que/.test(await page.textContent('#toast')), 'devolver sem motivo pede a explicação');
    await page.fill('#err-dev-mot', 'a folha está boa'); await page.click('[data-err-devolver]');
    await page.waitForFunction(() => /devolvida à revisão/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await recarregou(); await page.waitForTimeout(300);
    const depois = await page.evaluate(id => { const r = document.querySelector(`#err-body tr[data-err-linha="${id}"]`); return { top: r ? r.getBoundingClientRect().top : null, scroll: mainEl.scrollTop }; }, antes.prox);
    chk(!(await page.$('#err-body .code[title="F003-P9001-1972-S01-D00014"]')), 'a folha devolvida sai da lista de abertos (o problema fechou)');
    chk(antes.scroll > 0 && Math.abs(depois.scroll - antes.scroll) < 40 && depois.top !== null && Math.abs(depois.top - antes.top) < 40, `depois de resolver, a lista fica no MESMO lugar: o problema seguinte ocupa o lugar do resolvido (rolagem ${antes.scroll} -> ${depois.scroll}; topo ${Math.round(antes.top)} -> ${Math.round(depois.top)})`);
    await page.setViewportSize({ width: 1366, height: 900 });

    // ---- resolver o grupo inteiro em lote, com frase obrigatória, e Desfazer ----
    await page.check(grupo('F003-P9001') + ' [data-err-sel-grupo]');
    chk(await page.isVisible('#err-bulk') && /7 selecionados/.test(await page.textContent('#err-bulk-n')), 'marcar o grupo seleciona os 7 abertos dele e mostra a barra');
    await page.click('#err-bulk [data-err-lote="corrigido"]');
    chk(/Escreva em uma frase/.test(await page.textContent('#err-bulk-err')), 'em lote, "Marcar como corrigido" sem a frase pede a explicação');
    await page.fill('#err-bulk-res', 'retiradas conferidas: estavam certas');
    await page.click('#err-bulk [data-err-lote="corrigido"]');
    await page.waitForFunction(() => /7 problemas marcados como corrigidos/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await recarregou();
    chk(!(await page.$(grupo('F003-P9001'))) && !(await page.isVisible('#err-bulk')), 'os 7 fecham de uma vez e o grupo some dos abertos');
    const fechados = (await api('/api/erros?situacao=corrigido&projeto=F003-P9001')).json.filter(x => x.resolucao === 'retiradas conferidas: estavam certas');
    chk(fechados.length === 7, 'no servidor: 7 corrigidos com a mesma frase (' + fechados.length + ')');
    await page.click('#toast button'); await page.waitForFunction(() => /Desfeito/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await recarregou();
    chk(!!(await page.$(grupo('F003-P9001'))) && (await linhasDo('F003-P9001').count()) === 7, '"Desfazer" reabre os 7');

    // ---- a ação leva ao lugar certo e o Voltar traz a lista ----
    await page.click('#err-body tr[data-err-linha]:has-text("D00005") button.err-acao');
    await page.waitForFunction(() => location.hash === '#projeto/F023-P0011', null, { timeout: 8000 });
    await page.waitForFunction(() => (document.getElementById('d-title') || {}).textContent === 'Revisar folha' && /D00005/.test((document.getElementById('d-sub') || {}).textContent || ''), null, { timeout: 15000 });
    chk(true, '"Abrir a folha para girar" abre o projeto e a revisão da folha D00005 (com os botões de virar)');
    await page.evaluate(() => closeDrawer(true)); await page.goBack(); await page.waitForFunction(() => location.hash === '#erros', null, { timeout: 8000 }); await recarregou();
    chk(!!(await page.$(grupo('F023-P0011'))), 'o Voltar do navegador traz a lista de Problemas de novo');

    // ---- operador: o que é de admin aparece desabilitado com "peça a um admin" ----
    const ctxOp = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const op = await ctxOp.newPage();
    op.on('pageerror', e => erros.push('pageerror (operador): ' + e.message));
    await op.goto(BASE + '/'); await op.fill('#lg-email', 'operador@camp.arq.br'); await op.fill('#lg-senha', 'senha-operador-123'); await op.press('#lg-senha', 'Enter');
    await op.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await op.evaluate(() => nav('erros')); await op.waitForSelector(grupo('F023-P0011'), { timeout: 15000 });
    const mv = op.locator('#err-body tr[data-err-linha]:has-text("D00009") button.err-acao');
    chk(await mv.isDisabled() && /peça a um admin/.test(await op.textContent('#err-body tr[data-err-linha]:has-text("D00009")')), 'operador: "Mover para o projeto certo" desabilitado, com "peça a um admin"');
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
