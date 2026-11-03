// UX-59 (parte do painel) no navegador de verdade (Playwright + Chromium): folha com "orientação incerta" e giro sugerido pelo CAMP Vision
// (pendencias.rotacao_sugerida, campo OPCIONAL que o CAMP Vision ainda não manda) aparece JÁ de pé na conferência, sem gravar nada.
// Antes: a folha chegava de cabeça para baixo (ex.: F001-P0033 D00001) e só dizia "orientação incerta"; quem conferia tinha de achar o giro.
// Prova, a 1366×768, num lote de 4 folhas (prévia retrato 1000×1600 com uma faixa preta no PÉ = de cabeça para baixo):
//  - D1 (incerta, sugestão 180): a imagem vem de /previa?…&s=180 (a faixa preta aparece no ALTO), aviso "orientação incerta — confira",
//    e NADA foi gravado (giro_manual = 0);  "Gravar este giro" grava 180 e o aviso sai;
//  - D2 (incerta, sugestão 180): "Está certo" grava o giro junto (é o que a pessoa conferiu): conferida e giro 180;
//  - D3 (incerta, sugestão 90): "Ver como chegou" volta à imagem original (sem s=) e nada é gravado; "Girar 90°" com a sugestão
//    90 na tela grava 180 (o giro conta a partir do que a pessoa vê);
//  - D4 (incerta, SEM sugestão): nada muda (imagem sem s=, sem o aviso novo);  nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux59/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux59/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8973)
//   CAMP_DB_PATH=/tmp/ux59/t.db CAMP_BASE=http://127.0.0.1:8973 node tests/navegador_ux59_orientacao.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8973', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || path.dirname(DB || '/tmp/x');
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_ux59'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F001-P0133', D = n => `${P}-1979-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F001','Fundo Um','FUM',1)")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F001', 133)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente) VALUES ('${P}','F001',133,'Casa de Cabeça',1979,'Santos','SP','Cliente Z')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote orientação','${P}','/x/o59','revisao')").lastrowid
sug = {1: 180, 2: 180, 3: 90, 4: None}
for s in range(1, 5):
    cod = "${P}-1979-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1000, 1600), "white"); dr = ImageDraw.Draw(im); dr.rectangle((0, 1400, 999, 1599), fill="black")   # o carimbo (faixa preta) no PÉ: de cabeça para baixo
    im.save(raiz / rel, "JPEG", quality=85)
    pend = {"bloqueios": [], "sinais": ["orientação incerta"], "ressalvas": [], "previa": rel, "titulo_lido": "Planta %d" % s}
    if sug[s]: pend["rotacao_sugerida"] = sug[s]
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Planta %d" % s, 'Planta', "%02d/04" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente'))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
const item = n => JSON.parse(py(`r = con.execute("SELECT COALESCE(giro_manual,0), revisao FROM item WHERE codigo=?", ("${D(n)}",)).fetchone(); print(json.dumps(list(r)))`));
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };

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
  const abrir = async n => { await pg.evaluate(c => { closeDrawer(true); abrirRevisaoItem(c) }, D(n)); return espera(async () => (await sub()) === D(n) && !!(await pg.$('#d-body [data-rev-item="conferida"]'))); };
  const clicar = async sel => { const ok = await pg.waitForSelector(sel, { timeout: 3000 }).then(() => true, () => false); if (ok) await pg.click(sel); else chk(false, 'existe ' + sel); };
  // a imagem na tela: src e se a faixa preta (carimbo) está no alto (de pé) ou no pé (de cabeça para baixo)
  const imagem = () => pg.evaluate(async () => { const im = document.getElementById('rv-img'); if (!im) return null;
    await new Promise(r => { if (im.complete && im.naturalWidth) r(); else { im.onload = r; im.onerror = r; setTimeout(r, 4000) } });
    const cv = document.createElement('canvas'); cv.width = im.naturalWidth; cv.height = im.naturalHeight; const x = cv.getContext('2d'); x.drawImage(im, 0, 0);
    const lum = y => { const d = x.getImageData(Math.floor(cv.width / 2), Math.floor(y), 1, 1).data; return d[0] + d[1] + d[2]; };
    return { src: im.getAttribute('src'), w: im.naturalWidth, h: im.naturalHeight, altoPreto: lum(cv.height * 0.03) < 100, pePreto: lum(cv.height * 0.97) < 100 }; });
  const aviso = () => pg.evaluate(() => { const a = document.querySelector('#d-body [data-rev-sug]'); return a ? a.innerText : ''; });
  try {
    await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
    await pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 });

    // ---------- D1: sugestão 180 → de pé na tela, nada gravado; "Gravar este giro" grava ----------
    chk(await abrir(1), 'a D1 abre na gaveta');
    let im = await imagem();
    await pg.evaluate(() => { const a = document.querySelector('#d-body [data-rev-sug]'); if (a) a.scrollIntoView({ block: 'start' }) }); await pg.waitForTimeout(200);
    await pg.screenshot({ path: PRINTS + '/ux59_sugerida_1366.png' });
    await pg.evaluate(() => { document.getElementById('drawer').scrollTop = 0 });
    chk(im && /[?&]s=180\b/.test(im.src), 'D1: a prévia pedida já com o giro sugerido (s=180)', JSON.stringify(im));
    chk(im && im.altoPreto && !im.pePreto, 'D1: a folha aparece de pé (o carimbo no alto)', JSON.stringify(im));
    const av1 = await aviso();
    chk(/orientação incerta — confira/.test(av1) && /Nada foi gravado/.test(av1), 'D1: aviso "orientação incerta — confira" e "Nada foi gravado"', av1);
    chk(item(1)[0] === 0, 'D1: abrir a folha NÃO grava giro nenhum', JSON.stringify(item(1)));
    await clicar('#d-body [data-rev-sug-aceitar]');
    chk(await espera(async () => item(1)[0] === 180), '"Gravar este giro" grava 180', JSON.stringify(item(1)));
    chk(await espera(async () => !(await aviso())), 'D1: depois de gravar, o aviso da sugestão sai');
    im = await imagem();
    chk(im && !/[?&]s=/.test(im.src) && /g=180/.test(im.src) && im.altoPreto, 'D1: a imagem agora é a gravada (g=180, sem s=) e continua de pé', JSON.stringify(im));

    // ---------- D2: "Está certo" com a sugestão na tela grava o giro junto ----------
    chk(await abrir(2), 'a D2 abre');
    chk(/orientação incerta — confira/.test(await aviso()), 'D2: aviso da sugestão');
    await clicar('#d-body [data-rev-item="conferida"]');
    chk(await espera(async () => { const x = item(2); return x[0] === 180 && x[1] === 'conferida'; }), 'D2: "Está certo" grava o giro sugerido junto e confere', JSON.stringify(item(2)));

    // ---------- D3: "Ver como chegou" e girar a partir do que está na tela ----------
    chk(await abrir(3), 'a D3 abre');
    im = await imagem();
    chk(im && /[?&]s=90\b/.test(im.src) && im.w > im.h, 'D3: sugestão 90 (a prévia vem deitada, girada 90°)', JSON.stringify(im));
    await clicar('#d-body [data-rev-sug-original]');
    chk(await espera(async () => { const x = await imagem(); return x && !/[?&]s=/.test(x.src) && x.pePreto; }), '"Ver como chegou" volta à imagem original (sem s=)');
    chk(item(3)[0] === 0 && !(await aviso()), '"Ver como chegou" não grava nada e tira o aviso', JSON.stringify(item(3)));
    chk(await abrir(3) && /[?&]s=/.test((await imagem()).src) === false, 'reabrir a D3 na mesma visita não volta a sugerir (a pessoa recusou)');
    // nova visita (recarrega): a sugestão volta; Girar 90° com a sugestão de 90 na tela grava 180
    await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${D(3)}"]`, { timeout: 15000 });
    chk(await abrir(3), 'a D3 abre de novo (outra visita)');
    await clicar('#d-body [data-rev-girar-rapido="90"]');
    chk(await espera(async () => item(3)[0] === 180), 'D3: "Girar 90°" com a folha mostrada girada 90° grava 180 (conta a partir do que a pessoa vê)', JSON.stringify(item(3)));

    // ---------- D4: sem sugestão, nada muda ----------
    chk(await abrir(4), 'a D4 abre');
    im = await imagem();
    chk(im && !/[?&]s=/.test(im.src) && im.pePreto && !(await aviso()), 'D4 (incerta, sem rotacao_sugerida): imagem como chegou, sem o aviso novo', JSON.stringify(im));
    chk(item(4)[0] === 0, 'D4: nada gravado');

    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } finally { await br.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
