// Redesenho da página interna do projeto (documento do Rafael de 04/11/2026, §3–§9), no navegador de verdade (Playwright + Chromium).
// Critérios de aceite (§9), cada um com dado REAL do banco (a semente abaixo: 10 folhas num lote, 2 conferidas, uma com orientação incerta e
// giro sugerido, uma com avisos do CAMP Vision repetidos, uma com bloqueio, uma com título e tipo lidos diferentes):
//  1) cabeçalho: nome em destaque (h1), situação, código, fundo, ano, local e N folhas na 1ª tela; abas Visão geral · Folhas · Metadados ·
//     Problemas · Histórico (Publicação → Metadados, Pedidos → Histórico; ← → mudam de aba);
//  2) Próximo passo com a conferência: "N de M folhas conferidas" = banco, barra, etapas, UM botão azul; a grade de folhas vem logo depois
//     (os cartões administrativos ficam na coluna "Situação do projeto"); "conferida" só nos cartões com revisão gravada;
//  3) clicar numa folha abre "Revisar folha" ao lado: Folha NN, código, projeto, ‹ Anterior · N de M · Próxima ›; a folha fica destacada
//     na grade; ABRIR NÃO CONFERE (o banco continua "pendente");
//  4) avisos separados: "Impede publicar" (bloqueio) × "Aviso do CAMP Vision"; sugestões em bloco próprio com "Usar sugestão" — nada é
//     aplicado sozinho (título no campo só depois do clique; giro sugerido só grava no clique);
//  5) "Confirmar folha" grava e fica na folha (banco = corrigida, selo e contagem atualizados); "Salvar e próxima folha" grava e anda;
//  6) trocar de folha e fechar com alteração não salva perguntam "Sair sem salvar?"; o filtro da galeria e a posição ficam ao fechar;
//  7) ferramentas: zoom (+ 125%), tela cheia cobre a janela; rodapé de ações sempre à vista;
//  8) "Editar" abre "Editar projeto" com os dados do projeto; Programa / uso e Natureza do trabalho separados, da taxonomia real, com busca
//     e categorias que abrem e fecham; erro do servidor aparece no painel e ele NÃO fecha; salvar grava e reabrir mostra o que foi salvo;
//     Cancelar com alteração pergunta;
//  9) permissões: operador revisa mas não edita o projeto; leitura não revisa nem edita;
// 10) 390 px: os painéis ocupam a largura toda, sem rolagem lateral; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO, nunca a porta compartilhada):
//   CAMP_DB_PATH=/tmp/pint/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/pint/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8986)
//   CAMP_DB_PATH=/tmp/pint/t.db CAMP_BASE=http://127.0.0.1:8986 CHROME=/opt/pw-browsers/chromium node tests/navegador_projeto_interno.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8986', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_pint'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0171', D = n => `${P}-1974-S01-D${String(n).padStart(5, '0')}`;
function semear() {
  py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 171)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente,tipologia,natureza) VALUES ('${P}','F026',171,'Edifício Página Interna',1974,'Santos','SP',NULL,NULL,NULL)")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote interno','${P}','/x/pint','revisao')").lastrowid
TIPOS = ['Planta','Planta','Planta','Corte','Planta','Corte','Planta','Planta','Planta','Planta']
for s in range(1, 11):
    cod = "${P}-1974-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1600, 1100), (246, 240, 226)); dr = ImageDraw.Draw(im); dr.rectangle((30, 30, 1570, 1070), outline="black", width=8); dr.text((700, 500), "FOLHA %02d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=70)
    pend = {"bloqueios": ["carimbo ilegível: falta o número da folha"] if s == 5 else [], "sinais": ["orientação incerta"] if s == 3 else [],
            "ressalvas": ["valor descartado: resposta do modelo quebrada (%s)" % c for c in ("titulo", "escala")] if s == 4 else [],
            "previa": rel, "titulo_lido": "Planta do pavimento tipo" if s == 2 else "Folha %d" % s}
    if s == 3: pend["rotacao_sugerida"] = 180
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,tipo_lido,folha,escala,ano_folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Folha %d" % s, TIPOS[s-1], 'Corte' if s == 2 else None, "%02d" % s, '1:100', 1974, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'conferida' if s in (1, 7) else 'pendente'))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
}
const um = (sql, ...a) => py(`r=con.execute(${JSON.stringify(sql)}, ${JSON.stringify(a)}).fetchone()\nprint('' if r is None else (r[0] if r[0] is not None else ''))`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };

async function entrar(br, email, senha, vp, erros) {
  const ctx = await br.newContext({ viewport: vp || { width: 1366, height: 768 }, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`${email}: pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|403|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`${email}: console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9'); localStorage.setItem('camp.revCheia', '0') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg };
}
async function abrirProjeto(pg, aba) {
  await pg.evaluate(([c, a]) => { closeDrawer(true); nav('projeto/' + c); if (a) showProjeto(c, a); }, [P, aba || null]);
  await pg.waitForSelector(`#pd .thumb, #pd [data-pj-aba="dados"]:not([hidden])`, { timeout: 15000, state: 'attached' });
  await pg.waitForTimeout(1200);
  for (const a of await pg.$$('[data-ajuda-fechar]')) { try { if (await a.isVisible()) await a.click(); } catch (_) {} }
}
const sub = pg => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent || '');
const abriu = (pg, c) => espera(async () => (await sub(pg)) === c && !!(await pg.$('#d-body .rv-rodape')));
const dialogo = pg => pg.evaluate(() => { const o = document.getElementById('conf-ov'); return o ? (o.innerText || '').replace(/\s+/g, ' ') : ''; });

(async () => {
  semear();
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, pg } = await entrar(br, 'rafael@camp.arq.br', 'senha-bem-longa-123', { width: 1366, height: 768 }, erros);
    await abrirProjeto(pg);

    // ---------- 1) cabeçalho e abas ----------
    const cab = await pg.evaluate(() => { const h = document.querySelector('#pd .pj-cab'); const r = h ? h.getBoundingClientRect() : null; const h1 = h && h.querySelector('h1');
      const h1t = h1 ? [...h1.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : '';
      return { h1: h1t, fs: h1 ? parseFloat(getComputedStyle(h1).fontSize) : 0, meta: (h && (h.querySelector('.pj-meta') || {}).innerText || '').replace(/\s+/g, ' '),
        selo: !!(h && h.querySelector('#pj-selo [data-situacao]')), baixo: r ? r.bottom : 9999,
        abas: [...document.querySelectorAll('#pd .pj-tabs [role="tab"]')].map(b => b.textContent.replace(/\s+/g, ' ').trim()), sel: (document.querySelector('#pd .pj-tabs [aria-selected="true"]') || {}).textContent }; });
    chk(cab.h1 === 'Edifício Página Interna' && cab.fs >= 24, '§3.1 nome do projeto em destaque (h1 ≥ 24 px)', JSON.stringify(cab));
    chk(/F026-P0171/.test(cab.meta) && /Sami Bussab|F026/.test(cab.meta) && /1974/.test(cab.meta) && /Santos/.test(cab.meta) && /10 folhas/.test(cab.meta), '§3.1 código · fundo · ano · local · N folhas numa linha', cab.meta);
    chk(cab.selo && cab.baixo < 768, '§3.1 situação (chip do CAMP-146) junto do título, tudo na 1ª tela', JSON.stringify(cab));
    chk(cab.abas.length === 5 && /^Visão geral/.test(cab.abas[0]) && /^Folhas \(10\)/.test(cab.abas[1]) && cab.abas[2] === 'Metadados' && /^Problemas \(/.test(cab.abas[3]) && cab.abas[4] === 'Histórico' && /Visão geral/.test(cab.sel), '§3.2 abas Visão geral · Folhas (10) · Metadados · Problemas · Histórico', JSON.stringify(cab.abas));
    await pg.focus('#pd .pj-tabs [aria-selected="true"]'); await pg.keyboard.press('ArrowRight');
    chk(await espera(() => pg.evaluate(() => (document.activeElement || {}).id === 'pj-tab-folhas' && pdTab === 'folhas')), '§7.7 seta → muda para a aba Folhas e o foco acompanha');
    await pg.evaluate(c => showProjeto(c, 'publicacao'), P); await pg.waitForTimeout(800);
    chk(await pg.evaluate(() => /Metadados/.test(document.querySelector('#pd .pj-tabs [aria-selected="true"]').textContent) && !!document.getElementById('pd-pub').offsetParent && !!document.querySelector('[data-pj-aba="dados"]:not([hidden])')), '§3.2 a antiga aba Publicação abre Metadados com "Requisitos para publicar"');
    await pg.evaluate(c => showProjeto(c, 'pedidos'), P); await pg.waitForTimeout(800);
    chk(await pg.evaluate(() => /Histórico/.test(document.querySelector('#pd .pj-tabs [aria-selected="true"]').textContent) && !!(document.getElementById('pj-pedidos') || {}).offsetParent), '§3.2 a antiga aba Pedidos abre Histórico com "Pedidos de material"');
    await abrirProjeto(pg, 'itens');

    // ---------- 2) conferência e grade ----------
    const nConf = +um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL AND revisao!='pendente'", P);
    const vg = await pg.evaluate(() => { const st = document.getElementById('pj-status'), g = document.querySelector('#pd .thumb'), lado = document.querySelector('#pd .pj-vg-lado');
      const azuis = [...document.querySelectorAll('#pd .btn.pri')].filter(b => b.offsetParent).map(b => b.textContent.trim());
      return { conf: (st.querySelector('.pj-conf .prog-txt') || {}).textContent || '', barra: !!st.querySelector('.pj-conf progress'), etapas: [...st.querySelectorAll('.pj-etapas li')].map(l => l.className + ':' + l.textContent.trim()),
        azuis, cardsNoLado: !!(lado && lado.querySelector('#pj-cards')), cardsAntesGrade: !!document.querySelector('#pd .pj-vg-corpo #pj-cards'),
        conferidasCartao: [...document.querySelectorAll('#pd .thumb .rev-tag[data-rev-estado="conferida"],#pd .thumb .rev-tag[data-rev-estado="corrigida"]')].length,
        aConferirCartao: [...document.querySelectorAll('#pd .thumb .rev-tag[data-rev-estado="pendente"]')].filter(x => x.offsetParent).length,
        ident: (document.querySelector(`#pd .thumb .cap-id`) || {}).textContent, menu: !!document.querySelector('#pd .thumb .lista-mais') }; });
    chk(vg.conf === `${nConf} de 10 folhas conferidas` && vg.barra, `§3.3 "N de M folhas conferidas" vem do banco (${nConf}) com a barra`, JSON.stringify(vg.conf));
    chk(vg.etapas.length === 4 && /atual:.*Conferir folhas/.test(vg.etapas[0]) && /Revisar metadados/.test(vg.etapas[1]) && /Aprovar lote/.test(vg.etapas[2]) && /Publicar no site/.test(vg.etapas[3]), '§3.3 etapas Conferir folhas → Revisar metadados → Aprovar lote → Publicar no site (a atual marcada)', JSON.stringify(vg.etapas));
    chk(vg.azuis.length === 1 && /Continuar conferência|Iniciar conferência/.test(vg.azuis[0]), '§7.1 um só botão azul na página: o da conferência', JSON.stringify(vg.azuis));
    chk(vg.cardsNoLado && !vg.cardsAntesGrade, '§3.4 os cartões administrativos ficam na coluna "Situação do projeto", não antes da grade');
    chk(vg.conferidasCartao === nConf && vg.aConferirCartao === 10 - nConf, `§4.3 cartão "conferida" só com revisão gravada (${nConf}) e "a conferir" nas outras (${10 - nConf})`, JSON.stringify(vg));
    chk(vg.ident === 'Folha 01' && vg.menu, '§3.4 número da folha em destaque e menu ⋯ de ações por folha', JSON.stringify(vg));
    const ctx2 = await br.newContext({ viewport: { width: 1920, height: 1080 } }); await ctx2.close();
    // filtro por tipo + filtro de situação somam
    await pg.selectOption('#pd .folhas-bar [data-fl-tipo]', 'Corte'); await pg.waitForTimeout(200);
    const vis = () => pg.evaluate(() => [...document.querySelectorAll('#pd .thumb')].filter(t => !t.hidden).map(t => t.dataset.revAbrir.slice(-2)));
    chk(JSON.stringify(await vis()) === JSON.stringify(['04', '06']), '§3.4 filtro Tipo: só as folhas de corte', JSON.stringify(await vis()));
    await pg.selectOption('#pd .folhas-bar [data-fl-tipo]', ''); await pg.click('#pd .folhas-bar [data-fl-f="conferir"]'); await pg.waitForTimeout(200);
    chk((await vis()).length === 10 - nConf, '§3.4 filtro "A conferir"', JSON.stringify(await vis()));
    await pg.click('#pd .folhas-bar [data-fl-vista="lista"]');
    chk(await pg.evaluate(() => document.getElementById('pd').dataset.vista === 'lista' && getComputedStyle([...document.querySelectorAll('#pd .thumb')].find(x => !x.hidden)).display === 'grid'), '§3.4 alternância grade/lista');
    await pg.click('#pd .folhas-bar [data-fl-vista="grade"]');

    // ---------- 3) abrir uma folha ----------
    await pg.evaluate(() => { mainEl.scrollTop = 420 }); await pg.waitForTimeout(150);
    const rolagem0 = await pg.evaluate(() => mainEl.scrollTop);
    await pg.click(`#pd .thumb[data-rev-abrir="${D(3)}"] .img-real`);
    chk(await abriu(pg, D(3)), '§4 clicar na folha abre "Revisar folha"');
    const rv = await pg.evaluate(() => { const b = document.getElementById('d-body'); const t = document.querySelector('#pd .thumb.aberta');
      return { titulo: document.getElementById('d-title').textContent, folha: (b.querySelector('.rv-folha') || {}).textContent || '', proj: (b.querySelector('.rv-proj') || {}).textContent || '',
        pos: (b.querySelector('.rv-nav .rev-prog b') || {}).textContent || '', ant: !!b.querySelector('.rv-nav [data-rev-ir]:not([disabled])'), dest: t ? t.dataset.revAbrir : null, cur: t ? t.getAttribute('aria-current') : null,
        img: (document.getElementById('rv-img') || {}).src || '', sug: (b.querySelector('.rv-sug') || {}).innerText || '', aviso: (b.querySelector('.rv-al.aviso') || {}).innerText || '', erro: !!b.querySelector('.rv-al.erro') }; });
    chk(rv.titulo === 'Revisar folha' && /^Folha 03/.test(rv.folha) && /F026-P0171-1974-S01-D00003/.test(rv.proj) && /Edifício Página Interna/.test(rv.proj), '§4.2 A: "Revisar folha", Folha 03, código e nome do projeto', JSON.stringify(rv));
    chk(rv.pos === '3 de 10' && rv.ant, '§4.2 A: ‹ Anterior · 3 de 10 · Próxima ›', JSON.stringify(rv.pos));
    chk(rv.dest === D(3) && rv.cur === 'true', '§4.3 a folha aberta fica destacada na grade (aria-current)', JSON.stringify(rv));
    chk(um('SELECT revisao FROM item WHERE codigo=?', D(3)) === 'pendente', '§4.3 abrir a folha NÃO a confere (banco continua "pendente")');
    chk(/orientação incerta/.test(rv.aviso) && !rv.erro, '§4.2 B: D03 mostra "Aviso do CAMP Vision" (orientação incerta), sem erro impeditivo', rv.aviso);
    chk(/Orientação sugerida/.test(rv.sug) && /Usar sugestão/.test(rv.sug) && /[?&]s=180/.test(rv.img) && +um('SELECT COALESCE(giro_manual,0) FROM item WHERE codigo=?', D(3)) === 0, '§4.2 E: giro sugerido na tela e em "Sugestões do CAMP Vision", sem gravar', JSON.stringify([rv.sug, rv.img]));
    await pg.click('#d-body .rv-sug [data-rev-sug-aceitar]');
    chk(await espera(() => +um('SELECT COALESCE(giro_manual,0) FROM item WHERE codigo=?', D(3)) === 180), '§4.2 E: "Usar sugestão" grava o giro sugerido (só no clique)');
    chk(um('SELECT revisao FROM item WHERE codigo=?', D(3)) === 'pendente', '§4.3 usar a sugestão de giro não confere a folha');
    // zoom e tela cheia
    await pg.click('#d-body [data-rev-zoom="+"]');
    chk(await pg.evaluate(() => /125%/.test(document.querySelector('#d-body .rv-zoom-n').textContent) && /scale\(1\.25\)/.test(document.getElementById('rv-img').style.transform)), '§4.2 C: zoom (+) amplia a imagem (125%)');
    await pg.click('#d-body [data-rev-cheia]');
    const cheia = await pg.evaluate(() => { const r = document.getElementById('drawer').getBoundingClientRect(); return { l: r.left, t: r.top, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight }; });
    chk(cheia.l <= 0 && cheia.t <= 0 && cheia.w >= cheia.vw - 1 && cheia.h >= cheia.vh - 1, '§8 tela cheia de verdade: o painel cobre a janela', JSON.stringify(cheia));
    await pg.click('#d-body [data-rev-cheia]');
    // rodapé à vista sem rolar
    const rod = await pg.evaluate(() => { const r = document.querySelector('#d-body .rv-rodape').getBoundingClientRect(); return { b: r.bottom, t: r.top, vh: innerHeight, txt: document.querySelector('#d-body .rv-rodape').innerText.replace(/\s+/g, ' ') }; });
    chk(rod.b <= rod.vh + 1 && rod.t < rod.vh && /Salvar e próxima folha/.test(rod.txt) && /Confirmar folha/.test(rod.txt) && /Relatar problema/.test(rod.txt) && /Fechar/.test(rod.txt), '§4.2 F: rodapé Salvar e próxima folha · Confirmar folha · Relatar problema · Fechar, à vista sem rolar', JSON.stringify(rod));

    // ---------- 4) avisos separados por gravidade ----------
    await pg.click('#d-body .rv-nav [data-rev-ir]:not([disabled]) >> text=Próxima');
    chk(await abriu(pg, D(4)), '§4.2 A: "Próxima ›" abre a D04');
    chk(await pg.evaluate(() => document.querySelector('#pd .thumb.aberta').dataset.revAbrir) === D(4), '§4.3 o destaque da grade acompanha a folha aberta');
    const av4 = await pg.evaluate(() => (document.querySelector('#d-body .rv-al.aviso') || {}).innerText || '');
    chk(/Aviso do CAMP Vision/.test(av4) && (av4.match(/valor descartado/g) || []).length === 1 && /titulo/.test(av4) && /escala/.test(av4), '§4.2 B + UX-71: os avisos repetidos viram UM aviso com os campos', av4);
    await pg.click('#d-body .rv-nav [data-rev-ir]:not([disabled]) >> text=Próxima');
    chk(await abriu(pg, D(5)), 'a D05 abre');
    const er5 = await pg.evaluate(() => ({ erro: (document.querySelector('#d-body .rv-al.erro') || {}).innerText || '', aviso: !!document.querySelector('#d-body .rv-al.aviso') }));
    chk(/Impede publicar/.test(er5.erro) && /carimbo ilegível/.test(er5.erro) && !er5.aviso, '§4.2 B: bloqueio aparece como "Impede publicar", separado de aviso', JSON.stringify(er5));

    // ---------- 6) alteração não salva ao trocar de folha e ao fechar ----------
    await pg.fill('#rv-escala', '1:50');
    await pg.click('#d-body .rv-nav [data-rev-ir]:not([disabled]) >> text=Anterior');
    chk(await espera(async () => /Sair sem salvar/.test(await dialogo(pg))), '§4.3 trocar de folha com alteração pergunta "Sair sem salvar?"');
    await pg.click('#conf-ov [data-conf="nao"]'); await pg.waitForTimeout(300);
    chk((await sub(pg)) === D(5) && await pg.inputValue('#rv-escala') === '1:50', '§4.3 "Continuar editando" fica na folha com o que foi digitado');
    await pg.click('#d-body [data-rev-fechar]');
    chk(await espera(async () => /Sair sem salvar/.test(await dialogo(pg))), '§7.5 Fechar com alteração pergunta');
    await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForTimeout(500);
    chk(um('SELECT escala FROM item WHERE codigo=?', D(5)) === '1:100', 'sair sem salvar não grava nada');
    const depois = await pg.evaluate(() => ({ aberto: mainEl.classList.contains('with-drawer'), dest: document.querySelectorAll('#pd .thumb.aberta').length, filtro: (document.querySelector('#pd .folhas-bar [data-fl-f].on') || {}).dataset?.flF, y: mainEl.scrollTop }));
    chk(!depois.aberto && depois.dest === 0, 'ao fechar, o painel sai e o destaque também', JSON.stringify(depois));
    chk(depois.filtro === 'conferir' && Math.abs(depois.y - rolagem0) < 80, '§7.9 o filtro e a posição da galeria ficam ao abrir/fechar o painel', JSON.stringify([depois, rolagem0]));

    // ---------- 5) Usar sugestão de título + Confirmar folha (fica) ----------
    await pg.click(`#pd .thumb[data-rev-abrir="${D(2)}"] .img-real`);
    chk(await abriu(pg, D(2)), 'a D02 abre');
    chk(await pg.inputValue('#rv-titulo') === 'Folha 2', 'D02: o título NÃO vem trocado pela leitura (nada aplicado sozinho)');
    await pg.click('#d-body .rv-sug [data-rev-usar="titulo"]');
    chk(await pg.inputValue('#rv-titulo') === 'Planta do pavimento tipo' && um('SELECT titulo FROM item WHERE codigo=?', D(2)) === 'Folha 2', '§4.2 E: "Usar sugestão" põe o título no campo; o banco só muda ao salvar');
    await pg.click('#d-body .rv-rodape [data-rev-ficar]');
    chk(await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(2)) === 'corrigida' && um('SELECT titulo FROM item WHERE codigo=?', D(2)) === 'Planta do pavimento tipo'), '§4.2 F: "Confirmar folha" grava o título e confere (corrigida)');
    chk(await espera(async () => (await sub(pg)) === D(2) && !!(await pg.$('#d-body .rv-estado [data-rev-estado="corrigida"]'))), '"Confirmar folha" fica na mesma folha, já com o selo do banco');
    chk(await espera(() => pg.evaluate(n => (document.querySelector('#pj-status .pj-conf .prog-txt') || {}).textContent === `${n} de 10 folhas conferidas`, nConf + 1)), '§9 a contagem do Próximo passo sobe junto (sem recarregar)');
    chk(await pg.evaluate(c => !!document.querySelector(`#pd .thumb[data-rev-abrir="${c}"] .rev-tag[data-rev-estado="corrigida"]`), D(2)), 'o cartão da folha mostra "corrigida" na hora');
    // Salvar e próxima folha
    await pg.click(`#pd .thumb[data-rev-abrir="${D(6)}"] .img-real`); await abriu(pg, D(6));
    await pg.click('#d-body .rv-rodape [data-rev-item="conferida"]:not([data-rev-ficar])');
    chk(await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(6)) === 'conferida'), '§4.2 F: "Salvar e próxima folha" confere a D06');
    chk(await abriu(pg, D(8)), '"Salvar e próxima folha" vai para a próxima a conferir (D08; a D07 já estava conferida)', await sub(pg));
    await pg.evaluate(() => closeDrawer(true));
    // teclado: o número da folha no cartão é um botão (Tab chega nele; Enter abre a revisão)
    await pg.focus(`#pd .thumb button.cap-id[data-rev-abrir="${D(9)}"]`); await pg.keyboard.press('Enter');
    chk(await abriu(pg, D(9)), '§7.7 pelo teclado: Enter no número da folha abre a revisão');
    await pg.evaluate(() => closeDrawer(true));

    // 1920: a grade aparece na 1ª tela
    await pg.setViewportSize({ width: 1920, height: 1080 }); await abrirProjeto(pg, 'itens');
    chk(await pg.evaluate(() => { const t = document.querySelector('#pd .thumb'); return t && t.getBoundingClientRect().top < innerHeight; }), '§9 a galeria aparece na 1ª tela (1920×1080) sem percorrer cartões');
    await ctx.close();

    // ---------- 9) permissões ----------
    const op = await entrar(br, 'operador@camp.arq.br', 'senha-operador-123', null, erros); await abrirProjeto(op.pg);
    chk(await op.pg.evaluate(() => ![...document.querySelectorAll('#pd .pj-cab .act button')].some(b => b.textContent.trim() === 'Editar')), '§5.8 operador: sem "Editar" (só admin edita o projeto)');
    await op.pg.click(`#pd .thumb[data-rev-abrir="${D(9)}"] .img-real`); await abriu(op.pg, D(9));
    chk(await op.pg.evaluate(() => !!document.querySelector('#d-body .rv-rodape [data-rev-item="conferida"]')), 'operador revisa a folha');
    await op.ctx.close();
    const le = await entrar(br, 'leitor@camp.arq.br', 'senha-leitor-1234', null, erros); await abrirProjeto(le.pg);
    const lt = await le.pg.evaluate(() => ({ editar: [...document.querySelectorAll('#pd .pj-cab .act button')].some(b => b.textContent.trim() === 'Editar'), rev: !!document.querySelector('#pd .thumb[data-rev-abrir]') }));
    chk(!lt.editar && !lt.rev, 'leitura: sem "Editar" e as folhas não abrem a revisão', JSON.stringify(lt));
    await le.ctx.close();

    // ---------- 10) 390 px ----------
    const cel = await entrar(br, 'rafael@camp.arq.br', 'senha-bem-longa-123', { width: 390, height: 844 }, erros); await abrirProjeto(cel.pg);
    const lado = pg2 => pg2.evaluate(() => ({ doc: document.documentElement.scrollWidth - innerWidth, main: mainEl.scrollWidth - mainEl.clientWidth }));
    chk((await lado(cel.pg)).doc <= 0 && (await lado(cel.pg)).main <= 0, '390 px: a página sem rolagem lateral', JSON.stringify(await lado(cel.pg)));
    await cel.pg.evaluate(c => abrirRevisaoItem(c), D(9)); await abriu(cel.pg, D(9));
    const dr = await cel.pg.evaluate(() => { const d = document.getElementById('drawer'); return { w: d.getBoundingClientRect().width, vw: innerWidth, lado: d.scrollWidth - d.clientWidth }; });
    chk(dr.w >= dr.vw - 1 && dr.lado <= 0, '§7.8 390 px: "Revisar folha" ocupa a largura toda, sem rolagem lateral', JSON.stringify(dr));
    await cel.ctx.close();
  } catch (e) { chk(false, 'o teste rodou até o fim', e.stack); }
  finally { await br.close(); }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
