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
  if(!w.CSS)w.CSS={};if(!w.CSS.escape)w.CSS.escape=s=>String(s).replace(/[^a-zA-Z0-9_-]/g,c=>'\\'+c);   // o jsdom não tem CSS.escape (todo navegador tem)
  // P2-18: as confirmações são uma janela do painel (#conf-ov), não o confirm do navegador. Para os testes, a resposta continua vindo de w.confirm(texto).
  w.addEventListener('DOMContentLoaded',()=>{new w.MutationObserver(()=>{const ov=w.document.getElementById('conf-ov');if(!ov||ov.dataset.respondido||w.__semAutoResposta)return;ov.dataset.respondido='1';const resp=w.confirm(ov.textContent);setTimeout(()=>{if(!w.document.body.contains(ov))return;
    if(resp){const dg=ov.querySelector('#conf-dig');if(dg){dg.value=ov.dataset.digitar||'';dg.dispatchEvent(new w.Event('input',{bubbles:true}))}const mt=ov.querySelector('#conf-motivo');if(mt&&!mt.value){mt.value='teste';mt.dispatchEvent(new w.Event('input',{bubbles:true}))}}
    const b=ov.querySelector(resp?'[data-conf="sim"]':'[data-conf="nao"]')||ov.querySelector('[data-conf="sim"]');b&&b.click()},0)}).observe(w.document.body,{childList:true})});
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
w.confirm=()=>false; const c1=w.closeDrawer(); chk(c1===false&&!!d.getElementById('conf-ov')&&/alterações não salvas/.test(txt('#conf-ov'))&&!/confirm\(/.test(String(w.confirmarDescartar)),'[P2-18] fechar com alteração deveria abrir a janela do painel "Sair sem salvar?" (não o confirm do navegador)'); await sleep(150); chk(dr.className===cls0&&!d.getElementById('conf-ov'),'fechar com alteração e "Continuar editando" deveria manter o drawer aberto');
w.confirm=()=>true; const c2=w.closeDrawer(); await sleep(150); chk(c2===false&&!dr.className.includes('with-drawer'),'fechar com "Sair sem salvar" deveria fechar o drawer');
const ev=new w.Event('beforeunload',{cancelable:true}); w.editarFundo&&await w.editarFundo('F026'); await sleep(300); const t2=d.getElementById('ef-titulo'); t2.value+='y'; t2.dispatchEvent(new w.Event('input',{bubbles:true})); w.dispatchEvent(ev); chk(ev.defaultPrevented||ev.returnValue!==undefined,'beforeunload não protege edição pendente'); w.confirm=()=>true; w.closeDrawer();
okl.push('proteção de edição não salva (drawer + beforeunload)');
// ajuda
for(const rota of ['painel','fundos','projetos','etiquetas','config']){ w.route_to(rota); await sleep(500); try{w.abrirAjuda()}catch(e){problems.push('abrirAjuda em '+rota+': '+e.message)} chk(!!d.querySelector('section.content.on > .ajuda-caixa'),'ajuda não abriu em '+rota); }
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
  dl.window.route_to('item/'+IT); await sleep(1200); chk(!dl.window.document.getElementById('it-editar'),'usuário de LEITURA vê o botão Editar'); okl.push('usuário de leitura não vê o botão Editar'); dl.window.route_to('estacoes'); await sleep(2800); chk(!!dl.window.document.getElementById('qnap-card')&&!dl.window.document.getElementById('qnap-atualizar'),'leitura deveria ver o cartão do QNAP (em Estações e site) SEM o botão Atualizar agora'); dl.window.route_to('fundo/F003'); await sleep(2200); chk(!!dl.window.document.getElementById('fd-guia')&&!dl.window.document.querySelector('#fd-guia .chk button'),'leitura deveria ver o guia do fundo SEM botões de ação'); dl.window.route_to('projeto/F026-P0001'); await sleep(1800); chk(!!dl.window.document.getElementById('pd-pub')&&!dl.window.document.getElementById('pd-publicar')&&!dl.window.document.querySelector('#pd-pub .chk button'),'leitura deveria ver o checklist mas NÃO os botões de publicar/resolver'); dl.window.route_to('estacoes'); await sleep(3000); chk(!!dl.window.document.getElementById('imp-painel')&&!dl.window.document.getElementById('imp-ver'),'leitura deveria ver o painel de importação mas NÃO o botão "Ver o que está faltando"'); chk(!!dl.window.document.getElementById('bk-painel')&&!dl.window.document.getElementById('bk-agora'),'leitura deveria VER o painel de backup mas NÃO o botão "Fazer backup agora"'); dl.window.close(); }

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
chk(!txt('#v-projeto').includes('Ver página pública')&&!/Abrir no site/.test(txt('#v-projeto .dethdr'))&&txt('#v-projeto').includes('ainda não é pública'),'[#95] página real em RASCUNHO no site: nem "Ver página pública" nem link para uma página que dá erro (só a explicação): '+txt('#v-projeto .dethdr').slice(0,140));
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
  chk(!/offline/i.test(txt('#ini-saude')),'o resumo do painel não deveria dizer "offline" por causa de máquinas: '+txt('#ini-saude'));
  chk(!!d.querySelector('.machine-status button, .machine-status .ms'),'a barra do topo deve continuar mostrando as máquinas'); }
// QNAP: a mensagem diz O QUE é e o que fazer (antes: "Problema na infraestrutura")
w.route_to('painel'); await sleep(2500);
chk(txt('#ini-saude').includes('QNAP desconectado deste servidor')&&!/infraestrutura/i.test(txt('#ini-saude')),'o painel inicial deveria dizer exatamente o que está errado: "'+txt('#ini-saude')+'"');
chk(txt('#system-banner').includes('QNAP não está conectado a este servidor'),'o banner deveria dizer que o QNAP não está conectado a este servidor: "'+txt('#system-banner').slice(0,100)+'"');
w.route_to('estacoes'); await sleep(2800);
chk(!!d.getElementById('qnap-ajuda')&&txt('#qnap-ajuda').includes('diagnostico_qnap.sh')&&txt('#qnap-ajuda').includes('montar_qnap.sh')&&txt('#qnap-ajuda').includes('Macs'),'a tela Estações deveria explicar como conectar o QNAP (com os dois comandos)');
// cartão do QNAP (agora em Estações e site; o painel inicial só tem a linha "QNAP" em "Está tudo funcionando?"): informações úteis lidas do que o coletor guardou
w.route_to('estacoes'); await sleep(2800);
{ const c=txt('#qnap-card');
  chk(/11\.?880 GB/.test(c)&&/de 20\.?000 GB/.test(c),'o cartão deveria mostrar o espaço livre/total: '+c.slice(0,90));
  chk(!!d.querySelector('#qnap-card svg.qnap-spark'),'o cartão deveria ter o gráfico de espaço dos últimos 7 dias');
  chk(/Tendência/.test(c)&&/GB\/dia/.test(c)&&/enche em ~\d/.test(c),'o cartão deveria mostrar a tendência e quantos dias até encher: '+c.slice(0,200));
  chk(/Último material/.test(c)&&/há 3 h/.test(c)&&c.includes('F002-P0002-IGREJA/lote-12'),'o cartão deveria mostrar o último material recebido (há 3 h + nome)');
  chk(/Entrada bruta/.test(c)&&/14 pastas/.test(c)&&/2 paradas há mais de 3 dias/.test(c),'o cartão deveria mostrar a entrada bruta e as pastas paradas');
  chk(/Lotes prontos/.test(c)&&/230/.test(c)&&/Resposta/.test(c)&&/42 ms/.test(c),'o cartão deveria mostrar os lotes prontos e a resposta em ms');
  chk(/Atualizado há \d+ min/.test(c),'o cartão deveria dizer há quanto tempo foi atualizado: '+c.slice(-80));
  chk(!!d.getElementById('qnap-atualizar'),'o master deveria ver o botão "Atualizar agora"');
  // atualizar agora: pede a coleta, espera e recarrega o cartão
  d.getElementById('qnap-atualizar').click(); await sleep(7000);
  chk(/Atualizado (agora|há 0 min)/.test(txt('#qnap-card'))&&!!d.getElementById('qnap-atualizar')&&!d.getElementById('qnap-atualizar').disabled,'depois de "Atualizar agora" o cartão deveria mostrar a coleta nova: '+txt('#qnap-card').slice(-90)); }
// ---------- USO DO ACERVO (pedidos de download do formulário do site) ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('uso'); await sleep(2500);
  const R=(await J(adm,'/api/uso/resumo')).b, L=(await J(adm,'/api/uso')).b, linhas=()=>d.querySelectorAll('#us-body tr.us-row').length;
  chk(!!d.querySelector('#nav [data-v="uso"]')&&txt('#nav [data-v="uso"] kbd')==='6','o menu deveria ter "Uso do acervo" com o atalho 6');
  { let el=d.querySelector('#nav [data-v="uso"]').previousElementSibling; while(el&&!el.classList.contains('grp'))el=el.previousElementSibling; chk(el&&el.textContent.trim()==='Pedidos','"Uso do acervo" deveria ficar no grupo PEDIDOS do menu (junto das Solicitações), está em "'+(el&&el.textContent.trim())+'"'); }
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
  chk(/3 folhas importadas/.test(txt('[data-aviso="lote"]'))&&/Próximo passo: conferir/.test(txt('[data-aviso="lote"]'))&&!!d.querySelector('[data-aviso="lote"] [data-pp="conferir"]'),'[H4] depois de importar, o resultado deveria ficar NA TELA com o próximo passo e o botão "Começar a conferir": "'+txt('[data-aviso="lote"]')+'"');
  const dt=(await J(adm,'/api/projetos/'+pc+'/detalhe')).b;
  chk(dt.itens.length===3&&dt.itens.every(i=>i.revisao==='pendente'&&i.lote_id===loteId),'importar deveria criar 3 folhas pendentes ligadas ao lote: '+dt.itens.length);
  chk(/3 a conferir/.test(txt('#pj-revisao'))&&/Aprovar todas \(3\)/.test(txt('#pj-revisao'))&&!!d.querySelector('#pj-revisao [data-rev-lote="todas"]')&&!d.querySelector('#pj-revisao [data-rev-lote="aprovar"]'),'depois de importar: 3 a conferir e UM botão principal "Aprovar todas (3)" (o "Aprovar o lote" só aparece quando não restar nenhuma): "'+txt('#pj-revisao').slice(0,200)+'"');
  chk(!/Encontradas no QNAP, ainda não catalogadas/.test(txt('#pj-qnap'))||!/contatos/.test(txt('#pj-qnap')),'o painel do QNAP não deveria listar a folha de contatos (pasta catalogacao) como documento esperando');
  const cards=[...d.querySelectorAll('.thumb')].filter(x=>x.textContent.includes(pc));
  chk(cards.length===3&&cards.every(x=>/a conferir/.test(x.textContent)&&x.hasAttribute('data-rev-abrir')&&!x.querySelector('button')),'cada cartão deveria ter o selo "a conferir" e ABRIR a revisão ao clicar (sem botão repetido em cada folha): '+cards.length);
  cards[0].click(); await sleep(1800); chk(/Revisar folha/.test(txt('#d-title'))&&/Ainda faltam 3 folha/.test(txt('#d-body')),'clicar no cartão deveria abrir a revisão da folha: "'+txt('#d-body').slice(0,100)+'"'); w.closeDrawer(true);
  d.querySelector('[data-rev-lote="conferir"]').click(); await sleep(3200);
  chk((await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].itens.conferida===0,'conferir em lote não deveria marcar folha com pendência apontada pelo CAMP Vision (todas as 3 têm)');
  w.abrirRevisaoItem(D(3)); await sleep(1800);
  chk(/O que o CAMP Vision leu/.test(txt('#d-body'))&&/orientação incerta/.test(txt('#d-body'))&&!!d.querySelector('#rv-titulo')&&!!d.querySelector('#rv-tipo')&&!!d.querySelector('[data-rev-item="conferida"]'),'a janela de revisão deveria mostrar o que o CAMP Vision apontou e os campos: "'+txt('#d-body').slice(0,140)+'"');
  d.querySelector('[data-rev-item="conferida"]').click(); await sleep(3000);
  chk((await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].itens.conferida===1,'"Está certo" deveria marcar a folha como conferida');
  chk(new RegExp('Folha '+D(3)+' conferida').test(txt('#toast'))&&/Desfazer/.test(txt('#toast .toast-acao')),'[H4] conferir não pergunta: o aviso diz a folha e traz "Desfazer": "'+txt('#toast')+'"');
  const bx=d.querySelector('#d-body [data-rev-item="conferida"]'); chk(/Revisar folha/.test(txt('#d-title'))&&!!bx&&bx.dataset.codigo===D(1)&&w.eval('mainEl').classList.contains('with-drawer'),'depois de conferir, a janela deveria passar SOZINHA para a próxima folha pendente ('+D(1)+'): '+(bx&&bx.dataset.codigo));
  chk([...d.querySelectorAll('.thumb[data-rev-abrir="'+D(3)+'"] .rev-tag')].every(t=>/conferida/.test(t.textContent)),'o selo do cartão deveria virar "conferida" SEM recarregar a página');
  d.querySelector('[data-rev-girar="90"]').click(); await sleep(1500);
  chk((await J(adm,'/api/projetos/'+pc+'/detalhe')).b.itens.find(i=>i.codigo===D(1)).giro_manual===90&&/g=90/.test(d.getElementById('rv-img').getAttribute('src'))&&[...d.querySelectorAll('.thumb[data-rev-abrir="'+D(1)+'"] img')].every(i=>/g=90/.test(i.getAttribute('src'))),'"Virar à direita" deveria gravar o giro (90) e atualizar a imagem da janela e o cartão');
  d.querySelector('[data-rev-girar="-90"]').click(); await sleep(1500);
  chk((await J(adm,'/api/projetos/'+pc+'/detalhe')).b.itens.find(i=>i.codigo===D(1)).giro_manual===0,'"Virar à esquerda" deveria voltar o giro a 0');
  { const ta=d.querySelector('#toast .toast-acao'); chk(!!ta&&/girada para a esquerda/.test(txt('#toast')),'[H4] girar deveria dizer o que fez e trazer "Desfazer": "'+txt('#toast')+'"');
    if(ta){ ta.click(); await sleep(1500); chk((await J(adm,'/api/projetos/'+pc+'/detalhe')).b.itens.find(i=>i.codigo===D(1)).giro_manual===90&&/Giro desfeito/.test(txt('#toast'))&&!d.querySelector('#toast .toast-acao'),'[H4] "Desfazer" do giro deveria voltar a 90 (e não oferecer outro Desfazer): "'+txt('#toast')+'"');
      d.querySelector('[data-rev-girar="-90"]').click(); await sleep(1500); } }
  d.getElementById('rv-titulo').value='Planta corrigida no teste'; d.getElementById('rv-escala').value='1:75';
  d.querySelector('[data-rev-item="corrigida"]').click(); await sleep(3400);
  const e1=(await J(adm,'/api/itens/'+D(1)+'/edicao')).b.local, r1=(await J(adm,'/api/projetos/'+pc+'/detalhe')).b.itens.find(i=>i.codigo===D(1));
  chk(e1.titulo==='Planta corrigida no teste'&&e1.escala==='1:75'&&r1.revisao==='corrigida'&&r1.revisado_por,'"Salvar correção" deveria gravar os campos E marcar como corrigida: '+JSON.stringify({t:e1.titulo,e:e1.escala,r:r1.revisao}));
  w.closeDrawer(true); d.querySelector('#pj-revisao [data-rev-lote="todas"]').click(); await sleep(3600);
  chk((await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].itens.pendente===0,'"Aprovar todas" deveria conferir a folha que restava');
  chk(/Aprovar o lote/.test(txt('#pj-revisao'))&&d.querySelector('#pj-revisao [data-rev-lote="aprovar"]').disabled===false&&/pronta para aprovar/.test(txt('#pj-revisao')),'com todas revisadas, "Aprovar o lote" deveria liberar: "'+txt('#pj-revisao').slice(0,160)+'"');
  d.querySelector('#pj-revisao [data-rev-lote="aprovar"]').click(); await sleep(3600);
  const ap=(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0];
  chk(!!ap.aprovado_em&&ap.etapa==='revisao'&&/aprovado por/.test(txt('#pj-revisao'))&&!!d.querySelector('#pj-revisao [data-rev-lote="reabrir"]'),'aprovar deveria registrar quem/quando, manter a etapa e oferecer "Reabrir a revisão": '+JSON.stringify({a:ap.aprovado_em,e:ap.etapa}));
  d.querySelector('#pj-revisao [data-rev-lote="reabrir"]').click(); await sleep(3400);
  chk(!(await J(adm,'/api/projetos/'+pc+'/revisao')).b.lotes[0].aprovado_em,'reabrir deveria limpar a aprovação'); }
// ---------- ENDEREÇO DA PÁGINA PÚBLICA: o painel confirma no site em vez de presumir ----------
{ const box=d.createElement('div'); d.body.appendChild(box); const fetchOrig=w.fetch; let chamadas=[];
  const fake=resp=>{w.fetch=async(u,o)=>{chamadas.push((o&&o.method||'GET')+' '+u);return {ok:true,status:200,statusText:'OK',json:async()=>resp}}};
  fake({url:null,origem:'nao_encontrado',busca:'https://camp.arq.br/acervo/projetos/?q=F026-P0005'});
  box.innerHTML=w.linkPaginaSite('https://camp.arq.br/acervo/projetos/f026-p0005-clube-ipe-social-rua-estado-de-israel/',true,'btn',true); await sleep(1200);
  let a=box.querySelector('a');
  chk(chamadas.length===1&&/POST \/api\/projetos\/F026-P0005\/pagina-publica\/confirmar/.test(chamadas[0]),'um link presumido deveria perguntar ao site: '+JSON.stringify(chamadas));
  chk(a.textContent==='Procurar no site'&&a.href==='https://camp.arq.br/acervo/projetos/?q=F026-P0005','sem a página no site, o botão deveria levar à BUSCA PÚBLICA por código (nunca a um link morto): "'+a.textContent+'" '+a.href);
  fake({url:'https://camp.arq.br/acervo/projetos/f026-p0005-clube-ipe-social/',origem:'confirmado',como:'busca'}); chamadas=[];
  box.innerHTML=w.linkPaginaSite('https://camp.arq.br/acervo/projetos/f026-p0005-x/',true,'btn',true); await sleep(1200); a=box.querySelector('a');
  chk(a.textContent==='Ver página pública'&&a.href==='https://camp.arq.br/acervo/projetos/f026-p0005-clube-ipe-social/','achando a página real, o botão deveria apontar para ela: '+a.href);
  chamadas=[]; fake({});
  box.innerHTML=w.linkPaginaSite('https://camp.arq.br/acervo/projetos/f026-p0001-edificio-taruma/',true,'btn',false)+w.linkPaginaSite('https://camp.arq.br/acervo/projetos/f026-p0002-x/',false,'btn',true); await sleep(900);
  chk(chamadas.length===0,'link REAL do site (ou de projeto não publicado) não deveria perguntar nada: '+JSON.stringify(chamadas));
  w.fetch=fetchOrig; box.remove(); }
// ---------- LER DADOS AGORA: pedido de releitura ao CAMP Vision ----------
{ w.confirm=()=>true; const IT='F023-P0011-1959-S01-D00003';
  w.route_to('item/'+IT); await sleep(2600);
  chk(!!d.getElementById('it-releitura')&&/Ler dados agora/.test(txt('#it-releitura')),'a página da folha deveria ter o botão "Ler dados agora"');
  d.getElementById('it-releitura').click(); await sleep(2300);
  chk(/releitura pedida/.test(txt('#it-releitura-estado'))&&/ainda não consulta pedidos/.test(txt('#it-releitura-estado'))&&!!d.querySelector('#it-releitura-estado [data-rl-cancelar]'),'depois de clicar: "releitura pedida", a verdade sobre o CAMP Vision e o botão cancelar: "'+txt('#it-releitura-estado').slice(0,160)+'"');
  const lst=(await J(adm,'/api/itens/'+IT+'/releitura')).b; chk(!!lst.aberto&&lst.aberto.estado==='pedido'&&lst.aberto.item_codigo===IT,'o pedido deveria existir no servidor: '+JSON.stringify(lst.aberto));
  d.getElementById('it-releitura').click(); await sleep(1600); chk((await J(adm,'/api/itens/'+IT+'/releitura')).b.aberto.id===lst.aberto.id,'clicar de novo não deveria criar outro pedido');
  d.querySelector('#it-releitura-estado [data-rl-cancelar]').click(); await sleep(2300);
  chk(!(await J(adm,'/api/itens/'+IT+'/releitura')).b.aberto&&!/releitura pedida/.test(txt('#it-releitura-estado')),'cancelar deveria encerrar o pedido e limpar o estado');
  w.route_to('item/F023-P0011-1959-S01-D00001'); await sleep(2600);
  chk(/releitura falhou/.test(txt('#it-releitura-estado'))&&/modelo indisponível/.test(txt('#it-releitura-estado')),'a falha respondida pelo CAMP Vision deveria aparecer na página da folha: "'+txt('#it-releitura-estado')+'"');
  w.route_to('projeto/F003-P9001'); await sleep(3800);
  chk(/Ler o projeto de novo no CAMP Vision/.test(txt('#pj-revisao'))&&/releitura falhou/.test(txt('#pj-revisao .rl-estado')),'o painel de revisão do projeto deveria ter o botão e mostrar a última releitura: "'+txt('#pj-revisao').slice(0,140)+'"');
  d.querySelector('#pj-revisao [data-rev-lote="releitura"]').click(); await sleep(2400);
  chk(/releitura pedida/.test(txt('#pj-revisao .rl-estado')),'pedir o projeto inteiro deveria mostrar o estado no painel: "'+txt('#pj-revisao .rl-estado')+'"');
  d.querySelector('#pj-revisao [data-rl-cancelar]').click(); await sleep(2200);
  chk(!(await J(adm,'/api/projetos/F003-P9001/releitura')).b.aberto,'cancelar o pedido do projeto'); }
// ---------- FILAS: cada lista diz o que falta e tem UM botão para o próximo passo ----------
{ w.confirm=()=>true; w.route_to('filas'); await sleep(3000);
  const chips=[...d.querySelectorAll('#fila-chips [data-fila-filtro]')], lin=cod=>[...d.querySelectorAll('#filas-body tr')].find(t=>t.textContent.includes(cod));
  chk(chips.length===4&&['gente','processando','publicado','todas'].every(k=>chips.some(c=>c.dataset.filaFiltro===k)),'a Fila deveria ter 4 filtros (Precisam de você, CAMP Vision lendo, Publicadas, Todas): '+chips.length);
  chk(chips.find(c=>c.getAttribute('aria-pressed')==='true').dataset.filaFiltro==='gente','o filtro padrão deveria ser "Precisam de você" quando há o que fazer');
  chk(/para conferir/.test(txt('#fila-resumo'))&&/para importar/.test(txt('#fila-resumo')),'o resumo deveria dizer quantas listas estão em cada ponto: "'+txt('#fila-resumo')+'"');
  chk(d.querySelectorAll('#v-filas thead th').length===4&&!/Pasta no QNAP|Aprovação/.test(txt('#v-filas thead')),'a tabela deveria ter 4 colunas (Projeto, Situação, Atualizado, ação), sem "Pasta no QNAP" nem "Aprovação"');
  chk(!!d.querySelector('#filas-body details.fila-pasta'),'a pasta do QNAP deveria ficar recolhida dentro de cada linha');
  let l9001=lin('F003-P9001');
  chk(!!l9001&&/Faltam conferir/.test(l9001.textContent)&&!!l9001.querySelector('progress.pg')&&!!l9001.querySelector('[data-fila-ir="revisao"]')&&!l9001.querySelector('[data-fila-acao="aprovar"]'),'F003-P9001 deveria dizer que faltam conferir folhas, com a barra de andamento e o botão "Conferir folhas": "'+(l9001&&l9001.textContent.slice(0,140))+'"');
  const lq=lin('F026-P0001'); chk(!!lq&&!!lq.querySelector('[data-fila-acao="importar"]')&&/Importar/.test(lq.textContent),'uma lista em revisão sem folhas importadas (F026-P0001) deveria oferecer "Importar folhas": "'+(lq&&lq.textContent.slice(100,260))+'"');
  l9001.querySelector('[data-fila-ir="revisao"]').click(); await sleep(3400);
  chk(/projeto\/F003-P9001/.test(w.location.hash)&&!!d.getElementById('pj-revisao')&&/Revisão do lote/.test(txt('#pj-revisao')),'"Conferir folhas" deveria levar à página do projeto com a Revisão do lote: '+w.location.hash);
  const lid=(await J(adm,'/api/projetos/F003-P9001/revisao')).b.lotes[0].id; await J(adm,'/api/lotes/'+lid+'/conferir-todas',{method:'POST'});
  w.route_to('filas'); await sleep(2800); l9001=lin('F003-P9001');
  chk(/Falta aprovar o lote|Todas as/.test(l9001.textContent),'ao VOLTAR para a Fila a tela deve mostrar o dado de agora (e não o de quando você entrou): "'+l9001.textContent.slice(100,260)+'"');
  chk(/Falta aprovar o lote/.test(l9001.textContent)&&!!l9001.querySelector('[data-fila-acao="aprovar"]'),'com tudo conferido a lista deveria pedir "Aprovar lote": "'+l9001.textContent.slice(0,120)+'"');
  const bAp=l9001.querySelector('[data-fila-acao="aprovar"]'); if(bAp){bAp.click(); await sleep(3000)} else chk(false,'sem botão Aprovar; fase no servidor: '+JSON.stringify((await J(adm,'/api/filas')).b.filter(x=>x.projeto_codigo==='F003-P9001').map(x=>({fase:x.fase,t:x.itens_total,p:x.itens_pendentes,ap:x.aprovado_em}))));
  l9001=lin('F003-P9001');
  chk(/Lote aprovado/.test(l9001.textContent)&&!!l9001.querySelector('[data-fila-ir="publicar"]'),'depois de aprovar a lista deveria pedir "Publicar": "'+l9001.textContent.slice(0,120)+'"');
  const bPu=l9001&&l9001.querySelector('[data-fila-ir="publicar"]'); if(bPu){bPu.click(); await sleep(4500)}
  chk(/projeto\/F003-P9001/.test(w.location.hash)&&/Publicar/.test(txt('#d-title')),'"Publicar" deveria levar ao projeto e abrir o plano de publicação: '+w.location.hash+' / '+txt('#d-title')); w.closeDrawer(true);
  w.route_to('filas'); await sleep(2500); d.querySelector('[data-fila-filtro="processando"]').click(); await sleep(400);
  chk([...d.querySelectorAll('#filas-body tr[data-fase]')].every(t=>t.dataset.fase==='processando'),'o filtro "CAMP Vision lendo" deveria mostrar só listas em leitura');
  d.querySelector('[data-fila-filtro="todas"]').click(); await sleep(300);
  chk(d.querySelectorAll('#filas-body tr[data-fase]').length===(await J(adm,'/api/filas')).b.length,'o filtro "Todas" deveria mostrar todas as listas do servidor');
  await J(adm,'/api/lotes/'+lid+'/reabrir',{method:'POST'}); for(const it of (await J(adm,'/api/projetos/F003-P9001/detalhe')).b.itens) await J(adm,'/api/itens/'+it.codigo+'/revisao',{method:'POST',body:JSON.stringify({estado:'pendente'})}); }
// ---------- MENU POR TRABALHO e PRÓXIMO PASSO no topo do projeto ----------
{ w.confirm=()=>true;
  chk(JSON.stringify([...d.querySelectorAll('#nav .grp')].map(g=>g.textContent.trim()))===JSON.stringify(['Material novo','Pedidos','Acervo','Sistema']),'o menu deveria ter os grupos por trabalho: Material novo, Pedidos, Acervo, Sistema: '+[...d.querySelectorAll('#nav .grp')].map(g=>g.textContent.trim()));
  const grupo=nome=>{const g=[...d.querySelectorAll('#nav .grp')].find(x=>x.textContent.trim()===nome),r=[];for(let e=g&&g.nextElementSibling;e&&!e.classList.contains('grp');e=e.nextElementSibling)if(e.dataset.v)r.push(e.dataset.v);return r.join(',')};
  chk(grupo('Material novo')==='decisoes,filas,erros'&&grupo('Pedidos')==='solicitacoes,uso'&&grupo('Acervo')==='projetos,fundos,arquitetos,localizacao,etiquetas'&&grupo('Sistema')==='estacoes,auditoria,qualidade,config','cada grupo deveria ter os itens certos: '+['Material novo','Pedidos','Acervo','Sistema'].map(grupo).join(' | '));
  chk(txt('#nav [data-v="projetos"] kbd')==='7'&&txt('#nav [data-v="decisoes"] kbd')==='2'&&txt('#nav [data-v="filas"] kbd')==='3'&&txt('#nav [data-v="etiquetas"] kbd')==='T','os atalhos deveriam seguir a ordem do menu (Decisões 2, Filas 3, Projetos 7, Etiquetas T)');
  w.route_to('projeto/F003-P9001'); await sleep(3600);
  chk(!!d.querySelector('#pj-proximo .steps')&&[...d.querySelectorAll('#pj-proximo .steps span')].map(x=>x.textContent.trim().split(' ')[0]).join(',')==='Digitalizar,Enviar,Leitura,Importar,Conferir,Aprovar,Publicar','o topo do projeto deveria mostrar os 4 passos (Importar, Conferir, Aprovar, Publicar): "'+txt('#pj-proximo').slice(0,120)+'"');
  chk(/Conferir \d+\/\d+/.test(txt('#pj-proximo .steps .cur'))&&/Faltam conferir/.test(txt('#pj-proximo'))&&!!d.querySelector('#pj-proximo [data-pp="conferir"]'),'em conferência o passo atual deveria mostrar o andamento e o botão "Começar a conferir": "'+txt('#pj-proximo')+'"');
  chk(!/Fonte visual|reconhecidos no site/.test(txt('.project-source'))&&/folhas no painel/.test(txt('.project-source')),'a linha de números do projeto deveria falar de folhas no painel e no site, sem jargão: "'+txt('.project-source')+'"');
  d.querySelector('#pj-proximo [data-pp="conferir"]').click(); await sleep(2000);
  chk(/Revisar folha/.test(txt('#d-title')),'"Começar a conferir" deveria abrir a primeira folha pendente'); w.closeDrawer(true);
  w.route_to('projeto/F026-P0001'); await sleep(3600);
  chk(/Falta trazer as folhas/.test(txt('#pj-proximo'))&&!!d.querySelector('#pj-proximo [data-pp="importar"]')&&/Importar/.test(txt('#pj-proximo .steps .cur')),'um projeto com lote ainda não importado deveria pedir "Importar folhas" no passo 1: "'+txt('#pj-proximo')+'"'); }
// ---------- LISTA DE PROJETOS: situação, filtros, ordem e "limpar" ----------
{ w.limparSelecaoProjetos&&w.limparSelecaoProjetos(); w.route_to('projetos'); await sleep(3000);
  const R=(await J(adm,'/api/projetos/resumo')).b, chips=[...d.querySelectorAll('#proj-chips [data-proj-sit]')], linhas=()=>[...d.querySelectorAll('#projetos-body tr[data-nav]')];
  chk(chips.map(c=>c.dataset.projSit).join(',')==='todos,gente,publicado,nao_publicado,sem_folhas','a lista de projetos deveria ter 5 filtros de situação: '+chips.map(c=>c.dataset.projSit));
  chk(chips.every(c=>Number(c.querySelector('b').textContent.replace(/\D/g,''))===R[c.dataset.projSit]),'as contagens dos filtros deveriam bater com o servidor: '+JSON.stringify(R)+' / '+chips.map(c=>c.textContent.trim()).join(' | '));
  chk(d.querySelectorAll('#v-projetos thead th').length===6&&/Situação/.test(txt('#v-projetos thead'))&&!/Séries|Última atividade|Publicação/.test(txt('#v-projetos thead')),'a tabela deveria ter 5 colunas de conteúdo (Projeto, Fundo, Folhas, Situação, Atualizado), sem Séries nem Última atividade: "'+txt('#v-projetos thead')+'"');
  chk(linhas().length>0&&/P\d{4}/.test(linhas()[0].querySelector('td:nth-child(2) .code').textContent)&&!!linhas()[0].querySelector('td:nth-child(2) b'),'a coluna Projeto deveria juntar o código e o nome');
  d.querySelector('[data-proj-sit="gente"]').click(); await sleep(2000);
  chk(linhas().length===R.gente&&linhas().every(t=>/Conferir|Importar folhas|Aprovar lote|Pronto para publicar|Erro no CAMP Vision/.test(t.textContent)),'"Precisam de você" deveria mostrar só projetos com algo a fazer, cada um dizendo o quê: '+linhas().length+' de '+R.gente);
  chk(d.querySelector('[data-proj-sit="gente"]').getAttribute('aria-pressed')==='true'&&!d.getElementById('proj-limpar').hidden,'o filtro ativo deveria ficar marcado e aparecer "Limpar filtros"');
  const l9001=linhas().find(t=>t.textContent.includes('F003-P9001')); chk(!!l9001&&/Conferir \d+/.test(l9001.textContent),'F003-P9001 deveria aparecer como "Conferir N": "'+(l9001&&l9001.textContent.slice(0,140))+'"');
  w.limparSelecaoProjetos(); await w.selecionarTodosProjetosDoFiltro(); await sleep(900);
  chk(w.eval('PROJETOS_SELECIONADOS.size')===R.gente,'"Selecionar todos os resultados" deveria respeitar o filtro: '+w.eval('PROJETOS_SELECIONADOS.size')+' de '+R.gente); w.limparSelecaoProjetos();
  d.getElementById('proj-fundo').value='F003'; d.getElementById('proj-fundo').dispatchEvent(new w.Event('change',{bubbles:true})); await sleep(2000);
  chk(linhas().length>0&&linhas().every(t=>t.getAttribute('data-nav').startsWith('projeto/F003-')),'filtrar por fundo deveria mostrar só projetos do F003 (junto com a situação): '+linhas().map(t=>t.getAttribute('data-nav')).join(','));
  d.querySelector('[data-proj-sit="todos"]').click(); await sleep(1800); d.getElementById('proj-ordem').value='folhas'; d.getElementById('proj-ordem').dispatchEvent(new w.Event('change',{bubbles:true})); await sleep(1800);
  const nums=linhas().map(t=>Number(t.querySelector('td.num').textContent.replace(/\D/g,'')));
  chk(nums.length>1&&nums.every((n,i)=>i===0||nums[i-1]>=n),'ordenar por "Mais folhas" deveria listar da maior para a menor quantidade: '+nums.slice(0,8).join(','));
  d.getElementById('proj-limpar').click(); await sleep(2000);
  chk(d.getElementById('proj-fundo').value===''&&d.getElementById('proj-ordem').value==='codigo'&&d.getElementById('proj-q').value===''&&d.querySelector('[data-proj-sit="todos"]').getAttribute('aria-pressed')==='true'&&d.getElementById('proj-limpar').hidden===true,'"Limpar filtros" deveria voltar tudo ao padrão'); }
// ---------- AS LISTAS MOSTRAM O DADO DE AGORA ao voltar para elas (e não o de quando você entrou) ----------
{ w.route_to('projetos'); await sleep(2200); const antes=(await J(adm,'/api/projetos/resumo')).b;
  w.route_to('painel'); await sleep(1500);
  const novo=(await J(adm,'/api/projetos',{method:'POST',body:JSON.stringify({fundo_codigo:'F026',titulo:'Projeto criado só para provar a lista atualizada',ano:1980,confirmar_novo:true})})).b;
  w.route_to('projetos'); await sleep(2600);
  const depois=(await J(adm,'/api/projetos/resumo')).b, chipTodos=Number(d.querySelector('[data-proj-sit="todos"] b').textContent.replace(/\D/g,''));
  chk(depois.todos===antes.todos+1&&chipTodos===depois.todos,'ao voltar para Projetos a lista deveria mostrar o dado de agora (todos '+antes.todos+' -> '+depois.todos+'), mas o chip diz '+chipTodos);
  chk([...d.querySelectorAll('#projetos-body tr[data-nav]')].length>0,'a lista deveria ter linhas');
  w.route_to('erros'); await sleep(1800); const nErr=Number(txt('#n-err')||0); chk(!Number.isNaN(nErr),'Erros deveria carregar ao abrir');
  w.route_to('solicitacoes'); await sleep(1800); chk(!!d.querySelector('#v-solicitacoes tbody tr'),'Solicitações deveria carregar ao abrir');
  w.route_to('fundos'); await sleep(1800); chk(!!d.querySelector('#v-fundos tbody tr'),'Fundos deveria carregar ao abrir'); }
// ---------- [Auditoria P0-1] F5 ou link direto numa página de detalhe mostra a página COMPLETA ----------
{ const abrirEm=async hash=>{ const dx=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/'+hash,runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>adm.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}}); await sleep(4000); const t=sel=>(dx.window.document.querySelector(sel)||{textContent:''}).textContent.replace(/\s+/g,' ').trim(); const o={proj:t('#v-projeto'),fundo:t('#v-fundo'),item:t('#v-item')}; dx.window.close(); return o };
  let o=await abrirEm('#projeto/F003-P9001'); chk(o.proj.length>200&&o.proj.includes('Projeto de teste da revisão 9001'),'F5 em #projeto/... deveria mostrar o projeto, mas só há: "'+o.proj.slice(0,80)+'"');
  o=await abrirEm('#fundo/F003'); chk(o.fundo.length>200&&o.fundo.includes('Burle Marx'),'F5 em #fundo/... deveria mostrar o fundo, mas só há: "'+o.fundo.slice(0,80)+'"');
  o=await abrirEm('#item/F003-P9001-1972-S01-D00001'); chk(o.item.length>100&&o.item.includes('F003-P9001-1972-S01-D00001'),'F5 em #item/... deveria mostrar a folha, mas só há: "'+o.item.slice(0,80)+'"'); }
// ---------- [Auditoria P0-2] clicar numa linha abre o detalhe REAL (não o painel inventado do protótipo) ----------
{ const falso=()=>/Anotação interna|Relatório diário enviado|Responder por e-mail|Abrir contatos\.jpg|Marcar como corrigido|Abrir no Finder/.test(txt('#d-body')+' '+d.body.innerHTML.slice(0,0));
  chk(!/Relatório diário enviado por e-mail|Visível só para a equipe/.test(d.documentElement.innerHTML),'o painel falso do protótipo (histórico e anotação inventados) não deveria mais existir na página');
  w.route_to('filas'); await sleep(2000); const lf=d.querySelector('#v-filas tbody tr[data-nav]'); chk(!!lf&&/^projeto\//.test(lf.getAttribute('data-nav')),'a linha da Fila deveria abrir o projeto (data-nav)');
  w.route_to('solicitacoes'); await sleep(2000); const ls=d.querySelector('#v-solicitacoes tbody tr[data-abrir]');
  if(ls){ w.closeDrawer&&w.closeDrawer(true); ls.querySelector('td').click(); await sleep(1500); chk(txt('#d-title').length>0&&!falso(),'clicar numa Solicitação deveria abrir o pedido real, sem botões inventados: "'+txt('#d-title')+'"'); w.closeDrawer(true) }
  await w.carregarErros('todos'); await sleep(1200); const le=d.querySelector('#v-erros tbody tr[data-abrir]');
  if(le){ le.querySelector('td').click(); await sleep(1500); chk(txt('#d-title').length>0&&!falso(),'clicar num Erro deveria abrir o erro real, sem botões inventados: "'+txt('#d-title')+'"'); w.closeDrawer(true) }
  w.route_to('arquitetos'); await sleep(2000); const la=d.querySelector('#v-arquitetos tbody tr[data-abrir]');
  chk(!!la,'a linha de Arquitetos deveria abrir o detalhe real para admin (data-abrir)');
  if(la){ la.querySelector('td').click(); await sleep(1500); chk(txt('#d-title').length>0&&!falso(),'clicar num Arquiteto deveria abrir o cadastro real: "'+txt('#d-title')+'"'); w.closeDrawer(true) }
  w.route_to('localizacao'); await sleep(2000); const ll=d.querySelector('#v-localizacao tbody tr[data-abrir]');
  if(ll){ ll.querySelector('td').click(); await sleep(1500); chk(txt('#d-title').length>0&&!falso(),'clicar numa Localização deveria abrir a real: "'+txt('#d-title')+'"'); w.closeDrawer(true) } }
// ---------- [Auditoria P0-3] a caixa de seleção da lista de Projetos marca; não abre o projeto ----------
{ w.limparSelecaoProjetos(); w.route_to('projetos'); await sleep(2500); const h0=w.location.hash, cx=[...d.querySelectorAll('#projetos-body .proj-sel')];
  cx[0].click(); cx[1].click(); await sleep(300);
  chk(w.location.hash===h0&&w.eval('PROJETOS_SELECIONADOS.size')===2,'clicar na caixa deveria marcar sem navegar: hash '+h0+' -> '+w.location.hash+', selecionados='+w.eval('PROJETOS_SELECIONADOS.size'));
  const cel=d.querySelectorAll('#projetos-body .sel-cel')[2]; cel.click(); await sleep(300);
  chk(w.location.hash===h0&&w.eval('PROJETOS_SELECIONADOS.size')===3&&!!cel.querySelector('input').checked,'clicar na CÉLULA da caixa também deveria marcar sem navegar (selecionados='+w.eval('PROJETOS_SELECIONADOS.size')+')');
  chk(/3 selecionados/.test(txt('#proj-bulk-count')),'a barra deveria dizer "3 selecionados": "'+txt('#proj-bulk-count')+'"'); w.limparSelecaoProjetos();
  d.querySelector('#projetos-body tr[data-nav] b').click(); await sleep(800); chk(/^#projeto\//.test(w.location.hash),'clicar no nome deveria continuar abrindo o projeto: '+w.location.hash); w.route_to('painel'); }
// ---------- [Auditoria P0-4] os botões "Etiquetas" abrem a etiqueta do projeto/fundo/folha de ORIGEM (nunca a de outro fundo) ----------
{ const lab=()=>({f:d.getElementById('l-fundo').value,p:d.getElementById('l-proj').value,o:txt('#lab-origem'),aba:(d.querySelector('#lab-tabs .on')||{dataset:{}}).dataset.t});
  w.route_to('etiquetas/projeto/F003-P9001'); await sleep(3500); let L=lab();
  chk(L.f==='F003'&&L.p==='F003-P9001'&&L.aba==='projeto'&&/Etiqueta de: F003-P9001/.test(L.o),'etiquetas/projeto/F003-P9001 deveria abrir a etiqueta DESSE projeto: '+JSON.stringify(L));
  w.route_to('etiquetas/fundo/F026'); await sleep(2800); L=lab();
  chk(L.f==='F026'&&L.aba==='fundo'&&/Etiqueta de: F026/.test(L.o),'etiquetas/fundo/F026 deveria abrir a etiqueta do fundo F026: '+JSON.stringify(L));
  w.route_to('etiquetas/folha/F003-P9001-1972-S01-D00002'); await sleep(3500); L=lab();
  chk(L.f==='F003'&&L.p==='F003-P9001'&&L.aba==='documento','etiquetas/folha/<código> deveria abrir a aba de folha no projeto da folha: '+JSON.stringify(L));
  w.route_to('projeto/F003-P9001'); await sleep(3500); const bp=[...d.querySelectorAll('#v-projeto .act button')].find(x=>x.textContent.trim()==='Etiquetas');
  chk(!!bp&&/etiquetas\/projeto\/F003-P9001/.test(bp.getAttribute('onclick')),'o botão "Etiquetas" da página do projeto deveria levar o código do projeto: '+(bp&&bp.getAttribute('onclick')));
  w.route_to('fundo/F026'); await sleep(3000); const bf=[...d.querySelectorAll('#v-fundo .act button')].find(x=>/Etiqueta do fundo/.test(x.textContent));
  chk(!!bf&&/etiquetas\/fundo\/F026/.test(bf.getAttribute('onclick')),'o botão "Etiqueta do fundo" deveria levar o código do fundo: '+(bf&&bf.getAttribute('onclick')));
  const dx=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/#etiquetas',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>adm.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}}); await sleep(3500);
  const dd=dx.window.document; chk(dd.getElementById('l-fundo').value===''&&/Escolha o fundo/.test(dd.getElementById('lab-origem').textContent),'pelo menu lateral a etiqueta deveria abrir SEM fundo pré-escolhido (antes: sempre F014): "'+dd.getElementById('l-fundo').value+'" / "'+dd.getElementById('lab-origem').textContent+'"'); dx.window.close(); w.route_to('painel'); }
// ---------- [Auditoria P0-6] "Publicar" em lote: plano antes (quem publica, quem fica de fora e por quê) e execução que repete até acabar ----------
{ w.limparSelecaoProjetos(); w.eval("PROJETOS_SELECIONADOS.add('F003-P9001');PROJETOS_SELECIONADOS.add('F003-P9002')"); await w.acaoLoteProjetos('publicar'); await sleep(1500);
  chk(/Publicar 2 projetos/.test(txt('#d-title'))&&/serão publicados|será publicado/.test(txt('#d-body'))&&/ficam de fora|fica de fora/.test(txt('#d-body')),'o Publicar em lote deveria abrir o PLANO ("N serão publicados · M ficam de fora"): "'+txt('#d-title')+' / '+txt('#d-body').slice(0,160)+'"');
  chk(!/confirm/.test(String(w.acaoLoteProjetos).slice(0,200).split("'publicar'")[0]),'o lote não deveria mais confirmar com o confirm() nativo antes do plano'); w.closeDrawer(true); w.limparSelecaoProjetos();
  const fetchOrig=w.fetch; let chamadas=0; w.fetch=(u,o={})=>{ if(/\/api\/projetos\/lote$/.test(String(u))&&String(o.method||'GET').toUpperCase()==='POST'){ chamadas++; const corpo=chamadas===1?{ok:[{codigo:'F900-P0001'}],falhas:[],pendentes:['F900-P0002']}:{ok:[{codigo:'F900-P0002'}],falhas:[{codigo:'F900-P0003',erro:'Fundo com direitos restritos'}],pendentes:[]}; return Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>corpo}) } return fetchOrig(u,o) };
  w.openDrawer('Publicar 3 projeto(s)','plano do lote','<p>x</p>'); await w.executarLoteProjetos(['F900-P0001','F900-P0002','F900-P0003'],[{codigo:'F900-P0004',motivo:'Nenhuma folha conferida'}]); await sleep(1500); w.fetch=fetchOrig;
  chk(chamadas===2,'o lote deveria chamar de novo com os pendentes até acabar (2 chamadas), chamou '+chamadas);
  chk(/2 publicados · 2 sem publicar/.test(txt('#d-body'))&&/Fundo com direitos restritos/.test(txt('#d-body'))&&/Nenhuma folha conferida/.test(txt('#d-body')),'o resultado deveria dizer 2 publicados · 2 sem publicar, com o motivo de cada um: "'+txt('#d-body').slice(0,260)+'"'); w.closeDrawer(true); w.route_to('painel'); }
// ---------- [Auditoria P0-8] erro bloqueante em projeto PUBLICADO: pergunta o que fazer e avisa na página; o status do projeto não é mexido ----------
{ const g={estado:'no_ar',pode_agir:true,pode_despublicar:true,condicoes:[{id:'bloqueios',bloqueia:true,ok:false,texto:'Sem autoria divergente nem erros bloqueantes',detalhe:'1 erro bloqueante'}]};
  let h=w.avisoPubComBloqueio('F003-P9002',g);   // #95: a faixa fica fora da lista de requisitos (que é recolhida)
  chk(/Publicado com problema bloqueante em aberto/.test(h)&&/1 erro bloqueante/.test(h)&&/Ver erros/.test(h)&&/Despublicar/.test(h),'projeto PUBLICADO com erro bloqueante deveria mostrar a faixa vermelha com "Ver erros" e "Despublicar"');
  chk(!/Publicado com problema bloqueante/.test(w.avisoPubComBloqueio('F003-P9002',{...g,estado:'rascunho'})),'projeto em rascunho não deveria mostrar a faixa de "publicado com problema"');
  h=w.avisoPubComBloqueio('F003-P9002',{...g,pode_agir:false}); chk(/Publicado com problema/.test(h)&&!/Despublicar/.test(h),'quem não pode agir vê o aviso, mas sem o botão Despublicar');
  const fetchOrig=w.fetch, confirmOrig=w.confirm, chamadas=[]; let resposta=true, msg='';
  w.fetch=(u,o={})=>{ const m=String(o.method||'GET').toUpperCase(); if(m==='POST'&&/\/api\/erros$/.test(String(u))) return Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>({id:77,publicado_com_bloqueio:true,projeto:'F900-P0001'})}); if(m==='POST'&&/\/api\/projetos\/F900-P0001\/publicar$/.test(String(u))){chamadas.push(JSON.parse(o.body).acao);return Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>({ok:true})})} return fetchOrig(u,o) };
  w.confirm=m=>{msg=m;return resposta};
  const preencher=()=>{d.getElementById('ne-cod').value='F900-P0001';d.getElementById('ne-grav').value='bloqueia';const cat=d.getElementById('ne-cat');cat.value=cat.options[0].value;d.getElementById('ne-desc').value='folha de outro projeto'};
  preencher(); await w.criarErro(); await sleep(800);
  chk(/F900-P0001 está publicado/i.test(msg)&&chamadas.join()==='tirar_do_ar','ao relatar o erro num projeto publicado, "OK" deveria despublicar (chamadas: '+chamadas.join()+'): "'+msg.slice(0,80)+'"');
  chamadas.length=0; resposta=false; preencher(); await w.criarErro(); await sleep(800);
  chk(chamadas.length===0,'"Cancelar" deveria manter o projeto publicado (sem chamar tirar_do_ar): '+chamadas.join());
  w.fetch=fetchOrig; w.confirm=confirmOrig; w.closeModal&&w.closeModal(); }
// ---------- [Auditoria P0-5] o Painel inicial aparece sem esperar as estações (lentas); site em três estados ----------
{ const fetchOrig=w.fetch; w.fetch=(u,o={})=>/\/api\/estacoes(\?|$)/.test(String(u))?new Promise(r=>setTimeout(()=>r(fetchOrig(u,o)),2500)):fetchOrig(u,o);
  d.getElementById('v-painel').innerHTML=''; w.carregarPainel(); await sleep(900);
  chk(!!d.querySelector('#v-painel .ini-grid')&&!!d.getElementById('ini-tarefas')&&d.querySelectorAll('#ini-saude .ini-hskel').length>0,'o Painel deveria aparecer em menos de 1 s (saudação e "O que fazer agora"), com esqueleto na coluna "Está tudo funcionando?" enquanto as estações carregam');
  chk(!/QNAP desconectado/.test(txt('#ini-saude')),'enquanto verifica, o Painel não deveria alarmar "QNAP desconectado"');
  await sleep(3400); chk(!d.querySelector('#ini-saude .ini-hskel')&&/QNAP/.test(txt('#ini-saude')),'depois que as estações chegam, a coluna de saúde deveria ser preenchida: "'+txt('#ini-saude').slice(0,60)+'"'); w.fetch=fetchOrig;
  const R=w.siteRotulo, A=w.siteAlerta;
  chk(R({estado:'online',ms:800,ok:true}).txt==='online'&&R({estado:'lento',ms:7000,ok:true}).txt==='lento · 7,0 s'&&R({estado:'lento',ms:7000,ok:true}).cls==='a','site lento deveria aparecer amarelo "lento · 7,0 s", não offline: '+JSON.stringify(R({estado:'lento',ms:7000,ok:true})));
  chk(!A({estado:'sem_resposta',alerta:false,ok:false})&&A({estado:'sem_resposta',alerta:true,ok:false})&&A({ok:false})&&!A({ok:true}),'só "sem resposta" confirmada (alerta) vira alerta vermelho; servidor antigo sem estado continua valendo'); w.route_to('painel'); }
// ---------- [Auditoria P1-9] depois de gravar, a janela fecha SEM perguntar "alterações não salvas" (e a proteção continua para quem fecha sem salvar) ----------
{ const cOrig=w.confirm, asked=[]; w.confirm=m=>{asked.push(String(m));return true}; const perguntou=()=>asked.some(m=>/alterações não salvas/i.test(m));
  for(const f of ['salvarSolicitacao','salvarErro','salvarDireitos']) chk(/closeDrawer\(true\)/.test(String(w[f]))&&!/closeDrawer\(\)/.test(String(w[f])),f+' deveria fechar com closeDrawer(true) depois de gravar');
  chk(/limparAlteracoes\('drawer'\)/.test(String(w.alocar)),'alocar deveria limpar as alterações antes de reabrir a janela');
  const cat=d.getElementById('ne-cat').options[0].value;
  const er=(await (await adm.f('/api/erros',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codigo:'F003-P9001',gravidade:'corrigir',categoria:cat,descricao:'teste do fechar sem perguntar'})})).json());
  await w.carregarErros('todos'); await w.abrirErro(er.id); await sleep(300); w.marcarAlteracoes('drawer'); asked.length=0; await w.salvarErro(er.id); await sleep(600);
  chk(!perguntou(),'depois de salvar o Erro não deveria aparecer "Existem alterações não salvas": '+asked.join('|'));
  w.openDrawer('t','s','<input id="zz">'); w.marcarAlteracoes('drawer'); asked.length=0; w.closeDrawer(); await sleep(150);
  chk(perguntou(),'fechar a janela com alteração NÃO salva deveria continuar perguntando'); w.closeDrawer(true); w.confirm=cOrig; }
// ---------- [Auditoria P1-11] códigos inexistentes são recusados, com a mensagem no campo ----------
{ chk(d.getElementById('ne-cod').required&&d.getElementById('ne-desc').required,'código e descrição do "Relatar problema" deveriam estar marcados como obrigatórios');
  d.getElementById('ne-cod').value='F026-P9999'; d.getElementById('ne-grav').value='bloqueia'; d.getElementById('ne-cat').value=d.getElementById('ne-cat').options[0].value; d.getElementById('ne-desc').value='x';
  await w.criarErro(); await sleep(600); chk(/não existe/.test(txt('#ne-err')),'Relatar problema com código inexistente deveria mostrar "não existe" no próprio formulário: "'+txt('#ne-err')+'"'); w.closeModal&&w.closeModal();
  w.route_to('localizacao'); await sleep(2000); const tl=d.querySelector('#v-localizacao tbody tr[data-abrir]');
  if(tl){ const lid=+tl.getAttribute('data-abrir').split(':')[1]; await w.verLocalizacao(lid); await sleep(500); d.getElementById('al-proj').value='F099-P9999'; await w.alocar(lid); await sleep(600);
    chk(/não existe/.test(txt('#al-msg')),'Alocar com projeto inexistente deveria dizer "não existe" embaixo do campo: "'+txt('#al-msg')+'"'); w.closeDrawer(true) } w.route_to('painel'); }
// ---------- [Auditoria P1-13] busca global: sem acento, Enter que abre, dica que não cobre o texto ----------
{ const q=d.getElementById('q'), digita=async v=>{q.value=v;q.dispatchEvent(new w.Event('input',{bubbles:true}));await sleep(900)}, enter=()=>q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await digita('taruma'); const rs=[...d.querySelectorAll('#qres [data-search-index]')];
  chk(rs.some(x=>/F026-P0001/.test(x.textContent)),'"taruma" (sem acento) deveria achar a Casa Tarumã: '+rs.map(x=>x.textContent.slice(0,40)).join(' | '));
  chk(d.querySelector('.search').classList.contains('tem-texto'),'com texto digitado a dica "F0xx-P000x" deveria ficar escondida (classe tem-texto)');
  q.value='F026-P0001'; q.dispatchEvent(new w.Event('input',{bubbles:true})); enter(); await sleep(900);
  chk(w.location.hash==='#projeto/F026-P0001','"F026-P0001" + Enter deveria abrir o projeto direto: '+w.location.hash);
  await digita('casa taruma'); enter(); await sleep(900);
  chk(/^#(projeto|fundo|item)\//.test(w.location.hash)&&!/#projeto\/F026-P0001$/.test('')||/^#(projeto|fundo|item)\//.test(w.location.hash),'Enter sem escolher deveria abrir o primeiro resultado: '+w.location.hash);
  q.value=''; q.closest('.search').classList.remove('tem-texto'); w.route_to('painel'); }
// ---------- [Auditoria P1-10] permissões: cada papel só vê os botões e telas que pode usar (tabela única PODE) ----------
{ const abrir=async(cli,hash)=>{const dx=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/'+hash,runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>cli.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}});await sleep(3800);return dx};
  const visivel=(dd,sel)=>[...dd.querySelectorAll(sel)].some(e=>!e.hidden);
  let dx=await abrir(ope,'#fundos'), dd=dx.window.document;
  chk(!visivel(dd,'[data-pode="fundo.reservar"]')&&visivel(dd,'[data-pode="fundos.exportar"]'),'operador não deveria ver "Reservar próximo código", mas vê "Exportar fundos.json"');
  chk([...dd.querySelectorAll('[data-pode]')].length>0&&[...dd.querySelectorAll('[data-pode]')].every(e=>e.hidden===!dx.window.pode(e.dataset.pode)),'todo botão com data-pode deveria seguir a tabela PODE'); dx.window.close();
  for(const r of ['uso','config','auditoria']){ dx=await abrir(ope,'#'+r); dd=dx.window.document; const nf=dd.getElementById('v-nao-encontrado'); chk(!!nf&&nf.classList.contains('on')&&/Sem acesso/.test(nf.textContent),'operador em #'+r+' deveria ver "Sem acesso": "'+(nf?nf.textContent.slice(0,80):'sem seção')+'"'); dx.window.close() }
  dx=await abrir(lei,'#filas'); dd=dx.window.document; chk(!visivel(dd,'[data-pode="qnap.varrer"]'),'leitura não deveria ver "Varrer QNAP"'); dx.window.close();
  dx=await abrir(lei,'#fundos'); dd=dx.window.document; chk(!visivel(dd,'[data-pode="fundos.exportar"],[data-pode="fundo.reservar"],[data-pode="fundo.sigla"]'),'leitura não deveria ver Exportar, Reservar nem "definir sigla"'); dx.window.close();
  chk(w.pode('rota.uso')&&w.pode('fundo.reservar')&&[...d.querySelectorAll('[data-pode="fundo.reservar"]')].every(e=>!e.hidden),'admin deveria continuar vendo e podendo tudo'); }
// ---------- [Auditoria P0-9] Enviar folhas repete até acabar (cria o dossiê no servidor); "Conferir as folhas" abre a 1ª folha; texto de imagem ----------
{ const fetchOrig=w.fetch, confOrig=w.confirm, toastOrig=w.toast, msgs=[]; let n=0,g=0; w.toast=m=>{msgs.push(String(m))}; w.confirm=()=>true;
  // [H4] enviar folhas virou TAREFA no servidor: uma chamada (?tarefa=1) e a tela acompanha o andamento real ("1 de 3", a folha atual) até o fim
  const resp=c=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>c});
  w.fetch=(u,o={})=>{ const U=String(u),M=String(o.method||'GET').toUpperCase();
    if(/\/api\/projetos\/F900-P0009\/subir-folhas\?tarefa=1$/.test(U)&&M==='POST'){ n++; return resp({tarefa_id:777}) }
    if(/\/api\/tarefas\/777$/.test(U)){ g++; const base={id:777,tipo:'enviar_folhas',titulo:'Enviar folhas de F900-P0009 ao site',projeto_codigo:'F900-P0009',ator:'rafael@camp.arq.br',total:3,iniciada_em:'2026-10-13 10:00:00',decorrido_s:g*2,falhas:[],log:[]};
      return resp(g<3?{...base,estado:'rodando',etapa:'Enviando as folhas',folha_atual:'F900-P0009-1970-S01-D00002',feitas:1}:{...base,estado:'ok',etapa:'fim',feitas:3,terminada_em:'2026-10-13 10:00:09',resultado:{mensagem:'F900-P0009: 3 folha(s) enviada(s) ao site como rascunho.'}}) }
    return fetchOrig(u,o) };
  const pr=w.subirFolhas('F900-P0009'); await sleep(1500); const andamento=txt('[data-aviso="enviar-F900-P0009"]'); await pr; await sleep(200); w.fetch=fetchOrig; w.confirm=confOrig; w.toast=toastOrig;
  chk(n===1,'[H4] "Enviar folhas ao site" deveria começar UMA tarefa no servidor (?tarefa=1), chamou '+n);
  chk(/1 de 3/.test(andamento)&&/D00002/.test(andamento)&&/Pode sair desta tela/.test(andamento),'[H4] enquanto roda, a tela deveria mostrar "1 de 3", a folha atual e que dá para sair: "'+andamento+'"');
  chk(msgs.some(m=>/3 folha\(s\) enviada/.test(m))&&/✔.*3 folhas enviadas/.test(txt('[data-aviso="enviar-F900-P0009"]')),'[H4] no fim, o resultado deveria ficar na tela e no aviso: '+msgs.join(' | ')+' / '+txt('[data-aviso="enviar-F900-P0009"]'));
  w.route_to('projeto/F003-P9001'); await sleep(3500);
  const pend=(w.ITENS_PJ||[]).find(x=>x.lote_id&&x.revisao==='pendente');
  if(pend){ w.acaoCondicao('revisao','F003-P9001'); await sleep(1500); chk(/Revisar folha/.test(txt('#d-title')),'"Conferir as folhas" (condição revisao) deveria abrir a primeira folha pendente: "'+txt('#d-title')+'"'); w.closeDrawer(true) }
  chk(!/no site/.test(w.eval("semImagemHTML()")),'o texto de folha sem imagem não deveria dizer "no site": '+w.eval("semImagemHTML()").replace(/<[^>]+>/g,' ')); w.route_to('painel'); }
// ---------- [Auditoria P0-10] publicar é uma TAREFA em segundo plano: a tela mostra o progresso real e nunca "desiste" ----------
{ const H=w.tarefaPubHTML, txtH=h=>h.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
  const rodando={estado:'rodando',etapa:'folhas',feitas:3,total:5,folha_atual:'F900-P0001-1970-S01-D00004',s_por_folha:25,faltam_s:50,falhas:[],log:[{em:'2026-10-10 00:54:51',texto:'Dossiê criado no site'}]};
  let h=txtH(H('F900-P0001',rodando));
  chk(/3 de 5/.test(h)&&/agora: F900-P0001-1970-S01-D00004/.test(h)&&/cerca de 25 s por folha/.test(h)&&/faltam cerca de 50 s/.test(h)&&/Dossiê criado no site/.test(h)&&/Você pode fechar esta janela/.test(h),'a tarefa rodando deveria mostrar "3 de 5", a folha atual, ~25 s por folha, o que falta, o histórico e que dá para fechar: '+h.slice(0,260));
  chk(/✔ Criar a página do projeto no site/.test(h)&&/⏳ Enviar as folhas/.test(h)&&/→ Liberar/.test(h),'os passos deveriam estar com ✔ (feito), ⏳ (agora) e → (adiante): '+h.slice(0,200));
  h=txtH(H('F900-P0001',{...rodando,estado:'falhou',etapa:'folhas',folha_atual:null,falhas:[{codigo:'F900-P0001-1970-S01-D00002',erro:'WordPress recusou a imagem'}],resultado:{ok:false,mensagem:'1 folha não subiu ao site; nada foi publicado.'}}));
  chk(/não terminou/.test(h)&&/F900-P0001-1970-S01-D00002 WordPress recusou a imagem/.test(h)&&/Tentar de novo \(continua de onde parou\)/.test(h)&&/✖ Enviar as folhas/.test(h),'a tarefa que falhou deveria dizer qual folha e por quê, com "Tentar de novo (continua de onde parou)": '+h.slice(0,240));
  h=txtH(H('F900-P0001',{estado:'ok',etapa:'fim',feitas:5,total:5,falhas:[],log:[],resultado:{ok:true,mensagem:'Dossiê + 5 folhas publicados.'},decorrido_s:65}));
  chk(/✔ Dossiê \+ 5 folhas publicados\./.test(h)&&/Levou 1 min 5 s/.test(h)&&!/⏳/.test(h)&&/Fechar/.test(h),'a tarefa pronta deveria dizer o resultado e o tempo total: '+h.slice(0,200));
  // acompanhamento de verdade (respostas simuladas): rodando -> pronto; fechar a janela no meio não quebra nada
  const fetchOrig=w.fetch; let gets=0; const R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j});
  w.fetch=(u,o={})=>{ if(/\/publicar-tudo\?tarefa=1$/.test(String(u)))return R({tarefa_id:9}); if(/\/api\/tarefas\/9$/.test(String(u))){gets++;return R(gets===1?{...rodando,id:9}:{id:9,estado:'ok',etapa:'fim',feitas:5,total:5,falhas:[],log:[],resultado:{ok:true,mensagem:'Dossiê + 5 folhas publicados.'},decorrido_s:20})} return fetchOrig(u,o) };
  w.openDrawer('Publicar','F900-P0001','<div class="act"><button id="pub-go" data-pub-go="F900-P0001">Publicar agora</button></div><div id="pub-prog"></div>');
  const pronto=w.executarPublicacaoGuiada('F900-P0001'); await sleep(700);
  chk(/3 de 5/.test(txt('#d-body'))&&!/demorou demais|não deu/.test(txt('#d-body')),'durante o envio a janela deveria mostrar o progresso real (3 de 5), nunca "demorou demais": "'+txt('#d-body').slice(0,120)+'"');
  w.closeDrawer(true); await pronto; await sleep(300);
  chk(gets>=2,'fechar a janela no meio NÃO deveria parar o acompanhamento (consultou '+gets+' vez(es))');
  // reabrir no meio: volta ao acompanhamento, não ao plano
  w.fetch=(u,o={})=>{ if(/\/api\/projetos\/F900-P0002\/tarefa$/.test(String(u)))return R({tarefa:{...rodando,id:11}}); if(/\/api\/tarefas\/11$/.test(String(u)))return R({id:11,estado:'ok',etapa:'fim',feitas:5,total:5,falhas:[],log:[],resultado:{ok:true,mensagem:'Pronto.'},decorrido_s:9}); return fetchOrig(u,o) };
  await w.abrirPublicacaoGuiada('F900-P0002'); await sleep(300);
  chk(!!d.querySelector('[data-pub-tarefa="F900-P0002"]')&&!/Publicar agora/.test(txt('#d-body')),'reabrir a janela com a tarefa rodando deveria voltar ao acompanhamento, não ao plano: "'+txt('#d-body').slice(0,100)+'"'); await sleep(2500); w.closeDrawer(true);
  // faixa "Publicando…" na página do projeto
  let terminou=false; w.fetch=(u,o={})=>/\/api\/projetos\/F003-P9001\/tarefa$/.test(String(u))?R({tarefa:terminou?null:{...rodando,id:13}}):/\/api\/tarefas\/13$/.test(String(u))?R(terminou?{id:13,estado:'ok',etapa:'fim',feitas:5,total:5,falhas:[],log:[],resultado:{ok:true,mensagem:'Pronto.'}}:{...rodando,id:13}):fetchOrig(u,o);
  w.route_to('projeto/F003-P9001'); await sleep(3800);
  chk(!!d.querySelector('#pj-proximo .pp-tarefa')&&/Publicando… 3 de 5/.test(txt('#pj-proximo'))&&!!d.querySelector('#pj-proximo [data-pub-abrir]'),'a página do projeto deveria avisar "Publicando… 3 de 5" com o botão Acompanhar: "'+txt('#pj-proximo').slice(0,120)+'"');
  terminou=true; await sleep(2600); w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [Folha retida] na conferência dá para NÃO publicar uma folha: ela fica no painel, mas nunca vai ao site ----------
{ w.route_to('projeto/F003-P9001'); await sleep(3500); const pend=(w.ITENS_PJ||[]).find(x=>x.lote_id&&x.revisao==='pendente');
  if(pend){ await w.abrirRevisaoItem(pend.codigo); await sleep(1200);
    chk(!!d.querySelector('#d-body details.rev-reter')&&!!d.querySelector('#d-body [data-rev-item="reter"]')&&/Não publicar esta folha/.test(txt('#d-body')),'a janela de conferência deveria ter a opção "Não publicar esta folha"');
    d.getElementById('rv-motivo').value='foto de pessoa';
    const fetchOrig=w.fetch; let corpo=null; w.fetch=(u,o={})=>{ if(/\/api\/itens\/[^/]+\/retencao$/.test(String(u))&&String(o.method||'GET').toUpperCase()==='POST'){corpo=JSON.parse(o.body);return Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>({ok:true,retida:corpo.retida})})} return fetchOrig(u,o) };
    d.querySelector('#d-body [data-rev-item="reter"]').click(); await sleep(1500); w.fetch=fetchOrig;
    chk(!!corpo&&corpo.retida===true&&corpo.motivo==='foto de pessoa','"Reter esta folha" deveria enviar retida=true com o motivo: '+JSON.stringify(corpo));
    const it=(w.ITENS_PJ||[]).find(x=>x.codigo===pend.codigo); chk(!!it&&it.retida===1&&it.revisao==='conferida','a folha deveria ficar retida e conferida na tela');
    await w.abrirRevisaoItem(pend.codigo); await sleep(800);
    chk(/Retida/.test(txt('#d-body'))&&/não vai ao site/.test(txt('#d-body'))&&!!d.querySelector('#d-body [data-rev-item="liberar"]')&&/Motivo: foto de pessoa/.test(txt('#d-body'))&&!d.querySelector('#d-body [data-rev-item="reter"]'),'folha retida deveria mostrar "Retida", o motivo e "Voltar a publicar", sem oferecer reter de novo: "'+txt('#d-body').slice(0,200)+'"');
    chk(/retida/.test(w.tagRevisao('conferida',1)),'o cartão da folha retida deveria ter a etiqueta "retida"'); w.closeDrawer(true) }
  w.route_to('painel'); }
// ---------- [H1] caixa "Como funciona esta página": 1ª visita aberta, "Entendi" fecha e grava POR PESSOA, "?" reabre, versão nova volta com "Novo" ----------
{ const paginas=['painel','decisoes','filas','erros','solicitacoes','uso','projetos','fundos','arquitetos','localizacao','etiquetas','estacoes','auditoria','config'];
  for(const k of [...paginas,'projeto','fundo','item']) await J(adm,'/api/auth/eu/preferencias',{method:'PUT',body:JSON.stringify({chave:'ajuda.'+k,valor:null})});
  await w.carregarPreferenciasAjuda(); const sem=[];
  for(const k of paginas){ w.route_to(k); await sleep(500); const b=d.querySelector('#v-'+k+' > .ajuda-caixa'); if(!b||!/Como funciona esta página/.test(b.textContent)||!/Para que serve/.test(b.textContent)||!b.querySelector('ol li')||b.getAttribute('role')!=='note') sem.push(k) }
  chk(sem.length===0,'a caixa "Como funciona esta página" deveria aparecer na 1ª visita de toda página; faltou em: '+sem.join(', '));
  for(const [rota,k] of [['projeto/F003-P9001','projeto'],['fundo/F003','fundo'],['item/F003-P9001-1972-S01-D00001','item']]){ w.route_to(rota); await sleep(3500); chk(!!d.querySelector('#v-'+k+' > .ajuda-caixa'),'a caixa deveria aparecer também na página de '+k+' (mesmo depois de a página desenhar o conteúdo)') }
  w.route_to('painel'); await sleep(700); d.querySelector('#v-painel [data-ajuda-fechar="painel"]').click(); await sleep(1000);
  chk(!d.querySelector('#v-painel > .ajuda-caixa'),'"Entendi" deveria fechar a caixa'); const pf=(await J(adm,'/api/auth/eu/preferencias')).b; chk(pf['ajuda.painel']===String(w.eval('AJUDA_PAGINAS.painel.v')),'"Entendi" deveria gravar no servidor a versão vista: '+JSON.stringify(pf));
  const abrirJan=async(cli,hash)=>{const dx=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/'+hash,runScripts:'dangerously',pretendToBeVisual:true,beforeParse(x){x.fetch=(u,o={})=>cli.f(u,o);x.Element.prototype.scrollTo=()=>{};x.confirm=()=>true;x.alert=()=>{};x.console.error=()=>{}}});await sleep(3800);return dx};
  let dx=await abrirJan(adm,'#painel'); chk(!dx.window.document.querySelector('#v-painel > .ajuda-caixa'),'depois do F5 (ou em outro computador) a caixa que a pessoa já fechou deveria continuar fechada'); dx.window.close();
  dx=await abrirJan(ope,'#painel'); chk(!!dx.window.document.querySelector('#v-painel > .ajuda-caixa'),'outra pessoa (operador) deveria ver a caixa aberta: a preferência é por PESSOA'); dx.window.close();
  w.route_to('painel'); await sleep(500); w.abrirAjuda(); await sleep(400); chk(!!d.querySelector('#v-painel > .ajuda-caixa'),'"?" deveria reabrir a caixa'); await sleep(500); chk(!!d.querySelector('#v-painel > .ajuda-caixa'),'a caixa reaberta pelo "?" não deveria sumir sozinha');
  d.querySelector('#v-painel [data-ajuda-fechar="painel"]').click(); await sleep(700); const vAtual=w.eval('AJUDA_PAGINAS.painel.v'); w.eval("AJUDA_PAGINAS.painel.v="+(vAtual+1)); w.garantirCaixaAjuda(); await sleep(300);
  chk(!!d.querySelector('#v-painel > .ajuda-caixa')&&/Novo/.test(txt('#v-painel > .ajuda-caixa h2')),'texto com versão nova deveria voltar a aparecer, com a etiqueta "Novo"'); w.eval("AJUDA_PAGINAS.painel.v="+vAtual); w.route_to('painel'); }
// ---------- [H3] telas vazias que ensinam e erro que NÃO vira "vazio" ----------
{ const v=w.vazioHTML('Nada aqui','Quando houver, aparece nesta lista.','<button id="vz-b">Começar</button>');
  chk(/Nada aqui/.test(v)&&/Quando houver/.test(v)&&/id="vz-b"/.test(v)&&/role="status"/.test(v),'vazioHTML deveria trazer título, explicação e o botão para começar');
  const fetchOrig=w.fetch,R=(j,ok=true,st=200)=>Promise.resolve({ok,status:st,statusText:'x',json:async()=>j});
  w.fetch=(u,o={})=>/\/api\/erros\?/.test(String(u))?R([]):/\/api\/localizacoes$/.test(String(u))?R([]):fetchOrig(u,o);
  w.route_to('erros'); await sleep(900); chk(/Nenhum problema nesta situação/.test(txt('#v-erros tbody'))&&!!d.querySelector('#v-erros tbody [onclick*="m-erro"]'),'Erros vazio deveria explicar e oferecer "Relatar problema": "'+txt('#v-erros tbody').slice(0,140)+'"');
  w.route_to('localizacao'); await sleep(900); chk(/Ainda não há caixas, gavetas ou tubos/.test(txt('#loc-body'))&&!!d.querySelector('#loc-body [onclick*="m-loc"]'),'Localização vazia deveria oferecer "Nova localização": "'+txt('#loc-body').slice(0,140)+'"');
  w.fetch=(u,o={})=>/\/api\/erros\?/.test(String(u))?R({detail:'servidor caiu'},false,500):fetchOrig(u,o);
  w.route_to('erros'); await sleep(900); chk(/Não consegui carregar os problemas/.test(txt('#v-erros tbody'))&&!/Nenhum problema nesta situação/.test(txt('#v-erros tbody')),'com a API em erro a lista NÃO pode dizer "vazio": "'+txt('#v-erros tbody').slice(0,140)+'"');
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [H5] O caminho do material: os mesmos 7 nomes, na mesma ordem ----------
{ const h=w.caminhoMaterialHTML(4,' 3/14'),dd=d.createElement('div'); dd.innerHTML=h; const sp=[...dd.querySelectorAll('.steps.caminho span')];
  chk(sp.map(x=>x.firstChild.textContent.trim()).join(',')==='Digitalizar,Enviar ao QNAP,Leitura,Importar,Conferir 3/14,Aprovar,Publicar','o caminho deveria ter os 7 passos oficiais na ordem: '+sp.map(x=>x.textContent).join(' | '));
  chk(dd.querySelectorAll('span.done').length===4&&dd.querySelectorAll('span.cur').length===1&&/Conferir 3\/14/.test(dd.querySelector('span.cur').textContent)&&/você está aqui/.test(dd.querySelector('span.cur').textContent),'4 feitos, 1 atual com "3/14" e "você está aqui"');
  w.route_to('caminho'); await sleep(500); chk(d.querySelectorAll('#v-caminho-corpo details').length===7&&/Leva alguns minutos por pasta/.test(txt('#v-caminho-corpo'))&&d.querySelectorAll('#v-caminho-corpo .steps.caminho span').length===7,'a página #caminho deveria explicar os 7 passos');
  w.route_to('projeto/F003-P9001'); await sleep(3500); chk(d.querySelectorAll('#pj-proximo .steps.caminho span').length===7,'a página do projeto deveria mostrar o caminho de 7 passos com "você está aqui"'); w.route_to('painel'); }
// ---------- [H2] glossário: página com busca e balão no ponto de uso ----------
{ chk(w.eval('GLOSSARIO.length')>=22,'o glossário deveria ter pelo menos os 22 termos');
  w.route_to('glossario'); await sleep(500); const n=d.querySelectorAll('#gl-lista .gl-item').length; w.filtrarGlossario('rascunho'); const vis=[...d.querySelectorAll('#gl-lista .gl-item')].filter(e=>!e.hidden).length; w.filtrarGlossario('');
  chk(n>=22&&vis>=1&&vis<n,'a busca do glossário deveria reduzir a lista ('+vis+' de '+n+')');
  const c=w.comTermos('O dossiê e o lote, depois outro lote.'); chk((c.match(/<abbr class="termo"/g)||[]).length===2&&!/<abbr[^>]*>outro lote/.test(c)&&(c.match(/>lote</g)||[]).length===1,'só a 1ª ocorrência de cada termo vira balão: '+c);
  chk(!/<abbr/.test(w.comTermos('&lt;script&gt;')),'texto sem termo não vira balão');
  w.route_to('filas'); await sleep(900); const ab=d.querySelector('#v-filas .ajuda-caixa abbr.termo'); chk(!!ab,'a caixa da página deveria ter termos do glossário em balão');
  if(ab){ ab.click(); await sleep(200); chk(!!d.getElementById('termo-pop')&&/Ver no glossário/.test(txt('#termo-pop'))&&txt('#termo-pop').length>40,'clicar no termo deveria abrir o balão com a definição e o link do glossário'); d.body.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true})); await sleep(150); chk(!d.getElementById('termo-pop'),'Esc deveria fechar o balão') }
  w.route_to('painel'); }
// ---------- [H9] janela Revisar folha: progresso, aviso da última, atalhos, campo alterado, tipos na ordem de uso ----------
{ w.route_to('projeto/F003-P9001'); await sleep(3500); const L=(w.ITENS_PJ||[]).filter(x=>x.lote_id);
  if(L.length>=2){ const a=L[0]; await w.abrirRevisaoItem(a.codigo); await sleep(1200);
    chk(/Folha 1 de \d+ · \d+ conferidas?/.test(txt('#d-body .rev-prog'))&&!!d.querySelector('#d-body .rev-prog progress'),'a janela deveria mostrar "Folha 1 de N · X conferidas" com barra: "'+txt('#d-body .rev-prog')+'"');
    const ops=[...d.querySelectorAll('#rv-tipo option')].map(o=>o.value).filter(Boolean); const rk=v=>{const i=['planta','corte','eleva','fachada','perspectiva','detalhe','implanta'].findIndex(p=>v.toLowerCase().startsWith(p));return i<0?99:i};
    chk(ops.length===0||ops.every((v,i)=>i===0||rk(ops[i-1])<=rk(v)),'os tipos deveriam vir na ordem de uso (Planta, Corte, …): '+ops.slice(0,6).join(', '));
    const inp=d.getElementById('rv-folha'); inp.value=(inp.value||'')+'X'; inp.dispatchEvent(new w.Event('input',{bubbles:true})); chk(inp.closest('.rev-campo').classList.contains('alterado'),'campo mudado deveria ganhar a marca "alterado"');
    inp.value=inp.defaultValue; inp.dispatchEvent(new w.Event('input',{bubbles:true})); chk(!inp.closest('.rev-campo').classList.contains('alterado'),'voltando ao valor original a marca deveria sumir');
    d.activeElement&&d.activeElement.blur(); d.body.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})); await sleep(1200);
    chk((d.getElementById('d-sub')||{}).textContent===L[1].codigo,'a seta → deveria abrir a próxima folha ('+L[1].codigo+'), abriu "'+txt('#d-sub')+'"');
    d.body.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true})); await sleep(1200);
    chk((d.getElementById('d-sub')||{}).textContent===a.codigo,'a seta ← deveria voltar à folha anterior');
    // a última pendente: aviso e tela de conclusão
    const salvas=L.map(x=>x.revisao); L.forEach((x,i)=>{if(i<L.length-1)x.revisao='conferida'}); const ult=L[L.length-1]; ult.revisao='pendente';
    await w.abrirRevisaoItem(ult.codigo); await sleep(1200); chk(/É a última/.test(txt('#d-body .rev-ultima')),'na última folha pendente deveria avisar "É a última"');
    w.concluirConferencia(); await sleep(300); chk(/Conferência concluída/.test(txt('#d-title'))&&/Era a última\. \d+ de \d+ folhas conferidas/.test(txt('#d-body'))&&!!d.getElementById('rev-fim'),'ao terminar deveria mostrar "Era a última. N de N conferidas" com o botão do próximo passo: "'+txt('#d-body').slice(0,120)+'"');
    L.forEach((x,i)=>{x.revisao=salvas[i]}); w.closeDrawer(true) }
  w.route_to('painel'); }
// ---------- [H8] aba Folhas: filtros rápidos e contador fixo que acompanha a conferência ----------
{ w.route_to('projeto/F003-P9001'); await sleep(3500); const L=(w.ITENS_PJ||[]).filter(x=>x.lote_id), bar=d.querySelector('.folhas-bar');
  chk(!!bar&&/Conferidas \d+ de \d+/.test(txt('.folhas-bar .fb-cont')),'a aba Folhas deveria ter a barra com "Conferidas X de N": "'+txt('.folhas-bar')+'"');
  if(bar&&L.length){ const pend=L.filter(x=>x.revisao==='pendente').length, tot=d.querySelectorAll('.project-series .thumb').length;
    d.querySelector('[data-fl-f="conferir"]').click(); await sleep(200); const vis=[...d.querySelectorAll('.project-series .thumb')].filter(t=>!t.hidden).length;
    chk(vis===pend,'o filtro "A conferir" deveria mostrar só as '+pend+' pendentes, mostrou '+vis);
    d.querySelector('[data-fl-f=""]').click(); await sleep(200); chk([...d.querySelectorAll('.project-series .thumb')].filter(t=>!t.hidden).length===tot,'"Todas" deveria mostrar tudo de novo');
    const antes=Number((txt('.folhas-bar .fb-cont').match(/(\d+) de/)||[])[1]); const p1=L.find(x=>x.revisao==='pendente');
    if(p1){ p1.revisao='conferida'; w.atualizarCartaoRevisao(p1.codigo); await sleep(300); const depois=Number((txt('.folhas-bar .fb-cont').match(/(\d+) de/)||[])[1]); chk(depois===antes+1,'conferir uma folha deveria subir o contador de '+antes+' para '+(antes+1)+', foi para '+depois); p1.revisao='pendente' } }
  w.route_to('painel'); }
// ---------- [H10] janela Publicar: avisos antes de publicar (não bloqueiam) e passos em linguagem simples ----------
{ const fetchOrig=w.fetch; const R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j});
  const plano={passos:[{id:'dossie',texto:'Criar a página do projeto no site (ainda escondida)',estado:'sera_feito'},{id:'publicar',texto:'Tornar a página e as 5 folhas visíveis para todos',estado:'sera_feito'}],bloqueios:[],avisos:[{id:'titulo',texto:'O título “T102_Edifício X” parece ter um prefixo de pasta. Como ficaria: “Edifício X”.'},{id:'vazios',texto:'Sem ano e sem cidade: a página fica sem essa informação.'}],pode_executar:true,ja_publicado:false,folhas_a_enviar:5,folhas_a_publicar:5,fora:{}};
  w.fetch=(u,o={})=>/\/api\/projetos\/F900-P0003\/tarefa$/.test(String(u))?R({tarefa:null}):/\/api\/projetos\/F900-P0003\/publicar\/plano$/.test(String(u))?R(plano):fetchOrig(u,o);
  await w.abrirPublicacaoGuiada('F900-P0003'); await sleep(600); w.fetch=fetchOrig; const b=txt('#d-body');
  chk(/Antes de publicar, confira/.test(b)&&/prefixo de pasta/.test(b)&&/Sem ano e sem cidade/.test(b)&&/você pode publicar mesmo assim/.test(b),'a janela deveria listar os avisos antes de publicar e dizer que dá para publicar mesmo assim: "'+b.slice(0,200)+'"');
  chk(!d.getElementById('pub-go').disabled,'avisos NÃO deveriam bloquear o botão Publicar agora');
  chk(/ainda escondida/.test(b)&&/visíveis para todos/.test(b)&&!/dossiê/i.test(b.replace(/Criar a página/,'')),'os passos deveriam usar linguagem simples (sem "dossiê"): "'+b.slice(0,200)+'"'); w.closeDrawer(true); }
// ---------- [H7] Filas: quem espera há mais tempo vem primeiro, "esperando há N" acima de 48 h, grupos por papel ----------
{ w.route_to('filas'); await sleep(1500); d.querySelector('#fila-chips [data-fila-filtro="gente"]').click(); await sleep(300); const L=w.eval('FILAS_SRV'), rows=[...d.querySelectorAll('#filas-body tr[data-fase]')];
  const ts=r=>{const c=r.querySelector('.code').textContent,l=L.find(x=>x.projeto_codigo===c&&x.fase===r.dataset.fase);return l?String(l.atualizado_em):''};
  let ordemOk=true; for(let i=1;i<rows.length;i++){ if(rows[i].dataset.fase===rows[i-1].dataset.fase&&rows[i].dataset.fase!=='publicado'&&ts(rows[i-1])>ts(rows[i])) ordemOk=false }
  chk(ordemOk,'dentro da mesma etapa, a lista que espera há mais tempo deveria vir primeiro');
  const OPER=['erro','importar','conferir'], fases=rows.map(r=>r.dataset.fase), temOp=fases.some(f=>OPER.includes(f)), temAd=fases.some(f=>!OPER.includes(f)), gh=d.querySelectorAll('#filas-body .fila-grupo').length;
  chk(temOp&&temAd?gh===2:gh===0,'com os dois tipos de tarefa deveria haver 2 subtítulos ("Para operador" e "Para admin"), senão nenhum; havia '+gh);
  const velho=w.espera48({fase:'importar',atualizado_em:'2020-01-01 00:00:00'}), agora=w.espera48({fase:'importar',atualizado_em:new Date().toISOString().slice(0,19).replace('T',' ')}), pub=w.espera48({fase:'publicado',atualizado_em:'2020-01-01 00:00:00'});
  chk(/tag a/.test(velho)&&/esperando há/.test(velho)&&!/esperando/.test(agora)&&!/esperando/.test(pub),'"esperando há N" só para quem depende de pessoa e passou de 48 h: velho='+velho.replace(/<[^>]+>/g,'')+' | agora='+agora+' | publicada='+pub);
  w.route_to('painel'); }
// ---------- [P2-16] eventos em português: nenhum tipo técnico (site_item_criado…) visível ----------
{ chk(w.rotuloEvento('site_item_criado')==='folha criada no site'&&w.rotuloEvento('revisao_aprovada')==='lote aprovado'&&w.rotuloEvento('evento_novo_qualquer')==='evento novo qualquer','rotuloEvento deveria traduzir os tipos conhecidos e, nos demais, trocar _ por espaço');
  chk(w.rotulo('formas_variantes')==='grafias no carimbo','"formas_variantes" deveria aparecer como "grafias no carimbo"');
  const cruas=w.eval('Object.keys(ROTULO_EVENTO).filter(k=>k.includes("_"))');
  w.route_to('painel'); await sleep(2500); let vis=txt('#v-painel'); chk(!cruas.some(k=>vis.includes(k)),'a Atividade do painel não deveria mostrar tipos técnicos: '+cruas.filter(k=>vis.includes(k)).join(', '));
  w.route_to('auditoria'); await sleep(2500); { const ths=[...d.querySelectorAll('#v-auditoria thead th')].map(x=>x.textContent.trim()), ix=ths.findIndex(x=>/^Evento/i.test(x)); vis=[...d.querySelectorAll('#au-body tr')].map(r=>(r.children[ix]||{}).textContent||'').join(' | '); chk(ix>=0&&vis.length>20&&!cruas.some(k=>vis.includes(k)),'a coluna Evento da Auditoria não deveria mostrar tipos técnicos: '+cruas.filter(k=>vis.includes(k)).join(', ')+' (coluna '+ix+' de '+ths.join('/')+')') }
  w.route_to('painel'); }
// ---------- [#156] "Mais ⋯" na ficha do projeto: mesclar, mover folhas, mover lote, descartar lote, despublicar ----------
{ w.route_to('projeto/F003-P9001'); await sleep(3500); const b=d.querySelector('[data-pj-mais]');
  chk(!!b,'admin deveria ver "Mais ⋯" na ficha do projeto');
  if(b){ b.click(); await sleep(300); chk(/Mais ações/.test(txt('#d-title'))&&d.querySelectorAll('#d-body .mais-acao').length===5,'"Mais ⋯" deveria listar as 5 ações: '+d.querySelectorAll('#d-body .mais-acao').length);
    d.querySelector('[data-mais="mesclar"]').click(); await sleep(300);
    chk(d.getElementById('mx-go').disabled&&/mudam de código/.test(txt('#d-body')),'"Mesclar" deveria explicar a consequência e só habilitar depois de marcar "Entendi"');
    const fetchOrig=w.fetch; let req=null; const R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j});
    w.fetch=(u,o={})=>{ if(/\/mesclar-em$|\/api\/itens\/mover$/.test(String(u))&&String(o.method||'').toUpperCase()==='POST'){req={u:String(u),b:JSON.parse(o.body)};return R({movidos:[{de:'a',para:'b'}],duplicatas:[],ignorados:[],lotes:[]})} return fetchOrig(u,o) };
    const marcar=()=>{const ok=d.getElementById('mx-ok');ok.checked=true;ok.dispatchEvent(new w.Event('change',{bubbles:true}))};
    d.getElementById('mx-dest').value='xyz'; marcar(); d.getElementById('mx-go').click(); await sleep(300);
    chk(!req&&/código do projeto de destino/.test(txt('#mx-res')),'código de destino inválido não deveria enviar nada e deveria explicar');
    d.getElementById('mx-dest').value='F003-P9002'; d.getElementById('mx-motivo').value='duplicado'; d.getElementById('mx-go').click(); await sleep(900);
    chk(!!req&&/F003-P9001\/mesclar-em$/.test(req.u)&&req.b.destino==='F003-P9002'&&req.b.motivo==='duplicado','Mesclar deveria enviar o destino e o motivo: '+JSON.stringify(req));
    req=null; w.route_to('projeto/F003-P9001'); await sleep(3500); d.querySelector('[data-pj-mais]').click(); await sleep(300); d.querySelector('[data-mais="mover"]').click(); await sleep(300);
    const cbs=d.querySelectorAll('.mx-it'); chk(cbs.length>0&&cbs.length===(w.ITENS_PJ||[]).length,'Mover folhas deveria listar todas as folhas com caixa de seleção ('+cbs.length+')');
    if(cbs.length){ cbs[0].checked=true; d.getElementById('mx-dest').value='f003-p9002'; marcar(); d.getElementById('mx-go').click(); await sleep(900);
      chk(!!req&&req.b.itens.length===1&&req.b.itens[0]===cbs[0].value&&req.b.destino==='F003-P9002','Mover deveria enviar só as folhas marcadas e o destino em maiúsculas: '+JSON.stringify(req)) }
    w.fetch=fetchOrig; w.closeDrawer(true) }
  w.route_to('painel'); }
// ---------- [#148] o que o CAMP Vision entregou: alerta da contagem, avisos, sugestões, relatório, decisões e orientação da folha ----------
{ const fetchOrig=w.fetch, R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j});
  w.route_to('projeto/F003-P9001'); await sleep(3500); const it0=(w.ITENS_PJ||[]).find(x=>x.lote_id); const cod=it0?it0.codigo:'F003-P9001-1972-S01-D00001', dD='D'+String(+cod.slice(-5));
  const S={existe:true,pacote_ilegivel:false,avisos:['D2 é quase de D1 — publicar D1'],retirados:[{codigo:'F003-P9001-1972-S01-D00009',motivo:'autoria divergente'}],propostas:{obras_na_pasta:[],sem_codigo_de_unidade:[],fotos_sem_obra:[]},
    sugestoes:[{campo:'titulo',sugerido:'Edifício Tarumã',atual:'P0001'}],capa_sugerida:cod,relatorio:{formato_ok:true,alerta_origem:'12 arquivo(s) na origem, mas 10 arquivado(s): 2 não chegaram ao acervo.',numeros:{origem:12,arquivados:10,documentos:10},texto:'1. Arquivos...',partes:[{n:1,titulo:'Arquivos na origem × registros na saída',itens:['12 arquivo(s) na origem, 10 arquivado(s)']},{n:4,titulo:'Autoria divergente e projeto divergente (não publicar)',itens:['D9: autoria divergente']},{n:5,titulo:'Orientação e série incertas',itens:[dD]},{n:6,titulo:'Folhas esperadas que faltam',itens:[]}]},
    decisoes:[{codigo:cod,acao:'nota',motivo:'conferir carimbo',por:'Rafa',em:'2026-10-10T09:07:32-03:00'}],orientacao:{texto:'incerta — conferir: '+dD,linhas:[],incertas:[dD]},releituras:[{quando:'2026-10-10T10-00',comparacao:{[cod]:{escala:{antes:'',agora:'1:100'}}}}]};
  w.fetch=(u,o={})=>/\/api\/lotes\/\d+\/saidas-cv$/.test(String(u))?R(S):fetchOrig(u,o);
  w.route_to('projeto/F003-P9001'); await sleep(3800); const b=txt('#pj-cv');
  chk(/O que o CAMP Vision entregou/.test(b)&&/Conferir a contagem/.test(b)&&/2 não chegaram/.test(b)&&/Avisos do CAMP Vision/.test(b)&&/Sugestões para o projeto \(1\)/.test(b)&&/Edifício Tarumã/.test(b)&&/hoje: P0001/.test(b),'a ficha deveria mostrar o alerta da contagem, os avisos e a sugestão de título: "'+b.slice(0,220)+'"');
  chk(/Retiradas pelo CAMP Vision \(1\)/.test(b)&&/Decisões registradas \(1\)/.test(b)&&/Relatório completo/.test(b)&&/Releituras: o que mudou \(1\)/.test(b)&&/escala: “” → “1:100”/.test(b),'deveria listar retiradas, decisões, relatório completo e o que mudou na releitura');
  if(it0){ await w.abrirRevisaoItem(cod); await sleep(1200); chk(/orientação incerta/.test(txt('#d-body .cv-folha'))&&/conferir carimbo/.test(txt('#d-body .cv-folha')),'a janela da folha deveria mostrar a orientação incerta e a decisão registrada dela: "'+txt('#d-body .cv-folha')+'"'); w.closeDrawer(true) }
  const dd=d.createElement('div'); dd.innerHTML=w.saidasCVHTML({...S,avisos:['<img src=x onerror=alert(1)>'],relatorio:{formato_ok:false,texto:'<b>novo formato</b>',partes:[]}});
  chk(!dd.querySelector('img')&&!dd.querySelector('pre b')&&/formato do relatório mudou/.test(dd.textContent)&&/<b>novo formato<\/b>/.test(dd.textContent),'texto vindo dos arquivos do CV2 deveria aparecer escapado, e o relatório em formato novo como texto cru');
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [#148 parte B] responder ao CAMP Vision: Usar/Ignorar, Aceitar/Recusar, Devolver à revisão (com motivo) ----------
{ const fetchOrig=w.fetch, R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j}); const reqs=[];
  const S={existe:true,lote_id:41,avisos:[],retirados:[{codigo:'F003-P9001-1972-S01-D00009',motivo:'autoria divergente'}],propostas:{obras_na_pasta:['Obra A (unidade 2)'],fotos_sem_obra:[]},sugestoes:[{campo:'titulo',sugerido:'Edifício Tarumã',atual:'P0001'}],respostas:{},relatorio:null,decisoes:[],orientacao:null,releituras:[]};
  w.fetch=(u,o={})=>{ if(/\/api\/lotes\/\d+\/saidas-cv$/.test(String(u)))return R(S); if(/\/saidas-cv\/resposta$/.test(String(u))){reqs.push(JSON.parse(o.body));return R({ok:true})} return fetchOrig(u,o) };
  w.route_to('projeto/F003-P9001'); await sleep(3800);
  const usar=d.querySelector('#pj-cv [data-cv-resp="sugestao"][data-acao="usar"]'), aceitar=d.querySelector('#pj-cv [data-cv-resp="proposta"][data-acao="aceitar"]'), dev=d.querySelector('#pj-cv [data-cv-devolver]');
  chk(!!usar&&!!aceitar&&!!dev,'deveria haver "Usar" na sugestão, "Aceitar" na proposta e "Devolver à revisão" na retirada (admin)');
  if(usar&&aceitar&&dev){ usar.click(); await sleep(400); chk(reqs[0]&&reqs[0].tipo==='sugestao'&&reqs[0].chave==='titulo'&&reqs[0].acao==='usar'&&reqs[0].valor==='Edifício Tarumã','"Usar" deveria enviar o campo e o valor sugerido: '+JSON.stringify(reqs[0]));
    w.route_to('projeto/F003-P9001'); await sleep(3800);
    d.querySelector('#pj-cv [data-cv-resp="proposta"][data-acao="aceitar"]').click(); await sleep(400); chk(reqs.some(r=>r.tipo==='proposta'&&r.chave==='obras_na_pasta:0'&&r.acao==='aceitar'),'"Aceitar" deveria registrar a proposta pelo grupo e índice');
    w.route_to('projeto/F003-P9001'); await sleep(3800); const n0=reqs.length;
    d.querySelector('#pj-cv [data-cv-devolver]').click(); await sleep(150); const box=d.querySelector('#pj-cv [data-cv-dev-box]');
    chk(box&&!box.hidden,'"Devolver à revisão" deveria abrir o campo de motivo na própria tela (sem prompt)');
    box.querySelector('[data-cv-resp="retirado"]').click(); await sleep(300); chk(reqs.length===n0,'sem motivo, a devolução NÃO deveria ser enviada');
    box.querySelector('input').value='o carimbo é do próprio arquiteto'; box.querySelector('[data-cv-resp="retirado"]').click(); await sleep(400);
    const dv=reqs[reqs.length-1]; chk(reqs.length===n0+1&&dv.tipo==='retirado'&&dv.acao==='devolver'&&dv.chave==='F003-P9001-1972-S01-D00009'&&/carimbo/.test(dv.motivo),'com motivo, a devolução deveria ser enviada com o código e o motivo: '+JSON.stringify(dv)) }
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [#152] Qualidade do CAMP Vision: por versão, por campo, por lote, gabarito ----------
{ const fetchOrig=w.fetch, R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j});
  chk(w.pode('rota.qualidade')&&!!d.querySelector('[data-v="qualidade"]'),'admin deveria ver "Qualidade do CAMP Vision" no menu');
  const Q={por_versao:[{versao:'2026-10-10-02+d4f9308',pct_aceito:50,total:4,lotes:1,folhas:2,custo_usd:0.006,custo_por_folha:0.003}],por_campo:[{versao:'2026-10-10-02+d4f9308',campo:'folha',rotulo:'Folha',iguais:1,corrigidos:1,preenchidos:0,pct_aceito:50,total:2}],por_lote:[{id:1,nome:'Tarumã',projeto_codigo:'F026-P0001',versao_cv2:'2026-10-10-02+d4f9308',folhas:2,custo_usd:0.006,tempo_s:3.3,aprovado:true}]};
  w.fetch=(u,o={})=>/\/api\/qualidade-cv$/.test(String(u))?R(Q):fetchOrig(u,o); w.route_to('qualidade'); await sleep(800); const b=txt('#qc-corpo');
  chk(/Por versão/.test(b)&&/50%/.test(b)&&/US\$ 0\.003/.test(b)&&/Por campo/.test(b)&&/Folha/.test(b)&&/Por lote/.test(b)&&/Tarumã/.test(b)&&/3 s/.test(b),'a página deveria mostrar o placar por versão, por campo e o custo por lote: "'+b.slice(0,200)+'"');
  chk((d.getElementById('qc-gabarito')||{}).getAttribute&&d.getElementById('qc-gabarito').getAttribute('href')==='/api/qualidade-cv/gabarito.csv','"Exportar gabarito" deveria baixar /api/qualidade-cv/gabarito.csv');
  w.fetch=(u,o={})=>/\/api\/qualidade-cv$/.test(String(u))?R({por_versao:[],por_campo:[],por_lote:[]}):fetchOrig(u,o); w.route_to('qualidade'); await sleep(800);
  chk(/Ainda não há folhas conferidas/.test(txt('#qc-corpo')),'sem dados, a página deveria explicar que os números aparecem depois da conferência');
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [#151] alertas por e-mail em Estações (admin): estado de cada assunto e log de envio ----------
{ const fetchOrig=w.fetch, R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j}); let verif=0;
  const A={estado:[{assunto:'qnap',critico:1,texto:'O QNAP está com 1% livre (10 GB).'},{assunto:'backup',critico:0,texto:'A última cópia tem 2 h.'}],envios:[{assunto:'qnap',tipo:'critico',para:'rafael@camp.arq.br',ok:1,enviado_em:'2026-10-13 10:00:00'},{assunto:'qnap',tipo:'suprimido',ok:1,enviado_em:'2026-10-13 10:10:00'},{assunto:'site',tipo:'critico',para:'rafael@camp.arq.br',ok:0,erro:'SMTP não configurado',enviado_em:'2026-10-13 10:20:00'}]};
  w.fetch=(u,o={})=>{ if(/\/api\/alertas$/.test(String(u)))return R(A); if(/\/api\/alertas\/verificar$/.test(String(u))){verif++;return R({envios:[]})} return fetchOrig(u,o) };
  w.route_to('estacoes'); await sleep(3200); const t2=txt('#al-painel');
  chk(/Alertas por e-mail/.test(t2)&&/QNAP quase cheio/.test(t2)&&/crítico/.test(t2)&&/CAMP Vision parado/.test(t2)&&/ainda não medido/.test(t2)&&/não enviado \(já avisado há menos de 6 h\)/.test(t2)&&/SMTP não configurado/.test(t2),'Estações deveria mostrar o estado de cada alerta e o log de envio: "'+t2.slice(0,220)+'"');
  const b=d.getElementById('al-verificar'); if(b){ b.click(); await sleep(400) } chk(verif===1,'"Verificar agora" deveria pedir a verificação ao servidor');
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [#149] cópia do acervo em Estações e quarentena do CAMP Vision ----------
{ const fetchOrig=w.fetch, R=x=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>x});
  w.fetch=(u,o={})=>/\/api\/replica$/.test(String(u))?R({configurada:true,nivel:'critico',gravado_em:'2026-10-09T02:00:00-03:00',idade_horas:100,texto:'A réplica do acervo parou: última cópia há 100 h.'}):fetchOrig(u,o);
  w.route_to('estacoes'); await sleep(3200); const t3=txt('#replica-painel');
  chk(/Cópia do acervo/.test(t3)&&/parada/.test(t3)&&/há 100 h/.test(t3)&&/Verde: menos de 36 h/.test(t3),'Estações deveria mostrar a cópia do acervo com a cor e a idade: "'+t3.slice(0,160)+'"');
  const q=w.quarentenaHTML({arquivos:2,gb:0.0,ultima_replica:null,aviso:'quarentena sem réplica: 0.0 GB'}).replace(/<[^>]+>/g,'');
  chk(/Quarentena de 100 - Scanners: 2 arquivo\(s\) · 0 GB/.test(q)&&/quarentena sem réplica/.test(q),'a quarentena do heartbeat deveria aparecer no cartão do CAMP Vision: '+q);
  w.fetch=fetchOrig; w.route_to('painel'); }
// ---------- [H11] decisão: os botões dizem a consequência e o aviso final diz o que acontece depois ----------
{ const f=String(w.abrirDecisao)+String(w.resolverDecisao); chk(/as folhas entram em/.test(f)&&/próximo número do fundo/.test(f)&&/CAMP Vision continua a leitura em até 2 min/.test(f),'os botões da decisão deveriam dizer a consequência ("as folhas entram em …") e o aviso final deveria dizer que o CAMP Vision continua'); }
// ---------- [Auditoria P1-12] fluxo do lote: um caminho só, do "Importar" ao "Publicado" ----------
{ w.PUB_G=w.PUB_G||{}; const PP={lote:{id:1,fase:'publicar',etapa:'revisao',itens_total:2,itens_pendentes:0,itens_conferidos:2},pode_operar:true,pode_agir:true};
  w.PUB_G['F900-P0001']={estado:'rascunho',pode_agir:true,condicoes:[{id:'direitos',bloqueia:true,ok:false,texto:'Direitos do fundo F900 autorizados',acao:{tipo:'direitos',rotulo:'Definir direitos do fundo',alvo:'F900'}}]};
  let h=w.proximoPassoHTML(PP,'F900-P0001');
  chk(/Definir direitos do fundo/.test(h)&&/falta resolver/i.test(h)&&!/data-pp="publicar"/.test(h),'com direitos faltando, o Próximo passo NÃO deveria oferecer "Publicar": deveria dizer o que falta e dar o botão que resolve');
  w.PUB_G['F900-P0001']={estado:'rascunho',pode_agir:true,condicoes:[{id:'autorizado',bloqueia:true,ok:false,texto:'Projeto autorizado para publicação'}]};
  h=w.proximoPassoHTML(PP,'F900-P0001'); chk(/data-pp="publicar"/.test(h),'sem bloqueio de pessoa, o Próximo passo deveria oferecer "Publicar" (a guiada autoriza sozinha)');
  h=w.proximoPassoSemLoteHTML('F900-P0001',{estado:'rascunho',pode_agir:true,condicoes:[]}); chk(/Pronto para publicar/.test(h)&&/data-pp="publicar"/.test(h),'projeto sem lote e sem pendência deveria mostrar "Pronto para publicar" com o botão');
  const pub=w.proximoPassoSemLoteHTML('F900-P0001',{estado:'no_ar',pode_agir:true,condicoes:[]}); chk(/Publicado/.test(pub)&&!/btn pri/.test(pub),'projeto publicado deveria dizer "Publicado", sem botão azul');
  chk(!/btn pri/.test(w.botoesPublicacao('F900-P0001',{pode_agir:true,estado:'rascunho',pode_despublicar:true})),'o painel Publicação não deveria ter um segundo botão azul "Publicar" (o único é o do Próximo passo)');
  w.history.replaceState(null,'','#projeto/F003-P9001'); w.openDrawer('Publicar','F003-P9001','<button id="pub-go">x</button>'); w.acaoCondicao('direitos','F003'); await sleep(1800);
  chk(w.PUB_VOLTAR==='F003-P9001'&&/PUB_VOLTAR/.test(String(w.salvarDireitos)),'definir direitos a partir da publicação guiada deveria lembrar de voltar a ela depois de salvar (PUB_VOLTAR)'); w.PUB_VOLTAR=null; w.closeDrawer(true);
  const fetchOrig=w.fetch; w.fetch=(u,o={})=>{const R=j=>Promise.resolve({ok:true,status:200,statusText:'OK',json:async()=>j}); if(/\/publicar-tudo\?tarefa=1$/.test(String(u)))return R({tarefa_id:7}); if(/\/api\/tarefas\/7$/.test(String(u)))return R({id:7,estado:'ok',etapa:'fim',feitas:2,total:2,folha_atual:null,log:[],falhas:[],resultado:{ok:true,mensagem:'2 registros publicados.'},decorrido_s:12,s_por_folha:6}); return fetchOrig(u,o)};
  w.openDrawer('Publicar','F900-P0001','<div class="act"><button id="pub-go" data-pub-go="F900-P0001">Publicar agora</button></div><div id="pub-prog"></div>'); await w.executarPublicacaoGuiada('F900-P0001'); await sleep(800); w.fetch=fetchOrig;
  chk(/Publicado/.test(txt('#d-title'))&&/2 registro/.test(txt('#d-body'))&&!d.getElementById('pub-go')&&!/Publicar agora/.test(txt('#d-body')),'depois de publicar, a janela deveria mostrar o resultado (sem "Publicar agora"): "'+txt('#d-title')+' / '+txt('#d-body').slice(0,80)+'"'); w.closeDrawer(true);
  const absOrig=w.abrirRevisaoItem; let abriu=null; w.abrirRevisaoItem=c=>{abriu=c};
  w.route_to('projeto/F003-P9001'); await sleep(3500); const antes=(w.ITENS_PJ||[]).filter(x=>x.lote_id&&x.revisao==='pendente');
  if(antes.length){ w.route_to('painel'); w.irDaFila('revisao','F003-P9001'); await sleep(4800); chk(abriu===antes[0].codigo,'"Conferir folhas" vindo da Fila deveria abrir a primeira folha pendente ('+antes[0].codigo+'), abriu: '+abriu) }
  w.abrirRevisaoItem=absOrig; w.route_to('painel'); }
// ---------- [Auditoria P2-16] textos em português: rótulos com acento, datas no fuso certo, plurais ----------
{ chk(w.rotulo('aguarda_orcamento')==='aguarda orçamento'&&w.rotulo('em_correcao')==='em correção'&&w.rotulo('decisao')==='decisão'&&w.rotulo('jpg_3000')==='JPG 3000 px'&&w.rotulo('projeto_errado')==='folha de outro projeto'&&w.rotulo('qualquer_coisa')==='qualquer coisa','rotulo() deveria traduzir os valores do banco e ter um fallback sem "_"');
  d.body.insertAdjacentHTML('beforeend','<div id="zpl">3 folha(s) · 1 folha(s) · 2 item(ns) · 1 item(ns) · 12 pendência(s) · fundo(s) · 1.250 registro(s)</div>'); await sleep(500);
  chk(txt('#zpl')==='3 folhas · 1 folha · 2 itens · 1 item · 12 pendências · fundos · 1.250 registros','os "(s)" deveriam virar plural/singular certo no texto visível: "'+txt('#zpl')+'"'); d.getElementById('zpl').remove();
  const sol=(await J(adm,'/api/solicitacoes?situacao=todos')).b.itens[0];
  if(sol){ await w.abrirSolicitacao(sol.id); await sleep(500); const opts=[...d.querySelectorAll('#es-sit option')].map(o=>o.textContent);
    chk(!opts.some(o=>/_/.test(o))&&(!opts.some(o=>/orcamento|credito|preparacao/.test(o))),'as situações do pedido deveriam ter acento e sem "_": '+opts.join('|'));
    chk(/\d{2}\/\d{2}\/\d{4}/.test(txt('#d-body'))&&!/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(txt('#d-body')),'a data do pedido deveria estar em dd/mm/aaaa no horário de São Paulo: "'+txt('#d-body').slice(0,120)+'"'); w.closeDrawer(true) } }
// ---------- [Auditoria P2-17] Novo projeto: o fundo não vem escolhido; "Criar projeto" nunca fica mudo ----------
{ d.getElementById('np-fundo').value='F026'; w.abrirNovoProjeto(); await sleep(500); const nf=d.getElementById('np-fundo');
  chk(nf.value===''&&/escolha o fundo/.test(nf.options[0].textContent)&&/escolha o fundo/.test(txt('#np-code')),'Novo projeto pela lista deveria abrir com o fundo VAZIO ("— escolha o fundo —"): "'+nf.value+'" / "'+txt('#np-code')+'"'); d.getElementById('np-titulo').value='Teste sem fundo'; await w.criarProjeto(); await sleep(300);
  chk(/Escolha o fundo/.test(txt('#m-proj'))&&d.getElementById('m-proj').classList.contains('on'),'"Criar projeto" sem fundo deveria dizer "Escolha o fundo." no próprio campo: "'+txt('#m-proj').slice(0,160)+'"'); w.closeModal();
  w.route_to('fundo/F026'); await sleep(3000); const bn=[...d.querySelectorAll('#v-fundo .act button')].find(x=>x.textContent.trim()==='Novo projeto'); if(bn){ bn.click(); await sleep(600); chk(d.getElementById('np-fundo').value==='F026','Novo projeto pela página do F026 deveria abrir já com F026: "'+d.getElementById('np-fundo').value+'"'); w.closeModal() } w.route_to('painel'); }
// ---------- [Auditoria P1-15] contagens que batem ----------
{ w.route_to('painel'); await sleep(2500); const P=(await J(adm,'/api/pendencias')).b, k=[...d.querySelectorAll('#v-painel .ini-kpi')].map(b=>[b.dataset.iniRota,+b.querySelector('.v').textContent.replace(/\D/g,'')]);
  const esp={decisoes:P.decisoes,'filas/conferir':P.lotes_conferir,'filas/admin':P.esperam_admin,'fundos/travados':P.travados_direitos};
  chk(k.length===4&&k.every(([r,v])=>esp[r]===v),'[H6b] os 4 números do painel deveriam ser os da fonte única (/api/pendencias): '+JSON.stringify(k)+' x '+JSON.stringify(esp));
  chk(txt('#n-dec')===(P.decisoes?String(P.decisoes):'')&&txt('#n-filas')===(P.material_novo?String(P.material_novo):''),'[H6b] os contadores do menu deveriam vir da mesma fonte: decisões '+txt('#n-dec')+' / filas '+txt('#n-filas'));
  for(const [r,v] of k){ w.route_to(r); await sleep(2200); const sel={decisoes:'#dec-body tr[data-abrir]','filas/conferir':'#filas-body tr[data-fase]','filas/admin':'#filas-body tr[data-fase]','fundos/travados':'#fundos-body tr[data-nav]'}[r];
    chk(d.querySelectorAll(sel).length===v,`[H6b] clicar no número ${v} (${r}) deveria abrir uma lista com ${v} linha(s): ${d.querySelectorAll(sel).length}`) }
  w.route_to('painel'); await sleep(2000);
  chk(!/itens esperam você|Por onde começar|Acervo em números|Precisa de atenção|Atividade recente/.test(txt('#v-painel')),'[H6b] o painel não deveria mais repetir os blocos antigos');
  chk(d.querySelectorAll('#ini-caminho .ini-step').length===7&&/Digitalizar.*No QNAP.*CAMP Vision.*Importar.*Conferir.*Aprovar.*Publicar/.test(txt('#ini-caminho')),'[H6b] o caminho do material deveria ter os 7 passos na ordem oficial');
  chk(!!d.querySelector('#ini-ritmo svg rect')&&/(Média de|Nenhuma folha conferida)/.test(txt('#ini-ritmo')),'[H6b] o ritmo das 2 semanas deveria ter as barras e a frase');
  w.route_to('solicitacoes'); await sleep(2000); await w.carregarSolicitacoes('recusada'); await sleep(1000);
  const linhas=[...d.querySelectorAll('#v-solicitacoes tbody tr')].filter(r=>!r.querySelector('td.empty,td.state-row')).length;
  chk(new RegExp('^'+linhas+' registros?').test(txt('#v-solicitacoes .cnt')),'o contador de Solicitações deveria contar só as linhas de dados da aba ('+linhas+'): "'+txt('#v-solicitacoes .cnt')+'"'); w.route_to('painel'); }
// ---------- DECISÕES: o painel pergunta antes de criar projeto parecido ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('painel'); await sleep(3500);
  const drawerAberto=()=>w.eval("mainEl.classList.contains('with-drawer')"), dl=(await J(adm,'/api/decisoes')).b;
  chk(dl.total>=2,'a semente deveria ter 2 decisões pendentes: '+dl.total);
  const li=[...d.querySelectorAll('#v-painel .ini-task')].filter(x=>/é o mesmo projeto que/.test(x.textContent));
  chk(li.length>=1&&!!li[0].querySelector('button.pri')&&/Decidir/.test(li[0].textContent),'"O que fazer agora" deveria listar a decisão com o botão Decidir ('+li.length+')');
  chk(/CAMP Vision está parado/.test(txt('#ini-tarefas')),'deveria avisar que o CAMP Vision está parado esperando');
  chk(/^Decidir/i.test(txt('#ini-tarefas .ini-tgh')),'"Decidir" deveria ser o primeiro grupo de "O que fazer agora": "'+txt('#ini-tarefas .ini-tgh')+'"');
  const id1=dl.itens[0].id, id2=dl.itens[1].id; li[0].querySelector('button.pri').click(); await sleep(1600);
  chk(txt('#d-title').includes('Projeto parecido: é o mesmo?')&&/O que chegou/.test(txt('#d-body'))&&/Já existe no fundo/.test(txt('#d-body'))&&/está esperando a sua resposta/.test(txt('#d-body')),'a janela deveria mostrar o que chegou, o que já existe e que o CAMP Vision espera: "'+txt('#d-body').slice(0,110)+'"');
  chk(!!d.querySelector('#d-body [data-dec-acao="mesmo"]')&&!!d.querySelector('#d-body [data-dec-acao="novo"]')&&!!d.querySelector('#d-body .dec-cand')&&/folhas no painel/.test(txt('#d-body'))&&/mesmo nome/.test(txt('#d-body')),'deveria ter os dois caminhos e, em cada candidato, os motivos');
  const nProj0=(await J(adm,'/api/painel')).b.projetos.total;
  d.querySelector('#d-body [data-dec-acao="mesmo"]').click(); await sleep(2600);
  const r1=(await J(adm,'/api/decisoes/'+id1)).b;
  chk(r1.situacao==='resolvida'&&r1.resolucao==='mesmo'&&(await J(adm,'/api/painel')).b.projetos.total===nProj0&&!drawerAberto(),'"É o mesmo" deveria resolver SEM criar projeto e fechar a janela: '+JSON.stringify({s:r1.situacao,r:r1.resolucao}));
  w.abrirDecisao(id2); await sleep(1600); d.querySelector('#d-body [data-dec-acao="novo"]').click(); await sleep(2600);
  const r2=(await J(adm,'/api/decisoes/'+id2)).b;
  chk(r2.situacao==='resolvida'&&r2.resolucao==='novo'&&/^F026-P\d{4}$/.test(r2.projeto_codigo)&&(await J(adm,'/api/painel')).b.projetos.total===nProj0+1,'"É outro projeto" deveria criar o novo: '+JSON.stringify(r2).slice(0,140));
  w.abrirDecisao(id1); await sleep(1500); chk(/Decidido/.test(txt('#d-body'))&&/Era o mesmo projeto/.test(txt('#d-body'))&&!d.querySelector('#d-body [data-dec-acao]'),'uma decisão já resolvida deveria aparecer só para leitura, sem botões'); w.closeDrawer(true);
  w.route_to('painel'); await sleep(2800); chk(!/é o mesmo projeto que/.test(txt('#ini-tarefas'))&&txt('#n-dec')==='','depois de decidir, "O que fazer agora" e o contador do menu não deveriam mais mostrar as decisões');
  w.route_to('decisoes'); await sleep(2000); chk(d.querySelectorAll('#dec-body tr[data-abrir]').length===0&&/Nenhuma decisão esperando/.test(txt('#dec-body')),'a página Decisões deveria estar vazia e explicar');
  d.querySelector('[data-dec-sit="resolvida"]').click(); await sleep(1500); chk(d.querySelectorAll('#dec-body tr[data-abrir]').length>=2&&/era o mesmo/.test(txt('#dec-body')),'a aba "Decididas" deveria listar as 2 decisões com o resultado: '+txt('#dec-body').slice(0,120)); w.route_to('painel'); await sleep(800);
  // novo projeto à mão: o painel avisa dos parecidos antes de criar
  const tit=(await J(adm,'/api/projetos/F026-P0001/detalhe')).b.projeto.titulo, nP=(await J(adm,'/api/painel')).b.projetos.total;
  w.openModal('m-proj'); await sleep(600); d.getElementById('np-fundo').value='F026'; d.getElementById('np-titulo').value=tit; await w.criarProjeto(); await sleep(1500);
  chk(txt('#np-criar')==='Decida acima: é o mesmo ou é novo?'&&d.getElementById('np-criar').getAttribute('aria-disabled')==='true','[P2-17] com parecido, o botão "Criar projeto" deveria dizer o que falta: "'+txt('#np-criar')+'"');
  { const nP2=(await J(adm,'/api/painel')).b.projetos.total; await w.criarProjeto(); await sleep(800); chk((await J(adm,'/api/painel')).b.projetos.total===nP2&&!!d.querySelector('#np-parecidos .np-par'),'[P2-17] clicar de novo em "Criar projeto" sem decidir não pode criar: só leva ao aviso') }
  chk(/Já existe projeto parecido neste fundo/.test(txt('#np-parecidos'))&&/F026-P0001/.test(txt('#np-parecidos'))&&/É um projeto novo: criar F026-P\d{4}/.test(txt('#np-parecidos'))&&/Decida acima/.test(txt('#np-err')),'o modal de novo projeto deveria avisar do parecido (F026-P0001): "'+txt('#np-parecidos').slice(0,120)+'"');
  chk((await J(adm,'/api/painel')).b.projetos.total===nP,'avisar NÃO pode criar o projeto');
  d.querySelector('#np-parecidos [data-np-abrir]').click(); await sleep(1500); chk(/projeto\/F026-P0001/.test(w.location.hash),'"Abrir este" deveria levar ao projeto parecido: '+w.location.hash); w.closeModal(); }
// ---------- FOLHAS NO QNAP NA PÁGINA DO PROJETO ----------
{ w.closeDrawer(true); w.route_to('projeto/F026-P0001'); await sleep(3500);
  const fq=(await J(adm,'/api/projetos/F026-P0001/folhas-qnap')).b, lt=fq.lotes.find(l=>l.existe), qf=()=>d.querySelectorAll('#pj-qnap .qf');
  chk(!!lt&&lt.fora_do_painel===3&&lt.documentos.length===3,'a API deveria listar 3 documentos do lote de teste (JPG e TIF do mesmo código = 1): '+JSON.stringify(lt&&{t:lt.total,f:lt.fora_do_painel}));
  chk(/Encontradas no QNAP, ainda não catalogadas no painel/.test(txt('#pj-qnap'))&&qf().length===3,'a página do projeto deveria mostrar o painel "Encontradas no QNAP" com 3 documentos: '+qf().length+' ('+txt('#pj-qnap').slice(0,100)+')');
  chk(/3 documentos/.test(txt('#pj-qnap'))&&/F026-P0001-1970-S01-D90001/.test(txt('#pj-qnap'))&&/JPG · TIF/.test(txt('#pj-qnap')),'cada documento deveria mostrar o código e os formatos (JPG · TIF)');
  const im=[...d.querySelectorAll('#pj-qnap .qf img')];
  chk(im.length===3&&im.every(x=>x.getAttribute('src').startsWith('/api/projetos/F026-P0001/folhas-qnap/arquivo?lote=')&&x.getAttribute('src').includes('caminho=')),'as miniaturas deveriam vir do endpoint de prévia do projeto');
  chk(/ainda não viraram folhas do painel/.test(txt('#pj-qnap')),'o painel deveria dizer que ainda não viraram folhas e apontar a Revisão do lote');
  w.route_to('projeto/F023-P0011'); await sleep(3000);
  chk(d.querySelectorAll('#pj-qnap .qf').length===0&&!/Encontradas no QNAP/.test(txt('#pj-qnap')),'um projeto SEM lote no QNAP não deveria mostrar o painel'); }
// ---------- TOPO DO PAINEL, SELO, CARTÃO DO QNAP E DIVERGÊNCIAS ----------
{ w.confirm=()=>true; w.closeDrawer(true); w.route_to('painel'); await sleep(3000);   // fecha qualquer painel lateral de testes anteriores (o painel protege edição pendente)
  const pn=(await J(adm,'/api/painel')).b;
  chk(/^(Bom dia|Boa tarde|Boa noite), Rafael\. (\d+ coisas? pedem? você|Tudo em dia)\.$/.test(txt('#ini-saud')),'[H6b] a saudação deveria resumir o que pede a pessoa: "'+txt('#ini-saud')+'"');
  chk(d.querySelectorAll('#ini-tarefas .ini-tg').length===pn.tarefas.length&&pn.tarefas.every(g=>txt('#ini-tarefas').includes(g.titulo)),'[H6b] "O que fazer agora" deveria ter um grupo por tipo de trabalho, vindo do servidor');
  chk([...d.querySelectorAll('#ini-tarefas .ini-tg')].every(g=>g.querySelectorAll('.ini-task').length<=3),'[H6b] no máximo 3 linhas por grupo (o resto em "Ver os N…")');
  chk(!/folhas_importadas_do_lote|site_item_criado|campvision \(aviso\)/.test(txt('#v-painel')),'[H6b] "Hoje" deveria falar em frases, não com o nome técnico dos eventos');
  // diferenças com o site: o número leva a uma lista em português (agora na linha "Site" de "Está tudo funcionando?")
  chk(!!d.querySelector('#ini-saude [data-ini-div]')&&d.querySelector('#ini-saude [data-ini-div]').tagName==='BUTTON','a linha do site deveria ter o botão "ver o que são" nas diferenças (acessível por teclado)');
  d.querySelector('#ini-saude [data-ini-div]').click(); await sleep(2500);
  chk(txt('#d-title').includes('Divergências entre o painel e o site')&&txt('#d-body').includes('Item do site sem código CAMP')&&txt('#d-body').includes('Fundo sem nenhuma folha no site'),'a lista de divergências deveria explicar cada tipo em português: título="'+txt('#d-title')+'" corpo="'+txt('#d-body').slice(0,80)+'"');
  chk(!/sem_codigo|fundo_inexistente|sem_itens_no_site|_fora_do_ar/.test(txt('#d-body')),'a lista não pode mostrar o código cru das divergências'); w.closeDrawer(true);
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
  chk(!!d.getElementById('pd-importar')&&txt('#pd-importar').includes('2 folhas'),'o projeto deveria oferecer "Importar 2 folha(s) só no site": '+txt('#pd-source, .project-source').slice(0,120));
  // clicar no cartão abre a folha (importa na hora)
  d.querySelector('[data-nav="item/'+SO+'"]').click(); await sleep(3000);
  chk(w.location.hash==='#item/'+SO&&!!d.getElementById('it-editar')&&!/não encontrado/i.test(txt('.content.on')),'abrir a folha só no site deveria abrir a página dela com o botão Editar, não "não encontrado": '+txt('.content.on').slice(0,100));
  r=await J(adm,'/api/itens/'+SO); chk(r.s===200,'a folha deveria agora existir no catálogo: '+r.s);
  // EDITA como as outras
  await w.editarItem(SO); await sleep(600); const ti=d.getElementById('ei-titulo'); ti.value='Foto editada no painel'; ti.dispatchEvent(new w.Event('input',{bubbles:true})); await w.salvarItem(SO); await sleep(1800);
  r=await J(adm,'/api/itens/'+SO); chk(r.s===200&&r.b.item.titulo==='Foto editada no painel','a folha importada deveria salvar a edição: '+JSON.stringify(r.b&&r.b.item&&r.b.item.titulo));
  w.route_to('projeto/F002-P0002'); await sleep(2000);
  chk(!!d.getElementById('pd-importar')&&txt('#pd-importar').includes('1 folha'),'depois de importar uma, o botão deveria contar 1: '+(d.getElementById('pd-importar')?txt('#pd-importar'):'(sem botão)'));
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
const bp=d.getElementById('pd-publicar'); chk(bp&&!bp.disabled&&bp.getAttribute('aria-disabled')!=='true','o botão Publicar deveria estar SEMPRE ativo (o plano é que explica o que falta)');
let _conf=0;w.confirm=()=>{_conf++;return true}; bp.click(); await sleep(1300);
chk(_conf===0&&txt('#d-title').includes('Publicar')&&/O que vou fazer/.test(txt('#d-body'))&&d.querySelectorAll('#d-body h3 + ul.checklist li').length===4&&/Marcar o projeto como liberado/.test(txt('#d-body'))&&/Tornar a página e as \d+ folha/.test(txt('#d-body')),'clicar em Publicar deveria abrir o PLANO com os 4 passos (dossiê, folhas, autorizar, publicar), sem pedir confirmação ('+d.querySelectorAll('#d-body h3 + ul.checklist li').length+' passos, confirm='+_conf+'): \"'+txt('#d-body').slice(0,160)+'\"');
chk(d.querySelectorAll('#d-body .chk.falta').length===1&&/Direitos do fundo F026/.test(txt('#d-body'))&&d.querySelectorAll('#d-body .chk.falta button').length===1&&/Definir direitos do fundo/.test(txt('#d-body'))&&d.getElementById('pub-go').disabled===true,'só o que SÓ uma pessoa resolve (direitos do fundo) deveria bloquear, com o botão que resolve, e \"Publicar agora\" ficar desligado');
chk(!/Autorizar publicação/.test(txt('#d-body').replace('Autorizar o projeto para publicação','')),'a autorização NÃO deveria ser pedida: o painel faz sozinho'); w.closeDrawer(true);
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
// Publicar com um clique: sem o que só uma pessoa resolve, o plano libera e o clique executa (aqui o WordPress não tem credencial: o erro tem que ser dito e dar para tentar de novo)
w.closeDrawer(true); d.getElementById('pd-publicar').click(); await sleep(1300);
chk(d.querySelectorAll('#d-body .chk.falta').length===0&&d.getElementById('pub-go').disabled===false&&/Eu faço a sequência inteira/.test(txt('#d-body')),'com os requisitos humanos cumpridos o plano deveria liberar \"Publicar agora\": \"'+txt('#d-body').slice(0,140)+'\"');
d.getElementById('pub-go').click(); await sleep(4500);
chk(/não terminou|não deu/.test(txt('#d-body'))&&txt('#d-body').trim().length>40&&d.getElementById('pub-go').disabled===false&&/Tentar de novo/.test(txt('#pub-go')),'sem credencial do WordPress o clique deveria explicar o que houve e deixar TENTAR DE NOVO: \"'+txt('#d-body').slice(0,160)+'\"'); w.closeDrawer(true);
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
await w.abrirAjudaAtalhos(); await sleep(500);
chk(txt('#d-title').includes('Publicar um fundo')&&txt('#d-body').includes('Definir os direitos')&&txt('#d-body').includes('Autorizar cada projeto'),'a ajuda (?) do fundo deveria trazer o passo a passo: '+txt('#d-title')); w.closeDrawer(true);
w.location.hash='#arquitetos'; await sleep(2200);
{ const ags=await J(adm,'/api/agentes'); const a0=(ags.b||[])[0]; chk(!!a0,'o ambiente deveria ter arquitetos');
  await w.editarAgente(a0.id); await sleep(1800);
  chk(!!d.getElementById('ag-guia')&&txt('#ag-guia').includes('Como publicar este arquiteto'),'o formulário do arquiteto deveria ter o quadro "Como publicar este arquiteto"');
  chk(txt('#ag-guia').includes('marcador interno')&&txt('#ag-guia').includes('wp-admin'),'o guia do arquiteto deveria dizer que o status é só marcador e que foto/bio/ativar são no wp-admin');
  chk(d.querySelectorAll('#ag-guia .guia-passos li').length===6,'o passo a passo do arquiteto deveria ter 6 passos');
  w.closeDrawer(true); }
await w.abrirAjudaAtalhos(); await sleep(500);
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
// ---------- [P2-18] confirmações: janela do painel com alvo e consequência; nada de confirm/prompt/alert do navegador ----------
{ const cOrig=w.confirm; w.__semAutoResposta=true; const fonte=require('fs').readFileSync(require('path').join(__dirname,'..','frontend','index.html'),'utf8');
  const nativos=(fonte.match(/(?<![\w.])(?:confirm|prompt|alert)\(/g)||[]).length; chk(nativos===0,'[P2-18] o index.html não deveria ter confirm()/prompt()/alert() do navegador: '+nativos);
  // Usuários → Papel: lista com os 4 papéis e o que cada um faz (antes: digitar o nome do papel)
  w.confirm=()=>false; w.route_to('config'); await sleep(1800); await w.carregarUsuarios(); await sleep(500);
  const ul=(await J(adm,'/api/usuarios')).b, op=ul.find(x=>x.email==='operador@camp.arq.br'), eu=ul.find(x=>x.email==='rafael@camp.arq.br');
  const linhaEu=[...d.querySelectorAll('#usr-body tr')].find(tr=>tr.textContent.includes('rafael@camp.arq.br'));
  chk(!!linhaEu&&!/Desativar|>Papel</.test(linhaEu.innerHTML)&&/você/.test(linhaEu.textContent),'[P2-18] a própria linha não deveria ter "Papel" nem "Desativar"');
  w.mudarPapel(op.id,'operador'); await sleep(80);
  const radios=[...d.querySelectorAll('#conf-ov input[name="conf-op"]')].map(r=>r.value);
  chk(JSON.stringify(radios)==='["leitura","operador","admin","master"]'&&d.querySelector('#conf-ov input[value="operador"]').checked&&/importa e confere/.test(txt('#conf-ov'))&&/operador@camp\.arq\.br/.test(txt('#conf-ov')),'[P2-18] "Papel" deveria abrir a janela com os 4 papéis explicados, o atual marcado e o alvo: '+txt('#conf-ov').slice(0,160));
  d.querySelector('#conf-ov [data-conf="nao"]').click(); await sleep(150); chk(!d.getElementById('conf-ov')&&(await J(adm,'/api/usuarios')).b.find(x=>x.id===op.id).papel==='operador','"Cancelar" não muda o papel');
  // Nova senha: janela com a senha e o botão Copiar (antes: alert que sumia)
  const ap=w.acaoUsr(op.id,'redefinir-senha'); await sleep(80); chk(/sai do painel/.test(txt('#conf-ov')),'[P2-18] "Nova senha" deveria dizer a consequência'); d.querySelector('#conf-ov [data-conf="sim"]').click(); await sleep(900);
  chk(!!d.getElementById('senha-temp')&&d.getElementById('senha-temp').textContent.length>=8&&!!d.querySelector('#conf-ov [data-copiar-senha]')&&/não aparece de novo/.test(txt('#conf-ov')),'[P2-18] a senha temporária deveria aparecer numa janela do painel, com "Copiar"'); d.querySelector('#conf-ov [data-conf="sim"]').click(); await ap; await sleep(200);
  // Sigla: 3 letras e sem repetir, com o erro dentro da janela (antes: prompt sem validação)
  w.confirm=()=>false; w.definirSigla('F030','Teste'); await sleep(80); const cs=d.getElementById('conf-campo'), sim=d.querySelector('#conf-ov [data-conf="sim"]');
  cs.value='AB'; cs.dispatchEvent(new w.Event('input',{bubbles:true})); const e1=txt('#conf-err'), d1=sim.disabled;
  const usada=((await J(adm,'/api/fundos/resumo')).b.find(f=>f.sigla)||{}).sigla||'SBU'; cs.value=usada; cs.dispatchEvent(new w.Event('input',{bubbles:true})); const e2=txt('#conf-err');
  chk(d1&&/3 letras/.test(e1)&&/já é de outro fundo/.test(e2)&&sim.disabled,'[P2-18] a sigla deveria ser validada na janela (3 letras; não repetir): "'+e1+'" / "'+e2+'"');
  d.querySelector('#conf-ov [data-conf="nao"]').click(); await sleep(150);
  // Despublicar o fundo inteiro: motivo obrigatório e digitar o código para confirmar
  w.confirm=()=>false; w.statusFundoSite('F003','fora_do_ar'); await sleep(80); const sim2=d.querySelector('#conf-ov [data-conf="sim"]');
  chk(!!d.getElementById('conf-dig')&&!!d.getElementById('conf-motivo')&&sim2.disabled&&/digite/i.test(txt('#conf-ov'))&&/F003/.test(txt('#conf-ov')),'[P2-18] despublicar o fundo inteiro deveria pedir o motivo e digitar o código (botão travado até lá)');
  d.getElementById('conf-motivo').value='teste'; d.getElementById('conf-motivo').dispatchEvent(new w.Event('input',{bubbles:true})); d.getElementById('conf-dig').value='F00'; d.getElementById('conf-dig').dispatchEvent(new w.Event('input',{bubbles:true})); const trav=sim2.disabled;
  d.getElementById('conf-dig').value='f003'; d.getElementById('conf-dig').dispatchEvent(new w.Event('input',{bubbles:true}));
  chk(trav&&!sim2.disabled,'[P2-18] o botão só libera com o código certo (maiúscula/minúscula tanto faz)'); d.querySelector('#conf-ov [data-conf="nao"]').click(); await sleep(150);
  // Esc cancela; duplo clique numa ação com "acao" roda uma vez só
  let chamadas=0; const pr=w.confirmar({titulo:'Teste',botao:'Fazer',acao:async()=>{chamadas++;await new Promise(r=>setTimeout(r,300));return 'ok'}}); await sleep(30);
  const bs=d.querySelector('#conf-ov [data-conf="sim"]'); bs.click(); bs.click(); bs.click(); const ocup=bs.disabled&&/Trabalhando/.test(bs.textContent); const rr=await pr;
  chk(chamadas===1&&ocup&&rr&&rr.resultado==='ok','[P2-18] com ação, o botão vira "Trabalhando…" e o duplo clique não repete: '+chamadas);
  const pe=w.confirmar({titulo:'Esc'}); await sleep(30); d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true})); chk((await pe)===false,'[P2-18] Esc deveria cancelar');
  const perr=w.confirmar({titulo:'Erro',acao:async()=>{throw new Error('o servidor recusou')}}); await sleep(30); d.querySelector('#conf-ov [data-conf="sim"]').click(); await sleep(80);
  chk(/o servidor recusou/.test(txt('#conf-err'))&&!!d.getElementById('conf-ov'),'[P2-18] o erro da ação deveria aparecer DENTRO da janela, que continua aberta'); d.querySelector('#conf-ov [data-conf="nao"]').click(); await perr;
  w.__semAutoResposta=false; w.confirm=cOrig; w.route_to('painel'); okl.push('P2-18: confirmações do painel (papel, senha, sigla, despublicar fundo, duplo clique, Esc, erro na janela)'); }
// ---------- [#94] padrão único de tela: ≤1 botão azul no cabeçalho, abas de situação únicas, um só Voltar, linha clicável com data-abrir ----------
{ const ruins=[];
  for (const r of ['filas','decisoes','erros','solicitacoes','projetos','fundos','arquitetos','localizacao','auditoria','fundo/F003','projeto/F003-P9001']){ w.route_to(r); await sleep(1500);
    const v=d.querySelector('.content.on'); if(!v){ruins.push(r+': tela não abriu');continue}
    const hdr=v.querySelector('.hdr,.dethdr'), pri=hdr?hdr.querySelectorAll('.btn.pri').length:0; if(pri>1) ruins.push(r+': '+pri+' botões azuis no cabeçalho');
    if(v.querySelector('.backbar,.fila-chips,.fundos-filtros')) ruins.push(r+': variante antiga (Voltar duplo, pílulas)');
    if(v.querySelector('select[onchange*="carregarErros"]')) ruins.push(r+': select de situação');
    const soltas=[...v.querySelectorAll('tbody tr[onclick]')].filter(t=>!t.dataset.abrir&&!t.dataset.nav).length; if(soltas) ruins.push(r+': '+soltas+' linha(s) clicável(is) sem data-abrir'); }
  chk(!ruins.length,'[#94] padrão de tela: '+ruins.join(' | '));
  w.route_to('erros'); await sleep(1500);
  chk(d.querySelectorAll('#err-abas [data-err-sit]').length===3&&/Abertos\s*\d+/.test(txt('#err-abas'))&&!d.querySelector('#v-erros .hdr select'),'[#94] Erros deveria ter as abas Abertos · Corrigidos · Todos com contagem (e não o select): "'+txt('#err-abas')+'"');
  d.querySelector('#err-abas [data-err-sit="todos"]').click(); await sleep(1200);
  chk(d.querySelector('#err-abas [data-err-sit="todos"]').getAttribute('aria-pressed')==='true','[#94] clicar em "Todos" deveria ligar a aba'); w.carregarErros('abertos'); await sleep(600);
  w.route_to('fundo/F003'); await sleep(2500); const mm=d.querySelector('#v-fundo .mais-menu');
  chk(!!mm&&/Etiqueta do fundo/.test(mm.textContent)&&(!/Despublicar/.test(mm.textContent)||!!mm.querySelector('.perigo-txt'))&&/Burle Marx/.test(txt('#gcrumb')),'[#94] fundo: ações secundárias no "Mais ⋯" (despublicar em vermelho) e a trilha com o nome do fundo: "'+txt('#gcrumb')+'"');
  w.route_to('auditoria'); await sleep(1800); const ta=d.querySelector('#au-body tr[data-abrir^="auditoria:"]');
  if(ta){ ta.querySelector('td').click(); await sleep(500); chk(/Quando/.test(txt('#d-body')),'[#94] clicar na linha da auditoria deveria abrir o evento'); w.closeDrawer(true) } else chk(false,'[#94] as linhas da auditoria deveriam ter data-abrir');
  okl.push('#94: padrão de tela em 11 telas (≤1 azul no cabeçalho, abas de situação únicas, sem Voltar duplo, linhas com data-abrir, "Mais ⋯" no fundo)'); }
// ---------- [#95] página do projeto: um só próximo passo (logo abaixo do título), requisitos recolhidos, trilha sem repetir, título limpo ----------
{ w.route_to('projeto/F003-P9001'); await sleep(3500);
  const pp=d.getElementById('pj-proximo'), pub=d.getElementById('pd-pub');
  chk(!!pp&&!!pub&&!!(pp.compareDocumentPosition(pub)&4)&&!pp.closest('.tabs')&&!d.querySelector('#pd .tabs ~ * #pj-proximo'),'[#95] o Próximo passo deveria vir logo abaixo do título, antes dos requisitos e fora das abas');
  const azuis=[...d.querySelectorAll('#pd .btn.pri')].map(b=>b.textContent.trim());
  chk(azuis.length===1&&/conferir/i.test(azuis[0])&&pp.contains(d.querySelector('#pd .btn.pri')),'[#95] deveria haver UM só botão azul na página, o do Próximo passo: '+JSON.stringify(azuis));
  chk(d.getElementById('pd-pub-det')&&!d.getElementById('pd-pub-det').open&&/\d+ de \d+ ok/.test(txt('#pd-pub-resumo'))&&/falta:/.test(txt('#pd-pub-resumo')),'[#95] os requisitos deveriam ficar recolhidos, com o resumo "N de M ok · falta: …": "'+txt('#pd-pub-resumo')+'"');
  chk(/F003 Burle Marx/.test(txt('#gcrumb'))&&/F003-P9001 · Projeto de teste/.test(txt('#gcrumb'))&&!/F003-P9001 · F003-P9001/.test(txt('#gcrumb')),'[#95] a trilha não deveria repetir o código: "'+txt('#gcrumb')+'"');
  chk(/Projeto de teste/.test(txt('#where'))&&d.querySelectorAll('#where button').length===1,'[#95] o topo deveria ter um Voltar e o nome do projeto: "'+txt('#where')+'"');
  w.showProjeto('F003-P9001','historico'); await sleep(2500);
  chk(/Faltam conferir/.test(txt('#pj-proximo')),'[#95] o Próximo passo deveria aparecer em qualquer aba (aqui: Histórico): "'+txt('#pj-proximo').slice(0,80)+'"'); w.showProjeto('F003-P9001','itens'); await sleep(1500);
  chk(w.tituloExibicao('T102_Edifício Jockey Club São Paulo')==='Edifício Jockey Club São Paulo'&&w.tituloExibicao('Casa_do_Lago')==='Casa do Lago'&&w.tituloExibicao('Residência Martino')==='Residência Martino','[#95] o título deveria aparecer sem o prefixo da pasta e sem "_"');
  okl.push('#95: um só botão azul (Próximo passo, em qualquer aba), requisitos recolhidos com resumo, trilha e Voltar únicos, título limpo'); }
// ---------- [H4] toda ação mostra o que está acontecendo: botão "trabalhando", Desfazer, chip de tarefas no topo, aviso de conclusão ----------
{ w.route_to('painel'); await sleep(800);
  let hit=0; w.toast('Teste do desfazer',{acao:{rotulo:'Desfazer',fn:()=>{hit++}}}); const tb=d.querySelector('#toast .toast-acao');
  chk(!!tb&&d.getElementById('toast').classList.contains('com-acao'),'[H4] o toast com ação deveria ter o botão e aceitar clique'); tb.click(); await sleep(50);
  chk(hit===1&&!d.getElementById('toast').classList.contains('on'),'[H4] clicar em "Desfazer" deveria rodar a ação uma vez e fechar o aviso');
  // passado 1 s, o botão diz o que está fazendo (sem mudar de largura) e volta ao normal no fim
  const fetchOrig=w.fetch; w.fetch=(u,o={})=>/\/api\/teste-lento$/.test(String(u))?new Promise(r=>setTimeout(()=>r({ok:true,status:200,statusText:'OK',json:async()=>({ok:true})}),1500)):fetchOrig(u,o);
  const bt=d.createElement('button'); bt.className='btn'; bt.textContent='Importar'; bt.dataset.trabalhando='Importando…'; d.querySelector('.content.on').appendChild(bt); bt.focus();
  const pl=w.eval('API')('/api/teste-lento',{method:'POST'}); await sleep(400); const t04=bt.textContent; await sleep(900); const t13=bt.textContent, dis=bt.disabled; await pl; await sleep(30); w.fetch=fetchOrig;
  chk(t04==='Importar'&&t13==='Importando…'&&dis&&bt.textContent==='Importar'&&!bt.disabled&&bt.style.minWidth==='','[H4] o botão deveria dizer "Importando…" só depois de 1 s e voltar a "Importar" no fim: '+[t04,t13,dis,bt.textContent].join(' / ')); bt.remove();
  // chip do topo: tarefa rodando aparece de qualquer página; clicar leva ao andamento
  w.eval('clearTimeout(TAREFAS_TIMER)'); w.eval(`TAREFAS_EST={rodando:[{id:9001,tipo:'publicar',projeto_codigo:'F022-P0009',ator:'x',estado:'rodando',etapa:'folhas',folha_atual:'F022-P0009-1970-S01-D00004',feitas:3,total:5,decorrido_s:70,faltam_s:46,iniciada_em:'2026-10-13 10:00:00',log:[],falhas:[]}],terminadas:[]}`); w.desenharChipTarefas();
  const chip=d.getElementById('tarefas-chip'); chk(!chip.hidden&&/Publicando F022-P0009 · 3 de 5/.test(chip.textContent),'[H4] o chip do topo deveria dizer "Publicando F022-P0009 · 3 de 5": "'+chip.textContent+'"');
  chip.querySelector('[data-tarefas-abrir]').click();   // confere na hora: logo depois a lista se atualiza com o servidor de verdade
  chk(/Tarefas/.test(txt('#d-title'))&&/3 de 5/.test(txt('#d-body'))&&/D00004/.test(txt('#d-body'))&&/faltam cerca de 46 s/.test(txt('#d-body'))&&!!d.querySelector('#d-body [data-tarefa-projeto="F022-P0009"]'),'[H4] clicar no chip deveria abrir o andamento (3 de 5, folha atual, quanto falta, link do projeto): "'+txt('#d-body').slice(0,200)+'"'); w.closeDrawer(true); await sleep(100);
  // tarefa de verdade no servidor, terminada sem a pessoa ver: o aviso de conclusão fica até ela fechar (e não volta depois)
  const tr=await w.eval('API')('/api/backup/agora?tarefa=1',{method:'POST'}); await sleep(1800); await w.vigiarTarefas();
  chk(!chip.hidden&&chip.classList.contains('ok')&&/✔ Backup feito/.test(chip.textContent)&&!!chip.querySelector('[data-tarefas-visto]'),'[H4] terminada fora da vista, a tarefa deveria deixar o aviso "✔ Backup feito…" com × no topo: "'+chip.textContent+'"');
  chip.querySelector('[data-tarefas-visto]').click(); await sleep(400);
  const pf=(await J(adm,'/api/auth/eu/preferencias')).b; await w.vigiarTarefas();
  chk(chip.hidden&&!!pf['tarefas.vista'],'[H4] fechar o aviso deveria escondê-lo e lembrar (preferência tarefas.vista) para não voltar: '+JSON.stringify(pf));
  const lista=(await J(adm,'/api/tarefas')).b; chk(lista.terminadas.some(x=>x.id===tr.tarefa_id&&x.estado==='ok'),'[H4] /api/tarefas deveria listar a tarefa terminada');
  // pedido: mudar a situação não pergunta; o aviso diz quem e traz "Desfazer"
  const P=(await J(adm,'/api/solicitacoes?situacao=todos')).b.itens[0];
  if(P){ await w.abrirSolicitacao(P.id); await sleep(300); const nova=P.situacao==='em_preparacao'?'aguarda_resposta':'em_preparacao'; d.getElementById('es-sit').value=nova;
    await w.salvarSolicitacao(P.id); await sleep(200);
    chk(txt('#toast').includes('Pedido de '+P.solicitante+' marcado como')&&!!d.querySelector('#toast .toast-acao'),'[H4] o aviso do pedido deveria dizer de quem é e trazer "Desfazer": "'+txt('#toast')+'"');
    d.querySelector('#toast .toast-acao').click(); await sleep(900);
    chk(((await J(adm,'/api/solicitacoes?situacao=todos')).b.itens.find(x=>x.id===P.id)||{}).situacao===P.situacao,'[H4] "Desfazer" deveria voltar o pedido para a situação anterior ('+P.situacao+')'); }
  okl.push('H4: botão "trabalhando" após 1 s, Desfazer (conferir, girar, pedido), andamento de tarefa no lugar, chip no topo, aviso de conclusão que fica até fechar'); }
// rotas inválidas / deep link
w.location.hash='#projeto/F999-P9999'; await sleep(1000); chk(!/undefined|NaN/.test(txt('.content.on')),'rota de projeto inexistente mostra lixo: '+txt('.content.on').slice(0,80)); okl.push('deep link inexistente: "'+txt('.content.on').slice(0,60)+'"');
w.location.hash='#rota-que-nao-existe'; await sleep(600); okl.push('rota inválida: "'+txt('.content.on').slice(0,60)+'"');
console.log('\n=== OK ==='); okl.forEach(x=>console.log(' ✓',x));
console.log('\n=== PROBLEMAS ('+[...new Set(problems)].length+') ==='); [...new Set(problems)].forEach(x=>console.log(' ✗',x));
process.exit(0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
