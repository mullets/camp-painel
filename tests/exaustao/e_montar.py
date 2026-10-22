#!/usr/bin/env python3
"""Cenários do grupo E (CAMP-102 a CAMP-108) pelo caminho real: a pasta final do CAMP Vision montada a partir de uma ESPECIFICAÇÃO
(folhas, retiradas e erros.json) e o aviso HTTP ao painel, como o CAMP Vision faz. Reaproveita tests/fluxo_real_cv2.py (sem editá-lo).

  lote BASE RAIZ CODIGO '<spec json>' [--sem-aviso]   -> grava imagens, pacote, erros.json, status "pronto" e avisa o painel
  reservar_parecido BASE FUNDO "TITULO"               -> a estação pede um número para um nome parecido com um projeto que já existe
                                                         (sem confirmar_novo): o painel abre a decisão "projeto parecido"

spec = {"docs": [{"n": 1, "titulo": "PLANTA", "campos": {...}}], "retirados": [{"n": 7, "carimbo": "OUTRA OBRA"}], "erros": [{...}]}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402


def lote(base, raiz, codigo, spec, sem_aviso=False):
    spec = json.loads(json.dumps(spec).replace("{P}", codigo))
    p = cv.pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    prev.mkdir(parents=True, exist_ok=True)
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    jpg.mkdir(parents=True, exist_ok=True); tif.mkdir(parents=True, exist_ok=True)
    car = [nome[:22], "Arq. Sami Bussab", str(spec.get("ano_carimbo", "1972"))]
    documentos, retirados = [], []
    for d in spec.get("docs", []):
        n = d["n"]; cod = f"{codigo}-1972-S01-D{n:05d}"
        im = cv.prancha(d.get("titulo", f"PRANCHA {n}"), car, girar=d.get("girar", 0), espelhar=d.get("espelhar", False), w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=80); im.save(prev / f"{cod}.jpg", "JPEG", quality=75)
        documentos.append(cv.doc(nome, codigo, n, raiz_rel, **d.get("campos", {})))
    for r in spec.get("retirados", []):
        n = r["n"]; cod = f"{codigo}-1972-S01-D{n:05d}"; carimbo = r.get("carimbo", "OUTRA OBRA")
        im = cv.prancha(r.get("titulo", f"PRANCHA {n}"), [carimbo[:22], "Arq. Outro", "1981"], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=80); im.save(prev / f"{cod}.jpg", "JPEG", quality=75)
        retirados.append({**cv.doc(nome, codigo, n, raiz_rel), "publicavel": False, "projeto_divergente": True, "motivo": "projeto divergente",
                          "bloqueios": [f"projeto divergente: o carimbo diz '{carimbo}' (grupo pequeno sem projeto na base)"]})
    pac = {"versao": 2, "gerado_em": "2026-10-20T10:20:00-03:00", "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": str(spec.get("ano_projeto", "1972")), "cidade": "São Paulo", "uf": "SP", "cliente": "", "endereco": "",
                       "fontes": {}, "lacunas": [], "capa_sugerida": f"{codigo}-1972-S01-D{spec['docs'][0]['n']:05d}" if spec.get("docs") else ""},
           "documentos": documentos, "itens": documentos, "retirados": retirados, "propostas": {}, "avisos": [], "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    erros = [{**e, "arquivo": e["arquivo"].replace("{P}", codigo)} for e in spec.get("erros", [])]
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False, indent=1), encoding="utf-8")
    lote_ = f"20261020-102000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T10:20:05-03:00", "lote_atual": lote_,
                                               "versao_cv2": "2026-10-13-01", "fase": "organizado_v2", "lotes_prontos": [lote_], "imagens": len(documentos) + len(retirados),
                                               "folhas": len(documentos), "erros_bloqueantes": sum(1 for e in erros if e.get("gravidade") == "bloqueia"), "motivo": ""},
                                              ensure_ascii=False), encoding="utf-8")
    if sem_aviso:
        print(json.dumps({"aviso": "não enviado"}))
    else:
        print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


def erro(base, raiz, codigo, motivo, erros_json="[]"):
    """O CAMP Vision parou com erro nesta pasta (status.json "erro" + motivo) e avisou o painel."""
    p = cv.pasta_do(raiz, codigo)
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    erros = [{**e, "arquivo": e.get("arquivo", "").replace("{P}", codigo)} for e in json.loads(erros_json)]
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "erro", "status_em": "2026-10-20T10:20:05-03:00", "motivo": motivo, "mensagem": motivo},
                                              ensure_ascii=False), encoding="utf-8")
    print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": str(p.relative_to(raiz)), "status": "erro"}), ensure_ascii=False))


def reservar_parecido(base, fundo, titulo):
    try:
        r = cv.http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": fundo, "titulo": titulo, "ano": 1972, "cidade": "São Paulo",
                                                               "identificacao_original": f"P - {titulo}", "operador": "Beatriz"})
    except Exception as e:  # noqa: BLE001 (o painel pode responder 409/202 com a decisão)
        r = {"erro": str(e), "corpo": getattr(e, "read", lambda: b"")().decode("utf-8", "replace")}
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "lote":
        lote(a[0], a[1], a[2], json.loads(a[3]), "--sem-aviso" in a)
    elif cmd == "erro":
        erro(*a[:4], *(a[4:5] or []))
    elif cmd == "reservar_parecido":
        reservar_parecido(*a[:3])
    else:
        sys.exit(f"comando desconhecido: {cmd}")
