// Revisão da folha: "É de outro projeto…" no navegador de verdade (Playwright + Chromium), e "Mover folhas" num projeto publicado.
// Prova: a busca do destino só traz projetos do MESMO fundo; a prévia mostra o código novo; ao confirmar, a folha sai do lote e a
// revisão segue para a próxima pendente SEM voltar à tela do projeto; operador vê o botão desabilitado ("peça a um admin");
// no projeto publicado, "Mover folhas" abre e só a folha que está no site fica desabilitada; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 8910-8919, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/outro.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/outro.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8911)
//   CAMP_DB_PATH=/tmp/outro.db CAMP_BASE=http://127.0.0.1:8911 node tests/navegador_outro_projeto.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8911', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// Lote misturado no F026 (3 folhas a conferir), o projeto certo no F026, um homônimo no F023 (outro fundo) e um projeto PUBLICADO no F026.
py(`
def proj(cod, fundo, n, titulo, ano, status='nao_publicado', tid=None):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES (?,?)", (fundo, n))
    con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,status_site,tainacan_item_id) VALUES (?,?,?,?,?,?,?,?)", (cod, fundo, n, titulo, ano, 'São Paulo', status, tid))
proj('F026-P0090','F026',90,'Lote Misturado',1968)
proj('F026-P0091','F026',91,'Clube Destino',1969)
proj('F023-P0091','F023',91,'Clube Destino',1969)
proj('F026-P0092','F026',92,'Residência Publicada',1971,'no_ar',None)
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote misturado','F026-P0090','/x/misturado','revisao')")
lid = con.execute("SELECT MAX(id) FROM lista_processamento").fetchone()[0]
for q, t in ((1, 'Planta térreo'), (2, 'Fachada do clube'), (3, 'Corte AA')):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,origem,lote_id,revisao) VALUES (?,?,'S01',?,?,?,1968,'campvision',?,'pendente')", ('F026-P0090-1968-S01-D%05d' % q, 'F026-P0090', q, t, str(q), lid))
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,origem,status_site,tainacan_item_id,revisao) VALUES ('F026-P0092-1971-S01-D00001','F026-P0092','S01',1,'Planta publicada','1',1971,'importado','no_ar',7701,'conferida')")
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,origem,revisao) VALUES ('F026-P0092-1971-S01-D00002','F026-P0092','S01',2,'Folha nova','2',1971,'campvision','conferida')")
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test/.test(u);
  async function entrar(email, senha) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    page.on('console', m => { const u = ((m.location() || {}).url || ''); if (m.type() === 'error' && !ESPERADO(u) && !/ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|exemplo\.test/.test(m.text())) erros.push(email + ' console.error: ' + m.text() + ' [' + u.replace(BASE, '') + ']'); });
    page.on('pageerror', e => erros.push(email + ' pageerror: ' + e.message));
    page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(email + ' ' + r.status() + ' ' + r.url().replace(BASE, '')); });
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== "undefined" && EU && document.getElementById('login') && !document.getElementById('login').classList.contains('on'), null, { timeout: 15000 });
    return page;
  }
  try {
    // ---------------- admin na revisão do lote ----------------
    const page = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
    await page.evaluate(() => { nav('projeto/F026-P0090') });
    await page.waitForSelector('.thumb[data-rev-abrir="F026-P0090-1968-S01-D00002"]', { timeout: 15000 });
    // a folha não tem imagem: o cartão mostra "Sem imagem" com o botão "Pedir releitura" no meio (2b86656). O botão faz só a ação
    // dele (confirmação), sem abrir a revisão por baixo; o cartão continua abrindo a revisão pelo resto (aqui, a legenda)
    const btRel = '.thumb[data-rev-abrir="F026-P0090-1968-S01-D00002"] [data-releitura-item]';
    await page.waitForSelector(btRel, { timeout: 15000 });
    await page.click(btRel); await page.waitForSelector('#conf-ov', { timeout: 5000 }); await page.waitForTimeout(600);
    chk(/reler esta folha/.test(await page.textContent('#conf-ov')) && !(await page.$('#d-body .op-det')),
        '"Pedir releitura" dentro do cartão abre só a confirmação (a revisão não abre por baixo)');
    await page.click('#conf-ov [data-conf="nao"]'); await page.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 });
    await page.click('.thumb[data-rev-abrir="F026-P0090-1968-S01-D00002"] .cap');
    await page.waitForSelector('#d-body .op-det summary', { timeout: 10000 });
    chk(/É de outro projeto/.test(await page.textContent('#d-body .op-det summary')), 'revisão: a folha tem "É de outro projeto…"');
    await page.click('#d-body .op-det summary');
    // busca por nome: só projetos do mesmo fundo
    await page.fill('#d-body .op-busca', 'Clube Destino');
    await page.waitForFunction(() => /encontrado/.test((document.querySelector('#d-body .op-previa') || {}).textContent || ''), null, { timeout: 8000 });
    const opcoes = await page.$$eval('#op-lista option', os => os.map(o => o.value));
    chk(opcoes.includes('F026-P0091') && !opcoes.includes('F023-P0091'), 'a busca por nome só traz o projeto do mesmo fundo (F026-P0091, sem o homônimo F023-P0091): ' + JSON.stringify(opcoes));
    // outro fundo digitado direto: recusado na tela, sem chamar o servidor
    await page.fill('#d-body .op-busca', 'F023-P0091');
    await page.waitForFunction(() => /Fundos não se misturam/.test((document.querySelector('#d-body .op-previa') || {}).textContent || ''), null, { timeout: 8000 });
    chk(await page.isDisabled('#d-body .op-go'), 'código de outro fundo: "Fundos não se misturam" e o botão fica desabilitado');
    // o certo: mostra o código novo
    await page.fill('#d-body .op-busca', 'F026-P0091');
    await page.waitForSelector('#d-body .op-novo', { timeout: 8000 });
    const novo = (await page.textContent('#d-body .op-novo')).trim();
    chk(novo === 'F026-P0091-1969-S01-D00001', 'prévia: mostra o código novo que a folha vai ganhar (' + novo + ')');
    chk(/Clube Destino/.test(await page.textContent('#d-body .op-previa')), 'prévia: mostra o nome do projeto de destino');
    const aindaLa = py(`print(con.execute("SELECT COUNT(*) FROM item WHERE codigo='F026-P0090-1968-S01-D00002'").fetchone()[0])`);
    chk(aindaLa === '1', 'a prévia não move nada');
    await page.click('#d-body .op-go');
    await page.waitForSelector('#conf-x', { timeout: 5000 });
    chk(/F026-P0091-1969-S01-D00001/.test(await page.textContent('.conf-box')), 'confirmação mostra o código antigo e o novo');
    await page.click('[data-conf="sim"]');
    await page.waitForFunction(() => /agora é F026-P0091-1969-S01-D00001/.test(document.getElementById('toast').textContent), null, { timeout: 10000 });
    await page.waitForFunction(() => /F026-P0090-1968-S01-D00003/.test((document.getElementById('d-sub') || {}).textContent || ''), null, { timeout: 10000 });
    chk(true, 'depois de mover, a revisão segue para a próxima folha pendente do lote (D00003)');
    chk(/#projeto\/F026-P0090$/.test(page.url()) && await page.isVisible('#d-body .rev-acoes'), 'sem voltar à tela do projeto: o painel de revisão continua aberto');
    chk(await page.evaluate(() => !(window.ITENS_PJ || []).some(x => x.codigo === 'F026-P0090-1968-S01-D00002') && !document.querySelector('.thumb[data-rev-abrir="F026-P0090-1968-S01-D00002"]')), 'a folha movida sai do lote (da lista e das miniaturas)');
    const banco = py(`print(con.execute("SELECT projeto_codigo||'|'||codigo_anterior FROM item WHERE codigo='F026-P0091-1969-S01-D00001'").fetchone()[0])`);
    chk(banco === 'F026-P0091|F026-P0090-1968-S01-D00002', 'no banco: a folha está no destino com o código antigo guardado (' + banco + ')');
    // histórico dos dois projetos
    for (const pj of ['F026-P0090', 'F026-P0091']) {
      const h = await page.evaluate(async c => (await (await fetch('/api/projetos/' + c + '/detalhe')).json()).eventos.filter(e => e.tipo === 'folha_movida').length, pj);
      chk(h === 1, 'histórico de ' + pj + ' mostra a folha movida (' + h + ')');
    }
    // ---------------- página da folha ----------------
    await page.evaluate(() => { nav('item/F026-P0090-1968-S01-D00001') });
    await page.waitForSelector('.it-acoes [data-op-abrir]', { timeout: 15000 });
    await page.click('.it-acoes [data-op-abrir]');
    await page.waitForSelector('#d-body .op-outro .op-busca', { timeout: 5000 });
    await page.fill('#d-body .op-busca', 'F026-P0091');
    await page.waitForSelector('#d-body .op-novo', { timeout: 8000 });
    chk((await page.textContent('#d-body .op-novo')).trim() === 'F026-P0091-1969-S01-D00002', 'página da folha: "É de outro projeto…" abre a busca e mostra o próximo código (D00002)');
    // ---------------- projeto publicado: Mover folhas ----------------
    await page.evaluate(() => { nav('projeto/F026-P0092') });   // sem fechar nada antes: a busca digitada não conta como alteração a perder
    // desde caf753f (proposta B) "Mesclar, mover, mudar código…" fica dentro do menu "Mais ⋯" do cabeçalho
    await page.waitForSelector('.pj-mais-menu summary', { timeout: 15000 });
    await page.click('.pj-mais-menu summary');
    await page.waitForSelector('[data-pj-mais]', { timeout: 5000 });
    await page.click('[data-pj-mais]');
    await page.waitForSelector('[data-mais="mover"]', { timeout: 5000 });
    chk(!(await page.isDisabled('[data-mais="mover"]')), 'projeto publicado: "Mover folhas para outro projeto" fica disponível');
    await page.click('[data-mais="mover"]');
    await page.waitForSelector('.mx-it', { timeout: 5000 });
    const est = await page.$$eval('.mx-it', cs => cs.map(c => [c.value, c.disabled, c.closest('label').textContent]));
    const pub = est.find(x => x[0].endsWith('D00001')), nova = est.find(x => x[0].endsWith('D00002'));
    chk(pub && pub[1] && /está no site: despublique esta folha antes/.test(pub[2]), 'a folha que está no site aparece desabilitada com "está no site: despublique esta folha antes"');
    chk(nova && !nova[1], 'a folha que não está no site pode ser marcada');
    await page.check('.mx-it[value="F026-P0092-1971-S01-D00002"]');
    await page.fill('#mx-dest', 'F026-P0091'); await page.check('#mx-ok'); await page.click('#mx-go');
    await page.waitForFunction(() => /1 folha\(s\) movida/.test(document.getElementById('toast').textContent), null, { timeout: 10000 });
    const pubLa = py(`print(con.execute("SELECT projeto_codigo FROM item WHERE codigo='F026-P0092-1971-S01-D00001'").fetchone()[0], con.execute("SELECT COUNT(*) FROM item WHERE codigo_anterior='F026-P0092-1971-S01-D00002' AND projeto_codigo='F026-P0091'").fetchone()[0])`);
    chk(pubLa === 'F026-P0092 1', 'projeto publicado: a folha não publicada foi movida e a publicada ficou (' + pubLa + ')');
    await page.context().close();
    // ---------------- operador: botão desabilitado ----------------
    const op = await entrar('operador@camp.arq.br', 'senha-operador-123');
    await op.evaluate(() => { nav('projeto/F026-P0090') });
    await op.waitForSelector('.thumb[data-rev-abrir="F026-P0090-1968-S01-D00003"]', { timeout: 15000 });
    await op.click('.thumb[data-rev-abrir="F026-P0090-1968-S01-D00003"] .cap');
    await op.waitForSelector('#d-body .op-sem button', { timeout: 10000 });
    chk(await op.isDisabled('#d-body .op-sem button') && /peça a um admin/.test(await op.textContent('#d-body .op-sem')), 'operador: "É de outro projeto…" aparece desabilitado com "peça a um admin"');
    chk(!(await op.$('#d-body .op-outro')), 'operador: não há busca nem botão de mover');
    await op.context().close();
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
