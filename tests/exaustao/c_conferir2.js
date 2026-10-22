// Exaustão da página do projeto, grupo C (conferir, parte 2): CAMP-089 reter e devolver · 090 tirar folha (mover / criar projeto)
// · 091 desfazer a conferência reabre o que ela fechou · 092 autoria divergente · 093 bloqueio comum ("Já resolvi") · 094 "Aprovar todas"
// não fecha aviso que ninguém viu · 095 duas pessoas no mesmo lote. O lote nasce pelo caminho real (estação + CAMP Vision, tests/exaustao/c_montar.py);
// tudo o mais é clique no navegador. Rodar: bash tests/rodar_exaustao.sh tests/exaustao/c_conferir2.js
const { execFileSync } = require('child_process');
const path = require('path');
const T = require('./_comum');
const { chk, passo, sql, um, espera, print, txt, confirmar } = T;
const montar = (P, cenario) => execFileSync('python3', [path.join(__dirname, 'c_montar.py'), 'pronto', T.BASE, T.RAIZ, P, cenario], { encoding: 'utf-8' }).trim();
const novoLote = (nome, cenario) => {
  const P = T.cv2('reservar', T.BASE, 'F026', nome, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, nome);
  const r = JSON.parse(montar(P, cenario)); return { P, D: n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`, r };
};
const atual = pg => pg.evaluate(() => (typeof CONF !== 'undefined' && CONF.atual) || null);
const abrirFolha = async (pg, P, cod) => { await T.abrirConferir(pg, P, cod); await espera(async () => (await atual(pg)) === cod); await pg.waitForSelector('#cf-pane [data-rev-item]', { timeout: 10000 }).catch(() => {}); await pg.waitForTimeout(400) };
const COLS = ['revisao', 'retida', 'retida_motivo', 'status_site', 'autoria_divergente', 'credito', 'titulo', 'escala', 'projeto_codigo', 'pendencias'];
const item = c => { const r = sql(`SELECT ${COLS.join(', ')} FROM item WHERE codigo=?`, c)[0]; return r ? Object.fromEntries(COLS.map((k, i) => [k, r[i]])) : null };
const abertos = (c, cat) => um(`SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')${cat ? ' AND categoria=?' : ''}`, c, ...(cat ? [cat] : []));
const linha = (pg, c) => txt(pg, `#cf-linhas [data-cf-folha="${c}"]`);
const toastAcao = async pg => { const b = await pg.waitForSelector('#toast .toast-acao', { timeout: 5000 }).catch(() => null); if (b) await b.evaluate(x => x.click()); return !!b };

T.rodar(async () => {
  const { P, D, r } = novoLote('RESIDENCIA CONFERIR', 'conferir2');
  chk(r.ok && (r.importacao || {}).criadas === 10, 'montagem: o aviso do CAMP Vision importa as 10 folhas do grupo C', JSON.stringify(r).slice(0, 300));
  const op = await T.entrar('operador'), ad = await T.entrar('admin');

  // ---------------- CAMP-089 ----------------
  passo('CAMP-089: reter folha (com motivo) e devolver');
  await abrirFolha(op, P, D(1));
  await op.click('#cf-pane details.rev-reter:not(.op-det) > summary');
  await op.click(`#cf-pane [data-rev-item="reter"][data-codigo="${D(1)}"]`); await op.waitForTimeout(1200);
  chk(item(D(1)).retida === 0 && (await atual(op)) === D(1), 'CAMP-089: "Reter" sem motivo não grava e a folha continua aberta', JSON.stringify(item(D(1))));
  chk(/motivo/i.test(await txt(op, '#cf-pane')), 'CAMP-089: a tela pede o motivo', (await txt(op, '#cf-pane')).slice(0, 300));
  await op.fill('#rv-motivo', 'foto de pessoa sem autorização de imagem');
  await op.click(`#cf-pane [data-rev-item="reter"][data-codigo="${D(1)}"]`);
  chk(await espera(() => item(D(1)).retida === 1), 'CAMP-089: com o motivo, a folha fica retida', JSON.stringify(item(D(1))));
  chk(item(D(1)).retida_motivo === 'foto de pessoa sem autorização de imagem', 'CAMP-089: o motivo é gravado');
  chk(await espera(async () => (await atual(op)) === D(2)), 'CAMP-089: a próxima folha da fila abre sozinha (D00002)', await atual(op));
  chk(/retida/i.test(await linha(op, D(1))), 'CAMP-089: a linha da D00001 na lista do conferir mostra "retida"', await linha(op, D(1)));
  await print(op, '089_retida');
  chk(await toastAcao(op), 'CAMP-089: o aviso tem "Desfazer"');
  chk(await espera(() => item(D(1)).retida === 0), 'CAMP-089: "Desfazer" devolve a folha (volta a ir ao site)', JSON.stringify(item(D(1))));
  chk(item(D(1)).revisao === 'pendente' && (await atual(op)) === D(2), 'CAMP-089: devolvida, volta para conferir, e a pessoa continua na D00002', JSON.stringify([item(D(1)).revisao, await atual(op)]));
  // reter de novo e devolver pela própria folha ("Voltar a publicar")
  await abrirFolha(op, P, D(1)); await op.click('#cf-pane details.rev-reter:not(.op-det) > summary'); await op.fill('#rv-motivo', 'teste de devolução');
  await op.click(`#cf-pane [data-rev-item="reter"][data-codigo="${D(1)}"]`); await espera(() => item(D(1)).retida === 1);
  await abrirFolha(op, P, D(1));
  const pr = await txt(op, '#cf-pane'); chk(/Retida/.test(pr) && /teste de devolução/.test(pr), 'CAMP-089: a folha retida mostra "Retida" e o motivo', pr.slice(0, 300));
  await T.abrirProjeto(op, P);
  chk(/retida/i.test(await txt(op, `.thumb[data-rev-abrir="${D(1)}"]`)), 'CAMP-089: a miniatura na página do projeto mostra "retida"', await txt(op, `.thumb[data-rev-abrir="${D(1)}"]`));
  await abrirFolha(op, P, D(1)); await op.click(`#cf-pane [data-rev-item="liberar"][data-codigo="${D(1)}"]`);
  chk(await espera(() => item(D(1)).retida === 0), 'CAMP-089: "Voltar a publicar" devolve a folha');

  // ---------------- CAMP-090 ----------------
  passo('CAMP-090: tirar folha do projeto (mover para outro do mesmo fundo / criar projeto novo)');
  await abrirFolha(op, P, D(2));
  const opBt = await op.$('#cf-pane button:text("É de outro projeto…")');
  chk(!!opBt && await opBt.isDisabled() && /admin/i.test(await txt(op, '#cf-pane')), 'CAMP-090: para a operadora, "É de outro projeto…" fica desligado com "peça a um admin"');
  await abrirFolha(ad, P, D(2));
  await ad.click('#cf-pane details.op-det > summary');
  await ad.fill('#cf-pane .op-outro .op-busca', 'F023-P0011'); await ad.waitForTimeout(1500);
  chk(await ad.$eval('#cf-pane .op-outro .op-go', b => b.disabled).catch(() => true), 'CAMP-090: projeto de OUTRO fundo (F023) não pode ser destino', await txt(ad, '#cf-pane .op-outro'));
  await ad.fill('#cf-pane .op-outro .op-busca', 'F026-P0002');
  const goOk = await ad.waitForSelector('#cf-pane .op-outro .op-go:not([disabled])', { timeout: 8000 }).then(() => true, () => false);
  chk(goOk, 'CAMP-090: projeto do mesmo fundo (F026-P0002) é aceito como destino');
  const novoCod = goOk ? (await txt(ad, '#cf-pane .op-novo')).match(/F026-P0002-\S+/)?.[0] : null;
  if (goOk) { await ad.click('#cf-pane .op-outro .op-go'); await confirmar(ad) }
  chk(await espera(() => !item(D(2))), 'CAMP-090: a D00002 sai do projeto');
  chk(!!novoCod && !!item(novoCod) && item(novoCod).projeto_codigo === 'F026-P0002', `CAMP-090: ela ganha o código do projeto certo (${novoCod})`, novoCod);
  chk(um("SELECT COUNT(*) FROM redirecionamento WHERE codigo_antigo=? AND codigo_novo=?", D(2), novoCod || '') === 1 || um("SELECT COUNT(*) FROM item WHERE codigo_anterior=?", D(2)) === 1,
    'CAMP-090: o código antigo fica guardado (redirecionamento / código anterior)');
  chk(await espera(async () => (await atual(ad)) && (await atual(ad)) !== D(2)), 'CAMP-090: a fila segue para outra folha', await atual(ad));
  await print(ad, '090_movida');
  // criar projeto novo
  const nProj = um("SELECT COUNT(*) FROM projeto WHERE fundo_codigo='F026'");
  await abrirFolha(ad, P, D(3)); await ad.click('#cf-pane details.op-det > summary'); await ad.click('#cf-pane details.op-np > summary');
  await ad.fill('#cf-pane .op-np-titulo', 'Garagem Exaustao Nova 1972'); await ad.click('#cf-pane .op-np-go'); await confirmar(ad);
  chk(await espera(() => !item(D(3)), 15000), 'CAMP-090: "criar projeto novo" tira a D00003 do projeto');
  const pn = sql("SELECT codigo, fundo_codigo FROM projeto WHERE titulo LIKE 'Garagem Exaustao Nova%'")[0];
  chk(!!pn && pn[1] === 'F026' && um('SELECT COUNT(*) FROM projeto WHERE fundo_codigo=?', 'F026') === nProj + 1, 'CAMP-090: o projeto novo nasce no MESMO fundo (F026)', JSON.stringify(pn));
  chk(!!pn && um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', pn[0]) === 1, 'CAMP-090: a folha está no projeto novo', pn && pn[0]);

  // ---------------- CAMP-091 ----------------
  passo('CAMP-091: desfazer a conferência reabre o que ela fechou');
  chk(abertos(D(4), 'orientacao') === 1, 'CAMP-091: a D00004 começa com o problema de orientação aberto');
  await abrirFolha(op, P, D(4)); await op.click(`#cf-pane [data-rev-item="conferida"][data-codigo="${D(4)}"]`); await confirmar(op);
  chk(await espera(() => abertos(D(4), 'orientacao') === 0 && item(D(4)).revisao === 'conferida'), 'CAMP-091: "Está certo" fecha o problema de orientação');
  chk(await toastAcao(op), 'CAMP-091: o aviso "conferida" tem "Desfazer"');
  chk(await espera(() => item(D(4)).revisao === 'pendente'), 'CAMP-091: "Desfazer" volta a folha para conferir');
  chk(await espera(() => abertos(D(4), 'orientacao') === 1), 'CAMP-091: "Desfazer" reabre o problema que a conferência tinha fechado', JSON.stringify(sql("SELECT situacao, resolucao FROM erro WHERE codigo=?", D(4))));
  await espera(async () => /orienta|problema/i.test(await linha(op, D(4))));
  chk(/orienta|problema/i.test(await linha(op, D(4))), 'CAMP-091: a marca volta na lista do conferir', await linha(op, D(4)));
  await print(op, '091_desfeita');
  // "Voltar para a conferir" depois de "Salvar correção"
  await abrirFolha(op, P, D(5)); await op.fill('#rv-ano', '1972'); await op.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(5)}"]`); await confirmar(op);
  chk(await espera(() => abertos(D(5), 'metadado') === 0 && item(D(5)).revisao === 'corrigida'), 'CAMP-091: "Salvar correção" fecha o problema do ano lido');
  await abrirFolha(op, P, D(5)); await op.click(`#cf-pane [data-rev-item="pendente"][data-codigo="${D(5)}"]`);
  chk(await espera(() => item(D(5)).revisao === 'pendente'), 'CAMP-091: "Voltar para a conferir" volta a folha');
  chk(await espera(() => abertos(D(5), 'metadado') === 1), 'CAMP-091: "Voltar para a conferir" reabre o problema que a correção tinha fechado');
  chk(/problema|1927/i.test(await txt(op, '#cf-pane')), 'CAMP-091: o problema aparece de novo na folha', (await txt(op, '#cf-pane')).slice(0, 300));

  // ---------------- CAMP-092 ----------------
  passo('CAMP-092: autoria divergente');
  chk(item(D(6)).autoria_divergente === 1 && item(D(6)).credito === 'Autoria não confirmada', 'CAMP-092: sem decidir, a folha sobe com "Autoria não confirmada"', JSON.stringify(item(D(6))));
  await abrirFolha(op, P, D(6));
  chk(await op.$('#cf-pane [data-cf-aviso="autoria"]').then(Boolean), 'CAMP-092: aviso "Autoria" na folha');
  chk(!(await op.$('#cf-pane [data-cf-autoria-outro]')), 'CAMP-092: "É de outro arquiteto" não aparece para a operadora');
  await print(op, '092_autoria');
  await op.click(`#cf-pane [data-cf-autoria-ok="${D(6)}"]`); await confirmar(op);
  chk(await espera(() => item(D(6)).autoria_divergente === 0), 'CAMP-092: "É de <fundo>" tira a marca da folha');
  chk(abertos(D(6), 'autoria_divergente') === 0, 'CAMP-092: e fecha o problema de autoria');
  chk(item(D(6)).credito !== 'Autoria não confirmada', 'CAMP-092: o crédito deixa de ser "Autoria não confirmada"', item(D(6)).credito);
  chk(await espera(async () => !(await op.$('#cf-pane [data-cf-aviso="autoria"]'))), 'CAMP-092: o aviso some da tela na hora');
  await abrirFolha(ad, P, D(7));
  chk(await ad.$('#cf-pane [data-cf-autoria-outro]').then(Boolean), 'CAMP-092: o admin vê "É de outro arquiteto"');
  await ad.click('#cf-pane [data-cf-autoria-outro]');
  const temRa = await ad.waitForSelector('#conf-ov #ra-autoria', { timeout: 5000 }).then(() => true, () => false);
  chk(temRa, 'CAMP-092: "É de outro arquiteto" abre o registro da autoria do projeto');
  if (temRa) { await ad.fill('#ra-autoria', 'Fulano de Tal'); await ad.click('#conf-ov [data-conf="sim"]'); await ad.waitForTimeout(2000) }
  chk(await espera(() => item(D(7)).autoria_divergente === 0), 'CAMP-092: registrada a autoria, a D00007 deixa de ter o aviso', JSON.stringify(item(D(7))));
  chk(/^conferir\//.test(await ad.evaluate(() => rotaAtual())), 'CAMP-092: o admin continua na tela de conferir', await ad.evaluate(() => rotaAtual()));

  // ---------------- CAMP-093 ----------------
  passo('CAMP-093: bloqueio comum do CAMP Vision → "Já resolvi"');
  chk(item(D(8)).status_site === 'bloqueado', 'CAMP-093: a D00008 vem bloqueada pelo CAMP Vision', item(D(8)).status_site);
  await abrirFolha(op, P, D(8));
  chk(/carimbo ilegível/.test(await txt(op, '#cf-pane [data-cf-aviso="bloqueio"]')), 'CAMP-093: o aviso mostra o motivo do bloqueio', await txt(op, '#cf-pane [data-cf-aviso="bloqueio"]'));
  await op.click(`#cf-pane [data-cf-bloqueio-ok="${D(8)}"]`);
  await op.waitForSelector('#conf-ov #conf-motivo', { timeout: 5000 }).catch(() => {});
  await op.click('#conf-ov [data-conf="sim"]').catch(() => {}); await op.waitForTimeout(800);
  chk(item(D(8)).status_site === 'bloqueado' && !!(await op.$('#conf-ov')), 'CAMP-093: sem dizer o que foi feito, não libera (a janela continua aberta)');
  await op.fill('#conf-ov #conf-motivo', 'conferi o título à mão: COBERTURA'); await op.click('#conf-ov [data-conf="sim"]');
  chk(await espera(() => item(D(8)).status_site === 'nao_publicado'), 'CAMP-093: "Já resolvi" com o motivo tira a folha de "bloqueado"', JSON.stringify(item(D(8))));
  chk(await espera(async () => !(await op.$('#cf-pane [data-cf-aviso="bloqueio"]'))), 'CAMP-093: o aviso de bloqueio some da tela');
  chk(um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='bloqueio_resolvido'", D(8)) === 1, 'CAMP-093: fica no histórico com o motivo');
  await print(op, '093_bloqueio');

  // ---------------- CAMP-094 ----------------
  passo('CAMP-094: "Aprovar todas" não fecha aviso que ninguém viu');
  const V = novoLote('CASA VINTE FOLHAS', 'vinte');
  chk(V.r.ok && (V.r.importacao || {}).criadas === 20, 'CAMP-094: 20 folhas importadas', JSON.stringify(V.r).slice(0, 200));
  const avisos = [3, 7, 11, 15].map(V.D);
  await T.abrirProjeto(op, V.P);
  // o caminho na tela: cartão Folhas → "Detalhes dos lotes" → "Mais ações do lote" → "Aprovar todas (20)"
  if (!(await op.isVisible('.pj-gav[data-gav="folhas"]'))) { await op.click(`#pj-cards [data-pjc-gav="folhas"]`); await op.waitForTimeout(1000) }
  await op.click('.pj-gav[data-gav="folhas"] details.rev-mais > summary').catch(() => {});
  const bt = await op.waitForSelector('[data-rev-lote="todas"]:visible', { timeout: 8000 }).catch(() => null);
  chk(!!bt && /Aprovar todas \(20\)/.test(await bt.textContent()), 'CAMP-094: "Detalhes dos lotes" → "Mais ações do lote" tem "Aprovar todas (20)"', await txt(op, '#pj-gaveta'));
  if (bt) {
    await bt.click(); await op.waitForSelector('#conf-ov', { timeout: 5000 }).catch(() => {});
    const conf = await txt(op, '#conf-ov');
    chk(/4/.test(conf) && avisos.every(c => conf.includes(c.slice(-6))), 'CAMP-094: a confirmação diz quantas e quais (D00003, D00007, D00011, D00015) ficam para conferir uma a uma', conf);
    await print(op, '094_confirmacao');
    await confirmar(op);
  }
  chk(await espera(() => um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='conferida'", V.P) === 16), 'CAMP-094: as 16 sem aviso ficam conferidas',
    um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='conferida'", V.P));
  chk(avisos.every(c => item(c).revisao === 'pendente'), 'CAMP-094: as 4 com aviso continuam "a conferir"', JSON.stringify(avisos.map(c => item(c).revisao)));
  chk(abertos(V.D(3), 'orientacao') === 1 && abertos(V.D(7), 'metadado') === 1, 'CAMP-094: nenhum problema é fechado sem a pessoa ver');
  await espera(async () => /4/.test(await txt(op, '#pj-cards .pjc[data-pjc="folhas"]')));
  chk(/16 \/ 20/.test(await txt(op, '#pj-cards .pjc[data-pjc="folhas"]')), 'CAMP-094: o cartão Folhas diz 16 / 20 sem recarregar', await txt(op, '#pj-cards .pjc[data-pjc="folhas"]'));

  // ---------------- CAMP-095 ----------------
  passo('CAMP-095: duas pessoas no mesmo lote');
  const op2 = await T.entrar('operador');
  await abrirFolha(op, P, D(9)); await abrirFolha(op2, P, D(9));
  await op.fill('#rv-titulo', 'Implantação (corrigida pela pessoa A)'); await op.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(9)}"]`); await confirmar(op);
  chk(await espera(() => item(D(9)).titulo === 'Implantação (corrigida pela pessoa A)'), 'CAMP-095: a pessoa A salva o título');
  await op2.fill('#rv-escala', '1:200'); await op2.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(9)}"]`); await confirmar(op2);
  chk(await espera(() => item(D(9)).escala === '1:200'), 'CAMP-095: a pessoa B, com a folha aberta antes, salva só a escala');
  chk(item(D(9)).titulo === 'Implantação (corrigida pela pessoa A)', 'CAMP-095: a correção da pessoa A não é desfeita pela B', item(D(9)).titulo);
  // as duas mudam o MESMO campo: a segunda é avisada, nada some em silêncio
  await abrirFolha(op, P, D(10)); await abrirFolha(op2, P, D(10));
  await op.fill('#rv-titulo', 'Situação (A)'); await op.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(10)}"]`); await confirmar(op);
  await espera(() => item(D(10)).titulo === 'Situação (A)');
  await op2.fill('#rv-titulo', 'Situação (B)'); await op2.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(10)}"]`); await confirmar(op2); await op2.waitForTimeout(1500);
  const avisoB = await txt(op2, '#cf-pane');
  chk(item(D(10)).titulo === 'Situação (A)' && /outra pessoa|mudou/i.test(avisoB), 'CAMP-095: a segunda pessoa a mudar o MESMO campo é avisada e não apaga a correção da primeira',
    JSON.stringify([item(D(10)).titulo, avisoB.slice(0, 300)]));
  await print(op2, '095_conflito');
  const atu = await op2.$(`#cf-pane [data-rev-atualizar="${D(10)}"]`);
  chk(!!atu, 'CAMP-095: o aviso de conflito oferece "Atualizar a folha"');
  if (atu) { await atu.click(); await op2.waitForTimeout(2000) }
  chk(await espera(async () => (await op2.inputValue('#rv-titulo').catch(() => '')) === 'Situação (A)'), 'CAMP-095: "Atualizar a folha" mostra o título que a outra pessoa salvou, sem perguntar "Sair sem salvar?"',
    await op2.inputValue('#rv-titulo').catch(() => '?'));
  // contagem converge
  await T.abrirConferir(op, P); await T.abrirConferir(op2, P);
  const c1 = await txt(op, '#cf-prog'), c2 = await txt(op2, '#cf-prog');
  chk(c1 === c2 && c1.length > 0, 'CAMP-095: as duas pessoas veem a mesma contagem depois de recarregar', `${c1} × ${c2}`);
  // aprovar com folha pendente: recusado com mensagem clara
  const lote = um('SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', P);
  const ap = await ad.evaluate(l => fetch('/api/lotes/' + l + '/aprovar', { method: 'POST' }).then(async r => ({ s: r.status, t: await r.text() })), lote);
  chk([400, 409].includes(ap.s) && /conferir/i.test(ap.t), 'CAMP-095: aprovar com folha ainda pendente é recusado com a explicação', JSON.stringify(ap));
});
