// Problemas e Precisa de você no navegador de verdade (Playwright + Chromium), cards UX do board "CAMP Acervos — UX do painel".
// UX-06: com centenas de problemas abertos, a tela abre com as abas e a lista certas (direto pela URL, voltando de um projeto,
//        com um filtro guardado de outro dia); com filtro, o estado vazio diz QUAL filtro está ativo e tem "Limpar".
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
`);
const ABERTOS = +py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')").fetchone()[0])`);

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
    chk(await aba('abertos') === ABERTOS, `UX-06: aberta direto pela URL, a aba Abertos mostra os ${ABERTOS} abertos (filtro de outro dia não volta): ${await aba('abertos')}`);
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
    chk(await aba('abertos') === ABERTOS && (await page.locator('#err-body tr[data-err-linha]').count()) > 0 && await page.isHidden('#err-filtro-ativo'), 'UX-06: "Limpar" volta a lista inteira');

    // 4) voltar de um projeto: a lista volta com as abas certas
    await page.click('#err-body tr.err-gr a.lnk[href^="#projeto/"]'); await page.waitForTimeout(1500);
    await page.goBack(); await pronto();
    chk(await aba('abertos') === ABERTOS && (await page.locator('#err-body tr[data-err-linha]').count()) > 0, 'UX-06: voltando de um projeto, abas e lista certas');

    // 5) "Só este projeto" pela URL e Limpar: o filtro do projeto sai e não volta no F5
    const pj = py(`print(con.execute("SELECT substr(codigo,1,10) FROM erro WHERE situacao='aberto' AND codigo LIKE 'F___-P____%' GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0])`);
    const nPj = +py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND (codigo=? OR codigo LIKE ? || '-%')", ('${pj}','${pj}')).fetchone()[0])`);
    await page.evaluate(p => nav('erros/' + p), pj); await pronto();
    chk(await aba('abertos') === nPj && /Projeto: /.test(await page.textContent('#err-filtro-ativo')), `UX-06: #erros/${pj} mostra só o projeto (${nPj}) e diz "Projeto: ${pj}"`);
    await page.selectOption('#err-grav', 'bloqueia'); await pronto();
    await page.click('#err-filtro-ativo [data-err-limpar-tudo]'); await pronto();
    chk(await aba('abertos') === ABERTOS, 'UX-06: Limpar com o filtro do projeto volta a todos os projetos');
    await page.reload(); await entrar(); await pronto();
    chk(await aba('abertos') === ABERTOS && await page.inputValue('#err-grav') === '', 'UX-06: ...e o F5 não traz de volta o filtro limpo (antes o Limpar com projeto deixava a gravidade guardada)');

    // 6) "Ver avisos" do resumo com um Tipo escolhido antes: mostra os avisos, não "Todos 0"
    if (await page.isVisible('[data-err-diag-grav="aviso"]')) {
      await page.selectOption('#err-cat', 'duplicata'); await pronto();
      await page.click('[data-err-diag-grav="aviso"]'); await pronto();
      chk(await aba('todos') > 0 && await page.inputValue('#err-cat') === '', 'UX-06: "Ver avisos" mostra os avisos (tira o Tipo escolhido antes): ' + await aba('todos'));
      await page.click('#err-filtro-ativo [data-err-limpar-tudo]'); await pronto();
    }
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
