// Escritórios parceiros / projetos complementares na folha (19/10) no navegador de verdade (Playwright + Chromium).
// Prova: na revisão, adicionar dois parceiros (um com "Outra" + texto) e salvar grava, limpa "Alterações não salvas" e segue sem
// "Sair sem salvar?"; o nome salvo aparece como sugestão na folha seguinte; "Copiar para outras folhas…" aplica a outra folha escolhida;
// a página da folha mostra os parceiros; a edição da folha remove um; o projeto mostra "Parceiros neste projeto"; nada em onclick; sem erro de JS.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765/8777):
//   CAMP_DB_PATH=/tmp/pc.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/pc.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8931)
//   CAMP_DB_PATH=/tmp/pc.db CAMP_BASE=http://127.0.0.1:8931 node tests/navegador_parceiros.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8931', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0093', D = n => `${P}-1970-S01-D0000${n}`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',93)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',93,'Edifício com calculista',1970,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote estrutura','${P}','/nao/existe','revisao')").lastrowid
for n in (1,2,3):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,pendencias,titulo) VALUES (?,?,?,?,?,?,?,?,?)",
      ("${P}-1970-S01-D%05d" % n,"${P}","S01",n,'campvision',lote,'nao_publicado',json.dumps({"bloqueios":[],"sinais":[],"ressalvas":[]}),"Estrutura %d" % n))
`);
const espera = async (f, ms = 6000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 200)); } return false; };
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  const item = c => pg.evaluate(c => fetch('/api/itens/' + c).then(r => r.json()), c);
  const aberta = () => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent);
  const pergunta = () => pg.evaluate(() => { const o = document.getElementById('conf-ov'); return o ? o.querySelector('h2').textContent : ''; });
  const sujo = () => pg.evaluate(() => { const d = document.getElementById('dirty-state'); return !!d && d.classList.contains('on'); });
  const nomes = l => (l || []).map(x => `${x.escritorio}|${x.disciplina}`).join(' ; ');
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
  await pg.evaluate(c => abrirRevisaoItem(c), D(1)); await pg.waitForSelector('#rv-titulo');   // (o centro do cartão sem imagem é o botão "Pedir releitura")
  chk(await pg.isVisible('[data-parc-bloco="rv-parceiros"]'), 'a revisão tem o bloco "Escritórios parceiros" em "Dados da folha"');
  // adicionar dois
  await pg.click('[data-parc-bloco="rv-parceiros"] [data-parc-add]'); await pg.click('[data-parc-bloco="rv-parceiros"] [data-parc-add]');
  const L = '[data-parc-bloco="rv-parceiros"] .parc-linha';
  await pg.fill(`${L} >> nth=0 >> .parc-esc`, 'Escritório Técnico Calc'); await pg.selectOption(`${L} >> nth=0 >> .parc-dis`, 'Estrutura');
  await pg.fill(`${L} >> nth=1 >> .parc-esc`, 'Burle Marx & Cia'); await pg.selectOption(`${L} >> nth=1 >> .parc-dis`, 'Outra');
  chk(await pg.isVisible(`${L} >> nth=1 >> .parc-outra`), '"Outra" mostra o campo para escrever qual');
  await pg.fill(`${L} >> nth=1 >> .parc-outra`, 'Paisagismo de cobertura');
  chk(await sujo(), 'mexer nos parceiros marca "Alterações não salvas"');
  chk(await pg.evaluate(() => document.querySelector('[data-parc-bloco="rv-parceiros"]').classList.contains('alterado')), 'o bloco fica marcado como alterado');
  await pg.click('[data-rev-item="corrigida"]');
  await espera(async () => (await item(D(1))).item.revisao !== 'pendente');
  const i1 = (await item(D(1))).item;
  chk(nomes(i1.parceiros) === 'Escritório Técnico Calc|Estrutura ; Burle Marx & Cia|Paisagismo de cobertura' && i1.revisao === 'corrigida', '"Salvar correção" grava os dois parceiros', JSON.stringify([i1.parceiros, i1.revisao]));
  const foi = await espera(async () => await aberta() === D(2));
  chk(foi && !(await pergunta()) && !(await sujo()), 'depois de salvar, a próxima folha abre SEM "Sair sem salvar?" e sem "Alterações não salvas"', await pergunta());
  // sugestões de nome (datalist)
  chk(await espera(async () => await pg.evaluate(() => [...document.querySelectorAll('#parc-nomes option')].some(o => o.value === 'Escritório Técnico Calc'))), 'o nome já usado aparece como sugestão na folha seguinte');
  chk(!(await pg.$$(`[data-parc-bloco="rv-parceiros"] .parc-linha`)).length, 'a folha 2 começa sem parceiros');
  // "Está certo" sem mexer não manda parceiros (e segue sem perguntar)
  await pg.evaluate(c => abrirRevisaoItem(c), D(1)); await espera(async () => await aberta() === D(1));
  chk((await pg.$$(L)).length === 2 && await pg.inputValue(`${L} >> nth=1 >> .parc-outra`) === 'Paisagismo de cobertura', 'ao reabrir, a disciplina fora da lista volta como "Outra" + o texto');
  // copiar para a folha 3 (escolhida)
  await pg.click('[data-parc-bloco="rv-parceiros"] [data-parc-copiar]'); await pg.waitForSelector('.parc-copia', { timeout: 5000 });
  await pg.check('.parc-copia [name="parc-alvo"][value="itens"]'); await pg.check(`.parc-escolher input[value="${D(3)}"]`);
  chk(!(await sujo()), 'abrir e escolher na caixa de copiar não conta como alteração a perder');
  await pg.click('[data-parc-copiar-ok]'); await pg.waitForSelector('.parc-copiado', { timeout: 5000 });
  const i3 = (await item(D(3))).item, i2 = (await item(D(2))).item;
  chk(nomes(i3.parceiros) === nomes(i1.parceiros) && !(i2.parceiros || []).length, '"Copiar para outras folhas" aplica só à folha escolhida', JSON.stringify([i3.parceiros, i2.parceiros]));
  await pg.evaluate(() => closeDrawer(true));
  // página da folha
  await pg.goto(BASE + '/#item/' + D(1)); await pg.waitForSelector('#it-parceiros', { timeout: 10000 });
  const txt = await pg.textContent('#it-parceiros');
  chk(/Escritório Técnico Calc/.test(txt) && /Estrutura/.test(txt) && /Burle Marx & Cia/.test(txt) && /Paisagismo de cobertura/.test(txt), 'a página da folha mostra os parceiros', txt);
  chk(!(await pg.evaluate(() => [...document.querySelectorAll('[onclick]')].some(e => /Burle|Calc/.test(e.getAttribute('onclick'))))), 'nomes nunca em onclick');
  // edição da folha: remover um
  await pg.click('#it-editar'); await pg.waitForSelector('[data-parc-bloco="ei-parceiros"] .parc-linha');
  await pg.click('[data-parc-bloco="ei-parceiros"] .parc-linha >> nth=1 >> [data-parc-remover]');
  await pg.click('#ei-salvar'); await espera(async () => (((await item(D(1))).item.parceiros) || []).length === 1);
  chk(nomes((await item(D(1))).item.parceiros) === 'Escritório Técnico Calc|Estrutura', 'a edição da folha remove um parceiro');
  // dossiê
  await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pj-parceiros', { timeout: 10000 });
  const pj = await pg.textContent('#pj-parceiros');
  chk(/Parceiros neste projeto/.test(pj) && /Escritório Técnico Calc/.test(pj) && /Burle Marx & Cia/.test(pj), 'o projeto mostra "Parceiros neste projeto"', pj);
  // XSS: nome de escritório com HTML não executa (página da folha, revisão, sugestões e projeto)
  py(`con.execute("UPDATE item SET parceiros=? WHERE codigo='${D(2)}'", (json.dumps([{"escritorio":"<img src=x onerror=window.__xss=1>","disciplina":"<b>Outra</b>"}]),))`);
  await pg.goto(BASE + '/#item/' + D(2)); await pg.waitForSelector('#it-parceiros', { timeout: 10000 });
  await pg.evaluate(c => abrirRevisaoItem(c), D(2)); await pg.waitForSelector('[data-parc-bloco="rv-parceiros"] .parc-linha'); await pg.waitForTimeout(500);
  chk(await pg.inputValue('[data-parc-bloco="rv-parceiros"] .parc-esc') === '<img src=x onerror=window.__xss=1>' && await pg.inputValue('[data-parc-bloco="rv-parceiros"] .parc-outra') === '<b>Outra</b>', 'nome com HTML aparece como texto no campo');
  await pg.evaluate(() => closeDrawer(true)); await pg.goto(BASE + '/#projeto/' + P); await pg.waitForSelector('#pj-parceiros', { timeout: 10000 });
  chk(!(await pg.evaluate(() => window.__xss)) && !(await pg.$('#pj-parceiros img, #it-parceiros img')), 'nome com HTML não vira HTML (sem XSS)');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  if (process.env.CAPTURA) await pg.screenshot({ path: process.env.CAPTURA, fullPage: true }).catch(() => {});
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join('\n')); console.error('ERRO', e.message); process.exit(2); });
