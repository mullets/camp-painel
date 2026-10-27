// Problemas e Precisa de você no navegador de verdade (Playwright + Chromium), cards UX do board "CAMP Acervos — UX do painel".
// UX-06: com centenas de problemas abertos, a tela abre com as abas e a lista certas (direto pela URL, voltando de um projeto,
//        com um filtro guardado de outro dia); com filtro, o estado vazio diz QUAL filtro está ativo e tem "Limpar".
// UX-20: "todos deste tipo/projeto", prévia antes de fechar vários e Desfazer; "mensagens repetidas" → Ver → Mesclar (com Desfazer).
// UX-19: avisos em aba própria ("Abertos" = bloqueia + corrigir); os números do menu seguem "itens que pedem ação de você".
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/ux.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/ux.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8943)
//   CAMP_DB_PATH=/tmp/x/ux.db CAMP_BASE=http://127.0.0.1:8943 node tests/navegador_problemas_ux.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8943', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// 574 problemas abertos, como na produção de 26/10: 428 avisos, 92 "corrigir" e 54 que bloqueiam, espalhados pelos projetos do banco de teste.
py(`
import random
random.seed(7)
if not con.execute("SELECT 1 FROM erro WHERE descricao LIKE 'Problema sintético%' LIMIT 1").fetchone():
    itens = [r[0] for r in con.execute("SELECT codigo FROM item")]
    projs = [r[0] for r in con.execute("SELECT codigo FROM projeto")]
    for n in range(574):
        g = 'aviso' if n < 428 else 'corrigir' if n < 520 else 'bloqueia'
        cod = random.choice(itens) if n % 3 else random.choice(projs)
        con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por,criado_em) VALUES (?,?,?,?,?,?,datetime('now',?))",
                    (g, random.choice(['orientacao','espelhado','metadado','credito','outro']), 'campvision' if n % 2 else 'revisao', cod, 'Problema sintético %d' % n, 'CAMP Vision', '-%d days' % (n % 30)))
    for _ in range(3):   # UX-20: a mesma mensagem 3 vezes (o CAMP Vision registrou de novo a cada leitura)
        con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('aviso','outro','campvision',?,'Aviso menor do exiftool: tag duplicada','CAMP Vision')", (projs[0],))
`);
const ABERTOS = +py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')").fetchone()[0])`);
const AVISOS = +py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='aviso'").fetchone()[0])`);
const PEDEM = ABERTOS - AVISOS;   // UX-19: a aba "Abertos" é o que bloqueia ou pede correção

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/miniatura/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const entrar = async () => { await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); };
  const pronto = async () => { await page.waitForTimeout(300); await page.waitForFunction(() => document.querySelector('#err-body tr.err-gr, #err-body td.empty') && document.querySelector('#err-abas b'), null, { timeout: 15000 }); await page.waitForTimeout(500); };
  const aba = async k => +(((await page.textContent(`#err-abas [data-err-sit="${k}"] b`).catch(() => '')) || '').replace(/\D/g, '') || 0);
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await entrar();

    // ================= UX-06 =================
    // 1) filtro esquecido de outro dia (guardado sem data, como antes do UX-06): a tela abre SEM ele, com a lista e as abas certas
    await page.evaluate(() => { localStorage.setItem('camp.lista.erros.filtros', JSON.stringify({ categoria: 'duplicata', q: '' })); localStorage.setItem('camp.lista.erros.aba', JSON.stringify('abertos')); localStorage.removeItem('camp.lista.erros.filtros_em'); });
    await page.goto(BASE + '/#erros'); await page.reload(); await entrar(); await pronto();
    chk(await aba('pedem_acao') === PEDEM && await aba('todos') === ABERTOS, `UX-06: aberta direto pela URL, as abas mostram os números reais (filtro de outro dia não volta): ${await aba('pedem_acao')}/${await aba('todos')}`);
    chk((await page.locator('#err-body tr[data-err-linha]').count()) > 0 && !(await page.$('#err-body td.empty')), 'UX-06: a lista carrega ao abrir (sem "Nenhum problema com estes filtros")');
    chk(await page.isHidden('#err-filtro-ativo'), 'UX-06: sem filtro, nenhum aviso de filtro ativo');

    // 2) filtro que não acha nada: o vazio diz QUAL filtro, quantos existem sem ele, e tem "Limpar"
    await page.selectOption('#err-cat', 'duplicata'); await pronto();
    const vazio = (await page.textContent('#err-body')).replace(/\s+/g, ' ');
    chk(/Filtro ativo: Tipo: Duplicata/.test(vazio) && new RegExp('Sem filtro há ' + ABERTOS.toLocaleString('pt-BR').replace('.', '\\.') + ' problemas abertos').test(vazio), 'UX-06: o estado vazio explica o filtro ativo e quantos há sem ele: "' + vazio.slice(0, 160) + '"');
    chk(await page.isVisible('#err-body [data-err-limpar-tudo]'), 'UX-06: o estado vazio tem o botão "Limpar"');
    chk(await page.isVisible('#err-filtro-ativo') && /Tipo: Duplicata/.test(await page.textContent('#err-filtro-ativo')), 'UX-06: acima da lista, "Filtro ativo: Tipo: Duplicata" com Limpar');

    // 3) F5 no mesmo dia: o filtro guardado continua (e continua visível)
    await page.reload(); await entrar(); await pronto();
    chk(await page.inputValue('#err-cat') === 'duplicata' && await page.isVisible('#err-filtro-ativo'), 'UX-06: com F5 no mesmo dia, o filtro guardado continua e aparece no aviso');
    await page.click('#err-body [data-err-limpar-tudo]'); await pronto();
    chk(await aba('todos') === ABERTOS && (await page.locator('#err-body tr[data-err-linha]').count()) > 0 && await page.isHidden('#err-filtro-ativo'), 'UX-06: "Limpar" volta a lista inteira');

    // 4) voltar de um projeto: a lista volta com as abas certas
    await page.click('#err-body tr.err-gr a.lnk[href^="#projeto/"]'); await page.waitForTimeout(1500);
    await page.goBack(); await pronto();
    chk(await aba('todos') === ABERTOS && (await page.locator('#err-body tr[data-err-linha]').count()) > 0, 'UX-06: voltando de um projeto, abas e lista certas');

    // 5) "Só este projeto" pela URL e Limpar: o filtro do projeto sai e não volta no F5
    const pj = py(`print(con.execute("SELECT substr(codigo,1,10) FROM erro WHERE situacao='aberto' AND codigo LIKE 'F___-P____%' GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0])`);
    const nPj = +py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade<>'aviso' AND (codigo=? OR codigo LIKE ? || '-%')", ('${pj}','${pj}')).fetchone()[0])`);
    await page.evaluate(p => nav('erros/' + p), pj); await pronto();
    chk(await aba('pedem_acao') === nPj && /Projeto: /.test(await page.textContent('#err-filtro-ativo')), `UX-06: #erros/${pj} mostra só o projeto (${nPj}) e diz "Projeto: ${pj}"`);
    await page.selectOption('#err-grav', 'bloqueia'); await pronto();
    await page.click('#err-filtro-ativo [data-err-limpar-tudo]'); await pronto();
    chk(await aba('todos') === ABERTOS, 'UX-06: Limpar com o filtro do projeto volta a todos os projetos');
    await page.reload(); await entrar(); await pronto();
    chk(await aba('todos') === ABERTOS && await page.inputValue('#err-grav') === '', 'UX-06: ...e o F5 não traz de volta o filtro limpo (antes o Limpar com projeto deixava a gravidade guardada)');

    // 6) "Ver avisos" do resumo com um Tipo escolhido antes: mostra os avisos, não "Todos 0"
    if (await page.isVisible('[data-err-diag-grav="aviso"]')) {
      await page.selectOption('#err-cat', 'duplicata'); await pronto();
      await page.click('[data-err-diag-grav="aviso"]'); await pronto();
      chk(await aba('todos') > 0 && await page.inputValue('#err-cat') === '', 'UX-06: "Ver avisos" mostra os avisos (tira o Tipo escolhido antes): ' + await aba('todos'));
      await page.click('#err-filtro-ativo [data-err-limpar-tudo]'); await pronto();
    }

    // ================= UX-19 =================
    await page.click('#err-abas [data-err-sit="pedem_acao"]'); await pronto();
    chk(await aba('pedem_acao') === PEDEM && await aba('avisos') === AVISOS, `UX-19: avisos em aba própria: Abertos ${await aba('pedem_acao')} (esperado ${PEDEM}) · Avisos ${await aba('avisos')} (esperado ${AVISOS})`);
    const gravs = await page.$$eval('#err-body tr[data-err-linha] td:nth-child(2) .tag', L => [...new Set(L.map(x => x.textContent.trim()))]);
    chk(gravs.length > 0 && !gravs.includes('aviso'), 'UX-19: a aba Abertos só tem "bloqueia" e "corrigir": ' + gravs.join(','));
    await page.click('#err-abas [data-err-sit="avisos"]'); await pronto();
    const gravA = await page.$$eval('#err-body tr[data-err-linha] td:nth-child(2) .tag', L => [...new Set(L.map(x => x.textContent.trim()))]);
    chk(gravA.length === 1 && gravA[0] === 'aviso', 'UX-19: a aba Avisos só tem avisos: ' + gravA.join(','));
    await page.click('#err-abas [data-err-sit="pedem_acao"]'); await pronto();
    await page.selectOption('#err-grav', 'aviso'); await pronto();
    chk(await page.getAttribute('#err-abas [data-err-sit="avisos"]', 'aria-pressed') === 'true' && (await page.locator('#err-body tr[data-err-linha]').count()) > 0, 'UX-19: escolher a gravidade "Aviso" leva para a aba Avisos (não para uma lista vazia)');
    await page.click('#err-filtro-ativo [data-err-limpar-tudo]'); await pronto();
    await page.evaluate(() => atualizarPendencias()); await page.waitForTimeout(800);
    const pend = await page.evaluate(async () => (await fetch('/api/pendencias', { credentials: 'same-origin' })).json());
    const badge = id => page.evaluate(i => { const el = document.getElementById(i); return el && !el.hidden ? +el.textContent.replace(/\D/g, '') : 0; }, id);
    chk(pend.pedem_acao && pend.pedem_acao.problemas === PEDEM && await badge('n-err') === PEDEM, `UX-19: o número de Problemas no menu é o que pede ação (${await badge('n-err')}, esperado ${PEDEM}; antes ${ABERTOS} com os avisos)`);
    chk(pend.pedem_acao && await badge('n-gente') === pend.pedem_acao.precisa_de_voce && await badge('n-filas') === pend.pedem_acao.material_novo && await badge('n-dec') === pend.pedem_acao.decisoes, 'UX-19: os outros números do menu vêm da mesma regra (pedem_acao)');

    // ================= UX-20 =================
    await page.click('#err-abas [data-err-sit="pedem_acao"]'); await pronto();
    await page.locator('#err-body tr[data-err-linha] .err-sel').first().check(); await page.waitForTimeout(200);
    chk(await page.isVisible('#err-bulk [data-err-sel-mesmo="tipo"]') && await page.isVisible('#err-bulk [data-err-sel-mesmo="projeto"]'), 'UX-20: escolhido um problema, a barra oferece "Todos deste tipo" e "Todos deste projeto"');
    const esperadoTipo = await page.evaluate(() => errMesmos('tipo', ERR_LISTA.find(e => e.id === ERR_SEL_ULT)).length);
    await page.click('#err-bulk [data-err-sel-mesmo="tipo"]'); await page.waitForTimeout(200);
    const nSel = await page.evaluate(() => ERR_SEL.size);
    chk(nSel === esperadoTipo && nSel > 1 && /selecionados/.test(await page.textContent('#err-bulk-n')), `UX-20: "Todos deste tipo" escolhe os ${esperadoTipo} do mesmo tipo (escolheu ${nSel})`);
    await page.fill('#err-bulk-res', 'conferido em massa no teste');
    await page.click('#err-bulk [data-err-lote="ignorado"]'); await page.waitForSelector('#conf-ov', { timeout: 5000 });
    const prev = (await page.textContent('#conf-ov')).replace(/\s+/g, ' ');
    chk(new RegExp('Fechar ' + nSel + ' problemas').test(prev) && /Por tipo/.test(prev) && /Por projeto/.test(prev) && /conferido em massa no teste/.test(prev), 'UX-20: antes de fechar, a prévia diz quantos, por tipo, por projeto e a frase: "' + prev.slice(0, 140) + '"');
    chk(await aba('pedem_acao') === PEDEM, 'UX-20: ...e na prévia nada mudou ainda');
    await page.click('#conf-ov [data-conf="sim"]'); await page.waitForFunction(() => document.querySelector('#toast.on .toast-acao'), null, { timeout: 8000 }); await pronto();
    chk(await aba('pedem_acao') === PEDEM - nSel, `UX-20: confirmado, ${nSel} saem de Abertos (${await aba('pedem_acao')})`);
    await page.click('#toast .toast-acao'); await page.waitForFunction(() => /Desfeito/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await pronto();
    chk(await aba('pedem_acao') === PEDEM, `UX-20: Desfazer volta todos (${await aba('pedem_acao')})`);
    const resVolta = py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE resolucao='conferido em massa no teste'").fetchone()[0])`);
    chk(resVolta === '0', 'UX-20: ...com a resolução de antes (a frase da ação em massa não fica gravada)');
    // mensagens repetidas
    await page.click('#err-abas [data-err-sit="avisos"]'); await pronto();
    const av0 = await aba('avisos');
    chk(await page.isVisible('[data-err-repetidos]'), 'UX-20: o aviso "mensagens repetidas" tem o botão Ver');
    await page.click('[data-err-repetidos]'); await page.waitForSelector('#conf-ov', { timeout: 5000 });
    const mtxt = (await page.textContent('#conf-ov')).replace(/\s+/g, ' ');
    chk(/Mesclar 2/.test(mtxt) && /exiftool: tag duplicada/.test(mtxt) && /fica o nº/.test(mtxt), 'UX-20: Ver mostra os grupos repetidos, qual fica e quantas cópias fecham: "' + mtxt.slice(0, 160) + '"');
    await page.click('#conf-ov [data-conf="sim"]'); await page.waitForFunction(() => document.querySelector('#toast.on .toast-acao'), null, { timeout: 8000 }); await pronto();
    chk(await aba('avisos') === av0 - 2, `UX-20: Mesclar fecha as 2 cópias (${av0} -> ${await aba('avisos')})`);
    await page.click('#toast .toast-acao'); await page.waitForFunction(() => /Desfeito/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }); await pronto();
    chk(await aba('avisos') === av0, 'UX-20: Desfazer do Mesclar reabre as cópias');
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
