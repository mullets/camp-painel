"""Problemas com o FORMATO dos dados reais (CAMP-PROB-REAL, 22/11/2026).

Rafael, com o print da produção: "tá bem ruim de UI e UX, nem consigo alterar as coisas" — as ações rápidas e as miniaturas da lista de
Problemas só apareciam no banco sintético. Aqui as linhas nascem pelo MESMO caminho da produção: o pacote do CAMP Vision (`pacote_tainacan.json`
com `documentos` e `retirados`) e o `catalogacao/erros.json` numa pasta de lote dentro da raiz dos prontos, lidos por `importar_lote`
(que chama `registrar_problemas` e `registrar_erros_cv`). Resultado, como na produção:
- folha RETIRADA pelo CAMP Vision ("projeto divergente: o carimbo diz '…' — fora da publicação até decisão" e "sem identificação: pasta com
  várias obras…"): NÃO está na tabela de folhas; tem dois problemas abertos, o do erros.json (bloqueia, chave campvision:erros:…, código = a
  folha) e o da retirada (corrigir, chave campvision:retirado:<folha>); a imagem é a prévia do pacote em _campvision/preview ou o JPG da pasta do lote;
- folha importada com `arquivo_jpg` relativo à raiz dos prontos e `pendencias.previa` vazio (ou sem a chave, como os lotes antigos);
- uma folha retirada sem imagem em lugar nenhum (a tela mostra o aviso neutro, nunca uma imagem quebrada).

Uso como módulo: `semear(con, raiz)` (o banco já migrado). Uso pela linha de comando (teste de navegador):
    CAMP_DB_PATH=/dev/shm/x/pr.db python3 tests/semear_problemas_real.py /dev/shm/x/prontos
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FUNDO = ("F001", "Escritório Real")
# (código, título, folhas importadas, retiradas por projeto divergente, retiradas sem identificação, o que o carimbo diz)
PROJETOS = (
    ("F001-P0001", "Residência Teresa Martino", 3, 12, 0, "ESTAÇÃO DE RÁDIO F.M · RUA PIO XI"),
    ("F001-P0002", "ESTAÇÃO DE RÁDIO F.M, RUA PIO XI", 2, 0, 3, ""),
    ("F001-P0003", "RESIDÊNCIA - RAMALHO ALVES", 4, 0, 0, ""),
    ("F001-P0021", "RESIDÊNCIA SR. ORLANDO VIEIRA", 0, 1, 0, "RESIDÊNCIA RAMALHO ALVES"),
)
SEM_IMAGEM = "F001-P0001-1970-S01-D00015"          # retirada sem prévia e sem JPG na pasta do lote
ANTIGA = "F001-P0003-1970-S01-D00001"              # importada num lote antigo: pendencias sem a chave "previa"
EXISTENTE = "F001-P0003-1970-S01-D00002"           # importada, com "folha de outro projeto" relatada pela equipe (Mover vale)


def D(proj: str, n: int) -> str:
    return f"{proj}-1970-S01-D{n:05d}"


def _jpg(caminho: Path, cor=(200, 180, 150)) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        Image.new("RGB", (300, 220), cor).save(caminho, "JPEG")
    except ImportError:          # sem Pillow: um JPEG mínimo válido serve para a rota (sem miniatura)
        caminho.write_bytes(b"\xff\xd8\xff\xd9")


def semear(con, raiz) -> dict:
    """Cria o fundo, os projetos e um lote por projeto, grava pacote + erros.json na pasta do lote e importa como a produção. Idempotente."""
    from app.importador_lote import importar_lote
    raiz = Path(raiz)
    raiz.mkdir(parents=True, exist_ok=True)
    con.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (str(raiz),))
    con.execute("INSERT OR IGNORE INTO fundo (codigo, titulo) VALUES (?, ?)", FUNDO)
    lotes = {}
    for proj, titulo, n_imp, n_div, n_sem, carimbo in PROJETOS:
        num = int(proj[-4:])
        con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES (?, ?)", (FUNDO[0], num))
        con.execute("INSERT OR IGNORE INTO projeto (codigo, fundo_codigo, numero, titulo, ano) VALUES (?,?,?,?,1970)", (proj, FUNDO[0], num, titulo))
        rel_pasta = Path(f"{FUNDO[0]} - {FUNDO[1]}") / "01 - Projetos" / f"{proj} - {titulo.replace('/', '-')}"
        pasta = raiz / rel_pasta
        (pasta / "catalogacao").mkdir(parents=True, exist_ok=True)
        ja = con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=?", (proj,)).fetchone()
        lote = ja[0] if ja else con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES (?,?,?,'revisao')",
                                            (titulo, proj, str(pasta))).lastrowid
        lotes[proj] = lote
        docs, ret, erros = [], [], []
        jpg_rel = lambda cod: str(rel_pasta / "01 - Desenhos e pranchas" / "JPG" / f"{cod}.jpg")
        for n in range(1, n_imp + 1):
            cod = D(proj, n)
            _jpg(raiz / jpg_rel(cod))
            docs.append({"codigo": cod, "titulo": f"Planta {n}", "publicavel": True, "bloqueios": [], "preview": "", "arquivos": [jpg_rel(cod)]})
        seq = n_imp
        for i in range(n_div + n_sem):
            seq += 1
            cod = D(proj, seq)
            div = i < n_div
            prev = f"_campvision/preview/{proj}/{cod}.jpg"
            if cod != SEM_IMAGEM:
                _jpg(raiz / prev, (150, 170, 200))
            bloq = f"projeto divergente: o carimbo diz '{carimbo}'" if div else "sem identificação (pasta com várias obras)"
            ret.append({"codigo": cod, "titulo": f"Prancha {seq}", "publicavel": False, "projeto_divergente": div, "sem_identificacao": not div,
                        "bloqueios": [bloq], "preview": prev if cod != SEM_IMAGEM else "", "arquivos": []})
            erros.append({"arquivo": cod, "categoria": "projeto errado", "gravidade": "bloqueia", "origem": "CAMP Vision",
                          "detalhe": (f"projeto divergente: o carimbo diz '{carimbo}' — fora da publicação até decisão" if div else
                                      "sem identificação: pasta com várias obras e a folha não diz de qual é — fora da publicação até decisão")})
        (pasta / "catalogacao" / "pacote_tainacan.json").write_text(json.dumps({"versao": 2, "projeto_codigo": proj, "documentos": docs, "retirados": ret},
                                                                               ensure_ascii=False), encoding="utf-8")
        (pasta / "catalogacao" / "erros.json").write_text(json.dumps(erros, ensure_ascii=False), encoding="utf-8")
        con.commit()
        importar_lote(con, lote, "teste")
        con.commit()
    # lote antigo: a folha sem a chave "previa" nas pendências (só o JPG no QNAP)
    con.execute("UPDATE item SET pendencias=? WHERE codigo=?", (json.dumps({"bloqueios": [], "sinais": []}), ANTIGA))
    # folha que está no painel e alguém da equipe relatou ser de outro projeto (o caminho em que "Mover" vale)
    if not con.execute("SELECT 1 FROM erro WHERE codigo=? AND categoria='projeto_errado'", (EXISTENTE,)).fetchone():
        con.execute("""INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, criado_em)
                       VALUES ('corrigir','projeto_errado','operador',?,'Esta folha parece ser da Residência Teresa Martino','Equipe',datetime('now','-3 days'))""", (EXISTENTE,))
    con.execute("UPDATE erro SET criado_em=datetime('now','-24 days') WHERE origem='campvision' AND criado_em > datetime('now','-1 day')")
    con.commit()
    return {"lotes": lotes, "raiz": str(raiz)}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.db import connect
    if len(sys.argv) < 2:
        sys.exit("informe a raiz dos prontos (ex.: /dev/shm/x/prontos)")
    c = connect()
    try:
        r = semear(c, sys.argv[1])
        print(json.dumps({"ok": True, **r, "abertos": c.execute("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')").fetchone()[0]}))
    finally:
        c.close()
