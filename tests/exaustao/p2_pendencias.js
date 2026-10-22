// CAMP-123 (P2) e CAMP-130 (P9), quadro "CAMP Acervos — Painel de administração" (20/10, página do projeto F026-P0009, CRASA Sto. André).
// Cenário montado pelo caminho real (tests/exaustao/p2_montar.py): estação reserva, CAMP Vision grava a pasta e avisa, a operadora corrige 22,
// confere 9 e retém 3, o admin aprova e publica (site falso). Tudo verificado no navegador.
// Rodar: EXAUSTAO_PORTA=8972 EXAUSTAO_SAIDA=/tmp/pj2 bash tests/rodar_exaustao.sh tests/exaustao/p2_pendencias.js
const T = require('./_comum');
const { execFileSync } = require('child_process'); const path = require('path');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p2_montar.py'), ...a], { encoding: 'utf-8' }).trim().split('\n').pop();
const abrirGaveta = async (pg, k) => { if (!(await pg.isVisible(`.pj-gav[data-gav="${k}"]`))) { await pg.click(`#pj-cards [data-pjc-gav="${k}"]`); await pg.waitForTimeout(400) } };

T.rodar(async () => {
  const P = montar('p0009', T.BASE, T.RAIZ);
  T.chk(/^F026-P\d{4}$/.test(P) && T.um("SELECT status_site FROM projeto WHERE codigo=?", P) === 'no_ar' && T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P) === 31,
    `cenário P0009: ${P} publicado, 31 folhas no site, 3 retidas`);
  const ad = await T.entrar('admin');

  // ---------------- CAMP-123 (P2) ----------------
  T.passo('CAMP-123: barra "O que falta para fechar este projeto"');
  await T.abrirProjeto(ad, P);
  const temBarra = await ad.waitForSelector('#pj-falta:not([hidden]) .pj-falta-lista', { timeout: 20000 }).then(() => true, () => false);
  T.chk(temBarra, 'CAMP-123: a barra aparece logo abaixo do título', await T.txt(ad, '#pd'));
  const ordem = await ad.evaluate(() => { const f = document.getElementById('pj-falta'), h = document.querySelector('#pd .dethdr'), c = document.getElementById('pj-cards'); return !!(f && h && c && h.compareDocumentPosition(f) & 4 && f.compareDocumentPosition(c) & 4) });
  T.chk(ordem, 'CAMP-123: a barra fica entre o título e os cartões');
  const itens = await ad.$$eval('#pj-falta .pj-falta-lista li', l => l.map(x => ({ k: x.dataset.pjp, t: x.innerText.replace(/\s+/g, ' ').trim() })));
  const tx = k => (itens.find(x => x.k === k) || {}).t || '';
  T.chk(/Responder 23 propostas e 1 sugestão/.test(tx('cv_respostas')), 'CAMP-123 (P0: as 8 unidades têm item próprio): "Responder 23 propostas e 1 sugestão do CAMP Vision"', JSON.stringify(itens));
  T.chk(/8 códigos de unidade/.test(tx('obras')), 'CAMP-123 (P0): "Decidir sobre os 8 códigos de unidade que o CAMP Vision achou"', JSON.stringify(itens));
  T.chk(/autoria de 5 folhas/.test(tx('autoria')), 'CAMP-123: "Confirmar a autoria de 5 folhas"', JSON.stringify(itens));
  // 21/10: as correções de título foram feitas ANTES de publicar (foram ao site com a publicação): não são "alterações não enviadas"
  // (antes, no mesmo segundo da publicação, contavam como depois; o caso com correção depois de publicar está no p3_site)
  T.chk(itens.length === 3 && itens.map(x => x.k).join(',') === 'cv_respostas,obras,autoria', 'CAMP-123: exatamente o que falta, em ordem (projeto publicado: sem Conferir, Aprovar nem Publicar)', JSON.stringify(itens));
  const selo = await T.txt(ad, '#pj-selo');
  T.chk(/^publicado · 3 pendências$/.test(selo), 'CAMP-123: o selo do cabeçalho diz "publicado · 3 pendências"', selo);
  const men = await T.txt(ad, '#pj-falta .pj-falta-men summary');
  T.chk(!men || /avisos? menor(es)? \(não impedem publicar\)/.test(men), 'CAMP-123: avisos que não impedem publicar ficam recolhidos e não contam', men);
  await T.print(ad, 'p2_barra');
  // cada botão leva ao lugar certo
  await ad.click('#pj-falta li[data-pjp="cv_respostas"] [data-pjp-ir]'); await ad.waitForTimeout(1500);
  T.chk(await ad.evaluate(() => !!document.querySelector('#d-body [data-passo="propostas"] .cvp-tab')), 'CAMP-123 (P0): "Ver" das propostas abre o painel lateral com as propostas');
  await ad.evaluate(() => closeDrawer(true)); await ad.waitForTimeout(300);
  await ad.click('#pj-falta li[data-pjp="obras"] [data-pjp-ir]'); await ad.waitForTimeout(1500);
  T.chk(await ad.evaluate(() => document.querySelectorAll('#d-body [data-passo="obras"] [data-cv-obra]').length === 8), 'CAMP-123 (P0): "Ver" das unidades abre o painel lateral com os 8 grupos');
  await ad.evaluate(() => closeDrawer(true)); await ad.waitForTimeout(300);
  await ad.click('#pj-falta li[data-pjp="autoria"] [data-pjp-ir]');
  T.chk(await T.espera(() => ad.$eval('#pd .pj-tabs [aria-selected="true"]', b => /Problemas/.test(b.textContent))), 'CAMP-123: "Ver" da autoria abre a aba Problemas');
  // resolver a autoria tira o item da barra (a barra acompanha)
  for (const n of [23, 25, 26, 27, 28]) await ad.evaluate(c => fetch('/api/itens/' + c + '/autoria-confirmada', { method: 'POST' }), `${P}-1978-S01-D${String(n).padStart(5, '0')}`);
  await T.abrirProjeto(ad, P); await ad.waitForSelector('#pj-falta:not([hidden]) .pj-falta-lista', { timeout: 20000 }).catch(() => {});
  T.chk(!(await ad.$('#pj-falta li[data-pjp="autoria"]')) && /2 pendências/.test(await T.txt(ad, '#pj-selo')), 'CAMP-123: confirmada a autoria, o item sai da barra e o selo diz 2 pendências', await T.txt(ad, '#pj-falta'));
  // projeto sem nada pendente: verde, sem lista, e vai para o Histórico (uma vez só)
  const PL = montar('limpo', T.BASE, T.RAIZ);
  await T.abrirProjeto(ad, PL);
  const verde = await ad.waitForSelector('#pj-falta.ok [data-pj-fechado]', { timeout: 20000 }).then(() => true, () => false);
  T.chk(verde && /Projeto fechado: painel e site iguais/.test(await T.txt(ad, '#pj-falta')) && !(await ad.$('#pj-falta .pj-falta-lista')), 'CAMP-123: sem nada pendente, a barra fica verde: "Projeto fechado: painel e site iguais", sem lista', await T.txt(ad, '#pj-falta'));
  T.chk(/^publicado$/.test(await T.txt(ad, '#pj-selo')), 'CAMP-123: o selo diz só "publicado"', await T.txt(ad, '#pj-selo'));
  await T.print(ad, 'p2_fechado');
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='projeto_fechado'", PL) === 1), 'CAMP-123: "projeto fechado" gravado no Histórico');
  await T.abrirProjeto(ad, PL); await ad.waitForTimeout(2500);
  T.chk(T.um("SELECT COUNT(*) FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='projeto_fechado'", PL) === 1, 'CAMP-123: abrir de novo não grava outra vez');
  await ad.evaluate(c => showProjeto(c, 'historico'), PL); await ad.waitForTimeout(1200);
  T.chk(/fechado: painel e site iguais/.test(await T.txt(ad, '#pd')), 'CAMP-123: o Histórico mostra "fechado: painel e site iguais"');
  T.chk(!/fechado/.test(JSON.stringify(T.sql("SELECT tipo FROM evento WHERE entidade='projeto' AND codigo=?", P))), 'CAMP-123: o projeto com pendências não ganha "fechado" no Histórico');

  // ---------------- CAMP-130 (P9) ----------------
  T.passo('CAMP-130: contagens do lote que somam o total e o "aceite" explicado');
  await T.abrirProjeto(ad, P); await abrirGaveta(ad, 'folhas');
  await ad.waitForSelector('#pj-revisao .rev-chips', { state: 'attached', timeout: 15000 });
  const chips = await T.txt(ad, '#pj-revisao .rev-chips');
  const nums = [...chips.replace(/^\s*\d+ folhas:/, '').matchAll(/(\d+)\s+(sem mudança|corrigidas?|retidas?|a conferir)/g)].map(m => +m[1]);
  T.chk(/^34 folhas:/.test(chips) && nums.reduce((a, b) => a + b, 0) === 34, 'CAMP-130: as partes do lote somam 34 ("34 folhas: …")', chips);
  T.chk(/9 sem mudança/.test(chips) && /22 corrigidas/.test(chips) && /3 retidas/.test(chips) && !/conferida\(s\)/.test(chips), 'CAMP-130: "9 sem mudança · 22 corrigidas · 3 retidas" (a retida não conta duas vezes)', chips);
  await T.print(ad, 'p9_contagem');
  const semAc = await T.txt(ad, '#pj-cv [data-cv-aceite]');
  T.chk(/Não importa: o lote já foi aprovado por uma pessoa/.test(semAc) && /aceite/.test(semAc), 'CAMP-130: lote aprovado sem o checklist do CAMP Vision: 1 linha em cinza dizendo que não importa', semAc);
  T.chk(!/não mandou o aceite deste lote \(o checklist\)/.test(await T.txt(ad, '#pj-cv')), 'CAMP-130: a frase antiga sem explicação não aparece mais');
  // lote ainda não aprovado: explica o que é e que não impede publicar
  const B = T.loteReal('CASA SEM ACEITE');
  await T.abrirProjeto(ad, B.P); await abrirGaveta(ad, 'folhas');
  await ad.waitForSelector('#pj-cv [data-cv-aceite]', { state: 'attached', timeout: 15000 }).catch(() => {});
  const semAc2 = await T.txt(ad, '#pj-cv [data-cv-aceite]');
  T.chk(/a lista do que ele mesmo conferiu/.test(semAc2) && /Não impede publicar/.test(semAc2), 'CAMP-130: lote não aprovado sem o checklist: diz o que é o aceite e que não impede publicar', semAc2);
  const chipsB = await T.txt(ad, '#pj-revisao .rev-chips');
  T.chk(/^6 folhas: 6 a conferir( · das quais 1 bloqueada para o site)?$/.test(chipsB), 'CAMP-130: lote novo: "6 folhas: 6 a conferir" (a duplicata bloqueada vem como "das quais")', chipsB);
});
