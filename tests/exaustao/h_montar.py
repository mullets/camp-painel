#!/usr/bin/env python3
"""Cenário do print de 20/10 (F026-P0009 CRASA): o CAMP Vision manda em erros.json, para CADA folha, o aviso
"série incerta na triagem — sinais misturados (papel escuro ou foto em prancha); conferir na folha de contatos".
Uso: h_montar.py BASE RAIZ CODIGO CATEGORIA  → acrescenta o aviso nas 6 folhas do lote e avisa o painel (HTTP, como o CAMP Vision)."""
import json, sys, urllib.request
from pathlib import Path
base, raiz, cod, cat = sys.argv[1:5]
p = sorted((Path(raiz) / "F026 - SBU Sami Bussab" / "01 - Projetos").glob(cod + " - *"))[0]
arq = p / "catalogacao" / "erros.json"
erros = json.loads(arq.read_text(encoding="utf-8"))
for n in range(1, 7):
    erros.append({"arquivo": f"{cod}-1972-S01-D{n:05d}", "categoria": cat, "gravidade": "aviso", "origem": "CAMP Vision",
                  "detalhe": "série incerta na triagem — sinais misturados (papel escuro ou foto em prancha); conferir na folha de contatos"})
arq.write_text(json.dumps(erros, ensure_ascii=False, indent=1), encoding="utf-8")
req = urllib.request.Request(base + "/api/campvision/aviso", data=json.dumps({"codigo": cod, "pasta": str(p.relative_to(raiz)), "status": "pronto"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(req, timeout=30).read().decode())
