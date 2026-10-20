#!/usr/bin/env python3
"""CAMP-125/126 (20/10, F026-P0009 CRASA): monta, pelo caminho real, um lote como o da CRASA — o CAMP Vision grava a pasta final e avisa o painel.

  pronto BASE RAIZ CODIGO   -> 34 folhas (JPG, TIF e prévia), pacote_tainacan.json com:
                               - projeto.uf = "SP" (o painel não tem UF: vira a sugestão "UF: SP · hoje: vazio")
                               - documentos com 8 códigos de unidade (BL-A … BL-H, 3 folhas cada) e 10 folhas sem código
                               - propostas: obras_na_pasta (8 grupos) + sem_codigo_de_unidade (23 itens; 15 com o campo vazio hoje,
                                 8 já preenchidos) = 31 propostas, e o aviso "8 obras distintas … propostas.obras_na_pasta"
                               status.json "pronto" por último e o aviso HTTP ao painel (o painel importa sozinho).
O formato de cada item de propostas não é fixo no contrato (os exemplos reais vêm vazios): aqui os itens trazem os códigos
das folhas, como o painel precisa para mostrar. Nada toca o QNAP ou o site reais.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fluxo_real_cv2 import doc, http, pasta_do, prancha  # noqa: E402

UNIDADES = [f"BL-{c}" for c in "ABCDEFGH"]


def pronto(base, raiz, codigo):
    p = pasta_do(raiz, codigo)
    nome = p.name.split(" - ", 1)[1]
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / codigo
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    for d in (prev, jpg, tif):
        d.mkdir(parents=True, exist_ok=True)
    documentos, sem = [], []
    for n in range(1, 35):
        cod = f"{codigo}-1972-S01-D{n:05d}"
        un = UNIDADES[(n - 1) // 3] if n <= 24 else ""
        im = prancha(f"PLANTA {n}", [nome[:22], f"Unidade {un or '—'}", "1978"], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=70)
        im.save(tif / f"{cod}.tif", "TIFF")
        pv = im.copy(); pv.thumbnail((400, 400)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=70)
        documentos.append(doc(nome, codigo, n, raiz_rel, codigo_unidade=un))
        if not un:
            sem.append(cod)
    obras = [{"codigo_unidade": u, "documentos": [d["codigo"] for d in documentos if d["codigo_unidade"] == u], "proposta": "separar em projeto"}
             for u in UNIDADES]
    # 23 propostas de código de unidade: 10 folhas sem código + 5 com código mas lido pela metade (hoje vazio no painel)
    # + 8 que já têm código e o CAMP Vision propõe outro (hoje preenchido: nunca troca sem um clique)
    sem_cod = [{"codigo": c, "campo": "codigo_unidade", "atual": "", "proposta": "BL-I"} for c in sem]
    sem_cod += [{"codigo": documentos[i]["codigo"], "campo": "codigo_unidade", "atual": "", "proposta": UNIDADES[i // 3]} for i in range(5)]
    sem_cod += [{"codigo": documentos[i]["codigo"], "campo": "codigo_unidade", "atual": UNIDADES[i // 3], "proposta": UNIDADES[i // 3] + "1"} for i in range(8, 16)]
    assert len(obras) + len(sem_cod) == 31
    propostas = {"obras_na_pasta": obras, "sem_codigo_de_unidade": sem_cod, "fotos_sem_obra": []}
    pac = {"versao": 2, "gerado_em": "2026-10-20T10:20:00-03:00", "teste": False, "projeto_codigo": codigo, "projeto_nome": nome, "fundo_codigo": codigo[:4],
           "fundo": {"codigo": codigo[:4], "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": codigo, "titulo": nome, "ano": "1972", "cidade": "Santo André", "uf": "SP", "cliente": "", "endereco": "", "fontes": {}, "lacunas": [],
                       "programa_sugerido": [], "natureza_sugerida": [], "capa_sugerida": f"{codigo}-1972-S01-D00001", "descricao_sugerida": ""},
           "documentos": documentos, "itens": documentos, "retirados": [], "propostas": propostas,
           "avisos": ["8 obras distintas pelo código de unidade — ver propostas.obras_na_pasta e separar em projetos"],
           "execucao": {"versao_cv2": "2026-10-13-01"}}
    (p / "catalogacao").mkdir(exist_ok=True)
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "catalogacao" / "propostas.json").write_text(json.dumps(propostas, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text("[]", encoding="utf-8")
    lote = f"20261020-102000-{codigo} - {nome}"
    (p / "status.json").write_text(json.dumps({"codigo": codigo, "status": "pronto", "status_em": "2026-10-20T10:20:05-03:00", "lote_atual": lote, "versao_cv2": "2026-10-13-01",
                                               "fase": "organizado_v2", "lotes_prontos": [lote], "imagens": 34, "folhas": 34, "a_revisar": 0, "erros_bloqueantes": 0, "motivo": ""},
                                              ensure_ascii=False), encoding="utf-8")
    print(json.dumps(http(base, "/api/campvision/aviso", {"codigo": codigo, "pasta": raiz_rel, "status": "pronto"}), ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "pronto":
        pronto(*sys.argv[2:5])
    else:
        sys.exit("uso: p4_montar.py pronto BASE RAIZ CODIGO")
