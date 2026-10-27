// UX-22 / 27/10 (Rafael, print de "Tarefas e avisos recentes": "arruma isso, tá escrito errado, espaçamento errado").
// O cartão mostrava "começou 27/10/2026, 15:08 · rafael@camp.arq.brPublicando · 23 s até agora": autor e etapa GRUDADOS, o e-mail no lugar
// do nome, a data repetida sendo hoje e "Publicando…" repetido na lista de passos. Prova no navegador de verdade (Playwright + Chromium):
//  - nenhum texto grudado (e-mail seguido de letra) e nenhum e-mail no cartão: aparece o NOME cadastrado da pessoa;
//  - "começou 15:08" (sem a data quando é hoje); a etapa atual numa linha própria, em destaque, sem repetir na lista de passos;
//  - espaçamentos: padding do cartão, distância entre título/linha/etapa/lista/botão, lista com recuo e cor secundária, botão alinhado;
//  - o aviso de andamento na tela (seguirTarefa) também não gruda o título na etapa;
//  - nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8984)
//   CAMP_DB_PATH=/tmp/x/x.db CAMP_BASE=http://127.0.0.1:8984 node tests/navegador_ux22_cartao_tarefa.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8984';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const GRUDADO = /[\w.+-]+@[\w-]+(\.[\w-]+)+[A-Za-zÀ-ú]/;   // "rafael@camp.arq.brPublicando"
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/;

(async () => {
  if (!DB) { console.log('FALHA: defina CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(1); }
  // a pessoa tem nome cadastrado diferente do que se tiraria do e-mail; e uma sincronização dela terminou há 10 min
  execFileSync('python3', ['-c', `
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("UPDATE usuario SET nome='Rafael Teste' WHERE email='rafael@camp.arq.br'")
c.execute("""INSERT INTO tarefa_publicacao (projeto_codigo, ator, estado, etapa, tipo, titulo, iniciada_em, terminada_em, resultado, log)
             VALUES ('site','rafael@camp.arq.br','ok','fim','sincronizar','Sincronizar com o site', datetime('now','-10 minutes'), datetime('now','-1 minutes'),
                     '{"ok": true, "mensagem": "Sincronizado: 5057 item(ns) do site, 142 divergência(s)."}', '[]')""")
c.commit()`, DB]);
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU && AJUDA_VISTAS !== null, null, { timeout: 15000 });
    await page.waitForTimeout(1200);

    // ---- a tarefa terminada vem do servidor de verdade (/api/tarefas) ----
    await page.evaluate(() => abrirTarefas());
    await page.waitForSelector('#d-body [data-tarefas-lista] .tarefa-card', { timeout: 8000 });
    await page.evaluate(() => clearTimeout(TAREFAS_TIMER));
    const fim = await page.evaluate(() => { const c = document.querySelector('#d-body [data-tarefas-lista] .tarefa-card'); return { txt: c.innerText, meta: (c.querySelector('.tarefa-meta') || {}).innerText || '' }; });
    chk(/Sincronizado: 5\.?057 itens do site, 142 divergências/.test(fim.txt) && !/\((n?s)\)/.test(fim.txt), `"Suas tarefas": a sincronização do Rafael, com o resultado (${JSON.stringify(fim.txt)})`);
    chk(!EMAIL.test(fim.txt) && !GRUDADO.test(fim.txt), 'cartão terminado: sem e-mail e sem texto grudado');
    chk(/^começou \d{2}:\d{2} · Rafael Teste$/.test(fim.meta.trim()), `cartão terminado: "começou HH:MM · Rafael Teste" (nome cadastrado, sem a data de hoje) — veio ${JSON.stringify(fim.meta)}`);

    // ---- cartão de publicação EM ANDAMENTO (como no print) ----
    const agoraUtc = new Date(Date.now() - 23000).toISOString().slice(0, 19).replace('T', ' ');
    const t = { id: 99001, tipo: 'publicar', projeto_codigo: 'F009-P0092', ator: 'rafael@camp.arq.br', ator_nome: 'Rafael Teste', estado: 'rodando', etapa: 'publicar',
      feitas: 0, total: 0, decorrido_s: 23, iniciada_em: agoraUtc, log: [{ em: agoraUtc, texto: 'Projeto liberado para publicação' }, { em: agoraUtc, texto: 'Publicando…' }], falhas: [] };
    await page.evaluate(t => { TAREFAS_EST = { rodando: [t], terminadas: [] }; desenharChipTarefas(); clearTimeout(TAREFAS_TIMER); }, t);
    const r = await page.evaluate(() => {
      const c = document.querySelector('#d-body [data-tarefas-lista] .tarefa-card'), cs = getComputedStyle(c), q = s => c.querySelector(s);
      const box = e => e ? e.getBoundingClientRect() : null, h3 = q('h3'), meta = q('.tarefa-meta'), agora = q('.tarefa-agora'), passos = q('.tarefa-passos'), act = q('.act'), btn = q('.act button');
      const filhos = [...c.children].map(e => box(e)), gaps = filhos.slice(1).map((b, i) => Math.round(b.top - filhos[i].bottom));
      return { txt: c.innerText, meta: meta && meta.innerText, agora: agora && agora.innerText, etapaPeso: q('.tarefa-etapa') && getComputedStyle(q('.tarefa-etapa')).fontWeight,
        passos: passos ? [...passos.querySelectorAll('li')].map(l => l.innerText) : null,
        pad: [cs.paddingTop, cs.paddingLeft].map(parseFloat), gaps,
        agoraLinhaPropria: !!(agora && meta && box(agora).top >= box(meta).bottom - 1),
        recuo: passos ? parseFloat(getComputedStyle(passos).paddingLeft) : 0, corPassos: passos && getComputedStyle(passos).color, corTitulo: getComputedStyle(h3).color, pesoTitulo: getComputedStyle(h3).fontWeight, corTexto: getComputedStyle(document.body).color,
        btnX: btn && Math.round(box(btn).left), h3X: Math.round(box(h3).left), chip: document.getElementById('tarefas-chip').innerText };
    });
    chk(!GRUDADO.test(r.txt), `em andamento: nada grudado ao e-mail (antes "rafael@camp.arq.brPublicando") — ${JSON.stringify(r.txt)}`);
    chk(!EMAIL.test(r.txt) && /Rafael Teste/.test(r.meta || ''), `em andamento: o NOME da pessoa, nunca o e-mail (${JSON.stringify(r.meta)})`);
    chk(/^começou \d{2}:\d{2} · Rafael Teste$/.test((r.meta || '').trim()), `"começou 15:08 · Rafael Teste" (sem a data quando é hoje) — veio ${JSON.stringify(r.meta)}`);
    chk(r.agoraLinhaPropria && /^Publicando · 23 s até agora$/.test((r.agora || '').trim()) && +r.etapaPeso >= 600, `a etapa atual numa linha própria, em destaque: ${JSON.stringify(r.agora)} (peso ${r.etapaPeso})`);
    chk(r.passos && r.passos.length === 1 && /^\d{2}:\d{2} · Projeto liberado para publicação$/.test(r.passos[0]), `a lista de passos não repete a etapa atual e usa a hora curta: ${JSON.stringify(r.passos)}`);
    chk(r.pad[0] >= 10 && r.pad[1] >= 12, `padding do cartão ≥ 10/12 px (${r.pad})`);
    chk(r.gaps.length >= 4 && r.gaps.every(g => g >= 4 && g <= 10), `espaço entre título, linha, etapa, lista e botão uniforme, entre 4 e 10 px (${r.gaps})`);
    chk(+r.pesoTitulo >= 600 && r.corTitulo === r.corTexto, `título do cartão em destaque (peso ${r.pesoTitulo}, cor ${r.corTitulo}), não com cara de cabeçalho de seção cinza`);
    chk(r.recuo >= 16 && r.corPassos !== r.corTitulo, `lista de passos com recuo (${r.recuo} px) e cor secundária (${r.corPassos} × ${r.corTitulo})`);
    chk(r.btnX !== null && Math.abs(r.btnX - r.h3X) <= 2, `botão "Abrir F009-P0092" alinhado à esquerda com o título (${r.btnX} × ${r.h3X})`);
    chk(/⏳ Publicando F009-P0092/.test(r.chip) && !EMAIL.test(r.chip), `chip do topo sem e-mail: ${JSON.stringify(r.chip)}`);

    // ---- o aviso de andamento na própria tela (seguirTarefa) também não gruda o título na etapa ----
    const aviso = await page.evaluate(() => { const d = document.createElement('div'); d.className = 'aviso-local rodando';
      d.innerHTML = `<div class="t"><b>⏳ Sincronizando com o site…</b>${andamentoTarefaHTML({ etapa: 'Lendo coleções, folhas e páginas do site', total: 0, feitas: 0, decorrido_s: 65 })}</div>`;
      document.body.appendChild(d); const s = d.innerText; d.remove(); return s; });
    chk(/Sincronizando com o site…\s*\n\s*Lendo coleções, folhas e páginas do site · 1 min 5 s até agora/.test(aviso), `aviso na tela: título e etapa em linhas separadas (${JSON.stringify(aviso)})`);
    chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    chk(false, 'erro no teste: ' + (e && e.stack || e));
  } finally {
    await browser.close();
    console.log(linhas.join('\n'));
    console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
    process.exit(problemas.length ? 1 : 0);
  }
})();
