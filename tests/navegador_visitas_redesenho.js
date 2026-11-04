// Visitas ao site (especificação do Rafael, 04/11/2026). Desde 05/11 (plano de redesenho §12) a Home tem só o RESUMO (provado aqui e em
// tests/navegador_redesenho_relatorios.js) e a tela Visitas ao site tem o módulo completo — filtro de período, Evolução das visitas (indicadores + gráfico) e Projetos mais visitados (10, ver todos, busca, ordem,
// CSV, não identificadas, intervalo personalizado). Critérios de aceite provados no navegador de verdade:
// filtro muda gráfico e ranking juntos; 1º destacado; institucionais fora; tooltip (mouse e teclado); estados (carregando, sem dados,
// indisponível com o erro técnico e sem zero); 390 px sem rolagem lateral; rótulos do gráfico com o mesmo tamanho em 1366 e 1920 px;
// tema escuro. Tira prints (deviceScaleFactor 1) da Home e da tela em 1366, 1920 e 390 px, claro e escuro.
// Uso (servidor PRÓPRIO na porta 8975, banco próprio; nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/vr/vr.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/vr/vr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8975)
//   CAMP_DB_PATH=/tmp/vr/vr.db CAMP_BASE=http://127.0.0.1:8975 PRINTS=/tmp/vr node tests/navegador_visitas_redesenho.js
const { execFileSync } = require('child_process');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8975', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || '';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + String(det).slice(0, 300))); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------- semente: visitas sintéticas (números de teste, não da CAMP) ligadas aos projetos da semente pelo vínculo real ----------
const ESP = JSON.parse(py(`
import math, os, pathlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date(); ontem = hoje - timedelta(days=1)
raiz = pathlib.Path(sys.argv[1]).parent / "prontos_vr"; raiz.mkdir(exist_ok=True)
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
if not con.execute("SELECT 1 FROM configuracao WHERE chave='qnap.prontos_raiz'").fetchone():
    con.execute("INSERT INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (str(raiz),))
for t in ("visita_dia", "visita_dimensao", "visita_coleta", "visita_periodo"):
    con.execute(f"DELETE FROM {t}")
S = "https://camp.arq.br/acervo/projetos/"
# projetos da semente (item do site = vínculo pelo ID) + 6 novos (página do site com o código no slug)
novos = [("F026-P0003", "F026", 3, "Residência Butantã", 1966), ("F026-P0004", "F026", 4, "Edifício Copan Anexo", 1957), ("F023-P0012", "F023", 12, "Clube Paineiras", 1960),
         ("F010-P0007", "F010", 7, "Sede Social do Sindicato", 1974), ("F001-P0002", "F001", 2, "Residência Teresa Martino", 1964), ("F003-P0002", "F003", 2, "Praça Pública de Santo Amaro", 1971)]
for cod, f, n, t, a in novos:
    if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod,)).fetchone():
        con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES (?,?)", (f, n))
        con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade) VALUES (?,?,?,?,?,'São Paulo')", (cod, f, n, t, a))
pid = 90000
def slug(t):
    import unicodedata, re
    s = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")
caminho = {}
for r in con.execute("SELECT p.codigo, p.titulo, p.tainacan_item_id FROM projeto p ORDER BY p.codigo").fetchall():
    cod, tit, iid = r
    url = S + cod.lower() + "-" + slug(tit) + "/"
    if iid and con.execute("SELECT 1 FROM wp_item WHERE id=?", (iid,)).fetchone():
        con.execute("UPDATE wp_item SET url=?, status='publish' WHERE id=?", (url, iid))
    else:
        pid += 1
        con.execute("INSERT OR REPLACE INTO wp_pagina (id, titulo, slug, url, status, codigo_detectado) VALUES (?,?,?,?, 'publish', ?)", (pid, tit, cod.lower() + "-" + slug(tit), url, cod))
    caminho[cod] = url[len("https://camp.arq.br"):]
con.execute("UPDATE projeto SET autoria='Sylvio Sawaya; Equipe técnica' WHERE codigo='F026-P0003'")
# fotos: capa escolhida (F026-P0001), 1ª folha publicada (F023-P0011); os outros ficam com o desenho neutro
from PIL import Image, ImageDraw
def jpg(rel, cor):
    p = raiz / rel; p.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (480, 330), (226, 226, 222)); d = ImageDraw.Draw(im)
    d.rectangle([30, 120, 450, 300], outline=(60, 60, 60), width=6); d.polygon([(20, 125), (240, 30), (460, 125)], outline=(60, 60, 60), fill=cor)
    for x in range(70, 430, 60): d.rectangle([x, 170, x + 30, 230], fill=(90, 90, 90))
    im.save(p, "JPEG", quality=80)
for cod, cor in (("F026-P0001", (150, 150, 150)), ("F023-P0011", (120, 120, 130))):
    its = [x[0] for x in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY sequencial LIMIT 2", (cod,))]
    for ic in its:
        rel = f"vr/{ic}.jpg"; jpg(rel, cor)
        con.execute("UPDATE item SET arquivo_jpg=?, status_site='no_ar' WHERE codigo=?", (rel, ic))
    if cod == "F026-P0001" and its:
        con.execute("UPDATE projeto SET capa_item=? WHERE codigo=?", (its[-1], cod))
cid = con.execute("INSERT INTO visita_coleta (fonte, de, ate, linhas, por, inicio, fim) VALUES ('ga4', ?, ?, 1, 'teste', datetime('now','-2 hours'), datetime('now','-2 hours'))", ((hoje - timedelta(days=140)).isoformat(), ontem.isoformat())).lastrowid
cods = sorted(caminho)
ordem = ["F026-P0001", "F023-P0011", "F001-P0002", "F026-P0002", "F010-P0006", "F026-P0004", "F002-P0001", "F001-P0001", "F023-P0012", "F002-P0002", "F010-P0007", "F003-P0001", "F003-P0002"]
peso = {c: 2.0 for c in cods}
peso.update({c: 30 - k * 2.1 for k, c in enumerate(ordem)})
peso["F026-P0003"] = 4                                  # cresce na última semana: 1º em 7 dias, não em 30
vis = {}
for k in range(120):
    d = ontem - timedelta(days=k); ds = d.isoformat()
    s_ = int(70 + 25 * math.sin(k / 4.0) + (15 if d.weekday() < 5 else -10) + (190 if k == 3 else 0))
    con.execute("INSERT INTO visita_dia (dia, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?)", (ds, s_ - 5, s_, s_ * 3, cid))
    def pg(c, v, t=None):
        con.execute("INSERT OR REPLACE INTO visita_dimensao (dia, tipo, valor, extra, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?,?,?,?)", (ds, "pagina", c, t, 1, 1, v, cid))
    for c in cods:
        v = max(0, int(round(peso[c] * (1 + 0.35 * math.sin(k / 3.0 + len(c))))) + (60 if c == "F026-P0003" and k < 6 else 0))
        if c == "F026-P0001":
            pg(caminho[c] + "?utm_source=instagram&utm_medium=social", 2); pg(caminho[c].rstrip("/"), 1); v_extra = 3
        else:
            v_extra = 0
        if v: pg(caminho[c], v, None)
        vis.setdefault(ds, {})[c] = v + v_extra
    for c, v, t in (("/", 120, "CAMP – Casa da Arquitetura Moderna Paulista"), ("/acervo/arquitetos/rino-levi/", 60, "Rino Levi – CAMP"), ("/acervo/projetos/", 55, "Projetos – CAMP"),
                    ("/acervo/busca/", 30, "Buscar no acervo"), ("/noticias/abertura-do-acervo/", 25, "Notícias"), ("/acervo/projetos/residencia-sem-codigo/", 3, "Casa Tarumã – CAMP")):
        pg(c, v, t)
    for tipo, val in (("canal", "Organic Search"), ("canal", "Direct"), ("cidade", "São Paulo, Brazil"), ("dispositivo", "mobile"), ("origem", "google / organic")):
        con.execute("INSERT OR REPLACE INTO visita_dimensao (dia, tipo, valor, extra, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?,?,?,?)", (ds, tipo, val, None, 5, 9 if val != "Direct" else 4, 20, cid))
def top(n):
    dias = [(ontem - timedelta(days=k)).isoformat() for k in range(n)]
    t = {c: sum(vis[d][c] for d in dias) for c in cods}
    return sorted(((c, v) for c, v in t.items() if v), key=lambda x: (-x[1], x[0]))
print(json.dumps({"ontem": ontem.isoformat(), "de30": (ontem - timedelta(days=29)).isoformat(), "de7": (ontem - timedelta(days=6)).isoformat(), "top30": top(30), "top7": top(7),
                  "sem_hist_de": (hoje - timedelta(days=138)).isoformat(), "sem_hist_ate": (hoje - timedelta(days=130)).isoformat(), "projetos": len(cods)}))
`));

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, deviceScaleFactor: 1 });
  const P = await ctx.newPage();
  P.on('console', m => { if (m.type() === 'error' && !/favicon|\/previa\?|exemplo\.test|\/api\/auth\/eu/.test(((m.location() || {}).url || '') + m.text())) erros.push(m.text()); });
  P.on('pageerror', e => erros.push('pageerror: ' + e.message));
  // o painel rola por dentro (não a página): para o print inteiro, a janela fica alta o bastante e volta ao tamanho de antes
  const foto = async (nome, sel) => { if (!PRINTS) return; const f = path.join(PRINTS, nome), vp = P.viewportSize();
    const alt = await P.evaluate(s => { const e = s ? document.querySelector(s).closest('section') || document.querySelector(s) : document.querySelector('section.content.on') || document.body; return Math.ceil(e.getBoundingClientRect().height + 400); }, sel || null);
    await P.setViewportSize({ width: vp.width, height: Math.max(vp.height, alt) }); await P.waitForTimeout(250);
    if (sel) { const e = P.locator(sel).first().locator('xpath=ancestor::section[1]'); await e.scrollIntoViewIfNeeded(); await e.screenshot({ path: f }); } else await P.screenshot({ path: f });
    await P.setViewportSize(vp); await P.waitForTimeout(150); };
  const tema = t => P.evaluate(t => { document.documentElement.dataset.theme = t; }, t);
  const esperarModulo = async (sel) => { await P.waitForFunction(s => { const e = document.querySelector(s); return e && e.querySelector('.vm-sec') && !e.querySelector('.vm.vm-atualizando'); }, sel, { timeout: 15000 }); await P.waitForTimeout(300); };
  try {
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    // ---------- estado "carregando" (a resposta demora) ----------
    await P.route('**/api/visitas/evolucao*', async r => { await new Promise(ok => setTimeout(ok, 1500)); await r.continue().catch(() => {}); });
    await P.evaluate(() => { VM.ev = VM.pj = null; VM.t = 0; nav('painel'); carregarPainel(); });
    await P.waitForSelector('#ini-visitas', { timeout: 15000 });
    chk(await P.locator('#ini-visitas .vm-load').first().isVisible().catch(() => false) && /Carregando as visitas/.test(await P.locator('#ini-visitas').innerText()), 'estado carregando: esqueleto com "Carregando as visitas…"');
    await esperarModulo('#ini-visitas');
    await P.unroute('**/api/visitas/evolucao*');
    // ---------- posição na Home ----------
    const pos = await P.evaluate(() => { const r = document.getElementById('ini-ritmo').closest('section'), v = document.getElementById('ini-visitas').closest('section'); return { logo: r.nextElementSibling === v, col: r.parentElement === v.parentElement, w: v.getBoundingClientRect().width }; });
    chk(pos.logo && pos.col, 'Home: o resumo fica logo abaixo do gráfico de folhas conferidas por dia, na mesma coluna', JSON.stringify(pos));
    // 05/11 (plano de redesenho §12): a Home tem só o RESUMO (total, evolução, top 5, 7/30/90 dias e o link); o módulo completo fica na tela
    const hTxt = await P.locator('#ini-visitas').innerText();
    chk(await P.$$eval('#ini-visitas .vm-row', r => r.length) === 5 && !(await P.$('#ini-visitas [data-vm-todos], #ini-visitas [data-vm-csv], #ini-visitas .vm-ni'))
      && /Visitas no período/.test(hTxt) && /sessões/.test(hTxt) && /Ver análise completa de visitas/.test(hTxt) && (await P.$$eval('#ini-visitas [data-vm-per] option', o => o.map(x => x.value).join(','))) === '7d,30d,90d',
      'Home: só o resumo (top 5, total = sessões, 7/30/90 dias, "Ver análise completa de visitas"); o completo fica na tela', hTxt.slice(0, 300));
    if (PRINTS) { await tema('light'); await foto('vis-home-1366-claro.png', '#ini-visitas'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-home-1366-escuro.png', '#ini-visitas'); await tema('light'); }
    // ---------- tela Visitas ao site: o módulo completo (o que antes ficava também na Home) ----------
    await P.evaluate(() => nav('visitas')); await esperarModulo('#vis-modulo');
    const txt = await P.locator('#vis-modulo').innerText();
    chk(/Acompanhe a evolução dos acessos e descubra quais projetos despertam mais interesse/.test(txt) && /Evolução das visitas/.test(txt) && /Projetos mais visitados/.test(txt)
      && /Ranking dos projetos do acervo que receberam mais acessos no período selecionado/.test(txt), 'textos da especificação (subtítulo e as duas seções, nesta ordem)');
    const fmt = s => s.slice(8, 10) + '/' + s.slice(5, 7) + '/' + s.slice(0, 4);
    chk(await P.$eval('#vis-modulo [data-vm-per]', s => s.value) === '30d' && txt.includes(`De ${fmt(ESP.de30)} a ${fmt(ESP.ontem)}`) && /horário de São Paulo/.test(txt) && /dia de hoje ainda não terminou/.test(txt) && /Última sincronização: \d\d\/\d\d\/\d{4}/.test(txt),
      'período padrão: últimos 30 dias até ontem, com as datas, o fuso e a última sincronização', txt.slice(0, 400));
    chk(/Visitas no período/.test(txt) && /Média de visitas por dia/.test(txt) && /Variação vs\. período anterior/.test(txt) && /sessões/.test(txt) && /Visualizações da página do projeto|Visualizações\s+da página do projeto/.test(txt),
      'indicadores lado a lado e as duas métricas definidas na tela (visitas = sessões; ranking = visualizações da página do projeto)');
    // ---------- ranking ----------
    const rank = () => P.$$eval('#vis-modulo .vm-row', rs => rs.map(r => ({ c: r.dataset.vmProj, n: +r.querySelector('.vm-n b').textContent.replace(/\D/g, ''), top: r.classList.contains('top'), w: parseFloat(r.querySelector('.vm-barra i').style.width) })));
    let R = await rank();
    chk(R.length === 10 && JSON.stringify(R.map(r => [r.c, r.n])) === JSON.stringify(ESP.top30.slice(0, 10)), '10 projetos mais visitados em 30 dias, em ordem e com o número exato', JSON.stringify(R.map(r => [r.c, r.n])) + ' ≠ ' + JSON.stringify(ESP.top30.slice(0, 10)));
    chk(R.every(r => /^F\d{3}-P\d{4}$/.test(r.c)) && !/acervo\/arquitetos|\/acervo\/busca|noticias|Página inicial/.test(await P.locator('#vis-modulo .vm-rank').innerText()), 'institucionais fora do ranking (home, arquitetos, listagem, busca, notícias)');
    const est1 = await P.evaluate(() => { const r = document.querySelector('#vis-modulo .vm-row'), b = getComputedStyle(r).borderTopColor, a = getComputedStyle(document.documentElement).getPropertyValue('--amber').trim(); const c = document.createElement('i'); c.style.color = a; document.body.appendChild(c); const ac = getComputedStyle(c).color; c.remove(); return { b, ac, outro: getComputedStyle(document.querySelectorAll('#vis-modulo .vm-row')[1]).borderTopColor }; });
    chk(R[0].top && !R[1].top && est1.b === est1.ac && est1.outro !== est1.ac, '1º lugar com contorno dourado (var(--amber)); os outros não', JSON.stringify(est1));
    chk(R[0].w === 100 && R.every((r, i) => Math.abs(r.w - Math.max(1, r.n / R[0].n * 100)) < 0.2), 'barras proporcionais ao 1º do período', JSON.stringify(R.map(r => r.w)));
    const numDir = await P.evaluate(() => [...document.querySelectorAll('#vis-modulo .vm-n')].every(n => getComputedStyle(n).textAlign === 'right' && getComputedStyle(n.querySelector('b')).fontVariantNumeric.includes('tabular-nums')));
    chk(numDir, 'números à direita, com algarismos tabulares');
    await P.locator('#vis-modulo .vm-rank').scrollIntoViewIfNeeded(); await P.waitForFunction(() => [...document.querySelectorAll('#vis-modulo .vm-foto img')].every(i => i.complete), null, { timeout: 8000 }).catch(() => {});
    const fotos = await P.evaluate(() => [...document.querySelectorAll('#vis-modulo .vm-row')].map(r => ({ c: r.dataset.vmProj, img: !!r.querySelector('.vm-foto img'), ok: !!(r.querySelector('.vm-foto img') || {}).naturalWidth, svg: !!r.querySelector('.vm-foto svg') })));
    const f1 = fotos.find(f => f.c === 'F026-P0001'), f2 = fotos.find(f => f.c === 'F023-P0011'), sem = fotos.filter(f => !f.img);
    chk(f1 && f1.ok && f2 && f2.ok && sem.length >= 5 && sem.every(f => f.svg), 'miniatura real (capa / 1ª folha publicada) e desenho neutro quando não há foto', JSON.stringify(fotos));
    const pub = await P.$eval('#vis-modulo .vm-row .vm-pub', a => ({ h: a.href, t: a.target }));
    chk(/^https:\/\/camp\.arq\.br\/acervo\/projetos\/f\d{3}-p\d{4}-/.test(pub.h) && pub.t === '_blank', 'botão separado abre a página pública do projeto (outra aba)', JSON.stringify(pub));
    const sub = await P.$$eval('#vis-modulo .vm-row .vm-nome small', s => s.map(x => x.textContent));
    chk(sub.some(s => /^Sylvio Sawaya, Equipe técnica, 1966$/.test(s)) && sub.some(s => /^Acervo .+, \d{4}$/.test(s)), 'autoria cadastrada como autoria; sem autoria, só o acervo (nunca como autor)', JSON.stringify(sub.slice(0, 4)));
    chk(!(await P.$('#vis-modulo svg text')) && !(await P.$('#vis-modulo a[style*="underline"]')), 'nenhum texto dentro do SVG; nada sublinhado');
    // ---------- tooltip (mouse e teclado) ----------
    const area = await P.$('#vis-modulo [data-vm-area]'); await area.scrollIntoViewIfNeeded(); const bx = await area.boundingBox();
    await P.mouse.move(bx.x + bx.width * 0.5, bx.y + bx.height * 0.5); await P.waitForTimeout(150);
    const tip1 = await P.$eval('#vis-modulo [data-vm-tip]', t => ({ v: !t.hidden, s: t.textContent }));
    chk(tip1.v && /\d\d\/\d\d\/\d{4}/.test(tip1.s) && /\d+ visitas?/.test(tip1.s), 'tooltip ao passar o mouse: data e número exato', JSON.stringify(tip1));
    await P.mouse.move(bx.x + bx.width + 5, bx.y - 200);
    await P.focus('#vis-modulo [data-vm-g]'); await P.keyboard.press('End');
    const tipFim = await P.$eval('#vis-modulo [data-vm-tip]', t => t.textContent);
    await P.keyboard.press('ArrowLeft'); await P.keyboard.press('ArrowLeft'); await P.keyboard.press('ArrowLeft');
    const tipPico = await P.$eval('#vis-modulo [data-vm-tip]', t => t.textContent);
    const pico = await P.evaluate(() => VM.ev.pico);
    chk(tipFim.includes(fmt(ESP.ontem)) && tipPico.includes(fmt(pico.inicio)) && tipPico.includes(String(pico.visitas)), 'tooltip pelo teclado (setas): ontem e, 3 dias antes, o pico', tipFim + ' | ' + tipPico);
    chk(await P.$$eval('#vis-modulo .vm-pto.pico', p => p.length) === 1 && /pico:/.test(txt), 'destaque discreto do pico (um ponto + legenda)');
    const yZero = await P.$$eval('#vis-modulo .vm-g-y span', s => s.map(x => x.textContent.trim()));
    chk(yZero[0] === '0' && yZero.length === 5, 'eixo vertical começa em zero', JSON.stringify(yZero));
    await P.click('#vis-modulo .vm-num summary');
    const ntab = await P.$$eval('#vis-modulo .vm-num tbody tr', r => r.length);
    chk(ntab === 30, 'alternativa em texto: "Ver os números" com os 30 dias', String(ntab));
    await P.click('#vis-modulo .vm-num summary');
    // ---------- rótulos do gráfico: mesmo tamanho em 1366 e 1920 ----------
    const rot = () => P.evaluate(() => [...document.querySelectorAll('#vis-modulo .vm-g-x span, #vis-modulo .vm-g-y span, #vis-modulo .vm-g-leg')].map(e => getComputedStyle(e).fontSize));
    const r1366 = await rot();
    if (PRINTS) { await tema('light'); await foto('vis-tela-modulo-1366-claro.png', '#vis-modulo'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-tela-modulo-1366-escuro.png', '#vis-modulo'); await foto('vis-tela-modulo-1366-escuro-pagina.png'); await tema('light'); }
    await P.setViewportSize({ width: 1920, height: 1080 }); await P.waitForTimeout(400);
    const r1920 = await rot();
    chk(JSON.stringify(r1366) === JSON.stringify(r1920) && r1366.every(s => parseFloat(s) >= 12 && parseFloat(s) <= 14), 'rótulos do gráfico com o mesmo tamanho em 1366 e 1920 px (12–14 px, HTML)', JSON.stringify([r1366, r1920]));
    chk(await P.evaluate(() => [...document.querySelectorAll('#vis-modulo *')].filter(e => e.offsetParent && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).every(e => parseFloat(getComputedStyle(e).fontSize) >= 12)), 'nenhum texto do módulo abaixo de 12 px');
    if (PRINTS) { await foto('vis-tela-modulo-1920-claro.png', '#vis-modulo'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-tela-modulo-1920-escuro.png', '#vis-modulo'); await tema('light'); }
    await P.setViewportSize({ width: 1366, height: 900 }); await P.waitForTimeout(300);
    // ---------- filtro muda gráfico e ranking juntos ----------
    const pedidos = []; const ouvir = r => { if (/\/api\/visitas\/(evolucao|projetos)\?/.test(r.url())) pedidos.push(r.url()); }; P.on('request', ouvir);
    await P.selectOption('#vis-modulo [data-vm-per]', '7d'); await esperarModulo('#vis-modulo');
    P.off('request', ouvir);
    const st7 = await P.evaluate(() => ({ n: VM.ev.pontos.length, de: VM.ev.de, ate: VM.ev.ate, pde: VM.pj.de, pate: VM.pj.ate, x: document.querySelectorAll('#vis-modulo .vm-g-x span').length }));
    R = await rank();
    chk(pedidos.length === 2 && pedidos.every(u => /periodo=7d/.test(u)) && st7.n === 7 && st7.de === ESP.de7 && st7.pde === ESP.de7 && st7.ate === ESP.ontem && st7.pate === ESP.ontem, 'filtro 7 dias: gráfico e ranking pedidos com o MESMO período', JSON.stringify([pedidos, st7]));
    chk(JSON.stringify(R.map(r => [r.c, r.n])) === JSON.stringify(ESP.top7.slice(0, 10)) && R[0].c === 'F026-P0003' && R[0].top, 'ranking de 7 dias muda junto (o projeto que cresceu na semana vira o 1º)', JSON.stringify(R.slice(0, 3)));
    chk((await P.locator('#vis-modulo').innerText()).includes(`De ${fmt(ESP.de7)} a ${fmt(ESP.ontem)}`), 'as datas do período mudam junto');
    // comparar com o período anterior: segunda linha discreta
    await P.check('#vis-modulo [data-vm-comparar]'); await P.waitForTimeout(150);
    chk(await P.$$eval('#vis-modulo polyline.ant', p => p.length) >= 1 && /período anterior/.test(await P.locator('#vis-modulo .vm-g-leg').innerText()), '"Comparar com período anterior": segunda linha tracejada e legenda');
    await P.uncheck('#vis-modulo [data-vm-comparar]');
    await P.selectOption('#vis-modulo [data-vm-per]', '30d'); await esperarModulo('#vis-modulo');
    // ---------- ver todos, busca, ordem, CSV, não identificadas ----------
    await P.click('#vis-modulo [data-vm-todos="1"]'); await P.waitForFunction(() => document.querySelectorAll('#vis-modulo .vm-row').length > 10, null, { timeout: 8000 });
    const nTodos = await P.$$eval('#vis-modulo .vm-row', r => r.length);
    chk(nTodos === ESP.top30.length, `"Ver todos os projetos": lista completa (${nTodos})`);
    await P.fill('#vis-modulo [data-vm-busca]', 'sawaya'); await P.waitForFunction(() => document.querySelectorAll('#vis-modulo .vm-row').length === 1, null, { timeout: 5000 }).catch(() => {});
    R = await rank();
    chk(R.length === 1 && R[0].c === 'F026-P0003' && (await P.$eval('#vis-modulo [data-vm-busca]', i => document.activeElement === i)), 'busca por arquiteto/autoria dentro da lista completa (o campo não perde o foco)', JSON.stringify(R));
    await P.fill('#vis-modulo [data-vm-busca]', ''); await P.waitForFunction(n => document.querySelectorAll('#vis-modulo .vm-row').length === n, nTodos, { timeout: 5000 }).catch(() => {});
    await P.selectOption('#vis-modulo [data-vm-ordem]', 'menos'); await P.waitForTimeout(500);
    R = await rank();
    chk(R.length === nTodos && R[0].n <= R[R.length - 1].n && R[0].n === ESP.top30[ESP.top30.length - 1][1], 'ordenação "menos visitados"', JSON.stringify(R.slice(0, 2)));
    await P.selectOption('#vis-modulo [data-vm-ordem]', 'crescimento'); await P.waitForTimeout(500);
    chk((await rank()).length === nTodos, 'ordenação "maior crescimento"');
    const csv = await P.$eval('#vis-modulo [data-vm-csv]', a => a.getAttribute('href'));
    const csvR = await P.evaluate(async h => { const r = await fetch(h); return { s: r.status, t: (await r.text()).slice(0, 200) }; }, csv);
    chk(/periodo=30d/.test(csv) && csvR.s === 200 && /posição;código;projeto/.test(csvR.t), 'exportar CSV do ranking do período', JSON.stringify(csvR));
    await P.click('#vis-modulo .vm-ni summary');
    const ni = await P.locator('#vis-modulo .vm-ni').innerText();
    chk(/Páginas não identificadas: 1 página/.test(ni) && /\/acervo\/projetos\/residencia-sem-codigo\//.test(ni) && /Casa Tarumã – CAMP/.test(ni) && !(await rank()).some(r => r.n === 0), '"não identificadas" (mesmo título de um projeto) recolhida, com as visualizações, sem atribuir a projeto', ni.slice(0, 300));
    chk(/Fora do ranking também: [\d.]+ visualizações em 5 outras páginas/.test(await P.locator('#vis-modulo').innerText()), 'o que ficou fora do ranking é dito (outras páginas do site)');
    await P.click('#vis-modulo [data-vm-todos="0"]'); await P.waitForFunction(() => document.querySelectorAll('#vis-modulo .vm-row').length === 10, null, { timeout: 5000 }).catch(() => {});
    // ---------- linha clicável ----------
    await P.click('#vis-modulo .vm-row .vm-nome'); await P.waitForTimeout(500);
    chk(/^#projeto\/F\d{3}-P\d{4}$/.test(await P.evaluate(() => location.hash)), 'a linha inteira abre o projeto no painel', await P.evaluate(() => location.hash));
    await P.evaluate(() => nav('painel')); await esperarModulo('#ini-visitas');
    // ---------- tela Visitas ao site: o mesmo componente + detalhes do mesmo período ----------
    await P.evaluate(() => nav('visitas')); await esperarModulo('#vis-modulo');
    await P.waitForFunction(() => /Cidades/.test((document.getElementById('vis-corpo') || {}).textContent || ''), null, { timeout: 8000 }).catch(() => {});
    const tela = await P.locator('#v-visitas').innerText();
    chk(/Evolução das visitas/.test(tela) && /Projetos mais visitados/.test(tela) && /Google e outras buscas/.test(tela) && /São Paulo, Brazil/.test(tela) && /celular/.test(tela), 'tela Visitas ao site: o mesmo componente e, abaixo, canais, cidades e aparelhos do período');
    if (PRINTS) { await foto('vis-tela-1366-claro.png'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-tela-1366-escuro.png'); await tema('light');
      await P.setViewportSize({ width: 1920, height: 1080 }); await P.waitForTimeout(300); await foto('vis-tela-1920-claro.png'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-tela-1920-escuro.png'); await tema('light'); await P.setViewportSize({ width: 1366, height: 900 }); }
    // ---------- intervalo personalizado sem visitas (sincronizado) ----------
    await P.selectOption('#vis-modulo [data-vm-per]', 'livre');
    await P.fill('#vis-modulo [data-vm-de]', ESP.sem_hist_de); await P.fill('#vis-modulo [data-vm-ate]', ESP.sem_hist_ate); await P.click('#vis-modulo [data-vm-aplicar]'); await esperarModulo('#vis-modulo');
    const vz = await P.locator('#vis-modulo').innerText();
    chk(/Sem visitas registradas neste período/.test(vz) && vz.includes(`De ${fmt(ESP.sem_hist_de)} a ${fmt(ESP.sem_hist_ate)}`), 'intervalo personalizado; sem visitas: "Sem visitas registradas neste período"', vz.slice(0, 300));
    await P.selectOption('#vis-modulo [data-vm-per]', '30d'); await esperarModulo('#vis-modulo');
    // ---------- tema escuro ----------
    await tema('dark'); await P.waitForTimeout(100);
    const esc = await P.evaluate(() => { const lum = c => { const m = c.match(/\d+(\.\d+)?/g).map(Number); return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; }; const s = document.querySelector('#vis-modulo .vm-sec'); return { fundo: lum(getComputedStyle(s).backgroundColor), texto: lum(getComputedStyle(s.querySelector('h3')).color), linha: getComputedStyle(document.querySelector('#vis-modulo polyline.lin')).stroke }; });
    chk(esc.fundo < 0.2 && esc.texto > 0.8 && /rgb\(127, 166, 230\)/.test(esc.linha), 'tema escuro: fundo escuro, texto claro, linha azul dos tokens', JSON.stringify(esc));
    await tema('light');
    // ---------- celular (390 px) ----------
    await P.setViewportSize({ width: 390, height: 844 }); await P.waitForTimeout(500);
    const semRolar = () => P.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    chk(await semRolar(), '390 px: tela Visitas ao site sem rolagem lateral');
    if (PRINTS) { await foto('vis-tela-390-claro.png'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-tela-390-escuro.png'); await tema('light'); }
    await P.evaluate(() => nav('painel')); await esperarModulo('#ini-visitas'); await P.waitForTimeout(300);
    const cel = await P.evaluate(() => { const v = document.getElementById('ini-visitas').getBoundingClientRect(); return { rolar: document.documentElement.scrollWidth <= window.innerWidth + 1, dentro: [...document.querySelectorAll('#ini-visitas .vm-row, #ini-visitas .vm-kpi, #ini-visitas .vm-g')].every(e => e.getBoundingClientRect().right <= v.right + 1) }; });
    chk(cel.rolar && cel.dentro, '390 px: Home sem rolagem lateral; cada projeto vira linha compacta dentro do quadro', JSON.stringify(cel));
    if (PRINTS) { await foto('vis-home-390-claro.png', '#ini-visitas'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-home-390-escuro.png', '#ini-visitas'); await tema('light'); }
    await P.setViewportSize({ width: 1366, height: 900 });
    // ---------- integração indisponível: mensagem + erro técnico + tentar de novo; nunca zero ----------
    py(`con.execute("DELETE FROM visita_dimensao"); con.execute("DELETE FROM visita_dia"); con.execute("DELETE FROM visita_coleta")
con.execute("INSERT INTO visita_coleta (fonte, de, ate, linhas, erro, por, fim) VALUES ('ga4', date('now','-1 day'), date('now','-1 day'), 0, 'Nada ligado: sem a chave da conta de serviço (ga4.conta_servico) e o site não respondeu <b>x</b>', 'automático', datetime('now'))")
con.execute("UPDATE configuracao SET valor='' WHERE chave IN ('ga4.propriedade','ga4.conta_servico')")`);
    await P.evaluate(() => { VM.t = 0; VM.ev = VM.pj = null; carregarPainel(); }); await P.waitForSelector('#ini-visitas .vm-erro', { timeout: 10000 }).catch(() => {});
    const er = await P.evaluate(() => ({ t: (document.querySelector('#ini-visitas .vm-erro') || {}).innerText || '', kpi: !!document.querySelector('#ini-visitas .vm-kpis'), b: !!document.querySelector('#ini-visitas .vm-erro b b'), tag: (document.getElementById('ini-vis-tag') || {}).textContent, tentar: !!document.querySelector('#ini-visitas [data-vm-tentar]') }));
    chk(/Não foi possível carregar os dados de visitas/.test(er.t) && /ga4\.conta_servico/.test(er.t) && /<b>x<\/b>/.test(er.t) && !er.b && !er.kpi && er.tentar && er.tag === 'desligado',
      'integração indisponível: mensagem, erro técnico (escapado), "Tentar de novo", sem indicadores zerados, "desligado" no título', JSON.stringify(er));
    if (PRINTS) { await foto('vis-home-erro-1366-claro.png', '#ini-visitas'); await tema('dark'); await P.waitForTimeout(100); await foto('vis-home-erro-1366-escuro.png', '#ini-visitas'); await tema('light'); }
    const n0 = await P.evaluate(() => VM.vez); await P.click('#ini-visitas [data-vm-tentar]'); await P.waitForTimeout(600);
    chk(await P.evaluate(n => VM.vez > n && !!document.querySelector('#ini-visitas .vm-erro'), n0), '"Tentar de novo" pede de novo (continua indisponível, sem zero)');
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
