// "Tirar uma folha do projeto" na revisão da folha, no navegador de verdade (Playwright + Chromium). Relato de 19/10: "quando salvo que é pra
// tirar uma folha do projeto, ele salva e pula pra próxima folha, mas não tá funcionando bem isso".
// Prova, num lote em revisão E num lote já aprovado, pelos dois caminhos ("Não publicar esta folha" → Reter, e "É de outro projeto…" → Mover):
//  - não pergunta "Sair sem salvar?" ao pular para a próxima folha (antes o motivo digitado / o campo mudado faziam perguntar);
//  - o campo mudado no formulário antes de reter/mover é SALVO (antes era descartado em silêncio);
//  - abre a próxima folha (a próxima a conferir; sem nenhuma a conferir, a seguinte na ordem), nunca "Conferência concluída" num lote aprovado
//    nem a folha que acabou de sair do projeto;
//  - lote aprovado: reter funciona (antes: 409 "reabra a revisão") e "Desfazer" no aviso devolve a folha sem reabrir a revisão;
//  - depois de mover: a miniatura some, "Folhas (N)" e os contadores do lote diminuem, nenhuma chamada 404;
//  - dois cliques em "Reter" gravam uma vez só; Enter no "Não publicar esta folha" não marca a folha como conferida;
//  - nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/tf.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/tf.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8961)
//   CAMP_DB_PATH=/tmp/tf.db CAMP_BASE=http://127.0.0.1:8961 node tests/navegador_tirar_folha.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8961', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const PA = 'F026-P0093', PB = 'F026-P0094', DEST = 'F026-P0002', D = (p, n) => `${p}-1970-S01-D0000${n}`;
// (a folha é aberta por abrirRevisaoItem, como o clique na miniatura: sem imagem, o centro da miniatura é o botão de pedir releitura)
// A: lote em revisão, 4 folhas a conferir. B: lote APROVADO, 4 folhas conferidas. Destino do "mover": F026-P0002 (mesmo fundo, sem folhas).
py(`
for p,n,tit,apr in [('${PA}',93,'Tirar folha (em revisão)',False),('${PB}',94,'Tirar folha (aprovado)',True)]:
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',?)", (n,))
    con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES (?,'F026',?,?,1970,'São Paulo')", (p,n,tit))
    con.execute("DELETE FROM item WHERE projeto_codigo=?", (p,))
    lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por) VALUES (?,?,'/nao/existe','revisao',?,?)",
                     ('Lote '+tit, p, '2026-10-19 10:00:00' if apr else None, 'rafael@camp.arq.br' if apr else None)).lastrowid
    for s in range(1,5):
        con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,pendencias,titulo,folha,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          ("%s-1970-S01-D%05d" % (p,s),p,"S01",s,'campvision',lote,'nao_publicado','{"bloqueios":[],"sinais":[],"ressalvas":[]}',"Prancha %d" % s,"%02d/04" % s,'conferida' if apr else 'pendente'))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
let PG = null;
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } }); PG = pg;
  const erros = [], r404 = [], retencoes = [], revisoes = [];
  pg.on('pageerror', e => erros.push(e.message));
  pg.on('response', r => { if (r.status() === 404 && r.url().includes('/api/') && !r.url().includes('teste=1')) r404.push(r.url()); });
  pg.on('request', r => { if (r.method() === 'POST' && /\/retencao$/.test(r.url())) retencoes.push(r.url()); if (r.method() === 'POST' && /\/revisao$/.test(r.url())) revisoes.push(r.url()); });
  // toda janela de confirmação que aparecer fica registrada (o teste não pode depender de "pegar" a janela no instante certo)
  await pg.addInitScript(() => { window._DIALOGOS = []; new MutationObserver(() => { const o = document.getElementById('conf-ov'); if (o && !o.dataset.visto) { o.dataset.visto = '1'; window._DIALOGOS.push((o.querySelector('h2') || {}).textContent || ''); } }).observe(document, { childList: true, subtree: true }); });
  const item = c => pg.evaluate(c => fetch('/api/itens/' + encodeURIComponent(c) + '?teste=1').then(r => r.ok ? r.json() : null), c);
  const aberta = () => pg.evaluate(() => (document.getElementById('d-title') || {}).textContent === 'Revisar folha' ? (document.getElementById('d-sub') || {}).textContent : (document.getElementById('d-title') || {}).textContent);
  const dialogos = () => pg.evaluate(() => window._DIALOGOS.slice());
  const sairSemSalvar = async () => (await dialogos()).filter(t => /Sair sem salvar/.test(t)).length;
  // se a pergunta "Sair sem salvar?" aparecer, registra (a falha já foi contada) e responde para o teste seguir
  const fecharPergunta = async () => { if (await pg.$('#conf-ov') && /Sair sem salvar/.test(await pg.textContent('#conf-ov h2'))) await pg.click('#conf-ov [data-conf="sim"]'); };
  const sujo = () => pg.evaluate(() => { const d = document.getElementById('dirty-state'); return !!d && d.classList.contains('on'); });
  const abaFolhas = () => pg.evaluate(() => { const b = [...document.querySelectorAll('button,a')].find(x => /^Folhas \(\d+\)$/.test(x.textContent.trim())); return b ? +b.textContent.match(/\d+/)[0] : -1; });
  const chips = () => pg.evaluate(() => (document.querySelector('#pj-revisao .rev-chips') || {}).textContent || '');
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));

  const reter = async (P, n, titulo, motivo, rotulo, esperado) => {
    await pg.evaluate(c => abrirRevisaoItem(c), D(P, n)); await espera(async () => await aberta() === D(P, n)); await pg.waitForSelector('#rv-titulo');
    const antes = await sairSemSalvar(), nRet = retencoes.length;
    await pg.fill('#rv-titulo', titulo); await pg.click('details.rev-reter:not(.op-det) > summary'); await pg.fill('#rv-motivo', motivo);
    await pg.dblclick(`[data-rev-item="reter"][data-codigo="${D(P, n)}"]`);   // dois cliques: grava uma vez só
    const ok = await espera(async () => { await fecharPergunta(); return (await item(D(P, n)) || {}).item?.retida === 1 && await aberta() !== D(P, n); });
    const i = (await item(D(P, n))).item;
    chk(ok && i.retida === 1 && i.retida_motivo === motivo, `${rotulo}: "Reter esta folha" grava a retenção com o motivo`, JSON.stringify([i.retida, i.retida_motivo, await pg.textContent('#toast')]));
    chk(i.titulo === titulo, `${rotulo}: o título mudado antes de reter é salvo (antes era descartado)`, i.titulo);
    chk(await sairSemSalvar() === antes, `${rotulo}: pula para a próxima SEM perguntar "Sair sem salvar?"`, JSON.stringify(await dialogos()));
    chk(await aberta() === D(P, esperado), `${rotulo}: abre a próxima folha (${D(P, esperado).slice(-6)})`, await aberta());
    chk(!(await sujo()), `${rotulo}: a próxima folha abre sem "Alterações não salvas"`);
    chk(retencoes.length - nRet === 1, `${rotulo}: dois cliques em "Reter" gravam uma vez só`, String(retencoes.length - nRet));
    return i;
  };
  const mover = async (P, n, titulo, rotulo, esperado) => {
    if (await aberta() !== D(P, n)) { await pg.evaluate(c => abrirRevisaoItem(c), D(P, n)); await espera(async () => await aberta() === D(P, n)); }
    await pg.waitForSelector('#rv-titulo');
    const antes = await sairSemSalvar(), folhas = await abaFolhas(); r404.length = 0;
    await pg.fill('#rv-titulo', titulo); await pg.click('details.op-det > summary'); await pg.fill('.op-outro .op-busca', DEST);
    await pg.waitForSelector('.op-outro .op-go:not([disabled])', { timeout: 8000 }); const novo = await pg.textContent('.op-novo');
    await pg.click('.op-outro .op-go'); await pg.waitForSelector('#conf-ov [data-conf="sim"]'); await pg.click('#conf-ov [data-conf="sim"]');
    const ok = await espera(async () => { await fecharPergunta(); return !(await item(D(P, n))) && await aberta() !== D(P, n) && /^F026/.test(await aberta() || ''); });
    const m = await item(novo);
    chk(ok && !!m && m.item.projeto_codigo === DEST, `${rotulo}: a folha foi movida para ${DEST} (${novo})`, JSON.stringify(m && m.item.projeto_codigo));
    chk(!!m && m.item.titulo === titulo, `${rotulo}: o título mudado antes de mover é salvo (antes era descartado)`, m && m.item.titulo);
    chk(await sairSemSalvar() === antes, `${rotulo}: pula para a próxima SEM perguntar "Sair sem salvar?"`, JSON.stringify(await dialogos()));
    chk(await aberta() === D(P, esperado), `${rotulo}: abre a próxima folha (${D(P, esperado).slice(-6)}), não a que saiu`, await aberta());
    await espera(async () => await abaFolhas() === folhas - 1);
    chk(!(await pg.$(`.thumb[data-rev-abrir="${D(P, n)}"]`)), `${rotulo}: a miniatura da folha que saiu some da página`);
    chk(await abaFolhas() === folhas - 1, `${rotulo}: "Folhas (N)" diminui`, `${folhas} -> ${await abaFolhas()}`);
    chk(!(await pg.evaluate(c => (window.ITENS_PJ || []).some(x => x.codigo === c), D(P, n))), `${rotulo}: a lista da página não tem mais a folha que saiu`);
    chk(!r404.length, `${rotulo}: nenhuma chamada 404 depois de mover`, r404.join(' '));
  };

  // ---------- A: lote em revisão ----------
  await pg.goto(BASE + '/#projeto/' + PA); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(PA, 1)}"]`, { timeout: 15000 });
  await pg.waitForSelector('#pj-revisao .rev-chips', { state: 'attached' });
  // Enter no "Não publicar esta folha" (teclado) abre o quadro, não marca a folha como conferida
  await pg.evaluate(c => abrirRevisaoItem(c), D(PA, 1)); await espera(async () => await aberta() === D(PA, 1));
  const nd = (await dialogos()).length;
  await pg.focus('details.rev-reter:not(.op-det) > summary'); await pg.keyboard.press('Enter'); await new Promise(r => setTimeout(r, 800));
  const dEnter = (await dialogos()).slice(nd); if (await pg.$('#conf-ov')) { await pg.click('#conf-ov [data-conf="nao"]'); await pg.waitForSelector('#conf-ov', { state: 'detached' }); }
  chk((await item(D(PA, 1))).item.revisao === 'pendente' && await aberta() === D(PA, 1) && !dEnter.length && await pg.evaluate(() => document.querySelector('details.rev-reter:not(.op-det)').open),
    'Enter no "Não publicar esta folha" abre o quadro e não tenta marcar a folha como conferida', JSON.stringify(dEnter));
  await pg.evaluate(() => closeDrawer(true));
  await reter(PA, 1, 'Prancha 1 (retida)', 'foto de pessoa', 'lote em revisão', 2);
  await espera(async () => /1 retida/.test(await chips()));
  chk(/3 a conferir/.test(await chips()) && /1 retida/.test(await chips()), 'lote em revisão: os contadores do lote mostram a folha retida', await chips());
  await mover(PA, 2, 'Prancha 2 (de outro projeto)', 'lote em revisão', 3);
  await espera(async () => /2 a conferir/.test(await chips()));
  chk(/2 a conferir/.test(await chips()), 'lote em revisão: "a conferir" diminui depois de mover', await chips());
  // dois cliques em "Salvar correção": grava uma vez e vai para a próxima (antes gravava duas vezes)
  await pg.fill('#rv-titulo', 'Prancha 3 (corrigida)'); const nRev = revisoes.length;
  await pg.dblclick(`[data-rev-item="corrigida"][data-codigo="${D(PA, 3)}"]`);
  await espera(async () => await aberta() === D(PA, 4)); await new Promise(r => setTimeout(r, 600));
  chk(revisoes.length - nRev === 1 && (await item(D(PA, 3))).item.titulo === 'Prancha 3 (corrigida)', 'dois cliques em "Salvar correção" gravam uma vez só', String(revisoes.length - nRev));
  // "criar projeto novo" com nome PARECIDO de um que já existe no fundo: mostra o parecido como escolha e não cria nada
  const nProj = () => +py(`print(con.execute("SELECT COUNT(*) FROM projeto WHERE fundo_codigo='F026'").fetchone()[0])`);
  const proj0 = nProj();
  await pg.click('details.op-det > summary'); await pg.click('details.op-np > summary'); await pg.fill('.op-np-titulo', 'Edifício Paulista');
  await pg.click('.op-np-go'); await pg.waitForSelector(`.op-np-parecidos [data-op-par="${DEST}"]`, { timeout: 8000 });
  chk(nProj() === proj0 && !(await pg.$('#conf-ov')), '"criar projeto novo" com nome parecido: mostra o projeto que já existe e não cria nada');
  await pg.click(`.op-np-parecidos [data-op-par="${DEST}"]`); await pg.waitForSelector('.op-outro .op-go:not([disabled])', { timeout: 8000 });
  chk(await pg.inputValue('.op-outro .op-busca') === DEST, '"Mover para este" escolhe o projeto parecido como destino');
  await pg.evaluate(() => closeDrawer(true));

  // ---------- B: lote aprovado (nenhuma folha a conferir) ----------
  await pg.evaluate(() => closeDrawer(true));
  await pg.goto(BASE + '/#projeto/' + PB); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(PB, 1)}"]`, { timeout: 15000 });
  await pg.waitForSelector('#pj-revisao .rev-chips', { state: 'attached' });
  await reter(PB, 1, 'Prancha 1 (aprovado, retida)', 'sem autorização de imagem', 'lote aprovado', 2);
  chk(!/Conferência concluída/.test(await aberta()), 'lote aprovado: não mostra "Conferência concluída" depois de reter');
  // "Desfazer" no aviso devolve a folha (volta a poder ir ao site) sem reabrir a revisão do lote e sem tirar a pessoa da folha em que está
  const tem = await pg.$('#toast .toast-acao'); chk(!!tem && /Desfazer/.test(await pg.textContent('#toast .toast-acao')), 'lote aprovado: o aviso de "retida" tem "Desfazer"');
  if (tem) { await pg.click('#toast .toast-acao'); await espera(async () => (await item(D(PB, 1))).item.retida === 0); }
  const b1 = (await item(D(PB, 1))).item;
  chk(b1.retida === 0 && b1.revisao === 'conferida', '"Desfazer": a folha volta a ir ao site e continua conferida (lote aprovado não reabre)', JSON.stringify([b1.retida, b1.revisao]));
  chk(await aberta() === D(PB, 2), '"Desfazer" não tira a pessoa da folha em que está', await aberta());
  await mover(PB, 2, 'Prancha 2 (aprovado, de outro projeto)', 'lote aprovado', 3);
  chk(!/Conferência concluída/.test(await aberta()), 'lote aprovado: não mostra "Conferência concluída" depois de mover');
  // o projeto certo não existe: cria no mesmo fundo e move a folha, numa confirmação só (o pedido de 19/10)
  {
    const NOME = 'Garagem Zetaquatro Teste', antes = await sairSemSalvar(), proj0 = nProj();
    await pg.fill('#rv-titulo', 'Prancha 3 (projeto novo)'); await pg.click('details.op-det > summary'); await pg.fill('.op-outro .op-busca', NOME);
    await espera(async () => /crie abaixo/.test(await pg.textContent('.op-previa')) && await pg.evaluate(() => document.querySelector('details.op-np').open));
    chk(await pg.inputValue('.op-np-titulo') === NOME, 'busca sem resultado: oferece "criar projeto novo" já com o nome digitado');
    await pg.fill('.op-np-ano', '1971'); await pg.fill('.op-np-cidade', 'Santos'); await pg.click('.op-np-go');
    await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 8000 }); const txt = await pg.textContent('#conf-ov');
    const prox = (txt.match(/F026-P\d{4}(?!-)/) || [''])[0];
    chk(/Criar o projeto e mover a folha/.test(txt) && !!prox && txt.includes(`${prox}-1971-S01-D00001`), 'a confirmação diz o código do projeto novo e o código novo da folha', txt);
    await pg.click('#conf-ov [data-conf="sim"]');
    const ok = await espera(async () => { await fecharPergunta(); return !(await item(D(PB, 3))) && await aberta() === D(PB, 4); });
    const p = JSON.parse(py(`print(json.dumps([dict(zip(('codigo','titulo','ano','cidade'),r)) for r in con.execute("SELECT codigo,titulo,ano,cidade FROM projeto WHERE titulo=?", ('${NOME}',))]))`));
    const m = p.length ? await item(`${p[0].codigo}-1971-S01-D00001`) : null;
    chk(nProj() === proj0 + 1 && p.length === 1 && p[0].codigo === prox && p[0].ano === 1971 && p[0].cidade === 'Santos', 'cria o projeto no mesmo fundo, com nome, ano e cidade', JSON.stringify(p));
    chk(ok && !!m && m.item.titulo === 'Prancha 3 (projeto novo)', 'a folha vai para o projeto novo (com o título mudado salvo) e a próxima folha abre', JSON.stringify(m && m.item.codigo));
    chk(await sairSemSalvar() === antes, 'criar e mover: sem "Sair sem salvar?"', JSON.stringify(await dialogos()));
  }
  // a última folha do lote aprovado: reter fecha a janela com um aviso claro (não há próxima)
  await pg.evaluate(c => abrirRevisaoItem(c), D(PB, 4)); await espera(async () => await aberta() === D(PB, 4));
  await pg.click('details.rev-reter:not(.op-det) > summary'); await pg.fill('#rv-motivo', 'última folha');   // CAMP-089: reter exige motivo
  await pg.click(`[data-rev-item="reter"][data-codigo="${D(PB, 4)}"]`);
  await espera(async () => (await item(D(PB, 4))).item.retida === 1);
  await espera(async () => !(await pg.evaluate(() => document.querySelector('main').classList.contains('with-drawer'))) || await aberta() !== D(PB, 4));
  chk(!/Conferência concluída/.test(await aberta() || ''), 'lote aprovado, última folha: não mostra "Conferência concluída"', await aberta());
  chk(/retida/i.test(await pg.textContent('#toast')), 'lote aprovado, última folha: o aviso diz o que aconteceu', await pg.textContent('#toast'));
  chk(!(await pg.evaluate(() => [...document.querySelectorAll('[onclick]')].some(e => /F026-P009[34]-\d{4}-S\d\d-D\d/.test(e.getAttribute('onclick'))))), 'revisão: código de folha só em data-*, nunca em onclick');
  // na página da folha ("É de outro projeto…" fora da revisão) o "criar projeto novo" também aparece
  await pg.evaluate(() => closeDrawer(true)); await pg.goto(BASE + '/#item/' + D(PA, 4)); await pg.waitForSelector(`[data-op-abrir="${D(PA, 4)}"]`, { timeout: 10000 });
  await pg.click(`[data-op-abrir="${D(PA, 4)}"]`); await pg.waitForSelector('#d-body .op-outro');
  chk(!!(await pg.$('#d-body .op-outro details.op-np .op-np-go')), 'página da folha: "É de outro projeto…" também oferece criar projeto novo');
  await pg.evaluate(() => closeDrawer(true));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); if (PG) console.error('janelas:', JSON.stringify(await PG.evaluate(() => window._DIALOGOS).catch(() => null))); process.exit(2); });
