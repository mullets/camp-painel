// 20/10 (print da F026-P0009: "se eu resolvo um problema ele tem que sair da lista, pelo amor de deus isso é básico!").
// O CAMP Vision manda "série incerta na triagem … conferir na folha de contatos" em cada folha. Na aba Problemas do projeto a pessoa abre
// a folha, confere ("Está certo e próxima") e a linha daquela folha tem de SAIR da lista na hora (e continuar fora ao recarregar);
// o número da aba e do cartão descem junto. Vale para as categorias que o CAMP Vision pode usar para isso ("série", "metadado", sem categoria).
const T = require('./_comum');
const { execFileSync } = require('child_process'), path = require('path');
T.rodar(async () => {
  for (const cat of ['série', 'metadado', '']) {
    T.passo(`aviso "série incerta" com categoria "${cat || '(vazia)'}"`);
    const { P, D } = T.loteReal('CASA SERIE ' + (cat || 'VAZIA').toUpperCase(), 'F026', { semAviso: true });
    execFileSync('python3', [path.join(__dirname, 'h_montar.py'), T.BASE, T.RAIZ, P, cat], { encoding: 'utf-8' });
    const abertos = () => T.um("SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND situacao IN ('aberto','em_correcao') AND descricao LIKE '%série incerta%'", P + '%');
    T.chk(abertos() === 6, `[${cat}] cenário: 6 avisos "série incerta" abertos`, abertos());
    const op = await T.entrar('operador'); await T.abrirProjeto(op, P);
    await op.evaluate(c => showProjeto(c, 'erros'), P); await op.waitForTimeout(1500);
    const linhas = () => op.$$eval('#pd tr', l => l.filter(x => /série incerta/.test(x.textContent)).map(x => (x.textContent.match(/D\d{5}/) || [''])[0]));
    const antes = await linhas(); T.chk(antes.length === 6, `[${cat}] aba Problemas lista as 6 folhas`, JSON.stringify(antes));
    const aba = () => T.txt(op, '#pd [role="tab"][aria-selected="true"], #pd .tabs .on');
    const abaAntes = await aba();
    // abre a D00001 pela linha e confere
    await op.locator('#pd tr', { hasText: 'D00001' }).filter({ hasText: 'série incerta' }).first().click();
    await op.waitForSelector('#d-body', { timeout: 10000 }); await op.waitForTimeout(800);
    const titulo = await T.txt(op, '#d-title'); T.chk(!/^outro$/i.test(titulo), `[${cat}] a gaveta do problema não se chama "outro"`, titulo);
    const oQue = await T.txt(op, '#d-body'); T.chk(!/Problema relatado/.test(oQue), `[${cat}] não diz "Problema relatado" (quem apontou foi o CAMP Vision)`, oQue.slice(0, 200));
    if (!(await op.$('#d-body [data-rev-item="conferida"]'))) await op.click('#d-body [data-err-acao]');   // o botão azul "Abrir a folha" da gaveta do problema
    const abriu = await op.waitForSelector('#d-body [data-rev-item="conferida"]', { timeout: 10000 }).then(() => true, () => false);
    T.chk(abriu, `[${cat}] clicar na linha abre a folha para revisar`);
    if (abriu) { await op.click('#d-body [data-rev-item="conferida"]'); await T.confirmar(op); await op.waitForTimeout(1500) }
    T.chk(abertos() === 5, `[${cat}] conferir a D00001 fecha o aviso dela no banco`, abertos());
    await T.print(op, `serie_${cat || 'vazia'}_depois`);
    const depois = await linhas();
    T.chk(!depois.includes('D00001') && depois.length === 5, `[${cat}] a linha da D00001 sai da lista NA HORA (sem recarregar)`, JSON.stringify(depois));
    const abaDepois = await aba(), nAba = t => Number((t.match(/Problemas \((\d+)\)/) || [])[1]);
    T.chk(nAba(abaDepois) === nAba(abaAntes) - 1, `[${cat}] o número da aba Problemas desce 1`, `${abaAntes} → ${abaDepois}`);
    await op.evaluate(() => closeDrawer && closeDrawer(true)).catch(() => {});
    await T.abrirProjeto(op, P); await op.evaluate(c => showProjeto(c, 'erros'), P); await op.waitForTimeout(1500);
    const recarregado = await linhas(); T.chk(!recarregado.includes('D00001') && recarregado.length === 5, `[${cat}] ao recarregar, a D00001 continua fora`, JSON.stringify(recarregado));
    await op.context().close();
  }
});
