#!/usr/bin/env python3
"""CAMP-127/129 (P6/P8 do quadro do painel, 20/10): um lote parecido com o da F026-P0009 (CRASA, Sto. André), pelo caminho real
(estação reserva o número; CAMP Vision grava a pasta final com pacote_tainacan.json, erros.json e status.json e avisa o painel).

  montar BASE RAIZ   -> imprime o código do projeto

34 folhas, ano 1978:
- 30 sem tipo lido (o cartão mostra a série genérica "Desenhos e pranchas"); D00023 "Detalhe" e D00025–D00028 "Estrutura": carimbo do
  calculista AC Vasconcelos → "autoria não confirmada" (5 folhas); D00032 e D00033 "Planta" com o MESMO nº de folha 306;
- D00022 e D00031 sem nº de folha; nºs fora de ordem pelo código (5, 6, 315…324, 7, 325, 02, 8, 03…);
- D00029 (branca) e D00030 (cinza) — a pessoa as retém depois, com D00032 (o teste faz pela rota da tela);
- avisos de "dado lido" do CAMP Vision em 20 folhas (por isso "Com problema" pegava quase tudo) e "orientação incerta" na D00021.
"""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fluxo_real_cv2 as cv  # noqa: E402
from PIL import Image  # noqa: E402

ANO = "1978"
NOME = "CRASA STO ANDRE"
FOLHAS = {1: "5", 2: "6", 3: "315", 4: "316", 5: "317", 6: "318", 7: "319", 8: "320", 9: "321", 10: "322", 11: "323", 12: "324", 13: "7",
          14: "325", 15: "02", 16: "8", 17: "03", 18: "326", 19: "327", 20: "328", 21: "329", 22: "", 23: "03", 24: "330", 25: "04", 26: "05",
          27: "06", 28: "07", 29: "331", 30: "332", 31: "", 32: "306", 33: "306", 34: "333"}
TIPOS = {23: "Detalhe", 25: "Estrutura", 26: "Estrutura", 27: "Estrutura", 28: "Estrutura", 32: "Planta", 33: "Planta"}
AUTORIA = (23, 25, 26, 27, 28)


def montar(base, raiz):
    P = cv.http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": "F026", "titulo": NOME, "ano": int(ANO), "cidade": "Santo André",
                                                         "identificacao_original": "P - CRASA", "operador": "Beatriz", "confirmar_novo": True})["codigo"]
    with contextlib.redirect_stdout(io.StringIO()):   # o aviso imprime a resposta; aqui só o código sai
        cv.processando(base, raiz, P, NOME)
    p = cv.pasta_do(raiz, P)
    rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / P
    prev.mkdir(parents=True, exist_ok=True)
    jpg = p / "01 - Desenhos e pranchas" / "JPG"
    jpg.mkdir(parents=True, exist_ok=True)
    docs, erros = [], []
    for n in range(1, 35):
        cod = f"{P}-{ANO}-S01-D{n:05d}"
        if n == 29:
            im = Image.new("RGB", (1400, 990), (252, 252, 252))
        elif n == 30:
            im = Image.new("RGB", (1400, 990), (150, 150, 150))
        else:
            car = ["AC VASCONCELOS", "Calculista", ANO] if n in AUTORIA else [NOME, "Arq. Sami Bussab", ANO]
            im = cv.prancha(f"{TIPOS.get(n, 'PRANCHA').upper()} {FOLHAS[n]}".strip(), car)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=80)
        pv = im.copy(); pv.thumbnail((700, 700)); pv.save(prev / f"{cod}.jpg", "JPEG", quality=75)
        tipo = TIPOS.get(n, "")
        d = {"codigo": cod, "projeto_codigo": P, "fundo_codigo": "F026", "serie": "S01", "modo": "prancha", "titulo": f"Prancha {n}", "titulo_lido": f"PRANCHA {n}",
             "tipo": tipo, "tipo_de_desenho": tipo.lower(), "folha": FOLHAS[n], "escala": "1:50", "ano": ANO, "ano_do_projeto": ANO,
             "metadados": {"projeto": NOME, "arquiteto": "AC Vasconcelos" if n in AUTORIA else "Sami Bussab", "folha": FOLHAS[n], "ano": ANO},
             "carimbo": {"arquiteto": "AC Vasconcelos" if n in AUTORIA else "Sami Bussab"},
             "preview": f"_campvision/preview/{P}/{cod}.jpg", "arquivo": f"_campvision/preview/{P}/{cod}.jpg",
             "arquivos": [f"{rel}/01 - Desenhos e pranchas/JPG/{cod}.jpg"], "rotacao_aplicada": 0, "confianca_rotacao": 0.95, "espelhada": False,
             "orientacao_incerta": n == 21, "orientacao_corrigida": False, "projeto_divergente": False, "publicavel": True, "bloqueios": [], "sinais": [],
             "autoria_divergente": n in AUTORIA, "credito": "Acervo Sami Bussab/CAMP"}
        docs.append(d)
        if n <= 20:
            erros.append({"arquivo": cod, "categoria": "metadado", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": f"título lido não bate com o carimbo (D{n:05d})"})
    erros.append({"arquivo": f"{P}-{ANO}-S01-D00021", "categoria": "orientação", "gravidade": "aviso", "origem": "CAMP Vision", "detalhe": "orientação incerta — conferir"})
    pac = {"versao": 2, "teste": False, "projeto_codigo": P, "projeto_nome": NOME, "fundo_codigo": "F026", "fundo": {"codigo": "F026", "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": P, "titulo": NOME, "ano": ANO, "cidade": "Santo André", "uf": "SP", "capa_sugerida": f"{P}-{ANO}-S01-D00001"},
           "documentos": docs, "itens": docs, "retirados": [], "propostas": {}, "avisos": []}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "pronto", "lote_atual": f"20261020-{P} - {NOME}", "imagens": 34, "folhas": 34}), encoding="utf-8")
    r = cv.http(base, "/api/campvision/aviso", {"codigo": P, "pasta": rel, "status": "pronto"})
    if not (r.get("importacao") or {}).get("criadas"):
        sys.exit("o aviso não importou: " + json.dumps(r, ensure_ascii=False)[:400])
    print(P)


if __name__ == "__main__":
    if sys.argv[1] == "montar":
        montar(sys.argv[2], sys.argv[3])
