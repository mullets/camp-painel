// CAMP-125 (20/10, página do projeto F026-P0009 CRASA). Pelo caminho real (estação reserva, CAMP Vision grava a pasta e avisa;
// tests/exaustao/p4_montar.py) e clicando como uma pessoa: a sugestão "UF: SP" tem "Usar" à vista (no cartão Dados, sem abrir nada) e grava SP
// com 1 clique; as 31 propostas aparecem como "31 propostas sem resposta" e se resolvem rápido: tabela (folha, o que é, proposta, hoje), A/R no
// teclado seguindo para a próxima, "Aceitar as N onde hoje está vazio", "Recusar as restantes"; nada que alguém escreveu é trocado; o contador
// some no zero; tudo em menos de 1 minuto.
// Rodar: EXAUSTAO_PORTA=8974 bash tests/rodar_exaustao.sh tests/exaustao/p4_propostas_obras.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (P) => execFileSync('python3', [path.join(__dirname, 'p4_montar.py'), 'pronto', T.BASE, T.RAIZ, P], { encoding: 'utf-8' });
const novoProjeto = (nome) => { const P = T.cv2('reservar', T.BASE, 'F026', nome, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, nome); montar(P); return P };
const abrirLotes = async (pg, P) => { await T.abrirProjeto(pg, P); if (!(await pg.isVisible('.pj-gav[data-gav="folhas"]'))) await pg.click(`#pj-cards [data-pjc-gav="folhas"]`); await pg.waitForSelector('#pj-cv .cv-resumo', { timeout: 15000 }) };

T.rodar(async () => {
  T.passo('preparo: um lote como o da CRASA, pelo caminho real');
  const PA = novoProjeto('CRASA STO ANDRE');
  T.chk(T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PA) === 34, `o aviso do CAMP Vision trouxe as 34 folhas de ${PA}`);
  const op = await T.entrar('operador');

  T.passo('CAMP-125: sugestão "UF: SP" à vista e com 1 clique');
  await T.abrirProjeto(op, PA);
  const ufBt = `#pj-cards .pjc[data-pjc="dados"] [data-cv-resp="sugestao"][data-chave="uf"]`;
  T.chk(await T.espera(() => op.isVisible(ufBt)), 'CAMP-125: o cartão Dados mostra "Usar UF SP" sem abrir nada', await T.txt(op, '#pj-cards .pjc[data-pjc="dados"]'));
  await T.print(op, 'dados_sugestao_uf');
  if (await op.$(ufBt)) await op.click(ufBt);
  T.chk(await T.espera(() => T.um('SELECT uf FROM projeto WHERE codigo=?', PA) === 'SP'), 'CAMP-125: 1 clique e a UF do projeto vira SP', T.um('SELECT uf FROM projeto WHERE codigo=?', PA));
  T.chk(await T.espera(async () => !(await op.$(ufBt))), 'CAMP-125: a sugestão some depois de usada');

  T.passo('CAMP-125: 31 propostas resolvidas rápido, sem trocar nada escrito');
  await abrirLotes(op, PA);
  const resumo = await T.txt(op, '#pj-cv .cv-resumo');
  T.chk(/31 propostas sem resposta/.test(resumo), 'CAMP-125: o resumo diz "31 propostas sem resposta"', resumo);
  const t0 = Date.now(), antes = JSON.stringify(T.sql('SELECT codigo, titulo, ano_folha, pendencias, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo', PA));
  await op.click('#pj-cv [data-cv-abrir="propostas"]').catch(() => {});
  const nLinhas = await op.$$eval('#pj-cv .cvp-tab tr[data-cvp]', l => l.length).catch(() => 0);
  T.chk(nLinhas === 31, `CAMP-125: as 31 propostas viram uma tabela (folha, o que é, proposta, hoje): ${nLinhas} linhas`);
  T.chk(/Folha.*O que é.*Proposta do CAMP Vision.*Hoje/.test(await T.txt(op, '#pj-cv .cvp-tab thead')), 'CAMP-125: colunas folha, o que é, proposta e hoje');
  await T.print(op, 'propostas_tabela');
  // teclado: A na primeira, R na seguinte, o foco segue sozinho
  const l1 = await op.$eval('#pj-cv .cvp-tab tr[data-cvp]', t => t.dataset.cvp);
  await op.focus(`#pj-cv tr[data-cvp="${l1}"]`); await op.keyboard.press('a');
  T.chk(await T.espera(() => T.um("SELECT acao FROM cv_resposta WHERE tipo='proposta' AND chave=?", l1) === 'aceitar'), 'CAMP-125: tecla A aceita a proposta da linha');
  const l2 = await op.evaluate(() => (document.activeElement && document.activeElement.dataset) ? document.activeElement.dataset.cvp : null);
  T.chk(!!l2 && l2 !== l1, 'CAMP-125: depois de responder, o foco vai para a próxima proposta sem resposta', String(l2));
  if (l2) { await op.keyboard.press('r'); T.chk(await T.espera(() => T.um("SELECT acao FROM cv_resposta WHERE tipo='proposta' AND chave=?", l2) === 'recusar'), 'CAMP-125: tecla R recusa') }
  // em lote
  const vazBt = '#pj-cv [data-cvp-lote="vazias"]';
  const nVaz = +((await T.txt(op, vazBt)).match(/Aceitar as (\d+) onde hoje está vazio/) || [0, -1])[1];
  T.chk(nVaz === 21, `CAMP-125: botão "Aceitar as 21 onde hoje está vazio" (23 vazias menos as 2 já respondidas no teclado): ${nVaz}`, await T.txt(op, '#pj-cv .cvp-lote'));
  await op.click(vazBt);
  await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE tipo='proposta' AND projeto_codigo=?", PA) >= 23);
  const vazAceitas = T.sql("SELECT chave FROM cv_resposta WHERE tipo='proposta' AND acao='aceitar' AND projeto_codigo=?", PA).length;
  T.chk(vazAceitas === 22, `CAMP-125: aceitou só as vazias (21 do botão + 1 da tecla A; as 8 com código já escrito ficam): ${vazAceitas}`);
  await op.click('#pj-cv [data-cvp-lote="resto"]'); await T.confirmar(op);
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE tipo='proposta' AND projeto_codigo=?", PA) === 31), '"Recusar as restantes" responde o resto (31 de 31)');
  T.chk(T.sql("SELECT chave FROM cv_resposta WHERE tipo='proposta' AND acao='aceitar' AND projeto_codigo=? AND chave LIKE 'sem_codigo_de_unidade:%'", PA).every(r => +r[0].split(':')[1] < 15),
    'CAMP-125: nenhuma proposta com "hoje" preenchido foi aceita sem um clique explícito nela');
  T.chk(JSON.stringify(T.sql('SELECT codigo, titulo, ano_folha, pendencias, status_site FROM item WHERE projeto_codigo=? ORDER BY codigo', PA)) === antes, 'CAMP-125: responder não mexeu em nenhuma folha (só registra)');
  const seg = (Date.now() - t0) / 1000;
  T.chk(seg < 60, `CAMP-125: as 31 propostas resolvidas em ${seg.toFixed(1)} s (menos de 1 minuto)`);
  const rs = await T.txt(op, '#pj-cv .cv-resumo');
  T.chk(!/propostas? sem resposta/.test(rs) && !(await op.$('#cv-sec-propostas')), 'CAMP-125: o contador some no zero (nem no resumo nem a seção)', rs);
  await T.print(op, 'propostas_respondidas');
  T.chk(T.um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='cv_proposta_aceitar'", PA) === 22, 'CAMP-125: cada resposta fica no Histórico do projeto');
});
