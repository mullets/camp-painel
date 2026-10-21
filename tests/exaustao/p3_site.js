// CAMP-124 (P3, 20/10, F026-P0009 CRASA): "34 folhas no painel · 31 no site · números diferentes" era alerta quando a diferença eram só as
// 3 retidas; a página não dizia o que foi corrigido depois de publicar nem como mandar ao site. Caminho real: a estação reserva, o CAMP Vision
// grava 34 folhas e avisa; conferir, reter 3, aprovar e publicar (site falso); corrigir 1 folha publicada; enviar a alteração.
// Rodar: EXAUSTAO_PORTA=8973 bash tests/rodar_exaustao.sh tests/exaustao/p3_site.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8' }).trim();

T.rodar(async () => {
  T.passo('CAMP-124 (P3): cenário — 34 folhas pelo caminho real, 3 retidas, publicado');
  const NOME = 'CRASA STO ANDRE';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
  T.chk((av.importacao || {}).criadas === 34, 'CAMP-124: o aviso do CAMP Vision importa as 34 folhas', JSON.stringify(av).slice(0, 200));
  const ad = await T.entrar('admin');
  // conferir as 34 e reter 3 (as mesmas chamadas da tela de conferir)
  const r0 = await ad.evaluate(async (P) => {
    const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
    const j = async (u, b) => { const r = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }); return r.status };
    const out = [];
    for (const n of [29, 30, 32]) out.push(await j(`/api/itens/${D(n)}/retencao`, { retida: true, motivo: n === 32 ? 'duplicata de D00033' : 'em branco' }));
    const lotes = await (await fetch(`/api/projetos/${P}/revisao`)).json();
    const lote = lotes.lotes[0].id;
    out.push(await j(`/api/lotes/${lote}/conferir-todas`)); out.push(await j(`/api/lotes/${lote}/aprovar`));
    return out;
  }, P).catch(e => 'erro ' + e.message);
  T.chk(Array.isArray(r0) && r0.every(x => x === 200), 'cenário montado (reter 3, conferir todas, aprovar)', JSON.stringify(r0));
  const ret = T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1", P);
  T.chk(ret === 3, 'CAMP-124: 3 folhas retidas', ret);
  T.chk(T.um("SELECT COUNT(*) FROM lista_processamento WHERE projeto_codigo=? AND aprovado_em IS NOT NULL", P) === 1, 'CAMP-124: lote aprovado');
  // publicar pela tela
  await T.abrirProjeto(ad, P);
  await ad.evaluate(c => abrirPublicacaoGuiada(c), P);
  const go = await ad.waitForSelector('#pub-go:not([disabled])', { timeout: 15000 }).then(() => true, () => false);
  T.chk(go, 'CAMP-124: publicação guiada liberada', await T.txt(ad, '#d-body'));
  if (go) { await ad.click('#pub-go'); await ad.waitForSelector('#d-body .pub-resultado', { timeout: 60000 }).catch(() => {}) }
  await T.print(ad, 'publicado');
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P) === 31, 'CAMP-124: 31 folhas no ar (34 − 3 retidas)', T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P));
  const avisoPub = await ad.evaluate(c => { const t = (window.TAREFAS_VISTAS || []).find(x => x.projeto_codigo === c); return t ? fimTarefaTexto(t) : '' }, P).catch(() => '');
  const toastPub = await T.txt(ad, '#toast'), corpoPub = await T.txt(ad, '#d-body');
  T.chk(/folhas? atualizadas? · 31 no site no total/.test(avisoPub + ' ' + toastPub + ' ' + corpoPub) || /31 no site no total/.test(await ad.evaluate(c => fimTarefaTexto({ tipo: 'publicar', estado: 'ok', projeto_codigo: c, feitas: 31, resultado: { folhas_publicadas: 31 } }), P)),
    'CAMP-124: o aviso de publicação diz "N folhas atualizadas · 31 no site no total"', (avisoPub + ' | ' + toastPub).slice(0, 300));
  await ad.keyboard.press('Escape');

  T.passo('CAMP-124 (P3): faixa painel × site');
  await T.abrirProjeto(ad, P);
  const faixa = await T.txt(ad, '[data-conta-site]');
  T.chk(/31 no site = 34 no painel − 3 retidas ✔/.test(faixa), 'CAMP-124: faixa "31 no site = 34 no painel − 3 retidas ✔"', faixa);
  T.chk(!(await ad.$eval('[data-conta-site]', e => e.classList.contains('warn')).catch(() => true)), 'CAMP-124: com a conta fechando, a faixa fica neutra (sem amarelo)');
  T.chk(/D00029/.test(faixa) && /D00032/.test(faixa) && !/números diferentes/.test(faixa), 'CAMP-124: diz quais são as retidas e não fala em "números diferentes"', faixa);
  T.chk(!(await ad.$('[data-enviar-alteracoes]')), 'CAMP-124: sem alteração, não há botão de enviar');
  await T.print(ad, 'faixa_neutra');

  T.passo('CAMP-124 (P3): corrigir uma folha publicada → selo e "Enviar 1 alteração ao site" → enviar → somem');
  await T.abrirConferir(ad, P, D(5));
  await ad.waitForSelector('#rv-folha', { timeout: 10000 });
  await ad.fill('#rv-folha', '306'); await ad.click('#cf-pane [data-rev-item="corrigida"]'); await T.confirmar(ad);
  T.chk(await T.espera(() => T.um('SELECT folha FROM item WHERE codigo=?', D(5)) === '306'), 'CAMP-124: correção gravada no painel', T.um('SELECT folha FROM item WHERE codigo=?', D(5)));
  await T.abrirProjeto(ad, P);
  const selo = await ad.$eval(`.thumb[data-rev-abrir="${D(5)}"], .thumb[data-nav="item/${D(5)}"]`, t => t.textContent).catch(() => '');
  T.chk(/alterada depois de publicar/.test(selo), 'CAMP-124: a miniatura da D00005 mostra "alterada depois de publicar"', selo.slice(0, 200));
  T.chk(await ad.$$eval('.thumb .alt-site', l => l.length) === 1, 'CAMP-124: só a folha corrigida tem o selo');
  const bt = await T.txt(ad, '[data-enviar-alteracoes]');
  T.chk(/Enviar 1 alteração ao site/.test(bt), 'CAMP-124: botão "Enviar 1 alteração ao site" (admin)', bt);
  await T.print(ad, 'alterada');
  // operador vê o aviso, mas não o botão
  const op = await T.entrar('operador'); await T.abrirProjeto(op, P);
  T.chk(/1 folha alterada depois de publicar/.test(await T.txt(op, '[data-conta-site]')) && !(await op.$('[data-enviar-alteracoes]')), 'CAMP-124: operador vê "1 folha alterada" e "um admin envia", sem o botão');
  // enviar
  await ad.click('[data-enviar-alteracoes]');
  const conf = await ad.waitForSelector('#conf-ov', { timeout: 5000 }).then(() => T.txt(ad, '#conf-ov'), () => '');
  T.chk(/D00005/.test(conf) && /Nº da folha/.test(conf) && /05/.test(conf) && /306/.test(conf), 'CAMP-124: antes de confirmar, a lista do que muda ("D00005 · Nº da folha: 05 → 306")', conf);
  await T.print(ad, 'confirmar_envio');
  await T.confirmar(ad);
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='site_alteracoes_enviadas'", D(5)) === 1), 'CAMP-124: o envio fica no histórico da folha');
  T.chk(await T.espera(async () => !(await ad.$('[data-enviar-alteracoes]')) && !(await ad.$('.thumb .alt-site'))), 'CAMP-124: depois de enviar, o selo e o botão somem');
  T.chk(/"Folha"/.test(T.um('SELECT detalhe FROM evento WHERE codigo=? AND tipo=\'site_texto_editado\' ORDER BY id DESC LIMIT 1', D(5)) || ''), 'CAMP-124: o metadado "Folha" foi enviado ao site (falso)');
  await T.print(ad, 'enviado');

  T.passo('CAMP-124 (P3): diferença sem explicação fica amarela e lista os códigos');
  // a D00010 foi conferida de novo e ficou fora do site (ninguém publicou): devia estar lá e não está
  T.sql("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", D(10)); T.sql('DELETE FROM wp_item WHERE codigo_detectado=?', D(10));
  await T.abrirProjeto(ad, P);
  const f2 = await T.txt(ad, '[data-conta-site]');
  T.chk(await ad.$eval('[data-conta-site]', e => e.classList.contains('warn')) && /ainda não foram ao site: D00010/.test(f2), 'CAMP-124: folha que devia estar no site e não está → amarelo, com o código', f2);
  await T.print(ad, 'faixa_amarela');

  T.passo('21/10 (Rafa, F024-P0001: "pq fica como rascunho? eu quero que suba isso"): projeto publicado com folhas que o visitante não vê');
  T.sql("UPDATE item SET tainacan_item_id=NULL WHERE codigo=?", D(10));                       // nunca subiu
  for (const n of [11, 12]) { T.sql("UPDATE item SET status_site='rascunho' WHERE codigo=?", D(n)); T.sql("UPDATE wp_item SET status='draft' WHERE codigo_detectado=?", D(n)) }   // subiu em rascunho
  await T.abrirProjeto(ad, P);
  const cs = await T.txt(ad, '#pj-cards .pjc[data-pjc="site"]');
  T.chk(/Publicado/.test(cs) && /3 folhas ainda não aparecem no site \(2 em rascunho\)/.test(cs), 'o cartão Site diz "Publicado" e que 3 folhas ainda não aparecem (2 em rascunho)', cs);
  const btAt = await ad.$('#pj-cards [data-pj-atualizar-no-ar]');
  T.chk(!!btAt && /Atualizar a página pública/.test(await btAt.innerText()), 'o cartão Site tem "Atualizar a página pública"');
  T.chk(/Publicar 3 folhas que o visitante ainda não vê/.test(await T.txt(ad, '#pj-falta')), 'a barra "O que falta" tem "Publicar 3 folhas que o visitante ainda não vê"', await T.txt(ad, '#pj-falta'));
  await T.print(ad, 'atualizar_pagina_publica');
  if (btAt) {
    await btAt.click();
    const go = await ad.waitForSelector('#pub-go:not([disabled])', { timeout: 15000 }).then(() => true, () => false);
    T.chk(go, 'abre a publicação guiada', await T.txt(ad, '#d-body').catch(() => ''));
    if (go) { await ad.click('#pub-go'); await T.espera(async () => !!(await ad.$('#d-body .pub-resultado')), 60000) }
  }
  T.chk(await T.espera(() => [10, 11, 12].every(n => T.um('SELECT status_site FROM item WHERE codigo=?', D(n)) === 'no_ar'), 20000), 'as 3 folhas ficam publicadas (a nova sobe; as de rascunho ficam públicas)',
    JSON.stringify([10, 11, 12].map(n => T.um('SELECT status_site FROM item WHERE codigo=?', D(n)))));
  T.chk([29, 30, 32].every(n => T.um('SELECT status_site FROM item WHERE codigo=?', D(n)) !== 'no_ar'), 'as 3 retidas continuam fora');
  await T.abrirProjeto(ad, P);
  T.chk(!(await ad.$('#pj-cards [data-pj-atualizar-no-ar]')) && !/visitante ainda não vê/.test(await T.txt(ad, '#pj-falta').catch(() => '')), 'atualizada, o botão e o item da barra somem');
  await T.print(ad, 'pagina_publica_atualizada');
});
