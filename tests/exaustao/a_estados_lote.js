// Exaustão da página do projeto, grupo A: ESTADOS DO LOTE (CAMP-072 a CAMP-079). Tudo pelo caminho real: a estação reserva, o CAMP Vision grava a
// pasta e avisa (tests/fluxo_real_cv2.py; cenários extras em tests/exaustao/a_montar.py) e a equipe CLICA no navegador.
// Rodar: bash tests/rodar_exaustao.sh tests/exaustao/a_estados_lote.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const T = require('./_comum');
const { chk, passo, sql, um, espera, print, txt, confirmar, imgOk, entrar, abrirProjeto, abrirConferir, cv2, BASE, RAIZ } = T;
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'a_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const cartao = (pg, k) => txt(pg, `#pj-cards .pjc[data-pjc="${k}"]`);
const corCartao = (pg, k) => pg.$eval(`#pj-cards .pjc[data-pjc="${k}"]`, c => c.className.replace('pjc', '').trim()).catch(() => '?');
const gavetaAberta = pg => pg.evaluate(() => { const g = document.getElementById('pj-gaveta'); if (!g || g.hidden) return null; const s = [...g.querySelectorAll('.pj-gav')].find(x => !x.hidden); return s ? s.dataset.gav : null });
const botoesVisiveis = pg => pg.$$eval('#pj-cards button, #pj-cards a.btn', l => l.filter(b => b.offsetParent).map(b => b.textContent.trim()));
const reservar = nome => cv2('reservar', BASE, 'F026', nome, '1972');
// conferir todas as folhas do lote pela tela de conferir ("Está certo" em cada uma)
const conferirTudo = async (pg, P) => {
  await abrirConferir(pg, P); await pg.waitForSelector('#cf-pane [data-rev-item="conferida"], #cf-pane [data-fim-passo]', { timeout: 15000 });
  for (let i = 0; i < 30; i++) {
    if (await pg.$('#cf-pane [data-fim-passo]')) return true;
    const cod = await pg.evaluate(() => CONF.atual); if (!cod) return false;
    await pg.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(pg);
    await espera(async () => (await pg.evaluate(() => CONF.atual)) !== cod || !!(await pg.$('#cf-pane [data-fim-passo]')), 8000);
  }
  return !!(await pg.$('#cf-pane [data-fim-passo]'));
};

T.rodar(async () => { let pilhas = [];
  const op = await entrar('operador'), ad = await entrar('admin');
  for (const pg of [op, ad]) pg.on('pageerror', e => pilhas.push((e.stack || e.message).split('\n').slice(0, 4).join(' ⟵ ')));

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-072: projeto sem nenhum lote (só reservado pela estação)');
  const P72 = reservar('CASA SEM LOTE');
  await abrirProjeto(op, P72);
  const c72 = await cartao(op, 'folhas');
  chk(/nenhuma folha/i.test(c72), 'CAMP-072: cartão Folhas diz "nenhuma folha no painel ainda"', c72);
  chk(['problemas', 'dados', 'site'].every(Boolean) && (await op.$$('#pj-cards .pjc')).length === 4, 'CAMP-072: os 4 cartões aparecem');
  chk(!(await gavetaAberta(op)), 'CAMP-072: nenhuma gaveta abre sozinha', await gavetaAberta(op));
  const b72 = await botoesVisiveis(op);
  chk(!b72.some(t => /Importar|Conferir|Aprovar|Publicar$/.test(t)), 'CAMP-072: nenhum botão de etapa que não se aplica (Importar/Conferir/Aprovar/Publicar)', b72.join(' | '));
  const site72 = await cartao(op, 'site'); chk(!/pronto: o painel autoriza/.test(site72), 'CAMP-072: cartão Site não diz que está pronto para publicar um projeto sem folhas', site72);
  await print(op, '072_sem_lote');
  // admin: o que o admin vê também não pode oferecer publicar nada
  await abrirProjeto(ad, P72);
  const pub72 = await ad.$('#pj-cards [data-pjc-publicar]:not([aria-disabled])');
  chk(!pub72, 'CAMP-072: admin não vê "Publicar" liberado num projeto sem folhas', await cartao(ad, 'site'));
  await print(ad, '072_sem_lote_admin');

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-073: CAMP Vision lendo (processando)');
  const NOME73 = 'CASA LENDO';
  const P73 = reservar(NOME73); cv2('processando', BASE, RAIZ, P73, NOME73);
  await abrirProjeto(op, P73);
  const c73 = await cartao(op, 'folhas');
  chk(/CAMP Vision est[aá] lendo|na fila do CAMP Vision/.test(c73), 'CAMP-073: cartão Folhas diz que o CAMP Vision está lendo', c73);
  const b73 = await botoesVisiveis(op);
  chk(!b73.some(t => /^Importar|^Conferir$/.test(t)), 'CAMP-073: sem Importar nem Conferir enquanto lê', b73.join(' | '));
  chk(!(await gavetaAberta(op)) || (await gavetaAberta(op)) !== 'problemas', 'CAMP-073: nada de "problemas" aberto enquanto lê');
  await print(op, '073_lendo');
  // chega o "pronto" com a página aberta: ao voltar à página (ou recarregar) as folhas estão lá, sem quebrar
  cv2('pronto', BASE, RAIZ, P73);
  await op.reload(); await op.waitForSelector('#pj-cards .pjc[data-pjc="site"]', { timeout: 15000 }); await op.waitForTimeout(1500);
  const c73b = await cartao(op, 'folhas');
  chk(/a conferir/.test(c73b) && !/está lendo/.test(c73b), 'CAMP-073: depois do "pronto", o cartão mostra as folhas a conferir e não diz mais "lendo"', c73b);
  await print(op, '073_pronto');

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-074: CAMP Vision parou com erro');
  const NOME74 = 'CASA COM ERRO', MSG74 = 'falha ao ler o TIF scan 004.tif: arquivo corrompido';
  const P74 = reservar(NOME74); cv2('processando', BASE, RAIZ, P74, NOME74);
  const r74 = JSON.parse(montar('erro', BASE, RAIZ, P74, MSG74));
  chk(r74.etapa === 'erro', 'CAMP-074: o aviso de erro do CAMP Vision põe o lote em "erro"', JSON.stringify(r74));
  await abrirProjeto(op, P74);
  const c74 = await cartao(op, 'folhas');
  chk((await corCartao(op, 'folhas')) === 'bl', 'CAMP-074: cartão Folhas vermelho', await corCartao(op, 'folhas'));
  chk(/parado por erro/i.test(c74) && !/corrompido/.test(c74), 'CAMP-074: o cartão diz que parou (CAMP-128: em 1 linha; a mensagem fica uma vez, na gaveta)', c74);
  chk((await gavetaAberta(op)) === 'folhas', 'CAMP-074: "Detalhes dos lotes" abre sozinha', await gavetaAberta(op));
  const g74 = await txt(op, '#pj-gaveta');
  chk(/corrompido/.test(g74), 'CAMP-074: a gaveta mostra a mensagem do CAMP Vision', g74.slice(0, 400));
  const rel74 = await op.$('#pj-gav-erro [data-releitura-projeto]');
  chk(!!rel74 && (await op.$$('#pd [data-releitura-projeto]')).length === 1, 'CAMP-074: oferece "Pedir releitura" (CAMP-128: um só, junto da mensagem)');
  await print(op, '074_erro');
  if (rel74) { await rel74.click(); await confirmar(op); await op.waitForTimeout(1500);
    chk(um("SELECT COUNT(*) FROM pedido_releitura WHERE projeto_codigo=?", P74) >= 1, 'CAMP-074: "Pedir releitura" registra o pedido para o CAMP Vision');
    const t74 = await txt(op, '#toast'); chk(/releitura|pedido|CAMP Vision/i.test(t74), 'CAMP-074: aviso de que o pedido foi feito', t74) }
  await op.evaluate(() => nav('painel')); await op.waitForTimeout(2500);
  const ini74 = op.locator('.ini-task').filter({ hasText: P74 });
  chk(await ini74.count() > 0, 'CAMP-074: o Painel inicial mostra o lote parado', (await txt(op, '#pd')).slice(0, 300));
  await print(op, '074_painel');

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-075: aviso "pronto" perdido → Varrer QNAP → Importar');
  const NOME75 = 'CASA AVISO PERDIDO';
  const P75 = reservar(NOME75); cv2('processando', BASE, RAIZ, P75, NOME75); cv2('pronto', BASE, RAIZ, P75, '--sem-aviso');
  await op.evaluate(() => nav('filas')); await op.waitForTimeout(1500);
  const bV = op.locator('button', { hasText: /Varrer QNAP|Atualizar do QNAP|Ler o QNAP/ }).first();
  chk(await bV.count() > 0, 'CAMP-075: Material novo tem o botão de varrer o QNAP');
  if (await bV.count()) { await bV.click(); await confirmar(op); await espera(async () => !/Varrendo|Lendo/.test(await txt(op, '#pd')), 15000); await op.waitForTimeout(1500) }
  await abrirProjeto(op, P75);
  const bImp = await op.$('#pj-cards [data-pp="importar"]');
  chk(!!bImp && /Importar folhas/.test(await bImp.textContent()), 'CAMP-075: cartão Folhas mostra "Importar folhas"', await cartao(op, 'folhas'));
  await print(op, '075_importar');
  if (bImp) {
    let viuImportando = false;
    const obs = op.waitForFunction(() => { const b = document.querySelector('#pj-cards [data-pp="importar"]'); return !!document.querySelector('[data-aviso-id="lote"], .aviso-rodando') || (b && b.disabled) }, null, { timeout: 5000 }).then(() => { viuImportando = true }, () => {});
    await bImp.click(); await obs;
    chk(viuImportando, 'CAMP-075: ao clicar mostra "Importando…"/desliga o botão');
    chk(await espera(() => um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P75) === 6, 15000), 'CAMP-075: as 6 folhas entram no painel');
    chk(await espera(async () => /0 \/ 6|a conferir/.test(await cartao(op, 'folhas')), 10000), 'CAMP-075: o cartão Folhas atualiza sozinho (sem recarregar) com as folhas a conferir', await cartao(op, 'folhas'));
    chk(await espera(async () => !(await op.$('#pj-cards [data-pp="importar"]')), 10000), 'CAMP-075: o botão Importar some depois de importar');
    await print(op, '075_importado');
  }

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-076: Importar com a pasta sumida e com o QNAP fora');
  const NOME76 = 'CASA PASTA SUMIDA';
  const P76 = reservar(NOME76); cv2('processando', BASE, RAIZ, P76, NOME76); cv2('pronto', BASE, RAIZ, P76, '--sem-aviso');
  // a pasta existe quando o lote é registrado (varredura), depois some
  await op.evaluate(() => nav('filas')); await op.waitForTimeout(1200);
  if (await bV.count()) { await op.locator('button', { hasText: /Varrer QNAP|Atualizar do QNAP|Ler o QNAP/ }).first().click(); await confirmar(op); await op.waitForTimeout(4000) }
  chk(um("SELECT etapa FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", P76) === 'revisao', 'CAMP-076: lote registrado pela varredura', um("SELECT etapa FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", P76));
  montar('sumir', RAIZ, P76);
  await abrirProjeto(op, P76);
  const c76 = await cartao(op, 'folhas');
  chk(!(await op.$('#pj-cards [data-pp="importar"]')), 'CAMP-076: pasta sumida: o botão Importar não aparece', c76);
  chk(/Ainda não dá para importar/.test(c76) && /pasta|QNAP/i.test(c76), 'CAMP-076: o cartão diz por que não dá para importar (pasta)', c76);
  await print(op, '076_pasta_sumida');
  // QNAP inteiro fora: raiz que não existe
  const P76b = reservar('CASA QNAP FORA'); cv2('processando', BASE, RAIZ, P76b, 'CASA QNAP FORA'); cv2('pronto', BASE, RAIZ, P76b, '--sem-aviso');
  await op.evaluate(() => nav('filas')); await op.waitForTimeout(1200);
  await op.locator('button', { hasText: /Varrer QNAP|Atualizar do QNAP|Ler o QNAP/ }).first().click().catch(() => {}); await confirmar(op); await op.waitForTimeout(4000);
  fs.renameSync(RAIZ, RAIZ + '_desmontado');   // o QNAP sai do ar: a raiz final some inteira
  try {
    await abrirProjeto(op, P76b);
    const c76b = await cartao(op, 'folhas');
    chk(!(await op.$('#pj-cards [data-pp="importar"]')), 'CAMP-076: QNAP fora: o botão Importar não aparece', c76b);
    chk(/Ainda não dá para importar/.test(c76b) && /QNAP|pasta/i.test(c76b), 'CAMP-076: QNAP fora: o cartão diz por que', c76b);
    await print(op, '076_qnap_fora');
  } finally { fs.renameSync(RAIZ + '_desmontado', RAIZ) }

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-077: dois lotes (complemento depois do primeiro aprovado)');
  const NOME77 = 'CASA COMPLEMENTO';
  const P77 = reservar(NOME77); cv2('processando', BASE, RAIZ, P77, NOME77); cv2('pronto', BASE, RAIZ, P77);
  chk(await conferirTudo(ad, P77), 'CAMP-077: admin confere as 6 folhas do primeiro lote');
  const apr = await ad.$('#cf-pane [data-fim-passo] [data-pp="aprovar"]');
  chk(!!apr, 'CAMP-077: fim da conferência oferece "Aprovar o lote"');
  if (apr) { await apr.click(); await confirmar(ad) }
  chk(await espera(() => um("SELECT aprovado_em IS NOT NULL FROM lista_processamento WHERE projeto_codigo=? ORDER BY id LIMIT 1", P77) === 1), 'CAMP-077: primeiro lote aprovado');
  const antes77 = sql("SELECT codigo, revisao, titulo FROM item WHERE projeto_codigo=? ORDER BY codigo", P77);
  const r77 = JSON.parse(montar('complemento', BASE, RAIZ, P77, '2'));
  chk(r77.acao === 'complemento', 'CAMP-077: o aviso cria um lote de complemento', JSON.stringify(r77).slice(0, 300));
  chk(await espera(() => um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P77) === 8), 'CAMP-077: as 2 folhas novas entram (8 no total)', um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P77));
  const depois77 = sql("SELECT codigo, revisao, titulo FROM item WHERE projeto_codigo=? AND codigo IN (" + antes77.map(() => '?').join(',') + ") ORDER BY codigo", P77, ...antes77.map(r => r[0]));
  chk(JSON.stringify(antes77) === JSON.stringify(depois77), 'CAMP-077: as folhas do primeiro lote não mudam');
  await abrirProjeto(op, P77);
  const c77 = await cartao(op, 'folhas');
  chk(/6 \/ 8/.test(c77) && /2 a conferir/.test(c77), 'CAMP-077: cartão Folhas: 6 de 8 conferidas, 2 a conferir', c77);
  const det77 = await op.$('#pj-cards [data-pjc-gav="folhas"]'); if (det77 && (await gavetaAberta(op)) !== 'folhas') await det77.click(); await op.waitForTimeout(800);
  const g77 = await txt(op, '#pj-gaveta');
  chk(/complemento/i.test(g77), 'CAMP-077: "Detalhes dos lotes" mostra os dois lotes (o complemento identificado)', g77.slice(0, 500));
  await print(op, '077_dois_lotes');
  await abrirConferir(op, P77);
  const fila77 = await op.$$eval('#cf-linhas .cf-linha', l => l.map(x => x.dataset.cfFolha));
  const pend77 = await op.evaluate(() => CONF.atual);
  chk(/D0000(9)$|D00010$/.test(pend77 || ''), 'CAMP-077: o conferir abre direto numa folha nova (pendente)', pend77);
  chk((await op.$eval('#cf-filtros [data-cf-filtro="a_conferir"] b', b => b.textContent).catch(() => '')) === '2', 'CAMP-077: "A conferir" conta só as 2 novas', await txt(op, '#cf-filtros'));
  await print(op, '077_conferir');

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-078: lote descartado');
  const NOME78 = 'CASA DESCARTADA';
  const P78 = reservar(NOME78); cv2('processando', BASE, RAIZ, P78, NOME78);
  const L78 = um("SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", P78);
  await abrirProjeto(ad, P78);
  await ad.locator('.content.on summary', { hasText: /^Mais/ }).first().click().catch(() => {}); await ad.waitForTimeout(400);
  await ad.locator('.content.on .mais-lista [data-pj-mais]').first().click().catch(() => {}); await ad.waitForTimeout(800);
  const opDesc = ad.locator('[data-mais="descartar"]').first();
  const temDesc = await opDesc.count() > 0 && await opDesc.isEnabled();
  chk(temDesc, 'CAMP-078: admin acha "Descartar um lote repetido" em "Mais"', (await txt(ad, '#d-body')).slice(0, 400) || (await txt(ad, '.content.on .mais-lista')).slice(0, 400));
  if (temDesc) {
    await opDesc.click(); await ad.waitForSelector('#mx-go', { timeout: 8000 }).catch(() => {});
    await print(ad, '078_form');
    if (await ad.$('#mx-lote')) { const v = await ad.$eval('#mx-lote', s => (s.options[1] || s.options[0] || {}).value); if (v) await ad.selectOption('#mx-lote', String(L78)).catch(() => ad.selectOption('#mx-lote', v)) }
    if (await ad.$('#mx-motivo')) await ad.fill('#mx-motivo', 'pasta repetida pelo scanner (teste)');
    for (const cb of await ad.$$('#d-body input[type="checkbox"]')) await cb.check();
    await ad.click('#mx-go', { timeout: 8000 }); await confirmar(ad);
    chk(await espera(() => um("SELECT descartado_em IS NOT NULL FROM lista_processamento WHERE id=?", L78) === 1), 'CAMP-078: o lote foi descartado');
  }
  await abrirProjeto(op, P78);
  const c78 = await cartao(op, 'folhas'), b78 = await botoesVisiveis(op);
  chk(!b78.some(t => /^Importar|^Conferir$/.test(t)), 'CAMP-078: sem Importar nem Conferir para o lote descartado', b78.join(' | '));
  chk(!/est[aá] lendo/.test(c78), 'CAMP-078: o cartão não diz mais que o CAMP Vision está lendo', c78);
  await print(op, '078_descartado');
  await op.evaluate(() => nav('filas')); await op.waitForTimeout(1500);
  const mn78 = await op.evaluate(c => { const v = document.querySelector('.content.on'); const t = v ? v.innerText : ''; const i = t.indexOf(c); return i < 0 ? '' : t.slice(Math.max(0, i - 300), i + 200) }, P78);
  chk(!mn78, 'CAMP-078: o lote descartado sai de Material novo', mn78);
  await abrirProjeto(op, P78);
  await op.evaluate(c => showProjeto(c, 'historico'), P78).catch(() => {}); await op.waitForTimeout(1500);
  chk(/descartou/i.test(await txt(op, '#pd')), 'CAMP-078: o histórico do projeto mostra o descarte', (await txt(op, '#pd')).slice(0, 400));
  await print(op, '078_historico');

  // ------------------------------------------------------------------------------------------------
  passo('CAMP-079: releitura depois da conferência não apaga o que a pessoa fez');
  const NOME79 = 'CASA RELEITURA';
  const P79 = reservar(NOME79); cv2('processando', BASE, RAIZ, P79, NOME79); cv2('pronto', BASE, RAIZ, P79);
  const D79 = n => `${P79}-1972-S01-D${String(n).padStart(5, '0')}`;
  await abrirConferir(op, P79, D79(1)); await op.waitForSelector('#rv-titulo', { timeout: 15000 });
  await op.fill('#rv-titulo', 'Planta térreo (corrigida)'); await op.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(op);
  chk(await espera(() => um('SELECT titulo FROM item WHERE codigo=?', D79(1)) === 'Planta térreo (corrigida)'), 'CAMP-079: D00001 corrigida pela pessoa');
  await abrirConferir(op, P79, D79(2)); await op.waitForSelector('#cf-pane [data-rev-girar="90"]', { timeout: 15000 });
  await op.click('#cf-pane [data-rev-girar="90"]'); await op.waitForTimeout(900); await op.click('#cf-pane [data-rev-girar="90"]');
  chk(await espera(() => um('SELECT giro_manual FROM item WHERE codigo=?', D79(2)) === 180), 'CAMP-079: D00002 girada 180°');
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op);
  chk(await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D79(2)) === 'conferida'), 'CAMP-079: D00002 conferida');
  const r79 = JSON.parse(montar('releitura', BASE, RAIZ, P79));
  const imp79 = r79.importacao || {};
  chk((imp79.ignoradas_ja_revisadas || 0) >= 2, 'CAMP-079: a reimportação diz quantas folhas revisadas foram mantidas', JSON.stringify(imp79).slice(0, 300));
  chk(um('SELECT titulo FROM item WHERE codigo=?', D79(1)) === 'Planta térreo (corrigida)', 'CAMP-079: o título corrigido não foi sobrescrito', um('SELECT titulo FROM item WHERE codigo=?', D79(1)));
  chk(um('SELECT giro_manual FROM item WHERE codigo=?', D79(2)) === 180 && um('SELECT revisao FROM item WHERE codigo=?', D79(2)) === 'conferida', 'CAMP-079: o giro e a conferência ficaram');
  chk(um('SELECT ano_folha FROM item WHERE codigo=?', D79(1)) != 1999, 'CAMP-079: o ano relido não sobrescreveu a folha corrigida', um('SELECT ano_folha FROM item WHERE codigo=?', D79(1)));
  chk(/RELIDA/.test(um('SELECT titulo FROM item WHERE codigo=?', D79(3)) || ''), 'CAMP-079: folha ainda não revisada recebe a leitura nova', um('SELECT titulo FROM item WHERE codigo=?', D79(3)));
  await abrirProjeto(op, P79);
  const c79 = await cartao(op, 'folhas');
  chk(/2 \/ 6|1 \/ 6/.test(c79) || /conferidas/.test(c79), 'CAMP-079: o cartão Folhas continua contando as já conferidas', c79);
  await abrirConferir(op, P79, D79(1)); await op.waitForSelector('#rv-titulo', { timeout: 15000 });
  chk((await op.inputValue('#rv-titulo')) === 'Planta térreo (corrigida)', 'CAMP-079: a tela mostra o título que a pessoa corrigiu', await op.inputValue('#rv-titulo'));
  await print(op, '079_releitura');
  chk(!pilhas.length, 'CAMP-072..079: nenhum erro de JavaScript (com o rastro)', pilhas.join(' || '));
});
