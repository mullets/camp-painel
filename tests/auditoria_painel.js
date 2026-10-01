// Auditoria do painel no navegador simulado (jsdom). Uso: suba a API em 127.0.0.1:8765 com um banco de teste e rode: NODE_PATH=$(npm root -g) node tests/auditoria_painel.js
const {JSDOM}=require('jsdom');
const BASE='http://127.0.0.1:8765';
const problems=[]; const okl=[];
const cookies={};
async function nodeFetch(url,opt={}){ if(url.startsWith('/')) url=BASE+url;
  const h={...(opt.headers||{})}; if(Object.keys(cookies).length) h['cookie']=Object.entries(cookies).map(([k,v])=>`${k}=${v}`).join('; ');
  const r=await fetch(url,{...opt,headers:h,redirect:'manual'});
  const sc=r.headers.get('set-cookie'); if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) cookies[m[1]]=m[2];}
  return r; }
(async()=>{
const html=await (await fetch(BASE+'/')).text();
const dom=new JSDOM(html,{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){
  w.fetch=nodeFetch; w.Element.prototype.scrollTo=()=>{}; w.confirm=()=>true; w.alert=m=>okl.push('alert:'+m); w.prompt=()=>null;
  w.console.error=(...a)=>problems.push('console.error: '+a.join(' '));
  w.addEventListener('error',e=>problems.push('window.error: '+(e.error&&e.error.stack||e.message)));
  w.addEventListener('unhandledrejection',e=>problems.push('unhandled: '+(e.reason&&e.reason.stack||e.reason)));
}});
const w=dom.window, d=w.document;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=sel=>{const el=d.querySelector(sel);return el?el.textContent.replace(/\s+/g,' ').trim():null};
function checkDom(label){ // procura sinais de template quebrado / dados falsos
  const vis=[...d.querySelectorAll('.content.on, .modal.on, .drawer, .top, .side, #gcrumb')].map(e=>e.textContent).join(' ');const body=vis;
  for(const bad of ['undefined','NaN','${','[object Object]','null ·',' null','Carregando']){ if(body.includes(bad)) problems.push(`${label}: texto "${bad}" na tela`);}
  d.querySelectorAll('[onclick]').forEach(el=>{const fn=(el.getAttribute('onclick').match(/^\s*([A-Za-z_$][\w$]*)\s*\(/)||[])[1]; if(fn&&typeof w.eval(fn)!=='function') problems.push(`${label}: onclick chama função inexistente ${fn}()`)});
}
await sleep(1500);
if(!d.getElementById('login').classList.contains('on')) problems.push('tela de login não apareceu sem sessão');
d.getElementById('lg-email').value='rafael@camp.arq.br'; d.getElementById('lg-senha').value='senha-bem-longa-123';
try{await w.fazerLogin({preventDefault(){}});}catch(e){problems.push('fazerLogin lançou: '+e.stack)} await sleep(800);
if(!w.eval('EU')) problems.push('login não definiu EU: err='+txt('#lg-err')+' cookie='+JSON.stringify(cookies)); else okl.push('login ok como '+w.eval('EU').papel);
if(d.getElementById('login').classList.contains('on')) problems.push('tela de login continua aberta após login');
// rodapé versão
okl.push('rodapé: '+txt('#foot'));
// FUNDOS
w.route_to('fundos'); await sleep(1200);
const fr=d.querySelectorAll('#fundos-body tr').length; okl.push(`fundos: ${fr} linhas`); if(fr<30) problems.push('fundos: menos de 30 linhas ('+fr+')');
if(d.querySelector('#fundos-body').textContent.includes('Arnaldo') && d.querySelector('#fundos-body tr[data-nav="fundo/F001"]').textContent.includes('no ar')) problems.push('fundos: F001 aparece "no ar" indevidamente');
const siglas=[...d.querySelectorAll('#fundos-body .sig')].filter(e=>!e.classList.contains('na')).length; okl.push('fundos: siglas visíveis '+siglas); if(siglas<28) problems.push('fundos: siglas não aparecem ('+siglas+')');
// filtros operacionais de fundos
if(!d.querySelector('#fundos-filtros [data-ff="publicado"]')) problems.push('fundos: filtro Publicados não existe');
else {
  d.querySelector('#fundos-filtros [data-ff="publicado"]').click(); await sleep(100);
  const pubs=d.querySelectorAll('#fundos-body tr').length; okl.push('fundos: filtro publicados -> '+pubs+' linha(s)');
  d.querySelector('#fundos-filtros [data-ff="todos"]').click();
  d.getElementById('fundos-q').value='Sami'; d.getElementById('fundos-q').dispatchEvent(new w.Event('input')); await sleep(100);
  if(!txt('#fundos-body').includes('Sami')) problems.push('fundos: busca Sami não retornou');
  d.getElementById('fundos-q').value=''; d.getElementById('fundos-q').dispatchEvent(new w.Event('input'));
}
checkDom('fundos');
// FUNDO detalhe
w.route_to('fundo/F026'); await sleep(1200); okl.push('fundo F026: '+txt('#fd h1')+' | '+(txt('#fd .meta')||'').slice(0,80));
if(!txt('#fd h1')) problems.push('fundo/F026: sem título'); if(d.querySelectorAll('#fd tbody tr[data-nav]').length<1) problems.push('fundo/F026: lista de projetos vazia');
if(!txt('#gcrumb').includes('F026')) problems.push('breadcrumb não mostra F026'); checkDom('fundo/F026');
// editar fundo (drawer)
await w.editarFundo('F026'); await sleep(400); if(!d.querySelector('#ef-titulo')) problems.push('editar fundo: formulário não abriu'); else okl.push('editar fundo: drawer ok');
w.closeDrawer();
// PROJETOS lista
w.route_to('projetos'); await sleep(1200); const pr=d.querySelectorAll('#projetos-body tr[data-nav]').length; okl.push('projetos: '+pr+' linhas'); if(pr<6) problems.push('projetos: lista incompleta '+pr); checkDom('projetos');
// busca servidor
d.getElementById('proj-q').value='Taru'; d.getElementById('proj-q').dispatchEvent(new w.Event('input')); await sleep(900); okl.push('busca projetos "Taru": '+d.querySelectorAll('#projetos-body tr[data-nav]').length+' linha(s)');
// PROJETO detalhe
w.route_to('projeto/F026-P0001'); await sleep(1200); okl.push('projeto: '+txt('#pd h1')+' | folhas '+d.querySelectorAll('#pd .thumb').length);
if(d.querySelectorAll('#pd .thumb').length<6) problems.push('projeto F026-P0001: esperava 6 folhas, veio '+d.querySelectorAll('#pd .thumb').length);
if(!d.querySelector('#pd .thumb img')) problems.push('projeto: miniaturas do site não usadas'); checkDom('projeto');
for(const t of ['erros','pedidos','historico']){ await w.showProjeto('F026-P0001',t); await sleep(300); checkDom('projeto aba '+t); }
await w.editarProjeto('F026-P0001'); await sleep(300); if(!d.querySelector('#ep-titulo')) problems.push('editar projeto: formulário não abriu'); else okl.push('editar projeto: drawer ok'); w.closeDrawer();
// ITEM
const first=d.querySelector('#pd .thumb[data-nav]'); await w.showProjeto('F026-P0001','itens'); await sleep(300);
const code=d.querySelector('#pd .thumb[data-nav]').dataset.nav.split('/')[1]; w.route_to('item/'+code); await sleep(1000);
okl.push('folha: '+txt('#idet h1')+' | '+(txt('#idet .pager')||'')); if(!d.querySelector('#idet img')) problems.push('folha: imagem do site não aparece'); checkDom('item');
if(!txt('#gcrumb').includes('folha')) problems.push('breadcrumb da folha errado: '+txt('#gcrumb'));
// ARQUITETOS
w.route_to('arquitetos'); await sleep(1000); const ar=d.querySelectorAll('#v-arquitetos tbody tr').length; okl.push('arquitetos: '+ar+' linhas'); if(ar<30) problems.push('arquitetos: lista incompleta '+ar); checkDom('arquitetos');
// CONFIG
w.route_to('config'); await sleep(1000); okl.push('config: usuários '+d.querySelectorAll('#usr-body tr').length+' | campos config '+d.querySelectorAll('#cfg-body input').length);
if(d.querySelectorAll('#usr-body tr').length<2) problems.push('config: usuários não carregaram'); if(d.querySelectorAll('#cfg-body input').length<10) problems.push('config: configurações não carregaram'); checkDom('config');
// ETIQUETAS
w.route_to('etiquetas'); await sleep(900); if(!d.querySelector('#lab-preview .label')) problems.push('etiquetas: preview vazio'); else okl.push('etiquetas: preview ok');
if(!d.querySelector('.lab-section')||!d.querySelector('.lab-preview-shell')) problems.push('etiquetas: novo layout em blocos/prévia não carregou');
if(!d.getElementById('l-local')||!d.getElementById('l-docs-volume')) problems.push('etiquetas: localização/quantidade por volume ausentes'); 
for(const t of ['documento','caixa','tubo','fundo']){ d.querySelector(`#lab-tabs [data-t="${t}"]`).click(); await sleep(100); if(!d.querySelector('#lab-preview .label')) problems.push('etiqueta '+t+' sem preview'); }
checkDom('etiquetas');
// PERFIL
await w.abrirPerfil(); await sleep(600); if(!d.querySelector('#pf-nova')) problems.push('perfil: não abriu'); else okl.push('perfil: ok'); w.closeModal();
// PAINEL / FILAS / SOLICITACOES / ERROS (reais)
w.route_to('painel'); await sleep(1800); if(d.querySelector('#v-painel .aviso-exemplo')) problems.push('painel ainda com aviso de exemplo');
if(!txt('#v-painel').includes('Operação agora')) problems.push('painel: bloco Operação agora ausente');
if(!txt('#v-painel').includes('Audiência do site')) problems.push('painel: bloco Audiência do site ausente');
if(!txt('#v-painel').includes('QNAP')) problems.push('painel: status QNAP ausente');
if(!txt('#v-painel').includes('Site público')) problems.push('painel: status do site ausente');
okl.push('painel operacional e audiência renderizados'); checkDom('painel');
// filas: criar lista, avançar
w.route_to('filas'); await sleep(600); if(d.querySelector('#v-filas .aviso-exemplo')) problems.push('filas ainda com aviso de exemplo');
w.openModal('m-lista'); d.getElementById('nl-nome').value='LOTE AUDIT'; d.getElementById('nl-proj').value='F023-P0011'; d.getElementById('nl-pasta').value='/mnt/qnap/acervos/F023/P0011'; await w.addLista(); await sleep(800);
const fl=d.querySelectorAll('#filas-body tr').length; okl.push('filas: '+fl+' linha(s) após criar'); if(!d.querySelector('#filas-body').textContent.includes('LOTE AUDIT')) problems.push('filas: lista criada não apareceu');
const btn=d.querySelector('#filas-body .btn.pri'); if(btn){btn.click(); await sleep(800); okl.push('filas: avançou etapa -> '+(d.querySelector('#filas-body .steps .cur')||{}).textContent);} checkDom('filas');
// solicitacoes
w.route_to('solicitacoes'); await sleep(600); if(d.querySelector('#v-solicitacoes .aviso-exemplo')) problems.push('solicitações ainda com aviso de exemplo');
w.openModal('m-sol'); d.getElementById('ns-nome').value='Editora Teste'; d.getElementById('ns-itens').value='F023-P0011 tif\nF026-P0001-1968-S01-D00001 jpg_3000'; await w.criarSolicitacao(); await sleep(800);
if(!d.querySelector('#v-solicitacoes tbody').textContent.includes('Editora Teste')) problems.push('solicitação criada não apareceu'); else okl.push('solicitações: pedido criado e listado');
await w.abrirSolicitacao(1); await sleep(300); if(!d.querySelector('#es-sit')) problems.push('solicitação: drawer não abriu'); else {d.getElementById('es-sit').value='em_preparacao'; await w.salvarSolicitacao(1); await sleep(600); okl.push('solicitações: situação alterada');} checkDom('solicitacoes');
// erros
w.route_to('erros'); await sleep(600); if(d.querySelector('#v-erros .aviso-exemplo')) problems.push('erros ainda com aviso de exemplo');
w.openModal('m-erro'); d.getElementById('ne-cod').value='F023-P0011-1959-S01-D00003'; d.getElementById('ne-grav').value='bloqueia'; d.getElementById('ne-cat').value='autoria_divergente'; d.getElementById('ne-desc').value='Carimbo de outro autor'; await w.criarErro(); await sleep(800);
if(!d.querySelector('#v-erros tbody').textContent.includes('Carimbo de outro autor')) problems.push('erro criado não apareceu'); else okl.push('erros: problema criado');
// projeto deve estar bloqueado e publicar deve falhar
let pb=await (await nodeFetch('/api/projetos/F023-P0011/detalhe')).json(); okl.push('projeto F023-P0011 status após erro bloqueante: '+pb.projeto.status_site); const bl=await (await nodeFetch('/api/projetos/F023-P0011/publicar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acao:'publicar'})})).json(); if(!bl.erro||!/[Bb]loqueado|[Dd]ireitos/.test(bl.erro)) problems.push('publicar com erro bloqueante deveria ser recusado: '+JSON.stringify(bl)); else okl.push('publicar recusado por bloqueio: '+bl.erro);
await w.abrirErro(1); await sleep(300); d.getElementById('ee-sit').value='corrigido'; d.getElementById('ee-res').value='Folha movida'; await w.salvarErro(1); await sleep(600);
pb=await (await nodeFetch('/api/projetos/F023-P0011/detalhe')).json(); okl.push('status após resolver: '+pb.projeto.status_site);  checkDom('erros');
// direitos / entradas / localização / estações / auditoria
w.route_to('fundo/F023'); await sleep(1200); if(!txt('#fd-direitos').includes('Situação')) problems.push('fundo: painel de direitos não carregou'); else okl.push('direitos: '+txt('#fd-direitos .tag'));
// autorizar projeto de fundo sem direitos deve falhar
let au=await (await nodeFetch('/api/projetos/F010-P0006',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({autorizado_site:true})})).json(); if(!au.erro||!/[Dd]ireitos/.test(au.erro)) problems.push('autorizar sem direitos deveria falhar: '+JSON.stringify(au)); else okl.push('portão de direitos: '+au.erro.slice(0,60));
await w.editarDireitos('F010'); await sleep(300); d.getElementById('dr-sit').value='autorizado'; d.getElementById('dr-doc').value='termo família 2026'; await w.salvarDireitos('F010'); await sleep(500);
au=await (await nodeFetch('/api/projetos/F010-P0006',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({autorizado_site:true})})).json(); if(au.erro) problems.push('autorizar após direitos falhou: '+au.erro); else okl.push('autorização liberada após direitos');
w.openModal('m-entrada'); d.getElementById('nen-fundo').value='F010'; d.getElementById('nen-tipo').value='doacao'; d.getElementById('nen-por').value='Família Segnini'; d.getElementById('nen-vol').value='12'; await w.criarEntrada(); await sleep(900); if(!txt('#fd-entradas').includes('Família Segnini')) problems.push('entrada registrada não apareceu'); else okl.push('entrada de acervo registrada');
w.route_to('localizacao'); await sleep(800); w.openModal('m-loc'); d.getElementById('nloc-id').value='cx07'; d.getElementById('nloc-fundo').value='F023'; await w.criarLocalizacao(); await sleep(600); if(!txt('#loc-body').includes('CX07')) problems.push('localização criada não apareceu'); else okl.push('localização CX07 criada');
const lid=(await (await nodeFetch('/api/localizacoes')).json()).find(l=>l.identificador==='CX07').id; await w.verLocalizacao(lid); await sleep(300); d.getElementById('al-proj').value='F023-P0011'; await w.alocar(lid); await sleep(600); const nl=(await (await nodeFetch(`/api/localizacoes/${lid}/itens`)).json()).length; okl.push('alocadas em CX07: '+nl); if(nl<30) problems.push('alocação do projeto inteiro falhou: '+nl);
w.closeDrawer(); const c1=d.querySelector('#filas-body'); w.route_to('item/F023-P0011-1959-S01-D00001'); await sleep(900); if(!(txt('#it-loc')||'').includes('CX07')) problems.push('folha não mostra onde está: '+txt('#it-loc')); else okl.push('folha mostra localização CX07');
w.route_to('estacoes'); await sleep(2500); if(!txt('#est-body').includes('QNAP')) problems.push('estações não carregou'); else okl.push('estações: '+(txt('#est-body').slice(0,80)));
w.route_to('auditoria'); await sleep(800); const ne=d.querySelectorAll('#au-body tr').length; okl.push('auditoria: '+ne+' eventos'); if(ne<10) problems.push('auditoria vazia'); checkDom('auditoria');
w.route_to('painel'); await sleep(800); checkDom('painel2'); okl.push('painel precisa de você: '+d.querySelectorAll('#v-painel .list li').length+' item(ns)');
// modais: botões referenciam funções?
checkDom('global');
// novo fundo via modal
w.openModal('m-fundo'); d.getElementById('nf-nome').value='Teste Auditoria'; d.getElementById('nf-sigla').value='TAU'; await w.addFundo(); await sleep(1200);
okl.push('novo fundo: hash='+w.location.hash+' h1='+txt('#fd h1'));
console.log('\n=== OK ==='); okl.forEach(x=>console.log(' ✓',x));
console.log('\n=== PROBLEMAS ('+problems.length+') ==='); [...new Set(problems)].forEach(x=>console.log(' ✗',x));
process.exit(0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
