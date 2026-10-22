// Modo de conferir (#conferir/<projeto>[/<folha>]) no navegador de verdade (Playwright + Chromium). Pedido de 19/10 ("B e C são muito legais":
// C = lista das folhas à esquerda + a folha aberta à direita, com os avisos dela no alto e os campos e botões da revisão).
// Prova, num lote com 6 folhas (uma com autoria divergente, uma sem imagem, uma com orientação incerta, uma já conferida):
//  - a lista mostra as 6 folhas com a etiqueta certa e o progresso "1 de 6 conferidas"; a primeira a conferir já vem aberta;
//  - Enter marca a folha como conferida e abre a próxima, com a lista e o progresso atualizados no lugar (sem recarregar, sem "Sair sem salvar?");
//  - mudar um campo + "Salvar correção" grava (conferido pela API) e segue para a próxima sem perguntar nada;
//  - R gira a folha (giro gravado); "É de <arquiteto do fundo>" no aviso de autoria fecha o problema da folha;
//  - o filtro "Com problema" mostra só as folhas com aviso; com campo mudado, clicar em outra folha pergunta antes;
//  - o link direto #conferir/<projeto>/<folha> abre aquela folha e a URL acompanha a folha; Voltar volta ao projeto;
//  - a gaveta "Revisar folha" da página do projeto continua abrindo como antes;
//  - 390 px: a lista fica em cima da folha e não há rolagem para o lado; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/cf.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/cf.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8995)
//   CAMP_DB_PATH=/tmp/cf.db CAMP_BASE=http://127.0.0.1:8995 [CAMP_SHOTS=/pasta] node tests/navegador_conferir.js
const { execFileSync } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8995', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SHOTS = process.env.CAMP_SHOTS || '';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_conferir_ui'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0096', D = n => `${P}-1976-S01-D0000${n}`;
// D1 normal · D2 autoria divergente (com o problema aberto) · D3 sem imagem · D4 orientação incerta · D5 normal · D6 já conferida
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 96)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',96,'Residência Conferir',1976,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote conferir','${P}','/x/conferir','revisao')").lastrowid
for s in range(1, 7):
    cod = "${P}-1976-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    if s != 3:
        (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (400, 300), "white"); ImageDraw.Draw(im).rectangle((60, 60, 340, 240), outline="black", width=6); ImageDraw.Draw(im).text((180, 140), "D%d" % s, fill="black")
        im.save(raiz / rel, "JPEG", quality=90)
    pend = {"bloqueios": [], "sinais": (["orientação incerta"] if s == 4 else []), "ressalvas": [], "previa": (rel if s != 3 else "")}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao,autoria_divergente) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Prancha %d" % s, 'Planta' if s % 2 else 'Corte', "%02d/06" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'conferida' if s == 6 else 'pendente', 1 if s == 2 else 0))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por) VALUES ('corrigir','autoria_divergente','campvision',?,'carimbo de outro escritório','CAMP Vision')", ('${D(2)}',))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  async function pagina(vp) {
    const ctx = await br.newContext({ viewport: vp }); const pg = await ctx.newPage();
    pg.on('pageerror', e => erros.push(`${vp.width}px pageerror: ${e.message}`));
    pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|Failed to load resource/.test(m.text())) erros.push(`${vp.width}px console.error: ${m.text()}`); });
    await pg.addInitScript(() => { window._DIALOGOS = []; new MutationObserver(() => { const o = document.getElementById('conf-ov'); if (o && !o.dataset.visto) { o.dataset.visto = '1'; window._DIALOGOS.push((o.querySelector('h2') || {}).textContent || ''); } }).observe(document, { childList: true, subtree: true }); });
    await pg.goto(BASE + '/');
    await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
    return pg;
  }
  const pg = await pagina({ width: 1440, height: 900 });
  const item = c => pg.evaluate(c => fetch('/api/itens/' + encodeURIComponent(c)).then(r => r.ok ? r.json() : null).then(j => j && (j.item || j)), c);
  const aberta = () => pg.evaluate(() => { const s = document.querySelector('#cf-linhas .cf-linha.sel'); return s ? s.dataset.cfFolha : null; });
  const paneDe = () => pg.evaluate(() => (document.querySelector('#cf-pane > h2') || {}).textContent || '');
  const prog = () => pg.evaluate(() => (document.getElementById('cf-cont') || {}).textContent || '');
  const tagsDe = c => pg.evaluate(c => { const r = document.querySelector(`#cf-linhas [data-cf-folha="${c}"]`); return r ? [...r.querySelectorAll('.cf-tags .tag')].map(t => t.textContent.trim()) : null; }, c);
  const linhasVis = () => pg.evaluate(() => [...document.querySelectorAll('#cf-linhas .cf-linha')].map(x => x.dataset.cfFolha));
  const sairSemSalvar = async () => (await pg.evaluate(() => window._DIALOGOS.slice())).filter(t => /Sair sem salvar/.test(t)).length;
  const hash = () => pg.evaluate(() => location.hash);
  const abreu = async c => espera(async () => await aberta() === c && (await paneDe()).includes(c.split('-').pop()) && !!(await pg.$('#cf-pane [data-rev-item="corrigida"]')));

  // ---------- entra pela página do projeto (Voltar tem de voltar a ela) ----------
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
  // a gaveta "Revisar folha" da página do projeto continua igual
  await pg.click(`.thumb[data-rev-abrir="${D(1)}"]`);
  const gaveta = await espera(() => pg.evaluate(c => document.getElementById('d-title').textContent === 'Revisar folha' && document.getElementById('d-sub').textContent === c && !!document.querySelector('#d-body [data-rev-item="conferida"]') && !!document.querySelector('#d-body .rev-prog'), D(1)));
  chk(gaveta, 'a gaveta "Revisar folha" da página do projeto continua abrindo (com "Folha N de M")');
  await pg.evaluate(() => closeDrawer(true));

  await pg.evaluate(p => nav('conferir/' + p), P);
  const abriu = await pg.waitForSelector('#cf-linhas .cf-linha', { timeout: 10000 }).then(() => true, () => false);
  chk(abriu, 'a rota #conferir/<projeto> abre a tela de conferir');
  if (!abriu) { await fim(); return; }
  await abreu(D(1));
  chk(JSON.stringify(await linhasVis()) === JSON.stringify([1, 2, 3, 4, 5, 6].map(D)), 'a lista mostra as 6 folhas do lote, na ordem', JSON.stringify(await linhasVis()));
  const t = {}; for (const n of [1, 2, 3, 4, 6]) t[n] = await tagsDe(D(n));
  chk(t[1] && t[1].join('|') === 'a conferir', 'D00001: etiqueta "a conferir"', JSON.stringify(t[1]));
  chk(t[2] && t[2].includes('autoria') && t[2].includes('a conferir'), 'D00002: etiqueta "autoria"', JSON.stringify(t[2]));
  chk(t[3] && t[3].includes('sem imagem'), 'D00003: etiqueta "sem imagem"', JSON.stringify(t[3]));
  chk(t[4] && t[4].includes('orientação incerta'), 'D00004: etiqueta "orientação incerta"', JSON.stringify(t[4]));
  chk(t[6] && t[6].join('|') === 'conferida', 'D00006: etiqueta "conferida"', JSON.stringify(t[6]));
  chk(await prog() === '1 de 6 conferidas', 'progresso "1 de 6 conferidas"', await prog());
  chk(await aberta() === D(1) && /D00001/.test(await paneDe()), 'a primeira folha a conferir (D00001) já vem aberta e marcada na lista', await aberta());
  chk(await hash() === '#conferir/' + P + '/' + D(1), 'a URL acompanha a folha aberta', await hash());
  chk(!!(await pg.$('#cf-pane a#rv-img-link[target="_blank"] img#rv-img')), 'a imagem grande abre sozinha numa aba nova ao clicar (link target=_blank)');
  chk(!(await pg.evaluate(() => mainEl.classList.contains('with-drawer'))), 'a folha abre no painel da direita, não na gaveta');

  // ---------- Enter: conferida e próxima ----------
  await pg.focus('#cf-pane'); await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur());
  await pg.keyboard.press('Enter');
  const foi2 = await abreu(D(2));
  chk((await item(D(1))).revisao === 'conferida', 'Enter marca D00001 como conferida (API)', (await item(D(1))).revisao);
  chk(foi2, 'Enter abre a próxima folha (D00002) no painel da direita', await aberta());
  chk(await prog() === '2 de 6 conferidas' && (await tagsDe(D(1))).join('|') === 'conferida', 'a lista e o progresso se atualizam no lugar ("2 de 6", D00001 "conferida")', `${await prog()} ${JSON.stringify(await tagsDe(D(1)))}`);
  chk(await hash() === '#conferir/' + P + '/' + D(2), 'a URL passa para a folha D00002', await hash());
  // aviso de autoria no alto, com a ação
  const avisoAut = await pg.$eval('#cf-pane .cf-avisos', e => e.textContent).catch(() => '');
  chk(/Autoria/.test(avisoAut) && !!(await pg.$(`#cf-pane [data-cf-autoria-ok="${D(2)}"]`)), 'D00002: o aviso de autoria aparece no alto, com "É de <arquiteto do fundo>"', avisoAut);

  // ---------- Salvar correção ----------
  await pg.fill('#rv-titulo', 'Prancha 2 corrigida');
  await pg.click(`#cf-pane [data-rev-item="corrigida"][data-codigo="${D(2)}"]`);
  const foi3 = await abreu(D(3));
  const i2 = await item(D(2));
  chk(i2.titulo === 'Prancha 2 corrigida' && i2.revisao === 'corrigida', '"Salvar correção" grava o título e marca a folha como corrigida (API)', JSON.stringify([i2.titulo, i2.revisao]));
  chk(foi3, 'depois de salvar, abre a próxima (D00003)', await aberta());
  chk(await sairSemSalvar() === 0, 'nenhuma pergunta "Sair sem salvar?" ao seguir para a próxima');
  chk(!!(await pg.$('#cf-pane .sem-imagem')), 'D00003 sem imagem: o painel diz que não há imagem');
  // ---------- seta para baixo: próxima da lista ----------
  await pg.keyboard.press('ArrowDown');
  chk(await abreu(D(4)), '↓ abre a folha seguinte da lista (D00004)', await aberta());
  chk(/Orientação incerta/.test(await pg.$eval('#cf-pane .cf-avisos', e => e.textContent).catch(() => '')), 'D00004: o aviso de orientação incerta aparece no alto, com os botões de girar');
  // ---------- R: girar ----------
  await pg.keyboard.press('r');
  const girou = await espera(async () => +(await item(D(4))).giro_manual === 90);
  chk(girou, 'R gira a folha D00004 (giro gravado: 90°)', String((await item(D(4))).giro_manual));
  chk(await espera(() => pg.evaluate(() => /[?&]g=90/.test((document.getElementById('rv-img') || {}).src || ''))), 'a imagem grande passa a ser a girada');
  // ---------- campo mudado + clicar em outra folha: pergunta ----------
  await pg.fill('#rv-escala', '1:50'); await pg.click(`#cf-linhas [data-cf-folha="${D(5)}"]`);
  const perguntou = await pg.waitForSelector('#conf-ov [data-conf="nao"]', { timeout: 4000 }).then(() => true, () => false);
  chk(perguntou && await sairSemSalvar() === 1, 'com campo mudado, clicar em outra folha pergunta "Sair sem salvar?"');
  if (perguntou) { await pg.click('#conf-ov [data-conf="nao"]'); await pg.waitForSelector('#conf-ov', { state: 'detached' }).catch(() => {}); }
  chk(await aberta() === D(4) && await pg.inputValue('#rv-escala') === '1:50', '"Continuar editando" fica na mesma folha com o que foi digitado');
  await pg.fill('#rv-escala', ''); await pg.evaluate(() => { document.getElementById('rv-escala').blur(); limparAlteracoes('conferir'); });   // desfeito à mão: o "change" do blur não pode contar depois
  // ---------- filtro "Com problema" ----------
  await pg.click('#cf-filtros [data-cf-filtro="problema"]');
  const vis = await linhasVis();
  chk(JSON.stringify(vis) === JSON.stringify([D(2), D(4)]), 'filtro "Com problema": só D00002 (autoria) e D00004 (orientação incerta)', JSON.stringify(vis));
  await pg.click('#cf-filtros [data-cf-filtro="sem_imagem"]');
  chk(JSON.stringify(await linhasVis()) === JSON.stringify([D(3), D(4)]), 'filtro "Sem imagem": D00003 (e a folha aberta continua na lista)', JSON.stringify(await linhasVis()));
  await pg.click('#cf-filtros [data-cf-filtro="a_conferir"]');
  chk(JSON.stringify(await linhasVis()) === JSON.stringify([D(3), D(4), D(5)]), 'filtro "A conferir": D00003, D00004, D00005', JSON.stringify(await linhasVis()));
  await pg.click('#cf-filtros [data-cf-filtro="todas"]');
  // ---------- autoria: "É de <arquiteto>" fecha o problema da folha ----------
  await pg.click(`#cf-linhas [data-cf-folha="${D(2)}"]`); await abreu(D(2));
  await pg.click(`#cf-pane [data-cf-autoria-ok="${D(2)}"]`);
  const autOk = await espera(async () => (await item(D(2))).autoria_divergente === 0 && !(await pg.$('#cf-pane [data-cf-aviso="autoria"]')));
  chk(autOk && !(await tagsDe(D(2))).includes('autoria'), '"É de <arquiteto do fundo>" tira o aviso de autoria da folha (API, aviso e etiqueta)', JSON.stringify(await tagsDe(D(2))));
  // ---------- Voltar volta ao projeto ----------
  await pg.goBack();
  const voltou = await espera(async () => await hash() === '#projeto/' + P && await pg.evaluate(() => document.getElementById('v-projeto').classList.contains('on')));
  chk(voltou, 'Voltar (do navegador) volta à página do projeto', await hash());
  // ---------- link direto ----------
  await pg.goto(BASE + '/#conferir/' + P + '/' + D(5)); await pg.reload();
  chk(await pg.waitForSelector('#cf-linhas .cf-linha', { timeout: 10000 }).then(() => abreu(D(5)), () => false), 'o link direto #conferir/<projeto>/<folha> abre aquela folha (D00005)', await aberta());
  chk(await prog() === '3 de 6 conferidas', 'progresso depois de recarregar: "3 de 6 conferidas"', await prog());
  await pg.keyboard.press('ArrowUp');
  chk(await abreu(D(4)) && await hash() === '#conferir/' + P + '/' + D(4), '↑ volta uma folha e a URL acompanha', await hash());
  // ---------- última: Enter em todas as que faltam ----------
  for (const n of [3, 4, 5]) { if (await aberta() !== D(n)) { await pg.click(`#cf-linhas [data-cf-folha="${D(n)}"]`); await abreu(D(n)); }
    const b = `#cf-pane [data-rev-item="conferida"][data-codigo="${D(n)}"]`; await pg.click(b);
    if (n === 3) { await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 4000 }).then(() => pg.click('#conf-ov [data-conf="sim"]'), () => {}); }   // sem imagem: confirma
    await espera(async () => (await item(D(n))).revisao === 'conferida'); }
  const acabou = await espera(async () => /Era a última/.test(await pg.evaluate(() => (document.getElementById('cf-pane') || {}).textContent || '')));
  chk(acabou && await prog() === '6 de 6 conferidas', 'na última, o painel diz "Era a última" e o progresso fica "6 de 6"', await prog());
  chk(await sairSemSalvar() === 0, 'conferindo até a última pelo link direto: nenhuma pergunta "Sair sem salvar?"', String(await sairSemSalvar()));
  if (SHOTS) { await pg.click(`#cf-linhas [data-cf-folha="${D(2)}"]`); await abreu(D(2)); const ok = await pg.$('[data-ajuda-fechar="conferir"]'); if (ok) await ok.click();
    await pg.waitForTimeout(400); await pg.evaluate(() => mainEl.scrollTo(0, 0)); await pg.screenshot({ path: path.join(SHOTS, 'conferir_1440.png') }); }

  // ---------- 390 px ----------
  const m = await pagina({ width: 390, height: 844 });
  await m.goto(BASE + '/#conferir/' + P + '/' + D(4)); await m.reload();
  await m.waitForSelector('#cf-pane [data-rev-item]', { timeout: 10000 }).catch(() => {});
  await m.waitForTimeout(600);
  const lado = await m.evaluate(() => ({ doc: document.documentElement.scrollWidth, main: document.querySelector('.main').scrollWidth, vw: innerWidth }));
  chk(lado.doc <= lado.vw && lado.main <= lado.vw, '390 px: sem rolagem para o lado', JSON.stringify(lado));
  const emCima = await m.evaluate(() => { const a = document.querySelector('.cf-lista').getBoundingClientRect(), b = document.getElementById('cf-pane').getBoundingClientRect(); return a.bottom <= b.top + 1; });
  chk(emCima, '390 px: a lista fica em cima da folha aberta');
  if (SHOTS) { await m.setViewportSize({ width: 390, height: 2600 }); await m.waitForTimeout(400); await m.evaluate(() => mainEl.scrollTo(0, 0)); await m.screenshot({ path: path.join(SHOTS, 'conferir_390.png') }); }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await fim();
  async function fim() { await br.close(); console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0); }
})().catch(e => { console.log(linhas.join('\n')); console.error(e); process.exit(1); });
