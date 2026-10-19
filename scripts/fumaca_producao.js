// Navegação de fumaça no painel de PRODUÇÃO — SÓ LEITURA.
// Abre todas as telas do menu, vários projetos (abas, cartões, modo conferir, duplicatas, folhas, etiquetas), fundos e arquitetos,
// em computador e em celular, e anota: erro de JavaScript, erro no console, resposta 4xx/5xx do servidor e tela que não abriu.
// SEGURANÇA: o navegador só deixa passar GET. Qualquer POST/PATCH/PUT/DELETE (salvar, publicar, apagar…) é BLOQUEADO antes de sair,
// menos o login. Nada é gravado no painel nem no site. A senha não é gravada em lugar nenhum (nem no relatório).
//
// Uso (num computador da rede da CAMP, com Node 18+):
//   npm i playwright@1.48.2 && npx playwright install chromium        (uma vez, numa pasta qualquer)
//   PAINEL=http://192.168.15.60:8000 EMAIL=seu@email SENHA='…' node fumaca_producao.js
// Opcional: PROJETOS=12 (quantos projetos abrir; padrão 10), SAIDA=pasta (padrão ./fumaca-AAAAMMDD-HHMM)
// No fim: SAIDA/relatorio.txt (mande para o Claude) e SAIDA/*.png (prints de cada tela).
const fs = require('fs'), path = require('path');
let chromium; try { ({ chromium } = require('playwright')); } catch (_) { ({ chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright')); }
const BASE = (process.env.PAINEL || 'http://192.168.15.60:8000').replace(/\/$/, ''), EMAIL = process.env.EMAIL, SENHA = process.env.SENHA;
const NPROJ = +(process.env.PROJETOS || 10), CHROME = process.env.CHROME || undefined;
const agora = new Date(), carimbo = agora.toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1-$2');
const SAIDA = process.env.SAIDA || `fumaca-${carimbo}`;
if (!EMAIL || !SENHA) { console.error('Informe EMAIL e SENHA (variáveis de ambiente). Ex.: PAINEL=http://192.168.15.60:8000 EMAIL=... SENHA=... node fumaca_producao.js'); process.exit(2); }
fs.mkdirSync(SAIDA, { recursive: true });
const telas = [], bloqueados = [], semPrevia = new Set();
let atual = null;
const novaTela = (nome) => { atual = { nome, problemas: [], ms: 0 }; telas.push(atual); return atual; };
const anota = (txt) => { if (atual && !atual.problemas.includes(txt)) atual.problemas.push(txt); };
const arquivo = (n) => path.join(SAIDA, n.replace(/[^\w.-]+/g, '_').slice(0, 80) + '.png');
const espera = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const br = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  // só GET passa (e o login): nada é gravado
  await ctx.route('**/*', (r) => {
    const q = r.request(), u = q.url();
    if (q.method() === 'GET' || q.method() === 'HEAD' || q.method() === 'OPTIONS') return r.continue();
    if (q.method() === 'POST' && u.startsWith(BASE) && /\/api\/auth\/login$/.test(new URL(u).pathname)) return r.continue();
    bloqueados.push(`${atual ? atual.nome : '-'} · ${q.method()} ${u.replace(BASE, '')}`); return r.abort();
  });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => anota('erro de JavaScript: ' + String(e.message).split('\n')[0].slice(0, 200)));
  pg.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|ERR_BLOCKED|Failed to load resource: net::|status of (401|404)/i.test(m.text())) anota('console: ' + m.text().slice(0, 200)); });
  pg.on('response', r => { const u = r.url(); if (!u.startsWith(BASE) || !/\/api\//.test(u)) return;
    const m = r.status() === 404 && u.match(/\/api\/itens\/([^/]+)\/previa/); if (m) { semPrevia.add(decodeURIComponent(m[1])); return; }   /* folha sem imagem: vai numa lista à parte */
    if (r.status() >= 400 && r.status() !== 401) anota(`servidor ${r.status()}: ${r.request().method()} ${u.replace(BASE, '').slice(0, 140)}`); });

  // login
  novaTela('login');
  await pg.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  const lg = await pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [EMAIL, SENHA]);
  if (lg !== 200) { console.error(`Login recusado (${lg}). Confira EMAIL/SENHA.`); await br.close(); process.exit(3); }
  const eu = await pg.evaluate(() => fetch('/api/auth/eu').then(r => r.ok ? r.json() : {}).catch(() => ({})));
  const versao = await pg.evaluate(() => fetch('/api/versao').then(r => r.json()).catch(() => ({})));

  const visitar = async (nome, hash, extra) => {
    const t = novaTela(nome), t0 = Date.now();
    try {
      await pg.goto(BASE + '/#' + hash, { waitUntil: 'domcontentloaded' });
      await pg.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => anota('a tela demorou mais de 20 s para terminar de carregar'));
      await espera(400);
      const vis = await pg.evaluate(() => { const s = [...document.querySelectorAll('.content')].find(x => x.offsetParent !== null && x.getBoundingClientRect().height > 0); return ((s || document.querySelector('.main') || document.body).innerText || '').trim().length; });
      if (vis < 20) anota('a tela abriu vazia');
      const pagina = await pg.evaluate(() => { const s = [...document.querySelectorAll('.content')].find(x => x.offsetParent !== null); return /não encontrad/i.test(((s || document.body).innerText || '').slice(0, 400)); });
      if (pagina) anota('a tela diz "não encontrado"');
      if (extra) await extra(t);
      const larg = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (larg > 4) anota(`rolagem para o lado (${larg}px)`);
      await pg.screenshot({ path: arquivo(nome), fullPage: false });
    } catch (e) { anota('não abriu: ' + String(e.message).split('\n')[0].slice(0, 160)); }
    t.ms = Date.now() - t0;
  };

  // 1) todas as telas do menu
  await pg.goto(BASE + '/', { waitUntil: 'domcontentloaded' }); await pg.waitForLoadState('networkidle').catch(() => {});
  const menu = await pg.evaluate(() => [...document.querySelectorAll('.side [data-v]')].map(b => { const c = b.cloneNode(true); c.querySelectorAll('kbd,.badge,.cnt,span').forEach(x => x.remove()); return [b.dataset.v, (c.textContent || '').trim()]; }).filter(([v]) => v));
  for (const [v, rot] of menu) await visitar(`menu · ${rot || v}`, v);

  // 2) projetos de verdade: com folhas, variados
  const lista = await pg.evaluate(() => fetch('/api/projetos?com_folhas=true&por_pagina=200').then(r => r.json()).catch(() => ({})));
  const projs = (lista.itens || lista.projetos || lista.resultados || []).map(p => p.codigo).filter(Boolean);
  const escolhidos = [];
  for (let i = 0; i < projs.length && escolhidos.length < NPROJ; i += Math.max(1, Math.floor(projs.length / NPROJ))) escolhidos.push(projs[i]);
  for (const c of escolhidos) {
    await visitar(`projeto ${c}`, 'projeto/' + c, async () => {
      // abas
      const abas = await pg.$$eval('.content.on .tabs button, .content.on [role="tab"]', l => l.map(b => b.textContent.trim()).filter(Boolean));
      for (const a of abas) {
        const b = pg.locator('.content.on .tabs button, .content.on [role="tab"]', { hasText: a }).first();
        if (await b.count()) { await b.click({ timeout: 5000 }).catch(() => anota(`aba "${a}" não clicou`)); await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await espera(200); }
      }
      const pr = pg.locator('.content.on .tabs button, .content.on [role="tab"]').first(); if (await pr.count()) await pr.click().catch(() => {});
      // cartões: Decidir / Detalhes dos lotes (só abrem painéis)
      for (const txt of ['Decidir', 'Detalhes dos lotes', 'Ver detalhes']) {
        const b = pg.locator('.content.on button, .content.on a', { hasText: txt }).first();
        if (await b.count() && await b.isVisible().catch(() => false)) { await b.click({ timeout: 5000 }).catch(() => anota(`"${txt}" não clicou`)); await espera(400); await pg.screenshot({ path: arquivo(`projeto ${c} ${txt}`) }).catch(() => {}); }
      }
      // abrir uma folha na gaveta de revisão (só leitura) e fechar
      const th = pg.locator('.thumb[data-rev-abrir]').first();
      if (await th.count()) { await th.click({ timeout: 5000 }).catch(() => {}); await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await espera(300); await pg.screenshot({ path: arquivo(`projeto ${c} gaveta da folha`) }).catch(() => {}); await pg.keyboard.press('Escape').catch(() => {}); }
    });
    await visitar(`conferir ${c}`, 'conferir/' + c, async () => { for (let k = 0; k < 3; k++) { await pg.keyboard.press('ArrowDown').catch(() => {}); await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await espera(250); } });
    await visitar(`duplicatas ${c}`, 'duplicatas/' + c);
    await visitar(`etiquetas ${c}`, 'etiquetas/projeto/' + c, async () => {
      const opts = await pg.$$eval('#l-fmt option', l => l.map(o => o.value)).catch(() => []);
      for (const f of opts.slice(0, 8)) { await pg.selectOption('#l-fmt', f).catch(() => {}); await espera(250); }
      if (opts.includes('150x100')) { await pg.selectOption('#l-fmt', '150x100').catch(() => {}); await espera(300); await pg.screenshot({ path: arquivo(`etiquetas ${c} 150x100`) }).catch(() => {}); }
    });
    const det = await pg.evaluate(c => fetch('/api/projetos/' + c + '/detalhe').then(r => r.json()).catch(() => ({})), c);
    const folha = ((det.itens || [])[0] || {}).codigo; if (folha) await visitar(`folha ${folha}`, 'item/' + folha);
  }

  // 3) fundos e arquitetos
  const fundos = await pg.evaluate(() => fetch('/api/fundos').then(r => r.json()).then(j => (j.itens || j.fundos || j || []).map(f => f.codigo || f[0]).filter(Boolean)).catch(() => []));
  for (const f of fundos.slice(0, 5)) await visitar(`fundo ${f}`, 'fundo/' + f);

  // 4) celular: algumas telas
  await pg.setViewportSize({ width: 390, height: 844 });
  for (const [v, rot] of menu.slice(0, 6)) await visitar(`celular · ${rot || v}`, v);
  if (escolhidos[0]) { await visitar(`celular · projeto ${escolhidos[0]}`, 'projeto/' + escolhidos[0]); await visitar(`celular · conferir ${escolhidos[0]}`, 'conferir/' + escolhidos[0]); }
  await br.close();

  // relatório
  const ruins = telas.filter(t => t.problemas.length), lentas = telas.filter(t => t.ms > 8000);
  const linhas = [
    `Navegação de fumaça (só leitura) — ${agora.toLocaleString('pt-BR')}`,
    `Painel: ${BASE} · versão: ${versao.data || ''} ${versao.assunto || versao.versao || ''} · usuário: ${(eu && (eu.email || (eu.usuario || {}).email)) || EMAIL} (${(eu && (eu.papel || (eu.usuario || {}).papel)) || '?'})`,
    `${telas.length} telas abertas · ${ruins.length} com problema · ${lentas.length} lentas (> 8 s) · ${bloqueados.length} gravações bloqueadas (normal: a navegação não grava nada)`, '',
    ...(ruins.length ? ['TELAS COM PROBLEMA', ...ruins.flatMap(t => [`- ${t.nome} (${(t.ms / 1000).toFixed(1)} s)`, ...t.problemas.map(p => `    · ${p}`)]), ''] : ['Nenhuma tela com problema.', '']),
    ...(lentas.length ? ['TELAS LENTAS', ...lentas.map(t => `- ${t.nome}: ${(t.ms / 1000).toFixed(1)} s`), ''] : []),
    'TODAS AS TELAS', ...telas.map(t => `- ${t.problemas.length ? '✖' : '✔'} ${t.nome} (${(t.ms / 1000).toFixed(1)} s)`), '',
    ...(semPrevia.size ? [`FOLHAS SEM IMAGEM (a prévia não existe no servidor): ${semPrevia.size}`, ...[...semPrevia].slice(0, 40).map(c => '- ' + c), ''] : []),
    ...(bloqueados.length ? ['GRAVAÇÕES BLOQUEADAS (a tela tentou gravar sozinha ao abrir — vale olhar)', ...[...new Set(bloqueados)].slice(0, 60).map(b => '- ' + b)] : []),
  ];
  fs.writeFileSync(path.join(SAIDA, 'relatorio.txt'), linhas.join('\n') + '\n');
  console.log(linhas.slice(0, 3).join('\n')); console.log(`\nRelatório: ${path.join(SAIDA, 'relatorio.txt')} · prints em ${SAIDA}/`);
  process.exit(ruins.length ? 1 : 0);
})().catch(async e => { console.error('ERRO', e.message); process.exit(1); });
