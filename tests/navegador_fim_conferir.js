// CAMP-070 (20/10, relato da operadora: "etapas menos claras, não consegui publicar diretamente após conferir todas as folhas,
// foi necessário sair da página e clicar em publicar a partir daí"). Prova no navegador de verdade (Playwright + Chromium):
//  (A) tela de conferir (#conferir/<projeto>): ao conferir a última folha, o painel da direita mostra o caminho com "você está aqui"
//      em Aprovar e o botão "Aprovar o lote"; aprovar (com confirmação) atualiza ali mesmo para "Publicar"; "Publicar" abre a
//      publicação guiada (chama /publicar/plano) SEM sair da tela de conferir;
//  (B) gaveta da página do projeto: a última folha conferida mostra "Aprovar o lote" na própria gaveta; ao aprovar, a gaveta mostra
//      "Publicar" e a página por baixo (próximo passo e cartão Folhas) se atualiza sem recarregar;
//  (C) problema que impede publicar: depois de aprovar, diz o que falta ("erro bloqueante") com o botão para a lista;
//  (D) operador: ao terminar, vê "Falta um admin aprovar", sem o botão.
// O site do teste não existe (WP_BASE_URL=http://127.0.0.1:9): nada é publicado de verdade.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/fc.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/fc.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8941)
//   CAMP_DB_PATH=/tmp/fc.db CAMP_BASE=http://127.0.0.1:8941 [CAMP_SHOTS=/pasta] node tests/navegador_fim_conferir.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8941', DB = process.env.CAMP_DB_PATH, SHOTS = process.env.CAMP_SHOTS || '';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const PA = 'F026-P0171', PB = 'F026-P0172', PC = 'F026-P0173', PD = 'F026-P0174', ult = p => `${p}-1977-S01-D00003`;
const montar = (p, n, extra = '') => `
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', ${n})")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${p}','F026',${n},'Casa Fim ${n}',1977,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${p}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote fim ${n}','${p}','/nao/existe','revisao')").lastrowid
for s in range(1, 4):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,origem,lote_id,revisao,pendencias) VALUES (?,?,?,?,?,?,'campvision',?,?,?)",
                ('${p}-1977-S01-D%05d' % s, '${p}', 'S01', s, 'Planta %d' % s, 'Planta', lid, 'pendente' if s == 3 else 'conferida', json.dumps({"sinais": []})))
${extra}`;
py(`
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
${montar(PA, 171)}
${montar(PB, 172)}
${montar(PC, 173, `con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao) VALUES ('bloqueia','metadado','revisao','${ult(PC)}','Título ilegível')")`)}
${montar(PD, 174)}
`);

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const nova = async (email, senha) => {
    const ctx = await br.newContext({ viewport: { width: 1366, height: 900 } }), pg = await ctx.newPage();
    pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
    pg.on('console', m => { if (m.type() === 'error' && !/\/previa|\/miniatura|Failed to load resource/.test(m.text())) erros.push(m.text()) });
    await pg.goto(BASE + '/'); await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
    await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); return pg };
  const txt = async (pg, s) => ((await pg.$(s)) ? (await pg.textContent(s)).replace(/\s+/g, ' ').trim() : '');
  const ate = (pg, s, t = 10000) => pg.waitForSelector(s, { timeout: t }).then(() => true, () => false);
  // "Está certo" numa folha sem imagem pede confirmação ("conferir sem ver a imagem?"): confirma
  const conferir = async (pg, host) => { await pg.click(`${host} [data-rev-item="conferida"]`); if (await ate(pg, '#conf-ov [data-conf="sim"]', 2500)) { await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 }).catch(() => {}) } };
  try {
    const pg = await nova('rafael@camp.arq.br', 'senha-bem-longa-123');
    const planos = []; pg.on('request', r => { if (/\/publicar\/plano$/.test(r.url())) planos.push(r.url()) });

    // ---- (A) tela de conferir ----
    await pg.evaluate(c => nav('conferir/' + c), PA);
    await ate(pg, `#cf-pane [data-rev-item="conferida"]`, 15000);
    chk((await pg.evaluate(() => CONF.atual)) === ult(PA), '(A) a tela de conferir abre na última folha pendente (D00003)');
    await conferir(pg, '#cf-pane');
    const aprA = await ate(pg, '#cf-pane [data-fim-passo] [data-pp="aprovar"]');
    chk(aprA && /Aprovar o lote/.test(await txt(pg, '#cf-pane [data-fim-passo] [data-pp="aprovar"]')), '(A) depois da última folha: o botão "Aprovar o lote" aparece na própria tela', await txt(pg, '#cf-pane'));
    chk(/Aprovar/.test(await txt(pg, '#cf-pane [data-fim-passo] .caminho .cur')) && /você está aqui/.test(await txt(pg, '#cf-pane [data-fim-passo] .caminho .cur')), '(A) o caminho mostra "você está aqui" em Aprovar', await txt(pg, '#cf-pane [data-fim-passo] .caminho'));
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/fim_conferir_A_aprovar.png' });
    if (aprA) {
      await pg.click('#cf-pane [data-fim-passo] [data-pp="aprovar"]'); await pg.click('#conf-ov [data-conf="sim"]');
      const pubA = await ate(pg, '#cf-pane [data-fim-passo] [data-pp="publicar"]');
      chk(pubA, '(A) aprovado: o mesmo quadro mostra "Publicar" no lugar, sem sair da tela', await txt(pg, '#cf-pane'));
      chk(/^conferir\//.test(await pg.evaluate(() => rotaAtual())), '(A) continua na tela de conferir');
      if (SHOTS) await pg.screenshot({ path: SHOTS + '/fim_conferir_A_publicar.png' });
      if (pubA) {
        await pg.click('#cf-pane [data-fim-passo] [data-pp="publicar"]');
        const abriu = await pg.waitForFunction(() => (document.getElementById('d-title') || {}).textContent === 'Publicar', null, { timeout: 10000 }).then(() => true, () => false);
        chk(abriu && planos.some(u => u.includes(PA)), '(A) "Publicar" abre a publicação guiada do projeto (rota /publicar/plano)', planos.join(' '));
        chk(/^conferir\//.test(await pg.evaluate(() => rotaAtual())), '(A) a publicação abre por cima, sem sair da tela de conferir');
        await pg.evaluate(() => closeDrawer(true));
      }
    }

    // ---- (B) gaveta da página do projeto ----
    await pg.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, PB);
    await ate(pg, `#pj-proximo [data-pp]`, 15000);
    await pg.evaluate(c => abrirRevisaoItem(c), ult(PB)); await ate(pg, '#d-body [data-rev-item="conferida"]');
    await conferir(pg, '#d-body');
    const aprB = await ate(pg, '#d-body [data-fim-passo] [data-pp="aprovar"]');
    chk(aprB && /Conferência concluída/.test(await txt(pg, '#d-title')), '(B) gaveta "Conferência concluída" com "Aprovar o lote" ali mesmo', await txt(pg, '#d-body'));
    if (aprB) {
      await pg.click('#d-body [data-fim-passo] [data-pp="aprovar"]'); await pg.click('#conf-ov [data-conf="sim"]');
      chk(await ate(pg, '#d-body [data-fim-passo] [data-pp="publicar"]'), '(B) aprovado: a gaveta mostra "Publicar"', await txt(pg, '#d-body'));
      chk(await pg.waitForSelector('#pj-proximo [data-pp="publicar"]', { state: 'attached', timeout: 10000 }).then(() => true, () => false), '(B) a página por baixo já mostra "Publicar" no próximo passo, sem recarregar', await txt(pg, '#pj-proximo'));
      const folhas = await pg.waitForFunction(() => /lote aprovado/.test((document.querySelector('#pj-cards [data-pjc="folhas"]') || {}).textContent || ''), null, { timeout: 8000 }).then(() => true, () => false);
      chk(folhas, '(B) o cartão Folhas passa a dizer "lote aprovado" sem recarregar', await txt(pg, '#pj-cards [data-pjc="folhas"]'));
      await pg.evaluate(() => closeDrawer(true));
    }

    // ---- (C) problema que impede publicar ----
    await pg.evaluate(c => nav('conferir/' + c), PC); await ate(pg, `#cf-pane [data-rev-item="conferida"]`, 15000);
    await conferir(pg, '#cf-pane');
    if (await ate(pg, '#cf-pane [data-fim-passo] [data-pp="aprovar"]')) {
      await pg.click('#cf-pane [data-fim-passo] [data-pp="aprovar"]'); await pg.click('#conf-ov [data-conf="sim"]');
      const diz = await pg.waitForFunction(() => /erro bloqueante/.test((document.querySelector('#cf-pane [data-fim-passo]') || {}).textContent || ''), null, { timeout: 10000 }).then(() => true, () => false);
      chk(diz && !(await pg.$('#cf-pane [data-fim-passo] [data-pp="publicar"]')) && !!(await pg.$('#cf-pane [data-fim-passo] [data-pp-cond="erros"]')), '(C) com problema bloqueante: diz "1 erro bloqueante" e oferece "Ver erros", sem "Publicar"', await txt(pg, '#cf-pane [data-fim-passo]'));
    } else chk(false, '(C) "Aprovar o lote" deveria aparecer', await txt(pg, '#cf-pane'));
    await pg.context().close();

    // ---- (D) operador ----
    const po = await nova('operador@camp.arq.br', 'senha-operador-123');
    await po.evaluate(c => nav('conferir/' + c), PD); await ate(po, `#cf-pane [data-rev-item="conferida"]`, 15000);
    await conferir(po, '#cf-pane');
    const falta = await po.waitForFunction(() => /Falta um admin aprovar/.test((document.querySelector('#cf-pane [data-fim-passo]') || {}).textContent || ''), null, { timeout: 10000 }).then(() => true, () => false);
    chk(falta && !(await po.$('#cf-pane [data-pp="aprovar"]')), '(D) operador: "Falta um admin aprovar", sem o botão', await txt(po, '#cf-pane'));
    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } catch (e) { chk(false, 'o teste rodou até o fim', String(e && e.stack || e)) }
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
