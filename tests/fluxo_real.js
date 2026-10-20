// Teste de FLUXO REAL (20/10, "preciso que faça testes de fluxo reais"): o caminho inteiro de um lote, só pelos caminhos de verdade.
// A estação reserva o número (HTTP), o CAMP Vision grava a pasta final (imagens JPG/TIF de verdade, pacote_tainacan.json, erros.json,
// status.json) e avisa o painel (HTTP) — tests/fluxo_real_cv2.py. Daí em diante tudo é CLIQUE no navegador, como a equipe faz:
//   operadora (login pela tela) → Painel "O que fazer agora" → projeto → folhas "de outra obra" (ver imagem, "É deste projeto", desfazer,
//   "É de outro projeto") → conferir as folhas (girar, espelhar, corrigir o ano, duplicata) → as marcas somem → "Falta um admin aprovar"
//   admin → Aprovar o lote → Publicar (site FALSO: tests/servidor_wp_falso.py) → no ar
//   leitura → vê, não age · aviso do CAMP Vision que se perdeu → "Varrer QNAP" + "Importar"
// Cada passo grava um print em SAIDA. Nada toca o QNAP ou o site reais. Rodar com: bash tests/rodar_fluxo_real.sh
const { execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE, DB = process.env.CAMP_DB_PATH, RAIZ = process.env.FLUXO_RAIZ, SAIDA = process.env.SAIDA || '/tmp/fluxo_real';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
if (!BASE || !DB || !RAIZ) { console.error('use tests/rodar_fluxo_real.sh'); process.exit(2); }
fs.mkdirSync(SAIDA, { recursive: true });
const linhas = [], problemas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + String(det).slice(0, 400))); if (!ok) problemas.push(msg); return ok };
const passo = t => linhas.push('\n== ' + t);
const cv2 = (...a) => execFileSync('python3', [path.join(__dirname, 'fluxo_real_cv2.py'), ...a], { encoding: 'utf-8' }).trim();
const sql = (q, ...a) => JSON.parse(execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\nprint(json.dumps(con.execute(sys.argv[2],sys.argv[3:]).fetchall()))', DB, q, ...a], { encoding: 'utf-8' }));
const um = (q, ...a) => (sql(q, ...a)[0] || [])[0];
const espera = async (f, ms = 12000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true } catch (_) {} await new Promise(r => setTimeout(r, 250)); } return false; };
let nPrint = 0;
const print = async (pg, nome) => { nPrint++; await pg.screenshot({ path: path.join(SAIDA, `${String(nPrint).padStart(2, '0')}_${nome}.png`) }).catch(() => {}) };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const errosJs = [], http5 = [];
  const entrar = async (email, senha) => {
    const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }), pg = await ctx.newPage();
    pg.on('pageerror', e => errosJs.push(`${email}: ${e.message}`));
    pg.on('response', r => { if (r.status() >= 500) http5.push(`${email}: ${r.status()} ${r.url().replace(BASE, '')}`) });
    pg.on('dialog', d => d.accept());
    await pg.goto(BASE + '/'); await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
    await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    return pg;
  };
  const txt = async (pg, s) => ((await pg.$(s)) ? (await pg.innerText(s)).replace(/\s+/g, ' ').trim() : '');
  const confirmar = async pg => { if (await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 2500 }).then(() => true, () => false)) { await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 }).catch(() => {}) } };
  const imgOk = (pg, sel) => espera(() => pg.$eval(sel, i => i.complete && i.naturalWidth > 0));

  // ---------------- 0) estação + CAMP Vision ----------------
  passo('0) Estação reserva o número; CAMP Vision lê e avisa o painel');
  const NOME = 'RESIDENCIA FLUXO REAL';
  const P = cv2('reservar', BASE, 'F026', NOME, '1972');
  chk(/^F026-P\d{4}$/.test(P), `a estação reservou o número do projeto: ${P}`);
  const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
  const a1 = JSON.parse(cv2('processando', BASE, RAIZ, P, NOME));
  chk(a1.ok && a1.etapa === 'processando', 'aviso "processando" do CAMP Vision: o painel cria o lote', JSON.stringify(a1));
  const op = await entrar('operador@camp.arq.br', 'senha-operador-123');
  await op.evaluate(c => nav('projeto/' + c), P); await op.waitForSelector('#pj-cards', { timeout: 15000 }); await op.waitForTimeout(1500);
  chk(/lendo|CAMP Vision/i.test(await txt(op, '#pd')), 'operadora: a página do projeto diz que o CAMP Vision está lendo', await txt(op, '#pj-cards'));
  await print(op, 'cv_lendo');
  const a2 = JSON.parse(cv2('pronto', BASE, RAIZ, P));
  chk(a2.ok && a2.etapa === 'revisao' && (a2.importacao || {}).criadas === 6, 'aviso "pronto": o painel importa sozinho as 6 folhas (2 ficaram de fora por serem de outra obra)', JSON.stringify(a2).slice(0, 300));

  // ---------------- 1) operadora: do Painel ao projeto ----------------
  passo('1) Operadora: Painel → "O que fazer agora" → projeto');
  await op.evaluate(() => nav('painel')); await op.waitForTimeout(2500);
  const linhaIni = op.locator('.ini-task').filter({ hasText: NOME }).filter({ has: op.locator('button:text-is("Conferir")') }).first();
  const temIni = await linhaIni.count() > 0;
  chk(temIni, '"O que fazer agora" mostra o projeto com o botão "Conferir"');
  await print(op, 'painel_inicial');
  if (temIni) { await linhaIni.locator('button:text-is("Conferir")').first().click(); await op.waitForTimeout(2000) }
  const rota1 = await op.evaluate(() => rotaAtual());
  chk(rota1.includes(P), '"Conferir" leva ao projeto certo', rota1);
  await op.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P);
  await op.waitForSelector('#pj-cards .pjc[data-pjc="problemas"]', { timeout: 15000 }); await op.waitForTimeout(2000);

  // ---------------- 2) folhas "de outra obra" ----------------
  passo('2) Folhas que o CAMP Vision achou ser de outra obra (D00007 e D00008)');
  const naLista = await op.waitForSelector(`#pj-probs [data-fp-box="${D(7)}"]`, { timeout: 10000 }).then(() => true, () => false);
  chk(naLista && await op.isVisible('#pj-probs'), '"Problemas que impedem publicar" abre sozinha e lista a D00007', await txt(op, '#pj-gaveta'));
  chk(await imgOk(op, `#pj-probs [data-fp-box="${D(7)}"] img`), 'a miniatura da D00007 carrega (a folha não está no painel: vem da pasta do CAMP Vision)');
  chk(await imgOk(op, `#pj-probs [data-fp-box="${D(8)}"] img`), 'a miniatura da D00008 carrega');
  await print(op, 'outra_obra_lista');
  const [aba] = await Promise.all([op.context().waitForEvent('page', { timeout: 8000 }).catch(() => null), op.click(`#pj-probs [data-fp-folha="${D(7)}"]`).catch(() => {})]);
  if (aba) { const r = await aba.waitForLoadState().then(() => aba.evaluate(() => ({ t: document.contentType, w: (document.images[0] || {}).naturalWidth || 0 }))).catch(() => ({}));
    chk(/image/.test(r.t || '') && r.w > 300, 'um clique abre a D00007 grande em outra aba (imagem de verdade)', JSON.stringify(r)); await aba.close() }
  else chk(false, 'um clique abre a D00007 grande em outra aba');
  // É deste projeto → Desfazer → É deste projeto de novo
  await op.click(`#pj-probs [data-fp-box="${D(7)}"] [data-deste-projeto]`); await confirmar(op);
  chk(await espera(() => um('SELECT status_site FROM item WHERE codigo=?', D(7)) === 'nao_publicado', 15000), '"É deste projeto": a D00007 entra no projeto, liberada para publicar', um('SELECT status_site FROM item WHERE codigo=?', D(7)));
  const toast1 = await txt(op, '#toast'); chk(/Desfazer/.test(toast1), 'o aviso oferece "Desfazer"', toast1);
  await print(op, 'deste_projeto');
  const bDesf = await op.$('#toast button, #toast [data-deste-desfazer]');
  if (bDesf) { await bDesf.click(); await confirmar(op) }
  else { await op.evaluate(c => nav('erros/' + c), P); await op.click('#err-abas [data-err-sit="ignorado"]'); await op.click(`#err-body [data-deste-desfazer="${D(7)}"]`); await confirmar(op) }
  chk(await espera(() => um('SELECT status_site FROM item WHERE codigo=?', D(7)) === 'bloqueado'), '"Desfazer": a D00007 volta a ficar bloqueada como de outra obra');
  chk(um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao='aberto' AND gravidade='bloqueia'", D(7)) >= 1, 'o problema que impede publicar reabre');
  // decide de novo, agora pela tela Problemas (o outro caminho que a operadora usa)
  await op.evaluate(c => nav('erros/' + c), P);
  const temErr = await op.waitForSelector(`#err-body [data-fp-box="${D(7)}"] [data-deste-projeto], #err-body [data-deste-projeto="${D(7)}"]`, { timeout: 10000 }).then(() => true, () => false);
  chk(temErr, 'tela Problemas: a D00007 de novo com "É deste projeto"');
  if (temErr) { await op.click(`#err-body [data-fp-box="${D(7)}"] [data-deste-projeto], #err-body [data-deste-projeto="${D(7)}"]`); await confirmar(op) }
  chk(await espera(() => um('SELECT status_site FROM item WHERE codigo=?', D(7)) === 'nao_publicado'), 'refeito: a D00007 é deste projeto outra vez');
  chk(await espera(() => um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')", D(7)) === 0), 'refeito: nenhum problema da D00007 continua aberto (o "outra pasta" do erros.json também fecha)',
      JSON.stringify(sql("SELECT categoria, gravidade, descricao FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')", D(7))));
  // D00008: é mesmo de outra obra
  await op.waitForSelector(`#err-body [data-fp-outro="${D(8)}"]`, { timeout: 10000 }).catch(() => {});
  await op.click(`#err-body [data-fp-outro="${D(8)}"]`).catch(() => {}); await confirmar(op);
  chk(await espera(() => um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')", D(8)) === 0), '"É de outro projeto…": a D00008 fica fora e os problemas dela fecham');
  chk(!um('SELECT COUNT(*) FROM item WHERE codigo=?', D(8)), 'a D00008 não entra no projeto');
  await print(op, 'problemas_depois');

  // ---------------- 3) conferir ----------------
  passo('3) Conferir as 7 folhas');
  await op.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P);
  const temConf = await op.waitForSelector(`#pj-cards [data-pjc-conferir="${P}"]`, { timeout: 15000 }).then(() => true, () => false);
  chk(temConf, 'cartão Folhas: botão "Conferir"', await txt(op, '#pj-cards'));
  await print(op, 'projeto_antes_conferir');
  if (temConf) await op.click(`#pj-cards [data-pjc-conferir="${P}"]`); else await op.evaluate(c => nav('conferir/' + c), P);
  await op.waitForSelector('#cf-pane [data-rev-item="conferida"]', { timeout: 15000 }); await op.waitForTimeout(800);
  chk((await op.evaluate(() => rotaAtual())).startsWith('conferir/' + P), '"Conferir" abre a tela de conferir do projeto');
  const nProb = Number(await op.$eval('#cf-filtros [data-cf-filtro="problema"] b', b => b.textContent).catch(() => -1));
  chk(nProb >= 4, `filtro "Com problema" conta as folhas com aviso (giro, espelho, ano, duplicata): ${nProb}`);
  await print(op, 'conferir_inicio');
  const feito = {};
  for (let volta = 0; volta < 12; volta++) {
    if (await op.$('#cf-pane [data-fim-passo]')) break;
    const cod = await op.evaluate(() => CONF.atual); if (!cod) break;
    const n = Number(cod.slice(-2)), pane = async () => txt(op, '#cf-pane');
    await imgOk(op, '#cf-pane img').then(ok => chk(ok, `D${String(n).padStart(5, '0')}: a imagem grande carrega`));
    if (n === 2) {
      chk(/Orientação incerta/.test(await pane()), 'D00002: aviso "Orientação incerta"');
      const g0 = um('SELECT giro_manual FROM item WHERE codigo=?', cod);
      await op.click(`#cf-pane .cf-aviso [data-rev-girar="90"]`); await op.waitForTimeout(900); await op.click(`#cf-pane .cf-aviso [data-rev-girar="90"]`).catch(() => op.click('#cf-pane [data-rev-girar="90"]'));
      chk(await espera(() => ((um('SELECT giro_manual FROM item WHERE codigo=?', cod) || 0) - (g0 || 0) + 360) % 360 === 180), 'D00002: virou 180° (de cabeça para baixo → em pé)', um('SELECT giro_manual FROM item WHERE codigo=?', cod));
      await print(op, 'D2_girada');
    }
    if (n === 3) {
      const tem = /Espelhada\?/.test(await pane()); chk(tem, 'D00003: aviso "Espelhada?" com o botão Espelhar', (await pane()).slice(0, 300));
      // a imagem já aparece certa (o painel desfaz o espelho que o CAMP Vision apontou): a pessoa só confere; "Espelhar" seria para texto ao contrário
      await print(op, 'D3_espelho');
    }
    if (n === 4) {
      const t = await pane(); chk(/1927/.test(t) && /diverge/.test(t), 'D00004: o problema "ano lido 1927 diverge do projeto (1972)" aparece na folha', t.slice(0, 400));
      await print(op, 'D4_problema');
      await op.fill('#rv-ano', '1972'); await op.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(op);
      chk(await espera(() => um('SELECT ano_folha FROM item WHERE codigo=?', cod) == 1972), 'D00004: ano corrigido para 1972 ("Salvar correção")', um('SELECT ano_folha FROM item WHERE codigo=?', cod));
      feito[n] = 1; await op.waitForTimeout(800); continue;
    }
    if (n === 5) {
      chk(/Duplicata/.test(await pane()), 'D00005: aviso "Duplicata" (cópia da D00001)');
      await print(op, 'D5_duplicata');
    }
    await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op); feito[n] = 1;
    await espera(async () => (await op.evaluate(() => CONF.atual)) !== cod || !!(await op.$('#cf-pane [data-fim-passo]')), 8000);
  }
  chk(Object.keys(feito).length >= 7, `todas as folhas passaram pela conferência: ${Object.keys(feito).map(n => 'D' + n).join(', ')}`);
  chk(await espera(() => op.$('#cf-pane [data-fim-passo]').then(Boolean)), 'última folha conferida: o próximo passo aparece na própria tela');
  const fimOp = await txt(op, '#cf-pane'); chk(/Falta um admin aprovar/.test(fimOp), 'operadora: "Falta um admin aprovar" (sem botão de aprovar)', fimOp.slice(0, 300));
  await print(op, 'conferir_fim_operadora');
  const nProb2 = Number(await op.$eval('#cf-filtros [data-cf-filtro="problema"] b', b => b.textContent).catch(() => -1));
  chk(nProb2 <= 1, `depois de conferir, as marcas saem: "Com problema" ${nProb} → ${nProb2} (só a duplicata pode ficar)`);
  const abertos = sql("SELECT codigo, categoria, gravidade FROM erro WHERE (codigo LIKE ? ) AND situacao IN ('aberto','em_correcao')", P + '%');
  chk(!abertos.some(e => ['orientacao', 'espelhado', 'metadado'].includes(e[1])), 'os problemas de giro, espelho e ano lido fecharam no banco', JSON.stringify(abertos));
  chk(!abertos.some(e => e[2] === 'bloqueia'), 'nenhum problema que impede publicar ficou aberto', JSON.stringify(abertos));

  await op.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P); await op.waitForSelector('#pj-cards .pjc[data-pjc="problemas"]', { timeout: 15000 }); await op.waitForTimeout(1500);
  const cProb = await txt(op, '#pj-cards .pjc[data-pjc="problemas"]');
  chk(/^PROBLEMAS 1 aviso/i.test(cProb), 'cartão Problemas concorda com o conferir: só a duplicata (1 aviso)', cProb);
  // ---------------- 4) admin: aprovar e publicar ----------------
  passo('4) Admin: aprovar o lote e publicar (site falso)');
  const ad = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
  await ad.evaluate(() => nav('painel')); await ad.waitForTimeout(2500);
  const linhaAd = ad.locator('.ini-task').filter({ hasText: NOME }).first();
  const temLinhaAd = await linhaAd.count() > 0;
  chk(temLinhaAd && /aprovar/i.test(await linhaAd.innerText()), 'Painel do admin: "O que fazer agora" mostra o projeto para aprovar', temLinhaAd ? await linhaAd.innerText() : '(não aparece)');
  await print(ad, 'admin_painel');
  let aprovouNoPainel = false;
  if (temLinhaAd) { await linhaAd.locator('button').first().click();
    if (await ad.waitForSelector('#conf-ov', { timeout: 3000 }).then(() => true, () => false)) {   // o botão do Painel já pede a confirmação ali mesmo
      chk(/aprovar/i.test(await txt(ad, '#conf-ov')), 'o botão do Painel pede confirmação para aprovar o lote', await txt(ad, '#conf-ov'));
      await print(ad, 'admin_aprovar'); await confirmar(ad); aprovouNoPainel = true } else await ad.waitForTimeout(1500) }
  if (!aprovouNoPainel) {
    if (!(await ad.evaluate(() => rotaAtual())).includes(P)) await ad.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P);
    const temApr = await ad.waitForSelector('[data-pp="aprovar"]:visible', { timeout: 15000 }).then(() => true, () => false);
    chk(temApr, '"Aprovar o lote" visível', await txt(ad, '#pd'));
    await print(ad, 'admin_aprovar');
    if (temApr) { await ad.click('[data-pp="aprovar"]:visible'); await confirmar(ad) } }
  chk(await espera(() => um("SELECT aprovado_em IS NOT NULL FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", P) === 1), 'lote aprovado');
  if (!(await ad.evaluate(() => rotaAtual())).includes(P)) { await ad.waitForTimeout(1000); await ad.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P) }
  const temPub = await ad.waitForSelector('[data-pp="publicar"]:visible, [data-pjc-publicar]:not([aria-disabled]):visible', { timeout: 15000 }).then(() => true, () => false);
  chk(temPub, 'a página do projeto oferece "Publicar"', await txt(ad, '#pd'));
  await print(ad, 'admin_publicar');
  if (temPub) {
    await ad.locator('[data-pp="publicar"]:visible, [data-pjc-publicar]:not([aria-disabled]):visible').first().click();
    const go = await ad.waitForSelector('#pub-go:not([disabled])', { timeout: 15000 }).then(() => true, () => false);
    chk(go, 'a publicação guiada abre com "Publicar agora" liberado', await txt(ad, '#d-body'));
    await print(ad, 'publicacao_plano');
    if (go) {
      await ad.click('#pub-go');
      const fim = await ad.waitForSelector('#d-body .pub-resultado', { timeout: 60000 }).then(() => true, () => false);
      const corpo = await txt(ad, '#d-body'); chk(fim && /Publicado|O que ficou público/.test(corpo), 'publicado: a tela diz o que ficou público', corpo.slice(0, 400));
      await print(ad, 'publicado');
    }
  }
  await ad.keyboard.press('Escape'); await ad.waitForTimeout(800);
  const barra = await txt(ad, '.folhas-bar'), mSite = barra.match(/· (\d+) no site/), fSite = barra.match(/No site \((\d+)\)/);
  chk(mSite && fSite && mSite[1] === fSite[1] && fSite[1] === '6', 'depois de publicar, a barra das folhas diz o mesmo número no texto e no filtro (6 no site)', barra);
  const st = um('SELECT status_site FROM projeto WHERE codigo=?', P), noAr = sql("SELECT substr(codigo,-6) FROM item WHERE projeto_codigo=? AND status_site='no_ar' ORDER BY codigo", P).map(r => r[0]);
  chk(st === 'no_ar', 'o projeto está no ar', st);
  chk(noAr.join(',') === 'D00001,D00002,D00003,D00004,D00006,D00007', 'no site: D1, D2, D3, D4, D6 e a D7 (devolvida); a duplicata D5 e a D8 (outra obra) ficam fora', noAr.join(','));
  chk(um('SELECT ano_folha FROM item WHERE codigo=?', D(4)) == 1972, 'a D00004 foi publicada com o ano corrigido (1972)');

  // ---------------- 5) leitura ----------------
  passo('5) Leitura: vê, não age');
  const le = await entrar('leitor@camp.arq.br', 'senha-leitor-1234');
  await le.evaluate(c => nav('projeto/' + c), P); await le.waitForSelector('#pj-cards', { timeout: 15000 }); await le.waitForTimeout(2000);
  chk(!(await le.$('#pd [data-pp]:visible, #pd [data-rev-item]:visible, #pd [data-deste-projeto]:visible')), 'leitura não vê botões de ação no projeto');
  chk(await imgOk(le, '#pd .thumb img'), 'leitura vê as miniaturas');
  await print(le, 'leitura');

  // ---------------- 6) aviso perdido ----------------
  passo('6) O aviso "pronto" do CAMP Vision se perdeu: Varrer QNAP + Importar');
  const P2 = cv2('reservar', BASE, 'F026', 'CASA AVISO PERDIDO', '1972');
  cv2('processando', BASE, RAIZ, P2, 'CASA AVISO PERDIDO'); cv2('pronto', BASE, RAIZ, P2, '--sem-aviso');
  chk(!um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P2), 'sem o aviso, as folhas ainda não estão no painel');
  await op.evaluate(() => nav('filas')); await op.waitForTimeout(1500);
  const bV = op.locator('button', { hasText: /Varrer QNAP|Atualizar do QNAP|Ler o QNAP/ }).first();
  const temV = await bV.count() > 0; chk(temV, 'Material novo: botão para varrer o QNAP');
  if (temV) { await bV.click(); await confirmar(op); await op.waitForTimeout(4000) }
  await print(op, 'varrer');
  await op.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P2); await op.waitForSelector('#pj-cards', { timeout: 15000 }); await op.waitForTimeout(2000);
  if (!um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P2)) {
    const bI = await op.$('#pd [data-pp="importar"], #pd button:text("Importar folhas")');
    chk(!!bI, 'a página do projeto oferece "Importar folhas"', await txt(op, '#pj-cards'));
    if (bI) { await bI.click(); await op.waitForTimeout(500) }
    await print(op, 'importar');
  }
  chk(await espera(() => um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P2) === 6, 20000), 'as 6 folhas do lote chegaram ao painel', um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P2));

  chk(!errosJs.length, 'nenhum erro de JavaScript em nenhuma tela', errosJs.join(' | '));
  chk(!http5.length, 'nenhuma resposta 500 do painel', http5.join(' | '));
  await br.close();
  const rel = linhas.join('\n') + (problemas.length ? `\n\n${problemas.length} FALHA(S)` : '\n\nTUDO OK');
  fs.writeFileSync(path.join(SAIDA, 'relatorio.txt'), rel + '\n'); console.log(rel); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); console.log(linhas.join('\n')); process.exit(1); });
