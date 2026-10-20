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
