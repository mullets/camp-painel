#!/usr/bin/env python3
"""Grupo C dos testes de exaustão (CAMP-089 a CAMP-095): o CAMP Vision grava a pasta final com os casos deste grupo e avisa o painel.
Usa as peças de tests/fluxo_real_cv2.py (imagens de verdade, pacote no formato do contrato, aviso HTTP), sem mudar aquele arquivo.

  pronto BASE RAIZ CODIGO conferir2   -> 10 folhas: D1-D3 normais (reter, mover), D4 orientação incerta, D5 ano lido errado,
                                         D6-D7 autoria divergente, D8 bloqueio comum do CAMP Vision, D9-D10 normais (duas pessoas)
  pronto BASE RAIZ CODIGO vinte       -> 20 folhas, 4 com aviso: D3 orientação incerta, D7 ano lido errado, D11 bloqueio comum, D15 duplicata da D14
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402


def gravar(base, raiz, codigo, casos, erros):
    p = cv.pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    prev.mkdir(parents=True, exist_ok=True)
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    jpg.mkdir(parents=True, exist_ok=True); tif.mkdir(parents=True, exist_ok=True)
    docs = []
    for n, titulo, carimbo, girar, campos in casos:
        cod = f"{codigo}-1972-S01-D{n:05d}"
        im = cv.prancha(titulo, carimbo, girar=girar)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=80)
        im.save(tif / f"{cod}.tif", "TIFF")
        pv = im.copy(); pv.thumbnail((900, 900)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=75)
        docs.append(cv.doc(nome, codigo, n, raiz_rel, **campos))
    pac = {"versao": 2, "gerado_em": "2026-10-20T11:00:00-03:00", "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "uf": "SP", "fontes": {}, "lacunas": [], "capa_sugerida": f"{codigo}-1972-S01-D00001"},
           "documentos": docs, "itens": docs, "retirados": [], "propostas": {}, "avisos": [], "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao").mkdir(exist_ok=True)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False, indent=1), encoding="utf-8")
    lote = f"20261020-110000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T11:00:05-03:00", "lote_atual": lote, "versao_cv2": "2026-10-13-01",
                                               "fase": "organizado_v2", "lotes_prontos": [lote], "imagens": len(casos), "folhas": len(casos), "erros_bloqueantes": 0, "motivo": ""},
                                              ensure_ascii=False), encoding="utf-8")
    print(json.dumps(cv.http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


def conferir2(base, raiz, codigo):
    D = lambda n: f"{codigo}-1972-S01-D{n:05d}"  # noqa: E731
    car = ["RESIDENCIA CONFERIR", "Arq. Sami Bussab", "1972"]
    outro = ["RESIDENCIA CONFERIR", "Arq. Fulano de Tal", "1972"]
    casos = [
        (1, "PLANTA TÉRREO", car, 0, {}),
        (2, "PLANTA SUPERIOR", car, 0, {}),
        (3, "CORTE AA", car, 0, {}),
        (4, "CORTE BB", car, 180, {"orientacao_incerta": True, "confianca_rotacao": 0.4, "sinais": ["orientação incerta — conferir"]}),
        (5, "FACHADA", car[:2] + ["1927"], 0, {"ano": "1927", "data_lida": "1927", "data_outlier": True}),
        (6, "DETALHE JANELA", outro, 0, {"autoria_divergente": True, "metadados": {"arquiteto": "Fulano de Tal"}}),
        (7, "DETALHE PORTA", outro, 0, {"autoria_divergente": True, "metadados": {"arquiteto": "Fulano de Tal"}}),
        (8, "COBERTURA", ["?????", "", ""], 0, {"publicavel": False, "bloqueios": ["carimbo ilegível — conferir o título à mão"]}),
        (9, "IMPLANTAÇÃO", car, 0, {}),
        (10, "SITUAÇÃO", car, 0, {}),
    ]
    erros = [
        {"arquivo": D(4), "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "orientação incerta — conferir na folha de contatos"},
        {"arquivo": D(5), "categoria": "metadado", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "ano lido 1927 diverge do projeto (1972)"},
        {"arquivo": D(6), "categoria": "autoria divergente", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "carimbo de Fulano de Tal, não do titular do fundo"},
        {"arquivo": D(7), "categoria": "autoria divergente", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "carimbo de Fulano de Tal, não do titular do fundo"},
    ]
    gravar(base, raiz, codigo, casos, erros)


def vinte(base, raiz, codigo):
    D = lambda n: f"{codigo}-1972-S01-D{n:05d}"  # noqa: E731
    car = ["CASA VINTE FOLHAS", "Arq. Sami Bussab", "1972"]
    casos = []
    for n in range(1, 21):
        campos = {}
        if n == 3:
            campos = {"orientacao_incerta": True, "confianca_rotacao": 0.4, "sinais": ["orientação incerta — conferir"]}
        elif n == 7:
            campos = {"ano": "1927", "data_lida": "1927", "data_outlier": True}
        elif n == 11:
            campos = {"publicavel": False, "bloqueios": ["carimbo ilegível — conferir o título à mão"]}
        elif n == 15:
            campos = {"duplicata_de": D(14), "tipo_duplicata": "quase", "publicavel": False, "bloqueios": [f"duplicata de {D(14)}"]}
        casos.append((n, f"PRANCHA {n:02d}", car, 0, campos))
    erros = [
        {"arquivo": D(3), "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "orientação incerta — conferir na folha de contatos"},
        {"arquivo": D(7), "categoria": "metadado", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "ano lido 1927 diverge do projeto (1972)"},
        {"arquivo": D(15), "categoria": "duplicata", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": f"quase de {D(14)} — só a única publica"},
    ]
    gravar(base, raiz, codigo, casos, erros)


if __name__ == "__main__":
    cmd, base, raiz, codigo, cenario = sys.argv[1:6]
    assert cmd == "pronto"
    {"conferir2": conferir2, "vinte": vinte}[cenario](base, raiz, codigo)
