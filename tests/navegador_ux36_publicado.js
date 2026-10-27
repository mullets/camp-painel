// UX-36 no navegador de verdade (F026-P0030, 27/10: "por que ele fica pedindo para publicar se já está publicado?").
// Projeto publicado, lote aprovado, 12 folhas no site (uma com autoria não confirmada, ou seja, "com ressalva") e 1 retida.
// Prova: o chip do cabeçalho e o do Próximo passo dizem "No site" (não "Pronto para publicar"); "Atualizar no site" NÃO aparece e a frase diz
// "painel e site iguais"; o único botão azul é a 1ª pendência que falta para fechar o projeto. Depois, com uma folha de volta a rascunho,
// "Atualizar no site" volta, azul, dizendo o que muda ("ao atualizar, 1 folha fica pública"). Nenhum erro no console.
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
    const cab = await page.getAttribute('#pj-status .pjs-cab [data-situacao]', 'data-situacao');
    chk(selo === 'no_site' && cab === 'no_site', `chip do cabeçalho e do Próximo passo = "No site" (não "Pronto para publicar"): cabeçalho ${selo}, Próximo passo ${cab}`);
    const corpo = so(await page.textContent('#pj-status'));
    chk(!/Pronto para publicar/.test(corpo), 'o Próximo passo não diz "Pronto para publicar": "' + corpo.slice(0, 240) + '"');
    chk((await page.locator('#pj-status [data-pjs-atualizar]').count()) === 0, 'sem nada novo para enviar, "Atualizar no site" não aparece');
    chk(/publicado qualquer visitante vê · painel e site iguais/.test(corpo), 'a frase diz que painel e site estão iguais: "' + corpo.slice(0, 240) + '"');
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
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
