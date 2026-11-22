// CAMP-DOA-CENTRAL (21/11/2026): a central de cada doação de acervo, no navegador de verdade (Playwright + Chromium).
// Rafael: "seria o ideal lá no doações de acervo ter controle total sobre o acervo … Status, o que já aconteceu, o que não aconteceu,
// informações internas … cotar frete, comprar insumo para embalar e etc."
//  [A] abas da lista (Em andamento / Recebidos / Não aprovadas e arquivadas / Todas), com os números; nada some em Todas; setas trocam de aba
//  [B] linha de etapas no detalhe (feito com data, próximo passo, pulado) e "Próximo passo: …"
//  [C] contrato assinado sem tarefas → aviso "defina os próximos passos"; "Usar roteiro de logística" põe a lista; marcar uma como feita
//  [D] nova tarefa com valor e prazo; custos somados; apagar pede confirmação
//  [E] anexar um PDF (fica na lista, abre pelo link); tipo errado recusado com frase
//  [F] histórico único com filtro (Tudo / Notas / E-mails / Tarefas); nota interna salva aparece no histórico
//  [G] nomes só como texto (nada em onclick); sem erro de JavaScript; 390 px sem rolagem lateral
// Uso (servidor PRÓPRIO na porta 8870; nada vai ao site):
//   CAMP_DB_PATH=/dev/shm/doacentral/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/doacentral/m.db CAMP_COOKIE_SECURE=false CAMP_DOACOES_ANEXOS_DIR=/dev/shm/doacentral/anexos python3 -m uvicorn app.main:app --port 8870)
//   CAMP_DB_PATH=/dev/shm/doacentral/m.db CAMP_BASE=http://127.0.0.1:8870 node tests/navegador_doacao_central.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8870', DB = process.env.CAMP_DB_PATH;
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [], erros = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] });
const H = ['2026-11-02 13:00 UTC · Rafael: etapa Em análise → Aprovada', '2026-11-03 14:00 UTC · Rafael: contrato enviado para assinatura (e-mail TR30 pelo Sender)',
  '2026-11-03 14:01 UTC · Rafael: etapa Aprovada → Contrato enviado para assinatura', '2026-11-06 09:00 UTC · Autentique (painel): etapa Contrato enviado para assinatura → Contrato assinado pelas partes'];
const REG = (id, etapa, extra) => Object.assign({ id, protocolo: 'CAMP-2026-000' + id, recebida_em: '2026-11-01T12:00:00+00:00', nome: 'Pessoa <b>Doadora</b> ' + id, email: 'doa' + id + '@exemplo.com',
  autor: 'Arquiteto <img src=x onerror=alert(1)> ' + id, etapa, valor: 2500, notas: [], historico: [], avisos: [] }, extra || {});
(async () => {
  const regs = [REG(941, 'contrato_assinado', { assinado_em: '2026-11-06', aprovada_em: '2026-11-02T13:00:00+00:00', contrato_enviado_em: '2026-11-03T14:00:00+00:00', historico: H }),
    REG(942, 'recebido'), REG(943, 'arquivada'), REG(944, 'em_analise')];
  for (const r of regs) py(`r=json.loads(sys.argv[2])\ncon.execute("INSERT OR REPLACE INTO doacao_acervo (site_id, protocolo, recebida_em, nome, email, autor, etapa, valor, assinado_em, dados) VALUES (?,?,?,?,?,?,?,?,?,?)",(r['id'],r['protocolo'],'2026-11-01 12:00:00',r['nome'],r['email'],r['autor'],r['etapa'],r['valor'],r.get('assinado_em'),json.dumps(r)))`, JSON.stringify(r));
  py('con.execute("DELETE FROM doacao_tarefa WHERE site_id IN (941,942,943,944)")\ncon.execute("DELETE FROM doacao_anexo WHERE site_id IN (941,942,943,944)")');   // banco de teste: rodar de novo
  const browser = await chromium.launch({ executablePath: CHROME });
  try {
    for (const [w, h] of [[1366, 900], [390, 844]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const P = await ctx.newPage();
      P.on('pageerror', e => erros.push(`${w}px pageerror: ` + e.message));
      P.on('dialog', d => { erros.push(`${w}px dialog: ` + d.message()); d.dismiss(); });
      await P.goto(BASE + '/');
      await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
      await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
      await P.goto(BASE + '/#doacoes');
      await P.waitForSelector('#doa-lista tr[data-doa-abrir="941"]', { timeout: 15000 });
      const W = `[${w}px] `;
      // [A]
      const ids = async () => P.$$eval('#doa-lista tr[data-doa-abrir]', trs => trs.map(t => +t.dataset.doaAbrir));
      let l = await ids();
      chk(l.includes(941) && l.includes(944) && !l.includes(942) && !l.includes(943), W + '[A] Em andamento (padrão): a assinada e a em análise; sem recebido e arquivada');
      chk(/Em andamento\s*\d+/.test(await P.textContent('#doa-abas [data-doa-aba="abertas"]')), W + '[A] a aba mostra o número');
      await P.click('#doa-abas [data-doa-aba="recebidos"]'); await P.waitForTimeout(400); l = await ids();
      chk(l.includes(942) && !l.includes(941), W + '[A] Recebidos');
      await P.click('#doa-abas [data-doa-aba="encerradas"]'); await P.waitForTimeout(400); l = await ids();
      chk(l.includes(943) && !l.includes(942), W + '[A] Não aprovadas e arquivadas');
      await P.focus('#doa-abas [data-doa-aba="encerradas"]'); await P.keyboard.press('ArrowRight'); await P.waitForTimeout(400); l = await ids();
      chk([941, 942, 943, 944].every(i => l.includes(i)) && await P.getAttribute('#doa-abas [data-doa-aba=""]', 'aria-selected') === 'true', W + '[A] seta → Todas: nada some');
      const prox = await P.textContent('#doa-lista tr[data-doa-abrir="941"] .doa-prox');
      chk(/Gerar a cobrança|Receber o acervo|Aguardar/.test(prox), W + '[A] a linha mostra o próximo passo: ' + prox.trim().slice(0, 60));
      // [B]
      await P.click('#doa-lista tr[data-doa-abrir="941"]');
      await P.waitForSelector('.doa-det[data-doa-id="941"] .doa-passos', { timeout: 10000 });
      const est = await P.$$eval('.doa-passos li', lis => lis.map(li => li.className + ':' + li.querySelector('.nm').textContent + ':' + li.querySelector('small').textContent));
      chk(est.some(e => e === 'feito:Aprovada:02/11/2026') && est.some(e => e === 'feito:Contrato assinado:06/11/2026') && est.some(e => e.startsWith('pulado:Visita'))
        && est.filter(e => e.startsWith('atual:')).length === 1, W + '[B] etapas: feito com data, visita pulada, um próximo passo');
      chk(/Próximo passo:/.test(await P.textContent('.doa-prox-det')), W + '[B] "Próximo passo: …" no detalhe');
      // [B2] CAMP-DOA-CENTRAL (22/11): com o detalhe aberto a 1366 px a coluna "Próximo passo" da lista ficava cortada e a tabela rolava
      // para o lado. Com o detalhe aberto, a 1366 e a 1440 px: nenhuma rolagem lateral na tabela e "Próximo passo" (título e célula) à vista.
      if (w === 1366) {
        for (const vw of [1366, 1440]) {
          await P.setViewportSize({ width: vw, height: h }); await P.waitForTimeout(400);
          const m = await P.evaluate(() => { const tw = document.querySelector('#v-doacoes .tw'), r = tw.getBoundingClientRect(), vis = el => { if (!el) return false; const b = el.getBoundingClientRect(); return getComputedStyle(el).display !== 'none' && b.width > 40 && b.left >= r.left - 1 && b.right <= r.right + 1; };
            const th = [...document.querySelectorAll('#v-doacoes thead th')].find(t => /Próximo passo/.test(t.textContent)), td = document.querySelector('#doa-lista tr[data-doa-abrir="941"] .doa-prox');
            return { gaveta: mainEl.classList.contains('with-drawer'), sw: tw.scrollWidth, cw: tw.clientWidth, th: vis(th), td: vis(td), pag: document.documentElement.scrollWidth - innerWidth }; });
          chk(m.gaveta && m.sw <= m.cw && m.th && m.td && m.pag <= 0, `[${vw}px] [B2] detalhe aberto: a lista sem rolagem lateral e "Próximo passo" à vista: ` + JSON.stringify(m));
        }
        await P.setViewportSize({ width: w, height: h }); await P.waitForTimeout(300);
      }
      // [C]
      chk(await P.locator('.doa-aviso-roteiro').count() === 1 && /defina os próximos passos/.test(await P.textContent('.doa-aviso-roteiro')), W + '[C] contrato assinado e nada a fazer: aviso do roteiro');
      await P.click('.doa-aviso-roteiro [data-doac="roteiro"]');
      await P.waitForSelector('.doa-tfs .doa-tf', { timeout: 10000 });
      chk(await P.locator('.doa-tfs .doa-tf').count() === 8 && await P.locator('.doa-aviso-roteiro').count() === 0, W + '[C] roteiro de logística: 8 tarefas e o aviso some');
      const t1 = await P.getAttribute('.doa-tfs .doa-tf >> nth=0', 'data-tarefa-li');
      await P.selectOption(`[data-doac-sit="${t1}"]`, 'feita');
      await P.waitForFunction(id => { const li = document.querySelector(`[data-tarefa-li="${id}"]`); return li && li.classList.contains('feita'); }, t1, { timeout: 10000 });
      chk(/1 de 8 feitas/.test(await P.textContent('.doa-sec[aria-labelledby="doa-h-tf"]')), W + '[C] marcar "Feita": 1 de 8 feitas');
      // [D]
      await P.click('[data-doac="tf-nova"]');
      const f = '[data-tf-form="nova"]';
      await P.fill(f + ' [data-tf="titulo"]', 'Cotar frete com a segunda transportadora');
      await P.fill(f + ' [data-tf="valor"]', '1.250,00'); await P.fill(f + ' [data-tf="prazo"]', '2026-01-05'); await P.fill(f + ' [data-tf="responsavel"]', 'Rafael');
      await P.click(f + ' [data-doac="tf-salvar"]');
      await P.waitForFunction(() => document.querySelectorAll('.doa-tfs .doa-tf').length === 9, null, { timeout: 10000 });
      const sec = await P.textContent('.doa-sec[aria-labelledby="doa-h-tf"]');
      chk(/R\$\s*1\.250,00/.test(sec) && /atrasada/.test(sec), W + '[D] nova tarefa com valor e prazo vencido: custos e "atrasada"');
      const tAp = await P.getAttribute('.doa-tfs .doa-tf >> nth=8', 'data-tarefa-li');
      await P.click(`[data-tarefa-li="${tAp}"] [data-doac="tf-apagar"]`);
      await P.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
      chk(/Apagar tarefa/.test(await P.textContent('#conf-ov')), W + '[D] apagar pede confirmação');
      await P.click('#conf-ov [data-conf="sim"]');
      await P.waitForFunction(() => document.querySelectorAll('.doa-tfs .doa-tf').length === 8, null, { timeout: 10000 });
      chk(true, W + '[D] tarefa apagada');
      // [E]
      await P.setInputFiles('#doa-anx-arq', { name: 'Orçamento frete.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% orcamento\n%%EOF\n') });
      await P.click('[data-doac="anexar"]');
      await P.waitForSelector('.doa-arqs li', { timeout: 10000 });
      const href = await P.getAttribute('.doa-arqs li a', 'href');
      const corpo = await P.evaluate(u => fetch(u).then(r => r.text()), href);
      chk(/Orçamento frete\.pdf/.test(await P.textContent('.doa-arqs')) && corpo.startsWith('%PDF-'), W + '[E] PDF anexado: na lista e abre pelo link');
      await P.setInputFiles('#doa-anx-arq', { name: 'falso.pdf', mimeType: 'application/pdf', buffer: Buffer.from('nao e pdf') });
      await P.click('[data-doac="anexar"]');
      await P.waitForTimeout(800);
      const toastTxt = await P.evaluate(() => [...document.querySelectorAll('.toast, #toast, [role="status"]')].map(e => e.textContent).join(' '));
      chk(/não é PDF/.test(toastTxt) && await P.locator('.doa-arqs li').count() === 1, W + '[E] PDF falso recusado com frase');
      // [F]
      await P.fill('#doa-nota', 'Frete: pedir 3 orçamentos até sexta.');
      await P.click('[data-doac="nota"]');
      await P.waitForTimeout(1200);
      // (sem a senha do site a nota não vai: o histórico mostra as tarefas/arquivos; a nota é provada no teste de backend)
      const cats = await P.$$eval('.doa-tl li', lis => lis.map(li => li.dataset.cat));
      chk(cats.includes('tarefa') && cats.includes('etapa'), W + '[F] histórico único: etapas do site, tarefas e arquivos');
      await P.click('.doa-hist [data-doa-hist="tarefa"]');
      const vis = await P.$$eval('.doa-tl li', lis => lis.filter(li => !li.hidden).map(li => li.dataset.cat));
      chk(vis.length > 0 && vis.every(c => c === 'tarefa'), W + '[F] filtro Tarefas mostra só tarefas e arquivos');
      await P.click('.doa-hist [data-doa-hist="tudo"]');
      // [G]
      const onclickComNome = await P.evaluate(() => [...document.querySelectorAll('.doa-det [onclick], #doa-lista [onclick]')].some(el => /Doadora|Arquiteto/.test(el.getAttribute('onclick'))));
      chk(!onclickComNome && await P.locator('.doa-det img[src="x"]').count() === 0, W + '[G] nomes só como texto (nada em onclick, HTML do nome não vira tag)');
      const largura = await P.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      chk(largura <= 1, W + '[G] sem rolagem lateral (' + largura + ' px)');
      if (w === 1366 || w === 390) await P.screenshot({ path: `/dev/shm/doa-central/teste-tarefas-${w}.png` });
      py('con.execute("DELETE FROM doacao_tarefa WHERE site_id=941")\ncon.execute("DELETE FROM doacao_anexo WHERE site_id=941")');
      await ctx.close();
    }
  } finally { await browser.close(); }
  chk(!erros.length, 'sem erro de JavaScript' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} problema(s)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
