// Decisão "Projeto parecido" (19/10): além de "é o mesmo" (candidatos) e "criar novo", dá para escolher OUTRO projeto do fundo numa busca.
// Caso real: pasta "P0092 - 03 - Preview (JPG)" lida como "RESIDÊNCIA WIZ SALES"; o CAMP Vision sugeriu "Salles Publicidade" e a única
// saída era criar um projeto novo. Prova: o projeto da pasta entra na lista; a busca acha outro projeto do fundo; escolher resolve com ele.
// Uso (servidor PRÓPRIO numa porta 8970-8979):
//   CAMP_DB_PATH=/tmp/dc.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/dc.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8971)
//   CAMP_DB_PATH=/tmp/dc.db CAMP_BASE=http://127.0.0.1:8971 node tests/navegador_decisao_outro.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8971', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
py(`
for n,t in [(192,'Residência Sr. Luiz Marcelo Sales'),(193,'Salles Publicidade — São Paulo'),(194,'Casa Morumbi')]:
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',?)",(n,))
    con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES (?,?,?,?,?,?)",('F026-P%04d'%n,'F026',n,t,1977,'São Paulo'))
`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1300, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const reservar = (titulo, ident, chave) => pg.evaluate(([titulo, ident, chave]) => fetch('/api/estacoes/projetos/reservar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fundo_codigo: 'F026', titulo, ano: 0, identificacao_original: ident, chave_reserva: chave, candidatos: [{ codigo: 'F026-P0193', motivos: ["nome 'Salles Publicidade' no carimbo"] }] }) }).then(r => r.json()), [titulo, ident, chave]);
  // 1) pasta "P0192 - 03 - …": o projeto da pasta aparece na lista de candidatos e a busca já vem preenchida
  const a = await reservar('RESIDÊNCIA WIZ SALES, RUA DR. ALBERTO FARIA', 'P0192 - 03 - Preview (JPG)', 'a'.repeat(32));
  chk(a.pendente && a.decisao_id, 'o pedido com candidatos do CAMP Vision vira decisão (202)', JSON.stringify(a));
  await pg.goto(BASE + '/#decisoes'); await pg.reload(); await pg.waitForSelector(`[data-dec-abrir="${a.decisao_id}"]`, { timeout: 15000 });
  await pg.click(`[data-dec-abrir="${a.decisao_id}"]`); await pg.waitForSelector('#d-body .dec-cand');
  const cands = await pg.$$eval('#d-body .dec-cand header .code', l => l.map(x => x.textContent));
  chk(cands[0] === 'F026-P0192' && cands.includes('F026-P0193'), 'o projeto que a pasta indica (P0192) vem primeiro, junto do sugerido pelo carimbo', cands.join(','));
  chk(await pg.$eval('#d-body [data-dec-outro] .dec-busca', i => i.value) === 'P0192', 'a busca de "outro projeto" já vem com o número da pasta');
  chk(await pg.$eval('#d-body', b => /É uma obra nova/.test(b.textContent) && /Criar F026-P\d{4}/.test(b.textContent)), '"criar" ficou como uma opção separada: "É uma obra nova"');
  // 2) busca por outro projeto do fundo, fora da lista, e escolhe
  await pg.fill('#d-body [data-dec-outro] .dec-busca', 'Morumbi');
  const ok = await pg.waitForSelector('#d-body .dec-res [data-dec-valor="F026-P0194"][data-dec-acao="mesmo"]', { timeout: 6000 }).then(() => true, () => false);
  chk(ok, 'buscar "Morumbi" mostra F026-P0194 com o botão "É este"');
  const fora = await pg.$$eval('#d-body .dec-res [data-dec-acao="mesmo"]', l => l.map(x => x.dataset.decValor));
  chk(!fora.includes('F026-P0193'), 'a busca não repete os candidatos que já estão acima', fora.join(','));
  await pg.fill('#d-body [data-dec-outro] .dec-busca', 'P0194');
  await pg.waitForFunction(() => document.querySelectorAll('#d-body .dec-res [data-dec-acao="mesmo"]').length === 1 && document.querySelector('#d-body .dec-res [data-dec-valor="F026-P0194"]'), null, { timeout: 6000 }).catch(() => {});
  chk(await pg.$('#d-body .dec-res [data-dec-valor="F026-P0194"]') !== null, 'buscar só pelo número (P0194) também acha');
  await pg.click('#d-body .dec-res [data-dec-acao="mesmo"][data-dec-valor="F026-P0194"]');
  await pg.waitForSelector('#conf-ov [data-conf="sim"]'); await pg.click('#conf-ov [data-conf="sim"]');
  await pg.waitForFunction(() => !document.querySelector('#d-body [data-dec-outro]'), null, { timeout: 6000 }).catch(() => {});
  const d = await pg.evaluate(id => fetch('/api/decisoes/' + id).then(r => r.json()), a.decisao_id);
  chk(d.situacao === 'resolvida' && d.projeto_codigo === 'F026-P0194', 'a decisão foi resolvida com o projeto escolhido na busca (nenhum projeto novo)', JSON.stringify([d.situacao, d.projeto_codigo]));
  const de = await reservar('RESIDÊNCIA WIZ SALES, RUA DR. ALBERTO FARIA', 'P0192 - 03 - Preview (JPG)', 'a'.repeat(32));
  chk(de.codigo === 'F026-P0194' && de.existente === true, 'o CAMP Vision recebe o código escolhido', JSON.stringify(de).slice(0, 120));
  chk(!erros.length, 'nenhum erro de JavaScript na página', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
