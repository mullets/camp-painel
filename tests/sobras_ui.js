// Checagens de tela (Playwright, Chromium de verdade) dos itens do cartão "Sobras".
// Uso (servidor PRÓPRIO, nunca a porta 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 ../tests/servidor_wp_falso.py 8781)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8781 node tests/sobras_ui.js [auditoria] [fundo] [publicar]
// "publicar" exige o servidor com WordPress falso (tests/servidor_wp_falso.py); "auditoria" e "fundo" rodam também no uvicorn comum.
// O navegador só fala com o servidor de teste: todo pedido para fora é barrado (e anotado em BLOQUEADAS).
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8781', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const ETAPAS = process.argv.slice(2).length ? process.argv.slice(2) : ['auditoria', 'fundo', 'publicar'];
const problemas = [], linhas = [], BLOQUEADAS = [];   // pedidos para fora do servidor de teste: barrados e anotados
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
// mexe no banco do servidor de teste (só o banco semeado, nunca produção)
const pyArg = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

async function auditoria(page) {
  pyArg(`
evs=[('item','F026-P0001-1960-S01-D00009','folha_movida',{'de':'F026-P0002-1960-S01-D00001','para':'F026-P0001-1960-S01-D00009','motivo':'caiu no projeto errado'}),
     ('projeto','F026-P0001','publicacao_guiada',{'feitos':['dossie','autorizar'],'folhas_criadas':11,'publicados':13,'ok':True}),
     ('projeto','F026-P0001','site_publicar',{'ok':12,'falhas':0}),
     ('projeto','F026-P0001','editado',{'antes':{'titulo':'Casa A','ano':1960},'depois':{'titulo':'Casa B','ano':1960}}),
     ('projeto','F026-P0001','tipo_que_ninguem_conhece',{'campo_estranho':'valor x','quantidade_total':3,'ligado':True,'vazio':None})]
for e,c,t,d in evs: con.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe,quando) VALUES (?,?,?,'rafael@camp.arq.br',?,datetime('now','+1 minute'))",(e,c,t,json.dumps(d,ensure_ascii=False)))`);
  await page.goto(BASE + '/#auditoria'); await page.waitForSelector('#au-body tr[data-audit-id]', { timeout: 15000 });
  await page.waitForTimeout(800);
  const linhasAu = await page.$$eval('#au-body tr[data-audit-id]', trs => trs.map(t => ({ id: t.dataset.auditId, frase: t.querySelector('.au-frase').textContent, det: t.querySelector('.au-det').textContent })));
  const det = (re) => linhasAu.find(l => re.test(l.det));
  chk(!linhasAu.some(l => /[{}"]/.test(l.det)), 'a coluna Detalhe não mostra JSON cru (sem { } nem aspas): ' + JSON.stringify(linhasAu.filter(l => /[{}"]/.test(l.det)).slice(0, 2)));
  chk(!!det(/^Moveu a folha F026-P0002-1960-S01-D00001 para F026-P0001-1960-S01-D00009/), 'folha_movida vira "Moveu a folha X para Y": ' + JSON.stringify(linhasAu.map(l => l.det).slice(0, 6)));
  chk(!!det(/^Publicou a página do projeto e 12 folhas/), 'publicacao_guiada vira "Publicou a página do projeto e 12 folhas"');
  chk(!!det(/^Publicou 12 registros no site$/), 'site_publicar vira "Publicou 12 registros no site"');
  chk(!!det(/^Mudou título: Casa A → Casa B$/), 'edição mostra só o que mudou, com o nome do campo em português ("Mudou título: Casa A → Casa B")');
  const gen = det(/Campo estranho: valor x/);
  chk(!!gen && /Quantidade total: 3/.test(gen.det) && /Ligado: sim/.test(gen.det) && !/Vazio/.test(gen.det), 'tipo desconhecido cai no "Campo: valor" legível (sem _ , true vira sim, vazio some): ' + (gen && gen.det));
  chk(linhasAu.every(l => l.det.length <= 80), 'a coluna continua com no máximo 80 caracteres');
  // a janela do evento: a frase inteira e o JSON recolhido em "ver dados"
  const alvo = det(/^Moveu a folha/);
  if (alvo) {
    const sel = `#au-body tr[data-audit-id="${alvo.id}"]`;
    if (!(await page.isVisible(sel))) await page.click(`#au-body [data-au-grupo="${await page.$eval(sel, t => t.dataset.auFilho)}"]`);   // passo de um grupo: abre o grupo antes
    await page.click(sel + ' td.au-det'); await page.waitForSelector('#d-body .au-dados', { timeout: 5000 });
    const corpo = await page.$eval('#d-body', b => ({ frase: (b.querySelector('.au-frase-det') || {}).textContent || '', aberto: b.querySelector('.au-dados').open, json: b.querySelector('.au-json').textContent, visivel: b.querySelector('.au-json').checkVisibility() }));
    chk(/caiu no projeto errado/.test(corpo.frase) && !corpo.aberto && !corpo.visivel, 'na janela, a frase completa aparece e o JSON começa recolhido: ' + JSON.stringify(corpo).slice(0, 200));
    await page.click('#d-body .au-dados summary');
    chk(await page.$eval('#d-body .au-json', p => p.checkVisibility() && /"tainacan_item_id_antigo"|"motivo"/.test(p.textContent)), '"ver dados" abre o JSON original');
    await page.keyboard.press('Escape');
  }
}

async function fundo(page) {
  const F = 'F026';
  // um problema em aberto numa FOLHA de um projeto do fundo (o cabeçalho tem que contar o projeto como "com problema")
  pyArg(`
r=con.execute("SELECT i.codigo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE p.fundo_codigo='${F}' AND p.mesclado_em IS NULL ORDER BY i.codigo LIMIT 1").fetchone()
if r and not con.execute("SELECT 1 FROM erro WHERE codigo=? AND descricao='teste sobras'",(r[0],)).fetchone(): con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao) VALUES ('corrigir','outro','operador',?,'teste sobras')",(r[0],))`);
  const banco = JSON.parse(pyArg(`
v="SELECT codigo FROM projeto WHERE fundo_codigo='${F}' AND mesclado_em IS NULL"
q=lambda s: con.execute(s).fetchone()[0]
print(json.dumps({'todos':q(f"SELECT COUNT(*) FROM ({v})"),'publicado':q(f"SELECT COUNT(*) FROM projeto WHERE codigo IN ({v}) AND status_site='no_ar'"),'nao_publicado':q(f"SELECT COUNT(*) FROM projeto WHERE codigo IN ({v}) AND status_site<>'no_ar'"),
 'com_problema':q(f"SELECT COUNT(*) FROM ({v}) x WHERE EXISTS (SELECT 1 FROM erro e WHERE (e.codigo=x.codigo OR e.codigo LIKE x.codigo||'-%') AND e.situacao IN ('aberto','em_correcao'))"),
 'folhas':q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo IN ({v})"),'folhas_publicadas':q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo IN ({v}) AND status_site='no_ar'")}))`));
  await page.goto(BASE + '/#fundo/' + F); await page.waitForSelector('#fd .fd-contagens [data-fd-cont]', { timeout: 15000 });
  const tela = Object.fromEntries(await page.$$eval('#fd .fd-contagens [data-fd-cont]', bs => bs.map(b => [b.dataset.fdCont, +b.querySelector('b').textContent.replace(/\D/g, '')])));
  for (const [k, n] of Object.entries(banco)) chk(tela[k] === n, `cabeçalho do fundo: "${k}" mostra ${tela[k]}, o banco tem ${n}`);
  chk(banco.com_problema >= 1 && 'gente' in tela, 'o cabeçalho mostra "com problema" (≥1 no teste) e "precisam de você"');
  chk(!/itens publicados/.test(await page.textContent('#fd .dethdr')), 'o cabeçalho não usa mais "itens publicados" (contagem do site, que não batia com o painel)');
  // cada número abre a lista de Projetos filtrada, com o mesmo total
  const situacaoDe = { folhas: 'todos', folhas_publicadas: 'publicado' };
  for (const k of ['todos', 'publicado', 'nao_publicado', 'com_problema', 'gente', 'folhas']) {
    await page.goto(BASE + '/#fundo/' + F); await page.waitForSelector(`#fd [data-fd-cont="${k}"]`, { timeout: 15000 });
    const n = +(await page.textContent(`#fd [data-fd-cont="${k}"] b`)).replace(/\D/g, '');
    await page.click(`#fd [data-fd-cont="${k}"]`);
    await page.waitForFunction(() => location.hash === '#projetos', null, { timeout: 5000 });
    const sit = situacaoDe[k] || k;
    await page.waitForFunction((s) => !!document.querySelector(`#proj-chips [data-proj-sit="${s}"][aria-pressed="true"]`) && /Mostrando|Nenhum projeto/.test((document.querySelector('#v-projetos .cnt') || {}).textContent || ''), sit, { timeout: 10000 });
    await page.waitForTimeout(400);
    const st = await page.evaluate(() => ({ fundo: document.getElementById('proj-fundo').value, ordem: document.getElementById('proj-ordem').value, cnt: document.querySelector('#v-projetos .cnt').textContent, linhas: [...document.querySelectorAll('#projetos-body tr[data-nav]')].map(t => t.dataset.nav) }));
    const total = /Nenhum/.test(st.cnt) ? 0 : +(st.cnt.match(/de ([\d.]+)/) || [0, '-1'])[1].replace(/\./g, '');
    const esperado = k === 'folhas' ? banco.todos : n;
    chk(st.fundo === F && total === esperado && st.linhas.every(c => c.startsWith('projeto/' + F)), `"${k}" abre Projetos do ${F} filtrado (${sit}) com ${esperado}: fundo=${st.fundo} total=${total} (${st.cnt})`);
    if (k === 'folhas') chk(st.ordem === 'folhas', '"folhas" abre a lista ordenada por folhas: ' + st.ordem);
  }
  await page.evaluate(() => { PROJ_ESTADO = { ...PROJ_ESTADO, fundo: '', situacao: 'todos', ordem: 'codigo' } });
}

// #104 · precisa do servidor com WordPress FALSO (tests/servidor_wp_falso.py): publica de verdade pelo painel, sem tocar no site
async function publicar(page) {
  const P = 'F026-P0990';
  pyArg(`
if not con.execute("SELECT 1 FROM projeto WHERE codigo='${P}'").fetchone():
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F026',990)")
    con.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',990,'Residência Sobras, Rua das Flores','1965','São Paulo')")
    for n in (1,2,3): con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,status_site) VALUES (?,?,'S01',?,'importado','nao_publicado')",(f"${P}-1965-S01-D0000{n}",'${P}',n))
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,status_site,retida) VALUES ('${P}-1965-S01-D00004','${P}','S01',4,'importado','nao_publicado',1)")
    con.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES ('F026','autorizado','Família','Termo assinado')")`);
  await page.goto(BASE + '/#projeto/' + P); await page.waitForTimeout(2500);
  await page.evaluate((c) => abrirPublicacaoGuiada(c), P);
  await page.waitForSelector('#pub-go:not([disabled])', { timeout: 10000 });
  await page.click('#pub-go');
  await page.waitForSelector('#d-body .pub-resultado', { timeout: 30000 });
  const tela = await page.evaluate(() => ({ titulo: document.getElementById('d-title').textContent, corpo: document.getElementById('d-body').innerText,
    link: [...document.querySelectorAll('#d-body .pub-resultado a')].map(a => ({ txt: a.textContent.trim(), href: a.getAttribute('href'), alvo: a.target, cls: a.className })) }));
  const api = JSON.parse(pyArg(`
r=con.execute("SELECT resultado FROM tarefa_publicacao WHERE projeto_codigo='${P}' ORDER BY id DESC LIMIT 1").fetchone()
print(r[0] if r else '{}')`));
  const banco = JSON.parse(pyArg(`
print(json.dumps({'pub':con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND status_site='no_ar'").fetchone()[0],'st':con.execute("SELECT status_site FROM projeto WHERE codigo='${P}'").fetchone()[0],
 'url':con.execute("SELECT url FROM wp_pagina WHERE codigo_detectado='${P}'").fetchone()[0]}))`));
  chk(banco.st === 'no_ar' && banco.pub === 3, 'o projeto foi publicado de verdade pelo painel (3 folhas; a retida fica de fora): ' + JSON.stringify(banco));
  chk(api.url_publica === banco.url && api.url_origem === 'site' && api.folhas_publicadas === 3 && api.folhas_fora === 1 && (api.projeto || {}).codigo === P, 'o resultado da tarefa traz o endereço da página (do espelho do site) e o que foi publicado: ' + JSON.stringify(api).slice(0, 300));
  chk(/Publicado/.test(tela.titulo) && /O que ficou público/.test(tela.corpo) && /Residência Sobras/.test(tela.corpo) && /3 folhas publicadas/.test(tela.corpo) && /1 folha ficou só no painel/.test(tela.corpo), 'a tela de resultado diz o que ficou público: "' + tela.corpo.slice(0, 300) + '"');
  const ver = tela.link.find(a => a.txt === 'Ver página pública');
  chk(!!ver && ver.href === banco.url && ver.alvo === '_blank' && /pri/.test(ver.cls), 'botão "Ver página pública" (principal) com o endereço do backend, em nova aba: ' + JSON.stringify(tela.link));
  if (ver) {
    const antes = BLOQUEADAS.length;
    const [aba] = await Promise.all([page.context().waitForEvent('page', { timeout: 5000 }), page.click('#d-body .pub-resultado a:text("Ver página pública")')]);
    await page.waitForTimeout(800);
    chk(BLOQUEADAS.slice(antes).includes(banco.url), 'o clique abre, numa aba nova, a página pública do projeto (pedido barrado no teste: nada sai para fora): ' + JSON.stringify(BLOQUEADAS.slice(antes)));
    await aba.close();
  }
  chk(!/Publicar agora/.test(tela.corpo), 'depois de publicar a janela não oferece "Publicar agora" de novo');
  await page.keyboard.press('Escape');
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.route('**/*', rt => { const u = rt.request().url(); if (u.startsWith(BASE)) return rt.continue(); BLOQUEADAS.push(u); return rt.abort() });   // só o servidor de teste: nada sai para o site real
  const page = await ctx.newPage(); const erros = [];
  page.on('pageerror', e => erros.push(String(e)));
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login do usuário semeado');
  const mapa = { auditoria, fundo, publicar };
  for (const e of ETAPAS) { if (!mapa[e]) continue; linhas.push(`--- ${e}`); try { await mapa[e](page) } catch (x) { chk(false, `${e}: ${x.message.split('\n')[0]}`) } }
  chk(!erros.length, 'sem erro de JavaScript na página: ' + erros.slice(0, 2).join(' | '));
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== SOBRAS: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})();
