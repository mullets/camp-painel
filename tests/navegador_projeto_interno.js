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

    // 1920: a grade aparece na 1ª tela
    await pg.setViewportSize({ width: 1920, height: 1080 }); await abrirProjeto(pg, 'itens');
    chk(await pg.evaluate(() => { const t = document.querySelector('#pd .thumb'); return t && t.getBoundingClientRect().top < innerHeight; }), '§9 a galeria aparece na 1ª tela (1920×1080) sem percorrer cartões');
    await ctx.close();

    // ---------- 9) permissões ----------
    const op = await entrar(br, 'operador@camp.arq.br', 'senha-operador-123', null, erros); await abrirProjeto(op.pg);
    chk(await op.pg.evaluate(() => ![...document.querySelectorAll('#pd .pj-cab .act button')].some(b => b.textContent.trim() === 'Editar')), '§5.8 operador: sem "Editar" (só admin edita o projeto)');
    await op.ctx.close();
    const le = await entrar(br, 'leitor@camp.arq.br', 'senha-leitor-1234', null, erros); await abrirProjeto(le.pg);
    const lt = await le.pg.evaluate(() => ({ editar: [...document.querySelectorAll('#pd .pj-cab .act button')].some(b => b.textContent.trim() === 'Editar'), rev: !!document.querySelector('#pd .thumb[data-rev-abrir]') }));
    chk(!lt.editar && !lt.rev, 'leitura: sem "Editar" e as folhas não abrem a revisão', JSON.stringify(lt));
    await le.ctx.close();

    // ---------- 10) 390 px ----------
    const cel = await entrar(br, 'rafael@camp.arq.br', 'senha-bem-longa-123', { width: 390, height: 844 }, erros); await abrirProjeto(cel.pg);
    const lado = pg2 => pg2.evaluate(() => ({ doc: document.documentElement.scrollWidth - innerWidth, main: mainEl.scrollWidth - mainEl.clientWidth }));
    chk((await lado(cel.pg)).doc <= 0 && (await lado(cel.pg)).main <= 0, '390 px: a página sem rolagem lateral', JSON.stringify(await lado(cel.pg)));
    await cel.ctx.close();
  } catch (e) { chk(false, 'o teste rodou até o fim', e.stack); }
  finally { await br.close(); }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
