#!/usr/bin/env python3
"""Cenários do grupo D (CAMP-096 a CAMP-101: folhas de outro projeto e duplicatas) no formato REAL do CAMP Vision.

A pasta do projeto já existe (tests/fluxo_real_cv2.py reservar + processando). Este script grava imagens, pacote_tainacan.json,
erros.json e, por último, status.json "pronto", e avisa o painel por HTTP — como o CAMP Vision faz.

  retirados BASE RAIZ CODIGO   -> D1..D3 em documentos (D3 com sinal "projeto divergente": já entra no painel);
                                  retirados: D4 de outra obra SEM imagem nenhuma, D5 "sem identificação", D6 capa, D7 de outra obra com imagem
  dup50     BASE RAIZ CODIGO   -> 50 folhas; D26..D50 são cópias de D1..D25 (duplicata_de + tipo_duplicata "quase" ou "", como no contrato)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fluxo_real_cv2 import doc, http, pasta_do, prancha  # noqa: E402


def _base(raiz, codigo):
    p = pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    for d in (prev, jpg, tif, p / "catalogacao"):
        d.mkdir(parents=True, exist_ok=True)
    return p, nome, prev, jpg, tif


def _imagem(im, cod, prev, jpg, tif):
    im.save(jpg / f"{cod}.jpg", "JPEG", quality=80)
    im.save(tif / f"{cod}.tif", "TIFF")
    pv = im.copy(); pv.thumbnail((700, 700)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=75)


def _fechar(base, raiz, codigo, p, nome, documentos, retirados, erros, n_imagens):
    pac = {"versao": 2, "gerado_em": "2026-10-20T11:00:00-03:00", "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "uf": "SP", "capa_sugerida": f"{codigo}-1972-S01-D00001"},
           "documentos": documentos, "itens": documentos, "retirados": retirados, "propostas": {}, "avisos": [], "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False, indent=1), encoding="utf-8")
    lote = f"20261020-110000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T11:00:05-03:00", "lote_atual": lote,
                                               "versao_cv2": "2026-10-13-01", "fase": "organizado_v2", "lotes_prontos": [lote], "imagens": n_imagens,
                                               "folhas": len(documentos), "erros_bloqueantes": 0, "motivo": ""}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": str(p.relative_to(raiz)), "status": "pronto"}), ensure_ascii=False))


def retirados(base, raiz, codigo):
    p, nome, prev, jpg, tif = _base(raiz, codigo)
    raiz_rel = str(p.relative_to(raiz))
    car = [nome[:22], "Arq. Sami Bussab", "1972"]
    D = lambda n: f"{codigo}-1972-S01-D{n:05d}"
    documentos, retirados_, erros = [], [], []
    for n, titulo in ((1, "PLANTA TÉRREO"), (2, "CORTE AA")):
        _imagem(prancha(titulo, car), D(n), prev, jpg, tif)
        documentos.append(doc(nome, codigo, n, raiz_rel))
    # D3: o CAMP Vision achou que é de outra obra mas DEIXOU no lote (entra no painel com o sinal)
    _imagem(prancha("ELEVAÇÃO", ["CASA OUTRA OBRA", "Arq. Sami Bussab", "1972"]), D(3), prev, jpg, tif)
    documentos.append(doc(nome, codigo, 3, raiz_rel, projeto_divergente=True, sinais=["projeto divergente: o carimbo diz 'CASA OUTRA OBRA'"]))
    # D4: retirada de outra obra SEM imagem nenhuma (nem prévia, nem JPG): só o registro no pacote
    d4 = doc(nome, codigo, 4, raiz_rel)
    d4.update(publicavel=False, projeto_divergente=True, arquivos=[], preview="", arquivo="",
              bloqueios=["projeto divergente: o carimbo diz 'RESIDÊNCIA SEM IMAGEM'"])
    retirados_.append(d4)
    erros.append({"arquivo": D(4), "categoria": "projeto", "gravidade": "bloqueia", "origem": "CAMP Vision",
                  "detalhe": "D00004 com identificação para outra pasta (RESIDÊNCIA SEM IMAGEM) — fora da publicação até resolver"})
    # D5: "sem identificação" (pasta com várias obras)
    _imagem(prancha("DETALHE", ["(sem carimbo)"]), D(5), prev, jpg, tif)
    retirados_.append({**doc(nome, codigo, 5, raiz_rel), "publicavel": False, "sem_identificacao": True,
                       "bloqueios": ["sem identificação (pasta com várias obras)"]})
    # D6: capa da pasta
    _imagem(prancha("CAPA DA PASTA", ["PASTA 12"]), D(6), prev, jpg, tif)
    retirados_.append({**doc(nome, codigo, 6, raiz_rel), "publicavel": False, "capa": "capa da pasta (folha de rosto)",
                       "bloqueios": ["capa: folha de rosto da pasta, não é desenho"]})
    # D7: retirada de outra obra COM imagem (devolve, publica e tenta desfazer depois)
    _imagem(prancha("PLANTA COBERTURA", car), D(7), prev, jpg, tif)
    retirados_.append({**doc(nome, codigo, 7, raiz_rel), "publicavel": False, "projeto_divergente": True,
                       "bloqueios": [f"projeto divergente: o carimbo diz '{nome}' (grupo pequeno sem projeto na base)"]})
    erros.append({"arquivo": D(7), "categoria": "projeto", "gravidade": "bloqueia", "origem": "CAMP Vision",
                  "detalhe": f"D00007 com identificação para outra pasta ({nome}) — fora da publicação até resolver"})
    _fechar(base, raiz, codigo, p, nome, documentos, retirados_, erros, 7)


def dup50(base, raiz, codigo):
    p, nome, prev, jpg, tif = _base(raiz, codigo)
    raiz_rel = str(p.relative_to(raiz))
    D = lambda n: f"{codigo}-1972-S01-D{n:05d}"
    documentos, erros = [], []
    for n in range(1, 51):
        orig = n - 25 if n > 25 else n
        im = prancha(f"PRANCHA {orig:02d}", [nome[:22], "Arq. Sami Bussab", "1972"], w=700, h=495)
        _imagem(im, D(n), prev, jpg, tif)
        if n > 25:
            tipo = "quase" if n % 2 else ""
            documentos.append(doc(nome, codigo, n, raiz_rel, titulo=f"Planta {orig}", duplicata_de=D(orig), tipo_duplicata=tipo, publicavel=False,
                                  bloqueios=[f"duplicata de {D(orig)}"]))
            erros.append({"arquivo": D(n), "categoria": "duplicata", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": f"quase de {D(orig)} — só a única publica"})
        else:
            documentos.append(doc(nome, codigo, n, raiz_rel, titulo=f"Planta {n}", tipo_duplicata=""))
    _fechar(base, raiz, codigo, p, nome, documentos, [], erros, 50)


if __name__ == "__main__":
    {"retirados": retirados, "dup50": dup50}[sys.argv[1]](*sys.argv[2:5])
