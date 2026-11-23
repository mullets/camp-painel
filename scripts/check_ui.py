#!/usr/bin/env python3
"""Falha o deploy se estruturas visuais essenciais desaparecerem do frontend."""
from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "index.html"
# --html OUTRO.html: confere outro arquivo no lugar do index.html (o teste tests/teste_check_ui_tom.py usa uma cópia com emoji plantado)
if "--html" in sys.argv:
    HTML = Path(sys.argv[sys.argv.index("--html") + 1]).resolve()
text = HTML.read_text(encoding="utf-8")


def _rel(arq):
    try:
        return arq.relative_to(ROOT)
    except ValueError:
        return arq

required_css = [
    ".dash-v2{", ".dash-hero{", ".machine-status{", ".system-banner{",
    ".lab-wrap{", ".lab-preview{", ".bulkbar{", ".abas-sit{",
    ".dirty-state{", ".form-summary{", ".modal{", ".drawer{", ".filterbar{",
]
required_dom = [
    'id="v-painel"', 'id="v-fundos"', 'id="v-projetos"', 'id="v-etiquetas"',
    'id="v-config"', 'id="machine-status"', 'id="system-banner"',
    'id="fundos-filtros"', 'id="proj-bulk"', 'id="drawer"',
    # página do projeto (abas na ordem do trabalho) e Configurações
    'id="pj-proximo"', 'id="pd-pub"', 'data-pj-aba="publicacao"', 'data-pj-aba="dados"', 'id="cfg-busca"',
]

errors = []
for token in required_css:
    if token not in text:
        errors.append(f"CSS essencial ausente: {token}")
for token in required_dom:
    if token not in text:
        errors.append(f"estrutura essencial ausente: {token}")

# Impede voltar a crescer sem controle: o teto é o número atual (13/10/2026). Novo layout
# usa classes/componentes; quem tirar estilo inline pode baixar este número.
inline = len(re.findall(r'\bstyle="', text))
if inline > 157:     # CAMP-155 (22/10/2026): o teto desce para o número de hoje
    errors.append(f"orçamento de estilos inline excedido: {inline} > 157")

# --- CAMP-155: só os tokens do padrão (docs/padroes.md). No CSS e na marcação da página, tamanho de fonte e raio crus não podem
# crescer (o que é igual a um token já virou var(--fs-*) / var(--r*)), e o âmbar fora dos tokens não volta. O JS fica de fora: as
# janelas de impressão (etiquetas, folha de contatos) têm CSS próprio, sem os tokens. UX-27 (27/10/2026): o teto da fonte crua desceu de 65 para 50.
_pagina = text[text.index("<style>"):text.index("<script>")] if "<style>" in text and "<script>" in text else text
for _nome, _pad, _teto in (("tamanho de fonte cru (px)", r"font-size:\d+(\.\d+)?px", 50), ("raio cru (px)", r"border-radius:\d+(\.\d+)?px", 39)):
    _n = len(re.findall(_pad, _pagina))
    if _n > _teto:
        errors.append(f"tokens: {_nome} subiu para {_n} (teto {_teto}): use var(--fs-*) / var(--r-sm|--r|--r-md|--r-lg) — CAMP-155")
for _cru, _tok in (("font-size:11px", "--fs-2xs"), ("font-size:11.5px", "--fs-xs"), ("font-size:12px", "--fs-xs"), ("font-size:12.5px", "--fs-sm2"),
                   ("font-size:13px", "--fs-md"), ("font-size:14px", "--fs-base"), ("font-size:17px", "--fs-lg"), ("border-radius:4px", "--r-sm"),
                   ("border-radius:6px", "--r"), ("border-radius:8px", "--r-md"), ("border-radius:12px", "--r-lg")):
    if re.search(re.escape(_cru) + r"(?![\d.])", _pagina):
        errors.append(f"tokens: '{_cru}' tem token igual ({_tok}): use var({_tok}) — CAMP-155")
if re.search(r"#(c98a00|b7791f|fdf3e1)\b", text, re.I):
    errors.append("tokens: âmbar fora dos tokens (#c98a00/#b7791f/#fdf3e1): use var(--amber) / var(--amber-soft) — CAMP-155")
if "var(--panel" in text:
    errors.append("tokens: --panel não existe (no escuro vira branco): use var(--surface) — CAMP-155")

# Detecta HTML/JS de componentes sem seu CSS, causa da regressão real do dashboard.
pairs = [
    ("dash-v2", ".dash-v2{"),
    ("bulkbar", ".bulkbar{"),
    ("abas-sit", ".abas-sit{"),
    ("mais-menu", ".mais-menu{"),
    ("machine-status", ".machine-status{"),
    ("lab-wrap", ".lab-wrap{"),
]
for html_class, selector in pairs:
    if html_class in text and selector not in text:
        errors.append(f"componente {html_class} aparece no HTML/JS sem CSS {selector}")

# --- #94 padrão único de tela (docs/padrao-de-tela.md): variantes antigas não podem voltar ---
for velho, dica in (('class="backbar"', "detalhe tem um só Voltar (o do topo)"), ('class="fila-chips"', "use .abas-sit"),
                    ('class="fundos-filtros"', "use .abas-sit"), ('onchange="carregarErros(', "use as abas de situação")):
    if velho in text:
        errors.append(f"padrão de tela: {velho} voltou ({dica})")

# --- vocabulário único de publicação (docs/vocabulario.md): estas frases NÃO podem voltar ---
PROIBIDAS = [
    (r"\bno ar\b", "use 'publicado' / 'Publicar'"),
    (r"logado no WordPress", "o operador não precisa saber do WordPress: diga 'só a equipe vê'"),
    (r"fora do ar", "use 'despublicado' / 'Despublicar'"),
    (r"tirar (?:o fundo |todo o fundo )?do ar", "use 'Despublicar'"),
    (r"colocar[^`'\"<\n]{0,30}no ar", "use 'Publicar'"),
    (r"retirar[^`'\"<\n]{0,14}da publica", "use 'Voltar para rascunho' ou 'Despublicar'"),
    (r"\bnão pública\b", "use 'não publicado'"),
    # 21/10 (Rafa): "quem usa esse painel não usa o painel do WordPress, nem tem acesso direto… nunca mande alguém para o wordpress"
    (r"wp-admin", "quem usa o painel não entra no site: faça a ação no painel (ou 'avise quem cuida do site')"),
    (r"\b(?:no|pelo|ao|para o|entre no)\s+WordPress\b", "quem usa o painel não entra no site: faça a ação no painel (ou 'avise quem cuida do site')"),
]

# --- CAMP-146: as 5 situações (Chegando · Para conferir · Pronto para publicar · No site · Com problema). Os rótulos antigos de
# situação não voltam como etiqueta (chip) na tela: a situação vem de situacaoTag() (docs/vocabulario.md "Situação")
SITUACAO_ANTIGA = r'<span class="tag[^"]*">\s*(?:Em leitura|Na fila|Lendo|Importar folhas|Importar|Conferir(?: \$\{[^}]*\})?|Aprovar(?: lote)?|Publicar|Publicada|Erro(?: no CAMP Vision)?|aguardando importação|em revisão|pronta para aprovar)\s*</span>'
for m in re.finditer(SITUACAO_ANTIGA, text):
    errors.append(f"situação: etiqueta antiga '{m.group(0)[:60]}' em {_rel(HTML)}:{text.count(chr(10), 0, m.start()) + 1} — use situacaoTag() (CAMP-146)")
if "const SITUACOES={chegando:['b','Chegando'],conferir:['a','Para conferir'],pronto:['g','Pronto para publicar'],no_site:['g','No site'],problema:['r','Com problema']}" not in text:
    errors.append("situação: o mapa SITUACOES (as 5 situações do CAMP-146) sumiu ou mudou de nome sem atualizar docs/vocabulario.md")
for antigo in ("'CAMP Vision lendo',n(", "'Publicadas',n(", "fundos travados por direitos", "publicação bloqueada até existir termo"):
    if antigo in text:
        errors.append(f"situação: '{antigo}' voltou (CAMP-146)")
# --- CAMP-152 (padrao-de-tela §1): na página do projeto, Despublicar e Voltar para rascunho só no "Mais ⋯", em vermelho (perigo-txt + menuitem)
for m in re.finditer(r"publicarProjeto\('\$\{c\}','(rascunho|tirar_do_ar)',this\)", text):
    trecho = text[text.rfind("<button", 0, m.start()):m.start()]
    if 'perigo-txt' not in trecho or 'role="menuitem"' not in trecho:
        errors.append(f"perigo: botão '{m.group(1)}' do projeto fora do menu 'Mais ⋯' ou sem vermelho (linha {text.count(chr(10), 0, m.start()) + 1}) — CAMP-152")
fb = re.search(r"function botoesPublicacao\(code,g\)\{.*?\n  return h\}", text, re.S)
if fb and re.search(r"rascunho|tirar_do_ar", fb.group(0)):
    errors.append("perigo: a aba Publicação voltou a ter Voltar para rascunho/Despublicar fora do 'Mais ⋯' (CAMP-152)")
for arq in [HTML, *sorted((ROOT / "backend" / "app").glob("*.py"))]:
    conteudo = arq.read_text(encoding="utf-8")
    for padrao, dica in PROIBIDAS:
        for m in re.finditer(padrao, conteudo, re.I):
            linha = conteudo.count("\n", 0, m.start()) + 1
            errors.append(f"vocabulário: '{m.group(0)}' em {_rel(arq)}:{linha} — {dica}")

# --- CAMP-HOME-UX (Rafael, 22/11/2026: "não quero que fique infantil o sistema, tá? é algo bem sério"): tom sério e profissional.
# Nada de nível/título de jogo, XP, medalha, selo, troféu, emoji ou comemoração na interface (docs/padroes.md §15, docs/vocabulario.md
# "Tom"). Os comentários do código ficam de fora (podem citar a regra); o que vale é o que chega à tela.
# ÚNICA EXCEÇÃO (Rafael, 22/11/2026, apontando o cartão "Marcos": "aqui sim pode ficar gamificado como estava antes, com ícones e emojis"):
# emoji e arte de selo são aceitos SÓ entre os comentários MARCOS-ICONES-INICIO e MARCOS-ICONES-FIM, uma vez só no arquivo, num trecho curto
# que só declara funções/constantes marco*/MARCOS_*. Todo o resto (inclusive nível, XP, "Parabéns", exclamação) vale também lá dentro.
TOM_MARCA_INI, TOM_MARCA_FIM, TOM_MAX_LINHAS = "MARCOS-ICONES-INICIO", "MARCOS-ICONES-FIM", 30
TOM_NOME_MARCOS = re.compile(r"(?:marcos?[A-Z]\w*|MARCOS?_\w+)")
_TOM_GERAL = ((r"Guardião do Acervo|Primeiros passos|Olhar atento|Mão firme|Memória viva|Referência do acervo", "título de nível de jogo"),
              (r"(?<![\w-])XP(?![\w-])", "XP (use 'pontos validados')"),
              (r"Nível (?:\d+|\$\{[^}]*\})\s*·", "'Nível N · …' (sem níveis na tela: 'Seu trabalho')"),
              (r"Suas conquistas|Conquistas recentes|Seu progresso na resolução|dias? de sequência", "nome antigo da gamificação (use 'Seu trabalho' / 'Marcos')"),
              (r"Parabéns|[Cc]onfete|confetti", "comemoração (confirmação discreta, sem festa)"),
              (r"[A-Za-zÀ-ú]!['\"`<]", "frase com exclamação (tom sério: ponto final)"))
_TOM_SO_MARCOS = ((r"INI_MEDALHA|INI_SELO|ini-medalha|ini-selo|ini-nivel-card|cp-badge|CP_HEX|cp-hex|fc-medalha|cpIc\('trofeu'|MARCOS_SELO|marcosSeloSVG\(|MARCOS_EMOJI",
                   "arte de medalha, selo, hexágono ou troféu (só no cartão Marcos)"),
                  ("[\U0001F000-\U0001FAFF⌚⌛⏩-⏳⏸-⏺☔☕♈-♓♿⚓⚡⚪⚫⚽⚾"
                   "⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽✅✊✋✨❌❎❓-❕❗➕-➗"
                   "➰➿⬛⬜⭐⭕️]", "emoji (use texto, ✓/✕/! ou um ícone de traço neutro; só o cartão Marcos tem emoji)"))


def _tom_sem_coment(t):
    t = re.sub(r"/\*.*?\*/|<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), t, flags=re.S)   # mantém as linhas no lugar
    return re.sub(r"(?m)^\s*//.*$", " ", t)


def erros_tom(t, nome="index.html"):
    """Erros de tom do texto t. O trecho MARCOS-ICONES (se houver um só, curto e só com marco*/MARCOS_*) pode ter emoji e selo."""
    out, livre = [], t
    ni, nf = t.count(TOM_MARCA_INI), t.count(TOM_MARCA_FIM)
    if ni or nf:
        a, b = t.find(TOM_MARCA_INI), t.find(TOM_MARCA_FIM)
        if ni != 1 or nf != 1 or b < a:
            out.append(f"tom: o trecho de exceção dos Marcos tem de aparecer uma vez só ({TOM_MARCA_INI} {ni}×, {TOM_MARCA_FIM} {nf}×) em {nome}")
        else:
            trecho = t[a:b]
            ln0 = t.count("\n", 0, a) + 1
            if trecho.count("\n") > TOM_MAX_LINHAS:
                out.append(f"tom: o trecho de exceção dos Marcos ({nome}:{ln0}) passou de {TOM_MAX_LINHAS} linhas: a exceção é só o cartão Marcos")
            corpo = t[t.rfind("/*", 0, a):b] if t.rfind("/*", 0, a) > t.rfind("*/", 0, a) else trecho   # a marca fica num comentário: começa nele
            ln1 = t.count("\n", 0, b - len(corpo)) + 1
            for m in re.finditer(r"(?m)^(?:async\s+)?(?:function\s+([\w$]+)|(?:const|let|var)\s+([\w$]+)|([\w$.]+)\s*[(=])", _tom_sem_coment(corpo)):
                nm = m.group(1) or m.group(2) or m.group(3)
                if not TOM_NOME_MARCOS.fullmatch(nm or ""):
                    out.append(f"tom: '{nm}' dentro do trecho de exceção dos Marcos ({nome}:{ln1 + corpo.count(chr(10), 0, m.start())}): ali só cabem funções/constantes marco*/MARCOS_*")
            livre = t[:a] + re.sub(r"[^\n]", " ", trecho) + t[b:]
    for fonte, pads in ((t, _TOM_GERAL), (livre, _TOM_SO_MARCOS)):
        sc = _tom_sem_coment(fonte)
        for _pad, _dica in pads:
            for m in re.finditer(_pad, sc):
                out.append(f"tom: '{m.group(0)}' na interface ({nome}:{sc.count(chr(10), 0, m.start()) + 1}) — {_dica}; sem elementos infantis ou de jogo (padroes.md §15)")
    return out


# autoteste da exceção (roda sempre): emoji/selo só passam dentro do trecho dos Marcos; fora dele, ou com outra função lá dentro, falham
_ok = "/* MARCOS-ICONES-INICIO */\nconst MARCOS_EMOJI={folha:'\U0001F3C5'};\nfunction marcoIcHTML(t){return `<span>⭐</span>`}\n/* MARCOS-ICONES-FIM */\n"
for _caso, _txt, _espera in (("emoji só nos Marcos", "function ok(){return 'Seu trabalho'}\n" + _ok, 0),
                             ("emoji fora dos Marcos", _ok + "function rankingHTML(){return '<b>\U0001F3C6 1º</b>'}\n", 1),
                             ("selo fora dos Marcos", _ok + "function trabHTML(){return marcosSeloSVG('escudo','check')}\n", 1),
                             ("outra função no trecho dos Marcos", _ok.replace("function marcoIcHTML", "function rankingIcHTML"), 1),
                             ("trecho repetido", _ok + _ok, 1),
                             ("XP dentro dos Marcos", _ok.replace("<span>⭐", "<span>⭐ 10 XP"), 1),
                             ("sem trecho, emoji em qualquer lugar", "function seuTrabalhoHTML(){return '✅ ok'}\n", 1)):
    _n = len(erros_tom(_txt, "autoteste"))
    if (_n == 0) != (_espera == 0):
        errors.append(f"tom: autoteste da exceção dos Marcos falhou em '{_caso}' ({_n} erro(s))")
errors.extend(erros_tom(text, str(_rel(HTML))))

# --- atalhos do menu: a tabela NAV_ATALHOS segue a ORDEM VISUAL do menu (dígitos 1-9 em sequência; UX-28: letras podem vir entre eles) ---
mapa = re.search(r"const NAV_ATALHOS=\{([^}]*)\}", text)
menu = re.search(r'<nav class="nav" id="nav">(.*?)</nav>', text, re.S)
if not mapa or not menu:
    errors.append("atalhos: não achei NAV_ATALHOS ou o <nav> do menu")
else:
    teclas = dict(re.findall(r"(\w+):'(.)'", mapa.group(1)))
    ordem = re.findall(r'<button data-v="(\w+)"', menu.group(1))
    for v in ordem:
        if v not in teclas:
            errors.append(f"atalhos: o item de menu '{v}' não tem tecla em NAV_ATALHOS")
    for v in teclas:
        if v not in ordem:
            errors.append(f"atalhos: NAV_ATALHOS tem '{v}', que não existe no menu")
    digitos = [teclas[v] for v in ordem if v in teclas and teclas[v].isdigit()]
    if digitos != [str(i) for i in range(1, len(digitos) + 1)] or len(digitos) > 9:
        errors.append(f"atalhos: os dígitos deveriam ser 1..N na ordem do menu, mas estão {digitos}")
    # UX-28: o menu segue a ordem do trabalho e as teclas NÃO mudaram (1 Precisa de você · 2 Projetos · 3 Fundos · 4 Pedidos
    # de alta resolução · 5 Máquinas). Regra: dígitos crescentes na ordem do menu e só em item visível sem abrir o "Mais".
    no_mais = set(re.findall(r'<button data-v="(\w+)"[^>]*class="nav-sec"', menu.group(1)))
    for v in ordem:
        if v in teclas and teclas[v].isdigit() and v in no_mais:
            errors.append(f"atalhos: '{v}' tem o dígito {teclas[v]} mas fica escondido no \"Mais\" (dígito só em item sempre à vista)")
    todas = [k.lower() for k in teclas.values()]
    if len(set(todas)) != len(todas):
        errors.append("atalhos: há teclas repetidas em NAV_ATALHOS")
    for k in todas:
        if k in ("f", "k", "b", "?", "["):
            errors.append(f"atalhos: a tecla '{k}' é reservada (F filtro, ⌘K busca, [ e ⌘B recolher o menu, ? ajuda)")
    # UX-28 (menu recolhido): a ajuda de atalhos diz cada tecla do menu com o NOME ATUAL do item ("1–5" = 1..5; "D · N · P" na ordem da descrição)
    nomes = {v: re.sub(r"<[^>]+>", "", n).strip() for v, n in re.findall(r'<button data-v="(\w+)"[^>]*>(?:<svg.*?</svg>)?([^<]*)', menu.group(1), re.S)}
    aj = re.search(r"const AJUDA_ATALHOS=\[(.*?)\];", text)
    na_ajuda = {}
    for k, d in re.findall(r"\['([^']*)','([^']*)'\]", aj.group(1) if aj else ""):
        m = re.fullmatch(r"(\d)–(\d)", k)
        ks = [str(i) for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else k.split(" · ")
        ds = d.split(" · ")
        if len(ks) == len(ds) and all(re.fullmatch(r"[A-Z0-9]", x) for x in ks):
            na_ajuda.update({x: re.sub(r"\s*\(.*\)$", "", ds[i]).strip() for i, x in enumerate(ks)})
    for v, k in teclas.items():
        if v in nomes and na_ajuda.get(k) != nomes[v]:
            errors.append(f"atalhos: a ajuda (AJUDA_ATALHOS) diz {k} = '{na_ajuda.get(k)}', mas o item do menu se chama '{nomes[v]}'")

# Sintaxe do JavaScript (23/11/2026, CAMP-PAT-JS): um erro de sintaxe num <script> derruba a tela inteira, e nem a suíte do backend nem as
# checagens de texto acima percebem (o botão "Gerar link de pagamento" do PR #199 tinha aspas trocadas). Cada <script> embutido passa
# pelo `node --check`; sem node na máquina, avisa e segue.
import shutil as _sh, subprocess as _sp, tempfile as _tf
_node = _sh.which("node")
if _node:
    for _i, _js in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, re.S)):
        if not _js.strip():
            continue
        with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as _f:
            _f.write(_js)
        _r = _sp.run([_node, "--check", _f.name], capture_output=True, text=True)
        os.unlink(_f.name)
        if _r.returncode != 0:
            _msg = next((l for l in (_r.stderr or "").splitlines() if "Error" in l), (_r.stderr or "").strip()[:200])
            errors.append(f"javascript: o <script> nº {_i + 1} tem erro de sintaxe (a tela inteira para): {_msg}")
else:
    print("aviso: sem node nesta máquina, a sintaxe do JavaScript não foi conferida")

if errors:
    print("UI CHECK FALHOU")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"UI CHECK OK · {len(required_css)} seletores · {len(required_dom)} estruturas · {inline} estilos inline · vocabulário único ok · atalhos ok · tom ok (exceção só nos Marcos)")
