// CAMP-DOA-TEXTO (20/11/2026): "Copiar dados para o contrato" no detalhe da doação de acervo, no navegador de verdade (Playwright + Chromium).
// Rafael: "preciso poder em formato texto, copiar todos dados do formulario que ela preencheu e suas respostas, pergunta e resposta, com os
// dados dela, valor que vai doar e etc que eh pra enviar para fazer o contrato."
//  [A] o botão está no detalhe; a caixa do texto só aparece depois do clique
//  [B] o clique copia (área de transferência) o mesmo texto da caixa: pergunta → resposta, valor em R$, sem as notas internas
//  [C] "Incluir notas internas" marcada: o texto ganha as notas (e copiar de novo leva as notas)
//  [D] navegador que não deixa copiar: o texto fica na caixa, selecionado, e a tela diz para copiar com Ctrl+C
//  [E] dados da pessoa só como texto (nada de HTML com eles) e nunca dentro de onclick
// Uso (servidor PRÓPRIO na porta 8840; nada vai ao site):
//   CAMP_DB_PATH=/dev/shm/doatx/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/doatx/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8840)
//   CAMP_DB_PATH=/dev/shm/doatx/m.db CAMP_BASE=http://127.0.0.1:8840 node tests/navegador_doacao_texto.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8840', DB = process.env.CAMP_DB_PATH;
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

const REG = { id: 611, protocolo: 'CAMP-2026-000611', recebida_em: '2026-11-20T12:00:00+00:00', nome: "Maria D'Ávila <b>", email: 'maria@exemplo.com', telefone: '11 98888-7777',
  relacao: 'familia', relacao_nome: 'Sou familiar ou herdeiro(a)', autor: 'Escritório Fulano', descricao: '40 rolos e 6 caixas', tipos: ['desenhos'], tipos_nomes: ['Plantas, desenhos e croquis'],
  quantidade_estimativa_faixa: '51_500', faixa_nome: 'De 51 a 500 itens', conservacao: 'boa', conservacao_nome: 'Boa', local: 'Campinas/SP', n_fotos: 2, direitos: 'titular',
  direitos_nome: 'Sou titular dos direitos patrimoniais', marketing: false, termos_versao: '2026-11', etapa: 'aprovada', etapa_nome: 'Aprovada', valor: 2500, caixas: 6,
  contrato_link: '', notas: [{ em: '2026-11-20 13:00', quem: 'Rafael', texto: 'nota só da equipe' }], cobranca: null, pode_cobrar: false, historico: [], avisos: [],
  alterado_em: '2026-11-20T12:00:00+00:00' };

async function abrir(ctx) {
  const P = await ctx.newPage();
  P.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await P.goto(BASE + '/');
  await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
  await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await P.goto(BASE + '/#doacoes');
  await P.waitForSelector('#doa-lista tr[data-doa-abrir="611"]', { timeout: 15000 });
  await P.click('#doa-lista tr[data-doa-abrir="611"]');
  await P.waitForSelector('[data-doa-acao="texto"]', { timeout: 10000 });
  return P;
}
const erros = [];
(async () => {
  py(`r=json.loads(sys.argv[2])\ncon.execute("INSERT OR REPLACE INTO doacao_acervo (site_id, protocolo, recebida_em, nome, email, telefone, etapa, valor, dados) VALUES (611,?,?,?,?,?,?,?,?)",(r['protocolo'],'2026-11-20 12:00:00',r['nome'],r['email'],r['telefone'],'aprovada',2500,json.dumps(r)))`, JSON.stringify(REG));
  const browser = await chromium.launch({ executablePath: CHROME });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
    const P = await abrir(ctx);
    // [A]
    chk((await P.locator('[data-doa-acao="texto"]').textContent()).trim() === 'Copiar dados para o contrato', '[A] botão "Copiar dados para o contrato" no detalhe');
    chk(await P.locator('#doa-texto-campo').isHidden() && !(await P.isChecked('#doa-texto-notas')), '[A] caixa do texto escondida antes do clique; "Incluir notas internas" desmarcada');
    // [B]
    await P.click('[data-doa-acao="texto"]');
    await P.waitForSelector('#doa-texto-campo:not([hidden])', { timeout: 10000 });
    const t1 = await P.inputValue('#doa-texto');
    const cp1 = await P.evaluate(() => navigator.clipboard.readText());
    chk(t1.length > 100 && cp1 === t1, '[B] copiado para a área de transferência o mesmo texto da caixa (' + cp1.length + ' caracteres)');
    chk(t1.startsWith('Intenção de doação de acervo — CAMP\nProtocolo: CAMP-2026-000611') && t1.includes('Qual é sua relação com o acervo?\n  Sou familiar ou herdeiro(a)')
      && t1.includes('Qual é a quantidade aproximada de material?\n  De 51 a 500 itens') && t1.includes('Contribuição acordada: R$ 2.500,00'), '[B] o texto tem cabeçalho, pergunta → resposta e o valor em R$');
    chk(!t1.includes('nota só da equipe') && !t1.includes('NOTAS INTERNAS'), '[B] sem as notas internas por padrão');
    chk(await P.locator('#doa-texto').evaluate(e => e.readOnly), '[B] a caixa do texto é só leitura');
    await P.waitForFunction(() => /Dados copiados/.test(document.body.innerText), null, { timeout: 5000 }).then(() => chk(true, '[B] a tela diz "Dados copiados"'), () => chk(false, '[B] a tela diz "Dados copiados"'));
    // [C]
    await P.check('#doa-texto-notas');
    await P.waitForFunction(() => /NOTAS INTERNAS/.test(document.getElementById('doa-texto').value), null, { timeout: 10000 }).then(() => chk(true, '[C] marcar "Incluir notas internas" atualiza o texto da caixa'), () => chk(false, '[C] marcar "Incluir notas internas" atualiza o texto da caixa'));
    await P.click('[data-doa-acao="texto"]');
    await P.waitForFunction(() => navigator.clipboard.readText().then(t => /nota só da equipe/.test(t)), null, { timeout: 10000 }).then(() => chk(true, '[C] copiar de novo leva as notas internas'), () => chk(false, '[C] copiar de novo leva as notas internas'));
    // [E]
    const oc = await P.evaluate(() => [...document.querySelectorAll('[onclick]')].map(e => e.getAttribute('onclick')).join(' '));
    chk(!oc.includes('maria@exemplo.com') && !oc.includes('Ávila'), '[E] nenhum dado da pessoa dentro de onclick');
    chk(t1.includes("Nome completo: Maria D'Ávila <b>") && await P.locator('.doa-texto b').count() === 2, '[E] o nome vai como texto simples (sem virar HTML)');
    await ctx.close();
    // [D] sem área de transferência
    const ctx2 = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx2.addInitScript(() => {
      try { Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('negado')) } }); } catch (_) {}
      document.execCommand = () => false;
    });
    const P2 = await abrir(ctx2);
    await P2.click('[data-doa-acao="texto"]');
    await P2.waitForSelector('#doa-texto-campo:not([hidden])', { timeout: 10000 });
    const t2 = await P2.inputValue('#doa-texto');
    const sel = await P2.evaluate(() => { const e = document.getElementById('doa-texto'); return document.activeElement === e && e.selectionStart === 0 && e.selectionEnd === e.value.length; });
    chk(t2.includes('Qual é sua relação com o acervo?') && sel, '[D] sem copiar: o texto fica na caixa, inteiro e selecionado');
    await P2.waitForFunction(() => /Não deu para copiar sozinho/.test(document.body.innerText), null, { timeout: 5000 }).then(() => chk(true, '[D] a tela diz para copiar com Ctrl+C'), () => chk(false, '[D] a tela diz para copiar com Ctrl+C'));
    await ctx2.close();
  } catch (e) { chk(false, 'erro no teste: ' + e.message); }
  finally { await browser.close(); }
  chk(!erros.length, 'sem erro de JavaScript na página' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
