// CAMP-149 (Trello, 22/10): aba "Pronto para publicar" em Projetos e publicar vários de uma vez. As abas são as situações (CAMP-146):
// Precisa de você · Pronto para publicar · No site · Com problema · Todos. Na aba Pronto, marcar → a barra diz "N projetos selecionados ·
// X folhas" → "Publicar os N no site" (o mesmo caminho do Publicar do projeto; com o um passo do CAMP-148, aprova o lote junto).
// Rodar: EXAUSTAO_PORTA=8990 bash tests/rodar_exaustao.sh tests/exaustao/p11_pronto_para_publicar.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'f_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const lote = (nome, n) => { const P = T.cv2('reservar', T.BASE, 'F026', nome, '1972'); montar('processando', T.BASE, T.RAIZ, P, nome); montar('pronto', T.BASE, T.RAIZ, P, String(n)); return P };

T.rodar(async () => {
  T.passo('cenário: 3 projetos conferidos (5, 4 e 3 folhas), um ainda a conferir');
  const A = lote('CASA PRONTA A', 5), B = lote('CASA PRONTA B', 4), C = lote('CASA PRONTA C', 3), Z = lote('CASA A CONFERIR', 2);
  for (const P of [A, B, C]) T.sql("UPDATE item SET revisao='conferida' WHERE projeto_codigo=?", P);
  T.chk([A, B, C, Z].every(P => T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P) > 0), 'os 4 lotes foram importados');
  T.sql("UPDATE configuracao SET valor='1' WHERE chave='publicacao.publicar_um_passo'");     // CAMP-148 ligado: o Publicar aprova o lote junto
  const op = await T.entrar('operador');

  T.passo('as abas de Projetos são as situações');
  await op.evaluate(() => nav('projetos')); await op.waitForSelector('#proj-chips [data-proj-sit]', { timeout: 15000 });
  const abas = await op.$$eval('#proj-chips [data-proj-sit]', bs => bs.map(b => b.dataset.projSit + ':' + b.textContent.replace(/\s+\d[\d.]*$/, '').trim()));
  T.chk(abas.join(',') === 'gente:Precisa de você,pronto:Pronto para publicar,publicado:No site,com_problema:Com problema,todos:Todos', 'abas: Precisa de você · Pronto para publicar · No site · Com problema · Todos', abas.join(','));

  T.passo('aba "Pronto para publicar": os 3 conferidos estão; o que falta conferir não');
  await op.click('#proj-chips [data-proj-sit="pronto"]');
  await T.espera(async () => !!(await op.$(`#projetos-body tr[data-nav="projeto/${A}"]`)), 10000);
  const linhas = await op.$$eval('#projetos-body tr[data-nav]', trs => trs.map(t => t.dataset.nav.replace('projeto/', '')));
  T.chk([A, B, C].every(P => linhas.includes(P)) && !linhas.includes(Z), 'na aba: A, B e C; não o que falta conferir', JSON.stringify(linhas));
  T.chk(await op.$$eval('#projetos-body tr[data-nav] button', bs => bs.length) === 0, 'a linha não tem botão (clicar abre o projeto)');

  T.passo('marcar os 3 → a barra diz quantos e quantas folhas → "Publicar os 3 no site"');
  for (const P of [A, B, C]) await op.click(`#projetos-body tr[data-nav="projeto/${P}"] .proj-sel`);
  await op.waitForTimeout(400);
  const barra = await T.txt(op, '#proj-bulk');
  T.chk(/3 projetos selecionados · 12 folhas/.test(barra) && /Publicar os 3 no site/.test(barra), 'a barra: "3 projetos selecionados · 12 folhas" e "Publicar os 3 no site"', barra);
  const vis = await op.$$eval('#proj-bulk button', bs => bs.filter(b => b.offsetParent !== null).map(b => b.textContent.trim()));
  T.chk(vis.includes('Publicar os 3 no site') && !vis.some(t => /Autorizar|Voltar para rascunho/.test(t)), 'o operador só tem o Publicar (sem Autorizar nem Voltar para rascunho)', JSON.stringify(vis));
  await T.print(op, 'pronto_selecionados');
  await op.click('#proj-bulk-pub');
  const go = await op.waitForSelector('#lote-go', { timeout: 15000 }).catch(() => null);
  T.chk(!!go && /Publicar os 3/.test(await go.textContent()), 'o plano do lote: os 3 vão', await T.txt(op, '#d-body'));
  if (go) await go.click();
  const fim = await T.espera(() => [A, B, C].every(P => T.um('SELECT status_site FROM projeto WHERE codigo=?', P) === 'no_ar'), 120000);
  T.chk(fim, 'os 3 projetos ficaram publicados', JSON.stringify([A, B, C].map(P => T.um('SELECT status_site FROM projeto WHERE codigo=?', P))));
  T.chk(T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo IN (?,?,?) AND status_site='no_ar'", A, B, C) === 12, 'as 12 folhas publicadas');
  T.chk([A, B, C].every(P => !!T.um('SELECT aprovado_em FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', P)), 'os 3 lotes foram aprovados pelo mesmo clique (CAMP-148)');
  T.chk(T.um('SELECT status_site FROM projeto WHERE codigo=?', Z) !== 'no_ar', 'o projeto a conferir não foi publicado');
  await T.print(op, 'publicados');

  T.passo('desligado o um passo, o operador não publica em lote');
  T.sql("UPDATE configuracao SET valor='0' WHERE chave='publicacao.publicar_um_passo'");
  const r = await op.evaluate(async c => (await fetch('/api/projetos/lote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ codigos: [c], acao: 'publicar' }) })).status, Z);
  T.chk(r === 403, 'operador → 403 com o um passo desligado', r);
});
