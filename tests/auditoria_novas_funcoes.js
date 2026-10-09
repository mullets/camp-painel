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
  dl.window.route_to('item/'+IT); await sleep(1200); chk(!dl.window.document.getElementById('it-editar'),'usuário de LEITURA vê o botão Editar'); okl.push('usuário de leitura não vê o botão Editar'); dl.window.route_to('painel'); await sleep(2500); chk(!!dl.window.document.getElementById('qnap-card')&&!dl.window.document.getElementById('qnap-atualizar'),'leitura deveria ver o cartão do QNAP SEM o botão Atualizar agora'); dl.window.route_to('fundo/F003'); await sleep(2200); chk(!!dl.window.document.getElementById('fd-guia')&&!dl.window.document.querySelector('#fd-guia .chk button'),'leitura deveria ver o guia do fundo SEM botões de ação'); dl.window.route_to('projeto/F026-P0001'); await sleep(1800); chk(!!dl.window.document.getElementById('pd-pub')&&!dl.window.document.getElementById('pd-publicar')&&!dl.window.document.querySelector('#pd-pub .chk button'),'leitura deveria ver o checklist mas NÃO os botões de publicar/resolver'); dl.window.route_to('estacoes'); await sleep(3000); chk(!!dl.window.document.getElementById('imp-painel')&&!dl.window.document.getElementById('imp-ver'),'leitura deveria ver o painel de importação mas NÃO o botão "Ver o que está faltando"'); chk(!!dl.window.document.getElementById('bk-painel')&&!dl.window.document.getElementById('bk-agora'),'leitura deveria VER o painel de backup mas NÃO o botão "Fazer backup agora"'); dl.window.close(); }

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
w.route_to('projeto/F003-P0001'); await sleep(1500);
chk([...d.querySelectorAll('#v-projeto a')].some(a=>a.href==='https://camp.arq.br/acervo/projetos/f003-p0001-slug-real-do-plugin/'),'o link deveria usar o endereço REAL da página (do espelho do site), não o montado: '+[...d.querySelectorAll('#v-projeto a')].map(a=>a.href).filter(h=>/acervo\/projetos/.test(h)).join(' | '));
w.route_to('projeto/F001-P0001'); await sleep(1500);
chk(!txt('#v-projeto').includes('Ver página pública')&&txt('#v-projeto').includes('Abrir no site (não publicado)'),'página real em RASCUNHO no site não pode oferecer "Ver página pública": '+txt('#v-projeto .act').slice(0,100));
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
// QNAP: a mensagem diz O QUE é e o que fazer (antes: "Problema na infraestrutura")
w.route_to('painel'); await sleep(2500);
chk(txt('#v-painel .dash-state').includes('QNAP não está conectado a este servidor')&&!/infraestrutura/i.test(txt('#v-painel .dash-state')),'o painel inicial deveria dizer exatamente o que está errado: "'+txt('#v-painel .dash-state')+'"');
chk(txt('#system-banner').includes('QNAP não está conectado a este servidor'),'o banner deveria dizer que o QNAP não está conectado a este servidor: "'+txt('#system-banner').slice(0,100)+'"');
w.route_to('estacoes'); await sleep(2800);
chk(!!d.getElementById('qnap-ajuda')&&txt('#qnap-ajuda').includes('diagnostico_qnap.sh')&&txt('#qnap-ajuda').includes('montar_qnap.sh')&&txt('#qnap-ajuda').includes('Macs'),'a tela Estações deveria explicar como conectar o QNAP (com os dois comandos)');
// cartão do QNAP no painel inicial: informações úteis lidas do que o coletor guardou
w.route_to('painel'); await sleep(2800);
{ const c=txt('#qnap-card');
  chk(/11\.?880 GB/.test(c)&&/de 20\.?000 GB/.test(c),'o cartão deveria mostrar o espaço livre/total: '+c.slice(0,90));
  chk(!!d.querySelector('#qnap-card svg.qnap-spark'),'o cartão deveria ter o gráfico de espaço dos últimos 7 dias');
  chk(/Tendência/.test(c)&&/GB\/dia/.test(c)&&/enche em ~\d/.test(c),'o cartão deveria mostrar a tendência e quantos dias até encher: '+c.slice(0,200));
  chk(/Último material/.test(c)&&/há 3 h/.test(c)&&c.includes('F002-P0002-IGREJA/lote-12'),'o cartão deveria mostrar o último material recebido (há 3 h + nome)');
  chk(/Entrada bruta/.test(c)&&/14 pasta\(s\)/.test(c)&&/2 parada\(s\) há mais de 3 dias/.test(c),'o cartão deveria mostrar a entrada bruta e as pastas paradas');
  chk(/Lotes prontos/.test(c)&&/230/.test(c)&&/Resposta/.test(c)&&/42 ms/.test(c),'o cartão deveria mostrar os lotes prontos e a resposta em ms');
  chk(/Atualizado há \d+ min/.test(c),'o cartão deveria dizer há quanto tempo foi atualizado: '+c.slice(-80));
  chk(!!d.getElementById('qnap-atualizar'),'o master deveria ver o botão "Atualizar agora"');
  // atualizar agora: pede a coleta, espera e recarrega o cartão
  d.getElementById('qnap-atualizar').click(); await sleep(7000);
  chk(/Atualizado (agora há pouco|há 0 min)/.test(txt('#qnap-card'))&&!!d.getElementById('qnap-atualizar')&&!d.getElementById('qnap-atualizar').disabled,'depois de "Atualizar agora" o cartão deveria mostrar a coleta nova: '+txt('#qnap-card').slice(-90)); }
// ---------- USO DO ACERVO (pedidos de download do formulário do site) ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('uso'); await sleep(2500);
  const R=(await J(adm,'/api/uso/resumo')).b, L=(await J(adm,'/api/uso')).b, linhas=()=>d.querySelectorAll('#us-body tr.us-row').length;
  chk(!!d.querySelector('#nav [data-v="uso"]')&&txt('#nav [data-v="uso"] kbd')==='U','o menu deveria ter "Uso do acervo" com o atalho U');
  { let el=d.querySelector('#nav [data-v="uso"]').previousElementSibling; while(el&&!el.classList.contains('grp'))el=el.previousElementSibling; chk(el&&el.textContent.trim()==='Acervo','"Uso do acervo" deveria ficar no grupo ACERVO do menu, está em "'+(el&&el.textContent.trim())+'"'); }
  chk(d.querySelectorAll('#us-kpis .hoje-kpi').length===4&&txt('#us-kpis').includes('pedidos de download')&&txt('#us-kpis').includes(String(R.total)),'os 4 números do uso deveriam bater com a API (total '+R.total+'): "'+txt('#us-kpis').slice(0,120)+'"');
  chk(R.total>0&&linhas()===Math.min(50,L.total),'a tabela deveria ter '+Math.min(50,L.total)+' linhas, tem '+linhas());
  const D0=(await J(adm,'/api/uso/'+L.itens[0].id)).b;
  chk(!txt('#us-body').includes(D0.telefone),'o telefone não deveria aparecer na lista (só no detalhe)');
  chk(/Nenhuma coleta ainda|Última coleta/.test(txt('#us-coleta')),'a linha da última coleta deveria aparecer: "'+txt('#us-coleta')+'"');
  d.querySelector('#us-body tr.us-row').click(); await sleep(1500);
  chk(txt('#d-title').includes('Pedido de download')&&txt('#d-body').includes(D0.telefone)&&txt('#d-body').includes('Resposta completa do formulário')&&!!d.querySelector('#d-body [data-uso-acao="apagar-um"]')&&!!d.querySelector('#d-body [data-uso-acao="email"]'),'o detalhe deveria mostrar o telefone, a resposta completa e os botões de apagar e de e-mail: "'+txt('#d-body').slice(0,120)+'"');
  d.querySelector('#d-body [data-uso-acao="filtrar"]').click(); await sleep(1800);
  const T=(await J(adm,'/api/uso?q='+encodeURIComponent(D0.email))).b;
  chk(d.getElementById('us-q').value===D0.email&&T.total>=1&&linhas()===Math.min(50,T.total),'"Ver tudo desta pessoa" deveria filtrar pelo e-mail ('+T.total+' esperado, '+linhas()+' na tela)');
  d.getElementById('us-q').value=''; w.usoFiltrou(); await sleep(1200);
  w.usoAba('pessoas'); await sleep(1800); const PP=(await J(adm,'/api/uso/pessoas')).b;
  chk(/Instituição/.test(txt('#us-head'))&&/Pedidos/.test(txt('#us-head'))&&linhas()===Math.min(50,PP.total),'a aba Pessoas deveria ter '+Math.min(50,PP.total)+' linhas, tem '+linhas());
  w.usoAba('materiais'); await sleep(1800); const MM=(await J(adm,'/api/uso/materiais')).b;
  chk(/Material/.test(txt('#us-head'))&&MM.total>0&&linhas()===Math.min(50,MM.total),'a aba Materiais deveria ter '+Math.min(50,MM.total)+' linhas, tem '+linhas());
  const cod=MM.itens[0].codigo; d.querySelector('#us-body tr.us-row').click(); await sleep(1800);
  chk(d.getElementById('us-q').value===cod&&d.querySelector('#us-tabs button.on').dataset.aba==='downloads'&&linhas()>=1,'clicar num material deveria listar os pedidos dele');
  d.getElementById('us-q').value=''; const uso1=R.usos[0].uso; d.getElementById('us-uso').value=uso1; w.usoFiltrou(); await sleep(1500);
  const FU=(await J(adm,'/api/uso?uso='+encodeURIComponent(uso1))).b;
  chk(linhas()===Math.min(50,FU.total)&&/resultado/.test(txt('#us-cnt')),'o filtro por uso ('+uso1+') deveria bater com a API: '+FU.total+' esperado, '+linhas()+' na tela');
  d.getElementById('us-uso').value=''; d.getElementById('us-q').value='zzzz-nada-assim'; w.usoFiltrou(); await sleep(1300);
  chk(/Nada com esses filtros/.test(txt('#us-body')),'sem resultado deveria dizer "Nada com esses filtros"'); d.getElementById('us-q').value=''; w.usoFiltrou(); await sleep(900);
  w.__baixou=[]; w.exportarUsoCSV(); chk((w.__baixou||[]).some(x=>/^camp-uso-pedidos-\d{4}-\d{2}-\d{2}\.csv$/.test(x)),'"Exportar CSV" deveria gerar o download camp-uso-pedidos-AAAA-MM-DD.csv: '+JSON.stringify(w.__baixou));
  d.getElementById('us-q').value='abc'; chk(/q=abc/.test(w.usoQS()),'a exportação deveria levar os filtros ativos'); d.getElementById('us-q').value='';
  await w.puxarUso(false); await sleep(900);
  chk(!d.getElementById('us-atualizar').disabled,'o botão "Atualizar agora" deveria voltar a ficar ativo'); chk(/Application Password|site|coleta/i.test(txt('#toast')),'sem o site configurado deveria avisar com clareza: "'+txt('#toast')+'"');
  w.usoAba('downloads'); await sleep(1300); await w.abrirUsoDetalhe(D0.id); await sleep(1000);
  d.querySelector('#d-body [data-uso-acao="anonimizar"]').click(); await sleep(2200);
  const R2=(await J(adm,'/api/uso/resumo')).b, T2=(await J(adm,'/api/uso?q='+encodeURIComponent(D0.email))).b;
  chk(R2.anonimizadas>0&&T2.total===0&&R2.total===R.total,'apagar a pessoa deveria anonimizar os pedidos dela sem mudar o total: '+JSON.stringify({anon:R2.anonimizadas,depois:T2.total,total:[R.total,R2.total]}));
  chk(!txt('#v-uso').includes(D0.email)&&/dados pessoais apagados/.test(txt('#us-body')),'a tela não deveria mais mostrar o e-mail com dados pessoais removidos e deveria dizer "dados pessoais apagados"');
  // ---------- seleção, apagar de verdade, exportar por aba e e-mail para uma pessoa ----------
  w.closeDrawer(true); w.usoAba('downloads'); d.getElementById('us-q').value=''; d.getElementById('us-uso').value=''; w.usoFiltrou(); await sleep(1600);
  const caixas=()=>[...d.querySelectorAll('#us-body input[data-uso-sel]')], drawerAberto=()=>w.eval("mainEl.classList.contains('with-drawer')"), total=async()=>(await J(adm,'/api/uso/resumo')).b.total;
  chk(caixas().length>=6,'cada linha de pedido deveria ter uma caixinha de seleção ('+caixas().length+')');
  caixas()[0].click(); caixas()[1].click(); await sleep(250);
  chk(!d.getElementById('us-selbar').hidden&&/2 selecionado/.test(txt('#us-seln'))&&!drawerAberto(),'marcar 2 caixinhas deveria mostrar "2 selecionado(s)" SEM abrir o detalhe: "'+txt('#us-seln')+'"');
  d.getElementById('us-todos').click(); await sleep(250);
  chk(new RegExp('^'+caixas().length+' selecionado').test(txt('#us-seln')),'"selecionar todos desta página" deveria marcar todas ('+caixas().length+'): "'+txt('#us-seln')+'"');
  w.__baixou=[]; w.exportarUsoCSV(true); chk((w.__baixou||[]).some(x=>/^camp-uso-pedidos-selecionados-\d{4}-\d{2}-\d{2}\.csv$/.test(x)),'"Exportar selecionados" deveria gerar camp-uso-pedidos-selecionados-AAAA-MM-DD.csv: '+JSON.stringify(w.__baixou));
  d.getElementById('us-todos').click(); await sleep(200); chk(d.getElementById('us-selbar').hidden,'desmarcar tudo deveria esconder a barra de seleção');
  for(const aba of ['pessoas','materiais']){ w.usoAba(aba); await sleep(1300); w.__baixou=[]; w.exportarUsoCSV(); chk((w.__baixou||[]).some(x=>x.startsWith('camp-uso-'+aba+'-')),'a exportação da aba '+aba+' deveria se chamar camp-uso-'+aba+'-...: '+JSON.stringify(w.__baixou)); }
  w.usoAba('downloads'); await sleep(1500);
  let t0=await total(); caixas()[0].click(); caixas()[1].click(); await sleep(200); w.confirm=()=>true; d.querySelector('#us-selbar .us-apagar').click(); await sleep(2300);
  chk((await total())===t0-2&&d.getElementById('us-selbar').hidden,'apagar 2 selecionados deveria baixar o total em 2 ('+t0+' para '+(await total())+') e esconder a barra');
  t0=await total(); d.querySelector('#us-body tr.us-row').click(); await sleep(1500); d.querySelector('#d-body [data-uso-acao="apagar-um"]').click(); await sleep(2300);
  chk((await total())===t0-1&&!drawerAberto(),'"Apagar este pedido" deveria baixar o total em 1 e fechar o painel lateral');
  d.querySelector('#us-body tr.us-row').click(); await sleep(1500); const emailAlvo=(await J(adm,'/api/uso/'+d.querySelector('#d-body [data-uso-acao="apagar-um"]').dataset.usoValor)).b.email; const nPessoa=(await J(adm,'/api/uso?q='+encodeURIComponent(emailAlvo))).b.total;
  d.querySelector('#d-body [data-uso-acao="apagar-pessoa"]').click(); await sleep(2300);
  chk(nPessoa>=1&&(await J(adm,'/api/uso?q='+encodeURIComponent(emailAlvo))).b.total===0,'"Apagar todos desta pessoa" deveria remover os '+nPessoa+' pedidos dela');
  const usoX=(await J(adm,'/api/uso/resumo')).b.usos[0].uso, nX=(await J(adm,'/api/uso?uso='+encodeURIComponent(usoX))).b.total; t0=await total();
  d.getElementById('us-uso').value=usoX; w.usoFiltrou(); await sleep(1600); const bf=d.getElementById('us-apagar-filtro');
  chk(!bf.hidden&&bf.textContent.includes(String(nX)),'com um filtro ativo deveria aparecer "Apagar os '+nX+' resultados": "'+bf.textContent+'" (oculto='+bf.hidden+')');
  bf.click(); await sleep(2300); chk((await total())===t0-nX&&bf.hidden,'apagar os resultados do filtro deveria baixar o total em '+nX+' e esconder o botão ('+t0+' para '+(await total())+')');
  d.getElementById('us-uso').value=''; w.usoFiltrou(); await sleep(1200);
  // e-mail para UMA pessoa (neste banco o SMTP NÃO está configurado: o envio fica desativado e sobra o "Abrir no meu e-mail")
  d.querySelector('#us-body tr.us-row').click(); await sleep(1500); const detalheEmail=(await J(adm,'/api/uso/'+d.querySelector('#d-body [data-uso-acao="email"]').dataset.usoValor)).b;
  d.querySelector('#d-body [data-uso-acao="email"]').click(); await sleep(1500);
  chk(txt('#d-title').includes('E-mail para uma pessoa')&&txt('#d-body').includes(detalheEmail.email)&&/SÓ para/.test(txt('#d-body')),'a tela de e-mail deveria dizer que vai SÓ para '+detalheEmail.email);
  chk(d.getElementById('us-env').disabled&&/envio não configurado/.test(txt('#d-body')),'sem SMTP o botão Enviar deveria ficar desativado, com o aviso "envio não configurado"');
  chk(!/\{nome\}|\{material\}|\{data\}/.test(d.getElementById('us-ass').value+d.getElementById('us-msg').value)&&d.getElementById('us-msg').value.includes(detalheEmail.nome)&&d.getElementById('us-ass').value.length>3,'o texto padrão deveria vir preenchido com o nome e o material (sem {nome}): "'+d.getElementById('us-msg').value.slice(0,90)+'"');
  d.getElementById('us-ass').value='Assunto com acento: ção'; d.getElementById('us-msg').value='Linha 1\nLinha 2 & mais?'; w.__baixou=[]; d.querySelector('#d-body [data-uso-acao="mailto"]').click();
  chk((w.__baixou||[]).some(x=>x.startsWith('mailto:'+detalheEmail.email)&&x.includes('subject=Assunto%20com%20acento%3A%20%C3%A7%C3%A3o')&&x.includes('body=Linha%201%0ALinha%202%20%26%20mais%3F')),'"Abrir no meu e-mail" deveria montar um mailto: com assunto e texto codificados: '+JSON.stringify(w.__baixou));
  d.querySelector('#d-body [data-uso-acao="detalhe"]').click(); await sleep(1300); chk(txt('#d-title').includes('Pedido de download'),'"Voltar" deveria reabrir o detalhe do pedido');
  w.closeDrawer(true); }
// ---------- REVISÃO DO LOTE: importar o pacote do CAMP Vision, conferir, corrigir e aprovar ----------
{ w.confirm=()=>true; w.closeDrawer(true); const pc='F003-P9002', D=n=>pc+'-1972-S01-D0000'+n, loteId=(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].id;
  w.route_to('projeto/'+pc); await sleep(3500);
  chk(/Revisão do lote/.test(txt('#pj-revisao'))&&/aguardando importação/.test(txt('#pj-revisao'))&&!!d.querySelector('#pj-revisao [data-rev-lote="importar"]'),'o projeto com pacote e sem folhas importadas deveria oferecer "Importar as folhas do lote": "'+txt('#pj-revisao').slice(0,120)+'"');
  chk(/o CAMP Vision gravou 3 documento/.test(txt('#pj-revisao')),'deveria dizer quantos documentos o CAMP Vision gravou');
  d.querySelector('#pj-revisao [data-rev-lote="importar"]').click(); await sleep(3800);
  const dt=(await J(adm,'/api/projetos/'+pc+'/detalhe')).b;
  chk(dt.itens.length===3&&dt.itens.every(i=>i.revisao==='pendente'&&i.lote_id===loteId),'importar deveria criar 3 folhas pendentes ligadas ao lote: '+dt.itens.length);
  chk(/3 a conferir/.test(txt('#pj-revisao'))&&/Faltam conferir 3 folha/.test(txt('#pj-revisao'))&&d.querySelector('#pj-revisao [data-rev-lote="aprovar"]').disabled===true,'depois de importar: 3 a conferir e "Aprovar" bloqueado com o motivo: "'+txt('#pj-revisao').slice(0,160)+'"');
  const cards=[...d.querySelectorAll('.thumb')].filter(x=>x.textContent.includes(pc));
  chk(cards.length===3&&cards.every(x=>/a conferir/.test(x.textContent)&&!!x.querySelector('[data-rev-abrir]')),'cada cartão de folha deveria ter o selo "a conferir" e o botão Revisar: '+cards.length);
  d.querySelector('[data-rev-lote="conferir"]').click(); await sleep(3200);
  chk((await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].itens.conferida===0,'conferir em lote não deveria marcar folha com pendência apontada pelo CAMP Vision (todas as 3 têm)');
  w.abrirRevisaoItem(D(3)); await sleep(1800);
  chk(/O que o CAMP Vision leu/.test(txt('#d-body'))&&/orientação incerta/.test(txt('#d-body'))&&!!d.querySelector('#rv-titulo')&&!!d.querySelector('#rv-tipo')&&!!d.querySelector('[data-rev-item="conferida"]'),'a janela de revisão deveria mostrar o que o CAMP Vision apontou e os campos: "'+txt('#d-body').slice(0,140)+'"');
  d.querySelector('[data-rev-item="conferida"]').click(); await sleep(3200);
  chk((await J(adm,'/api/itens/'+D(3)+'/edicao')).b.codigo===D(3)&&(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].itens.conferida===1,'"Está certo" deveria marcar a folha como conferida');
  w.abrirRevisaoItem(D(1)); await sleep(1800); d.getElementById('rv-titulo').value='Planta corrigida no teste'; d.getElementById('rv-escala').value='1:75';
  d.querySelector('[data-rev-item="corrigida"]').click(); await sleep(3400);
  const e1=(await J(adm,'/api/itens/'+D(1)+'/edicao')).b.local, r1=(await J(adm,'/api/projetos/'+pc+'/detalhe')).b.itens.find(i=>i.codigo===D(1));
  chk(e1.titulo==='Planta corrigida no teste'&&e1.escala==='1:75'&&r1.revisao==='corrigida'&&r1.revisado_por,'"Salvar correção" deveria gravar os campos E marcar como corrigida: '+JSON.stringify({t:e1.titulo,e:e1.escala,r:r1.revisao}));
  w.abrirRevisaoItem(D(2)); await sleep(1800); d.querySelector('[data-rev-item="conferida"]').click(); await sleep(3200);
  chk(/Aprovar o lote/.test(txt('#pj-revisao'))&&d.querySelector('#pj-revisao [data-rev-lote="aprovar"]').disabled===false&&/pronta para aprovar/.test(txt('#pj-revisao')),'com todas revisadas, "Aprovar o lote" deveria liberar: "'+txt('#pj-revisao').slice(0,160)+'"');
  d.querySelector('#pj-revisao [data-rev-lote="aprovar"]').click(); await sleep(3600);
  const ap=(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0];
  chk(!!ap.aprovado_em&&ap.etapa==='revisao'&&/aprovado por/.test(txt('#pj-revisao'))&&!!d.querySelector('#pj-revisao [data-rev-lote="reabrir"]'),'aprovar deveria registrar quem/quando, manter a etapa e oferecer "Reabrir a revisão": '+JSON.stringify({a:ap.aprovado_em,e:ap.etapa}));
  d.querySelector('#pj-revisao [data-rev-lote="reabrir"]').click(); await sleep(3400);
  chk(!(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].aprovado_em,'reabrir deveria limpar a aprovação'); }
// ---------- DECISÕES: o painel pergunta antes de criar projeto parecido ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('painel'); await sleep(3500);
  const drawerAberto=()=>w.eval("mainEl.classList.contains('with-drawer')"), dl=(await J(adm,'/api/decisoes')).b;
  chk(dl.total>=2,'a semente deveria ter 2 decisões pendentes: '+dl.total);
  const li=[...d.querySelectorAll('#v-painel .action-list li')].filter(x=>/Projeto parecido/.test(x.textContent));
  chk(li.length>=1&&!!li[0].querySelector('button.pri')&&/Decidir/.test(li[0].textContent),'o "Precisa de atenção" deveria listar a decisão com o botão Decidir ('+li.length+')');
  chk(/CAMP Vision está esperando/.test(txt('#v-painel .action-card')),'deveria avisar que o CAMP Vision está esperando');
  chk(/Decisões esperando/.test(txt('#v-painel .hoje-acoes')),'"Por onde começar" deveria incluir as decisões nas pendências: "'+txt('#v-painel .hoje-acoes').slice(0,120)+'"');
  const id1=dl.itens[0].id, id2=dl.itens[1].id; li[0].querySelector('button.pri').click(); await sleep(1600);
  chk(txt('#d-title').includes('Projeto parecido: é o mesmo?')&&/O que chegou/.test(txt('#d-body'))&&/Já existe no fundo/.test(txt('#d-body'))&&/está esperando a sua resposta/.test(txt('#d-body')),'a janela deveria mostrar o que chegou, o que já existe e que o CAMP Vision espera: "'+txt('#d-body').slice(0,110)+'"');
  chk(!!d.querySelector('#d-body [data-dec-acao="mesmo"]')&&!!d.querySelector('#d-body [data-dec-acao="novo"]')&&!!d.querySelector('#d-body .dec-cand')&&/folha\(s\) no painel/.test(txt('#d-body'))&&/mesmo nome/.test(txt('#d-body')),'deveria ter os dois caminhos e, em cada candidato, os motivos');
  const nProj0=(await J(adm,'/api/painel')).b.projetos.total;
  d.querySelector('#d-body [data-dec-acao="mesmo"]').click(); await sleep(2600);
  const r1=(await J(adm,'/api/decisoes/'+id1)).b;
  chk(r1.situacao==='resolvida'&&r1.resolucao==='mesmo'&&(await J(adm,'/api/painel')).b.projetos.total===nProj0&&!drawerAberto(),'"É o mesmo" deveria resolver SEM criar projeto e fechar a janela: '+JSON.stringify({s:r1.situacao,r:r1.resolucao}));
  w.abrirDecisao(id2); await sleep(1600); d.querySelector('#d-body [data-dec-acao="novo"]').click(); await sleep(2600);
  const r2=(await J(adm,'/api/decisoes/'+id2)).b;
  chk(r2.situacao==='resolvida'&&r2.resolucao==='novo'&&/^F026-P\d{4}$/.test(r2.projeto_codigo)&&(await J(adm,'/api/painel')).b.projetos.total===nProj0+1,'"É outro projeto" deveria criar o novo: '+JSON.stringify(r2).slice(0,140));
  w.abrirDecisao(id1); await sleep(1500); chk(/Decidido/.test(txt('#d-body'))&&/Era o mesmo projeto/.test(txt('#d-body'))&&!d.querySelector('#d-body [data-dec-acao]'),'uma decisão já resolvida deveria aparecer só para leitura, sem botões'); w.closeDrawer(true);
  w.route_to('painel'); await sleep(2800); chk(!/Projeto parecido/.test(txt('#v-painel .action-card')),'depois de decidir, o "Precisa de atenção" não deveria mais listar as decisões');
  // novo projeto à mão: o painel avisa dos parecidos antes de criar
  const tit=(await J(adm,'/api/projetos/F026-P0001/detalhe')).b.projeto.titulo, nP=(await J(adm,'/api/painel')).b.projetos.total;
  w.openModal('m-proj'); await sleep(600); d.getElementById('np-fundo').value='F026'; d.getElementById('np-titulo').value=tit; await w.criarProjeto(); await sleep(1500);
  chk(/Já existe projeto parecido neste fundo/.test(txt('#np-parecidos'))&&/F026-P0001/.test(txt('#np-parecidos'))&&/É um projeto novo: criar mesmo assim/.test(txt('#np-parecidos')),'o modal de novo projeto deveria avisar do parecido (F026-P0001): "'+txt('#np-parecidos').slice(0,120)+'"');
  chk((await J(adm,'/api/painel')).b.projetos.total===nP,'avisar NÃO pode criar o projeto');
  d.querySelector('#np-parecidos [data-np-abrir]').click(); await sleep(1500); chk(/projeto\/F026-P0001/.test(w.location.hash),'"Abrir este" deveria levar ao projeto parecido: '+w.location.hash); w.closeModal(); }
// ---------- FOLHAS NO QNAP NA PÁGINA DO PROJETO ----------
{ w.closeDrawer(true); w.route_to('projeto/F026-P0001'); await sleep(3500);
  const fq=(await J(adm,'/api/projetos/F026-P0001/folhas-qnap')).b, lt=fq.lotes.find(l=>l.existe), qf=()=>d.querySelectorAll('#pj-qnap .qf');
  chk(!!lt&&lt.fora_do_painel===3&&lt.documentos.length===3,'a API deveria listar 3 documentos do lote de teste (JPG e TIF do mesmo código = 1): '+JSON.stringify(lt&&{t:lt.total,f:lt.fora_do_painel}));
  chk(/Encontradas no QNAP, ainda não catalogadas no painel/.test(txt('#pj-qnap'))&&qf().length===3,'a página do projeto deveria mostrar o painel "Encontradas no QNAP" com 3 documentos: '+qf().length+' ('+txt('#pj-qnap').slice(0,100)+')');
  chk(/3 documento\(s\)/.test(txt('#pj-qnap'))&&/F026-P0001-1970-S01-D90001/.test(txt('#pj-qnap'))&&/JPG · TIF/.test(txt('#pj-qnap')),'cada documento deveria mostrar o código e os formatos (JPG · TIF)');
  const im=[...d.querySelectorAll('#pj-qnap .qf img')];
  chk(im.length===3&&im.every(x=>x.getAttribute('src').startsWith('/api/projetos/F026-P0001/folhas-qnap/arquivo?lote=')&&x.getAttribute('src').includes('caminho=')),'as miniaturas deveriam vir do endpoint de prévia do projeto');
  chk(/ainda não viraram folhas do painel/.test(txt('#pj-qnap')),'o painel deveria dizer que ainda não viraram folhas e apontar a Revisão do lote');
  w.route_to('projeto/F023-P0011'); await sleep(3000);
  chk(d.querySelectorAll('#pj-qnap .qf').length===0&&!/Encontradas no QNAP/.test(txt('#pj-qnap')),'um projeto SEM lote no QNAP não deveria mostrar o painel'); }
// ---------- TOPO DO PAINEL, SELO, CARTÃO DO QNAP E DIVERGÊNCIAS ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('painel'); await sleep(3000);   // fecha qualquer painel lateral de testes anteriores (o painel protege edição pendente)
  const hj=(await J(adm,'/api/hoje')).b;
  chk(/pedem você hoje|Nada urgente hoje/.test(txt('#v-painel .hoje-frase')),'o topo deveria ter a frase do dia: "'+txt('#v-painel .hoje-frase')+'"');
  chk(!/Visão rápida da operação do acervo/.test(txt('#v-painel .dash-hero-main')),'a frase fixa antiga não deveria mais aparecer quando há dados do dia');
  chk(d.querySelectorAll('#v-painel .hoje-kpi').length===4&&/pendências/.test(txt('#v-painel .hoje-kpis'))&&/travados por direitos/.test(txt('#v-painel .hoje-kpis'))&&/prontos para publicar/.test(txt('#v-painel .hoje-kpis')),'o topo deveria ter os 4 números do dia');
  chk(new RegExp('prontos para publicar').test(txt('#v-painel .hoje-kpis'))&&txt('#v-painel .hoje-kpis').includes(String(hj.kpis.prontos.valor)),'o número de prontos para publicar deveria bater com a API ('+hj.kpis.prontos.valor+')');
  if(hj.kpis.prontos.valor===0) chk(/nenhum projeto foi autorizado ainda|nenhum passa em todos os requisitos/.test(txt('#v-painel .hoje-kpis')),'zero precisa de EXPLICAÇÃO ("nenhum projeto foi autorizado ainda"): '+txt('#v-painel .hoje-kpis').slice(0,260));
  const n=Math.min(3,hj.acoes.length+(txt('#v-painel .action-card .tag')&&0)); chk(d.querySelectorAll('#v-painel .hoje-acao').length>=Math.min(3,hj.acoes.length),'o topo deveria listar até 3 ações do dia: '+d.querySelectorAll('#v-painel .hoje-acao').length+' (API tem '+hj.acoes.length+')');
  chk(/Por onde começar|Tudo em dia/.test(txt('#v-painel .dash-hero-main')),'o topo deveria ter o título "Por onde começar"');
  // "Hoje no acervo": só o que é DE HOJE, com o dia anterior ao lado
  chk(/folhas trabalhadas hoje/.test(txt('#v-painel'))&&/projetos novos hoje/.test(txt('#v-painel'))&&/publicações hoje/.test(txt('#v-painel'))&&/pedidos e erros novos hoje/.test(txt('#v-painel'))&&/ontem: \d+/.test(txt('#v-painel')),'"Hoje no acervo" deveria mostrar só números de hoje, com "ontem: N"');
  chk(!/fundos publicados/.test(txt('#v-painel'))&&!/lotes prontos para revisão/.test(txt('#v-painel .kpi-grid')),'os totais gerais ("fundos publicados") não pertencem a "Hoje no acervo"');
  // divergências: o número leva a uma lista em português
  chk(/Divergências/.test(txt('#v-painel .site-card'))&&!!d.querySelector('#v-painel .site-card .lnk'),'o cartão do site deveria ter o link "ver o que são" nas divergências');
  d.querySelector('#v-painel .site-card .lnk').click(); await sleep(2500);
  chk(txt('#d-title').includes('Divergências entre o painel e o site')&&txt('#d-body').includes('Item do site sem código CAMP')&&txt('#d-body').includes('Fundo sem nenhuma folha no site'),'a lista de divergências deveria explicar cada tipo em português: título="'+txt('#d-title')+'" corpo="'+txt('#d-body').slice(0,80)+'"');
  chk(d.querySelector('#v-painel .site-card .lnk').tagName==='BUTTON','"ver o que são" deveria ser um botão (acessível por teclado), não um <a> sem href');
  chk(!/sem_codigo|fundo_inexistente|sem_itens_no_site|_fora_do_ar/.test(txt('#d-body')),'a lista não pode mostrar o código cru das divergências'); w.closeDrawer(true);
  // selo geral: o espaço do QNAP conta (função pura, testada com os números reais do painel)
  { const E=w.estadoGeral, base={q:{montado:true},site:{http:{ok:true}},pend:0};
    let r=E({...base,qi:{nivel_espaco:'critico',livre_pct:2.2,coleta:{livre_gb:28}}}); chk(r.geral==='bad'&&/QNAP quase cheio: 28 GB livres \(2,2%\)/.test(r.texto),'28 GB de 1.255 (2,2%) deveria deixar o selo VERMELHO e dizer o espaço: '+JSON.stringify(r));
    r=E({...base,qi:{nivel_espaco:'aviso',livre_pct:11.9,coleta:{livre_gb:150}}}); chk(r.geral==='warn'&&/QNAP com pouco espaço/.test(r.texto),'espaço em aviso deveria deixar o selo ÂMBAR: '+JSON.stringify(r));
    r=E({...base,qi:{nivel_espaco:'ok',livre_pct:60,coleta:{livre_gb:700}}}); chk(r.geral==='ok'&&r.texto==='Operação saudável','espaço ok = saudável');
    r=E({...base,pend:3,qi:{nivel_espaco:'ok',coleta:{livre_gb:700}}}); chk(r.geral==='warn'&&/3 pendência/.test(r.texto),'pendências = âmbar');
    r=E({q:{montado:false},site:{http:{ok:true}},pend:0,qi:{nivel_espaco:'critico',livre_pct:1,coleta:{livre_gb:5}}}); chk(r.geral==='bad'&&/não está conectado/.test(r.texto)&&!/quase cheio/.test(r.texto),'QNAP desconectado: não usa o espaço velho da última coleta: '+JSON.stringify(r)); }
  // cartão do QNAP: barra vermelha, aviso de cota e explicação dos zeros
  { const cfgv={entrada_caminho:'',prontos_caminho:'/mnt/qnap/acervos/Arquivos/100 - Scanners',dias_parado:3};
    let h=w.qnapInnerHTML({montado:true,livre_gb:28,total_gb:1255,uso_pct:98},{nivel_espaco:'critico',coleta:{prontos:0,prontos_pastas:5,prontos_existe:1,entrada_bruta:null,latencia_ms:2,coletado_em:'2026-01-01 00:00:00'},config:cfgv});
    chk(/<i class="critico"/.test(h)&&/quase cheio/.test(h)&&/cota/i.test(h),'o cartão crítico deveria ter barra vermelha, a etiqueta "quase cheio" e o aviso de cota');
    chk(/há 5 pasta\(s\), mas nenhuma com info_projeto\.json ou status\.json/.test(h),'"Lotes prontos 0" deveria explicar: há 5 pastas, mas nenhuma com info_projeto.json ou status.json');
    chk(/não configurada/.test(h)&&/definir/.test(h),'"Entrada bruta" sem caminho deveria dizer "não configurada" e oferecer "definir" ao admin');
    chk(/nenhum lote lido ainda/.test(h),'"Último material" sem dado deveria dizer "nenhum lote lido ainda", não só "—"');
    h=w.qnapInnerHTML({montado:true,livre_gb:700,total_gb:1255,uso_pct:44},{nivel_espaco:'ok',coleta:{prontos:0,prontos_pastas:0,prontos_existe:1,entrada_bruta:3,entrada_existe:1,latencia_ms:2,coletado_em:'2026-01-01 00:00:00'},config:{...cfgv,entrada_caminho:'/x'}});
    chk(/está vazia/.test(h)&&!/cota/i.test(h)&&!/class="critico"/.test(h),'espaço ok não mostra aviso de cota; pasta de lotes vazia é explicada');
    h=w.qnapInnerHTML({montado:true,livre_gb:700,total_gb:1255,uso_pct:44},{nivel_espaco:'ok',coleta:{prontos:0,prontos_existe:0,entrada_bruta:null,entrada_existe:0,latencia_ms:2,coletado_em:'2026-01-01 00:00:00'},config:{...cfgv,entrada_caminho:'/x/entrada'}});
    chk(/pasta do material pronto não existe/.test(h)&&/a pasta configurada não existe/.test(h),'pasta de lotes e de entrada que não existem deveriam ser ditas'); }
  // banner global
  w.atualizarBannerSistema({qnap:{montado:true,nivel_espaco:'critico',livre_gb:28,livre_pct:2.2},site:{http:{ok:true}}}); chk(/QNAP quase cheio \(28 GB livres, 2,2%\)/.test(txt('#system-banner')),'o banner global deveria avisar o QNAP quase cheio: "'+txt('#system-banner')+'"');
  w.atualizarBannerSistema({qnap:{montado:true,nivel_espaco:'ok'},site:{http:{ok:true}}}); }
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
const bp=d.getElementById('pd-publicar'); chk(bp&&bp.getAttribute('aria-disabled')==='true'&&!bp.disabled&&/pendências/.test(bp.title),'botão Publicar deveria estar apagado (aria-disabled, mas clicável) dizendo por quê');
let _conf=0;w.confirm=()=>{_conf++;return true}; bp.click(); await sleep(900);
chk(_conf===0&&/Por que não dá para publicar/.test(txt('#d-title'))&&/Faltam \d+ requisito/.test(txt('#d-body'))&&d.querySelectorAll('#d-body .chk.falta').length>=1&&d.querySelectorAll('#d-body .chk.ok').length===0,'clicar em Publicar sem os requisitos deveria EXPLICAR (janela só com o que falta), sem pedir confirmação: "'+txt('#d-body').slice(0,140)+'"'); w.closeDrawer(true);
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
chk(d.querySelectorAll('#pd-pub .chk.falta').length===0&&d.getElementById('pd-publicar')&&d.getElementById('pd-publicar').getAttribute('aria-disabled')!=='true','com os requisitos cumpridos o botão Publicar deveria ficar ativo');
// WordPress sem credencial neste ambiente: o erro tem que ser EXPLICADO e FICAR na tela
await w.publicarProjeto('F026-P0001','publicar'); await sleep(1800);
chk(txt('#d-title').includes('Não foi possível publicar')&&txt('#d-body').includes('WordPress')&&txt('#d-body').includes('Configurações'),'sem credencial do WordPress deveria explicar e apontar Configurações: '+txt('#d-body').slice(0,120));
w.closeDrawer(true);
// fundo inteiro sem direitos: o erro vira painel fixo com o botão que resolve (caso real do F001)
await w.statusFundoSite('F003','no_ar'); await sleep(1800);
chk(txt('#d-title').includes('Não foi possível publicar o fundo')&&txt('#d-body').includes('F003')&&txt('#d-body').includes('Direitos do fundo')&&txt('#d-body').includes('Definir direitos do fundo'),'fundo sem direitos deveria abrir painel fixo com o botão: '+txt('#d-title')+' | '+txt('#d-body').slice(0,100)); w.closeDrawer(true);
okl.push('publicação: checklist antes de clicar, erro com todas as razões e botões, resultado fixo, WordPress sem credencial explicado');

// ---------- FOTO DE PERFIL ----------
{ const {Blob:NB}=require('buffer'); const JPG=Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDIooor5E+4P//Z','base64');
  w.prepararFoto=async()=>new NB([JPG],{type:'image/jpeg'});   // jsdom não tem canvas: o recorte/redução é do navegador real
  const eu0=await J(adm,'/api/auth/eu'); const meuId=eu0.b.id;
  chk(typeof meuId==='number'&&eu0.b.tem_foto===false,'o /eu deveria trazer id e tem_foto=false: '+JSON.stringify(eu0.b));
  chk(!d.querySelector('.who .av img')&&d.querySelector('.who .av').textContent.trim().length>0,'sem foto o topo deveria mostrar as iniciais');
  await w.trocarFoto(meuId,{files:[{name:'x.jpg'}],value:'x'}); await sleep(1800);
  const img=d.querySelector('.who .av img'); chk(img&&img.getAttribute('src').startsWith('/api/usuarios/'+meuId+'/foto'),'depois de enviar, o topo deveria mostrar a foto: '+(img?img.getAttribute('src'):'(sem img)'));
  const g=await adm.f('/api/usuarios/'+meuId+'/foto'); chk(g.status===200&&g.headers.get('content-type')==='image/jpeg'&&g.headers.get('x-content-type-options')==='nosniff','a foto deveria ser servida como JPEG com nosniff');
  w.route_to('config'); await sleep(1800);
  chk(!!d.querySelector('#usr-body .av img'),'a tabela de usuários deveria mostrar a foto de quem tem');
  chk([...d.querySelectorAll('#usr-body button')].some(b=>b.textContent.trim()==='Foto'),'a tabela de usuários deveria ter o botão "Foto" para o master');
  // arquivo inválido: mensagem clara e a foto anterior continua
  w.prepararFoto=async()=>new NB([Buffer.from('<html><script>alert(1)</script></html>')],{type:'image/jpeg'});
  await w.trocarFoto(meuId,{files:[{name:'y.jpg'}],value:'y'}); await sleep(1500);
  chk(/JPEG ou PNG/.test(txt('#toast')),'arquivo inválido deveria dizer "Envie uma foto JPEG ou PNG": '+txt('#toast'));
  chk((await adm.f('/api/usuarios/'+meuId+'/foto')).status===200,'a recusa não pode apagar a foto anterior');
  // remover
  await w.removerFoto(meuId); await sleep(1800);
  chk(!d.querySelector('.who .av img'),'depois de remover, o topo deveria voltar às iniciais');
  chk((await adm.f('/api/usuarios/'+meuId+'/foto')).status===404,'depois de remover a foto deveria dar 404');
  okl.push('foto de perfil: envia, aparece no topo e na tabela de usuários, recusa arquivo inválido com mensagem, remove'); }

// ---------- GUIA: como publicar fundo e arquiteto ----------
w.location.hash='#fundo/F003'; await sleep(2800);
chk(!!d.getElementById('fd-guia')&&txt('#fd-guia').includes('Como publicar este fundo')&&txt('#fd-guia').includes('Próximo passo:'),'a página do fundo deveria ter o quadro "Como publicar este fundo" com o próximo passo: '+txt('#fd-guia').slice(0,80));
chk(d.querySelectorAll('#fd-guia .chk').length>=4&&txt('#fd-guia').includes('Direitos do fundo F003 autorizados'),'o checklist do fundo deveria listar os requisitos');
chk(d.querySelectorAll('#fd-guia .guia-passos li').length===8,'o passo a passo completo do fundo deveria ter 8 passos: '+d.querySelectorAll('#fd-guia .guia-passos li').length);
{ const bt=[...d.querySelectorAll('#fd-guia .chk.falta button')].find(b=>b.textContent.includes('Definir direitos')); chk(!!bt,'o checklist deveria oferecer "Definir direitos do fundo"'); if(bt){ bt.click(); await sleep(1500); chk(txt('#d-title').includes('Direitos e licença'),'o botão deveria abrir a edição de direitos: '+txt('#d-title')); w.closeDrawer(true); } }
await w.abrirAjuda(); await sleep(500);
chk(txt('#d-title').includes('Publicar um fundo')&&txt('#d-body').includes('Definir os direitos')&&txt('#d-body').includes('Autorizar cada projeto'),'a ajuda (?) do fundo deveria trazer o passo a passo: '+txt('#d-title')); w.closeDrawer(true);
w.location.hash='#arquitetos'; await sleep(2200);
{ const ags=await J(adm,'/api/agentes'); const a0=(ags.b||[])[0]; chk(!!a0,'o ambiente deveria ter arquitetos');
  await w.editarAgente(a0.id); await sleep(1800);
  chk(!!d.getElementById('ag-guia')&&txt('#ag-guia').includes('Como publicar este arquiteto'),'o formulário do arquiteto deveria ter o quadro "Como publicar este arquiteto"');
  chk(txt('#ag-guia').includes('marcador interno')&&txt('#ag-guia').includes('wp-admin'),'o guia do arquiteto deveria dizer que o status é só marcador e que foto/bio/ativar são no wp-admin');
  chk(d.querySelectorAll('#ag-guia .guia-passos li').length===6,'o passo a passo do arquiteto deveria ter 6 passos');
  w.closeDrawer(true); }
await w.abrirAjuda(); await sleep(500);
chk(txt('#d-title').includes('Publicar um arquiteto')&&txt('#d-body').includes('Completar no WordPress'),'a ajuda (?) de Arquitetos deveria trazer o passo a passo: '+txt('#d-title')); w.closeDrawer(true);
okl.push('guia: checklist vivo do fundo e do arquiteto, passo a passo, botão que resolve e ajuda (?) contextual');

// ---------- PAGINAÇÃO: projetos e auditoria (servidor) + paginador genérico + exportação completa ----------
{ const lerBlob=b=>new Promise(r=>{const fr=new w.FileReader();fr.onload=()=>r(fr.result);fr.readAsText(b)});
  w.URL.createObjectURL=b=>{w.__ultimoBlob=b;return 'blob:teste'};
  const tot=(await J(adm,'/api/projetos?por_pagina=1')).b.total;
  chk(tot>=10,'precondição: o ambiente de teste deveria ter pelo menos 10 projetos: '+tot);
  w.eval('PROJ_PAG.por=5;PROJ_PAG.pagina=1');   // o banco de teste é pequeno: força páginas de 5 (no seu, 1.794 projetos)
  w.route_to('projetos'); await w.carregarProjetosAPI({q:''}); await sleep(1500);
  const pgs=Math.ceil(tot/5), linhasP=()=>[...d.querySelectorAll('#projetos-body tr[data-nav]')].map(tr=>tr.getAttribute('data-nav'));
  chk(!d.getElementById('projetos-pag').hidden&&txt('#projetos-pag').includes('de '+tot)&&new RegExp('Página 1 de '+pgs).test(txt('#projetos-pag')),'Projetos deveria mostrar o controle de paginação com o total: "'+txt('#projetos-pag').slice(0,90)+'"');
  const pag1=linhasP(); chk(pag1.length===5,'a página 1 deveria ter 5 linhas: '+pag1.length);
  chk(txt('#v-projetos .cnt').includes('1–5 de '+tot+' projetos'),'o contador deveria dizer "1–5 de '+tot+' projetos" (e não "N registros"): "'+txt('#v-projetos .cnt')+'"');
  w.toggleProjetoSelecionado(pag1[0].replace('projeto/',''),true);
  d.querySelector('#projetos-pag button[data-pg="prox"]').click(); await sleep(1800);
  const pag2=linhasP(); chk(pag2.length===5&&!pag2.some(c=>pag1.includes(c)),'a página 2 deveria ter 5 linhas diferentes das da 1: '+pag2.length);
  chk(txt('#v-projetos .cnt').includes('6–10 de '+tot),'o contador da página 2 deveria dizer 6–10: "'+txt('#v-projetos .cnt')+'"');
  chk(w.eval('PROJETOS_SELECIONADOS.size')===1,'a seleção deveria sobreviver à troca de página');
  for(let k=2;k<pgs;k++){ d.querySelector('#projetos-pag button[data-pg="prox"]').click(); await sleep(1500); }
  chk(d.querySelector('#projetos-pag button[data-pg="prox"]').disabled&&linhasP().length===tot-5*(pgs-1),'na última página Próxima deveria estar desabilitada e restar '+(tot-5*(pgs-1))+' linha(s): '+linhasP().length);
  // exportar: traz TODOS do filtro, não só a página
  w.__baixou=[]; w.exportarVisaoAtual('projetos'); await sleep(2800);
  { const csv=await lerBlob(w.__ultimoBlob); const cods=new Set(csv.match(/F\d{3}-P\d{4}/g)||[]);
    chk((w.__baixou||[]).length>0&&cods.size>=tot,'a exportação deveria trazer os '+tot+' projetos (não só os '+linhasP().length+' da página): achei '+cods.size); }
  // mudar o filtro volta à página 1
  await w.carregarProjetosAPI({q:'Casa'}); await sleep(1500);
  chk(!/Página [2-9]/.test(txt('#projetos-pag')),'depois de buscar, a lista deveria voltar à página 1: "'+txt('#projetos-pag').slice(0,60)+'"');
  // o seletor "por página" funciona
  w.eval('PROJ_PAG.por=5'); await w.carregarProjetosAPI({q:''}); await sleep(1500);
  { const sel=d.querySelector('#projetos-pag select[data-pg="por"]'); sel.value='25'; sel.dispatchEvent(new w.Event('change',{bubbles:true})); await sleep(1800);
    chk(linhasP().length===Math.min(25,tot)&&d.getElementById('projetos-pag').hidden===(tot<=25),'trocar para 25 por página deveria mostrar '+Math.min(25,tot)+' linhas: '+linhasP().length); }
  w.eval('PROJ_PAG.por=100;PROJ_PAG.pagina=1'); await w.carregarProjetosAPI({q:''}); await sleep(1200); w.limparSelecaoProjetos();
  // auditoria
  w.route_to('auditoria'); await sleep(2200);
  const totAu=(await J(adm,'/api/eventos?por_pagina=1')).b.total;
  chk(totAu>60,'precondição: a auditoria deveria ter mais de 60 eventos: '+totAu);
  w.eval('AUD_PAG.por=25;AUD_PAG.pagina=1'); await w.carregarAuditoria(); await sleep(1800);
  chk(!d.getElementById('au-pag').hidden&&!!d.querySelector('#au-pag select[data-pg="por"]')&&txt('#au-pag').includes('de '+totAu),'a Auditoria deveria ter o controle de paginação com o total: "'+txt('#au-pag').slice(0,80)+'"');
  const idsAu=()=>[...d.querySelectorAll('#au-body tr[data-audit-id]')].map(tr=>tr.getAttribute('data-audit-id'));
  const a1=idsAu(); chk(a1.length===25,'a Auditoria com 25 por página deveria mostrar 25 linhas: '+a1.length);
  d.querySelector('#au-pag button[data-pg="prox"]').click(); await sleep(1800);
  const a2=idsAu(); chk(a2.length>0&&!a2.some(i=>a1.includes(i))&&Math.max(...a2.map(Number))<Math.min(...a1.map(Number)),'a página 2 da auditoria deveria ter eventos MAIS ANTIGOS e sem repetição');
  w.eval('AUD_PAG.por=100;AUD_PAG.pagina=1'); await w.carregarAuditoria(); await sleep(1500);
  // paginador genérico (qualquer lista desenhada na tela)
  { const raiz=d.createElement('section'); raiz.id='v-fake'; raiz.innerHTML='<div class="filterbar"></div><div class="tw"><table><thead><tr><th>N</th></tr></thead><tbody id="fk"></tbody></table></div><div class="thumbs" id="gr"></div>'; d.body.appendChild(raiz);
    const fk=d.getElementById('fk'); fk.innerHTML=Array.from({length:120},(_,i)=>'<tr><td>'+(i+1)+'</td></tr>').join('');
    w.ativarPaginacao('#fk',{por:50}); await sleep(150);
    const vis=()=>[...fk.children].filter(r=>!r.classList.contains('pg-oculta')&&r.style.display!=='none').map(r=>+r.textContent);
    const ctl=()=>fk.closest('.tw').nextElementSibling;
    chk(vis().length===50&&vis()[0]===1&&/Mostrando 1–50 de 120/.test(ctl().textContent)&&/Página 1 de 3/.test(ctl().textContent),'paginador genérico: 120 linhas deveriam virar 3 páginas de 50: '+vis().length+' | '+ctl().textContent.slice(0,70));
    ctl().querySelector('button[data-pg="prox"]').click(); chk(vis()[0]===51&&vis().length===50,'a página 2 deveria começar na linha 51');
    ctl().querySelector('button[data-pg="prox"]').click(); chk(vis().length===20&&vis()[0]===101,'a página 3 deveria ter as 20 últimas');
    ctl().querySelector('button[data-pg="ant"]').click(); chk(vis()[0]===51,'Anterior deveria voltar à página 2');
    // exportar uma lista paginada só na tela: as linhas escondidas pela página ENTRAM
    w.__baixou=[]; w.exportarVisaoAtual('fake'); chk(/120 linha\(s\) exportadas/.test(txt('#toast')),'exportar deveria trazer as 120 linhas, não só as 50 da página: "'+txt('#toast')+'"');
    // filtro por style.display recalcula as páginas
    [...fk.children].slice(0,100).forEach(r=>{r.style.display='none'}); await sleep(150);
    chk(ctl().hidden&&vis().length===20,'filtrando para 20 linhas o controle deveria sumir e as 20 aparecerem: '+vis().length);
    [...fk.children].forEach(r=>{r.style.display=''}); await sleep(150);
    chk(!ctl().hidden&&vis().length===50,'ao remover o filtro a paginação deveria voltar');
    // redesenho com outro tamanho volta à página 1
    fk.innerHTML=Array.from({length:75},(_,i)=>'<tr><td>'+(i+1)+'</td></tr>').join(''); await sleep(150);
    chk(vis().length===50&&vis()[0]===1&&/Página 1 de 2/.test(ctl().textContent),'redesenhar a lista deveria voltar à página 1');
    // modo "mostrar mais" (grades de folhas)
    const gr=d.getElementById('gr'); gr.innerHTML=Array.from({length:130},(_,i)=>'<div class="card">'+(i+1)+'</div>').join(''); w.ativarPaginacao('#gr',{por:60,modo:'mais'}); await sleep(150);
    const gv=()=>[...gr.children].filter(r=>!r.classList.contains('pg-oculta')).length, gc=()=>gr.nextElementSibling;
    chk(gv()===60&&/Mostrando 60 de 130/.test(gc().textContent),'grade: deveria mostrar 60 de 130: '+gv());
    gc().querySelector('button[data-pg="mais"]').click(); chk(gv()===120,'"Mostrar mais" deveria mostrar 120');
    gc().querySelector('button[data-pg="mais"]').click(); chk(gv()===130&&!gc().querySelector('button'),'depois de tudo exibido o botão deveria sumir');
    raiz.remove(); d.querySelectorAll('.pg-ctl').forEach(c=>{if(!c.id)c.remove()}); }
  // as grades de folhas dos projetos já saem paginadas (60) quando passam disso
  w.route_to('projeto/F023-P0011'); await sleep(2000);
  chk([...d.querySelectorAll('.project-series .thumbs')].every(g=>g.dataset.pg==='mais'),'as grades de folhas do projeto deveriam estar ligadas ao "Mostrar mais"');
  okl.push('paginação: projetos e auditoria no servidor (páginas sem repetir, seleção mantida, busca volta à 1ª, exporta tudo), paginador genérico e "mostrar mais"'); }
// rotas inválidas / deep link
w.location.hash='#projeto/F999-P9999'; await sleep(1000); chk(!/undefined|NaN/.test(txt('.content.on')),'rota de projeto inexistente mostra lixo: '+txt('.content.on').slice(0,80)); okl.push('deep link inexistente: "'+txt('.content.on').slice(0,60)+'"');
w.location.hash='#rota-que-nao-existe'; await sleep(600); okl.push('rota inválida: "'+txt('.content.on').slice(0,60)+'"');
console.log('\n=== OK ==='); okl.forEach(x=>console.log(' ✓',x));
console.log('\n=== PROBLEMAS ('+[...new Set(problems)].length+') ==='); [...new Set(problems)].forEach(x=>console.log(' ✗',x));
process.exit(0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
