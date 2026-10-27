// UX-36 no navegador de verdade (F026-P0030, 27/10: "por que ele fica pedindo para publicar se já está publicado?").
// Projeto publicado, lote aprovado, 12 folhas no site (uma com autoria não confirmada, ou seja, "com ressalva") e 1 retida.
// Prova: o chip do cabeçalho e o do Próximo passo dizem "No site" (não "Pronto para publicar"); "Atualizar no site" NÃO aparece e a frase diz
// "painel e site iguais"; o único botão azul é a 1ª pendência que falta para fechar o projeto. Depois, com uma folha de volta a rascunho,
// "Atualizar no site" volta, azul, dizendo o que muda ("ao atualizar, 1 folha fica pública"). Nenhum erro no console.
// UX-36 (visual, F009-P0015, 27/10: "feio.. meio jogado, margens e paddings ruins"): publicado e em dia, sem pendência = UMA caixa (o
// "Projeto fechado" está no Próximo passo, sem a faixa verde a mais), "painel e site iguais" e "No site" uma vez só na página, nenhum botão azul,
// nenhum anel de foco ao abrir (nem ao voltar de "Ver no site ↗" clicado com o mouse), botões da mesma altura e alinhados (≤ 2 px),
// padding interno ≥ 16 px; pelo teclado (Tab) o anel de 2 px do UX-27 continua.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada nem o site de verdade):
//   CAMP_DB_PATH=/tmp/ux36.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux36.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8985)
//   CAMP_DB_PATH=/tmp/ux36.db CAMP_BASE=http://127.0.0.1:8985 node tests/navegador_ux36_publicado.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8985', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F076-P0030';

py(`
P = 'F076-P0030'
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F076','Fundo Em Dia','FED',1)")
con.execute("INSERT OR IGNORE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES ('F076','autorizado','Família','Termo')")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F076',30)")
con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,autorizado_site) VALUES (?,'F076',30,'Ed. de Apartamentos, Rua das Mangueiras',1977,'São Paulo','SP',1)", (P,))
con.execute("DELETE FROM item WHERE projeto_codigo=?", (P,))
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo=?", (P,))
con.execute("UPDATE projeto SET status_site='no_ar', tainacan_item_id=97300 WHERE codigo=?", (P,))
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por) VALUES ('Ed. de Apartamentos',?,'/x/nao-existe/F076-P0030','revisao',datetime('now','-2 days'),'rafael@camp.arq.br')", (P,)).lastrowid
for k in range(1, 14):
    retida = int(k == 10)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,origem,revisao,status_site,tainacan_item_id,lote_id,retida,autoria_divergente,tipo_documento) VALUES (?,?,'S01',?,?,'campvision','conferida',?,?,?,?,?,'Planta')",
                ('%s-1977-S01-D%05d' % (P, k), P, k, 'Planta %d' % k, 'nao_publicado' if retida else 'no_ar', None if retida else 97300 + k, lid, retida, int(k == 2)))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|site-falso\.invalid|\/previa\?|\/miniatura|\/imagem/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const so = t => String(t || '').replace(/\s+/g, ' ').trim();
  const abrir = async () => {
    await page.evaluate(() => nav('painel')); await page.waitForTimeout(300);
    await page.evaluate(c => nav('projeto/' + c), P);
    await page.waitForSelector('#pj-status .pjs-corpo', { timeout: 20000 });
    await page.waitForFunction(() => window.PJ_FALTA && window.PJ_FALTA.code === 'F076-P0030' && !!document.querySelector('#pj-selo [data-situacao]'), null, { timeout: 25000 });
    await page.waitForTimeout(800);
  };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });

    // ---- 1) publicado e em dia ----
    await abrir();
    const selo = await page.getAttribute('#pj-selo [data-situacao]', 'data-situacao');
    const cab = await page.evaluate(() => { const x = document.querySelector('#pj-status .pjs-cab [data-situacao]'); return x ? x.dataset.situacao : null; });
    chk(selo === 'no_site' && cab === null, `chip do cabeçalho = "No site" (não "Pronto para publicar") e o Próximo passo não repete o chip: cabeçalho ${selo}, Próximo passo ${cab}`);
    const corpo = so(await page.textContent('#pj-status'));
    chk(!/Pronto para publicar/.test(corpo), 'o Próximo passo não diz "Pronto para publicar": "' + corpo.slice(0, 240) + '"');
    chk((await page.locator('#pj-status [data-pjs-atualizar]').count()) === 0, 'sem nada novo para enviar, "Atualizar no site" não aparece');
    chk(/Painel e site iguais/.test(corpo) && !/publicado qualquer visitante vê/.test(corpo) && !/Projeto fechado/.test(corpo), 'a frase diz que painel e site estão iguais (sem "Projeto fechado": ainda há pendência): "' + corpo.slice(0, 240) + '"');
    const azuis = await page.evaluate(() => [...document.querySelectorAll('#pd .btn.pri')].filter(b => b.offsetParent).map(b => (b.textContent || '').trim()));
    const falta = await page.evaluate(() => (window.PJ_FALTA.L || []).map(x => x.texto));
    chk(azuis.length === 1 && falta.length > 0 && azuis[0] === falta[0], `o único botão azul é a 1ª pendência que falta (${JSON.stringify(azuis)} × ${JSON.stringify(falta)})`);
    if (azuis.length === 1) {
      await page.click('#pj-status .pjs-pend'); await page.waitForTimeout(800);
      await page.waitForTimeout(1200);
      chk(await page.evaluate(() => pdTab === 'erros'), 'o botão azul faz o mesmo que o "Ver" da pendência (abre os problemas do projeto, onde se confirma a autoria)');
    }

    // ---- 2) uma folha volta a rascunho: Atualizar no site volta, dizendo o que muda ----
    py(`con.execute("UPDATE item SET status_site='rascunho' WHERE codigo='${P}-1977-S01-D00004'")`);
    await abrir();
    const corpo2 = so(await page.textContent('#pj-status'));
    const bt = page.locator('#pj-status [data-pjs-atualizar]');
    chk((await bt.count()) === 1 && /\bpri\b/.test(await bt.getAttribute('class')), 'com 1 folha que o visitante ainda não vê, "Atualizar no site" volta e é o botão azul');
    chk(/ao atualizar, 1 folha fica pública/.test(corpo2), 'e diz o que muda antes do clique ("ao atualizar, 1 folha fica pública"): "' + corpo2.slice(0, 240) + '"');
    const cab2 = await page.getAttribute('#pj-status .pjs-cab [data-situacao]', 'data-situacao');
    chk(cab2 === 'pronto', `com folha fora do site o lote volta a pedir publicar (chip ${cab2})`);

    // ---- 3) publicado, em dia e sem pendência: projeto fechado, numa caixa só ----
    py(`con.execute("UPDATE item SET status_site='no_ar' WHERE codigo='${P}-1977-S01-D00004'")
con.execute("UPDATE item SET autoria_divergente=0 WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")`);
    await page.mouse.click(5, 890);   // a última interação é do mouse (como quem clica na lista para abrir o projeto)
    await abrir();
    await page.waitForFunction(() => !!document.querySelector('#pj-status [data-pj-fechado]'), null, { timeout: 15000 }).catch(() => {});
    const r3 = await page.evaluate(() => {
      const vis = el => !!(el && el.offsetParent && el.getBoundingClientRect().height > 0);
      const st = document.getElementById('pj-status'), falta = document.getElementById('pj-falta'), pd = document.getElementById('pd');
      const txtPd = pd.innerText || '', cs = getComputedStyle(st);
      const bts = [...st.querySelectorAll('.pjs-acao .btn')].filter(vis).map(b => { const r = b.getBoundingClientRect(); return { t: (b.textContent || '').trim(), top: r.top, h: r.height }; });
      const a = document.activeElement;
      return { fechado: st.querySelectorAll('[data-pj-fechado]').length, faltaVis: vis(falta) && !!(falta.innerText || '').trim(),
        iguais: (txtPd.match(/painel e site iguais/gi) || []).length, fechadoTxt: (txtPd.match(/Projeto fechado/g) || []).length,
        noSite: ((document.querySelector('#pd .dethdr').innerText + ' ' + st.innerText).match(/\bNo site\b/g) || []).length,
        azuis: [...pd.querySelectorAll('.btn.pri')].filter(vis).map(b => b.textContent.trim()),
        foco: !!(a && st.contains(a)), fv: [...document.querySelectorAll(':focus-visible')].map(x => x.tagName + ' ' + (x.textContent || '').trim().slice(0, 30)),
        pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].map(parseFloat), bts };
    });
    chk(r3.fechado === 1 && !r3.faltaVis, `uma caixa só: "Projeto fechado" dentro do Próximo passo e nenhuma faixa separada (${r3.fechado} no bloco, faixa visível: ${r3.faltaVis})`);
    chk(r3.iguais === 1 && r3.fechadoTxt === 1, `"painel e site iguais" e "Projeto fechado" aparecem UMA vez na página (${r3.iguais} e ${r3.fechadoTxt})`);
    chk(r3.noSite === 1, `"No site" uma vez só entre o cabeçalho e o Próximo passo (${r3.noSite})`);
    chk(r3.azuis.length === 0, 'sem pendência, nenhum botão azul na página: ' + JSON.stringify(r3.azuis));
    chk(!r3.foco && r3.fv.length === 0, 'ao abrir, nada no Próximo passo tem foco e nenhum anel de foco aparece: ' + JSON.stringify(r3.fv));
    chk(Math.min(...r3.pad) >= 16, 'padding interno do Próximo passo ≥ 16 px: ' + JSON.stringify(r3.pad));
    const hs = r3.bts.map(b => b.h), tops = r3.bts.map(b => b.top);
    chk(r3.bts.length >= 2 && Math.max(...hs) - Math.min(...hs) <= 2 && Math.max(...tops) - Math.min(...tops) <= 2, 'botões do Próximo passo com a mesma altura e alinhados (≤ 2 px): ' + JSON.stringify(r3.bts));
    const sub = await page.evaluate(() => [...document.querySelectorAll('#pj-status .pjs-acao a.btn')].map(a => getComputedStyle(a).textDecorationLine));
    chk(sub.length > 0 && sub.every(x => x === 'none'), 'os links-botão ("Ver no site ↗", "Etiquetar e guardar") têm o mesmo estilo de botão, sem sublinhado: ' + JSON.stringify(sub));
    // "Ver no site ↗" clicado com o mouse abre outra aba; de volta, o link não fica com o foco (o anel aparecia ao voltar)
    const lk = page.locator('#pj-status a.btn[target="_blank"]');
    if (await lk.count()) {
      const [pop] = await Promise.all([ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null), lk.first().click()]);
      if (pop) await pop.close().catch(() => {});
      await page.bringToFront(); await page.waitForTimeout(300);
      const f2 = await page.evaluate(() => { const a = document.activeElement; return !!(a && a.closest && a.closest('#pj-status')) || !!document.querySelector('#pj-status :focus-visible'); });
      chk(!f2, 'depois de "Ver no site ↗" com o mouse, o link não fica com o foco (sem anel ao voltar para a aba)');
    } else chk(false, '"Ver no site ↗" no Próximo passo');
    // pelo teclado o anel continua (UX-27: 2 px)
    let anel = null;
    for (let i = 0; i < 60 && !anel; i++) {
      await page.keyboard.press('Tab');
      anel = await page.evaluate(() => { const a = document.activeElement; if (!a || !a.closest('#pj-status')) return null; const c = getComputedStyle(a); return { fv: a.matches(':focus-visible'), w: c.outlineWidth, s: c.outlineStyle }; });
    }
    chk(!!anel && anel.fv && anel.w === '2px' && anel.s !== 'none', 'pelo Tab o foco chega ao Próximo passo com o anel de 2 px: ' + JSON.stringify(anel));
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
