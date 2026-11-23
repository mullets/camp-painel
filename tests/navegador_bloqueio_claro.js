// CAMP-BLOQUEIO (23/11/2026). Rafael, em F010-P0174 "Concurso Público/Votorantim", Folha 1/7 com a marca vermelha "bloqueada" e, no "Revisar
// folha", só a pílula "ficha de documentação (não é obra)": "não entendi por que tá bloqueado". No navegador de verdade (Playwright + Chromium):
//  - o cartão da folha diz "bloqueada · ficha?" com a frase inteira no título; a caixa vermelha do "Revisar folha" mostra a frase;
//  - "É prancha do projeto · liberar" (caixa "trocar o tipo para Planta" marcada): a caixa some, a marca sai do cartão, o filtro "bloqueada (N)"
//    baixa sem recarregar, o tipo vira Planta e o aviso "Resolvido." tem Desfazer; Desfazer devolve o bloqueio, o tipo e a conta;
//  - "É ficha · deixar fora": a folha fica retida (não vai ao site) e a marca sai;
//  - o Próximo passo lista a folha bloqueada com a frase; nenhum erro de JavaScript.
// CAMP-BLOQUEIO, 2ª parte (Rafael: "só aviso"): a ficha de documentação NUNCA segurou a publicação. Agora: selo âmbar "aviso · ficha?", caixa âmbar
//  "Aviso do CAMP Vision" (a vermelha "Impede publicar" só com o que segura de verdade: aqui, o lote de teste da Folha 4/7), chip "aviso · ficha? (N)"
//  separado, "bloqueada (N)" conta só o lote de teste; botões "É prancha · tirar o aviso" e "É ficha · deixar fora".
// Uso (servidor PRÓPRIO numa porta 9030–9039):
//   CAMP_DB_PATH=/dev/shm/bq/b.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/bq/b.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 9031)
//   CAMP_DB_PATH=/dev/shm/bq/b.db CAMP_BASE=http://127.0.0.1:9041 [CAMP_SHOTS=/pasta] node tests/navegador_bloqueio_claro.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9031', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const SHOTS = process.env.CAMP_SHOTS || '';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_bloqueio_ui'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const q = (sql) => py(`print(json.dumps([list(r) for r in con.execute(${JSON.stringify(sql)})], ensure_ascii=False))`);
const P = 'F010-P0174', D = n => `${P}-1985-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO fundo (codigo, titulo) VALUES ('F010','Fundo Teste F010')")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F010', 174)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F010',174,'Concurso Público/Votorantim',1985,'Votorantim')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote Votorantim','${P}','/x/vot','revisao')").lastrowid
tit = "CONCURSO PÚBLICO ESTADUAL · PAÇO MUNICIPAL / CENTRO CÍVICO · VOTORANTIM · MEMORIAL"
for s in range(1, 5):
    cod = "${P}-1985-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (600, 420), "white"); dr = ImageDraw.Draw(im)
    dr.rectangle((20, 20, 580, 400), outline="black", width=4); dr.text((40, 40), "CONCURSO PUBLICO ESTADUAL - PACO MUNICIPAL / CENTRO CIVICO - VOTORANTIM %d/7" % s, fill="black")
    for y in range(80, 260, 14): dr.line((40, y, 300, y), fill="gray", width=2)
    dr.polygon([(380, 300), (480, 250), (560, 300), (460, 350)], outline="black"); dr.line((380, 300, 380, 200), fill="black"); dr.line((480, 250, 480, 150), fill="black")
    im.save(raiz / rel, "JPEG", quality=90)
    bl = ["ficha de documentação (não é obra)"] if s in (1, 2) else ["lote de teste (CV-24)"] if s == 4 else []
    pend = {"titulo_lido": tit, "bloqueios": bl, "sinais": (["orientação incerta"] if s == 1 else []), "ressalvas": ["autoria não confirmada: FERNANDO C. BELLOUBE DOS SANTOS"], "previa": rel}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao,autoria_divergente) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Concurso Público %d" % s, 'Documento' if s in (1, 2) else 'Planta', "%d/7" % s, 'campvision', lid, 'bloqueado' if bl else 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'conferida', 1))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
const FRASE = 'Aviso: o CAMP Vision acha que esta folha pode ser uma ficha de documentação, não uma prancha do projeto (o título lido tem a palavra "memorial" e o tipo é "Documento"). Não impede publicar. Se for ficha, deixe fora do site.';

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1440, height: 1000 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|Failed to load resource/.test(m.text())) erros.push('console.error: ' + m.text()); });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const tagRe = (c, re) => pg.evaluate(([c, re]) => { const t = [...document.querySelectorAll(`.thumb[data-rev-abrir="${c}"] .tag`)].find(x => new RegExp(re).test(x.textContent)); return t ? { t: t.textContent.trim(), title: t.title, cls: t.className } : null; }, [c, re]);
  const tagBloq = c => tagRe(c, 'bloqueada'), tagAviso = c => tagRe(c, '^aviso');
  const chip = k => pg.evaluate(k => { const b = document.querySelector(`.folhas-bar [data-fl-f="${k}"]`); return b ? { t: b.textContent.trim(), cls: b.className, title: b.title } : null; }, k);
  const chipBloq = async () => ((await chip('t-bloqueada')) || {}).t || '', chipAviso = async () => ((await chip('t-aviso-ficha')) || {}).t || '';
  const abrirDrawer = async c => { await pg.evaluate(c => abrirRevisaoItem(c), c); return espera(async () => !!(await pg.$('#d-body .rv-alertas'))); };
  const caixa = () => pg.evaluate(() => { const b = document.querySelector('#d-body .rv-al.erro'); return b ? b.innerText : ''; });
  const caixaAviso = () => pg.evaluate(() => { const b = document.querySelector('#d-body .rv-al.aviso'); return b ? b.innerText : ''; });
  const toastTxt = () => pg.evaluate(() => (document.getElementById('toast') || {}).textContent || '');
  const entrar = async () => { await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); return pg.waitForSelector(`.thumb[data-rev-abrir="${D(1)}"]`, { timeout: 15000 }).then(() => true, () => false); };
  try {
    chk(await entrar(), 'abre a página do projeto');
    await espera(async () => /aviso · ficha\? \(2\)/.test(await chipAviso()));
    const t1 = await tagAviso(D(1));
    chk(t1 && t1.t === 'aviso · ficha?' && / a /.test(' ' + t1.cls + ' ') && t1.title === FRASE && !(await tagBloq(D(1))),
      'cartão: o selo âmbar diz "aviso · ficha?" (não "bloqueada") e o título tem a frase de aviso', JSON.stringify([t1, await tagBloq(D(1))]));
    const t4 = await tagBloq(D(4));
    chk(t4 && t4.t === 'bloqueada · lote de teste' && / r /.test(' ' + t4.cls + ' '), 'cartão da Folha 4/7 (lote de teste): continua vermelho "bloqueada · lote de teste"', JSON.stringify(t4));
    const cA = await chip('t-aviso-ficha');
    chk(/bloqueada \(1\)/.test(await chipBloq()), 'filtro: "bloqueada (1)" conta só o lote de teste (a ficha não)', await chipBloq());
    chk(cA && /aviso · ficha\? \(2\)/.test(cA.t) && !/chip-bloq/.test(cA.cls) && cA.title === 'Aviso: não impede publicar', 'filtro âmbar "aviso · ficha? (2)", "Aviso: não impede publicar"', JSON.stringify(cA));
    await pg.click('.folhas-bar [data-fl-f="t-aviso-ficha"]');
    const vis = await pg.evaluate(() => [...document.querySelectorAll('.thumb[data-rev-abrir]')].filter(t => t.offsetParent !== null).map(t => t.dataset.revAbrir.slice(-1)));
    chk(JSON.stringify(vis) === '["1","2"]', 'o filtro "aviso · ficha?" mostra só as Folhas 1 e 2', JSON.stringify(vis));
    await pg.click('.folhas-bar [data-fl-f="t-aviso-ficha"]');
    const ppA = await pg.evaluate(() => (document.querySelector('#pj-proximo .pp-bloq.aviso') || {}).innerText || '');
    const ppB = await pg.evaluate(() => (document.querySelector('#pj-proximo .pp-bloq:not(.aviso)') || {}).innerText || '');
    chk(ppA.includes('2 folhas com aviso do CAMP Vision (não impede publicar)') && ppA.includes('pode ser uma ficha de documentação') && /Decidir na folha/.test(ppA)
      && ppB.includes('1 folha bloqueada pelo CAMP Vision') && ppB.includes('lote de teste') && !ppB.includes('ficha'),
      'Próximo passo: as folhas com aviso (âmbar) separadas da bloqueada pelo lote de teste', JSON.stringify([ppA.slice(0, 200), ppB.slice(0, 200)]));
    // a gaveta "Revisar folha"
    chk(await abrirDrawer(D(1)), 'abre o Revisar folha da Folha 1/7');
    const cx = await caixaAviso();
    chk(!(await caixa()) && cx.includes('Aviso do CAMP Vision') && cx.includes('confira; não impede publicar') && cx.includes(FRASE) && cx.includes('O CAMP Vision escreveu: ficha de documentação (não é obra)') && cx.includes('Abrir em Problemas'),
      'caixa âmbar "Aviso do CAMP Vision · confira; não impede publicar" com a frase e o texto original; sem caixa vermelha', JSON.stringify([await caixa(), cx.slice(0, 400)]));
    const bts = await pg.$$eval('#d-body .rv-al.aviso button', bs => bs.map(b => b.textContent.trim()));
    const cxT = await pg.$eval('#d-body .rv-al.aviso [data-blq-trocar]', i => i.checked).catch(() => null);
    chk(bts.includes('É prancha · tirar o aviso') && bts.includes('É ficha · deixar fora') && cxT === true, 'botões "É prancha · tirar o aviso" e "É ficha · deixar fora"; caixa "trocar o tipo para Planta" marcada', JSON.stringify([bts, cxT]));
    const foto = async nome => { if (!SHOTS) return; await pg.evaluate(() => { const b = [...document.querySelectorAll('#d-body button')].find(x => /^Entendi/.test(x.textContent.trim())); if (b) b.click(); });
      await pg.evaluate(() => { const a = document.querySelector('#d-body .rv-alertas') || document.querySelector('#d-body .rv'); if (a) a.scrollIntoView({ block: 'start' }); const d = document.getElementById('d-body'); if (d) d.scrollTop = Math.max(0, d.scrollTop - 120); });
      await pg.waitForTimeout(300); await pg.screenshot({ path: path.join(SHOTS, nome) }); };
    await foto('aviso_antes.png');
    // tirar o aviso
    await pg.click('#d-body [data-blq-decidir="liberar"]');
    const liberou = await espera(async () => !(await pg.$('#d-body [data-blq-motivo="ficha"]')) && !(await tagAviso(D(1))) && /aviso · ficha\? \(1\)/.test(await chipAviso()) && /bloqueada \(1\)/.test(await chipBloq()));
    chk(liberou, '"É prancha · tirar o aviso": o aviso some da gaveta e do cartão, "aviso · ficha? (1)" sem recarregar; "bloqueada (1)" não muda', JSON.stringify([await caixaAviso(), await tagAviso(D(1)), await chipAviso(), await chipBloq()]));
    const db1 = JSON.parse(q(`SELECT tipo_documento, status_site, pendencias FROM item WHERE codigo='${D(1)}'`))[0];
    chk(db1[0] === 'Planta' && db1[1] === 'nao_publicado' && JSON.parse(db1[2]).bloqueios.length === 0, 'tirar o aviso: no banco, tipo Planta, sem o aviso, fora de "bloqueado"', JSON.stringify(db1));
    const tipoCartao = await pg.evaluate(c => (document.querySelector(`.thumb[data-rev-abrir="${c}"] .cap-tipo`) || {}).textContent, D(1));
    chk(tipoCartao === 'Planta', 'o cartão já está com o tipo Planta', tipoCartao);
    chk(/^Resolvido\. O tipo passou a Planta\./.test(await toastTxt()) && !!(await pg.$('#toast .toast-acao')), 'aviso "Resolvido. O tipo passou a Planta." com Desfazer', await toastTxt());
    await foto('aviso_depois.png');
    // Desfazer
    await pg.click('#toast .toast-acao');
    const voltou = await espera(async () => { const r = JSON.parse(q(`SELECT tipo_documento, pendencias FROM item WHERE codigo='${D(1)}'`))[0]; return r[0] === 'Documento' && JSON.parse(r[1]).bloqueios.length === 1 && /aviso · ficha\? \(2\)/.test(await chipAviso()) && !!(await tagAviso(D(1))); });
    chk(voltou, 'Desfazer: o aviso e o tipo Documento voltam; "aviso · ficha? (2)" e o selo voltam', JSON.stringify([q(`SELECT tipo_documento, pendencias FROM item WHERE codigo='${D(1)}'`), await chipAviso()]));
    chk(await espera(async () => (await caixaAviso()).includes(FRASE) && !(await caixa())), 'Desfazer: a caixa âmbar volta na gaveta (e nenhuma vermelha)', (await caixaAviso()).slice(0, 200));
    // deixar fora (Folha 2/7)
    await pg.evaluate(() => closeDrawer(true));
    chk(await abrirDrawer(D(2)), 'abre o Revisar folha da Folha 2/7');
    await pg.click('#d-body [data-blq-decidir="deixar_fora"]');
    const fora = await espera(async () => { const r = JSON.parse(q(`SELECT retida, pendencias FROM item WHERE codigo='${D(2)}'`))[0]; return r[0] === 1 && JSON.parse(r[1]).bloqueios.length === 0 && !(await tagAviso(D(2))) && /aviso · ficha\? \(1\)/.test(await chipAviso()); });
    chk(fora, '"É ficha · deixar fora": a folha fica retida (não vai ao site), o selo sai e "aviso · ficha? (1)"', JSON.stringify([q(`SELECT retida, retida_motivo FROM item WHERE codigo='${D(2)}'`), await chipAviso()]));
    chk(/Resolvido\. A folha fica fora do site\./.test(await toastTxt()), 'aviso "Resolvido. A folha fica fora do site."', await toastTxt());
    const ret = await pg.evaluate(c => { const t = document.querySelector(`.thumb[data-rev-abrir="${c}"]`); return t ? t.textContent : ''; }, D(2));
    chk(/retida/.test(ret), 'o cartão da Folha 2/7 mostra "retida"', ret.slice(0, 200));
    // a do lote de teste continua na caixa vermelha
    await pg.evaluate(() => closeDrawer(true));
    chk(await abrirDrawer(D(4)), 'abre o Revisar folha da Folha 4/7');
    const cv = await caixa();
    chk(cv.includes('Impede publicar') && cv.includes('Bloqueada: a folha veio de um lote de teste') && !(await caixaAviso()).includes('lote de teste'), 'lote de teste: continua na caixa vermelha "Impede publicar"', cv.slice(0, 300));
    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } catch (e) { chk(false, 'o teste rodou até o fim', String(e).slice(0, 300)); }
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
