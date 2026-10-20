#!/usr/bin/env python3
"""Cenários do grupo A (estados do lote, CAMP-072..079) que o simulador comum não gera. Usa tests/fluxo_real_cv2.py sem mudá-lo.

  erro       BASE RAIZ CODIGO "MENSAGEM"   -> status.json "erro" com a mensagem (o CAMP Vision parou) + aviso
  complemento BASE RAIZ CODIGO N           -> o CAMP Vision traz N folhas NOVAS (D00009…) para a mesma pasta + status "pronto" + aviso
  releitura  BASE RAIZ CODIGO              -> o CAMP Vision relê o lote: títulos e ano mudam no pacote ("RELIDA …") + aviso
  sumir      RAIZ CODIGO                   -> a pasta do projeto some do QNAP (renomeada para fora da raiz)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402


def _aviso(base, raiz, codigo, p, status):
    return cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": str(p.relative_to(raiz)), "status": status})


def erro(base, raiz, codigo, msg):
    p = cv.pasta_do(raiz, codigo)
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "erro", "status_em": "2026-10-20T10:30:00-03:00", "mensagem": msg, "motivo": msg},
                                              ensure_ascii=False), encoding="utf-8")
    print(json.dumps(_aviso(base, raiz, codigo, p, "erro"), ensure_ascii=False))


def complemento(base, raiz, codigo, n):
    p = cv.pasta_do(raiz, codigo)
    pac_f = p / "catalogacao" / "pacote_tainacan.json"
    pac = json.loads(pac_f.read_text(encoding="utf-8"))
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    jpg = p / "01 - Desenhos e pranchas" / "JPG"
    nome = p.name.split(" - ", 1)[1]
    for k in range(int(n)):
        seq = 9 + k
        cod = f"{codigo}-1972-S01-D{seq:05d}"
        im = cv.prancha(f"COMPLEMENTO {seq}", [nome[:22], "Arq. Sami Bussab", "1972"])
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=85)
        pv = im.copy(); pv.thumbnail((900, 900)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=80)
        d = cv.doc(nome, codigo, seq, raiz_rel)
        d["arquivos"] = [d["arquivos"][0]]
        pac["documentos"].append(d)
    pac["itens"] = pac["documentos"]
    pac_f.write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    st = json.loads((p / "status.json").read_text(encoding="utf-8"))
    st.update({"status": "pronto", "status_em": "2026-10-20T15:00:00-03:00", "imagens": st.get("imagens", 8) + int(n)})
    (p / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(_aviso(base, raiz, codigo, p, "pronto"), ensure_ascii=False))


def releitura(base, raiz, codigo):
    p = cv.pasta_do(raiz, codigo)
    pac_f = p / "catalogacao" / "pacote_tainacan.json"
    pac = json.loads(pac_f.read_text(encoding="utf-8"))
    for d in pac["documentos"]:
        d["titulo"] = "RELIDA " + d["titulo"]
        d["ano"] = "1999"
        d["rotacao_aplicada"] = 0
    pac["itens"] = pac["documentos"]
    pac["gerado_em"] = "2026-10-20T16:00:00-03:00"
    pac_f.write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    st = json.loads((p / "status.json").read_text(encoding="utf-8"))
    st.update({"status": "pronto", "status_em": "2026-10-20T16:00:05-03:00"})
    (p / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(_aviso(base, raiz, codigo, p, "pronto"), ensure_ascii=False))


def sumir(raiz, codigo):
    p = cv.pasta_do(raiz, codigo)
    destino = Path(raiz).parent / ("sumida_" + p.name)
    p.rename(destino)
    print(json.dumps({"de": str(p), "para": str(destino)}, ensure_ascii=False))


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    {"erro": erro, "complemento": complemento, "releitura": releitura, "sumir": sumir}[cmd](*a)
