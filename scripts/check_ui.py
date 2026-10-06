#!/usr/bin/env python3
"""Falha o deploy se estruturas visuais essenciais desaparecerem do frontend."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "index.html"
text = HTML.read_text(encoding="utf-8")

required_css = [
    ".dash-v2{", ".dash-hero{", ".machine-status{", ".system-banner{",
    ".lab-wrap{", ".lab-preview{", ".bulkbar{", ".fundos-filtros{",
    ".dirty-state{", ".form-summary{", ".modal{", ".drawer{", ".filterbar{",
]
required_dom = [
    'id="v-painel"', 'id="v-fundos"', 'id="v-projetos"', 'id="v-etiquetas"',
    'id="v-config"', 'id="machine-status"', 'id="system-banner"',
    'id="fundos-filtros"', 'id="proj-bulk"', 'id="drawer"',
]

errors = []
for token in required_css:
    if token not in text:
        errors.append(f"CSS essencial ausente: {token}")
for token in required_dom:
    if token not in text:
        errors.append(f"estrutura essencial ausente: {token}")

# Impede voltar a crescer sem controle. O orçamento atual é 183; deixamos pequena folga
# para correções, mas novo layout estrutural deve usar classes/componentes.
inline = len(re.findall(r'\bstyle="', text))
if inline > 190:
    errors.append(f"orçamento de estilos inline excedido: {inline} > 190")

# Detecta HTML/JS de componentes sem seu CSS, causa da regressão real do dashboard.
pairs = [
    ("dash-v2", ".dash-v2{"),
    ("bulkbar", ".bulkbar{"),
    ("fundos-filtros", ".fundos-filtros{"),
    ("machine-status", ".machine-status{"),
    ("lab-wrap", ".lab-wrap{"),
]
for html_class, selector in pairs:
    if html_class in text and selector not in text:
        errors.append(f"componente {html_class} aparece no HTML/JS sem CSS {selector}")

# --- vocabulário único de publicação (docs/vocabulario.md): estas frases NÃO podem voltar ---
PROIBIDAS = [
    (r"\bno ar\b", "use 'publicado' / 'Publicar'"),
    (r"fora do ar", "use 'despublicado' / 'Despublicar'"),
    (r"tirar (?:o fundo |todo o fundo )?do ar", "use 'Despublicar'"),
    (r"colocar[^`'\"<\n]{0,30}no ar", "use 'Publicar'"),
    (r"retirar[^`'\"<\n]{0,14}da publica", "use 'Voltar para rascunho' ou 'Despublicar'"),
    (r"\bnão pública\b", "use 'não publicado'"),
]
for arq in [HTML, *sorted((ROOT / "backend" / "app").glob("*.py"))]:
    conteudo = arq.read_text(encoding="utf-8")
    for padrao, dica in PROIBIDAS:
        for m in re.finditer(padrao, conteudo, re.I):
            linha = conteudo.count("\n", 0, m.start()) + 1
            errors.append(f"vocabulário: '{m.group(0)}' em {arq.relative_to(ROOT)}:{linha} — {dica}")

if errors:
    print("UI CHECK FALHOU")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"UI CHECK OK · {len(required_css)} seletores · {len(required_dom)} estruturas · {inline} estilos inline · vocabulário único ok")
