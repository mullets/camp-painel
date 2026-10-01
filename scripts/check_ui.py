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

# Impede voltar a crescer sem controle. O orçamento atual é 176; deixamos pequena folga
# para correções, mas novo layout estrutural deve usar classes/componentes.
inline = len(re.findall(r'\bstyle="', text))
if inline > 180:
    errors.append(f"orçamento de estilos inline excedido: {inline} > 180")

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

if errors:
    print("UI CHECK FALHOU")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"UI CHECK OK · {len(required_css)} seletores · {len(required_dom)} estruturas · {inline} estilos inline")
