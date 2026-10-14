// Tela Decisões com um caso de CADA tipo (Playwright, Chromium de verdade): projeto parecido, lote com números repetidos,
// dado diferente do cadastro (divergência do CAMP Vision) e mesmo nome em outro fundo. Também o aviso de fundo parecido.
// Uso (servidor PRÓPRIO numa porta 8870-8879, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/dec.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/dec.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8871)
//   CAMP_DB_PATH=/tmp/dec.db CAMP_BASE=http://127.0.0.1:8871 node tests/decisoes_tipos_ui.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8871', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [], BLOQUEADAS = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

function semear() {
  return py(`
con.execute("DELETE FROM decisao_chave"); con.execute("DELETE FROM decisao")
con.execute("UPDATE configuracao SET valor='http://127.0.0.1:9' WHERE chave='wp.url'")
p=con.execute("SELECT codigo,fundo_codigo,titulo,ano FROM projeto WHERE codigo='F026-P0001'").fetchone()
o=con.execute("SELECT codigo,fundo_codigo,titulo FROM projeto WHERE codigo='F023-P0011'").fetchone()
def ins(tipo,chave,fundo,titulo,ctx,origem='campvision'):
    con.execute("INSERT INTO decisao (tipo,chave,fundo_codigo,titulo,contexto,origem) VALUES (?,?,?,?,?,?)",(tipo,chave,fundo,titulo,json.dumps(ctx,ensure_ascii=False),origem))
ins('projeto_parecido','auto-ui-1','F026','Casa Taruma',{'pedido':{'titulo':'Casa Taruma','ano':1968,'identificacao_original':'scan Taruma'},'candidatos':[{'codigo':p[0],'titulo':p[2],'ano':p[3],'cidade':'São Paulo','folhas':6,'score':0.97,'nivel':'forte','motivos':['mesmo nome (igual sem acento, maiúscula e palavras genéricas)']}]},'estacao')
ins('lote_colide','lote_colide:999:1','F026','Lote Tarumã 2',{'lote_id':999,'lote_nome':'Lote Tarumã 2','projeto_codigo':p[0],'projeto_titulo':p[2],'folhas_no_projeto':6,'maior_d':6,'folhas_no_lote':4,
  'colisoes':[{'codigo':p[0]+'-1968-S01-D00002','serie':'S01','d':2,'existente':p[0]+'-1968-S01-D00002','existente_revisao':'pendente','existente_status':'nao_publicado','existente_titulo':'Planta térreo'},
              {'codigo':p[0]+'-1968-S01-D00003','serie':'S01','d':3,'existente':p[0]+'-1968-S01-D00003','existente_revisao':'conferida','existente_status':'nao_publicado'}]})
ins('divergencia','divergencia:%s:ano:1972'%p[0],'F026',p[2],{'projeto_codigo':p[0],'projeto_titulo':p[2],'campo':'ano','valor_cadastro':str(p[3]),'valor_cv':'1972',
  'candidatos':[{'valor':str(p[3]),'fontes':['cadastro do painel'],'folhas':1},{'valor':'1972','fontes':['CAMP Vision','nome da pasta'],'folhas':5}]})
ins('projeto_outro_fundo','outro_fundo:x:y','F026',p[2],{'projeto_codigo':p[0],'projeto_titulo':p[2],'ano':p[3],'cidade':'São Paulo',
  'outro':{'codigo':o[0],'titulo':p[2],'fundo_codigo':o[1],'fundo_titulo':'Fundo de teste','ano':p[3],'cidade':'São Paulo','score':1.0,'motivos':['mesmo nome (igual sem acento, maiúscula e palavras genéricas)']}})
print(con.execute("SELECT ano FROM projeto WHERE codigo='F026-P0001'").fetchone()[0])`);
}

(async () => {
  const anoAntes = semear();
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.route('**/*', rt => { const u = rt.request().url(); if (u.startsWith(BASE)) return rt.continue(); BLOQUEADAS.push(u); return rt.abort() });
  const page = await ctx.newPage(); const erros = [];
  page.on('pageerror', e => erros.push(String(e)));
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push('console: ' + m.text()) });
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login do usuário semeado');
  try {
    await page.goto(BASE + '/#decisoes'); await page.waitForSelector('#dec-body tr[data-dec-tipo]', { timeout: 15000 }); await page.waitForTimeout(600);
    const tipos = await page.$$eval('#dec-body tr[data-dec-tipo]', trs => trs.map(t => [t.dataset.decTipo, t.textContent]));
    chk(['projeto_parecido', 'lote_colide', 'divergencia', 'projeto_outro_fundo'].every(t => tipos.some(x => x[0] === t)), 'a lista mostra os 4 tipos: ' + tipos.map(x => x[0]).join(', '));
    const txt = t => (tipos.find(x => x[0] === t) || [])[1] || '';
    chk(/números repetidos/.test(txt('lote_colide')) && /2 folhas repetidas/.test(txt('lote_colide')), 'lote_colide com texto próprio na lista: ' + txt('lote_colide').slice(0, 120));
    chk(/Dado diferente do cadastro/.test(txt('divergencia')) && /1972/.test(txt('divergencia')), 'divergência com texto próprio e os candidatos na lista');
    chk(/Mesmo nome em outro fundo/.test(txt('projeto_outro_fundo')) && /F023/.test(txt('projeto_outro_fundo')), 'mesmo nome em outro fundo com texto próprio na lista');
    chk(/Casa Taruma/.test(txt('projeto_parecido')) && /parado esperando/.test(txt('projeto_parecido')), 'projeto parecido continua como antes na lista');
    const abrir = async t => { await page.click(`#dec-body tr[data-dec-tipo="${t}"] [data-dec-abrir]`); await page.waitForSelector('#drawer [data-dec-escolha], #drawer [data-dec-acao]', { timeout: 8000 }); await page.waitForTimeout(300); return page.$eval('#drawer', d => d.textContent) };
    const fechar = async () => { await page.keyboard.press('Escape'); await page.waitForTimeout(300) };
    const confirmarJanela = async () => { await page.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 }); await page.click('#conf-ov [data-conf="sim"]'); await page.waitForTimeout(900) };
    // projeto parecido
    let t = await abrir('projeto_parecido');
    chk(/é o mesmo\?/i.test(t) && /É o mesmo: as folhas entram em F026-P0001/.test(t) && /É outro projeto/.test(t), 'projeto parecido: as duas opções de sempre');
    await fechar();
    // lote_colide
    t = await abrir('lote_colide');
    const bl = await page.$$eval('#drawer [data-dec-escolha]', bs => bs.map(b => b.dataset.decEscolha));
    chk(/Lote com números repetidos/.test(t) && JSON.stringify(bl) === JSON.stringify(['adicionar_ao_fim', 'ignorar', 'substituir']), 'lote: texto próprio e as 3 opções (adicionar ao fim, ignorar, substituir): ' + bl.join(','));
    chk(/já conferida/.test(t) && /ainda não conferida/.test(t), 'lote: diz a situação de cada folha que já existe');
    await page.click('#drawer [data-dec-escolha="ignorar"]'); await confirmarJanela();
    chk(py(`print(con.execute("SELECT escolha FROM decisao WHERE tipo='lote_colide'").fetchone()[0])`) === 'ignorar', 'lote: "Ignorar as repetidas" resolve a decisão');
    // divergência
    t = await abrir('divergencia');
    const bd = await page.$$eval('#drawer [data-dec-escolha="escolher"]', bs => bs.map(b => b.dataset.decValor));
    chk(/Ano diferente do cadastro/.test(t) && bd.includes('1972') && bd.includes(anoAntes) && /nome da pasta/.test(t), 'divergência: os candidatos com de onde veio cada um e um botão para escolher: ' + bd.join(','));
    await page.click('#drawer [data-dec-escolha="escolher"][data-dec-valor="1972"]'); await confirmarJanela();
    chk(py(`print(con.execute("SELECT ano FROM projeto WHERE codigo='F026-P0001'").fetchone()[0])`) === '1972', 'divergência: escolher 1972 grava no cadastro');
    // mesmo nome em outro fundo
    t = await abrir('projeto_outro_fundo');
    chk(/Já existe “Casa Tarumã” no fundo F023/.test(t) && /Ver o projeto F023-P0011/.test(t), 'outro fundo: nota forte "já existe ... no fundo F023 — é o mesmo?" com link');
    await page.click('#drawer [data-dec-escolha="diferente"]'); await confirmarJanela();
    chk(py(`print(con.execute("SELECT escolha FROM decisao WHERE tipo='projeto_outro_fundo'").fetchone()[0])`) === 'diferente', 'outro fundo: "São projetos diferentes" resolve');
    // decididas
    await page.goto(BASE + '/#decisoes'); await page.waitForSelector('[data-dec-sit="resolvida"]'); await page.click('[data-dec-sit="resolvida"]'); await page.waitForTimeout(800);
    const dec = await page.$$eval('#dec-body tr[data-dec-tipo]', trs => trs.map(t => t.textContent).join(' | '));
    chk(/ficou “1972”/.test(dec) && /as repetidas ficaram de fora/.test(dec) && /são projetos diferentes/.test(dec), 'aba Decididas mostra a escolha de cada tipo');
    // fundo parecido: aviso antes de reservar
    await page.goto(BASE + '/#fundos'); await page.waitForTimeout(800);
    await page.evaluate(() => abrirReservaFundo()); await page.fill('#nf-nome', 'Sami Bussab Arquitetos'); await page.fill('#nf-sigla', 'SBX');
    await page.click('#m-fundo .pf .btn.pri'); await page.waitForTimeout(900);
    const av = await page.$eval('#m-fundo', m => m.textContent);
    chk(/Já existe fundo com nome parecido/.test(av) && /F026/.test(av) && /%/.test(av), 'fundo: aviso com o parecido e a semelhança antes de criar');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    // projeto novo com o mesmo nome de um de OUTRO fundo: nota forte com link
    await page.goto(BASE + '/#projetos'); await page.waitForTimeout(800);
    await page.evaluate(() => abrirNovoProjeto('F023')); await page.fill('#np-titulo', 'Casa Tarumã'); await page.click('#np-criar'); await page.waitForTimeout(900);
    const np = await page.$eval('#m-proj', m => m.textContent);
    chk(/Já existe “Casa Tarumã” no fundo F026/.test(np) && /Abrir F026-P0001/.test(np), 'projeto novo: nota forte "já existe ... no fundo F026: é o mesmo?" com link');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    // pedido repetido em 30 dias
    for (const cod of ['F026-P0001', 'F026-P0001-1968-S01-D00001']) await ctx.request.post(BASE + '/api/solicitacoes', { data: { solicitante: 'Maria Teste', email: 'maria@teste.org', finalidade: 'pesquisa', itens: [{ codigo: cod, formato: 'jpg_3000' }] } });
    await page.goto(BASE + '/#solicitacoes'); await page.waitForSelector('#v-solicitacoes [data-pedido-anterior]', { timeout: 10000 });
    await page.click('#v-solicitacoes [data-pedido-anterior]'); await page.waitForTimeout(900);
    const dr = await page.$eval('#drawer', d => d.textContent);
    chk(/Maria Teste/.test(dr), 'Solicitações: "pedido repetido" com link que abre o pedido anterior');
  } catch (x) { chk(false, 'roteiro: ' + x.message.split('\n')[0]) }
  chk(!erros.length, 'sem erro no console: ' + erros.slice(0, 3).join(' | '));
  linhas.push('pedidos para fora barrados pelo teste: ' + BLOQUEADAS.length);
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== DECISÕES: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})();
