// CAMP-FICHA (25/11/2026). Rafael, na ficha da folha ("Nas outras folhas deste projeto · esta folha parece de estrutura", 3 escritórios
// com "Usar"): "quero usar os 3, mas clico e só dá pra usar um.. estranho isso". E o mesmo escritório com duas grafias do carimbo
// ("DAPA LIMA OTERO…" × "DAFRA- LIMA OTERO…").
// Prova: depois do 1º "Usar" as outras sugestões continuam (com "Adicionado: …"); "Usar todos" põe os que faltam; "Mover para Escritórios
// parceiros" com nome quase igual a outro do projeto oferece "Parece o mesmo que DAFRA-…" → "Usar esse nome"; na página do projeto,
// "Parceiros neste projeto" mostra os nomes parecidos e "Unificar nomes" (prévia, aplica em todas as folhas).
// Uso (servidor PRÓPRIO; banco: semear_banco_teste.py + semente_revisao_sequencia.py + semente_escritorios_usar.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9137 PRINTS=<pasta> node tests/navegador_escritorios_usar.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9137';
const PRINTS = process.env.PRINTS || '/dev/shm';
const P = 'F026-P0001', D4 = `${P}-1968-S01-D00004`;
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
(async () => {
  fs.mkdirSync(PRINTS, { recursive: true });
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.addStyleTag({ content: '#toast,.toast{display:none!important}' }).catch(() => {});
  await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 20000 });
  // cartões: escritório abreviado embaixo; filtro "Sem escritório"
  const esc1 = await pg.$eval(`#pd .thumb[data-rev-abrir="${P}-1968-S01-D00001"] .cap-esc`, e => ({ t: e.textContent, title: e.title })).catch(() => null);
  chk(esc1 && esc1.t === 'Parisi · Estrutura +1' && /José Roberto Parisi/.test(esc1.title) && /DAFRA/.test(esc1.title), `cartão da D1: "${esc1 && esc1.t}" (nome inteiro no title)`);
  chk(!(await pg.$(`#pd .thumb[data-rev-abrir="${D4}"] .cap-esc`)), 'cartão sem escritório não mostra nada');
  const chip = await pg.$('#pd .folhas-bar [data-fl-f="semesc"]');
  chk(chip && /Sem escritório \(2\)/.test(await chip.textContent()), 'filtro "Sem escritório (2)": D4 e D5');
  if (chip) { await chip.click(); await pg.waitForTimeout(300); const vis = await pg.$$eval('#pd .pj-folhas .thumb', T => T.filter(t => !t.hidden && t.offsetParent).map(t => t.dataset.revAbrir)); chk(vis.length === 2 && vis.includes(D4), `filtro mostra só as 2 sem escritório (${vis.length})`); await pg.click('#pd .folhas-bar [data-fl-f=""]'); }
  await pg.locator('#pd .pj-folhas').screenshot({ path: `${PRINTS}/cartoes-escritorio-1440.png` });
  await pg.evaluate(c => abrirRevisaoItem(c), D4);
  await pg.waitForSelector('#d-body .parc-sug [data-parc-sug-usar]', { timeout: 15000 });
  const nomes = () => pg.$$eval('#d-body .parc-sug-linha b', B => B.map(b => b.textContent));
  const linhas = () => pg.$$eval('#d-body .parc-linha .parc-esc', I => I.map(i => i.value).filter(Boolean));
  const n0 = await nomes();
  chk(n0.length === 3, `3 escritórios sugeridos (${n0.join(' | ')})`);
  await pg.click('#d-body [data-parc-sug-usar="0"]'); await pg.waitForTimeout(300);
  const n1 = await nomes();
  chk(n1.length === 2 && !n1.includes(n0[0]), `depois do 1º "Usar", as outras 2 continuam (${n1.join(' | ')})`);
  chk((await pg.textContent('#d-body [data-parc-sug-box]')).includes('Adicionado'), 'mostra "Adicionado: …"');
  await pg.screenshot({ path: `${PRINTS}/escritorios-usar-um-1440.png` });
  await pg.click('#d-body [data-parc-sug-todos]'); await pg.waitForTimeout(300);
  const L = await linhas();
  chk(L.length === 3 && n0.every(x => L.includes(x)), `"Usar todos": os 3 nas linhas (${L.join(' | ')})`);
  chk((await nomes()).length === 0, 'sem sugestão sobrando, o bloco some');
  // nome quase igual: tira as linhas e move o Cliente (DAPA…) para escritórios
  await pg.evaluate(() => { document.querySelectorAll('#d-body [data-parc-remover]').forEach(b => b.click()); });
  await pg.waitForTimeout(200);
  const mover = await pg.$('#d-body [data-cli-mover]');
  chk(!!mover, 'aviso "Parece o escritório de estrutura, não o cliente" com "Mover para Escritórios parceiros"');
  if (mover) { await mover.click(); await pg.waitForTimeout(300); }
  const q = await pg.textContent('#d-body [data-parc-sug-box]').catch(() => '');
  chk(/Parece o mesmo que DAFRA- LIMA OTERO/.test(q), `nome parecido: "Parece o mesmo que DAFRA- LIMA OTERO…" (${q.slice(0, 120)})`);
  chk((await nomes()).length >= 2, 'mover não esconde as outras sugestões');
  await pg.screenshot({ path: `${PRINTS}/escritorios-nome-parecido-1440.png` });
  await pg.click('#d-body [data-parc-quase-usar]'); await pg.waitForTimeout(300);
  const L2 = await linhas();
  chk(L2.includes('DAFRA- LIMA OTERO ENGENHARIA LTDA. S/C.') && !L2.includes('DAPA LIMA OTERO ENGENHARIA LTDA. S/C.'), `"Usar esse nome" troca pela grafia de lá (${L2.join(' | ')})`);
  // volta a grafia DAPA e escolhe "Manter os dois": grava assim, para o projeto ficar com os dois nomes
  await pg.fill('#d-body .parc-linha .parc-esc >> nth=0', 'DAPA LIMA OTERO ENGENHARIA LTDA. S/C.');
  await pg.evaluate(() => { const bl = document.querySelector('#d-body [data-parc-bloco]'); parcQuaseChecar(bl); });
  await pg.waitForSelector('#d-body [data-parc-quase-manter]', { timeout: 5000 });
  await pg.click('#d-body [data-parc-quase-manter]'); await pg.waitForTimeout(200);
  chk(!(await pg.$('#d-body [data-parc-quase-usar]')), '"Manter os dois" fecha o aviso e mantém DAPA');
  await pg.click('#d-body [data-rev-item="conferida"]'); await pg.waitForTimeout(1200);
  await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(800);
  // página do projeto: nomes parecidos (a D00004 ficou com DAPA…) → Unificar nomes
  await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pj-parc-semelhantes [data-parc-unificar]', { timeout: 15000 }).catch(() => {});
  const blk = await pg.textContent('#pj-parc-semelhantes').catch(() => '');
  chk(/Nomes parecidos/.test(blk) && /DAPA/.test(blk) && /DAFRA/.test(blk), 'Parceiros neste projeto: "Nomes parecidos" DAPA × DAFRA');
  await pg.click('#pj-parc-semelhantes [data-parc-unificar]'); await pg.waitForSelector('#pun-previa');
  await pg.waitForFunction(() => /Vai mudar/.test((document.getElementById('pun-previa') || {}).textContent || ''), null, { timeout: 8000 });
  chk(/Vai mudar 1 folha/.test(await pg.textContent('#pun-previa')), 'prévia: vai mudar 1 folha');
  await pg.locator('#pj-parceiros').screenshot({ path: `${PRINTS}/escritorios-unificar-1440.png` }).catch(() => {});
  await pg.screenshot({ path: `${PRINTS}/escritorios-unificar-dialogo-1440.png` });
  await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached' });
  await pg.waitForTimeout(1500);
  const blk2 = await pg.textContent('#pj-parc-semelhantes').catch(() => '');
  chk(!/Nomes parecidos/.test(blk2) && !/DAPA LIMA/.test(await pg.textContent('#pj-parceiros')), 'depois de unificar: um nome só');
  chk(erros.length === 0, 'nenhum erro de JS ' + erros.join(' | ').slice(0, 200));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
