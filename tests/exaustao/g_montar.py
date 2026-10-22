#!/usr/bin/env python3
"""Lotes do grupo G (CAMP-118 e CAMP-119) no formato REAL do CAMP Vision, gravados na pasta final falsa e avisados por HTTP.

  grande  BASE RAIZ CODIGO [N]   -> N folhas (padrão 500) espalhadas em S01–S08 e S99, imagens pequenas de verdade
  xss     BASE RAIZ CODIGO       -> título lido, carimbo, tipo, avisos e problema com <script>, aspas, emoji e 300 caracteres

O projeto vem da estação (fluxo_real_cv2.py reservar/processando); aqui só o "pronto". Usa as funções de fluxo_real_cv2.py sem mudá-lo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fluxo_real_cv2 import http, pasta_do, prancha  # noqa: E402

from PIL import Image  # noqa: E402

SERIES = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S99"]
PASTA_SERIE = {"S01": "01 - Desenhos e pranchas", "S02": "02 - Fotografias", "S03": "03 - Documentos", "S04": "04 - Croquis",
               "S05": "05 - Memoriais", "S06": "06 - Publicacoes", "S07": "07 - Maquetes", "S08": "08 - Outros", "S99": "99 - Sem serie"}
XSS = '<script>window.__xss=1</script><img src=x onerror="window.__xss=2">"\'&'
LONGO = ("Prancha de detalhamento executivo da escada helicoidal em concreto aparente com guarda-corpo metálico "
         "e corrimão em madeira de lei, conforme memorial descritivo revisado pelo escritório parceiro em diversas versões ") * 3


def _doc(P, cod, serie, n, raiz_rel, **extra):
    d = {"codigo": cod, "projeto_codigo": P, "fundo_codigo": P[:4], "serie": serie, "modo": "prancha", "titulo": f"Planta {n}", "titulo_lido": f"PLANTA {n}",
         "tipo": "Planta", "tipo_de_desenho": "planta", "folha": f"{n:03d}", "escala": "1:50", "ano": "1972", "ano_do_projeto": "1972",
         "metadados": {"folha": f"{n:03d}", "ano": "1972"}, "rastreio": {}, "alternativas": {}, "onde": {},
         "preview": f"_campvision/preview/{P}/{cod}.jpg", "arquivo": f"_campvision/preview/{P}/{cod}.jpg",
         "arquivos": [f"{raiz_rel}/{PASTA_SERIE[serie]}/JPG/{cod}.jpg"], "arquivo_origem": [], "origem_formato": "jpg",
         "rotacao_aplicada": 0, "confianca_rotacao": 0.97, "espelhada": False, "orientacao_incerta": False, "orientacao_corrigida": False,
         "projeto_divergente": False, "publicavel": True, "bloqueios": [], "sinais": []}
    d.update(extra)
    return d


def _gravar(base, raiz, P, documentos, erros, avisos=()):
    p = pasta_do(raiz, P)
    nome = p.name.split(" - ", 1)[1]
    pac = {"versao": 2, "teste": False, "projeto_codigo": P, "projeto_nome": nome, "fundo_codigo": P[:4],
           "projeto": {"codigo": P, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "capa_sugerida": documentos[0]["codigo"]},
           "documentos": documentos, "itens": documentos, "retirados": [], "propostas": {}, "avisos": list(avisos)}
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "pronto", "lote_atual": f"20261020-{P}", "fase": "organizado_v2",
                                               "imagens": len(documentos), "folhas": len(documentos)}), encoding="utf-8")
    print(json.dumps(http(base, "/api/campvision/aviso", {"codigo": P, "pasta": str(p.relative_to(raiz)), "status": "pronto"}), ensure_ascii=False)[:600])


def grande(base, raiz, P, n=500):
    n = int(n)
    p = pasta_do(raiz, P)
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / P
    prev.mkdir(parents=True, exist_ok=True)
    base_img = prancha("PLANTA", ["OBRA GRANDE", "Arq.", "1972"], w=420, h=300)
    docs = []
    for i in range(1, n + 1):
        serie = SERIES[(i - 1) % len(SERIES)]
        cod = f"{P}-1972-{serie}-D{i:05d}"
        pasta_jpg = p / PASTA_SERIE[serie] / "JPG"
        pasta_jpg.mkdir(parents=True, exist_ok=True)
        base_img.save(pasta_jpg / f"{cod}.jpg", "JPEG", quality=60)
        base_img.save(prev / f"{cod}.jpg", "JPEG", quality=60)
        docs.append(_doc(P, cod, serie, i, raiz_rel))
    _gravar(base, raiz, P, docs, [])


def xss(base, raiz, P):
    p = pasta_do(raiz, P)
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / P
    prev.mkdir(parents=True, exist_ok=True)
    jpg = p / PASTA_SERIE["S01"] / "JPG"
    jpg.mkdir(parents=True, exist_ok=True)
    docs = []
    for i in (1, 2, 3):
        cod = f"{P}-1972-S01-D{i:05d}"
        im = prancha(f"FOLHA {i}", ["CARIMBO", "Arq.", "1972"], w=700, h=500)
        im.save(jpg / f"{cod}.jpg", "JPEG"); im.save(prev / f"{cod}.jpg", "JPEG")
    docs.append(_doc(P, f"{P}-1972-S01-D00001", "S01", 1, raiz_rel, titulo=XSS + " 🏛️ Ação ç ã", titulo_lido=XSS + LONGO, tipo=XSS,
                     metadados={"projeto": XSS, "arquiteto": XSS, "folha": "01", "ano": "1972"}, sinais=[XSS + " sinal"], orientacao_incerta=True))
    docs.append(_doc(P, f"{P}-1972-S01-D00002", "S01", 2, raiz_rel, titulo=LONGO, titulo_lido=LONGO, escala=XSS, folha=XSS[:20]))
    docs.append(_doc(P, f"{P}-1972-S01-D00003", "S01", 3, raiz_rel, titulo="Corte “AA” — 'aspas' & <b>negrito</b> 😀", bloqueios=[XSS + " bloqueio"], publicavel=False))
    erros = [{"arquivo": f"{P}-1972-S01-D00001", "categoria": "metadado", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": XSS + " " + LONGO},
             {"arquivo": f"{P}-1972-S01-D00002", "categoria": "projeto", "gravidade": "bloqueia", "origem": "CAMP Vision",
              "detalhe": f"D00002 com identificação para outra pasta ({XSS}) — fora da publicação até resolver"},
             {"arquivo": "", "categoria": "metadado", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": XSS + " sem pasta de material"}]
    _gravar(base, raiz, P, docs, erros, avisos=[XSS + " aviso do lote"])


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    {"grande": grande, "xss": xss}[cmd](*a)
