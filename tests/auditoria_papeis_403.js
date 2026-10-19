// #106 Varredura de papéis: com operador@ e leitor@ (usuários do seed), abre cada tela que o papel pode abrir e FALHA se alguma chamada
// de API voltar 403 (meta: "nenhum 403 no console"). O painel não deve pedir ao servidor o que a pessoa não pode ver:
// ou o botão/chamada some (PODE / pode() no index.html), ou o servidor libera a leitura que é inofensiva para aquele papel.
// Navegador de verdade (Playwright/Chromium). Uso: suba a API com um banco de tests/semear_banco_teste.py e rode:
//   BASE=http://127.0.0.1:8803 NODE_PATH=$(npm root -g) node tests/auditoria_papeis_403.js
// BASE padrão: http://127.0.0.1:8765. Use uma porta só sua (ex.: 8800-8809) para não brigar com outra auditoria.
// O teste cria UM problema e UM pedido (como master) se o banco não tiver nenhum, para abrir as gavetas de detalhe.
const {chromium}=require('playwright');
const BASE=(process.env.BASE||'http://127.0.0.1:8765').replace(/\/$/,'');
const MASTER=['rafael@camp.arq.br','senha-bem-longa-123'];
const USUARIOS=[['operador','operador@camp.arq.br','senha-operador-123'],['leitura','leitor@camp.arq.br','senha-leitor-1234']];
const ESPERA=Number(process.env.ESPERA||1800);
// Botões que levariam a um 403 (ou à tela "Sem acesso") ao clicar: não podem aparecer para o papel.
const SO_ADMIN=[['[onclick^="abrirNovoProjeto("]','"Novo projeto"'],['[onclick^="abrirCadastroArquiteto("]','"Cadastrar arquiteto"'],
  ['#proj-bulk [onclick^="acaoLoteProjetos"]','"Publicar/Voltar para rascunho" dos projetos selecionados'],['#proj-bulk [onclick^="autorizarEmLote"]','"Autorizar" dos projetos selecionados'],
  ['[onclick*="\'editar_projeto\'"]','"Preencher" (editar o projeto)'],['.ini-rodape[data-ini-rota="estacoes"]','"Ver estações e site"']];
const SO_OPERADOR=[['#drawer [data-err-res]','os botões de resolver o problema'],['#drawer [data-sol-etapa]','as etapas clicáveis do pedido'],['#drawer [onclick^="salvarSolicitacao"]','"Salvar" do pedido']];
const PROIBIDOS={operador:SO_ADMIN,leitura:[...SO_ADMIN,...SO_OPERADOR]};
const problems=[]; const okl=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
const browser=await chromium.launch();
try{
  // ---------- dados mínimos para as gavetas (Problemas e Pedidos) ----------
  { const ctx=await browser.newContext();const rq=ctx.request;
    const lg=await rq.post(BASE+'/api/auth/login',{data:{email:MASTER[0],senha:MASTER[1]}});
    if(!lg.ok())problems.push('master: login falhou (HTTP '+lg.status()+'); as gavetas podem ficar sem dados');
    else{
      const pj=((await (await rq.get(BASE+'/api/projetos?ordem=folhas&por_pagina=1')).json()).itens||[])[0];
      if(pj&&!((await (await rq.get(BASE+'/api/erros?situacao=todos')).json()).length))
        await rq.post(BASE+'/api/erros',{data:{codigo:pj.codigo,gravidade:'aviso',categoria:'outro',descricao:'teste da varredura de papéis'}});
      if(!(((await (await rq.get(BASE+'/api/solicitacoes')).json()).itens||[]).length))
        await rq.post(BASE+'/api/solicitacoes',{data:{solicitante:'Visitante de teste',finalidade:'pesquisa',origem:'email',itens:pj?[{codigo:pj.codigo,formato:'jpg_1200'}]:[]}});
    }
    await ctx.close() }

  for(const [papel,email,senha] of USUARIOS){
    const ctx=await browser.newContext({viewport:{width:1366,height:900}});
    const page=await ctx.newPage();
    let tela='login';
    const vistos=[];
    page.on('response',r=>{const u=r.url();if(r.status()===403&&u.includes('/api/'))vistos.push({tela,txt:`${papel} · tela ${tela}: ${r.request().method()} ${u.replace(BASE,'')}`})});
    page.on('pageerror',e=>problems.push(`${papel} · tela ${tela}: erro de script ${String(e.message||e).slice(0,160)}`));
    const lg=await ctx.request.post(BASE+'/api/auth/login',{data:{email,senha}});
    if(!lg.ok()){problems.push(`${papel}: login falhou (HTTP ${lg.status()})`);await ctx.close();continue}
    tela='painel';await page.goto(BASE+'/#painel');await sleep(ESPERA);
    const eu=await page.evaluate(()=>typeof EU!=='undefined'&&EU?EU.papel:null);
    if(eu!==papel){problems.push(`${papel}: o painel entrou como "${eu}"`);await ctx.close();continue}
    // as telas que a pessoa pode abrir: os botões do menu que aparecem para ela e cuja rota o pode() libera
    const telas=await page.evaluate(()=>[...document.querySelectorAll('#nav > button[data-v]')].filter(b=>!b.hidden).map(b=>b.dataset.v).filter(v=>pode('rota.'+v)));
    // e as páginas de detalhe: um fundo, o projeto com mais folhas e uma folha dele
    const det=await page.evaluate(async()=>{const out=[];
      try{const p=await API('/api/projetos?ordem=folhas&por_pagina=5');const pj=(p.itens||[])[0];if(pj){out.push('fundo/'+pj.codigo.slice(0,4),'projeto/'+pj.codigo);
        const d=await API('/api/projetos/'+encodeURIComponent(pj.codigo)+'/detalhe');const it=(d.itens||[]).find(x=>x.codigo&&x.origem_catalogacao!=='site');if(it)out.push('item/'+it.codigo)}}catch(e){}
      return out});
    if(det.length<3)problems.push(`${papel}: não achei fundo, projeto e folha no banco de teste para abrir (${det.join(', ')})`);
    const botoes=async()=>{for(const [sel,nome] of PROIBIDOS[papel]){
      if(await page.evaluate(s=>[...document.querySelectorAll(s)].some(el=>!el.hidden&&!el.disabled&&el.offsetParent!==null),sel))
        problems.push(`${papel} · tela ${tela}: aparece ${nome}, mas este papel não pode usar (o servidor responde 403 ou a tela é só de admin)`)}};
    for(const rota of [...telas,...det]){
      tela=rota;
      await page.evaluate(r=>nav(r),rota);await sleep(ESPERA+(rota==='estacoes'?1500:0));
      await botoes();
      if(rota==='projetos'){   // com um projeto selecionado aparece a barra de ações em lote
        const cx=await page.$('#projetos-body input[type="checkbox"]');
        if(cx){tela='projetos (selecionado)';await cx.click().catch(()=>{});await sleep(400);await botoes();await page.evaluate(()=>window.limparSelecaoProjetos&&limparSelecaoProjetos()).catch(()=>{})}
      }
      if(rota.startsWith('projeto/')){   // as abas da página do projeto pedem coisas diferentes
        for(const aba of await page.$$eval('[data-pj-aba]',bs=>bs.filter(b=>b.offsetParent!==null).map(b=>b.dataset.pjAba))){
          tela=rota+' (aba '+aba+')';await page.click(`[data-pj-aba="${aba}"]`).catch(()=>{});await sleep(900);await botoes()}
      }
      // a primeira linha que abre detalhe (gaveta) na tela atual
      const lin=await page.$('.content.on [data-abrir]');
      if(lin){tela=rota+' (detalhe)';await lin.click().catch(()=>{});await sleep(1100);await botoes();await page.evaluate(()=>window.closeDrawer&&closeDrawer(true)).catch(()=>{});await sleep(200)}
    }
    // o modo de conferir (#conferir/<projeto>, 6db0b12) de um projeto com lote: a lista e a folha aberta à direita (leitura vê só para ler)
    let conf=null;
    for(const pj of (((await (await ctx.request.get(BASE+'/api/projetos?por_pagina=100')).json()).itens)||[])){
      const rv=await ctx.request.get(BASE+'/api/projetos/'+encodeURIComponent(pj.codigo)+'/revisao');
      if(rv.ok()&&(((await rv.json()).lotes)||[]).length){conf=pj.codigo;break}}
    if(!conf)problems.push(`${papel}: não achei projeto com lote no banco de teste para abrir o modo de conferir`);
    else{
      tela='conferir/'+conf;await page.evaluate(r=>nav(r),tela);await sleep(ESPERA);
      const linhasCf=await page.$$('.cf-linha');
      if(!linhasCf.length)problems.push(`${papel} · tela ${tela}: a lista de folhas não apareceu`);
      for(const l of linhasCf.slice(0,2)){await l.click().catch(()=>{});await sleep(900)}
      const corpo=await page.$eval('#cf-pane',el=>el.textContent).catch(()=>'');
      if(!/Dados da folha/.test(corpo))problems.push(`${papel} · tela ${tela}: a folha aberta não mostrou os dados ("Dados da folha")`);
      if(papel==='leitura'&&await page.evaluate(()=>[...document.querySelectorAll('#cf-pane .rev-campos input:not([type=hidden]), #cf-pane .rev-campos select, #cf-pane .rev-campos textarea')].some(i=>!i.disabled)))problems.push(`leitura · tela ${tela}: os campos da folha deveriam vir desligados (só leitura)`);
      det.push(tela);
    }
    // a busca do topo e o "Meu perfil"
    tela='busca do topo';await page.fill('#q','Casa').catch(()=>{});await sleep(1200);await page.keyboard.press('Escape').catch(()=>{});
    tela='meu perfil';await page.evaluate(()=>window.abrirPerfil&&abrirPerfil()).catch(()=>{});await sleep(1000);await page.evaluate(()=>window.closeModal&&closeModal()).catch(()=>{});
    // o painel faz chamadas de tempo em tempo (contagens, sinal das máquinas): espera um pouco parado na tela inicial
    tela='painel (parado)';await page.evaluate(()=>nav('painel'));await sleep(ESPERA*2);
    // controle: o detector precisa enxergar um 403 de verdade (senão o teste passaria sem olhar nada)
    tela='controle';await page.evaluate(()=>fetch('/api/config').catch(()=>{}));await sleep(400);
    if(!vistos.some(v=>v.tela==='controle'))problems.push(`${papel}: o detector de 403 não viu a chamada de controle (/api/config); o teste não é confiável`);
    okl.push(`${papel}: ${telas.length} telas do menu (${telas.join(', ')}) + ${det.length} detalhes (${det.join(', ')}) + busca e perfil`);
    problems.push(...[...new Set(vistos.filter(v=>v.tela!=='controle').map(v=>v.txt))].map(v=>'403 no console: '+v));
    await ctx.close();
  }
}finally{await browser.close()}
console.log(okl.map(l=>'  ok  '+l).join('\n'));
if(problems.length){console.log(`\n${problems.length} PROBLEMA(S):\n`+problems.map(p=>' - '+p).join('\n'));process.exit(1)}
console.log('\nNENHUM 403 para operador e leitura');
})().catch(e=>{console.error(e);process.exit(2)});
