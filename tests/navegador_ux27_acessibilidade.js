// UX-27 · acessibilidade WCAG 2.2 AA (Playwright, Chromium de verdade). Servidor PRÓPRIO, nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8954)
//   CAMP_BASE=http://127.0.0.1:8954 node tests/navegador_ux27_acessibilidade.js
// Auditoria automática, SEM dependência nova no repositório, nas telas Home (Precisa de você), Material novo, Problemas, Projetos e na gaveta
// "Revisar folha", nos temas claro e escuro:
//  - todo campo (input/select/textarea) do DOM tem nome acessível (aria-label, aria-labelledby, <label>, title ou placeholder);
//  - h1 visíveis = 1 por tela, e as telas inativas ficam fora da árvore de acessibilidade (hidden);
//  - nenhum texto visível com tamanho computado < 12 px (a impressão das etiquetas não entra: tem tamanhos físicos próprios);
//  - contraste dos tokens de texto (--ink, --ink2, --ink3, --blue, --red, --green, --amber) ≥ 4,5 sobre --bg/--surface/--surface2,
//    e contraste computado de cada texto visível sobre o fundo efetivo ≥ 4,5 (≥ 3 para texto grande; botões desativados não entram);
//  - foco visível (anel ≥ 2 px) em cada elemento alcançado com Tab;
//  - as etapas compactas "1 2 3 4 5 6 7" têm o nome da etapa (aria-label e title) em cada número.
// Opcional: AXE_JS=/caminho/axe.min.js (axe-core instalado fora do repo, ex.: npm i axe-core numa pasta temporária) roda também as
// regras "label" e "color-contrast" do axe em cada tela. Sem AXE_JS, só as verificações próprias acima.
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8954';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const AXE = process.env.AXE_JS && fs.existsSync(process.env.AXE_JS) ? fs.readFileSync(process.env.AXE_JS, 'utf-8') : null;
const linhas = [], prob = [], erros = [];
const chk = (ok, m, det) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m + (!ok && det ? '\n        ' + det : '')); if (!ok) prob.push(m) };
const amostra = (l, n = 8) => process.env.DUMP ? '\n          ' + l.join('\n          ') : l.slice(0, n).join(' | ') + (l.length > n ? ` | … (+${l.length - n})` : '');

// tudo o que a auditoria mede, numa função só, executada dentro da página
function auditar() {
  const vis = e => !!(e.offsetParent || (getComputedStyle(e).position === 'fixed' && e.getClientRects().length)) && getComputedStyle(e).visibility !== 'hidden';
  const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
  const desc = e => { const id = e.id ? '#' + e.id : ''; const cl = typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''; return e.tagName.toLowerCase() + id + cl };
  // 1) campos sem nome acessível (todos os do DOM)
  const nome = e => {
    if ((e.getAttribute('aria-label') || '').trim()) return true;
    const lb = e.getAttribute('aria-labelledby'); if (lb && lb.split(/\s+/).some(i => txt(document.getElementById(i)))) return true;
    if (e.labels && [...e.labels].some(l => txt(l))) return true;
    if ((e.getAttribute('title') || '').trim()) return true;
    if ((e.getAttribute('placeholder') || '').trim()) return true;
    if (e.type === 'submit' || e.type === 'button') return !!(e.value || '').trim();
    return false };
  const campos = [...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e => !e.closest('[aria-hidden="true"]'));   // aria-hidden + tabindex=-1: substituído por cartões com rótulo
  const semNome = campos.filter(e => !nome(e)).map(desc);
  // 2) h1 visíveis; telas inativas fora da árvore (hidden)
  const h1s = [...document.querySelectorAll('h1')].filter(vis).map(e => txt(e).slice(0, 40));
  const inativasSemHidden = [...document.querySelectorAll('section.content:not(.on)')].filter(s => !s.hidden).map(s => s.id);
  // 3) tamanho e 4) contraste de cada texto visível
  const rgba = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return [0, 0, 0, 0]; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1] };
  const sob = (c, b) => [0, 1, 2].map(i => c[i] * c[3] + b[i] * (1 - c[3])).concat(1);
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4) }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]) };
  const razao = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) };
  const fundo = e => { const pilha = []; let temImg = false; for (let n = e; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n); if (cs.backgroundImage !== 'none' && !/gradient/.test(cs.backgroundImage)) temImg = true; const c = rgba(cs.backgroundColor); if (c[3] > 0) { pilha.push(c); if (c[3] >= 1) break } } let b = [255, 255, 255, 1]; if (!pilha.length || pilha[pilha.length - 1][3] < 1) b = rgba(getComputedStyle(document.body).backgroundColor); for (let i = pilha.length - 1; i >= 0; i--) b = sob(pilha[i], b); return temImg ? null : b };
  const opac = e => { let o = 1; for (let n = e; n && n.nodeType === 1; n = n.parentElement) o *= +getComputedStyle(n).opacity; return o };
  const pequenos = [], baixos = [];
  for (const e of document.querySelectorAll('body *')) {
    if (['SCRIPT', 'STYLE', 'OPTION', 'svg'].includes(e.tagName) || e.closest('svg')) continue;
    const temTxt = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!temTxt || !vis(e)) continue;
    const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    const o = opac(e); if (o < 0.05) continue;   // invisível (aparece só no hover/foco): medido quando aparece
    const cs = getComputedStyle(e), fs = parseFloat(cs.fontSize);
    const t = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim().slice(0, 24);
    if (fs < 11.95) pequenos.push(`${desc(e)} ${fs}px "${t}"`);
    if (e.closest(':disabled,[aria-disabled="true"],.disabled') ) continue;
    const b = fundo(e); if (!b) continue;
    const c = rgba(cs.color); const cf = sob([c[0], c[1], c[2], c[3] * o], b);
    const grande = fs >= 24 || (fs >= 18.66 && +cs.fontWeight >= 700), min = grande ? 3 : 4.5, rz = razao(cf, b);
    if (rz < min - 0.005) baixos.push(`${desc(e)} ${rz.toFixed(2)} "${t}" (${cs.color} sobre rgb(${b.slice(0, 3).map(Math.round)}))`);
  }
  // campos (o texto do valor não é nó de texto): mesmo critério, sobre o fundo do próprio campo
  for (const e of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=range]):not([type=color]),select,textarea')) {
    if (!vis(e) || e.disabled || opac(e) < 0.05) continue; const b = fundo(e); if (!b) continue; const cs = getComputedStyle(e), c = rgba(cs.color), rz = razao(sob([c[0], c[1], c[2], c[3] * opac(e)], b), b);
    if (rz < 4.495) baixos.push(`${desc(e)} ${rz.toFixed(2)} campo (${cs.color} sobre rgb(${b.slice(0, 3).map(Math.round)}))`) }
  // tokens de texto
  const raiz = getComputedStyle(document.documentElement), tok = n => { const d = document.createElement('i'); d.style.color = `var(${n})`; document.body.appendChild(d); const c = rgba(getComputedStyle(d).color); d.remove(); return c };
  const tokens = [];
  for (const t of ['--ink', '--ink2', '--ink3', '--blue', '--red', '--green', '--amber']) for (const f of ['--bg', '--surface', '--surface2']) { const rz = razao(tok(t), tok(f)); if (rz < 4.5) tokens.push(`${t} sobre ${f}: ${rz.toFixed(2)} (${raiz.getPropertyValue(t).trim()} / ${raiz.getPropertyValue(f).trim()})`) }
  // etapas compactas (Material novo): cada número com o nome da etapa
  const etapas = [...document.querySelectorAll('.steps.caminho.compacto')].filter(vis);
  const etapasSemNome = etapas.flatMap(s => [...s.querySelectorAll(':scope > span')].filter(sp => !/\.\s*\S/.test(sp.getAttribute('aria-label') || '') || !/\.\s*\S/.test(sp.title || '')).map(sp => sp.textContent));
  const etapasRoleImg = etapas.filter(s => s.getAttribute('role') === 'img').length;
  return { campos: campos.length, semNome, h1s, inativasSemHidden, pequenos, baixos, tokens, etapas: etapas.length, etapasSemNome, etapasRoleImg };
}

(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login');
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(m.text()) });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/#painel'); await page.waitForTimeout(1800);
  const item = await page.evaluate(() => API('/api/projetos/F026-P0001/itens').then(l => (l.itens || l)[0].codigo).catch(() => 'F026-P0001-1968-S01-D00001'));
  const TELAS = [
    ['Home', async () => { await page.evaluate(() => go('painel')); await page.waitForTimeout(1500) }],
    ['Material novo', async () => { await page.evaluate(() => go('filas')); await page.waitForTimeout(1500) }],
    ['Problemas', async () => { await page.evaluate(() => go('erros')); await page.waitForTimeout(1500) }],
    ['Projetos', async () => { await page.evaluate(() => go('projetos')); await page.waitForTimeout(1500) }],
    ['Revisar folha', async () => { await page.evaluate(c => { nav('projeto/F026-P0001'); return new Promise(ok => setTimeout(() => { abrirRevisaoItem(c); ok() }, 900)) }, item); await page.waitForTimeout(1800) }],
  ];
  for (const tema of ['light', 'dark']) {
    await page.evaluate(t => { document.documentElement.dataset.theme = t }, tema);
    for (const [nome, ir] of TELAS) {
      await ir();
      const a = await page.evaluate(auditar);
      const T = `[${tema === 'light' ? 'claro' : 'escuro'}] ${nome}`;
      if (tema === 'light') {
        chk(a.semNome.length === 0, `${T}: todo campo tem nome acessível (${a.campos} campos no DOM)`, amostra(a.semNome, 20));
        chk(a.h1s.length === 1, `${T}: um só h1 visível (${a.h1s.length}: ${a.h1s.join(' · ')})`);
        chk(a.inativasSemHidden.length === 0, `${T}: telas inativas com hidden (fora do leitor de tela)`, amostra(a.inativasSemHidden));
        chk(a.pequenos.length === 0, `${T}: nenhum texto visível < 12 px`, amostra(a.pequenos, 20));
      }
      chk(a.baixos.length === 0, `${T}: contraste de cada texto visível ≥ 4,5 (3 se grande)`, amostra(a.baixos, 20));
      if (nome === 'Home') chk(a.tokens.length === 0, `${T}: tokens de texto com contraste ≥ 4,5 sobre --bg/--surface/--surface2`, a.tokens.join(' | '));
      if (nome === 'Material novo' && tema === 'light') chk(a.etapas > 0 && a.etapasSemNome.length === 0 && a.etapasRoleImg === 0,
        `${T}: etapas "1 2 3 4 5 6 7" com o nome da etapa em cada número (aria-label e title; ${a.etapas} trilhos)`, `sem nome: ${a.etapasSemNome.join(',')} · role=img: ${a.etapasRoleImg}`);
      if (AXE) {
        await page.evaluate(AXE);
        const res = await page.evaluate(() => axe.run(document, { runOnly: { type: 'rule', values: ['label', 'color-contrast', 'select-name', 'aria-input-field-name'] } }).then(r => r.violations.map(v => `${v.id}: ${v.nodes.length} (${v.nodes.slice(0, 4).map(n => n.target.join(' ')).join(', ')})`)));
        chk(res.length === 0, `${T}: axe-core (label, select-name, color-contrast) sem violações`, res.join(' | '));
      }
    }
  }
  // 5) foco visível com Tab (tema claro, Home e Material novo)
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light' });
  for (const [nome, v] of [['Home', 'painel'], ['Material novo', 'filas'], ['Problemas', 'erros']]) {
    await page.evaluate(v => go(v), v); await page.waitForTimeout(1300);
    await page.evaluate(() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); window.scrollTo(0, 0) });
    await page.mouse.click(5, 890).catch(() => {});
    const sem = [], vistos = new Set();
    for (let i = 0; i < 45; i++) {
      await page.keyboard.press('Tab');
      const f = await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e); const id = e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/)[0] : '') + ' "' + (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 18) + '"';
        return { id, ok: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2 } });
      if (!f) continue; if (vistos.has(f.id)) continue; vistos.add(f.id); if (!f.ok) sem.push(f.id);
    }
    chk(vistos.size >= 10 && sem.length === 0, `${nome}: foco visível (anel ≥ 2 px) em todo elemento alcançado com Tab (${vistos.size} elementos)`, amostra(sem, 20));
  }
  chk(erros.length === 0, 'nenhum erro de JavaScript', amostra(erros, 5));
  console.log(linhas.join('\n')); if (!AXE) console.log('(axe-core não informado em AXE_JS: só as verificações próprias)');
  console.log(prob.length ? `\n${prob.length} FALHA(S)` : '\nTUDO OK');
  await b.close(); process.exit(prob.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2) });
