// UX-69 no navegador de verdade (Playwright + Chromium): o painel não pode ficar parado em "Montando o painel…" e o aviso
// "Dados de exemplo… nada aqui é real" nunca aparece com a pessoa logada.
// Antes: no navegador embutido do app (Chromium/Electron) a tela inicial ficou parada em "Montando o painel…" com "Dados de exemplo".
// Causas: (1) limparExemplos() punha o aviso "Dados de exemplo" em TODAS as telas (inclusive o Painel, que não tem dado de exemplo)
// assim que a página abria no servidor, e só a carga bem-sucedida o tirava; (2) uma exceção no começo (ex.: localStorage bloqueado:
// `let FUNDO_FILTRO=localStorage.getItem(...)` no topo do script, ou dentro de aplicarUsuario) parava tudo antes de carregar o painel,
// sem mensagem nem tempo-limite.
// Prova (cada cenário num contexto novo, entrando pelo formulário):
//  - normal: o painel carrega; nenhum "Dados de exemplo" em nenhuma tela; nada de "Montando o painel…";
//  - /api/painel com 500: erro claro com "Tentar de novo"; clicar (com a rota de volta) carrega o painel;
//  - localStorage lançando exceção (como num navegador que bloqueia o armazenamento): o painel carrega igual;
//  - APIs do navegador removidas (structuredClone, IntersectionObserver, ResizeObserver, requestIdleCallback): o painel carrega;
//  - exceção dentro do começo (aplicarUsuario quebrando): erro com "Tentar de novo" em vez de parado;
//  - /api/painel que nunca responde: depois do tempo-limite aparece o erro com "Tentar de novo".
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux69.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux69.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8973)
//   CAMP_BASE=http://127.0.0.1:8973 node tests/navegador_ux69_boot.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8973';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };

async function cenario(br, nome, prep, { espera = 15000 } = {}) {
  const ctx = await br.newContext({ viewport: { width: 1366, height: 768 } });
  const pg = await ctx.newPage(), erros = [];
  pg.on('pageerror', e => erros.push(e.message));
  if (prep) await prep(pg, ctx);
  await pg.goto(BASE + '/#painel');
  const temLogin = await pg.waitForSelector('#lg-email', { state: 'visible', timeout: 10000 }).then(() => true, () => false);
  if (temLogin) { await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter'); }
  else erros.push('o formulário de entrada nunca apareceu (o script parou no começo)');
  // espera o painel montar OU uma mensagem de erro com "Tentar de novo"
  const t0 = Date.now(); let est = null;
  while (Date.now() - t0 < espera) {
    est = await pg.evaluate(() => {
      const sec = document.getElementById('v-painel'), txt = document.body.innerText;
      return { montou: !!(sec && sec.querySelector('.ini-grid')), montando: /Montando o (painel|resumo do dia)/.test(sec ? sec.innerText : ''),
        tentar: [...document.querySelectorAll('button')].some(b => b.offsetParent && /^Tentar de novo$/.test(b.textContent.trim())),
        exemplo: /Dados de exemplo|nada aqui é real/.test(txt) || !!document.querySelector('.aviso-exemplo'),
        exemploEmAlgumaTela: !!document.querySelector('.aviso-exemplo') };
    }).catch(() => null);
    if (est && (est.montou || est.tentar)) break;
    await pg.waitForTimeout(250);
  }
  return { ctx, pg, est: est || {}, erros, ms: Date.now() - t0 };
}

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  try {
    // ---------- normal ----------
    let r = await cenario(br, 'normal');
    chk(r.est.montou && !r.est.montando, 'normal: o painel carrega', JSON.stringify(r.est));
    chk(!r.est.exemploEmAlgumaTela, 'normal: nenhuma tela com "Dados de exemplo" (logado de verdade)', JSON.stringify(r.est));
    for (const v of ['filas', 'solicitacoes', 'erros']) {
      await r.pg.evaluate(v => nav(v), v); await r.pg.waitForTimeout(700);
      const ex = await r.pg.evaluate(v => /Dados de exemplo|nada aqui é real/.test(document.getElementById('v-' + v).innerText), v);
      chk(!ex, `normal: "${v}" sem "Dados de exemplo"`);
    }
    const sol = await r.pg.evaluate(() => document.getElementById('v-solicitacoes').innerText);
    chk(!/Editora Romano Guerra|Revista Projeto/.test(sol), 'normal: os pedidos de exemplo do HTML nunca aparecem como se fossem reais', sol.slice(0, 200));
    chk(!r.erros.length, 'normal: nenhum erro de JavaScript', r.erros.join(' | '));
    await r.ctx.close();

    // ---------- /api/painel com 500 ----------
    let falhar = true;
    r = await cenario(br, '500', async pg => { await pg.route('**/api/painel*', rt => falhar ? rt.fulfill({ status: 500, contentType: 'application/json', body: '{"erro":"falha simulada"}' }) : rt.continue()); });
    chk(r.est.tentar && !r.est.montou, '/api/painel 500: aparece o erro com "Tentar de novo"', JSON.stringify(r.est));
    chk(!r.est.exemplo, '/api/painel 500: sem "Dados de exemplo"', JSON.stringify(r.est));
    const txt500 = await r.pg.evaluate(() => document.getElementById('v-painel').innerText);
    chk(/Não (foi possível|consegui) (carregar|montar) o painel/i.test(txt500), '/api/painel 500: mensagem clara do que houve', txt500.slice(0, 200));
    falhar = false;
    const bt = r.pg.locator('#v-painel button', { hasText: 'Tentar de novo' }).first();
    if (await bt.count()) await bt.click();
    chk(await r.pg.waitForSelector('#v-painel .ini-grid', { timeout: 15000 }).then(() => true, () => false), '/api/painel 500: "Tentar de novo" carrega o painel quando o servidor volta');
    await r.ctx.close();

    // ---------- localStorage bloqueado ----------
    r = await cenario(br, 'localStorage', async pg => {
      await pg.addInitScript(() => {
        const err = () => { throw new DOMException('O acesso ao armazenamento foi negado', 'SecurityError'); };
        Object.defineProperty(window, 'localStorage', { configurable: true, get: err });
        Object.defineProperty(window, 'sessionStorage', { configurable: true, get: err });
      });
    });
    chk(r.est.montou, 'localStorage bloqueado: o painel carrega mesmo assim', JSON.stringify(r.est) + ' ' + r.erros.join(' | '));
    chk(!r.est.exemplo, 'localStorage bloqueado: sem "Dados de exemplo"', JSON.stringify(r.est));
    await r.ctx.close();

    // ---------- APIs do navegador ausentes ----------
    r = await cenario(br, 'apis', async pg => {
      await pg.addInitScript(() => { for (const k of ['structuredClone', 'IntersectionObserver', 'ResizeObserver', 'requestIdleCallback']) { try { delete window[k] } catch (_) {} try { window[k] = undefined } catch (_) {} } });
    });
    chk(r.est.montou, 'sem structuredClone/IntersectionObserver/ResizeObserver/requestIdleCallback: o painel carrega', JSON.stringify(r.est) + ' ' + r.erros.join(' | '));
    chk(!r.est.exemplo, 'APIs ausentes: sem "Dados de exemplo"');
    await r.ctx.close();

    // ---------- exceção no começo (aplicarUsuario quebra) ----------
    r = await cenario(br, 'excecao', async pg => {
      // o avatar do topo quebra (como uma API do navegador que falta no meio do começo)
      await pg.addInitScript(() => { document.addEventListener('DOMContentLoaded', () => { window.atualizarAvatarTopo = () => { throw new TypeError('x is not a function (simulado)') }; try { atualizarAvatarTopo = window.atualizarAvatarTopo } catch (_) {} }); });
    });
    chk(r.est.montou || r.est.tentar, 'exceção no começo: o painel carrega ou mostra o erro com "Tentar de novo" (nunca parado)', JSON.stringify(r.est));
    chk(!r.est.montando || r.est.tentar, 'exceção no começo: não fica em "Montando o painel…"', JSON.stringify(r.est));
    chk(!r.est.exemplo, 'exceção no começo: sem "Dados de exemplo"', JSON.stringify(r.est));
    await r.ctx.close();

    // ---------- erro no topo do script (antes do login) ----------
    r = await cenario(br, 'topo', async pg => {
      await pg.addInitScript(() => { const q0 = Document.prototype.querySelector; Document.prototype.querySelector = function (sel) { if (sel === '.who' && !window.__quebrou) { window.__quebrou = 1; throw new TypeError('API ausente (simulado)') } return q0.call(this, sel) } });
    }, { espera: 6000 });
    chk(r.est.tentar && !r.est.montou, 'erro no topo do script: aparece o erro com "Tentar de novo" (antes ficava em "Montando o painel…" sem login)', JSON.stringify(r.est));
    chk(!r.est.exemplo, 'erro no topo: sem "Dados de exemplo"');
    await r.ctx.close();

    // ---------- /api/painel que nunca responde ----------
    r = await cenario(br, 'pendurado', async pg => {
      await pg.addInitScript(() => { window.CAMP_BOOT_LIMITE_MS = 4000 });   // o tempo-limite real é maior; o teste encurta
      await pg.route('**/api/painel*', () => { /* nunca responde */ });
    }, { espera: 15000 });
    chk(r.est.tentar && !r.est.montou, 'promessa que nunca resolve: depois do tempo-limite aparece "Tentar de novo"', JSON.stringify(r.est) + ` (${r.ms} ms)`);
    chk(!r.est.exemplo, 'pendurado: sem "Dados de exemplo"');
    await r.pg.screenshot({ path: (process.env.PRINTS || '/tmp') + '/ux69_pendurado.png' });
    await r.ctx.close();
  } finally { await br.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
