// UX-66 no navegador de verdade (Playwright + Chromium): girar a folha com UM clique, sem rolar, na conferência.
// Antes: na gaveta "Revisar folha" os botões de virar ficavam embaixo da imagem (a 1366×768 só rolando), e o "? mostra todos os
// atalhos" parecia link mas era texto: clicar não fazia nada.
// Prova, a 1366×768, num lote de 3 folhas:
//  - gaveta (clique na miniatura), tela cheia (UX-10, "Começar a conferir") e tela de conferir (#conferir/…): "Girar 90°" e
//    "Girar 180°" estão inteiros DENTRO da janela sem rolar nada;
//  - "Girar 90°" grava 90 (a mesma rota do atalho R: POST /api/itens/{c}/girar) e a imagem troca; "Girar 180°" soma 180 (90 → 270);
//  - o "?" é um botão: clicar abre "Atalhos da conferência";
//  - a tecla R continua girando (mesma rotina);  nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux66/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux66/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8973)
//   CAMP_DB_PATH=/tmp/ux66/t.db CAMP_BASE=http://127.0.0.1:8973 node tests/navegador_ux66_girar.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8973', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || path.dirname(DB || '/tmp/x');
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_ux66'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0166', D = n => `${P}-1975-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 166)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente) VALUES ('${P}','F026',166,'Casa Girar',1975,'Santos','SP','Cliente X')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote girar','${P}','/x/g66','revisao')").lastrowid
for s in range(1, 4):
    cod = "${P}-1975-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1400, 2000), "white"); dr = ImageDraw.Draw(im); dr.rectangle((60, 60, 1340, 1940), outline="black", width=12); dr.text((680, 300), "TOPO D%d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=80)
    sinais = ["orientação incerta"] if s == 2 else []
    ress = ["valor descartado: resposta do modelo quebrada (%s)" % c for c in ("titulo", "escala", "folha", "data")] if s == 1 else []
    pend = {"bloqueios": [], "sinais": sinais, "ressalvas": ress, "previa": rel, "titulo_lido": "Planta %d" % s}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Planta %d" % s, 'Planta', "%02d/03" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente'))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
const giro = n => +py(`print(con.execute("SELECT COALESCE(giro_manual,0) FROM item WHERE codigo=?", ("${D(n)}",)).fetchone()[0])`);
const zerar = () => py(`con.execute("UPDATE item SET giro_manual=0 WHERE projeto_codigo='${P}'")`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };

// os dois botões estão inteiros dentro da janela, sem rolar (nenhum contêiner rolado)
async function visiveisSemRolar(pg, host) {
  return pg.evaluate(host => {
    const h = document.querySelector(host); if (!h) return { erro: 'sem ' + host };
    const rolado = (host === '#cf-pane' ? [document.scrollingElement, document.getElementById('cf-pane')] : [document.getElementById('drawer'), document.getElementById('d-body')]).filter(Boolean).some(e => e.scrollTop > 0);
    const r = sel => { const b = h.querySelector(sel); if (!b) return null; const q = b.getBoundingClientRect(), cs = getComputedStyle(b);
      const topo = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2);
      return { t: Math.round(q.top), b: Math.round(q.bottom), l: Math.round(q.left), r: Math.round(q.right), vis: cs.visibility !== 'hidden' && cs.display !== 'none' && q.width > 0, naFrente: !!topo && (topo === b || b.contains(topo)), txt: b.textContent.trim() }; };
    return { rolado, g90: r('[data-rev-girar-rapido="90"]'), g180: r('[data-rev-girar-rapido="180"]'), ajuda: r('[data-rev-atalhos]'), vw: innerWidth, vh: innerHeight };
  }, host);
}
const dentro = (x, v) => !!x && x.vis && x.naFrente && x.t >= 0 && x.b <= v.vh && x.l >= 0 && x.r <= v.vw;

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => { try { localStorage.setItem('camp.revCheia', '0') } catch (_) {} });
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const sub = () => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent || '');
  const abriu = c => espera(async () => (await sub()) === c && !!(await pg.$('#d-body [data-rev-item="conferida"]')));
  const clicar = async sel => { const ok = await pg.waitForSelector(sel, { timeout: 2000 }).then(() => true, () => false); if (ok) await pg.click(sel); else chk(false, 'existe ' + sel); };
  const img = () => pg.evaluate(() => (document.getElementById('rv-img') || {}).getAttribute && document.getElementById('rv-img').getAttribute('src'));
  try {
    // ---------- gaveta (clique na miniatura) ----------
    await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
    await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });
    await pg.click(`.thumb[data-rev-abrir="${D(1)}"]`);
    chk(await abriu(D(1)), 'a gaveta "Revisar folha" abre na D1', await sub());
    await pg.waitForTimeout(500);
    let g = await visiveisSemRolar(pg, '#d-body');
    await pg.screenshot({ path: PRINTS + '/ux66_gaveta_1366.png' });
    chk(dentro(g.g90, g) && dentro(g.g180, g) && !g.rolado, 'gaveta 1366×768: "Girar 90°" e "Girar 180°" visíveis sem rolar', JSON.stringify(g));
    chk(g.g90 && /Girar 90°/.test(g.g90.txt) && g.g180 && /Girar 180°/.test(g.g180.txt), 'os botões dizem "Girar 90°" e "Girar 180°"', JSON.stringify([g.g90, g.g180]));
    const src0 = await img();
    await clicar('#d-body [data-rev-girar-rapido="90"]');
    chk(await espera(async () => giro(1) === 90), '"Girar 90°" (um clique) grava o giro de 90° (mesma rota do atalho R)', String(giro(1)));
    chk(await espera(async () => (await img()) !== src0), 'a imagem troca depois de girar');
    await clicar('#d-body [data-rev-girar-rapido="180"]');
    chk(await espera(async () => giro(1) === 270), '"Girar 180°" soma 180° (90 → 270)', String(giro(1)));
    // tela mais baixa (a barra natural ficaria abaixo da dobra): a barra gruda no pé da janela; rolando até os campos, gruda no alto
    await pg.setViewportSize({ width: 1366, height: 600 }); await pg.waitForTimeout(300);
    g = await visiveisSemRolar(pg, '#d-body');
    await pg.screenshot({ path: PRINTS + '/ux66_gaveta_1366x600.png' });
    chk(dentro(g.g90, g) && dentro(g.g180, g) && !g.rolado, 'gaveta 1366×600: os botões de girar continuam à vista (grudados no pé)', JSON.stringify(g));
    await pg.evaluate(() => { const d = document.getElementById('drawer'); d.scrollTop = d.scrollHeight });
    await pg.waitForTimeout(200);
    g = await visiveisSemRolar(pg, '#d-body');
    chk(dentro(g.g90, g) && dentro(g.g180, g), 'gaveta rolada até o fim: os botões de girar continuam à vista (grudados no alto)', JSON.stringify(g));
    await pg.evaluate(() => { document.getElementById('drawer').scrollTop = 0 });
    await pg.setViewportSize({ width: 1366, height: 768 }); await pg.waitForTimeout(300);
    // "?" é botão e abre a lista de atalhos
    g = await visiveisSemRolar(pg, '#d-body');
    chk(dentro(g.ajuda, g), 'o "?" dos atalhos está à vista', JSON.stringify(g.ajuda));
    await clicar('#d-body [data-rev-atalhos]');
    chk(await espera(() => pg.evaluate(() => /Atalhos da conferência/.test((document.getElementById('conf-ov') || {}).innerText || ''))), 'clicar no "?" abre "Atalhos da conferência"');
    await pg.click('#conf-ov button:has-text("Fechar")').catch(() => {}); await pg.waitForTimeout(200);
    // R continua girando
    zerar(); await pg.evaluate(() => { const b = document.getElementById('d-body'); b.focus() });
    await pg.keyboard.press('r');
    chk(await espera(async () => giro(1) === 90), 'a tecla R continua girando (mesma rotina)', String(giro(1)));
    await pg.evaluate(() => closeDrawer(true));

    // ---------- tela cheia (UX-10) ----------
    zerar();
    await pg.evaluate(() => { try { localStorage.setItem('camp.revCheia', '1') } catch (_) {} });
    await pg.reload(); await pg.waitForSelector('#pj-proximo [data-pp="conferir"]', { timeout: 15000 });
    await pg.click('#pj-proximo [data-pp="conferir"]');
    chk(await abriu(D(1)), '"Começar a conferir" abre a D1 em tela cheia', await sub());
    chk(await pg.evaluate(() => document.querySelector('.main').classList.contains('rev-cheia')), 'está em tela cheia');
    await pg.waitForTimeout(500);
    g = await visiveisSemRolar(pg, '#d-body');
    await pg.screenshot({ path: PRINTS + '/ux66_cheia_1366.png' });
    chk(dentro(g.g90, g) && dentro(g.g180, g) && !g.rolado, 'tela cheia 1366×768: "Girar 90°" e "Girar 180°" visíveis sem rolar', JSON.stringify(g));
    await clicar('#d-body [data-rev-girar-rapido="180"]');
    chk(await espera(async () => giro(1) === 180), 'tela cheia: "Girar 180°" grava 180', String(giro(1)));
    await pg.evaluate(() => closeDrawer(true));

    // ---------- tela de conferir (#conferir/…) ----------
    zerar();
    await pg.goto(BASE + '/#conferir/' + P + '/' + D(2)); await pg.reload();
    await pg.waitForSelector('#cf-pane [data-rev-item="conferida"]', { timeout: 15000 }); await pg.waitForTimeout(500);
    g = await visiveisSemRolar(pg, '#cf-pane');
    await pg.screenshot({ path: PRINTS + '/ux66_conferir_1366.png' });
    chk(dentro(g.g90, g) && dentro(g.g180, g) && !g.rolado, 'tela de conferir 1366×768: "Girar 90°" e "Girar 180°" visíveis sem rolar', JSON.stringify(g));
    await clicar('#cf-pane [data-rev-girar-rapido="90"]');
    chk(await espera(async () => giro(2) === 90), 'tela de conferir: "Girar 90°" grava 90', String(giro(2)));
    await clicar('#cf-pane [data-rev-atalhos]');
    chk(await espera(() => pg.evaluate(() => /Atalhos da conferência/.test((document.getElementById('conf-ov') || {}).innerText || ''))), 'tela de conferir: o "?" abre os atalhos');
    await pg.keyboard.press('Escape');

    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } finally { await br.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
