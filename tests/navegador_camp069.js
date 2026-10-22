// CAMP-069 (20/10, operadora no F009-P0092): "Reconhecimento automático de folhas de outros projetos, não é possível abrir para checar, ou refazer a ação".
// No navegador de verdade (Playwright + Chromium). Prova: a folha que o CAMP Vision retirou "por ser de outra obra" aparece com a IMAGEM na lista
// "Problemas que impedem publicar" da página do projeto e na tela Problemas; um clique abre a imagem grande em outra aba (sem abrir a gaveta da linha);
// "É deste projeto" devolve a folha ao lote, importa e ela entra no painel liberada; "Desfazer" (na aba "Não era problema") volta o aviso;
// folha sem imagem diz isso; "É de outro projeto…" numa folha fora do painel fecha os problemas; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO, portas 8930-8939):
//   CAMP_DB_PATH=/tmp/c069.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/c069.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8931)
//   CAMP_DB_PATH=/tmp/c069.db CAMP_BASE=http://127.0.0.1:8931 node tests/navegador_camp069.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8931', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0192', D = n => `${P}-1970-S01-D0000${n}`;
// a pasta do lote: pacote com a D1 em documentos, D5 e D6 retiradas "de outra obra"; só a D5 tem JPG
const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'c069-lote-'));
fs.mkdirSync(path.join(pasta, 'catalogacao')); fs.mkdirSync(path.join(pasta, '01 - Desenhos e pranchas', 'JPG'), { recursive: true });
execFileSync('python3', ['-c', 'import sys\nfrom PIL import Image\nImage.new("RGB",(600,420),(200,170,120)).save(sys.argv[1],"JPEG")', path.join(pasta, '01 - Desenhos e pranchas', 'JPG', D(5) + '.jpg')]);
const ret = (n) => ({ codigo: D(n), titulo: 'Prancha ' + n, publicavel: false, projeto_divergente: true, arquivos: [], bloqueios: ["projeto divergente: o carimbo diz 'Residência Fulano'"] });
fs.writeFileSync(path.join(pasta, 'catalogacao', 'pacote_tainacan.json'), JSON.stringify({ versao: 2, projeto_codigo: P,
  documentos: [{ codigo: D(1), titulo: 'Prancha 1', publicavel: true, bloqueios: [], arquivos: [] }], retirados: [ret(5), ret(6)] }));
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',192)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',192,'Residência Luiz Sales',1970,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'"); con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote Luiz Sales','${P}',?,'revisao')", (sys.argv[2],)).lastrowid
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,pendencias,titulo) VALUES (?,?,?,?,?,?,?,?,?)", ("${D(1)}","${P}","S01",1,'campvision',lote,'nao_publicado','{}','Prancha 1'))
for n in (5, 6):
    c = "${P}-1970-S01-D0000%d" % n
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por,chave) VALUES ('bloqueia','projeto_errado','campvision',?,?, 'CAMP Vision', ?)", (c, "D0000%d com identificação para outra pasta (RESIDÊNCIA FULANO) — fora da publicação até resolver" % n, "teste069:%d" % n))
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por,chave) VALUES ('corrigir','projeto_errado','campvision',?,'O CAMP Vision retirou esta folha do lote: projeto divergente. Ela não entrou na revisão.','CAMP Vision',?)", (c, "campvision:retirado:" + c))
`, pasta);
const q = (sql) => py(`print(json.dumps(con.execute(${JSON.stringify(sql)}).fetchall()))`);
const espera = async (f, ms = 10000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 200)); } return false; };
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const ctx = await br.newContext({ viewport: { width: 1400, height: 900 } }); const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  // 1) página do projeto: a lista "Problemas que impedem publicar" (aberta pelo cartão; P0: nada abre sozinho) mostra a folha com a imagem, uma vez por folha
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  await pg.waitForSelector('#pj-cards [data-pjc-gav="problemas"]', { timeout: 15000 }).catch(() => {}); await pg.click('#pj-cards [data-pjc-gav="problemas"]').catch(() => {});
  const naLista = await pg.waitForSelector(`#pj-probs [data-fp-box="${D(5)}"] img.fp-mini`, { timeout: 15000 }).then(() => true, () => false);
  chk(naLista, 'página do projeto: a folha "de outro projeto" aparece com a imagem em "Problemas que impedem publicar"');
  chk(await espera(() => pg.$eval(`#pj-probs [data-fp-box="${D(5)}"] img.fp-mini`, i => i.complete && i.naturalWidth > 0).catch(() => false)), 'a imagem da folha retirada carrega (vem da pasta do lote)');
  chk(await pg.$$eval(`#pj-probs [data-fp-box="${D(5)}"]`, l => l.length).catch(() => 0) === 1, 'uma linha por folha (os 2 problemas da mesma folha não repetem a imagem)');
  chk(await pg.$eval(`#pj-probs [data-fp-folha="${D(5)}"]`, a => a.target === '_blank' && /\/api\/itens\/.+\/previa$/.test(a.getAttribute('href'))).catch(() => false), 'um clique abre a imagem grande em outra aba');
  chk(await espera(() => pg.$eval(`#pj-probs [data-fp-box="${D(6)}"]`, b => /Não há imagem desta folha/.test(b.textContent)).catch(() => false)), 'folha sem imagem em lugar nenhum: diz isso no lugar da imagem');
  // 2) tela Problemas do projeto: a mesma folha com imagem e as decisões; clicar na imagem abre a aba e NÃO abre a gaveta da linha
  await pg.goto(BASE + '/#erros/' + P);
  if (!(await pg.waitForSelector(`#err-body [data-fp-box="${D(5)}"]`, { timeout: 15000 }).then(() => true, () => false))) { chk(false, 'Problemas: a folha "de outro projeto" aparece com a imagem e as decisões'); console.log(linhas.join('\n')); console.log(`\n${problemas.length} FALHA(S)`); await br.close(); process.exit(1); }
  const [popup] = await Promise.all([ctx.waitForEvent('page', { timeout: 8000 }).catch(() => null), pg.click(`#err-body [data-fp-folha="${D(5)}"]`)]);
  chk(!!popup && /\/previa$/.test(popup.url()), 'Problemas: "Ver a folha" abre a imagem grande em outra aba (um clique)', popup ? popup.url() : 'nenhuma aba');
  chk(!(await pg.$('#err-body img.fp-mini')), 'a linha da lista não carrega miniaturas (a lista continua leve; a imagem fica na gaveta)');
  if (popup) await popup.close();
  chk(!(await pg.isVisible('#drawer.on, #d-body:not(:empty)').catch(() => false)) || !/Folha retirada|Folha de outro/.test(await pg.textContent('#d-title').catch(() => '')), '"Ver a folha" não abre a gaveta da linha');
  // 3) "É deste projeto" na folha fora do painel: devolve, importa o lote e a folha entra liberada
  await pg.click(`#err-body [data-fp-box="${D(5)}"] [data-deste-projeto]`); await pg.click('#conf-ov [data-conf="sim"]');
  const entrou = await espera(() => JSON.parse(q(`SELECT status_site FROM item WHERE codigo='${D(5)}'`)).length === 1, 15000);
  chk(entrou && JSON.parse(q(`SELECT status_site FROM item WHERE codigo='${D(5)}'`))[0][0] === 'nao_publicado', '"É deste projeto": a folha entra no painel (o lote é lido de novo) e não fica bloqueada', q(`SELECT status_site, pendencias FROM item WHERE codigo='${D(5)}'`));
  chk(JSON.parse(q(`SELECT COUNT(*) FROM erro WHERE codigo='${D(5)}' AND situacao IN ('aberto','em_correcao')`))[0][0] === 0, 'os 2 problemas da folha fecham (publicar não fica bloqueado por eles)');
  const t1 = await pg.evaluate(() => document.getElementById('toast').textContent);
  chk(/voltou ao projeto/.test(t1) && /Desfazer/.test(t1), 'aviso diz que a folha voltou, com "Desfazer"', t1);
  chk(await espera(async () => !(await pg.$(`#err-body [data-fp-box="${D(5)}"]`))), 'a folha sai da lista de abertos');
  // 4) depois: aba "Não era problema" tem "Desfazer É deste projeto"
  await pg.click('#err-abas [data-err-sit="ignorado"]');
  const temDesf = await pg.waitForSelector(`#err-body [data-deste-desfazer="${D(5)}"]`, { timeout: 10000 }).then(() => true, () => false);
  chk(temDesf, 'aba "Não era problema": a decisão aparece com "Desfazer \\"É deste projeto\\""');
  if (temDesf) await pg.click(`#err-body [data-deste-desfazer="${D(5)}"]`);
  chk(await espera(() => JSON.parse(q(`SELECT status_site FROM item WHERE codigo='${D(5)}'`))[0][0] === 'bloqueado'), 'Desfazer: a folha volta a ficar bloqueada com o aviso de outro projeto');
  // o de "folha retirada" fecha sozinho de novo (a folha já está no painel); o que importa é o que bloqueia publicar reabrir
  chk(JSON.parse(q(`SELECT COUNT(*) FROM erro WHERE codigo='${D(5)}' AND situacao='aberto' AND gravidade='bloqueia'`))[0][0] === 1, 'Desfazer: o problema "de outro projeto" que bloqueia publicar reabre');
  // 5) "É de outro projeto…" na folha que nem entrou no painel: fecha os problemas dela (fica fora)
  await pg.click('#err-abas [data-err-sit="abertos"]'); await pg.waitForSelector(`#err-body [data-fp-outro="${D(6)}"]`, { timeout: 10000 });
  await pg.click(`#err-body [data-fp-outro="${D(6)}"]`); await pg.click('#conf-ov [data-conf="sim"]');
  chk(await espera(() => JSON.parse(q(`SELECT COUNT(*) FROM erro WHERE codigo='${D(6)}' AND situacao='corrigido'`))[0][0] === 2), '"É de outro projeto…" (folha fora do painel): os problemas fecham como corrigidos, a folha fica fora');
  // 6) a gaveta do problema também tem a imagem e as decisões
  await pg.goto(BASE + '/#erros/' + P); await pg.waitForSelector(`#err-body tr[data-err-linha]`, { timeout: 10000 });
  await pg.click(`#err-body tr[data-err-linha] .err-oque`);
  chk(await pg.waitForSelector(`#d-body [data-fp-box="${D(5)}"] [data-deste-projeto]`, { timeout: 8000 }).then(() => true, () => false), 'a gaveta do problema mostra a imagem e "É deste projeto"');
  chk(await espera(() => pg.$eval(`#d-body [data-fp-box="${D(5)}"] img.fp-mini`, i => i.complete && i.naturalWidth > 0).catch(() => false)), 'na gaveta a imagem carrega (a folha já no painel, sem prévia do CAMP Vision: vem da pasta do lote)');
  await pg.screenshot({ path: path.join(os.tmpdir(), 'camp069_gaveta.png') });
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
