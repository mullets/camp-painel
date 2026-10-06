// Auditoria das funções novas (busca global, lote, recentes/favoritos, ajuda, validação, dirty-state, export,
// estações, analytics, permissões). Uso: bash tests/rodar_auditoria.sh  (sobe servidor + banco sintético)
const {JSDOM}=require('jsdom');
const BASE='http://127.0.0.1:8765'; const problems=[]; const okl=[];
function jar(){ const c={}; return {c, async f(url,opt={}){ if(url.startsWith('/')) url=BASE+url;
  const h={...(opt.headers||{})}; if(Object.keys(c).length) h.cookie=Object.entries(c).map(([k,v])=>`${k}=${v}`).join('; ');
  if(opt.body&&!h['Content-Type']) h['Content-Type']='application/json';
  const r=await fetch(url,{...opt,headers:h,redirect:'manual'}); const sc=r.headers.get('set-cookie');
  if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) c[m[1]]=m[2];} return r; }}; }
const adm=jar(), ope=jar(), anon=jar();
const J=async(j,u,o)=>{const r=await j.f(u,o); let b=null; try{b=await r.json()}catch(_){} return {s:r.status,b}};
const chk=(c,m)=>{ if(!c) problems.push(m); };
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
// ---------- API ----------
await J(adm,'/api/auth/login',{method:'POST',body:JSON.stringify({email:'rafael@camp.arq.br',senha:'senha-bem-longa-123'})});
await J(ope,'/api/auth/login',{method:'POST',body:JSON.stringify({email:'operador@camp.arq.br',senha:'senha-operador-123'})});
// busca global
for(const [q,tipo,cod] of [['Taru','projeto','F026-P0001'],['F023-P0011-1959-S01-D00003','documento','F023-P0011-1959-S01-D00003'],['BSG','fundo','F002'],['F010','fundo','F010'],['F002-P0002','projeto','F002-P0002']]){
  const r=await J(adm,'/api/busca?q='+encodeURIComponent(q)); const hit=(r.b&&r.b.resultados||[]).find(x=>x.codigo===cod);
  chk(r.s===200&&hit,`busca "${q}": esperava ${tipo} ${cod}; status ${r.s}; veio ${(r.b&&r.b.resultados||[]).slice(0,3).map(x=>x.codigo)}`);
  if(hit&&hit.tipo!==tipo) problems.push(`busca "${q}": tipo ${hit.tipo} em vez de ${tipo}`); }
let r=await J(adm,'/api/busca?q=zzzzqqq'); chk(r.s===200&&r.b.resultados.length===0,'busca sem resultado deveria ser lista vazia');
r=await J(adm,'/api/busca?q=%25'); chk(r.s===200,'busca com % não pode quebrar: '+r.s);
r=await J(adm,"/api/busca?q="+encodeURIComponent("' OR 1=1 --")); chk(r.s===200&&r.b.resultados.length===0,'busca com aspas/SQL: '+r.s+' '+JSON.stringify(r.b).slice(0,80));
r=await J(anon,'/api/busca?q=F001'); chk(r.s===401,'busca SEM login deveria dar 401, deu '+r.s);
okl.push('busca global: códigos de fundo/projeto/folha/sigla/título, vazio, injeção e sem login');
// lote e exportação
r=await J(adm,'/api/projetos/lote',{method:'POST',body:JSON.stringify({codigos:['F026-P0001'],acao:'apagar'})}); chk(r.s===400,'lote com ação inválida: '+r.s);
r=await J(adm,'/api/projetos/lote',{method:'POST',body:JSON.stringify({codigos:[],acao:'publicar'})}); chk(r.s===400,'lote vazio: '+r.s);
r=await J(adm,'/api/projetos/lote',{method:'POST',body:JSON.stringify({codigos:['F026-P0001','F999-P0001'],acao:'publicar'})});
chk(r.s===200&&r.b.selecionados===2&&Array.isArray(r.b.falhas),'lote publicar deveria devolver resultado parcial estruturado, não 500: '+r.s+' '+JSON.stringify(r.b).slice(0,160));
if(r.s===200) chk(r.b.ok.length===0,'lote publicou sem direitos do fundo definidos: '+JSON.stringify(r.b.ok));
if(r.s===200) okl.push('lote publicar sem direitos -> bloqueado com motivo: '+((r.b.falhas[0]||{}).erro||'?').slice(0,70));
r=await J(ope,'/api/projetos/lote',{method:'POST',body:JSON.stringify({codigos:['F026-P0001'],acao:'publicar'})}); chk(r.s===403,'OPERADOR não deveria publicar em lote: '+r.s);
r=await J(adm,'/api/projetos/exportar-selecao',{method:'POST',body:JSON.stringify({codigos:['F026-P0001','F023-P0011'],acao:'exportar'})}); chk(r.s===200&&r.b.itens.length===2,'exportar seleção: '+r.s);
r=await J(adm,'/api/projetos/codigos?q=Taru'); chk(r.s===200&&r.b.codigos.includes('F026-P0001'),'/api/projetos/codigos: '+r.s);
// permissões do operador
r=await J(ope,'/api/logs'); chk(r.s===403,'operador lendo /api/logs: '+r.s); r=await J(adm,'/api/logs'); chk(r.s===200,'admin /api/logs: '+r.s);
r=await J(ope,'/api/analytics/diagnostico'); okl.push('operador em /analytics/diagnostico: HTTP '+r.s);
r=await J(adm,'/api/analytics/diagnostico'); chk(r.s<500,'/api/analytics/diagnostico sem WordPress configurado deu '+r.s+' (deveria explicar, não quebrar)'); else_ok:{ okl.push('analytics/diagnostico sem WP: HTTP '+r.s+' '+JSON.stringify(r.b).slice(0,90)); }
r=await J(adm,'/api/analytics'); chk(r.s<500,'/api/analytics sem WordPress deu '+r.s);
r=await J(ope,'/api/usuarios'); chk(r.s===403,'operador listando usuários: '+r.s);
// estações (sem login, rede local)
r=await J(anon,'/api/estacoes/contexto'); chk(r.s===200,'estacoes/contexto na LAN: '+r.s);
const hb={estacao_id:'foto1',tipo_estacao:'foto',app:'CAMP Foto',versao:'1.0',hostname:'mac-foto1',estado:'capturando',fundo_codigo:'F001',projeto_codigo:'F001-P0001',operador:'Teste'};
const raw=(u,o)=>fetch(BASE+u,{...o,headers:{'Content-Type':'application/json',...((o||{}).headers||{})}});
let rr=await raw('/api/estacoes/heartbeat',{method:'POST',body:JSON.stringify(hb)}); chk(rr.status===200,'heartbeat válido: '+rr.status);
rr=await raw('/api/estacoes/heartbeat',{method:'POST',body:JSON.stringify({...hb,estado:'dormindo'})}); chk(rr.status===400,'heartbeat estado inválido: '+rr.status);
rr=await raw('/api/estacoes/heartbeat',{method:'POST',body:JSON.stringify({...hb,tipo_estacao:'impressora'})}); chk(rr.status===400,'heartbeat tipo inválido: '+rr.status);
rr=await raw('/api/estacoes/heartbeat',{method:'POST',body:JSON.stringify({...hb,estacao_id:'x'.repeat(200)})}); chk(rr.status===400,'heartbeat id enorme: '+rr.status);
rr=await raw('/api/estacoes/heartbeat',{method:'POST',headers:{'X-Forwarded-For':'8.8.8.8'},body:JSON.stringify(hb)}); chk(rr.status===403,'SEGURANÇA heartbeat via proxy deveria ser 403: '+rr.status);
rr=await raw('/api/estacoes/projetos/reservar',{method:'POST',headers:{'CF-Connecting-IP':'8.8.8.8'},body:JSON.stringify({fundo_codigo:'F001',titulo:'Invasor'})}); chk(rr.status===403,'SEGURANÇA reservar via túnel deveria ser 403: '+rr.status);
rr=await raw('/api/estacoes/projetos/reservar',{method:'POST',body:JSON.stringify({fundo_codigo:'F001',titulo:'   '})}); chk(rr.status===400,'reservar sem título: '+rr.status);
rr=await raw('/api/estacoes/projetos/reservar',{method:'POST',body:JSON.stringify({fundo_codigo:'F999',titulo:'X'})}); chk(rr.status===404,'reservar fundo inexistente: '+rr.status);
rr=await raw('/api/estacoes/projetos/reservar',{method:'POST',body:JSON.stringify({fundo_codigo:'F001',titulo:'X',ano:3000})}); chk(rr.status===400,'reservar ano inválido: '+rr.status);
const par=await Promise.all(Array.from({length:6},(_,i)=>raw('/api/estacoes/projetos/reservar',{method:'POST',body:JSON.stringify({fundo_codigo:'F001',titulo:'Concorrente '+i,identificacao_original:'CX0'+i})}).then(async x=>({s:x.status,b:await x.json().catch(()=>({}))}))));
const cods=par.map(x=>x.b.codigo||(x.b.projeto&&x.b.projeto.codigo)||JSON.stringify(x.b).slice(0,60));
chk(par.every(x=>x.s===200),'reservas simultâneas: status '+par.map(x=>x.s)); chk(new Set(cods).size===6,'RACE: códigos duplicados nas reservas simultâneas: '+cods.join(', '));
okl.push('6 reservas simultâneas -> '+cods.join(', '));
r=await J(adm,'/api/estacoes'); chk(r.s===200&&JSON.stringify(r.b).includes('foto1'),'heartbeat não aparece em /api/estacoes');
r=await J(adm,'/api/projetos/F001-P0002/detalhe'); chk(r.s===200&&r.b.projeto.titulo.startsWith('Concorrente'),'projeto reservado pela estação não existe/legível: '+r.s); okl.push('projeto reservado pela estação: '+(r.b&&r.b.projeto&&r.b.projeto.titulo)+' | identificação original: '+(r.b&&r.b.projeto&&r.b.projeto.identificacao_original));
// ---------- NAVEGADOR ----------
const html=await (await fetch(BASE+'/')).text();
const dom=new JSDOM(html,{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){
  w.fetch=(u,o={})=>adm.f(u,o); w.Element.prototype.scrollTo=()=>{}; w.confirm=()=>true; w.alert=m=>okl.push('alert:'+m); w.prompt=()=>null;
  w.URL.createObjectURL=()=>'blob:teste'; w.URL.revokeObjectURL=()=>{}; w.HTMLAnchorElement.prototype.click=function(){w.__baixou=(w.__baixou||[]).concat(this.download||this.href)};
  w.console.error=(...a)=>problems.push('console.error: '+a.join(' '));
  w.addEventListener('error',e=>problems.push('window.error: '+(e.error&&e.error.stack||e.message)));
  w.addEventListener('unhandledrejection',e=>problems.push('unhandled: '+(e.reason&&e.reason.stack||e.reason)));
}});
const w=dom.window,d=w.document; await sleep(1500);
d.getElementById('lg-email').value='rafael@camp.arq.br'; d.getElementById('lg-senha').value='senha-bem-longa-123'; await w.fazerLogin({preventDefault(){}}); await sleep(800);
chk(w.eval('EU'),'login no navegador falhou');
const txt=s=>{const e=d.querySelector(s);return e?e.textContent.replace(/\s+/g,' ').trim():''};
// busca global pela interface
const Q=w.eval('q'), QR=w.eval('qres');
Q.value='Taru'; Q.dispatchEvent(new w.Event('input')); await sleep(900);
chk(QR.classList.contains('open')&&QR.querySelectorAll('[data-search-index]').length>=1,'busca UI: sem resultados para "Taru"'); chk(QR.textContent.includes('Casa Tarumã'),'busca UI: não mostra Casa Tarumã');
Q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true})); Q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true})); await sleep(900);
chk(w.location.hash==='#projeto/F026-P0001','busca UI: teclado ↓ + Enter não abriu o projeto (hash='+w.location.hash+')');
Q.value='zzzzqqq'; Q.dispatchEvent(new w.Event('input')); await sleep(900); chk(QR.textContent.includes('Nenhum resultado'),'busca UI: sem mensagem de zero resultados'); Q.value=''; QR.classList.remove('open');
okl.push('busca UI: digitar, ↓, Enter, zero resultados');
// recentes e favoritos
const rec=JSON.parse(w.localStorage.getItem('camp.recentes')||w.localStorage.getItem('camp.recentes:rafael@camp.arq.br')||'null');
const chaves=Object.keys(w.localStorage).filter(k=>k.includes('recentes')); chk(chaves.length>0,'recentes: nada gravado após abrir projeto');
w.toggleFavorito('projeto/F026-P0001'); chk(w.ehFavorito('projeto/F026-P0001'),'favorito não marcou'); Q.value=''; Q.dispatchEvent(new w.Event('focus')); await sleep(200);
chk(QR.textContent.includes('Tarumã')||QR.textContent.includes('F026'),'busca vazia não mostra favoritos/recentes: '+QR.textContent.slice(0,80)); w.toggleFavorito('projeto/F026-P0001'); chk(!w.ehFavorito('projeto/F026-P0001'),'favorito não desmarcou'); QR.classList.remove('open');
okl.push('recentes e favoritos pessoais');
// lote na interface
w.route_to('projetos'); await sleep(1200);
w.selecionarProjetosVisiveis(true); chk(d.getElementById('proj-bulk').classList.contains('on'),'barra de lote não apareceu'); const nvis=d.querySelectorAll('#projetos-body .proj-sel').length; chk(nvis>=8&&txt('#proj-bulk-count')===nvis+' selecionados','contagem do lote: '+txt('#proj-bulk-count')+' para '+nvis+' linhas');
await w.exportarProjetosSelecionados(); await sleep(500); chk((w.__baixou||[]).length>0,'exportar seleção não gerou download');
w.limparSelecaoProjetos(); chk(!d.getElementById('proj-bulk').classList.contains('on'),'barra de lote não sumiu ao limpar');
await w.acaoLoteProjetos('publicar'); w.route_to('projetos'); okl.push('lote na interface: selecionar, exportar, limpar');
// exportar visão atual
for(const v of ['fundos','projetos','solicitacoes','erros']){ w.route_to(v); await sleep(700); w.__baixou=[]; try{w.exportarVisaoAtual(v)}catch(e){problems.push('exportarVisaoAtual('+v+') lançou: '+e.message)} chk((w.__baixou||[]).length>0,'exportar visão atual de '+v+' não baixou nada'); }
okl.push('exportar visão atual (CSV) em 4 listas');
// validação por campo
w.route_to('fundos'); await sleep(500); w.openModal('m-fundo'); d.getElementById('nf-nome').value=''; d.getElementById('nf-sigla').value='ab'; const antes=d.querySelectorAll('#fundos-body tr').length;
try{await w.addFundo()}catch(e){problems.push('addFundo vazio lançou: '+e.message)} await sleep(600);
chk(d.querySelectorAll('.field.invalid .field-error').length>=1,'validação: nenhum erro por campo apareceu com formulário vazio'); chk(d.querySelectorAll('#fundos-body tr').length===antes,'validação: fundo inválido foi criado'); w.closeModal();
okl.push('validação por campo: '+0+' fundos inválidos criados');
// dirty-state
w.route_to('fundo/F026'); await sleep(900); await w.editarFundo('F026'); await sleep(400);
const dr=w.eval('mainEl'); const cls0=dr.className; chk(cls0.includes('with-drawer'),'drawer não abriu'); const t=d.getElementById('ef-titulo'); t.value=t.value+' x'; t.dispatchEvent(new w.Event('input',{bubbles:true})); await sleep(100);
chk(d.getElementById('dirty-state').classList.contains('on'),'dirty-state não apareceu após editar');
w.confirm=()=>false; const c1=w.closeDrawer(); chk(c1===false&&dr.className===cls0,'fechar com alteração e "cancelar" deveria manter o drawer aberto');
w.confirm=()=>true; const c2=w.closeDrawer(); chk(c2===true&&!dr.className.includes('with-drawer'),'fechar com "ok" deveria fechar o drawer');
const ev=new w.Event('beforeunload',{cancelable:true}); w.editarFundo&&await w.editarFundo('F026'); await sleep(300); const t2=d.getElementById('ef-titulo'); t2.value+='y'; t2.dispatchEvent(new w.Event('input',{bubbles:true})); w.dispatchEvent(ev); chk(ev.defaultPrevented||ev.returnValue!==undefined,'beforeunload não protege edição pendente'); w.confirm=()=>true; w.closeDrawer();
okl.push('proteção de edição não salva (drawer + beforeunload)');
// ajuda
for(const rota of ['painel','fundos','projetos','etiquetas','config']){ w.route_to(rota); await sleep(500); try{w.abrirAjuda()}catch(e){problems.push('abrirAjuda em '+rota+': '+e.message)} chk(txt('#d-title').startsWith('Ajuda'),'ajuda não abriu em '+rota); w.closeDrawer(); }
d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'?',bubbles:true})); await sleep(300); okl.push('ajuda contextual em 5 telas');
// analytics diagnóstico (UI)
w.route_to('painel'); await sleep(1500); try{await w.diagnosticarAnalytics(); await sleep(800)}catch(e){problems.push('diagnosticarAnalytics lançou: '+e.message)}
chk(!/undefined|NaN|\[object Object\]/.test(txt('#v-painel')),'painel após diagnóstico mostra texto quebrado');
okl.push('botão Diagnosticar Analytics sem WordPress: '+txt('#v-painel').slice(0,0)+'sem exceção');

// ---------- EDIÇÃO DE TEXTOS DA FOLHA ----------
const IT='F023-P0011-1959-S01-D00001', IT3='F023-P0011-1959-S01-D00003';
const lei=jar(); await J(lei,'/api/auth/login',{method:'POST',body:JSON.stringify({email:'leitor@camp.arq.br',senha:'senha-leitor-1234'})});
r=await J(lei,'/api/itens/'+IT+'/edicao'); chk(r.s===403,'leitura abrindo edição da folha: '+r.s);
r=await J(lei,'/api/itens/'+IT,{method:'PATCH',body:JSON.stringify({titulo:'x'})}); chk(r.s===403,'leitura editando folha: '+r.s);
r=await J(ope,'/api/itens/'+IT+'/edicao'); chk(r.s===200&&r.b.site&&r.b.site.campos.length===3,'operador abre edição com 3 campos do site: '+r.s+' '+JSON.stringify(r.b&&r.b.site&&r.b.site.campos.map(c=>c.nome)));
w.route_to('item/'+IT); await sleep(1200);
chk(!!d.getElementById('it-editar'),'botão Editar não aparece para master');
await w.editarItem(IT); await sleep(500);
chk(txt('#d-title').startsWith('Editar'),'drawer de edição da folha não abriu');
for(const id of ['ei-titulo','ei-tipo_documento','ei-folha','ei-escala','ei-ano_folha','ei-suporte','ei-dimensoes','ei-credito','ei-titulo_site','ei-descricao_site','ei-md-0','ei-md-1','ei-md-2']) chk(d.getElementById(id),'campo ausente no formulário: '+id);
const selTax=[...d.querySelectorAll('#drawer select[data-nome]')][0]; chk(selTax&&[...selTax.options].map(o=>o.value).includes('Corte'),'taxonomia sem opções existentes');
chk(selTax&&selTax.value==='Planta','taxonomia não veio com o valor atual selecionado: '+(selTax&&selTax.value));
chk(d.getElementById('ei-descricao_site').value==='Planta baixa do pavimento térreo.','descrição atual não veio preenchida');
chk(txt('#drawer').includes('Somente leitura aqui')&&txt('#drawer').includes('Data do registro fotográfico'),'campo de tipo não suportado deveria aparecer como somente leitura');
// sem mudança -> "Nada mudou"
await w.salvarItem(IT); await sleep(400); chk(txt('#toast').includes('Nada mudou'),'salvar sem mudar deveria dizer "Nada mudou": '+txt('#toast'));
// validação: título do site obrigatório
await w.editarItem(IT); await sleep(300); d.getElementById('ei-titulo_site').value=''; await w.salvarItem(IT); await sleep(300);
chk(d.querySelectorAll('#drawer .field.invalid .field-error').length>=1,'título do site vazio deveria acusar erro no campo'); w.closeDrawer(true);
// XSS: texto malicioso salvo e exibido como texto
await w.editarItem(IT); await sleep(300); d.getElementById('ei-titulo').value='<img src=x onerror="window.__xss=1"> Planta'; d.getElementById('ei-escala').value='<script>window.__xss=2</script>';
await w.salvarItem(IT); await sleep(1500);
chk(!w.__xss,'XSS: o texto digitado foi executado como HTML!'); chk(!d.querySelector('#idet img[src="x"]'),'XSS: <img> injetado apareceu na tela'); chk(txt('#idet').includes('<img src=x'),'o texto salvo deveria aparecer literal na tela');
okl.push('edição: texto com <img onerror> e <script> salvo e mostrado literalmente (sem executar)');
// edição de taxonomia + site sem credencial (Tainacan não configurado no teste) => salva no painel e avisa
await w.editarItem(IT); await sleep(300); d.getElementById('ei-titulo').value='Planta baixa térrea'; d.getElementById('ei-escala').value='1:100'; d.getElementById('ei-titulo_site').value='Planta térrea — P0011';
const s2=[...d.querySelectorAll('#drawer select[data-nome]')][0]; s2.value='Corte'; for(const id of ['ei-titulo','ei-escala','ei-titulo_site'])d.getElementById(id).dispatchEvent(new w.Event('input',{bubbles:true})); s2.dispatchEvent(new w.Event('change',{bubbles:true}));
chk(d.getElementById('dirty-state').classList.contains('on'),'edição da folha não marcou "alterações não salvas"');
await w.salvarItem(IT); await sleep(1800);
r=await J(adm,'/api/itens/'+IT); chk(r.b.item.titulo==='Planta baixa térrea'&&r.b.item.escala==='1:100','painel não gravou a catalogação: '+JSON.stringify(r.b.item).slice(0,80));
chk(!!d.querySelector('#idet .edit-alerta'),'falha do site deveria aparecer como aviso fixo na folha'); chk(txt('#idet .edit-alerta').includes('o site não aceitou'),'texto do aviso de falha: '+txt('#idet .edit-alerta').slice(0,80));
chk(txt('#idet').includes('Planta baixa térrea'),'folha não recarregou com o título novo');
r=await J(adm,'/api/eventos?entidade=item&codigo='+IT); const evs=JSON.stringify(r.b); chk(evs.includes('"editado"')&&evs.includes('antes')&&evs.includes('depois'),'auditoria da edição da folha sem antes/depois');
okl.push('edição de folha: catalogação salva + site recusado (sem WordPress no teste) -> aviso fixo na folha');
w.route_to('item/'+IT3); await sleep(900); w.route_to('item/'+IT); await sleep(900); chk(!d.querySelector('#idet .edit-alerta'),'o aviso de falha deveria aparecer só uma vez');
// leitura não vê o botão
{ const dl=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>lei.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}});
  await sleep(1500); dl.window.document.getElementById('lg-email').value='leitor@camp.arq.br'; dl.window.document.getElementById('lg-senha').value='senha-leitor-1234'; await dl.window.fazerLogin({preventDefault(){}}); await sleep(800);
  dl.window.route_to('item/'+IT); await sleep(1200); chk(!dl.window.document.getElementById('it-editar'),'usuário de LEITURA vê o botão Editar'); okl.push('usuário de leitura não vê o botão Editar'); dl.window.route_to('projeto/F026-P0001'); await sleep(1800); chk(!!dl.window.document.getElementById('pd-pub')&&!dl.window.document.getElementById('pd-publicar')&&!dl.window.document.querySelector('#pd-pub .chk button'),'leitura deveria ver o checklist mas NÃO os botões de publicar/resolver'); dl.window.route_to('estacoes'); await sleep(3000); chk(!!dl.window.document.getElementById('imp-painel')&&!dl.window.document.getElementById('imp-ver'),'leitura deveria ver o painel de importação mas NÃO o botão "Ver o que está faltando"'); chk(!!dl.window.document.getElementById('bk-painel')&&!dl.window.document.getElementById('bk-agora'),'leitura deveria VER o painel de backup mas NÃO o botão "Fazer backup agora"'); dl.window.close(); }

// ---------- IMAGENS: nunca desenhar planta falsa ----------
await w.showProjeto('F001-P0001','itens'); await sleep(1000);
const cardsSem=[...d.querySelectorAll('#pd .thumb')]; chk(cardsSem.length>=2,'projeto sem imagens: cards não apareceram ('+cardsSem.length+')');
chk(cardsSem.every(c=>c.querySelector('.sem-imagem')),'folha sem imagem deveria mostrar a caixa "Sem imagem"');
chk(!d.querySelector('#pd .thumb svg'),'PLANTA FALSA: a grade ainda desenha SVG inventado no lugar da imagem');
chk(txt('#pd .sem-imagem').includes('Sem imagem'),'texto "Sem imagem" ausente');
await w.showProjeto('F026-P0001','itens'); await sleep(1000);
chk(d.querySelectorAll('#pd .thumb img.img-real').length>=6,'folhas com miniatura do site deveriam mostrar a imagem real');
chk(!d.querySelector('#pd .thumb svg'),'projeto com imagens também não pode ter SVG sintético');
okl.push('grade do projeto: folhas sem imagem mostram "Sem imagem"; com miniatura mostram a imagem real; zero SVG inventado');
w.route_to('item/F001-P0001-1961-S01-D00001'); await sleep(1000);
chk(!!d.querySelector('#idet .sem-imagem')&&!d.querySelector('#idet .viewer svg'),'folha sem imagem: deveria mostrar aviso, não desenho');
w.route_to('item/F001-P0001-1961-S01-D00002'); await sleep(1000);
chk(!!d.querySelector('#idet .sem-imagem'),'documento TIFF não é imagem de navegador: deveria dizer "Sem imagem"');
w.route_to('item/'+IT3); await sleep(1000);
const big=d.querySelector('#idet .viewer img.img-grande'); chk(big&&big.getAttribute('src').endsWith('D00003.jpg'),'folha com documento JPG deveria mostrar o arquivo do documento: '+(big&&big.getAttribute('src')));
chk(txt('#idet').includes('Imagem mostrada'),'folha não informa de onde vem a imagem');
// imagem que não carrega -> aviso em vez de ícone quebrado
const im=d.querySelector('#idet .viewer img.img-real'); chk(!!im,'folha com imagem não usa <img class="img-real"> (sem tratamento de imagem quebrada)');
if(im){im.dispatchEvent(new w.Event('error')); await sleep(100);
 chk(!d.querySelector('#idet .viewer img.img-real')&&!!d.querySelector('#idet .viewer .sem-imagem'),'imagem quebrada deveria virar aviso "não carregou"'); chk(txt('#idet .sem-imagem').includes('não carregou'),'mensagem de imagem quebrada');}
okl.push('folha: imagem grande vem do documento; sem imagem/TIFF/imagem quebrada mostram aviso explícito');

// ---------- LINK DA PÁGINA PÚBLICA SÓ QUANDO É PÚBLICA ----------
w.route_to('item/'+IT); await sleep(1100);
chk(!txt('#idet').includes('Ver página pública')&&txt('#idet').includes('Abrir no site (não publicado)'),'folha em RASCUNHO não pode oferecer "Ver página pública": '+txt('#idet .act').slice(0,90));
chk(/No site\s*rascunho/.test(txt('#idet')),'folha em rascunho deveria mostrar "No site: rascunho": '+(txt('#idet').match(/No site.{0,40}/)||[''])[0]);
w.route_to('item/F023-P0011-1959-S01-D00002'); await sleep(1100);
chk(txt('#idet').includes('Ver página pública')&&!txt('#idet').includes('Abrir no site (não publicado)'),'folha PUBLICADA deveria oferecer "Ver página pública"');
chk(/No site\s*publicado/.test(txt('#idet')),'folha publicada deveria mostrar "No site: publicado"');
w.route_to('projeto/F026-P0001'); await sleep(1300);
chk(!txt('#v-projeto').includes('Ver página pública')&&!txt('#v-projeto').includes('abrir página pública'),'projeto NÃO publicado oferece link de página pública'); chk(txt('#v-projeto').includes('ainda não é pública'),'projeto não publicado deveria explicar que a página ainda não é pública');
w.route_to('projeto/F003-P0001'); await sleep(1300);
chk(txt('#v-projeto').includes('Ver página pública')&&[...d.querySelectorAll('#v-projeto a')].some(a=>/\/acervo\/projetos\/f003-p0001-/.test(a.href)),'projeto PUBLICADO deveria ter link /acervo/projetos/f003-p0001-...');
okl.push('link da página pública: só em item/projeto publicado; rascunho/privado explica por que não abre');

// ---------- BACKUP DO BANCO ----------
r=await J(ope,'/api/backup'); chk(r.s===403,'operador vendo /api/backup: '+r.s);
r=await J(ope,'/api/backup/agora',{method:'POST'}); chk(r.s===403,'operador fazendo backup: '+r.s);
r=await J(adm,'/api/backup'); chk(r.s===200&&r.b.existe===false,'sem backup ainda deveria dar existe=false: '+JSON.stringify(r.b).slice(0,80));
w.route_to('estacoes'); await sleep(3000);
chk(!!d.getElementById('bk-painel')&&txt('#bk-painel').includes('sem backup'),'painel de backup deveria dizer "sem backup": '+txt('#est-body').slice(0,60));
chk(txt('#system-banner').includes('nenhum backup do banco'),'banner global deveria avisar "nenhum backup do banco": "'+txt('#system-banner').slice(0,80)+'"');
chk(!!d.getElementById('bk-agora'),'botão "Fazer backup agora" não aparece para master');
await w.backupAgora(); await sleep(3500);
chk(txt('#bk-painel').includes('em dia'),'depois do backup o painel deveria dizer "em dia": '+txt('#bk-painel').slice(0,90));
chk(!txt('#system-banner').includes('nenhum backup do banco'),'banner continua acusando falta de backup depois do backup');
r=await J(adm,'/api/backup'); chk(r.b.existe&&r.b.ok===true&&r.b.quantidade===1&&r.b.contagens.integridade==='ok','API depois do backup: '+JSON.stringify(r.b).slice(0,120));
r=await J(ope,'/api/estacoes'); chk(r.s===200&&r.b.backup&&r.b.backup.existe&&!('arquivo' in r.b.backup),'operador deveria receber o estado do backup sem caminhos');
// máquinas sem resposta são normais: NÃO podem aparecer no banner global nem no resumo do painel inicial
{ const est=await J(adm,'/api/estacoes'); const off=(est.b.maquinas||[]).filter(m=>m.ip&&m.online===false).map(m=>m.nome);
  chk(off.length>0,'precondição: o ambiente de teste deveria ter máquinas sem resposta ('+off.length+')');
  chk(!off.some(n=>txt('#system-banner').includes(n))&&!/CAMP Vision 2 sem resposta|QNAP sem resposta/.test(txt('#system-banner')),'o banner global não deveria citar máquina sem resposta: "'+txt('#system-banner').slice(0,140)+'"');
  w.route_to('painel'); await sleep(2500);
  chk(!d.querySelector('#v-painel .machine-strip'),'o painel inicial não deveria repetir a faixa de máquinas (a barra do topo já mostra)');
  chk(!/offline/i.test(txt('#v-painel .dash-state')),'o resumo do painel não deveria dizer "offline" por causa de máquinas: '+txt('#v-painel .dash-state'));
  chk(!!d.querySelector('.machine-status button, .machine-status .ms'),'a barra do topo deve continuar mostrando as máquinas'); }
okl.push('backup: painel na tela de Estações, banner global (some depois do backup), botão e permissões');


// ---------- FOLHAS SÓ NO SITE: abrir importa e passa a editar como as demais ----------
{ const SO='F002-P0002-1977-S01-D00002', SO1='F002-P0002-1977-S01-D00001';
  // quem só lê: recebe a explicação e NADA é importado
  const dl2=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>lei.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}});
  await sleep(1500); dl2.window.document.getElementById('lg-email').value='leitor@camp.arq.br'; dl2.window.document.getElementById('lg-senha').value='senha-leitor-1234'; await dl2.window.fazerLogin({preventDefault(){}}); await sleep(800);
  dl2.window.route_to('item/'+SO1); await sleep(2000);
  chk(/existe só no site/.test(dl2.window.document.body.textContent)&&/operador/.test(dl2.window.document.body.textContent),'leitura deveria ver a explicação "existe só no site… peça a um operador"');
  r=await J(adm,'/api/itens/'+SO1); chk(r.s===404,'leitura NÃO pode ter importado a folha: '+r.s); dl2.window.close();
  // master/operador: vê a tag e o botão no projeto
  w.route_to('projeto/F002-P0002'); await sleep(2000);
  chk(!!d.querySelector('[data-nav="item/'+SO+'"] .tag.origin'),'a folha só no site deveria ter a tag "só no site"');
  chk(!!d.getElementById('pd-importar')&&txt('#pd-importar').includes('2 folha(s)'),'o projeto deveria oferecer "Importar 2 folha(s) só no site": '+txt('#pd-source, .project-source').slice(0,120));
  // clicar no cartão abre a folha (importa na hora)
  d.querySelector('[data-nav="item/'+SO+'"]').click(); await sleep(3000);
  chk(w.location.hash==='#item/'+SO&&!!d.getElementById('it-editar')&&!/não encontrado/i.test(txt('.content.on')),'abrir a folha só no site deveria abrir a página dela com o botão Editar, não "não encontrado": '+txt('.content.on').slice(0,100));
  r=await J(adm,'/api/itens/'+SO); chk(r.s===200,'a folha deveria agora existir no catálogo: '+r.s);
  // EDITA como as outras
  await w.editarItem(SO); await sleep(600); const ti=d.getElementById('ei-titulo'); ti.value='Foto editada no painel'; ti.dispatchEvent(new w.Event('input',{bubbles:true})); await w.salvarItem(SO); await sleep(1800);
  r=await J(adm,'/api/itens/'+SO); chk(r.s===200&&r.b.item.titulo==='Foto editada no painel','a folha importada deveria salvar a edição: '+JSON.stringify(r.b&&r.b.item&&r.b.item.titulo));
  w.route_to('projeto/F002-P0002'); await sleep(2000);
  chk(!!d.getElementById('pd-importar')&&txt('#pd-importar').includes('1 folha(s)'),'depois de importar uma, o botão deveria contar 1: '+(d.getElementById('pd-importar')?txt('#pd-importar'):'(sem botão)'));
  okl.push('folha só no site: leitura recebe explicação sem importar; abrir importa e edita como as demais; botão do projeto conta certo'); }
// ---------- CATÁLOGO LOCAL × SITE (prévia e importação) ----------
r=await J(ope,'/api/importacao/previa'); chk(r.s===403,'operador vendo a prévia do importador: '+r.s);
r=await J(adm,'/api/importacao/previa'); chk(r.s===200&&r.b.itens_novos===1&&r.b.projetos_novos===0,'prévia do seed deveria ter exatamente 1 item novo: '+JSON.stringify(r.b).slice(0,120));
w.route_to('estacoes'); await sleep(3000);
chk(!!d.getElementById('imp-painel')&&!!d.getElementById('imp-ver'),'painel "Catálogo local × site" ou botão não aparece para master');
await w.previaImportacao(); await sleep(1800);
chk(txt('#imp-corpo').includes('Itens no painel × no site')&&txt('#imp-corpo').includes('Entrariam'),'prévia não renderizou: '+txt('#imp-corpo').slice(0,90));
chk(!!d.getElementById('imp-exec')&&txt('#imp-exec').includes('1 item'),'botão de importar deveria mostrar "1 item(ns)": '+txt('#imp-exec'));
chk(txt('#imp-corpo').includes('F002-P0002-1977-S01-D00001'),'o item novo deveria estar listado');
await w.executarImportacao(); await sleep(2500);
r=await J(adm,'/api/itens/F002-P0002-1977-S01-D00001'); chk(r.s===200,'item importado deveria existir no painel: '+r.s);
chk(!d.getElementById('imp-exec'),'depois de importar não deveria sobrar botão de importar');
okl.push('importação: prévia, botão com os números certos, importou 1 item e a prévia zerou');

// ---------- PUBLICAÇÃO: checklist antes de clicar + resultado que FICA na tela ----------
w.route_to('projeto/F026-P0001'); await sleep(1800);
chk(!!d.getElementById('pd-pub-corpo')&&/Situação:\s*(não publicado|rascunho)/.test(txt('#pd-pub')),'painel "Publicação" não apareceu com a situação: '+txt('#pd-pub').slice(0,80));
const faltam=[...d.querySelectorAll('#pd-pub .chk.falta')].map(e=>e.textContent);
chk(faltam.length===2&&faltam.some(t=>t.includes('Direitos do fundo F026'))&&faltam.some(t=>t.includes('autorizado para publicação')),'checklist deveria mostrar exatamente 2 pendências (direitos e autorização): '+faltam.length);
chk(!!d.querySelector('#pd-pub .chk.falta button')&&txt('#pd-pub').includes('Definir direitos do fundo')&&txt('#pd-pub').includes('Autorizar publicação'),'cada pendência deveria ter o botão que a resolve');
const bp=d.getElementById('pd-publicar'); chk(bp&&bp.disabled&&/pendências/.test(bp.title),'botão Publicar deveria estar desabilitado dizendo por quê');
chk(!d.querySelector('.dethdr #pd-publicar'),'o botão Publicar não deveria mais ficar no cabeçalho (escondia o porquê)');
chk(txt('#pd-pub').includes('Sem autoria divergente nem erros bloqueantes'),'checklist deveria listar também o que JÁ está ok');
// força o clique (como se o botão estivesse ativo): o erro vira um painel que FICA, com tudo o que falta e os botões
await w.publicarProjeto('F026-P0001','publicar'); await sleep(1800);
chk(txt('#d-title').includes('Não foi possível publicar'),'recusa deveria abrir painel fixo "Não foi possível publicar": '+txt('#d-title'));
chk(txt('#d-body').includes('Direitos do fundo')&&txt('#d-body').includes('não foi autorizado'),'o painel deveria trazer TODAS as razões, não só a primeira');
chk(d.querySelectorAll('#d-body .chk.falta').length===2&&d.querySelectorAll('#d-body .chk.falta button').length===2,'o painel de erro deveria listar o que falta COM botões');
await sleep(3500); chk(w.eval('mainEl').classList.contains('with-drawer'),'o resultado sumiu sozinho (como o balão de 2,6 s)');
d.querySelector('#d-body .chk.falta button').click(); await sleep(1200);
chk(txt('#d-title').includes('Direitos e licença'),'o botão "Definir direitos do fundo" deveria abrir a edição de direitos: '+txt('#d-title')); w.closeDrawer(true);
// satisfaz os requisitos pela API e confere que o painel libera
r=await J(adm,'/api/fundos/F026/direitos',{method:'PUT',body:JSON.stringify({situacao:'autorizado',titular:'Família teste',documento_autorizacao:'Termo 001'})}); chk(r.s===200,'não consegui autorizar direitos no teste: '+r.s);
r=await J(adm,'/api/projetos/F026-P0001',{method:'PATCH',body:JSON.stringify({autorizado_site:true})}); chk(r.s===200,'não consegui autorizar o projeto no teste: '+r.s+' '+JSON.stringify(r.b).slice(0,80));
await w.carregarPublicacao('F026-P0001'); await sleep(900);
chk(d.querySelectorAll('#pd-pub .chk.falta').length===0&&d.getElementById('pd-publicar')&&!d.getElementById('pd-publicar').disabled,'com os requisitos cumpridos o botão Publicar deveria ficar ativo');
// WordPress sem credencial neste ambiente: o erro tem que ser EXPLICADO e FICAR na tela
await w.publicarProjeto('F026-P0001','publicar'); await sleep(1800);
chk(txt('#d-title').includes('Não foi possível publicar')&&txt('#d-body').includes('WordPress')&&txt('#d-body').includes('Configurações'),'sem credencial do WordPress deveria explicar e apontar Configurações: '+txt('#d-body').slice(0,120));
w.closeDrawer(true);
// fundo inteiro sem direitos: o erro vira painel fixo com o botão que resolve (caso real do F001)
await w.statusFundoSite('F003','no_ar'); await sleep(1800);
chk(txt('#d-title').includes('Não foi possível publicar o fundo')&&txt('#d-body').includes('F003')&&txt('#d-body').includes('Direitos do fundo')&&txt('#d-body').includes('Definir direitos do fundo'),'fundo sem direitos deveria abrir painel fixo com o botão: '+txt('#d-title')+' | '+txt('#d-body').slice(0,100)); w.closeDrawer(true);
okl.push('publicação: checklist antes de clicar, erro com todas as razões e botões, resultado fixo, WordPress sem credencial explicado');
// rotas inválidas / deep link
w.location.hash='#projeto/F999-P9999'; await sleep(1000); chk(!/undefined|NaN/.test(txt('.content.on')),'rota de projeto inexistente mostra lixo: '+txt('.content.on').slice(0,80)); okl.push('deep link inexistente: "'+txt('.content.on').slice(0,60)+'"');
w.location.hash='#rota-que-nao-existe'; await sleep(600); okl.push('rota inválida: "'+txt('.content.on').slice(0,60)+'"');
console.log('\n=== OK ==='); okl.forEach(x=>console.log(' ✓',x));
console.log('\n=== PROBLEMAS ('+[...new Set(problems)].length+') ==='); [...new Set(problems)].forEach(x=>console.log(' ✗',x));
process.exit(0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
