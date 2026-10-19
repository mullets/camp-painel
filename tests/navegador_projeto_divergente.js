// Revisão da folha com "projeto divergente" (Clube Sírio, 19/10) no navegador de verdade (Playwright + Chromium).
// Prova: salvar a correção grava, limpa "Alterações não salvas" e segue para a próxima folha SEM perguntar "Sair sem salvar?"
// (antes perguntava logo depois de salvar); Tipo pelas caixas salva; "Está certo" com campo mudado salva (antes descartava);
// valor lido pelo CAMP Vision maior que o limite não impede salvar; erro do servidor aparece no lugar e o que foi digitado fica;
// "É deste projeto (o CAMP Vision errou)" na revisão e na página da folha; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 8910-8919, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/pd.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/pd.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8912)
//   CAMP_DB_PATH=/tmp/pd.db CAMP_BASE=http://127.0.0.1:8912 node tests/navegador_projeto_divergente.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8912', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0092', D = n => `${P}-1970-S01-D0000${n}`;
// 3 folhas a conferir, sem imagem; a 1 e a 2 com "projeto divergente"; o CAMP Vision leu "folha" com 57 caracteres (limite: 40)
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',92)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',92,'Clube Sírio',1970,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote Sírio','${P}','/nao/existe','revisao')").lastrowid
for n,pend,st in [(1,{"bloqueios":["projeto divergente: o carimbo diz 'Clube Atlético Sírio'"],"sinais":["projeto divergente","orientação incerta"],"ressalvas":[]},'bloqueado'),
                  (2,{"bloqueios":[],"sinais":["projeto divergente"],"ressalvas":[]},'bloqueado'),(3,{"bloqueios":[],"sinais":[],"ressalvas":[]},'nao_publicado')]:
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,pendencias,titulo,folha) VALUES (?,?,?,?,?,?,?,?,?,?)",
      ("${P}-1970-S01-D%05d" % n,"${P}","S01",n,'campvision',lote,st,json.dumps(pend,ensure_ascii=False),"Prancha %d" % n,"Prancha 03/12 - planta do pavimento térreo e da cobertura"))
`);
const espera = async (f, ms = 6000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 200)); } return false; };
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  const item = c => pg.evaluate(c => fetch('/api/itens/' + c).then(r => r.json()), c);
  const aberta = () => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent);
  const pergunta = () => pg.evaluate(() => { const o = document.getElementById('conf-ov'); return o ? o.querySelector('h2').textContent : ''; });
  const sujo = () => pg.evaluate(() => { const d = document.getElementById('dirty-state'); return !!d && d.classList.contains('on'); });
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
  await pg.click(`.thumb[data-rev-abrir="${D(1)}"]`); await pg.waitForSelector('#rv-titulo');
  chk(await pg.isVisible(`[data-deste-projeto="${D(1)}"]`), 'a revisão mostra "É deste projeto (o CAMP Vision errou)" na folha com projeto divergente');
  // erro: o motivo aparece no lugar e o que foi digitado fica
  await pg.fill('#rv-titulo', 'Planta do térreo (Sírio)'); await pg.fill('#rv-ano', '1958/59');
  await pg.click('[data-rev-item="corrigida"]'); await pg.waitForSelector('.aviso-local.erro', { timeout: 5000 });
  chk(/Ano da folha/.test(await pg.textContent('.aviso-local.erro')), 'erro de ano aparece no lugar, com o motivo');
  chk(await pg.inputValue('#rv-titulo') === 'Planta do térreo (Sírio)' && await pg.inputValue('#rv-ano') === '1958/59', 'depois do erro, o que foi digitado continua');
  // "É deste projeto"
  await pg.click(`[data-deste-projeto="${D(1)}"]`); await pg.click('#conf-ov [data-conf="sim"]');
  await pg.waitForFunction(() => !document.querySelector('[data-deste-box]'), null, { timeout: 5000 });
  const chips = await pg.textContent('#rv-chips');
  chk(!/projeto divergente/.test(chips) && /orientação incerta/.test(chips), '"É deste projeto": o aviso sai e os outros sinais ficam', chips);
  chk(await pg.inputValue('#rv-titulo') === 'Planta do térreo (Sírio)', '"É deste projeto" não apaga o que foi digitado');
  chk((await item(D(1))).item.status_site === 'nao_publicado', 'servidor: a folha sai de "bloqueado"');
  // "Está certo" com campo mudado: pergunta (sem imagem) ANTES de gravar; depois grava, conta como corrigida e segue sem "Sair sem salvar?"
  await pg.fill('#rv-ano', '1958'); await pg.click('[data-rev-item="conferida"]'); await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 3000 });
  chk((await item(D(1))).item.revisao === 'pendente', 'sem imagem: pergunta antes de gravar');
  await pg.click('#conf-ov [data-conf="sim"]');
  await espera(async () => (await item(D(1))).item.revisao !== 'pendente');
  const i1 = (await item(D(1))).item;
  chk(i1.titulo === 'Planta do térreo (Sírio)' && i1.ano_folha === 1958 && i1.revisao === 'corrigida', '"Está certo" com campos mudados grava (antes descartava) e conta como corrigida', JSON.stringify([i1.titulo, i1.ano_folha, i1.revisao]));
  const foi = await espera(async () => await aberta() === D(2));
  chk(foi && !(await pergunta()) && !(await sujo()), 'depois de salvar, a próxima folha abre SEM "Sair sem salvar?" e sem "Alterações não salvas"', await pergunta());
  // Tipo pelas caixas (campo escondido) + "Salvar correção"
  await pg.evaluate(c => abrirRevisaoItem(c), D(3)); await espera(async () => await aberta() === D(3));
  chk(!(await pg.$(`[data-deste-projeto="${D(3)}"]`)), 'folha sem o aviso não mostra o botão');
  await pg.check('[data-tipos-para="rv-tipo"] input[value="Planta"]'); await pg.check('[data-tipos-para="rv-tipo"] input[value="Corte"]');
  await pg.click('[data-rev-item="corrigida"]'); await espera(async () => (await item(D(3))).item.revisao !== 'pendente');
  const i3 = (await item(D(3))).item, foi2 = await espera(async () => await aberta() === D(2));
  chk(i3.tipo_documento === 'Planta; Corte' && i3.revisao === 'corrigida', 'Tipo marcado nas caixas é salvo pela revisão', JSON.stringify([i3.tipo_documento, i3.revisao]));
  chk(foi2 && !(await pergunta()) && !(await sujo()), 'Tipo + "Salvar correção": segue para a próxima sem "Sair sem salvar?"', await pergunta());
  // página da folha
  await pg.evaluate(() => closeDrawer(true)); await pg.goto(BASE + '/#item/' + D(2)); await pg.waitForSelector(`#idet [data-deste-projeto="${D(2)}"]`, { timeout: 10000 });
  chk(!(await pg.evaluate(() => [...document.querySelectorAll('[onclick]')].some(e => /deste/i.test(e.getAttribute('onclick'))))), 'código só em data-*, nunca em onclick');
  await pg.click(`#idet [data-deste-projeto="${D(2)}"]`); await pg.click('#conf-ov [data-conf="sim"]');
  chk(await espera(async () => !(await pg.$('#idet [data-deste-projeto]'))), 'página da folha: o aviso sai depois de confirmar');
  chk((await item(D(2))).item.status_site === 'nao_publicado', 'servidor: folha 2 sai de "bloqueado"');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join('\n')); console.error('ERRO', e.message); process.exit(2); });
