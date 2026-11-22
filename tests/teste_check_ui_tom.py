#!/usr/bin/env python3
"""CAMP-HOME-UX (Rafael, 22/11/2026, apontando o cartão "Marcos": "aqui sim pode ficar gamificado como estava antes, com ícones e emojis").

O check_ui aceita emoji e arte de selo SÓ no trecho MARCOS-ICONES do index.html (o cartão Marcos). Este teste roda o check_ui de verdade
(`--html` numa cópia do index.html) e prova que:
  - o index.html atual passa, e o trecho dos Marcos existe e tem emoji (a exceção está em uso);
  - emoji plantado no ranking ou em "Seu trabalho" continua barrado;
  - selo dos Marcos usado fora do cartão continua barrado;
  - uma função que não é dos Marcos colocada dentro do trecho de exceção é barrada (a exceção não vira porta aberta).
Uso: python3 tests/teste_check_ui_tom.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HTML = RAIZ / "frontend" / "index.html"
falhas = []


def chk(ok, msg):
    print(("ok    " if ok else "FALHA ") + msg)
    if not ok:
        falhas.append(msg)


def check_ui(conteudo):
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as d:
        alvo = Path(d) / "index.html"
        alvo.write_text(conteudo, encoding="utf-8")
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "check_ui.py"), "--html", str(alvo)], capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr


base = HTML.read_text(encoding="utf-8")
ini, fim = base.find("MARCOS-ICONES-INICIO"), base.find("MARCOS-ICONES-FIM")
trecho = base[ini:fim] if 0 <= ini < fim else ""
chk(bool(trecho) and bool(re.search("[\U0001F300-\U0001FAFF⭐✅]", trecho)), "o index.html tem o trecho de exceção dos Marcos, com emoji")

rc, out = check_ui(base)
chk(rc == 0 and "tom ok" in out, f"o index.html atual passa no check_ui (rc={rc}) {out.strip()[-300:]}")


def plantar(antes, depois, desc):
    if base.count(antes) != 1:
        chk(False, f"{desc}: âncora não encontrada ({antes[:60]})")
        return None
    return base.replace(antes, depois)


casos = [
    ("emoji no ranking", "<td>${escHtml(r.nome)}</td>", "<td>\U0001F3C6 ${escHtml(r.nome)}</td>", "tom: '\U0001F3C6'"),
    ("emoji em \"Seu trabalho\"", "<dt>Pontos validados nesta semana</dt>", "<dt>\U0001F525 Pontos validados nesta semana</dt>", "tom: '\U0001F525'"),
    ("selo dos Marcos fora do cartão", "function trabalhoNumerosHTML(e){", "function trabalhoNumerosHTML(e){const _s=marcosSeloSVG('escudo','check');", "tom: 'marcosSeloSVG('"),
    ("função que não é dos Marcos dentro do trecho", "/* MARCOS-ICONES-FIM */", "function rankingIcHTML(){return '\U0001F947'}\n/* MARCOS-ICONES-FIM */", "tom: 'rankingIcHTML' dentro do trecho"),
]
for desc, antes, depois, espera in casos:
    t = plantar(antes, depois, desc)
    if t is None:
        continue
    rc, out = check_ui(t)
    chk(rc != 0 and espera in out, f"{desc}: o check_ui recusa (rc={rc}, espera \"{espera}\") {out.strip()[-240:]!r}")

print(f"\n{len(falhas)} falha(s)" if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
