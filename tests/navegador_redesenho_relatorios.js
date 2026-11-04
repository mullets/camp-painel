// Redesenho da Home, parte de baixo e relatórios (plano do Rafael, 05/11/2026, §10–17), no navegador de verdade (Playwright + Chromium):
//  §10 caminho do material: as 7 etapas com posição, quantidade e UNIDADE (estações/pastas/lotes, nunca somadas), maior acúmulo e próximo passo
//      em texto (não só cor), zero = "nada esperando" sem cor de problema, cada etapa abre a lista certa, percurso vertical no celular;
//  §11 folhas conferidas por dia: barras em HTML com dica (data, quantidade, unidade, origem), total e média, legenda "dia corrido", estado vazio
//      SEM gráfico falso, falha na coleta ≠ sem atividade, rótulos do mesmo tamanho em 1366 e 1920 px;
//  §12 visitas na Home: só o RESUMO (total, evolução, top 5, 7/30/90 dias, link "Ver análise completa de visitas"), falha ≠ zero;
//      §14 na tela completa: filtro por fundo e por arquiteto;
//  §15 qualidade: variação em PONTOS PERCENTUAIS frente a um dia nomeado; 0% em direitos = atenção;
//  §16 melhorias: ordem alfabética, o que conta;  §17 cobertura: numerador / denominador / % e "Não aplicável" com total zero;
//  390 px sem rolagem lateral; nenhum erro no console. Tira prints em 1920, 1366, 1024 e 390 px, claro e escuro (PRINTS=pasta).
// Uso (servidor PRÓPRIO, banco próprio; nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/rr/rr.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/rr/rr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8983)
//   CAMP_DB_PATH=/tmp/rr/rr.db CAMP_BASE=http://127.0.0.1:8983 PRINTS=/tmp/rr node tests/navegador_redesenho_relatorios.js
const { execFileSync } = require('child_process');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8983', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || '', PRE = process.env.PREFIXO || 'c-';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + String(det).slice(0, 400))); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------- semente: as visitas sintéticas do teste de visitas (números de teste, não da CAMP) ----------
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
// conferências espalhadas nos últimos dias (para o gráfico) e um retrato da qualidade de 8 dias atrás (para a variação em pontos percentuais)
const QB = JSON.parse(py(`
its = [r[0] for r in con.execute("SELECT codigo FROM item ORDER BY codigo LIMIT 20")]
for c, d in zip(its, [1, 1, 1, 2, 4, 4, 4, 4, 8, 10, 10, 12]):
    con.execute("UPDATE item SET revisao='conferida', revisado_em=datetime('now','-%d days','-1 hours') WHERE codigo=?" % d, (c,))
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
dia = (datetime.now(ZoneInfo("America/Sao_Paulo")).date() - timedelta(days=8)).isoformat()
con.execute("DELETE FROM qualidade_retrato WHERE fundo_codigo='*'")
con.execute("INSERT INTO qualidade_retrato (dia, fundo_codigo, folhas, com_imagem, com_codigo, com_titulo, com_direitos, indice, gravado_em) VALUES (?,?,?,?,?,?,?,?,datetime('now'))", (dia, '*', 10, 10, 10, 10, 10, 50.0))
print(json.dumps({"dia": dia}))
`));

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, deviceScaleFactor: 1 });
  const P = await ctx.newPage();
  P.on('console', m => { if (m.type() === 'error' && !/favicon|\/previa\?|exemplo\.test|\/api\/auth\/eu|status of 500|Failed to load resource/.test(((m.location() || {}).url || '') + m.text())) erros.push(m.text()); });
  P.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const tema = t => P.evaluate(t => { document.documentElement.dataset.theme = t; }, t);
  const foto = async (nome) => { if (!PRINTS) return; const vp = P.viewportSize();
    const alt = await P.evaluate(() => Math.ceil((document.querySelector('section.content.on') || document.body).scrollHeight + 200));
    await P.setViewportSize({ width: vp.width, height: Math.min(Math.max(vp.height, alt), 7000) }); await P.waitForTimeout(400);
    await P.screenshot({ path: path.join(PRINTS, PRE + nome) }); await P.setViewportSize(vp); await P.waitForTimeout(150); };
  const home = async () => { await P.evaluate(() => { nav('painel'); carregarPainel(); });
    await P.waitForSelector('#v-painel .ini-grid #ini-caminho .ini-flow', { timeout: 15000 });
    await P.waitForFunction(() => { const r = document.getElementById('ini-ritmo'), v = document.getElementById('ini-visitas'); return r && !r.querySelector('.rt-load') && (!v || (v.querySelector('.vm-sec,.vm-erro') && !v.querySelector('.vm-atualizando'))); }, null, { timeout: 15000 }).catch(() => {});
    await P.waitForTimeout(500); };
  try {
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await P.evaluate(() => { try { localStorage.setItem('camp.ajuda.painel', '1'); } catch (_) {} });
    await home();
    const pa = await P.evaluate(() => PAINEL_D);

    // ================= §10 o caminho do material =================
    const passos = await P.$$eval('#ini-caminho .ini-passo', ls => ls.map(l => { const b = l.querySelector('.ini-step'); return { id: b.id.replace('ini-passo-', ''), cls: l.className, un: b.dataset.unidade, q: b.querySelector('.q').textContent.trim(), u: b.querySelector('.u').textContent.trim(), w: (b.querySelector('.w') || {}).textContent || '', st: (b.querySelector('.st') || {}).textContent || '', x: (b.querySelector('.x') || {}).textContent || '', rota: b.dataset.iniRota, aria: b.getAttribute('aria-label') }; }));
    chk(passos.length === 7 && JSON.stringify(passos.map(p => p.id)) === '["digitalizar","qnap","campvision","importar","conferir","aprovar","publicar"]', 'as 7 etapas, na ordem Digitalizar → … → Publicar', JSON.stringify(passos.map(p => p.id)));
    const UN = { digitalizar: /^estaç(ão|ões) ligadas?$/, qnap: /^pastas?$/, campvision: /^pastas?$/, importar: /^lotes?$/, conferir: /^lotes?$/, aprovar: /^lotes?$/, publicar: /^lotes?$/ };
    chk(passos.every(p => UN[p.id].test(p.u) && p.u === p.un && p.w.length > 10 && new RegExp('^Passo \\d de 7, ').test(p.aria)), 'cada etapa: posição, quantidade, a UNIDADE por extenso (estações/pastas/lotes) e uma linha de descrição', JSON.stringify(passos.map(p => [p.id, p.q, p.u, p.w.slice(0, 20)])));
    chk(!/\d+\s*(itens|unidades)\b/.test(await P.locator('#ini-caminho').innerText()) && /os números não se somam/.test(await P.locator('#ini-caminho').innerText()), 'a tela diz que as unidades não se somam (nenhum total misturado)');
    const cam = Object.fromEntries(pa.caminho.map(c => [c.id, c]));
    const acum = passos.find(p => cam[p.id].estado === 'acumula'), prox = passos.find(p => cam[p.id].proxima);
    chk(!!acum && /maior acúmulo/.test(acum.st) && /stuck/.test(acum.cls), 'a etapa com maior acúmulo destacada em amarelo E com o texto "maior acúmulo"', JSON.stringify(acum));
    chk(!!prox && /próximo passo/.test(prox.st) && /(go|stuck)/.test(prox.cls), 'a próxima ação humana destacada ("próximo passo")', JSON.stringify(prox));
    const zeros = passos.filter(p => p.q === '0' && p.id !== 'digitalizar');
    chk(zeros.length > 0 && zeros.every(p => /zero/.test(p.cls) && /nada esperando/.test(p.x) && !/stuck|bloq/.test(p.cls) && !p.st), 'etapa com zero = "nada esperando", sem cor de problema', JSON.stringify(zeros));
    chk(/O que é cada passo\?/.test(await P.locator('#ini-t-cam').locator('xpath=..').innerText()), 'link "O que é cada passo?"');
    for (const [id, rota, filtro] of [['conferir', '#filas/conferir', 'conferir'], ['importar', '#filas/importar', 'importar'], ['aprovar', '#filas/aprovar', 'aprovar']]) {
      await P.click(`#ini-passo-${id}`); await P.waitForFunction(r => location.hash === r, rota, { timeout: 5000 }).catch(() => {});
      await P.waitForSelector(`#fila-chips [data-fila-filtro="${filtro}"]`, { timeout: 8000 }).catch(() => {});
      const st = await P.evaluate(f => ({ h: location.hash, f: FILA_FILTRO, chip: (document.querySelector(`#fila-chips [data-fila-filtro="${f}"]`) || {}).getAttribute && document.querySelector(`#fila-chips [data-fila-filtro="${f}"]`).getAttribute('aria-pressed') }), filtro);
      chk(st.h === rota && st.f === filtro && st.chip === 'true', `a etapa "${id}" abre a lista filtrada (${rota})`, JSON.stringify(st));
      await home();
    }
    // a cor nunca sozinha: toda etapa colorida tem texto de estado
    chk(passos.filter(p => /stuck|go|bloq/.test(p.cls)).every(p => p.st), 'toda etapa colorida tem o estado também em texto');

    // ================= §11 folhas conferidas por dia =================
    const rt = await P.evaluate(() => ({ h2: document.getElementById('ini-t-ritmo').textContent, cols: document.querySelectorAll('#ini-ritmo .rt-col').length, svg: document.querySelectorAll('#ini-ritmo svg').length, t: document.getElementById('ini-ritmo').innerText }));
    chk(rt.h2 === 'Folhas conferidas por dia — últimas 2 semanas', 'título descritivo "Folhas conferidas por dia — últimas 2 semanas"', rt.h2);
    chk(rt.cols === 14 && rt.svg === 0 && /Total no período/.test(rt.t) && /Média por dia de trabalho/.test(rt.t) && /dia corrido/.test(rt.t), 'gráfico em HTML (sem SVG) com 14 dias, total, média e a legenda "dia corrido"', JSON.stringify(rt).slice(0, 300));
    const ri = await P.evaluate(async () => (await fetch('/api/painel/ritmo?dias=14')).json());
    const totalEsp = ri.dias.reduce((a, d) => a + d.conferidas, 0);
    chk(new RegExp('Total no período\\s*' + totalEsp.toLocaleString('pt-BR')).test(rt.t), `total do período = soma real da API (${totalEsp})`, rt.t.slice(0, 200));
    const alturas = await P.$$eval('#ini-ritmo .rt-bar', b => b.map(x => parseFloat(x.style.height) || 0));
    chk(alturas.length === 14 && ri.dias.every((d, i) => (d.conferidas > 0) === (alturas[i] > 0)), 'barras com altura só onde houve conferência (nenhum pico inventado)', JSON.stringify(alturas));
    const col = P.locator('#ini-ritmo .rt-col').nth(ri.dias.findIndex(d => d.conferidas > 0));
    await col.scrollIntoViewIfNeeded(); await col.hover(); await P.waitForTimeout(150);
    const tip = await col.locator('.rt-tip').evaluate(t => ({ v: getComputedStyle(t).display !== 'none', s: t.textContent }));
    chk(tip.v && /\d\d\/\d\d\/\d{4}/.test(tip.s) && /folhas? conferidas?/.test(tip.s) && /origem/.test(tip.s), 'dica ao passar o mouse: data, quantidade, unidade e origem', JSON.stringify(tip));
    await P.mouse.move(5, 5); await P.focus('#ini-ritmo .rt-col >> nth=12'); await P.keyboard.press('Tab'); await P.waitForTimeout(100);
    chk(await P.$eval('#ini-ritmo .rt-col.hoje .rt-tip', t => getComputedStyle(t).display !== 'none' && /hoje/.test(t.textContent) && document.activeElement === t.parentElement).catch(() => false), 'dica também pelo teclado (Tab até a barra de hoje)');
    const tam = () => P.evaluate(() => [...document.querySelectorAll('#ini-ritmo .rt-x span, #ini-ritmo .rt-y span')].filter(e => getComputedStyle(e).visibility !== 'hidden').map(e => getComputedStyle(e).fontSize));
    const t1366 = await tam();
    await P.setViewportSize({ width: 1920, height: 1080 }); await P.waitForTimeout(400);
    const t1920 = await tam();
    chk(t1366.length && [...new Set(t1366)].length === 1 && [...new Set(t1920)].length === 1 && t1366[0] === t1920[0] && parseFloat(t1366[0]) >= 12, 'rótulos do gráfico com o MESMO tamanho em 1366 e 1920 px (≥ 12 px, não esticam)', JSON.stringify([[...new Set(t1366)], [...new Set(t1920)]]));
    await P.setViewportSize({ width: 1366, height: 900 });
    // sem atividade: estado vazio útil, sem gráfico
    await P.route('**/api/painel/ritmo*', async r => { const resp = await r.fetch(); const j = await resp.json(); j.dias.forEach(d => { d.conferidas = 0; }); j.media_conferidas = 0; j.dias_para_zerar = null; await r.fulfill({ response: resp, json: j }); });
    await home();
    const vz = await P.evaluate(() => ({ t: document.getElementById('ini-ritmo').innerText, g: document.querySelectorAll('#ini-ritmo .rt-col, #ini-ritmo svg, #ini-ritmo .rt-kpis').length, bt: !!document.querySelector('#ini-ritmo .rt-vazio [data-ini-rota]') }));
    chk(/Nenhuma folha conferida no período selecionado/.test(vz.t) && vz.g === 0 && vz.bt, 'sem atividade: "Nenhuma folha conferida no período selecionado" + atalho, SEM gráfico falso', JSON.stringify(vz));
    if (PRINTS) await P.locator('#ini-ritmo').screenshot({ path: path.join(PRINTS, PRE + 'ritmo-vazio-1366-claro.png') });
    await P.unroute('**/api/painel/ritmo*');
    // falha na coleta ≠ sem atividade
    await P.route('**/api/painel/ritmo*', r => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'banco ocupado (teste)' }) }));
    await home();
    const fe = await P.evaluate(() => ({ t: document.getElementById('ini-ritmo').innerText, tentar: !!document.querySelector('#ini-ritmo [data-rt-tentar]'), g: document.querySelectorAll('#ini-ritmo .rt-col').length }));
    chk(/Não foi possível carregar o ritmo/.test(fe.t) && !/Nenhuma folha conferida/.test(fe.t) && fe.tentar && fe.g === 0 && !/\b0\b/.test(fe.t), 'falha na coleta: mensagem de erro + "Tentar de novo" (não vira "sem atividade" nem zero)', JSON.stringify(fe));
    if (PRINTS) await P.locator('#ini-ritmo').screenshot({ path: path.join(PRINTS, PRE + 'ritmo-erro-1366-claro.png') });
    await P.unroute('**/api/painel/ritmo*');
    await P.click('#ini-ritmo [data-rt-tentar]'); await P.waitForSelector('#ini-ritmo .rt-col', { timeout: 8000 }).catch(() => {});
    chk(await P.$$eval('#ini-ritmo .rt-col', c => c.length) === 14, '"Tentar de novo" busca de novo e mostra o gráfico');

    // ================= §12 visitas na Home: só o resumo =================
    await home();
    const vh = await P.evaluate(() => { const v = document.getElementById('ini-visitas'); return { t: v.innerText, rows: v.querySelectorAll('.vm-row').length, todos: !!v.querySelector('[data-vm-todos]'), csv: !!v.querySelector('[data-vm-csv]'), ni: !!v.querySelector('.vm-ni'), busca: !!v.querySelector('[data-vm-busca]'),
      per: [...v.querySelectorAll('[data-vm-per] option')].map(o => o.value), ir: (v.querySelector('[data-vm-ir]') || {}).textContent || '', antes: v.closest('section').previousElementSibling === document.getElementById('ini-ritmo').closest('section') }; });
    chk(vh.rows === 5 && !vh.todos && !vh.csv && !vh.ni && !vh.busca, 'Home: só o top 5 (sem "Ver todos", busca, CSV nem "não identificadas")', JSON.stringify(vh).slice(0, 300));
    chk(JSON.stringify(vh.per) === '["7d","30d","90d"]' && /Visitas no período/.test(vh.t) && /sessões/.test(vh.t) && /Última sincronização: \d\d\/\d\d\/\d{4}/.test(vh.t) && !!(await P.$('#ini-visitas .vm-res .vm-g')), 'Home: total de visitas (sessões) com a definição, evolução ao lado, filtro 7/30/90 e a data da sincronização', JSON.stringify(vh).slice(0, 400));
    chk(/Ver análise completa de visitas/.test(vh.ir) && vh.antes, 'Home: link "Ver análise completa de visitas" e o bloco logo abaixo do gráfico de folhas');
    const top5 = await P.$$eval('#ini-visitas .vm-row', r => r.map(x => x.dataset.vmProj));
    chk(JSON.stringify(top5) === JSON.stringify(ESP.top30.slice(0, 5).map(x => x[0])), 'top 5 = os 5 mais visitados de verdade em 30 dias', JSON.stringify(top5));
    await P.selectOption('#ini-visitas [data-vm-per]', '7d'); await P.waitForFunction(() => VM.ev && VM.ev.periodo === '7d' && !VM.carregando, null, { timeout: 8000 }); await P.waitForTimeout(200);
    chk(JSON.stringify(await P.$$eval('#ini-visitas .vm-row', r => r.map(x => x.dataset.vmProj))) === JSON.stringify(ESP.top7.slice(0, 5).map(x => x[0])), 'filtro 7 dias muda o resumo e o top 5 juntos');
    await P.selectOption('#ini-visitas [data-vm-per]', '30d'); await P.waitForFunction(() => VM.ev && VM.ev.periodo === '30d' && !VM.carregando, null, { timeout: 8000 });
    // falha ≠ zero
    await P.route('**/api/visitas/evolucao*', r => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'GA fora (teste)' }) }));
    await P.evaluate(() => { VM.t = 0; VM.ev = VM.pj = null; }); await home();
    const vf = await P.evaluate(() => ({ t: document.getElementById('ini-visitas').innerText, kpi: !!document.querySelector('#ini-visitas .vm-res-tot'), rows: document.querySelectorAll('#ini-visitas .vm-row').length }));
    chk(/Dados de audiência temporariamente indisponíveis/.test(vf.t) && !vf.kpi && vf.rows === 0 && !/Visitas no período\s*0/.test(vf.t) && /Tentar de novo/.test(vf.t), 'Home: falha nas visitas = "Dados de audiência temporariamente indisponíveis", sem indicador zerado', JSON.stringify(vf).slice(0, 300));
    if (PRINTS) await P.locator('#ini-visitas').screenshot({ path: path.join(PRINTS, PRE + 'visitas-home-erro-1366-claro.png') });
    await P.unroute('**/api/visitas/evolucao*');
    await P.evaluate(() => { VM.t = 0; VM.ev = VM.pj = null; }); await home();
    await P.click('#ini-visitas [data-vm-ir]'); await P.waitForFunction(() => location.hash === '#visitas', null, { timeout: 5000 }).catch(() => {});
    await P.waitForFunction(() => document.querySelector('#vis-modulo .vm-sec') && !document.querySelector('#vis-modulo .vm-atualizando'), null, { timeout: 10000 }).catch(() => {});
    const vc = await P.evaluate(() => ({ h: location.hash, todos: !!document.querySelector('#vis-modulo [data-vm-todos]'), csv: !!document.querySelector('#vis-modulo [data-vm-csv]'), livre: [...document.querySelectorAll('#vis-modulo [data-vm-per] option')].some(o => o.value === 'livre'), rows: document.querySelectorAll('#vis-modulo .vm-row').length }));
    chk(vc.h === '#visitas' && vc.todos && vc.csv && vc.livre && vc.rows === 10, '"Ver análise completa de visitas" abre a tela com o módulo completo (10, ver todos, CSV, intervalo personalizado)', JSON.stringify(vc));
    // §14 filtros por fundo e arquiteto no ranking completo
    await P.click('#vis-modulo [data-vm-todos="1"]'); await P.waitForSelector('#vis-modulo [data-vm-fundo]', { timeout: 8000 }).catch(() => {});
    await P.selectOption('#vis-modulo [data-vm-fundo]', 'F026'); await P.waitForFunction(() => VM.pj && VM.pj.fundo === 'F026', null, { timeout: 8000 }).catch(() => {}); await P.waitForTimeout(300);
    const ff = await P.evaluate(() => ({ c: [...document.querySelectorAll('#vis-modulo .vm-row')].map(r => r.dataset.vmProj), csv: document.querySelector('#vis-modulo [data-vm-csv]').getAttribute('href') }));
    chk(ff.c.length >= 2 && ff.c.every(c => c.startsWith('F026-')) && /fundo=F026/.test(ff.csv), 'tela completa: filtro por fundo (a lista e o CSV)', JSON.stringify(ff));
    await P.selectOption('#vis-modulo [data-vm-fundo]', ''); await P.waitForTimeout(400);
    await P.selectOption('#vis-modulo [data-vm-autor]', 'Sylvio Sawaya'); await P.waitForFunction(() => VM.pj && VM.pj.autor === 'Sylvio Sawaya', null, { timeout: 8000 }).catch(() => {}); await P.waitForTimeout(300);
    chk(JSON.stringify(await P.$$eval('#vis-modulo .vm-row', r => r.map(x => x.dataset.vmProj))) === '["F026-P0003"]', 'tela completa: filtro por arquiteto (autoria cadastrada)');
    await P.selectOption('#vis-modulo [data-vm-autor]', ''); await P.waitForTimeout(400);
    // "sem comparação" por projeto: intervalo cujo período anterior não tem dados
    await P.selectOption('#vis-modulo [data-vm-per]', 'livre'); await P.fill('#vis-modulo [data-vm-de]', ESP.sem_hist_ate); await P.fill('#vis-modulo [data-vm-ate]', ESP.ontem); await P.click('#vis-modulo [data-vm-aplicar]');
    await P.waitForFunction(() => VM.ev && VM.ev.periodo === 'livre' && !VM.carregando, null, { timeout: 8000 }).catch(() => {}); await P.waitForTimeout(300);
    const sc = await P.$$eval('#vis-modulo .vm-row .vm-var', v => v.map(x => x.textContent));
    chk(sc.length > 0 && sc.every(x => x === 'sem comparação'), 'por projeto: "sem comparação" quando o período anterior não tem dados completos (nada de seta)', JSON.stringify(sc.slice(0, 3)));
    // voltar à Home recoloca o resumo no padrão (30 dias, top 5)
    await home();
    chk(await P.evaluate(() => VM.periodo === '30d' && document.querySelectorAll('#ini-visitas .vm-row').length === 5 && !VM.todos), 'de volta à Home: resumo nos 30 dias e top 5 (o intervalo livre fica na tela completa)');

    // ================= §15 qualidade da base =================
    const qb = await P.evaluate(() => document.getElementById('ini-qualidade').innerText);
    chk(new RegExp(`(subiu|caiu) [\\d,]+ pontos? percentua(l|is) frente a ${QB.dia.slice(8, 10)}/${QB.dia.slice(5, 7)}`).test(qb) && !/(subiu|caiu) [\d,]+%/.test(qb), 'índice geral com a variação em PONTOS PERCENTUAIS frente ao dia nomeado (não "%")', qb.slice(0, 300));
    const crit = await P.$$eval('#ini-qualidade .qb-crit label', ls => ls.map(l => ({ r: l.querySelector('.qb-rot').textContent, v: l.querySelector('.qb-v').textContent, p: !!l.querySelector('progress'), z: l.classList.contains('qb-zero') })));
    chk(crit.length === 4 && crit.every(c => /%$/.test(c.v) && c.p), 'os 4 critérios com o % ao lado do rótulo e a barra', JSON.stringify(crit));
    const dir = crit.find(c => /direitos/.test(c.r));
    chk(dir && (dir.v !== '0%' || (dir.z && /atenção/.test(dir.r))), '0% em "Com direitos definidos" aparece como atenção', JSON.stringify(dir));
    chk(/Como cada medida é calculada/.test(qb) && /folhas de projetos ativos/.test(qb) && (await P.$$eval('#ini-qualidade .qb-def dt', d => d.length)) === 5, 'definição de cada critério e do universo');
    chk((await P.$$eval('#ini-qualidade > .pb > .qb-fundos li', l => l.length)) <= 3, 'poucos fundos priorizados (no máximo 3) + "Ver todos"');

    // ================= §16 melhorias =================
    const nomes = await P.$$eval('#ini-melhorias .mh-lista li > span:first-child', s => s.map(x => x.textContent));
    chk(JSON.stringify(nomes) === JSON.stringify([...nomes].sort((a, b) => a.localeCompare(b, 'pt-BR'))) && /Criar, importar e sincronizar com o site não contam/.test(await P.locator('#ini-melhorias').innerText()), 'melhorias: ordem alfabética (não é ranking) e o que conta', JSON.stringify(nomes));

    // ================= §17 cobertura =================
    const cob = await P.$$eval('#ini-cobertura .ini-prog-row', rs => rs.map(r => ({ id: r.dataset.cob, n: r.querySelector('.ini-cob-n').textContent, pct: (r.querySelector('.ini-cob-pct') || {}).textContent, w: parseFloat((r.querySelector('.ini-bar i') || { style: {} }).style.width) })));
    const ns = pa.no_site, esp = { folhas: [ns.folhas.no_ar, ns.folhas.total, 'folhas publicadas'], projetos: [ns.projetos.no_ar, ns.projetos.total, 'projetos com página publicada'], fundos: [ns.fundos.no_ar, ns.fundos.total, 'fundos com página publicada'] };
    chk(cob.length === 3 && cob.every(c => { const [a, b, u] = esp[c.id], p = 100 * a / b; return c.n.includes(`${a.toLocaleString('pt-BR')} de ${b.toLocaleString('pt-BR')} ${u}`) && c.pct === (p > 0 && p < 1 ? p.toFixed(1).replace('.', ',') + '%' : Math.round(p) + '%') && Math.abs(c.w - p) < 0.1; }),
      'cobertura: Folhas, Projetos e Fundos com página, cada um com publicado / total / % / barra e a unidade por extenso', JSON.stringify([cob, esp]));
    chk(/não é erro/.test(await P.locator('#ini-cobertura [data-cob="projetos"]').innerText()) || !ns.projetos.sem_folhas, 'projetos sem folhas: nota do denominador, sem chamar de erro');
    await P.route(/\/api\/painel(\?|$)/, async r => { const resp = await r.fetch(); const j = await resp.json(); j.no_site.fundos = { no_ar: 0, total: 0 }; await r.fulfill({ response: resp, json: j }); });
    await home();
    chk(/Não aplicável/.test(await P.locator('#ini-cobertura [data-cob="fundos"]').innerText()) && !(await P.$('#ini-cobertura [data-cob="fundos"] .ini-bar')), 'total zero = "Não aplicável" (sem 0% e sem barra)');
    await P.unroute(/\/api\/painel(\?|$)/);
    await P.click('#ini-cobertura [data-cob="projetos"] .ini-cob-ir'); await P.waitForTimeout(400);
    chk(await P.evaluate(() => location.hash) === '#projetos/nao_publicado', 'link para a lista do que falta (projetos não publicados)');

    // ================= prints e 390 px =================
    await home();
    for (const [w, h] of [[1920, 1080], [1366, 900], [1024, 900], [390, 844]]) {
      await P.setViewportSize({ width: w, height: h }); await P.evaluate(() => { VM.t = 0; }); await home();
      const lat = await P.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
      chk(lat, `${w} px: Home sem rolagem lateral`);
      if (w === 390) {
        const vert = await P.$$eval('#ini-caminho .ini-step', b => b.map(x => Math.round(x.getBoundingClientRect().left)));
        chk(new Set(vert).size === 1, '390 px: o caminho vira percurso vertical', JSON.stringify(vert));
        const alvo = await P.$$eval('#ini-caminho .ini-step, #ini-qualidade .qb-fundos button', b => b.every(x => x.getBoundingClientRect().height >= 44));
        chk(alvo, '390 px: alvos de toque com 44 px ou mais');
      }
      if (w === 1920) chk(await P.$$eval('#ini-caminho .ini-step', b => new Set(b.map(x => Math.round(x.getBoundingClientRect().top))).size === 1), '1920 px: as 7 etapas lado a lado, ligadas');
      for (const t of ['claro', 'escuro']) { await tema(t === 'claro' ? 'light' : 'dark'); await P.waitForTimeout(150); await foto(`home-${w}-${t}.png`); }
      await tema('light');
      await P.evaluate(() => nav('visitas')); await P.waitForFunction(() => document.querySelector('#vis-modulo .vm-sec') && !document.querySelector('#vis-modulo .vm-atualizando'), null, { timeout: 10000 }).catch(() => {}); await P.waitForTimeout(400);
      chk(await P.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${w} px: tela Visitas ao site sem rolagem lateral`);
      for (const t of ['claro', 'escuro']) { await tema(t === 'claro' ? 'light' : 'dark'); await P.waitForTimeout(150); await foto(`visitas-${w}-${t}.png`); }
      await tema('light');
    }
    // acessibilidade mínima: cada etapa tem nome acessível e o gráfico tem alternativa em tabela
    await P.setViewportSize({ width: 1366, height: 900 }); await home();
    chk(await P.$$eval('#ini-ritmo .rt-num tbody tr', r => r.length) === 14 && await P.$$eval('#ini-ritmo .rt-col', c => c.every(x => x.getAttribute('aria-label') && x.tabIndex === 0)), 'gráfico com alternativa textual (tabela "Ver os números" e rótulo em cada barra, focável)');
    const tela = await P.locator('#v-painel').innerText();
    for (const ruim of ['undefined', 'NaN', '[object Object]', 'null%']) chk(!tela.includes(ruim), `Home sem "${ruim}"`);
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
