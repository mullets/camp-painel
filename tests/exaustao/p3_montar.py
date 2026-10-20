#!/usr/bin/env python3
"""CAMP-124 (P3): um lote de 34 folhas como o da F026-P0009 (CRASA), gravado pelo caminho real do CAMP Vision (pasta final,
pacote_tainacan.json, status.json "pronto") e avisado ao painel por HTTP. Reaproveita o desenho das pranchas de tests/fluxo_real_cv2.py.

  python3 tests/exaustao/p3_montar.py BASE RAIZ CODIGO NOME
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402


def pronto34(base, raiz, codigo, nome, n=34):
    p = cv.pasta_do(raiz, codigo, nome)
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    for d in (prev, jpg, tif):
        d.mkdir(parents=True, exist_ok=True)
    documentos = []
    for k in range(1, n + 1):
        cod = f"{codigo}-1972-S01-D{k:05d}"
        im = cv.prancha(f"PRANCHA {k}", [nome[:22], "Arq. Sami Bussab", "1972"], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=70)
        im.save(tif / f"{cod}.tif", "TIFF")
        im.save(prev / f"{cod}.jpg", "JPEG", quality=60)
        documentos.append(cv.doc(nome, codigo, k, raiz_rel))
    pac = {"versao": 2, "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "Santo André", "uf": "SP", "capa_sugerida": f"{codigo}-1972-S01-D00001"},
           "documentos": documentos, "itens": documentos, "retirados": [], "propostas": {}, "avisos": []}
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text("[]", encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "lote_atual": f"20261020-{codigo}", "imagens": n, "folhas": n}), encoding="utf-8")
    print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


if __name__ == "__main__":
    pronto34(*sys.argv[1:5])
