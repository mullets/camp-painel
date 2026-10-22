#!/usr/bin/env python3
"""Faz o papel da ESTAÇÃO e do CAMP Vision 2 num teste de fluxo real (tests/fluxo_real.js): só pelos caminhos de verdade.

  reservar  BASE FUNDO "TITULO" ANO          -> POST /api/estacoes/projetos/reservar (como a estação); imprime o código
  processando BASE RAIZ CODIGO "NOME"        -> cria a pasta final, info_projeto.json e status.json "processando"; POST /api/campvision/aviso
  pronto    BASE RAIZ CODIGO [--sem-aviso]   -> grava imagens (JPG, TIF e prévia), pacote_tainacan.json, erros.json e, POR ÚLTIMO,
                                               status.json "pronto"; avisa o painel (ou não, com --sem-aviso: o aviso que se perdeu)

O lote tem 8 folhas, cada uma com um caso que a operadora encontra de verdade:
  D00001 normal · D00002 de cabeça para baixo ("orientação incerta") · D00003 espelhada · D00004 ano lido errado (metadado)
  D00005 duplicata da D00001 · D00006 normal · D00007 e D00008 o CAMP Vision achou que são de OUTRA obra (vão para `retirados`)
Nada aqui toca o QNAP ou o site reais: RAIZ é uma pasta temporária e BASE é o painel de teste.
"""
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FUNDO_NOME = {"F026": "F026 - SBU Sami Bussab"}


def http(base, rota, corpo):
    req = urllib.request.Request(base + rota, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def pasta_do(raiz, codigo, nome=None):
    base = Path(raiz) / FUNDO_NOME.get(codigo[:4], codigo[:4]) / "01 - Projetos"
    if nome is None:
        achadas = sorted(base.glob(codigo + " - *"))
        return achadas[0]
    return base / f"{codigo} - {nome}"


def fonte(tam):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def prancha(texto, carimbo, girar=0, espelhar=False, w=1400, h=990):
    """Uma prancha que dá para ler: margem, desenho, título grande no alto e carimbo no canto inferior direito (mostra se está em pé)."""
    im = Image.new("RGB", (w, h), (244, 239, 226))
    d = ImageDraw.Draw(im)
    d.rectangle([30, 30, w - 30, h - 30], outline=(40, 40, 40), width=6)
    d.rectangle([180, 240, 760, 700], outline=(60, 60, 60), width=5)
    d.line([180, 470, 760, 470], fill=(60, 60, 60), width=3)
    d.line([470, 240, 470, 700], fill=(60, 60, 60), width=3)
    d.text((80, 70), texto, fill=(20, 20, 20), font=fonte(70))
    d.rectangle([w - 520, h - 230, w - 50, h - 50], outline=(20, 20, 20), width=4)
    for i, linha in enumerate(carimbo):
        d.text((w - 500, h - 215 + i * 44), linha, fill=(20, 20, 20), font=fonte(30))
    if espelhar:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if girar:
        im = im.rotate(girar, expand=True)
    return im


def reservar(base, fundo, titulo, ano):
    r = http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": fundo, "titulo": titulo, "ano": int(ano), "cidade": "São Paulo",
                                                         "identificacao_original": f"P - {titulo}", "operador": "Beatriz", "confirmar_novo": True})
    print(r["codigo"])


def processando(base, raiz, codigo, nome):
    p = pasta_do(raiz, codigo, nome)
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "info_projeto.json").write_text(json.dumps({"codigo": codigo, "nome": nome, "fundo_codigo": codigo[:4], "ano": "1972", "folhas_esperadas": 8,
                                                     "estacao": "scanner-a3", "tipo_estacao": "windows", "operador": "Beatriz", "operador_email": "operador@camp.arq.br",
                                                     "teste": False, "atualizado_em": "2026-10-20T10:00:00-03:00", "gerado_por": "CAMP Vision 2 2026-10-13-01"},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "processando", "status_em": "2026-10-20T10:00:05-03:00", "fase": "lendo"}), encoding="utf-8")
    print(json.dumps(http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": str(p.relative_to(raiz)), "status": "processando"}), ensure_ascii=False))


def doc(codigo, P, n, raiz_rel, **extra):
    cod = f"{P}-1972-S01-D{n:05d}"
    d = {"codigo": cod, "projeto_codigo": P, "fundo_codigo": P[:4], "serie": "S01", "modo": "prancha", "titulo": f"Planta {n}", "titulo_lido": f"PLANTA {n}",
         "tipo": "Planta", "tipo_de_desenho": "planta", "folha": f"{n:02d}", "escala": "1:50", "codigo_unidade": "", "revisao": "", "data_lida": "", "data_iso": "",
         "data_sugerida": "", "data_outlier": False, "ano": "1972", "ano_do_projeto": "1972",
         "metadados": {"projeto": codigo, "arquiteto": "Sami Bussab", "folha": f"{n:02d}", "ano": "1972"},
         "rastreio": {"projeto": "leitura", "arquiteto": "leitura", "folha": "leitura", "ano": "leitura"}, "alternativas": {}, "onde": {},
         "credito": "Acervo Sami Bussab/CAMP - Casa da Arquitetura Moderna Paulista",
         "preview": f"_campvision/preview/{P}/{cod}.jpg", "arquivo": f"_campvision/preview/{P}/{cod}.jpg",
         "arquivos": [f"{raiz_rel}/01 - Desenhos e pranchas/JPG/{cod}.jpg", f"{raiz_rel}/01 - Desenhos e pranchas/TIF/{cod}.tif"],
         "arquivo_origem": [{"arquivo_origem": f"100 - Scanners/F026/RESIDENCIA FLUXO/scan {n:03d}.tif", "nome_original": f"scan {n:03d}.tif", "origem_formato": "tif"}],
         "origem_formato": "tif", "rotacao_aplicada": 0, "confianca_rotacao": 0.97, "espelhada": False, "orientacao_incerta": False, "orientacao_corrigida": False,
         "projeto_divergente": False, "publicavel": True, "bloqueios": [], "sinais": []}
    d.update(extra)
    return d


def pronto(base, raiz, codigo, sem_aviso=False):
    p = pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    prev.mkdir(parents=True, exist_ok=True)
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    jpg.mkdir(parents=True, exist_ok=True); tif.mkdir(parents=True, exist_ok=True)
    car = [nome[:22], "Arq. Sami Bussab", "1972"]
    # (n, imagem, campos do pacote)
    casos = [
        (1, prancha("PLANTA TÉRREO", car), {}),
        (2, prancha("PLANTA SUPERIOR", car, girar=180), {"orientacao_incerta": True, "confianca_rotacao": 0.41, "sinais": ["orientação incerta — conferir"]}),
        (3, prancha("CORTE AA", car, espelhar=True), {"espelhada": True, "sinais": ["espelhada? — conferir"]}),
        (4, prancha("FACHADA", car[:2] + ["1927"]), {"ano": "1927", "data_lida": "1927", "data_outlier": True}),
        (5, prancha("PLANTA TÉRREO", car), {"duplicata_de": f"{codigo}-1972-S01-D00001", "tipo_duplicata": "quase", "publicavel": False,
                                             "bloqueios": [f"duplicata de {codigo}-1972-S01-D00001"]}),
        (6, prancha("COBERTURA", car), {}),
        (7, prancha("DETALHE ESCADA", [nome[:22], "Arq. Sami Bussab", "1972"]), None),
        (8, prancha("RESID. FULANO", ["RESIDÊNCIA FULANO DE TAL", "Arq. Outro", "1981"]), None),
    ]
    documentos, retirados = [], []
    for n, im, campos in casos:
        cod = f"{codigo}-1972-S01-D{n:05d}"
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=85)
        im.save(tif / f"{cod}.tif", "TIFF")
        pv = im.copy(); pv.thumbnail((900, 900)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=80)
        if campos is None:
            carimbo = "RESIDÊNCIA FULANO DE TAL" if n == 8 else nome
            retirados.append({**doc(nome, codigo, n, raiz_rel), "publicavel": False, "projeto_divergente": True,
                              "motivo": "projeto divergente", "bloqueios": [f"projeto divergente: o carimbo diz '{carimbo}' (grupo pequeno sem projeto na base)"]})
        else:
            documentos.append(doc(nome, codigo, n, raiz_rel, **campos))
    pac = {"versao": 2, "gerado_em": "2026-10-20T10:20:00-03:00", "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "uf": "SP", "cliente": "", "endereco": "", "fontes": {}, "lacunas": [],
                       "programa_sugerido": [], "natureza_sugerida": [], "capa_sugerida": f"{codigo}-1972-S01-D00001", "descricao_sugerida": ""},
           "documentos": documentos, "itens": documentos, "retirados": retirados, "propostas": {},
           "avisos": [f"D00005 é quase de D00001 — publicar D00001"], "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    erros = [
        {"arquivo": f"{codigo}-1972-S01-D00002", "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "orientação incerta — conferir na folha de contatos"},
        {"arquivo": f"{codigo}-1972-S01-D00003", "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "espelhada? — conferir na folha de contatos"},
        {"arquivo": f"{codigo}-1972-S01-D00004", "categoria": "metadado", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "ano lido 1927 diverge do projeto (1972)"},
        {"arquivo": f"{codigo}-1972-S01-D00005", "categoria": "duplicata", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": f"quase de {codigo}-1972-S01-D00001 — só a única publica"},
        # como no F009-P0092 (print da operadora, 20/10): a folha de outra obra vem também como problema que impede publicar
        {"arquivo": f"{codigo}-1972-S01-D00007", "categoria": "projeto", "gravidade": "bloqueia", "origem": "CAMP Vision",
         "detalhe": f"D00007 com identificação para outra pasta ({nome}) — fora da publicação até resolver"},
        {"arquivo": f"{codigo}-1972-S01-D00008", "categoria": "projeto", "gravidade": "bloqueia", "origem": "CAMP Vision",
         "detalhe": "D00008 com identificação para outra pasta (RESIDÊNCIA FULANO DE TAL) — fora da publicação até resolver"},
    ]
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False, indent=1), encoding="utf-8")
    lote = f"20261020-102000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T10:20:05-03:00", "lote_atual": lote, "versao_cv2": "2026-10-13-01",
                                               "fase": "organizado_v2", "lotes_prontos": [lote], "imagens": 8, "folhas": 6, "a_revisar": 3, "erros_bloqueantes": 0, "motivo": ""},
                                              ensure_ascii=False), encoding="utf-8")
    if sem_aviso:
        print(json.dumps({"aviso": "não enviado (simula aviso perdido)"}))
    else:
        print(json.dumps(http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "reservar":
        reservar(*a)
    elif cmd == "processando":
        processando(*a)
    elif cmd == "pronto":
        pronto(a[0], a[1], a[2], "--sem-aviso" in a)
    else:
        sys.exit(f"comando desconhecido: {cmd}")
