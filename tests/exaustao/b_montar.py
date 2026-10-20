#!/usr/bin/env python3
"""Montador do grupo B (conferir, CAMP-080..088): um lote pelo caminho REAL (estação reserva, CAMP Vision grava a pasta final e avisa).

  b_montar.py BASE RAIZ "NOME" N [--sem-imagem 3,5] [--torta 4] [--incerta 2] [--espelhada 3] [--metadado 4] [--deitada 6]

Imprime o código do projeto. Usa as pranchas e o formato de tests/fluxo_real_cv2.py (sem editá-lo).
  --sem-imagem: a folha não tem prévia nem JPG (o CAMP Vision perdeu o arquivo)
  --torta: a folha tem borda de mesa e está inclinada (para "Recortar e alinhar")
  --incerta: de cabeça para baixo, "orientação incerta"   --deitada: deitada (90°), "orientação incerta"
  --espelhada: digitalizada pelo verso (CAMP Vision marca "espelhada")
  --metadado: ano lido 1927 (erros.json: "ano lido 1927 diverge do projeto (1972)")
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fluxo_real_cv2 import doc, http, pasta_do, prancha  # noqa: E402
from PIL import Image  # noqa: E402


def lista(a, chave):
    if chave in a:
        return {int(x) for x in a[a.index(chave) + 1].split(",") if x}
    return set()


def torta(im):
    """Folha fotografada sobre a mesa: fundo escuro em volta e 4° de inclinação."""
    fundo = Image.new("RGB", (im.width + 300, im.height + 300), (60, 52, 44))
    fundo.paste(im.rotate(4, expand=True, fillcolor=(60, 52, 44)).resize((im.width + 60, im.height + 60)), (120, 120))
    return fundo


def main():
    base, raiz, nome, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    a = sys.argv[5:]
    sem, tor, inc, esp, met, dei = (lista(a, k) for k in ("--sem-imagem", "--torta", "--incerta", "--espelhada", "--metadado", "--deitada"))
    P = http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": "F026", "titulo": nome, "ano": 1972, "cidade": "São Paulo",
                                                        "identificacao_original": f"P - {nome}", "operador": "Beatriz", "confirmar_novo": True})["codigo"]
    p = pasta_do(raiz, P, nome)
    (p / "catalogacao").mkdir(parents=True, exist_ok=True)
    (p / "info_projeto.json").write_text(json.dumps({"codigo": P, "nome": nome, "fundo_codigo": "F026", "ano": "1972", "folhas_esperadas": n, "estacao": "scanner-a3",
                                                     "operador": "Beatriz", "teste": False, "gerado_por": "CAMP Vision 2 2026-10-13-01"}, ensure_ascii=False), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "processando"}), encoding="utf-8")
    raiz_rel = str(p.relative_to(raiz))
    http(base, "/api/campvision/aviso", {"codigo": P, "pasta": raiz_rel, "status": "processando"})
    prev = Path(raiz) / "_campvision" / "preview" / P
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    for d in (prev, jpg, tif):
        d.mkdir(parents=True, exist_ok=True)
    car = [nome[:22], "Arq. Sami Bussab", "1972"]
    documentos, erros = [], []
    for i in range(1, n + 1):
        cod = f"{P}-1972-S01-D{i:05d}"
        campos = {}
        girar = 180 if i in inc else 90 if i in dei else 0
        im = prancha(f"PRANCHA {i:02d}", car if i not in met else car[:2] + ["1927"], girar=girar, espelhar=i in esp)
        if i in tor:
            im = torta(im)
        if girar:
            campos.update(orientacao_incerta=True, confianca_rotacao=0.4)
            erros.append({"arquivo": cod, "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "orientação incerta — conferir na folha de contatos"})
        if i in esp:
            campos.update(espelhada=True)
        if i in met:
            campos.update(ano="1927", data_lida="1927", data_outlier=True)
            erros.append({"arquivo": cod, "categoria": "metadado", "gravidade": "corrigir", "origem": "CAMP Vision", "detalhe": "ano lido 1927 diverge do projeto (1972)"})
        if i not in sem:
            im.save(jpg / f"{cod}.jpg", "JPEG", quality=80)
            im.save(tif / f"{cod}.tif", "TIFF")
            pv = im.copy(); pv.thumbnail((900, 900)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=75)
        d = doc(nome, P, i, raiz_rel, **campos)
        d["titulo"], d["titulo_lido"] = f"Prancha {i}", f"PRANCHA {i:02d}"
        if i in sem:
            d.update(preview="", arquivo="", arquivos=[])
        documentos.append(d)
    pac = {"versao": 2, "teste": False, "projeto_codigo": P, "projeto_nome": nome, "fundo_codigo": "F026",
           "projeto": {"codigo": P, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "capa_sugerida": f"{P}-1972-S01-D00001"},
           "documentos": documentos, "itens": documentos, "retirados": [], "propostas": {}, "avisos": []}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "pronto", "lotes_prontos": [f"20261020-{P}"], "folhas": n}), encoding="utf-8")
    r = http(base, "/api/campvision/aviso", {"codigo": P, "pasta": raiz_rel, "status": "pronto"})
    if not (r.get("importacao") or {}).get("criadas") == n:
        sys.exit(f"importação inesperada: {json.dumps(r)[:400]}")
    print(P)


def em_pe(caminho):
    """A prancha está em pé e não espelhada? O título fica no alto à ESQUERDA e o carimbo embaixo à DIREITA (ver prancha())."""
    im = Image.open(caminho).convert("L")
    w, h = im.size
    escuro = lambda x0, y0, x1, y1: 255 - sum(im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).get_flattened_data() if hasattr(Image.Image, 'get_flattened_data') else im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).getdata()) / max(1, int((x1 - x0) * w) * int((y1 - y0) * h))
    tit_esq, tit_dir = escuro(.06, .06, .46, .16), escuro(.54, .06, .94, .16)
    return {"w": w, "h": h, "em_pe": w > h and tit_esq > tit_dir + 8, "titulo_esq": round(tit_esq, 1), "titulo_dir": round(tit_dir, 1)}


def site_img(db, codigo):
    """Como a folha IRIA ao site (publicador.imagem_pronta_para_o_site): tamanho e se está em pé e sem espelho."""
    import os
    os.environ["CAMP_DB_PATH"] = db
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from app.db import connect
    from app.publicador import imagem_pronta_para_o_site
    con = connect()
    i = con.execute("SELECT i.*, p.fundo_codigo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE i.codigo=?", (codigo,)).fetchone()
    cam, lado = imagem_pronta_para_o_site(con, i)
    print(json.dumps({"caminho": cam, "lado": lado, **(em_pe(cam) if cam else {})}))


if __name__ == "__main__":
    if sys.argv[1] == "site-img":
        site_img(sys.argv[2], sys.argv[3])
    else:
        main()
