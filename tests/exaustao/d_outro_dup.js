// Exaustão da página do projeto, grupo D (CAMP-096 a CAMP-101): folhas "de outro projeto" e duplicatas.
// Os lotes nascem pelo caminho real (estação reserva, CAMP Vision grava a pasta e avisa: tests/fluxo_real_cv2.py + d_montar.py);
// daí em diante é tudo clique no navegador. Rodar: bash tests/rodar_exaustao.sh tests/exaustao/d_outro_dup.js
const T = require('./_comum'); const { execFileSync } = require('child_process'); const path = require('path');
const montar = (...a) => JSON.parse(execFileSync('python3', [path.join(__dirname, 'd_montar.py'), ...a], { encoding: 'utf-8' }).trim());
const abertos = c => T.um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')", c);
const irErros = async (pg, P, aba) => { await pg.evaluate(c => nav('erros/' + c), P); await pg.waitForSelector('#err-body', { timeout: 15000 }); await pg.waitForTimeout(1500);
  await pg.click(`#err-abas [data-err-sit="${aba || 'abertos'}"]`); await pg.waitForTimeout(1200) };   // a tela lembra a última aba

T.rodar(async () => {
  // ---------------- lote com retiradas ----------------
  const NOME = 'CASA RETIRADAS';
  const OUTRA = T.cv2('reservar', T.BASE, 'F026', 'CASA OUTRA OBRA', '1972');              // o projeto certo da D3 já existe no fundo
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
  const av = montar('retirados', T.BASE, T.RAIZ, P);
  T.chk(av.ok && (av.importacao || {}).criadas === 3 && (av.importacao.retirados || []).length === 4, 'preparação: o aviso importa D1–D3 e registra 4 retiradas (D4–D7)', JSON.stringify(av.importacao || av).slice(0, 300));
  const op = await T.entrar('operador'), ad = await T.entrar('admin');

  // ---------------- CAMP-096 ----------------
  T.passo('CAMP-096: folha retirada sem imagem nenhuma');
  await T.abrirProjeto(op, P);
  const b4 = `#pj-probs [data-fp-box="${D(4)}"]`;
  T.chk(await op.waitForSelector(b4, { timeout: 10000 }).then(() => true, () => false), 'CAMP-096: a D00004 (sem imagem) aparece em "Problemas que impedem publicar"');
  T.chk(await T.espera(async () => /Não há imagem desta folha/.test(await T.txt(op, b4))), 'CAMP-096: no lugar da miniatura diz "Não há imagem desta folha"', await T.txt(op, b4));
  const rl = await op.$(`${b4} [data-releitura-projeto="${P}"]`);
  T.chk(!!rl, 'CAMP-096: oferece "Pedir releitura do lote" (a folha não está no painel para pedir só ela)', await T.txt(op, b4));
  if (rl) { await rl.click(); await T.confirmar(op); T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM pedido_releitura WHERE projeto_codigo=? AND estado='pedido'", P) === 1), 'CAMP-096: o pedido de releitura do lote fica registrado') }
  T.chk(!!(await op.$(`${b4} [data-deste-projeto="${D(4)}"]`)), 'CAMP-096: "É deste projeto" continua possível mesmo sem imagem');
  await T.print(op, '096_sem_imagem');
  await irErros(op, P);
  const linha4 = await T.txt(op, '#err-body');
  T.chk(!/não existe mais no painel/.test(linha4), 'CAMP-096: a tela Problemas não chama a folha retirada de "folha que sumiu… confira e feche"', linha4.slice(0, 600));
  await op.locator('#err-body tr[data-err-linha]').filter({ hasText: 'RESIDÊNCIA SEM IMAGEM' }).filter({ hasText: 'outra pasta' }).first().locator('.err-oque').click().catch(() => {});
  await op.waitForSelector('#d-body', { timeout: 8000 }).catch(() => {}); await op.waitForTimeout(600);
  const gav4 = await T.txt(op, '#d-body');
  T.chk(/tirou esta folha do lote por achar que é de outro projeto/.test(gav4) && !/não existe mais/.test(gav4), 'CAMP-096: a gaveta do problema explica que o CAMP Vision a tirou do lote por achar que é de outro projeto', gav4.slice(0, 400));
  await op.evaluate(() => closeDrawer(true));
  await T.print(op, '096_problemas');
  // D4 é mesmo de outra obra: fica fora
  await op.click(`#err-body [data-fp-outro="${D(4)}"]`); await T.confirmar(op);
  T.chk(await T.espera(() => abertos(D(4)) === 0), 'CAMP-096: "É de outro projeto…" fecha os 2 problemas da D00004 e ela fica fora');

  // ---------------- CAMP-097 ----------------
  T.passo('CAMP-097: "sem identificação" e capa');
  await irErros(op, P);
  const b5 = `#err-body [data-fp-box="${D(5)}"]`;
  T.chk(!!(await op.$(`${b5} [data-fp-folha="${D(5)}"]`)) && !!(await op.$(`${b5} [data-deste-projeto="${D(5)}"]`)), 'CAMP-097: "sem identificação" tem "Ver a folha" e "É deste projeto" (o mesmo caso de outro projeto)', await T.txt(op, '#err-body'));
  const [aba5] = await Promise.all([op.context().waitForEvent('page', { timeout: 8000 }).catch(() => null), op.click(`${b5} [data-fp-folha="${D(5)}"]`).catch(() => {})]);
  if (aba5) { const r = await aba5.waitForLoadState().then(() => aba5.evaluate(() => ({ t: document.contentType, w: (document.images[0] || {}).naturalWidth || 0 }))).catch(() => ({}));
    T.chk(/image/.test(r.t || '') && r.w > 100, 'CAMP-097: a imagem da folha "sem identificação" abre em outra aba', JSON.stringify(r)); await aba5.close() } else T.chk(false, 'CAMP-097: a imagem da folha "sem identificação" abre em outra aba');
  await op.click(`${b5} [data-deste-projeto="${D(5)}"]`); await T.confirmar(op);
  T.chk(await T.espera(() => T.um('SELECT status_site FROM item WHERE codigo=?', D(5)) === 'nao_publicado', 15000), 'CAMP-097: "É deste projeto" na "sem identificação" (operadora) a traz para o projeto, liberada');
  await irErros(op, P, 'ignorado');
  const d5 = await op.$(`#err-body [data-deste-desfazer="${D(5)}"]`);
  T.chk(!!d5, 'CAMP-097: "Desfazer" aparece em "Não era problema"');
  if (d5) { await d5.click(); await T.confirmar(op) }
  T.chk(await T.espera(() => T.um('SELECT status_site FROM item WHERE codigo=?', D(5)) === 'bloqueado'), 'CAMP-097: desfeito, a D00005 volta a ficar fora da publicação');
  // desfeito, a folha já está no painel com o aviso: refazer é na conferência dela ("É deste projeto (o CAMP Vision errou)")
  await T.abrirConferir(op, P, D(5));
  const redo = await op.waitForSelector(`#cf-pane [data-deste-projeto="${D(5)}"]`, { timeout: 10000 }).then(() => true, () => false);
  T.chk(redo, 'CAMP-097: desfeito, a conferência da D00005 oferece "É deste projeto" de novo', await T.txt(op, '#cf-pane'));
  if (redo) { await op.click(`#cf-pane [data-deste-projeto="${D(5)}"]`); await T.confirmar(op) }
  T.chk(await T.espera(() => T.um('SELECT status_site FROM item WHERE codigo=?', D(5)) === 'nao_publicado'), 'CAMP-097: refeito, a D00005 é deste projeto de novo');
  // capa: outro motivo de retirada → só admin devolve; mas a imagem tem de dar para ver
  await irErros(op, P);
  const linhaCapa = op.locator('#err-body tr[data-err-linha]').filter({ hasText: 'capa' }).first();
  T.chk(await linhaCapa.count() > 0, 'CAMP-097: a capa retirada aparece em Problemas');
  T.chk(await linhaCapa.locator(`[data-fp-folha="${D(6)}"]`).count() > 0, 'CAMP-097: a capa retirada tem "Ver a folha" (dá para conferir antes de decidir)', await linhaCapa.innerText().catch(() => ''));
  T.chk(await linhaCapa.locator(`[data-deste-projeto="${D(6)}"]`).count() === 0, 'CAMP-097: a capa não tem "É deste projeto" (outro motivo: decisão de admin)');
  const r403 = await op.evaluate(c => fetch('/api/itens/' + c + '/deste-projeto', { method: 'POST' }).then(r => r.status), D(6));
  T.chk(r403 === 409, 'CAMP-097: pela API, "É deste projeto" na capa é recusado com explicação (409)', r403);
  await T.print(op, '097_capa');
  // admin devolve a capa à revisão; ela tem de entrar no painel sem ninguém procurar outro botão
  await irErros(ad, P);
  const capaAd = ad.locator('#err-body tr[data-err-linha]').filter({ hasText: 'capa' }).first();
  await capaAd.locator('.err-oque').click().catch(() => capaAd.click());
  const temDev = await ad.waitForSelector('#err-dev-mot', { timeout: 8000 }).then(() => true, () => false);
  T.chk(temDev, 'CAMP-097: admin: a capa tem "Devolver à revisão"', await T.txt(ad, '#d-body'));
  if (temDev) { await ad.fill('#err-dev-mot', 'é a capa do projeto, vai como folha de rosto'); await ad.click('[data-err-devolver]') }
  T.chk(await T.espera(() => T.um('SELECT COUNT(*) FROM item WHERE codigo=?', D(6)) === 1, 15000), 'CAMP-097: devolvida, a capa entra no painel (sem precisar importar de novo à mão)', T.um('SELECT COUNT(*) FROM item WHERE codigo=?', D(6)));

  // ---------------- CAMP-098 ----------------
  T.passo('CAMP-098: "É de outro projeto" com a folha já no painel');
  await T.abrirConferir(op, P, D(3));
  await op.waitForSelector('#cf-pane [data-rev-item="conferida"]', { timeout: 10000 });
  T.chk(/outro projeto\?/.test(await T.txt(op, `#cf-linhas [data-cf-folha="${D(3)}"]`)), 'CAMP-098: a D00003 (no painel, carimbo de outra obra) aparece com "outro projeto?"', await T.txt(op, `#cf-linhas [data-cf-folha="${D(3)}"]`));
  const btOutroOp = await op.$('#cf-pane button:text("É de outro projeto…")');
  T.chk(!!btOutroOp && await btOutroOp.isDisabled() && /peça a um admin/.test(await T.txt(op, '#cf-pane')), 'CAMP-098: operadora vê "É de outro projeto…" desligado com "peça a um admin"');
  await T.print(op, '098_operadora');
  await T.abrirConferir(ad, P, D(3)); await ad.waitForSelector('#cf-pane details.op-det > summary', { timeout: 10000 });
  await ad.click('#cf-pane details.op-det > summary'); await ad.fill('#cf-pane .op-outro .op-busca', OUTRA);
  const go = await ad.waitForSelector('#cf-pane .op-outro .op-go:not([disabled])', { timeout: 8000 }).then(() => true, () => false);
  T.chk(go, 'CAMP-098: admin acha o projeto certo (mesmo fundo) e pode mover');
  if (go) { const novo = (await T.txt(ad, '#cf-pane .op-novo')).trim(); await ad.click('#cf-pane .op-outro .op-go'); await T.confirmar(ad);
    T.chk(await T.espera(() => T.um('SELECT projeto_codigo FROM item WHERE codigo=?', novo) === OUTRA, 15000), `CAMP-098: a folha foi para ${OUTRA} com código novo (${novo})`);
    T.chk(!T.um('SELECT COUNT(*) FROM item WHERE codigo=?', D(3)), 'CAMP-098: o código antigo não existe mais no projeto de origem');
    T.chk(T.um("SELECT COUNT(*) FROM evento WHERE codigo IN (?,?) AND tipo='folha_movida'", D(3), novo) >= 1, 'CAMP-098: o histórico registra a mudança');
    T.chk(!T.um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao') AND (categoria='projeto_errado' OR descricao LIKE '%outra%')", D(3)), 'CAMP-098: nenhum problema de "outro projeto" fica aberto na folha que saiu') }
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE lote_id=(SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1) AND projeto_codigo<>?", P, P) === 0,
        'CAMP-098: a folha movida sai do lote de origem (não fica "faltando conferir" lá)');
  // releitura do CAMP Vision (o pacote ainda lista a D3 neste projeto): a folha movida NÃO volta para cá
  const re = montar('retirados', T.BASE, T.RAIZ, P);
  T.chk(re.ok && !T.um('SELECT COUNT(*) FROM item WHERE codigo=?', D(3)), 'CAMP-098: depois da releitura, a D00003 movida não é recriada no projeto de origem', JSON.stringify((re.importacao || {})).slice(0, 300));
  // fundo nunca mistura: buscar projeto de outro fundo não deixa mover
  await T.abrirConferir(ad, P, D(1)); await ad.waitForSelector('#cf-pane details.op-det > summary', { timeout: 10000 });
  await ad.click('#cf-pane details.op-det > summary'); await ad.fill('#cf-pane .op-outro .op-busca', 'F023-P0011'); await ad.waitForTimeout(1500);
  T.chk(!(await ad.$('#cf-pane .op-outro .op-go:not([disabled])')), 'CAMP-098: projeto de OUTRO fundo não pode ser destino (fundos nunca se misturam)', await T.txt(ad, '#cf-pane .op-outro'));
  await T.print(ad, '098_admin');

  // ---------------- CAMP-099 ----------------
  T.passo('CAMP-099: desfazer "É deste projeto" depois de publicada');
  await T.abrirProjeto(op, P);
  await op.click(`#pj-probs [data-fp-box="${D(7)}"] [data-deste-projeto="${D(7)}"]`).catch(() => {}); await T.confirmar(op);
  T.chk(await T.espera(() => T.um('SELECT status_site FROM item WHERE codigo=?', D(7)) === 'nao_publicado', 15000), 'CAMP-099: D00007 devolvida ("É deste projeto")');
  // confere tudo e publica (admin)
  await T.abrirConferir(ad, P);
  for (let i = 0; i < 10 && !(await ad.$('#cf-pane [data-fim-passo]')); i++) {
    if (!(await ad.$('#cf-pane [data-rev-item="conferida"]'))) break;
    await ad.click('#cf-pane [data-rev-item="conferida"]'); await T.confirmar(ad); await ad.waitForTimeout(900) }
  const aprovar = await ad.waitForSelector('#cf-pane [data-fim-passo] [data-pp="aprovar"]', { timeout: 10000 }).then(() => true, () => false);
  T.chk(aprovar, 'CAMP-099: conferência concluída, "Aprovar o lote" ali mesmo', await T.txt(ad, '#cf-pane'));
  if (aprovar) { await ad.click('#cf-pane [data-fim-passo] [data-pp="aprovar"]'); await T.confirmar(ad) }
  const pub = await ad.waitForSelector('#cf-pane [data-fim-passo] [data-pp="publicar"]', { timeout: 10000 }).then(() => true, () => false);
  T.chk(pub, 'CAMP-099: nada impede publicar (os problemas de outro projeto foram decididos)', await T.txt(ad, '#cf-pane [data-fim-passo]'));
  if (pub) { await ad.click('#cf-pane [data-fim-passo] [data-pp="publicar"]'); await ad.waitForSelector('#pub-go:not([disabled])', { timeout: 15000 }).catch(() => {});
    await ad.click('#pub-go').catch(() => {}); await ad.waitForSelector('#d-body .pub-resultado', { timeout: 60000 }).catch(() => {}); await ad.keyboard.press('Escape') }
  T.chk(await T.espera(() => T.um('SELECT status_site FROM item WHERE codigo=?', D(7)) === 'no_ar', 20000), 'CAMP-099: a D00007 está no site', T.um('SELECT status_site FROM item WHERE codigo=?', D(7)));
  const antes = JSON.stringify(T.sql("SELECT status_site, pendencias FROM item WHERE codigo=?", D(7))) + JSON.stringify(T.sql("SELECT id, situacao FROM erro WHERE codigo=? ORDER BY id", D(7)));
  await irErros(op, P, 'ignorado');
  const d7 = await op.$(`#err-body [data-deste-desfazer="${D(7)}"]`);
  T.chk(!!d7, 'CAMP-099: o "Desfazer" aparece (a decisão está registrada)');
  if (d7) { await d7.click(); await T.confirmar(op); await op.waitForTimeout(1200) }
  const t7 = await T.txt(op, '#toast');
  T.chk(/Despublique/i.test(t7), 'CAMP-099: desfazer é recusado com "despublique antes", em português', t7);
  const depois = JSON.stringify(T.sql("SELECT status_site, pendencias FROM item WHERE codigo=?", D(7))) + JSON.stringify(T.sql("SELECT id, situacao FROM erro WHERE codigo=? ORDER BY id", D(7)));
  T.chk(antes === depois, 'CAMP-099: nada muda no banco (folha e problemas iguais)', antes + ' ≠ ' + depois);
  await T.print(op, '099_recusa');

  // ---------------- duplicatas ----------------
  const NOME2 = 'CASA DUPLICATAS';
  const P2 = T.cv2('reservar', T.BASE, 'F026', NOME2, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P2, NOME2);
  const E = n => `${P2}-1972-S01-D${String(n).padStart(5, '0')}`;
  montar('dup50', T.BASE, T.RAIZ, P2);
  T.passo('CAMP-100: 50 folhas, 25 duplicatas');
  T.chk(T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND duplicata_de IS NOT NULL', P2) === 25, 'CAMP-100: o painel marcou as 25 cópias');
  await T.abrirProjeto(op, P2);
  const cartaoP = await T.txt(op, '#pj-cards .pjc[data-pjc="problemas"]');
  T.chk(/PROBLEMAS 25 avisos/i.test(cartaoP), 'CAMP-100: cartão Problemas conta 25 (não 50: cópia + problema da mesma folha)', cartaoP);
  await op.click('#pd .pj-mais-menu > summary').catch(() => {});
  const bDup = op.locator('#pd .pj-mais-menu [data-nav^="duplicatas/"], #pd .pj-mais-menu button:has-text("Duplicatas"), #pd .pj-mais-menu a:has-text("Duplicatas")').first();
  if (await bDup.count()) await bDup.click(); else await op.evaluate(c => nav('duplicatas/' + c), P2);
  await op.waitForSelector('#dupv-cont', { timeout: 15000 }); await op.waitForTimeout(800);
  T.chk(/0 de 25 conferidas/.test(await T.txt(op, '#dupv-cont')) && (await op.locator('#dupv-grupos .dupv-grupo').count()) === 25, 'CAMP-100: a tela Duplicatas abre com "0 de 25 conferidas" e 25 grupos', await T.txt(op, '#dupv-cont'));
  T.chk(await T.imgOk(op, `#dupv-grupos .dupv-grupo[data-dupv-grupo="${E(1)}"] img`), 'CAMP-100: as imagens dos grupos carregam (lado a lado)');
  await T.print(op, '100_duplicatas');
  const grupo = n => `#dupv-grupos .dupv-grupo[data-dupv-grupo="${E(n)}"]`;
  const cont = async t => op.waitForFunction(x => ((document.getElementById('dupv-cont') || {}).textContent || '').includes(x), t, { timeout: 10000 }).then(() => true, () => false);
  await op.locator(grupo(1) + ' [data-dupv-confirmar]').click();
  T.chk(await cont('1 de 25 conferidas'), 'CAMP-100: "Confirmar" anda o progresso (1 de 25)');
  await op.locator(grupo(2) + ' [data-dupv-confirmar]').click(); T.chk(await cont('2 de 25'), 'CAMP-100: segundo grupo (2 de 25)');

  T.passo('CAMP-101: trocar a que publica e "Não é duplicata"');
  await op.click(`${grupo(3)} [data-dupv-nao="${E(28)}"]`).catch(() => op.locator(grupo(3) + ' [data-dupv-nao]').first().click()); await T.confirmar(op);
  T.chk(await T.espera(() => T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(28)) === null), 'CAMP-101: "Não é duplicata": a D00028 volta a poder ir ao site');
  T.chk(await T.espera(() => abertos(E(28)) === 0), 'CAMP-101: "Não é duplicata" fecha o problema de duplicata da D00028', JSON.stringify(T.sql("SELECT categoria, situacao FROM erro WHERE codigo=?", E(28))));
  await op.click(`${grupo(4)} [data-dupv-trocar="${E(29)}"]`); await T.confirmar(op);
  T.chk(await T.espera(() => T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(4)) === E(29) && T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(29)) === null), 'CAMP-101: "Publicar esta em vez da outra": a D00029 vai ao site e a D00004 vira a cópia');
  T.chk(T.um("SELECT COUNT(*) FROM erro WHERE codigo=? AND categoria='duplicata' AND situacao IN ('aberto','em_correcao')", E(29)) === 0, 'CAMP-101: a que passou a publicar não fica com problema de duplicata aberto');
  // confirmar todos os que eu não mexi
  const bt = op.locator('[data-dupv-todos]');
  const tTodos = await bt.textContent().catch(() => '');
  T.chk(/\(21\)/.test(tTodos), 'CAMP-100: "Confirmar todos os grupos que eu não mexi (21)" (25 − 2 confirmados − 1 trocado − 1 que não era)', tTodos);
  await bt.click().catch(() => {}); await T.confirmar(op);
  const fimTxt = await T.espera(async () => /24 de 24 conferidas/.test(await T.txt(op, '#dupv-cont')));
  T.chk(fimTxt, 'CAMP-100: fim: "24 de 24 conferidas" (a que não era duplicata saiu da conta)', await T.txt(op, '#dupv-cont'));
  T.chk(T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(4)) === E(29), 'CAMP-100: "Confirmar todos" não desfez a troca feita à mão');
  await T.print(op, '100_fim');
  await T.abrirProjeto(op, P2);
  const nAb = T.um("SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND situacao IN ('aberto','em_correcao')", P2 + '%');
  const cP2 = await T.txt(op, '#pj-cards .pjc[data-pjc="problemas"]'), aba = await T.txt(op, '#pd [role="tab"]:has-text("Problemas")');
  const nCard = (cP2.match(/PROBLEMAS (\d+)/i) || [, '0'])[1], nAba = (aba.match(/\((\d+)\)/) || [, '0'])[1];
  T.chk(String(nAb) === nCard && nCard === nAba, `CAMP-100: cartão, aba e banco batem depois de conferir as duplicatas (${nAb} / ${nCard} / ${nAba})`, cP2 + ' | ' + aba);
  // releitura do CAMP Vision: nada volta
  montar('dup50', T.BASE, T.RAIZ, P2);
  T.chk(T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(28)) === null, 'CAMP-101: depois da releitura, a D00028 continua "não é duplicata"', T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(28)));
  T.chk(T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(29)) === null && T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(4)) === E(29), 'CAMP-101: depois da releitura, a troca (D29 publica, D4 cópia) continua',
        JSON.stringify([T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(29)), T.um('SELECT duplicata_de FROM item WHERE codigo=?', E(4))]));
  T.chk(abertos(E(28)) === 0 && abertos(E(29)) === 0, 'CAMP-101: depois da releitura, os problemas resolvidos não reabrem', JSON.stringify(T.sql("SELECT codigo, categoria, situacao FROM erro WHERE codigo IN (?,?)", E(28), E(29))));
  T.chk(/24 de 24/.test(await (async () => { await op.evaluate(c => nav('duplicatas/' + c), P2); await op.waitForSelector('#dupv-cont', { timeout: 15000 }); await op.waitForTimeout(800); return T.txt(op, '#dupv-cont') })()), 'CAMP-101: depois da releitura, a tela Duplicatas continua "24 de 24 conferidas"', await T.txt(op, '#dupv-cont'));
});
