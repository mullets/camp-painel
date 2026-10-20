#!/usr/bin/env python3
"""Cenário "parecido com a F026-P0009 (CRASA, Sto. André)" para os testes de P2/P9 (CAMP-123 e CAMP-130), pelo caminho real:

  p0009 BASE RAIZ [--sem-publicar]   -> imprime o código do projeto
  limpo BASE RAIZ                    -> projeto de 3 folhas sem nada pendente, publicado (para o "Projeto fechado")

1. a ESTAÇÃO reserva o número (POST /api/estacoes/projetos/reservar);
2. o CAMP VISION grava a pasta final (34 folhas JPG/TIF/prévia, pacote_tainacan.json com a sugestão de UF "SP", 31 propostas
   (8 "obras na pasta" + 23 "sem código de unidade"), o aviso "8 obras distintas…", 5 folhas com autoria divergente (D00023,
   D00025 a D00028), 2 folhas sem nº (D00022 e D00031)) e avisa o painel (POST /api/campvision/aviso), que importa sozinho;
3. as PESSOAS trabalham pela API do painel (login de verdade): a operadora corrige 22 folhas (título), confere 9 sem mudança e retém 3
   (D00029, D00030, D00032); o admin aprova o lote e publica (site FALSO do executor de testes).
Resultado igual ao da P0009: "12 conferidas · 22 corrigidas · 3 retidas" (que somavam 37 para 34 folhas), projeto publicado com 31 no site.
"""
import http.cookiejar
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

_cv = importlib.util.spec_from_file_location("fluxo_real_cv2", Path(__file__).resolve().parent.parent / "fluxo_real_cv2.py")
cv = importlib.util.module_from_spec(_cv)
_cv.loader.exec_module(cv)

NOME = "CRASA STO ANDRE"
AUTORIA = {23, 25, 26, 27, 28}
SEM_NUMERO = {22, 31}
RETIDAS = {29: "em branco", 30: "em branco", 32: "duplicata de D00033"}
CORRIGIDAS = set(range(1, 23))                       # 22


class Sessao:
    def __init__(self, base, email, senha):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.chamar("POST", "/api/auth/login", {"email": email, "senha": senha})

    def chamar(self, metodo, rota, corpo=None):
        req = urllib.request.Request(self.base + rota, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Content-Type": "application/json"}, method=metodo)
        with self.op.open(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")


def p0009(base, raiz, publicar=True):
    r = cv.http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": "F026", "titulo": NOME, "ano": 1978, "cidade": "Santo André",
                                                         "identificacao_original": "P - CRASA", "operador": "Beatriz", "confirmar_novo": True})
    P = r["codigo"]
    cv.processando(base, raiz, P, NOME)
    p = cv.pasta_do(raiz, P)
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / P
    jpg, tif = p / "01 - Desenhos e pranchas" / "JPG", p / "01 - Desenhos e pranchas" / "TIF"
    for x in (prev, jpg, tif):
        x.mkdir(parents=True, exist_ok=True)
    docs = []
    for n in range(1, 35):
        cod = f"{P}-1978-S01-D{n:05d}"
        im = cv.prancha(f"PLANTA {n}", ["CRASA STO ANDRE", "Arq. Sami Bussab", "1978"], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=70)
        im.save(tif / f"{cod}.tif", "TIFF")
        im.save(prev / f"{cod}.jpg", "JPEG", quality=70)
        d = cv.doc(NOME, P, n, raiz_rel)
        d.update({"codigo": cod, "ano": "1978", "ano_do_projeto": "1978", "preview": f"_campvision/preview/{P}/{cod}.jpg", "arquivo": f"_campvision/preview/{P}/{cod}.jpg",
                  "arquivos": [f"{raiz_rel}/01 - Desenhos e pranchas/JPG/{cod}.jpg", f"{raiz_rel}/01 - Desenhos e pranchas/TIF/{cod}.tif"],
                  "folha": "" if n in SEM_NUMERO else f"{300 + n}", "codigo_unidade": f"U{(n % 8) + 1}"})
        if n in AUTORIA:
            d.update({"autoria_divergente": True, "metadados": {**d["metadados"], "arquiteto": "AC Vasconcelos"}, "tipo": "Estrutura"})
        docs.append(d)
    obras = [f"unidade U{i}: {len([n for n in range(1, 35) if (n % 8) + 1 == i])} folhas" for i in range(1, 9)]
    sem_unid = [f"{P}-1978-S01-D{n:05d}: sem código de unidade legível" for n in range(1, 24)]
    pac = {"versao": 2, "gerado_em": "2026-10-20T10:20:00-03:00", "teste": False, "projeto_codigo": P, "projeto_nome": NOME, "fundo_codigo": "F026",
           "fundo": {"codigo": "F026", "sigla": "SBU", "nome": "Sami Bussab"},
           "projeto": {"codigo": P, "titulo": NOME, "ano": "1978", "cidade": "Santo André", "uf": "SP", "cliente": "", "endereco": "", "fontes": {}, "lacunas": [],
                       "capa_sugerida": f"{P}-1978-S01-D00001"},
           "documentos": docs, "itens": docs, "retirados": [],
           "propostas": {"obras_na_pasta": obras, "sem_codigo_de_unidade": sem_unid, "fotos_sem_obra": []},
           "avisos": ["8 obras distintas pelo código de unidade — ver propostas.obras_na_pasta e separar em projetos"]}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    erros = [{"arquivo": f"{P}-1978-S01-D{n:05d}", "categoria": "autoria divergente", "gravidade": "aviso", "origem": "CAMP Vision",
              "detalhe": "carimbo de AC Vasconcelos (estrutura), não de Sami Bussab"} for n in sorted(AUTORIA)]
    (p / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
    lote = f"20261020-102000-{P} - {NOME}"
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "pronto", "status_em": "2026-10-20T10:20:05-03:00", "lote_atual": lote, "fase": "organizado_v2",
                                               "lotes_prontos": [lote], "imagens": 34, "folhas": 34, "erros_bloqueantes": 0, "motivo": ""}), encoding="utf-8")
    cv.http(base, "/api/campvision/aviso", {"codigo": P, "pasta": raiz_rel, "status": "pronto"})
    # as pessoas
    op = Sessao(base, "operador@camp.arq.br", "senha-operador-123")
    for n in range(1, 35):
        cod = f"{P}-1978-S01-D{n:05d}"
        if n in CORRIGIDAS:
            op.chamar("PATCH", f"/api/itens/{cod}", {"titulo": f"Planta {n} (corrigida)"})
            op.chamar("POST", f"/api/itens/{cod}/revisao", {"estado": "corrigida"})
        elif n in RETIDAS:
            op.chamar("POST", f"/api/itens/{cod}/retencao", {"retida": True, "motivo": RETIDAS[n]})
        else:
            op.chamar("POST", f"/api/itens/{cod}/revisao", {"estado": "conferida"})
    if publicar:
        ad = Sessao(base, "rafael@camp.arq.br", "senha-bem-longa-123")
        rv = ad.chamar("GET", f"/api/projetos/{P}/revisao")
        ad.chamar("POST", f"/api/lotes/{rv['lotes'][0]['id']}/aprovar")
        ad.chamar("POST", f"/api/projetos/{P}/publicar-tudo")
    print(P)


def limpo(base, raiz):
    """Um projeto sem nada pendente: 3 folhas lidas sem aviso, conferidas, lote aprovado e publicado (para o "Projeto fechado")."""
    nome = "CASA LIMPA"
    r = cv.http(base, "/api/estacoes/projetos/reservar", {"fundo_codigo": "F026", "titulo": nome, "ano": 1972, "cidade": "São Paulo", "operador": "Beatriz", "confirmar_novo": True})
    P = r["codigo"]
    cv.processando(base, raiz, P, nome)
    p = cv.pasta_do(raiz, P)
    raiz_rel = str(p.relative_to(raiz))
    prev = Path(raiz) / "_campvision" / "preview" / P
    jpg = p / "01 - Desenhos e pranchas" / "JPG"
    for x in (prev, jpg):
        x.mkdir(parents=True, exist_ok=True)
    docs = []
    for n in (1, 2, 3):
        cod = f"{P}-1972-S01-D{n:05d}"
        im = cv.prancha(f"PLANTA {n}", [nome, "Arq. Sami Bussab", "1972"], w=700, h=495)
        im.save(jpg / f"{cod}.jpg", "JPEG", quality=70); im.save(prev / f"{cod}.jpg", "JPEG", quality=70)
        d = cv.doc(nome, P, n, raiz_rel)
        d["arquivos"] = [f"{raiz_rel}/01 - Desenhos e pranchas/JPG/{cod}.jpg"]
        docs.append(d)
    pac = {"versao": 2, "teste": False, "projeto_codigo": P, "projeto_nome": nome, "fundo_codigo": "F026",
           "projeto": {"codigo": P, "titulo": nome, "ano": "1972", "cidade": "São Paulo", "uf": "", "cliente": "", "endereco": ""},
           "documentos": docs, "itens": docs, "retirados": [], "propostas": {}, "avisos": []}
    (p / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
    (p / "catalogacao" / "erros.json").write_text("[]", encoding="utf-8")
    (p / "status.json").write_text(json.dumps({"codigo": P, "status": "pronto", "fase": "organizado_v2", "imagens": 3, "folhas": 3, "erros_bloqueantes": 0, "motivo": ""}), encoding="utf-8")
    cv.http(base, "/api/campvision/aviso", {"codigo": P, "pasta": raiz_rel, "status": "pronto"})
    op = Sessao(base, "operador@camp.arq.br", "senha-operador-123")
    for n in (1, 2, 3):
        op.chamar("POST", f"/api/itens/{P}-1972-S01-D{n:05d}/revisao", {"estado": "conferida"})
    ad = Sessao(base, "rafael@camp.arq.br", "senha-bem-longa-123")
    rv = ad.chamar("GET", f"/api/projetos/{P}/revisao")
    ad.chamar("POST", f"/api/lotes/{rv['lotes'][0]['id']}/aprovar")
    ad.chamar("POST", f"/api/projetos/{P}/publicar-tudo")
    print(P)


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "p0009":
        p0009(a[0], a[1], "--sem-publicar" not in a)
    elif cmd == "limpo":
        limpo(a[0], a[1])
    else:
        sys.exit(f"comando desconhecido: {cmd}")
