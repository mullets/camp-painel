// CAMP-122 (P1), CAMP-128 (P7) e CAMP-131 (P10), 20/10, página do projeto F026-P0009 CRASA (print do Rafa). Pelo caminho real (tests/exaustao/p1_montar.py):
// a estação reserva, o CAMP Vision lê 34 folhas e avisa; a equipe corrigiu 22, conferiu 9, reteve 3 e aprovou; o CAMP Vision releu e gravou "erro"
// que é SÓ `…D00034.tif Warning: [Minor] IPTC:By-line exceeds length limit (truncated)`; o projeto foi publicado. Tudo no navegador.
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p1_montar.py'), ...a], { encoding: 'utf-8' }).trim().split('\n').pop();
const folhaTxt = async (pg) => T.txt(pg, '#pj-cards .pjc[data-pjc="folhas"]');
const corFolhas = (pg) => pg.$eval('#pj-cards .pjc[data-pjc="folhas"]', c => c.className);
const abrirDet = async (pg) => { if (!(await pg.isVisible('.pj-gav[data-gav="folhas"]'))) { await pg.click('#pj-cards [data-pjc-gav="folhas"]'); await pg.waitForTimeout(600) } };
T.rodar(async () => {
  T.passo('montagem (caminho real: estação + CAMP Vision + avisos)');
  const A = montar('crasa', T.BASE, T.RAIZ, T.DB, 'CRASA STO ANDRE');
  const B = montar('legado', T.BASE, T.RAIZ, T.DB, 'CRASA LEGADO');
  const C = montar('erro_vazio', T.BASE, T.RAIZ, 'CASA ERRO VAZIO');
  const D = montar('erro_com_folhas', T.BASE, T.RAIZ, T.DB, 'CASA ERRO COM FOLHAS');
  const DA = n => `${A}-1978-S01-D${String(n).padStart(5, '0')}`;
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", A) === 34 && T.um("SELECT status_site FROM projeto WHERE codigo=?", A) === 'no_ar', `cenário: ${A} com 34 folhas, publicado`);

  T.passo('CAMP-122 (P1): aviso [Minor] do exiftool não é "Lote parado por erro"');
  const op = await T.entrar('operador', { viewport: { width: 1920, height: 1080 } });
  await T.abrirProjeto(op, A);
  let f = await folhaTxt(op);
  T.chk(!/Lote parado/i.test(f) && !/\bbl\b/.test(await corFolhas(op)), 'CAMP-122: na CRASA o cartão Folhas não fica vermelho nem diz "Lote parado por erro"', f);
  T.chk(/1 aviso do CAMP Vision · não impede publicar/.test(f), 'CAMP-122: o cartão Folhas diz "1 aviso do CAMP Vision · não impede publicar"', f);
  T.chk(T.um("SELECT etapa FROM lista_processamento WHERE projeto_codigo=?", A) === 'publicado', 'CAMP-122: o lote saiu de "erro" (publicado, como o projeto)', T.um("SELECT etapa FROM lista_processamento WHERE projeto_codigo=?", A));
  const prob = await T.txt(op, '#pj-cards .pjc[data-pjc="problemas"]');
  T.chk(/1\s+aviso · nenhum impede publicar/.test(prob), 'CAMP-122: o aviso aparece em Problemas como "não impede publicar"', prob);
  await abrirDet(op);
  const gav = await T.txt(op, '#pj-gav-erro');
  T.chk(/1 arquivo \(D00034\): o nome do autor era longo demais para o campo IPTC e foi cortado\. Não impede publicar\./.test(gav), 'CAMP-122: a mensagem em linguagem de gente, com a folha D00034', gav);
  T.chk(await op.$(`#pj-gav-erro a[href="#conferir/${A}/${DA(34)}"]`) !== null, 'CAMP-122: link para a folha D00034');
  T.chk(!/Nada foi importado/.test(await T.txt(op, '#pd')), 'CAMP-122: nunca "Nada foi importado" num projeto com folhas desse lote');
  await T.print(op, 'crasa_aviso');

  T.passo('CAMP-131 (P10): Pedir releitura diz antes o que muda e o que fica; reler só a folha com aviso');
  const antes = JSON.stringify(T.sql("SELECT codigo, titulo, escala, revisao, retida, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo", A));
  const btRel = await op.$$('#pd [data-releitura-projeto]:visible');
  T.chk(btRel.length === 1, `CAMP-128: um só "Pedir releitura" na página (${btRel.length})`);
  await op.click('#pj-gav-erro [data-releitura-projeto]');
  await op.waitForSelector('#conf-ov', { timeout: 8000 });
  const conf = await T.txt(op, '#conf-ov');
  T.chk(/34 folhas/.test(conf) && /22 correções suas/.test(conf) && /9 conferidas/.test(conf) && /3 retidas/.test(conf) && /31 folhas/.test(conf) && /O site só muda quando você publicar de novo/.test(conf),
    'CAMP-131: a confirmação traz os números reais (34 folhas; ficam 22 correções, 9 conferidas, 3 retidas e as 31 do site)', conf);
  T.chk(/Só a folha com aviso \(D00034\)/.test(conf) && /tempo estimado: 1 min/.test(conf) && /O lote inteiro \(34 folhas\)/.test(conf), 'CAMP-131: opção de reler só a folha com aviso, com tempo estimado', conf);
  await T.print(op, 'releitura_confirmacao');
  await op.click('#conf-ov [data-conf="sim"]'); await op.waitForTimeout(800);
  const ped = T.sql("SELECT item_codigo FROM pedido_releitura WHERE projeto_codigo=? AND estado='pedido'", A);
  T.chk(ped.length === 1 && ped[0][0] === DA(34), 'CAMP-131: o pedido é só da D00034 (nenhum pedido do projeto inteiro)', JSON.stringify(ped));
  const rcv = JSON.parse(montar('releitura', T.BASE, T.RAIZ, T.DB, A));
  T.chk(rcv.pedidos === 1, 'cenário: o CAMP Vision atendeu o pedido e gravou o que mudou', JSON.stringify(rcv));
  const depois = JSON.stringify(T.sql("SELECT codigo, titulo, escala, revisao, retida, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo", A));
  T.chk(antes === depois && T.um("SELECT status_site FROM projeto WHERE codigo=?", A) === 'no_ar', 'CAMP-131: a releitura não altera as 33 outras folhas, a D00034 nem o site (nada muda sozinho)');
  await T.abrirProjeto(op, A); await abrirDet(op);
  await op.waitForSelector('[data-rl-mud]', { timeout: 15000 }).catch(() => {});
  const rl = await T.txt(op, '#pj-cv');
  T.chk(/Releituras: o que mudou \(1\) · 2 mudanças para decidir/.test(rl), 'CAMP-131: "Releituras: o que mudou" aberto, com 2 mudanças para decidir', rl.slice(0, 600));
  await T.print(op, 'releitura_o_que_mudou');
  const chT = `20261020-160000|${DA(34)}|titulo`, chE = `20261020-160000|${DA(34)}|escala`;
  await op.click(`[data-rl-mud="${chT}"] [data-acao="aceitar"]`);
  T.chk(await T.espera(() => T.um("SELECT titulo FROM item WHERE codigo=?", DA(34)) === 'PLANTA DE COBERTURA'), 'CAMP-131: "Aceitar" grava na folha o título que a releitura trouxe');
  await T.abrirProjeto(op, A); await abrirDet(op); await op.waitForSelector(`[data-rl-mud="${chE}"] [data-acao="ignorar"]`, { timeout: 15000 }).catch(() => {});
  await op.click(`[data-rl-mud="${chE}"] [data-acao="ignorar"]`);
  T.chk(await T.espera(() => T.um("SELECT acao FROM cv_resposta WHERE tipo='proposta' AND chave=?", 'releitura:' + chE) === 'ignorar') && T.um("SELECT escala FROM item WHERE codigo=?", DA(34)) === '1:50',
    'CAMP-131: "Ignorar" registra e a folha fica como está');
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND codigo<>? AND titulo LIKE 'PLANTA DE COBERTURA'", A, DA(34)) === 0, 'CAMP-131: nenhuma outra folha mudou');

  T.passo('CAMP-122 (P1): "Marcar como visto"');
  await T.abrirProjeto(op, A); await abrirDet(op);
  await op.click('#pj-gav-erro [data-cv-visto]');
  T.chk(await T.espera(async () => !/aviso do CAMP Vision/.test(await folhaTxt(op))), 'CAMP-122: "Marcar como visto" tira o aviso do cartão Folhas', await folhaTxt(op));
  T.chk(T.um("SELECT situacao FROM erro WHERE chave LIKE 'campvision:aviso-menor:%' AND codigo=?", DA(34)) === 'fechado', 'CAMP-122: o aviso fica fechado em Problemas (com quem viu)');

  T.passo('CAMP-122 (P1): a base que já estava em "erro" (produção antes desta versão) se cura ao abrir');
  await T.abrirProjeto(op, B);
  f = await folhaTxt(op);
  T.chk(!/Lote parado/i.test(f) && /aviso do CAMP Vision/.test(f) && T.um("SELECT etapa FROM lista_processamento WHERE projeto_codigo=?", B) === 'publicado',
    'CAMP-122: lote antigo em "erro" só por aviso [Minor] sai do vermelho e mostra o aviso', f);

  T.passo('CAMP-122 / CAMP-128: erro de verdade continua vermelho; mensagem uma vez só');
  await T.abrirProjeto(op, C);
  f = await folhaTxt(op);
  T.chk(/Lote parado por erro do CAMP Vision/.test(f) && /\bbl\b/.test(await corFolhas(op)), 'CAMP-122: erro de verdade sem nada importado continua vermelho', f);
  T.chk(!/timeout/.test(f), 'CAMP-128: o cartão só resume (sem o texto cortado no meio)', f);
  T.chk(await op.isVisible('.pj-gav[data-gav="folhas"]'), 'CAMP-128: com ação pendente (lote parado), Detalhes dos lotes abre sozinho');
  const pd = await op.innerText('#pd');
  T.chk((pd.match(/não respondeu \(timeout\)/g) || []).length === 1, 'CAMP-128: a mensagem do erro aparece 1 vez na página', (pd.match(/não respondeu \(timeout\)/g) || []).length);
  T.chk((await op.$$('#pd [data-releitura-projeto]:visible')).length === 1, 'CAMP-128: um só "Pedir releitura"');
  T.chk(/Nada foi importado deste lote/.test(await T.txt(op, '#pj-gav-erro')), 'CAMP-122: sem folhas, diz "Nada foi importado"');
  await T.print(op, 'erro_de_verdade');
  await T.abrirProjeto(op, D);
  const gD = await T.txt(op, '#pj-gav-erro');
  T.chk(/Lote parado/.test(await folhaTxt(op)) && !/Nada foi importado/.test(gD) && /As 4 folhas que já vieram deste lote continuam no painel/.test(gD), 'CAMP-122: erro de verdade com folhas importadas: vermelho, mas sem "Nada foi importado"', gD);

  T.passo('CAMP-128 (P7): Detalhes dos lotes fechado por padrão; lembra o que a pessoa deixou');
  const op2 = await T.entrar('operador', { viewport: { width: 1920, height: 1080 } });   // navegador novo (sem preferência guardada)
  await T.abrirProjeto(op2, A);
  T.chk(await op2.isHidden('#pj-gaveta'), 'CAMP-128: sem pendência no lote, Detalhes dos lotes fica fechado');
  await op2.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /^Entendi/.test(x.textContent.trim())); if (b) b.click() });
  await op2.waitForTimeout(300);
  const topo = await op2.$eval('#pd .folhas-bar', e => e.getBoundingClientRect().top).catch(() => 9999);
  T.chk(topo < 1080, `CAMP-128: numa tela de 1080 px, a grade de folhas aparece sem rolar (topo em ${Math.round(topo)} px)`);
  await T.print(op2, 'crasa_sem_pendencia');
  await op2.click('#pj-cards [data-pjc-gav="folhas"]'); await op2.waitForTimeout(300);
  await T.abrirProjeto(op2, A);
  T.chk(await op2.isVisible('.pj-gav[data-gav="folhas"]'), 'CAMP-128: a pessoa abriu: na próxima visita continua aberto');
  await op2.click('.pj-gav[data-gav="folhas"] [data-pjc-fechar]'); await op2.waitForTimeout(300);
  await T.abrirProjeto(op2, A);
  T.chk(await op2.isHidden('#pj-gaveta'), 'CAMP-128: a pessoa fechou: na próxima visita continua fechado');

  T.passo('Painel inicial');
  const ex = await T.entrar('operador');   // Painel numa aba nova (abre já no Painel)
  await ex.waitForTimeout(3000);
  const ini = (await ex.innerText('body')).replace(/\s+/g, ' ');
  T.chk(!/parou com erro em CRASA/i.test(ini) && /parou com erro em CASA ERRO VAZIO/i.test(ini), 'CAMP-122: o Painel não lista a CRASA como parada; o erro de verdade continua lá', ini.slice(0, 400));
});
