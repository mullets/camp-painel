// CAMP-148 (22/10, decidido pelo Rafa): "Publicar no site" único. Com publicacao.publicar_um_passo ligado, o lote conferido não pede
// "Aprovar o lote": o Próximo passo já é "Publicar N folhas", o operador também publica, e o clique aprova o lote junto.
// Desligado (padrão), o operador não vê botão de publicar. Na lista de Projetos, o botão "Autorizar" da barra some.
// Rodar: EXAUSTAO_PORTA=8988 bash tests/rodar_exaustao.sh tests/exaustao/p10_um_passo.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const azuis = pg => pg.evaluate(() => [...document.querySelectorAll('#pd .btn.pri')].filter(b => b.offsetParent !== null).map(b => b.textContent.trim()));

T.rodar(async () => {
  T.passo('cenário: 34 folhas conferidas, lote ainda não aprovado');
  const NOME = 'CASA UM PASSO';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  T.chk((av.importacao || {}).criadas === 34, 'o aviso do CAMP Vision importa as 34 folhas', JSON.stringify(av).slice(0, 200));
  T.sql("UPDATE item SET revisao='conferida' WHERE projeto_codigo=?", P);
  const lote = T.um('SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', P);
  T.chk(T.um('SELECT aprovado_em FROM lista_processamento WHERE id=?', lote) === null, 'o lote está conferido e NÃO aprovado');

  T.passo('desligado (padrão): o operador não publica');
  T.sql("UPDATE configuracao SET valor='0' WHERE chave='publicacao.publicar_um_passo'");
  let op = await T.entrar('operador');
  await T.abrirProjeto(op, P); await op.waitForTimeout(1500);
  const st0 = await T.txt(op, '#pj-status');
  T.chk(!(await op.$('#pj-status [data-pjs-publicar]:not([disabled])')) && !(await op.$('#pj-status [data-pp="publicar"]')) && /admin/.test(st0), 'desligado: o operador não tem botão de publicar ("Falta um admin aprovar")', st0);
  await op.context().close();

  T.passo('ligado: o operador vê "Publicar N folhas" no Próximo passo, sem passo "Aprovar o lote"');
  T.sql("UPDATE configuracao SET valor='1' WHERE chave='publicacao.publicar_um_passo'");
  op = await T.entrar('operador');
  await T.abrirProjeto(op, P);
  const ligou = await T.espera(async () => !!(await op.$('#pj-status [data-pjs-publicar]:not([disabled])')), 15000);
  const st1 = await T.txt(op, '#pj-status');
  T.chk(ligou && /Publicar 34 folhas/.test(st1) && !/Aprovar o lote/.test(st1) && /aprovado junto/.test(st1), 'o bloco: "Publicar 34 folhas · o lote conferido é aprovado junto", sem "Aprovar o lote"', st1);
  const az = await azuis(op);
  T.chk(az.length === 1 && /Publicar 34 folhas/.test(az[0]), 'um só botão azul, o Publicar', JSON.stringify(az));
  await op.waitForTimeout(1500);
  const resto = (await T.txt(op, '#pj-falta').catch(() => '')) + ' | ' + (await T.txt(op, '#pj-cards'));
  T.chk(!/Aprovar o lote|falta um admin aprovar|um administrador publica|falta aprovar o lote/.test(resto), 'a página toda concorda: nenhum "Aprovar o lote" / "falta um admin aprovar" / "um administrador publica"', resto.slice(0, 400));
  await T.print(op, 'um_passo_operador');

  T.passo('um clique: aprova, publica, e o operador vê o resultado');
  await op.click('#pj-status [data-pjs-publicar]');
  T.chk(!(await op.$('#conf-ov.on, #conf-ov[open]')), 'sem janela de confirmação');
  const ok = await T.espera(async () => /Publicado ✓/.test(await T.txt(op, '#pj-status').catch(() => '')), 90000);
  T.chk(ok, 'no fim: "Publicado ✓"', await T.txt(op, '#pj-status'));
  T.chk(T.um('SELECT aprovado_por FROM lista_processamento WHERE id=?', lote) === 'operador@camp.test' || !!T.um('SELECT aprovado_em FROM lista_processamento WHERE id=?', lote), 'o lote foi aprovado pelo mesmo clique', T.um('SELECT aprovado_por FROM lista_processamento WHERE id=?', lote));
  T.chk(T.um('SELECT status_site FROM projeto WHERE codigo=?', P) === 'no_ar' && T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", P) === 34, 'projeto e 34 folhas publicados');
  T.chk(T.um("SELECT COUNT(*) FROM evento WHERE tipo='revisao_aprovada' AND codigo=? AND detalhe LIKE '%junto_com_publicar%'", P) === 1, 'a aprovação está no histórico como "junto com publicar"');

  T.passo('Fila e Projetos com o um passo');
  const P2 = T.cv2('reservar', T.BASE, 'F026', 'CASA FILA', '1973'); T.cv2('processando', T.BASE, T.RAIZ, P2, 'CASA FILA');
  JSON.parse(montar(T.BASE, T.RAIZ, P2, 'CASA FILA'));
  T.sql("UPDATE item SET revisao='conferida' WHERE projeto_codigo=?", P2);
  await op.evaluate(() => nav('filas/todas')); await op.waitForSelector('#filas-body tr[data-fase]', { timeout: 15000 }); await op.waitForTimeout(800);
  const lf = await T.txt(op, `#filas-body tr[data-nav="projeto/${P2}"]`);
  T.chk(/Pronto para publicar/.test(lf) && /Publicar no site/.test(lf) && !/Aprovar lote/.test(lf), 'Fila: o lote conferido do operador tem "Publicar no site" (não "Aprovar lote")', lf);
  const ad = await T.entrar('admin');
  await ad.evaluate(() => nav('projetos')); await ad.waitForSelector('#projetos-body tr[data-nav]', { timeout: 15000 });
  await ad.evaluate(() => { const i = document.querySelector('#projetos-body .proj-sel'); if (i) i.click() });
  await ad.waitForTimeout(500);
  const aut = await ad.$$eval('#proj-bulk button', bs => bs.filter(b => /Autorizar/.test(b.textContent)).map(b => getComputedStyle(b).display));
  T.chk(aut.length === 1 && aut[0] === 'none', 'Projetos: o botão "Autorizar" da barra em lote some (publicar já autoriza)', JSON.stringify(aut));
  T.sql("UPDATE configuracao SET valor='0' WHERE chave='publicacao.publicar_um_passo'");
});
