// UX-71 no navegador de verdade (Playwright + Chromium): a conferência sem rolagem para o lado e com avisos legíveis.
// Antes: em "Revisar folha" com ~1570 px de largura aparecia barra de rolagem horizontal e os avisos da coluna direita ficavam
// cortados (ex.: "resposta do modelo quebrada (codigo_unidade" sem fim): a etiqueta (.tag) não quebra linha (white-space:nowrap)
// e "valor descartado: resposta do modelo quebrada (campo)" vinha uma vez por campo (16 etiquetas).
// Prova, numa folha com 16 campos descartados + uma ressalva longa sem espaço + um sinal longo, em 1570, 1366 e 390 px,
// na gaveta, na tela cheia (UX-10) e na tela de conferir:
//  - nenhuma rolagem horizontal (página, gaveta e coluna da direita);
//  - nenhuma etiqueta de aviso passa da borda da coluna (o texto quebra linha);
//  - os 16 "valor descartado: resposta do modelo quebrada" viram UM aviso com a lista dos campos (todos os 16 nomes à vista);
//  - nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux71/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux71/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8973)
//   CAMP_DB_PATH=/tmp/ux71/t.db CAMP_BASE=http://127.0.0.1:8973 node tests/navegador_ux71_avisos.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8973', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || path.dirname(DB || '/tmp/x');
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_ux71'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0171', D = n => `${P}-1979-S01-D0000${n}`;
const CAMPOS = ['titulo', 'escala', 'folha', 'data', 'arquiteto', 'cidade', 'cliente', 'endereco', 'tipo_documento', 'codigo_unidade', 'disciplina', 'desenhista', 'calculista', 'aprovacao', 'revisao', 'observacoes'];
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 171)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente) VALUES ('${P}','F026',171,'Edifício Avisos',1979,'São Paulo','SP','Cliente Y')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote avisos','${P}','/x/a71','revisao')").lastrowid
campos = ${JSON.stringify(CAMPOS)}
for s in range(1, 3):
    cod = "${P}-1979-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (2000, 1300), "white"); dr = ImageDraw.Draw(im); dr.rectangle((60, 60, 1940, 1240), outline="black", width=12)
    im.save(raiz / rel, "JPEG", quality=80)
    ress = ["valor descartado: resposta do modelo quebrada (%s)" % c for c in campos] + ["valor descartado: resposta do modelo quebrada (titulo_prancha, resto de marcação tirado)",
            "conferir_na_folha_de_contatos_porque_o_carimbo_estava_ilegivel_e_o_modelo_nao_conseguiu_ler_nenhum_dos_campos_principais_da_prancha"] if s == 1 else []
    sinais = ["resposta do modelo quebrada: 16 campo(s) sem leitura mesmo depois de nova tentativa (arquiteto, cidade, cliente, endereco, tipo_documento, codigo_unidade) — preencher na revisão"] if s == 1 else []
    pend = {"bloqueios": [], "sinais": sinais, "ressalvas": ress, "previa": rel, "titulo_lido": "Planta %d" % s}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Planta %d" % s, 'Planta', "%02d/02" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente'))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };

async function medir(pg, host) {
  return pg.evaluate(({ host, CAMPOS }) => {
    const h = document.querySelector(host); if (!h) return { erro: 'sem ' + host };
    const lado = e => e ? e.scrollWidth - e.clientWidth : 0;
    const col = h.querySelector('.rev-col-dados'), chips = h.querySelector('#rv-chips');
    const cr = (col || h).getBoundingClientRect();
    const tags = chips ? [...chips.querySelectorAll('.tag, .rev-aviso-grupo')] : [];
    const fora = tags.filter(t => { const r = t.getBoundingClientRect(); return r.right > cr.right + 1 || r.left < cr.left - 1 || t.scrollWidth > t.clientWidth + 1; }).map(t => t.textContent.slice(0, 60));
    const txt = chips ? chips.innerText : '';
    const nDesc = (txt.match(/valor descartado: resposta do modelo quebrada/g) || []).length;
    const faltam = CAMPOS.filter(c => !txt.includes(c));
    return { pagina: lado(document.scrollingElement), gaveta: lado(document.getElementById('drawer')), corpo: lado(document.getElementById('d-body')), pane: lado(document.getElementById('cf-pane')), coluna: lado(col),
      larguraJanela: innerWidth, docLarg: document.documentElement.scrollWidth, fora, nDesc, faltam, nTags: tags.length };
  }, { host, CAMPOS });
}
function avaliar(rot, m) {
  chk(m.pagina <= 0 && m.gaveta <= 0 && m.corpo <= 0 && m.pane <= 0 && m.coluna <= 0 && m.docLarg <= m.larguraJanela, `${rot}: sem rolagem horizontal`, JSON.stringify(m));
  chk(!m.fora.length, `${rot}: nenhum aviso cortado (quebra linha dentro da coluna)`, JSON.stringify(m.fora));
  chk(m.nDesc === 1, `${rot}: os campos descartados viram UM aviso (eram ${CAMPOS.length + 1})`, `${m.nDesc} avisos`);
  chk(!m.faltam.length, `${rot}: o aviso único lista todos os campos`, 'faltam ' + m.faltam.join(', '));
}

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1570, height: 900 }, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const sub = () => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent || '');
  const abriu = c => espera(async () => (await sub()) === c && !!(await pg.$('#d-body [data-rev-item="conferida"]')));
  try {
    for (const [w, h] of [[1570, 900], [1366, 768], [390, 844]]) {
      await pg.setViewportSize({ width: w, height: h });
      // gaveta
      await pg.evaluate(() => { try { localStorage.setItem('camp.revCheia', '0') } catch (_) {} });
      await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
      await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
      await pg.click(`.thumb[data-rev-abrir="${D(1)}"]`);
      chk(await abriu(D(1)), `${w}px: a gaveta abre na D1`);
      await pg.waitForTimeout(600);
      await pg.evaluate(() => { const c = document.getElementById('rv-chips'); if (c) c.scrollIntoView({ block: 'center' }) });
      await pg.screenshot({ path: `${PRINTS}/ux71_gaveta_${w}.png` });
      avaliar(`${w}px gaveta`, await medir(pg, '#d-body'));
      await pg.evaluate(() => closeDrawer(true));
      // tela cheia
      await pg.evaluate(() => { try { localStorage.setItem('camp.revCheia', '1') } catch (_) {} });
      await pg.reload(); await pg.waitForSelector('#pj-proximo [data-pp="conferir"]', { timeout: 15000 });
      await pg.click('#pj-proximo [data-pp="conferir"]');
      chk(await abriu(D(1)), `${w}px: "Começar a conferir" abre a D1 em tela cheia`);
      await pg.waitForTimeout(600);
      await pg.screenshot({ path: `${PRINTS}/ux71_cheia_${w}.png` });
      avaliar(`${w}px tela cheia`, await medir(pg, '#d-body'));
      await pg.evaluate(() => closeDrawer(true));
      // tela de conferir
      await pg.goto(BASE + '/#conferir/' + P + '/' + D(1)); await pg.reload();
      await pg.waitForSelector('#cf-pane #rv-chips', { timeout: 15000 }); await pg.waitForTimeout(600);
      await pg.evaluate(() => { const c = document.getElementById('rv-chips'); if (c) c.scrollIntoView({ block: 'center' }) });
      await pg.screenshot({ path: `${PRINTS}/ux71_conferir_${w}.png` });
      avaliar(`${w}px tela de conferir`, await medir(pg, '#cf-pane'));
    }
    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } finally { await br.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
