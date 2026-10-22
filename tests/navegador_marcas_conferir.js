// CAMP-068 (20/10, operadora): "as marcações de problemas não somem ao corrigir, na etapa de conferir". No navegador de verdade (Playwright + Chromium).
// Lote com 4 folhas: D1 orientação incerta + espelhada pelo CAMP Vision + problema "orientação" que impede publicar; D2 autoria divergente SEM
// problema aberto; D3 bloqueada pelo CAMP Vision ("imagem cortada"); D4 normal. Prova, na tela de conferir:
//  - "Está certo" na D1: a etiqueta "orientação incerta" sai da linha na hora e o filtro "Com problema" baixa;
//  - D2: o aviso de autoria tem o botão "É de <fundo>" (antes só com problema aberto) e, clicado, a marca sai;
//  - D3: "Já resolvi" pede o que foi feito e tira a marca "bloqueada";
//  - recarregando, nada volta; na página do projeto a lista "Problemas que impedem publicar" não tem mais o da D1 e a miniatura
//    da D1 não mostra "orientação incerta" nem "espelhada?"; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/mc.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/mc.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8921)
//   CAMP_DB_PATH=/tmp/mc.db CAMP_BASE=http://127.0.0.1:8921 [CAMP_SHOTS=/pasta] node tests/navegador_marcas_conferir.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8921', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SHOTS = process.env.CAMP_SHOTS || '';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_marcas_ui'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0168', D = n => `${P}-1976-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 168)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',168,'Casa das Marcas',1976,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote marcas','${P}','/x/marcas','revisao')").lastrowid
for s in range(1, 5):
    cod = "${P}-1976-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (400, 300), "white"); ImageDraw.Draw(im).rectangle((60, 60, 340, 240), outline="black", width=6); ImageDraw.Draw(im).text((180, 140), "D%d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=90)
    pend = {"bloqueios": (["imagem cortada: falta a margem direita"] if s == 3 else []), "sinais": (["orientação incerta"] if s == 1 else []), "ressalvas": [], "previa": rel}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao,autoria_divergente,espelhado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Prancha %d" % s, 'Planta', "%02d/04" % s, 'campvision', lid, 'bloqueado' if s == 3 else 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente', 1 if s == 2 else 0, 1 if s == 1 else 0))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por) VALUES ('bloqueia','orientacao','campvision',?,'a folha está de lado','CAMP Vision')", ('${D(1)}',))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|Failed to load resource/.test(m.text())) erros.push('console.error: ' + m.text()); });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const tagsDe = c => pg.evaluate(c => { const r = document.querySelector(`#cf-linhas [data-cf-folha="${c}"]`); return r ? [...r.querySelectorAll('.cf-tags .tag')].map(t => t.textContent.trim()) : null; }, c);
  const comProblema = () => pg.evaluate(() => { const b = document.querySelector('#cf-filtros [data-cf-filtro="problema"] b'); return b ? +b.textContent : -1; });
  const aberta = () => pg.evaluate(() => { const s = document.querySelector('#cf-linhas .cf-linha.sel'); return s ? s.dataset.cfFolha : null; });
  const abre = async c => { await pg.click(`#cf-linhas [data-cf-folha="${c}"]`); return espera(async () => await aberta() === c && !!(await pg.$('#cf-pane [data-rev-item="corrigida"]'))); };
  const entrar = async () => { await pg.goto(BASE + '/#conferir/' + P + '/' + D(1)); await pg.reload(); return pg.waitForSelector('#cf-linhas .cf-linha', { timeout: 15000 }).then(() => true, () => false); };
  try {
    chk(await entrar(), 'abre a tela de conferir do lote');
    await espera(async () => await aberta() === D(1));
    const t0 = { 1: await tagsDe(D(1)), 2: await tagsDe(D(2)), 3: await tagsDe(D(3)) }, n0 = await comProblema();
    chk(t0[1].includes('orientação incerta') && t0[2].includes('autoria') && t0[3].includes('bloqueada') && n0 === 3, 'antes: as 3 folhas aparecem com a marca e "Com problema 3"', JSON.stringify([t0, n0]));
    // (1) "Está certo" na D1
    await pg.click('#cf-pane [data-rev-item="conferida"]');
    const saiu1 = await espera(async () => { const t = await tagsDe(D(1)); return t && !t.includes('orientação incerta') && await comProblema() === 2; });
    chk(saiu1, '"Está certo": a etiqueta "orientação incerta" sai da linha na hora e "Com problema" baixa para 2', JSON.stringify([await tagsDe(D(1)), await comProblema()]));
    // (2) autoria sem problema aberto
    await abre(D(2));
    const btA = await pg.$('#cf-pane [data-cf-autoria-ok]');
    chk(!!btA, 'D2 (autoria sem problema aberto): o aviso tem o botão "É de <fundo>"');
    if (btA) { await btA.click();
      chk(await espera(async () => !(await tagsDe(D(2))).includes('autoria') && !(await pg.$('#cf-pane [data-cf-aviso="autoria"]'))), 'clicado, a marca "autoria" sai da linha e o aviso some', JSON.stringify(await tagsDe(D(2)))); }
    // (3) bloqueio
    await abre(D(3));
    const btB = await pg.$('#cf-pane [data-cf-bloqueio-ok]');
    chk(!!btB && /imagem cortada/.test(await pg.textContent('#cf-pane [data-cf-aviso="bloqueio"]')), 'D3: o aviso "Bloqueada pelo CAMP Vision" diz o motivo e tem "Já resolvi"');
    if (btB) { await btB.click(); await pg.waitForSelector('#conf-ov #conf-motivo', { timeout: 5000 });
      chk(await pg.$eval('#conf-ov [data-conf="sim"]', b => b.disabled), '"Já resolvi" não deixa tirar sem dizer o que foi feito');
      await pg.fill('#conf-ov #conf-motivo', 'conferi: a imagem está inteira'); await pg.click('#conf-ov [data-conf="sim"]');
      chk(await espera(async () => !(await tagsDe(D(3))).includes('bloqueada') && !(await pg.$('#cf-pane [data-cf-aviso="bloqueio"]')) && await comProblema() === 0), 'tirado o bloqueio, a marca "bloqueada" sai e "Com problema" fica 0', JSON.stringify([await tagsDe(D(3)), await comProblema()])); }
    if (SHOTS) await pg.screenshot({ path: path.join(SHOTS, 'marcas_conferir.png') });
    // (4) recarregar: nada volta
    await entrar(); await espera(async () => await comProblema() >= 0);
    const t1 = [await tagsDe(D(1)), await tagsDe(D(2)), await tagsDe(D(3))];
    chk(await comProblema() === 0 && !t1.flat().some(x => /orientação incerta|autoria|bloqueada/.test(x)), 'recarregando, nenhuma das marcas resolvidas volta', JSON.stringify(t1));
    // (5) página do projeto
    await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
    await espera(() => pg.evaluate(() => !!(window.PJ_D && document.getElementById('pj-probs'))));
    const probs = await pg.evaluate(() => ((window.PJ_D || {}).erros || []).filter(e => e.gravidade === 'bloqueia' && ['aberto', 'em_correcao'].includes(e.situacao || 'aberto')).length);
    chk(probs === 0, 'página do projeto: o problema da D1 que impedia publicar não está mais aberto', String(probs));
    const mini = await pg.$eval(`.thumb[data-rev-abrir="${D(1)}"]`, t => t.textContent);
    chk(!/orientação incerta|espelhada\?/.test(mini), 'a miniatura da D1 não mostra "orientação incerta" nem "espelhada?"', mini.slice(0, 200));
    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } catch (e) { chk(false, 'o teste rodou até o fim', String(e).slice(0, 300)); }
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
