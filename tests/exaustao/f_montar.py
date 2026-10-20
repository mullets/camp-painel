#!/usr/bin/env python3
"""Montador do grupo F (site e publicação, CAMP-109 a CAMP-114): um lote LIMPO de N folhas pelo caminho real do CAMP Vision.

  processando BASE RAIZ CODIGO "NOME" [--teste] -> como `fluxo_real_cv2.py processando`, mas com "teste": true já no info_projeto
                                          (o CAMP Vision grava o lote de teste assim desde o começo).
  pronto BASE RAIZ CODIGO N [--teste]   -> depois de `fluxo_real_cv2.py reservar` e `processando`: grava N pranchas (JPG, TIF e prévia),
                                          pacote_tainacan.json sem retirados nem problemas, erros.json vazio e, por último, status.json
                                          "pronto"; avisa o painel. --teste: lote de teste ("teste": true no info_projeto e no pacote).
Usa as mesmas peças de tests/fluxo_real_cv2.py (imagens, documento do pacote, aviso HTTP); não muda aquele arquivo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402


def pronto(base, raiz, codigo, n, teste=False):
    p = cv.pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    raiz_rel = str(p.relative_to(raiz))
    info = json.loads((p / "info_projeto.json").read_text(encoding="utf-8"))
    info.update({"folhas_esperadas": n, "teste": bool(teste)})
    (p / "info_projeto.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    prev.mkdir(parents=True, exist_ok=True)
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    jpg.mkdir(parents=True, exist_ok=True)
    tif.mkdir(parents=True, exist_ok=True)
    docs = []
    for i in range(1, n + 1):
        cod = f"{codigo}-1972-S01-D{i:05d}"
        im = cv.prancha(f"PRANCHA {i:02d}", [nome[:22], "Arq. Sami Bussab", "1972"])
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=85)
        im.save(tif / f"{cod}.tif", "TIFF")
        pv = im.copy(); pv.thumbnail((900, 900)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=80)
        docs.append(cv.doc(nome, codigo, i, raiz_rel, publicavel=not teste))
    pac = {"versao": 2, "gerado_em": "2026-10-20T10:20:00-03:00", "teste": bool(teste), "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "uf": "SP", "cliente": "", "endereco": "", "fontes": {}, "lacunas": [],
                       "programa_sugerido": [], "natureza_sugerida": [], "capa_sugerida": f"{codigo}-1972-S01-D00001", "descricao_sugerida": ""},
           "documentos": docs, "itens": docs, "retirados": [], "propostas": {}, "avisos": [], "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text("[]", encoding="utf-8")
    lote = f"20261020-102000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T10:20:05-03:00", "lote_atual": lote, "versao_cv2": "2026-10-13-01",
                                               "fase": "organizado_v2", "lotes_prontos": [lote], "imagens": n, "folhas": n, "a_revisar": 0, "erros_bloqueantes": 0, "motivo": ""},
                                              ensure_ascii=False), encoding="utf-8")
    print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


def processando(base, raiz, codigo, nome, teste=False):
    p = cv.pasta_do(raiz, codigo, nome)
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "info_projeto.json").write_text(json.dumps({"codigo": codigo, "nome": nome, "fundo_codigo": codigo[:4], "ano": "1972", "folhas_esperadas": 3,
                                                     "estacao": "scanner-a3", "tipo_estacao": "windows", "operador": "Beatriz", "operador_email": "operador@camp.arq.br",
                                                     "teste": bool(teste), "atualizado_em": "2026-10-20T10:00:00-03:00", "gerado_por": "CAMP Vision 2 2026-10-13-01"},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "processando", "status_em": "2026-10-20T10:00:05-03:00", "fase": "lendo"}), encoding="utf-8")
    print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": str(p.relative_to(raiz)), "status": "processando"}), ensure_ascii=False))


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "processando":
        processando(a[0], a[1], a[2], a[3], "--teste" in a)
    elif cmd == "pronto":
        pronto(a[0], a[1], a[2], int(a[3]), "--teste" in a)
    else:
        sys.exit(f"comando desconhecido: {cmd}")
