// 21/10 — especificação "CAMP Acervos — publicar sem travar", etapa 2 (5.1 e 5.2): um bloco no topo do projeto e Publicar de UM clique.
// Caminho real: a estação reserva, o CAMP Vision grava 34 folhas e avisa; antes de conferir o botão explica; conferir, reter 2, uma folha com
// problema que bloqueia (de outro projeto); "Publicar 31 folhas" publica direto (sem painel lateral), com o progresso no próprio botão e
// "Publicado ✓ · Ver no site" no fim; Desfazer (master) volta para rascunho; bloqueio registrado por pessoa desliga o botão com o motivo.
// Rodar: EXAUSTAO_PORTA=8980 bash tests/rodar_exaustao.sh tests/exaustao/p7_publicar_um_clique.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8' }).trim();

T.rodar(async () => {
  T.passo('cenário: 34 folhas pelo caminho real');
  const NOME = 'CASA UM CLIQUE';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
  T.chk((av.importacao || {}).criadas === 34, 'o aviso do CAMP Vision importa as 34 folhas', JSON.stringify(av).slice(0, 200));
  const ad = await T.entrar('admin');

  T.passo('5.1: antes de conferir, o bloco diz o que falta e o botão fica desligado');
  await T.abrirProjeto(ad, P);
  await ad.waitForSelector('#pj-status .pjs-acao', { timeout: 15000 });
  await T.espera(async () => !/verificando/.test(await T.txt(ad, '#pj-status')));
  const s0 = await T.txt(ad, '#pj-status');
  T.chk(/CASA UM CLIQUE/i.test(s0) && s0.includes(P) && /1972/.test(s0), 'o bloco tem o título, o código e o ano', s0);
  T.chk(/34 a conferir/.test(s0) && await ad.$eval('#pj-status [data-pjs-publicar]', b => b.disabled), 'antes de conferir: "34 a conferir" e Publicar desligado', s0);
  T.chk(/(Nenhuma folha pronta|Não dá para publicar porque).*34 folhas esperam conferência/.test(s0) && await ad.$$eval('#pj-status .pjs-razao button', bs => bs.some(b => /Conferir as folhas/.test(b.textContent))), 'a razão vem em uma linha, com o botão que resolve ("Conferir as folhas")', s0);

  T.passo('conferir, reter 2 e 1 folha "de outro projeto"');
  const r0 = await ad.evaluate(async (P) => {
    const D = n => `${P}-1972-S01-D${String(n).padStart(5, '0')}`;
    const j = async (u, b) => (await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) })).status;
    const out = [];
    for (const n of [29, 30]) out.push(await j(`/api/itens/${D(n)}/retencao`, { retida: true, motivo: 'em branco' }));
    const lote = (await (await fetch(`/api/projetos/${P}/revisao`)).json()).lotes[0].id;
    out.push(await j(`/api/lotes/${lote}/conferir-todas`)); out.push(await j(`/api/lotes/${lote}/aprovar`));
    return out;
  }, P);
  T.chk(r0.every(x => x === 200), 'cenário montado', JSON.stringify(r0));
  T.sql("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('bloqueia','projeto_errado','campvision',?,'folha de outra obra','CAMP Vision')", D(5));

  T.passo('5.1: o bloco conta prontas / fora e o botão diz quantas vão');
  await T.abrirProjeto(ad, P);
  await T.espera(async () => !/verificando/.test(await T.txt(ad, '#pj-status')));
  const s1 = await T.txt(ad, '#pj-status');
  const bt = await ad.$('#pj-status [data-pjs-publicar]');
  T.chk(/31 prontas|prontas/.test(s1) && /3 fora do projeto/.test(s1), 'o bloco: prontas e "3 fora do projeto" (2 retidas + 1 de outra obra)', s1);
  T.chk(!!bt && !(await bt.isDisabled()) && /Publicar 31 folhas/.test(await bt.textContent()), 'o botão diz "Publicar 31 folhas" e está ligado', bt ? await bt.textContent() : '');
  await T.print(ad, 'status_pronto');

  T.passo('5.2: um clique publica, sem painel lateral, com o progresso no botão');
  await bt.click();
  const viuProgresso = await T.espera(async () => /Publicando/.test(await T.txt(ad, '#pj-status')), 8000);
  T.chk(viuProgresso, 'o botão vira "Publicando…" no próprio lugar');
  T.chk(!(await ad.$('#pub-go')), 'nenhum painel lateral de plano abre (sem "Publicar agora")');
  const ok = await T.espera(async () => /Publicado ✓/.test(await T.txt(ad, '#pj-status').catch(() => '')), 90000);
  const s2 = await T.txt(ad, '#pj-status');
  T.chk(ok && /Ver no site/.test(s2), 'no fim: "Publicado ✓ · Ver no site"', s2);
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P) === 31, '31 folhas publicadas', T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P));
  T.chk(T.um("SELECT status_site FROM item WHERE codigo=?", D(5)) !== 'no_ar', 'a folha de outra obra ficou de fora');
  T.chk(!!(await ad.$('#pj-status [data-pjs-atualizar]')) && /publicado/.test(s2), 'publicado: o botão vira "Atualizar no site"', s2);
  T.chk(!!(await ad.$('#pj-status [data-pjs-desfazer]')), 'Desfazer disponível logo depois (master)');
  await T.print(ad, 'publicado');

  T.passo('5.2: Desfazer volta para rascunho');
  await ad.click('#pj-status [data-pjs-desfazer]');
  T.chk(await T.espera(() => T.um("SELECT status_site FROM projeto WHERE codigo=?", P) === 'rascunho', 15000), 'Desfazer: o projeto volta para rascunho', T.um("SELECT status_site FROM projeto WHERE codigo=?", P));

  T.passo('o que ainda trava: bloqueio registrado por pessoa no projeto');
  T.sql("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('bloqueia','outro','operador',?,'não publicar até a família responder','adm')", P);
  await T.abrirProjeto(ad, P);
  await T.espera(async () => !/verificando/.test(await T.txt(ad, '#pj-status')));
  const s3 = await T.txt(ad, '#pj-status');
  T.chk(await ad.$eval('#pj-status [data-pjs-publicar]', b => b.disabled) && /Não dá para publicar porque/.test(s3), 'bloqueio de pessoa: botão cinza com "Não dá para publicar porque…" em uma linha', s3);
  T.chk(!!(await ad.$('#pj-status .pjs-razao button')), 'e o botão que resolve está ao lado');
  await T.print(ad, 'bloqueado');
});
