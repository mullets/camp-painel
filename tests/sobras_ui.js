// Checagens de tela (Playwright, Chromium de verdade) dos itens do cartão "Sobras".
// Uso (servidor PRÓPRIO, nunca a porta 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8781)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8781 node tests/sobras_ui.js [auditoria] [fundo] [publicar]
const path = require('path'), { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8781', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const ETAPAS = process.argv.slice(2).length ? process.argv.slice(2) : ['auditoria', 'fundo', 'publicar'];
const problemas = [], linhas = [];
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

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());   // só o servidor de teste: nada sai para o site real
  const page = await ctx.newPage(); const erros = [];
  page.on('pageerror', e => erros.push(String(e)));
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login do usuário semeado');
  const mapa = { auditoria };
  for (const e of ETAPAS) { if (!mapa[e]) continue; linhas.push(`--- ${e}`); try { await mapa[e](page) } catch (x) { chk(false, `${e}: ${x.message.split('\n')[0]}`) } }
  chk(!erros.length, 'sem erro de JavaScript na página: ' + erros.slice(0, 2).join(' | '));
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== SOBRAS: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})();
