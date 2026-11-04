#!/usr/bin/env python3
"""CAMP-DUP-FORMATOS · Limpeza das folhas repetidas por formato (a mesma prancha em TIFF, DNG, JPG, JPG LIMPO, "fotos em alta"…).

PADRÃO = SIMULAR: abre o banco SÓ LEITURA, mostra por projeto o que seria feito e grava o plano (JSON). Nada muda.

No servidor do painel:
  cd ~/camp-painel && source .venv/bin/activate
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py                          # simula o F001 inteiro
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --projeto F001-P0013     # só um projeto (pode repetir --projeto)
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --plano ~/plano.json     # simula e grava o plano neste arquivo
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --aplicar --plano ~/plano.json
        aplica EXATAMENTE o plano lido (recusa se o banco mudou desde a simulação), depois de um backup do banco
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer ~/plano.desfazer.json            # mostra o que voltaria
  PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer ~/plano.desfazer.json --aplicar  # volta como estava
  Outras opções: --fundo F00x (padrão F001) · --db caminho.db · --sem-imagens · --listar N (grupos de exemplo por projeto)

O que faz ao aplicar: cada cópia vira "duplicata de" a folha que fica (tipo 'mesma_folha', conferida, com evento no histórico),
pela MESMA função da tela Duplicatas do projeto (app.duplicatas._marcar), com o ator "limpeza de formatos". NUNCA apaga folha nem
arquivo, nunca mexe em folha que está no site (lista à parte: precisa despublicar e redirecionar 301), e o que só casou pela ordem
na subpasta (sem a imagem confirmar) não entra. Também guarda o md5/dHash das folhas analisadas (para a importação reconhecer
a mesma prancha da próxima vez).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import folhas_repetidas as fr  # noqa: E402

ATOR = "limpeza de formatos"
COLS = """codigo, projeto_codigo, sequencial, serie_codigo, titulo, arquivo_origem, arquivo_jpg, pendencias, md5, phash, duplicata_de,
          tipo_duplicata, revisao, status_site, tainacan_item_id, lote_id"""
CAMPOS_DESFAZER = ("duplicata_conferida_em", "duplicata_conferida_por", "duplicata_conferida_de", "revisao", "revisado_por", "revisado_em",
                   "pendencias", "status_site")


# ----------------------------------------------------------------- banco
def caminho_db(a) -> str:
    if a.db:
        return str(Path(a.db).resolve())
    from app.config import settings
    return str(Path(settings.CAMP_DB_PATH).resolve())


def abrir(db: str, escrita: bool) -> sqlite3.Connection:
    if not Path(db).is_file():
        sys.exit(f"ERRO: o banco {db} não existe.")
    con = sqlite3.connect(db if escrita else f"file:{db}?mode=ro", uri=not escrita, timeout=30)
    con.row_factory = sqlite3.Row
    if escrita:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
    return con


def raiz_prontos(con) -> Path | None:
    for chave in ("qnap.prontos_raiz", "qnap.raiz"):
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
        if r and r[0]:
            return Path(r[0])
    try:
        from app.config import settings
        return Path(settings.CAMP_QNAP_ROOT)
    except Exception:  # noqa: BLE001
        return None


def carimbo(con, proj: str) -> str:
    """Impressão digital do que importa para a limpeza: se mudar entre simular e aplicar, o plano está velho."""
    linhas = con.execute("""SELECT codigo, duplicata_de, tipo_duplicata, revisao, status_site, tainacan_item_id, duplicata_conferida_em,
                                   duplicata_conferida_de, arquivo_origem FROM item WHERE projeto_codigo=? ORDER BY codigo""", (proj,)).fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in linhas], ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def d_curto(cod: str) -> str:
    try:
        return "D" + str(int(cod.rsplit("-D", 1)[1]))
    except (IndexError, ValueError):
        return cod


def situacao(i) -> str:
    if i["duplicata_de"]:
        return f"já é cópia de {d_curto(i['duplicata_de'])}"
    if fr.no_site(i):
        return "no site"
    return "conferida" if fr.conferida(i) else "a conferir"


# ----------------------------------------------------------------- análise (só leitura)
def analisar(con, proj: str, raiz: Path | None, usar_imagens: bool) -> dict | None:
    itens = con.execute(f"SELECT {COLS} FROM item WHERE projeto_codigo=? ORDER BY sequencial", (proj,)).fetchall()
    if not itens:
        return None
    p = con.execute("SELECT titulo FROM projeto WHERE codigo=?", (proj,)).fetchone()
    preparo: dict[str, dict] = {}
    for (pasta,) in con.execute("SELECT DISTINCT pasta_qnap FROM lista_processamento WHERE projeto_codigo=? AND pasta_qnap IS NOT NULL", (proj,)):
        preparo.update(fr.ler_preparo(pasta))
    md5, hashes, guardar_md5, guardar_phash = {}, {}, {}, {}
    lidas = falhas = 0
    for i in itens:
        c, pr = i["codigo"], preparo.get(i["codigo"], {})
        md5[c] = (i["md5"] or pr.get("md5") or "").strip().lower()
        hashes[c] = [h for h in ((i["phash"] or "").strip().lower(), pr.get("phash") or "") if h]
        if not i["md5"] and pr.get("md5"):
            guardar_md5[c] = pr["md5"]
        if usar_imagens:
            arq = fr.imagem_da_folha(raiz, i)
            if arq:
                try:
                    rot = fr.dhash_rotacoes(arq)
                    hashes[c] += rot
                    lidas += 1
                except Exception:  # noqa: BLE001 — imagem ilegível: só não casa pela imagem
                    falhas += 1
            else:
                falhas += 1
        if not i["phash"] and hashes[c]:
            guardar_phash[c] = pr.get("phash") or hashes[c][0]
    r = fr.agrupar(itens, md5, hashes)
    por_cod = {i["codigo"]: i for i in itens}
    decisoes, publicadas, pulados, ja_copias = [], [], [], []
    for g in r["grupos"]:
        orig = g[0]
        if por_cod[orig]["duplicata_de"]:
            pulados.append(g)                          # todas já são cópias de alguém: a tela Duplicatas resolve
            continue
        livres = []
        for c in g[1:]:
            if por_cod[c]["duplicata_de"]:
                ja_copias.append(c)
            elif fr.no_site(por_cod[c]):
                publicadas.append({"copia": c, "fica": orig, "situacao": por_cod[c]["status_site"], "site_id": por_cod[c]["tainacan_item_id"]})
            else:
                livres.append(c)
        if livres:
            decisoes.append({"acao": "marcar", "original": orig, "copias": livres})
    viram = sum(len(d["copias"]) for d in decisoes)
    return {"titulo": p["titulo"] if p else "", "itens": itens, "por_cod": por_cod, "r": r, "decisoes": decisoes, "publicadas": publicadas,
            "pulados": pulados, "ja_copias": ja_copias, "folhas": len(itens), "pranchas": len(itens) - sum(len(g) - 1 for g in r["grupos"]),
            "viram_copia": viram, "lidas": lidas, "falhas": falhas, "guardar_md5": guardar_md5, "guardar_phash": guardar_phash,
            "carimbo": carimbo(con, proj)}


def mostrar(proj: str, a: dict, listar: int) -> None:
    pc, r = a["por_cod"], a["r"]
    nome = f"{proj.split('-')[-1]} {a['titulo'] or ''}".strip()
    ficam = a["folhas"] - a["viram_copia"] - len(a["ja_copias"])
    print("\n" + "─" * 100)
    print(f"{nome}: {a['folhas']} folhas → {a['pranchas']} pranchas; ficam {ficam}, {a['viram_copia']} viram cópia"
          + (f"; {len(a['ja_copias'])} já eram cópia" if a["ja_copias"] else "")
          + (f" (das que ficam, {len(a['publicadas'])} repetida(s) já no site: ver abaixo)" if a["publicadas"] else ""))
    if not r["grupos"]:
        print("   nenhuma prancha repetida.")
    def fmt(c):
        rot, sp = fr.rotulo_formato(pc[c]["arquivo_origem"]), fr.subpasta(pc[c]["arquivo_origem"])
        return f"{d_curto(c)} ({rot}{'' if fr.norm(sp) == fr.norm(rot) else ' · pasta ' + sp} · {situacao(pc[c])})"
    for k, g in enumerate(r["grupos"]):
        if k >= listar:
            print(f"   … e mais {len(r['grupos']) - listar} prancha(s) repetida(s) (use --listar {len(r['grupos'])} para ver todas)")
            break
        mot = sorted({m for x in g for y in g if x < y for m in r["motivos"].get(frozenset((x, y)), ())})
        print(f"   fica {fmt(g[0])}\n        ← " + "\n        ← ".join(fmt(c) for c in g[1:]) + f"\n        por quê: {'; '.join(mot)}")
    if a["publicadas"]:
        print("   JÁ NO SITE e repetidas — NÃO mexo nelas. Para limpar: despublicar a cópia e redirecionar (301) para a que fica:")
        for x in a["publicadas"]:
            print(f"     {d_curto(x['copia'])} ({x['situacao']}, item {x['site_id'] or '?'} do site) → redirecionar para {x['fica']}")
    for g in a["pulados"]:
        print(f"   grupo só de cópias ({', '.join(d_curto(c) for c in g)}): não mexo; confira na tela Duplicatas do projeto.")
    if r["incertos"]:
        print(f"   INCERTOS (não entram no plano; confira na tela Duplicatas se quiser): {len(r['incertos'])}")
        for x, y, m in r["incertos"][:listar]:
            print(f"     {d_curto(x)} [{fr.subpasta(pc[x]['arquivo_origem'])}] ~ {d_curto(y)} [{fr.subpasta(pc[y]['arquivo_origem'])}]: {m}")


# ----------------------------------------------------------------- simular
def simular(a, db: str) -> int:
    con = abrir(db, escrita=False)
    print(f"SIMULAÇÃO (nada é gravado no banco). Banco, só leitura: {db}")
    raiz = raiz_prontos(con)
    usar = not a.sem_imagens
    acessivel = bool(raiz) and raiz.is_dir()
    if usar and not acessivel:
        print(f"AVISO: a pasta do acervo no QNAP ({raiz}) não está acessível (montada?). Sigo SEM as imagens: só md5, nome e posição;"
              " o que dependeria da imagem fica de fora (contado abaixo). Monte o QNAP e simule de novo para pegar tudo.")
        usar = False
    elif usar:
        print(f"Imagens: prévias do painel em {raiz} (só leitura).")
    else:
        print("Imagens: desligadas (--sem-imagens).")
    fundo = a.fundo.upper()
    projetos = [p.upper() for p in a.projeto] if a.projeto else [r[0] for r in con.execute(
        "SELECT DISTINCT projeto_codigo FROM item WHERE projeto_codigo LIKE ? ORDER BY 1", (fundo + "-%",))]
    plano = {"tipo": "limpeza_formatos", "versao": 1, "gerado_em": datetime.now().isoformat(timespec="seconds"), "banco": db,
             "com_imagens": usar, "aviso": "PROPOSTA. Nada foi aplicado. Para aplicar: --aplicar --plano <este arquivo>.", "projetos": {}}
    tot = {"folhas": 0, "pranchas": 0, "viram": 0, "publicadas": 0, "incertos": 0, "sem_imagem": 0}
    for proj in projetos:
        an = analisar(con, proj, raiz, usar)
        if not an:
            continue
        mostrar(proj, an, a.listar)
        r = an["r"]
        tot["folhas"] += an["folhas"]; tot["pranchas"] += an["pranchas"]; tot["viram"] += an["viram_copia"]
        tot["publicadas"] += len(an["publicadas"]); tot["incertos"] += len(r["incertos"]); tot["sem_imagem"] += r["incertos_sem_imagem"]
        plano["projetos"][proj] = {
            "titulo": an["titulo"], "carimbo": an["carimbo"], "folhas": an["folhas"], "pranchas": an["pranchas"],
            "decisoes": an["decisoes"], "publicadas_despublicar_e_301": an["publicadas"],
            "incertos": [{"a": x, "b": y, "motivo": m} for x, y, m in r["incertos"]],
            "guardar_md5": an["guardar_md5"], "guardar_phash": an["guardar_phash"]}
    con.close()
    print("\n" + "═" * 100)
    print(f"TOTAL: {tot['folhas']} folhas → {tot['pranchas']} pranchas; {tot['viram']} viram cópia ao aplicar"
          f" · {tot['publicadas']} repetida(s) já no site (não mexo) · {tot['incertos']} par(es) incerto(s) (não entram)")
    if not usar:
        print(f"SEM IMAGENS: {tot['sem_imagem']} par(es) ficaram de fora só por falta de imagem para confirmar.")
    arq = Path(a.plano) if a.plano else Path.cwd() / f"plano_limpeza_formatos_{datetime.now():%Y%m%d-%H%M%S}.json"
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nPlano gravado em {arq}. NADA foi aplicado.")
    print(f"Para aplicar (depois de conferir): PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --aplicar --plano {arq}")
    return 0


# ----------------------------------------------------------------- aplicar
def _backup(db: str) -> str:
    from app import backup as bk
    try:
        r = bk.fazer_backup(origem=db)
    except bk.BackupErro as e:
        sys.exit(f"ERRO: o backup do banco falhou ({e}). Nada foi aplicado.")
    return str(bk.PASTA / r["arquivo"])


def aplicar(a, db: str) -> int:
    from fastapi import HTTPException
    from app import duplicatas
    if not a.plano or not Path(a.plano).is_file():
        sys.exit("ERRO: --aplicar precisa de --plano <arquivo> gerado pela simulação (rode sem --aplicar primeiro).")
    plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
    if plano.get("tipo") != "limpeza_formatos":
        sys.exit("ERRO: este arquivo não é um plano da limpeza de formatos.")
    if str(Path(plano.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: o plano foi feito no banco {plano.get('banco')}, e este é {db}. Simule de novo neste banco.")
    con = abrir(db, escrita=True)
    velhos = [p for p, x in plano["projetos"].items() if carimbo(con, p) != x["carimbo"]]
    if velhos:
        con.close()
        print("RECUSADO: o banco mudou desde a simulação nestes projetos: " + ", ".join(velhos) + ".")
        print("Nada foi aplicado. Rode a simulação de novo, confira e aplique o plano novo.")
        return 3
    n = sum(len(d["copias"]) for x in plano["projetos"].values() for d in x["decisoes"])
    if not n:
        con.close()
        print("O plano não tem nada a aplicar.")
        return 0
    con.close()
    copia = _backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = abrir(db, escrita=True)
    desfazer = {"tipo": "desfazer_limpeza_formatos", "banco": db, "plano": str(Path(a.plano).resolve()), "backup": copia,
                "aplicado_em": datetime.now().isoformat(timespec="seconds"), "projetos": {}}
    marcadas = falhas = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        if [p for p, x in plano["projetos"].items() if carimbo(con, p) != x["carimbo"]]:   # mudou durante o backup
            con.rollback()
            print("RECUSADO: o banco mudou durante o backup. Nada foi aplicado; simule de novo.")
            return 3
        for proj, x in plano["projetos"].items():
            feitos, erros = [], []
            for k, d in enumerate(x["decisoes"]):
                antes = {c: dict(con.execute(f"SELECT {', '.join(CAMPOS_DESFAZER)} FROM item WHERE codigo=?", (c,)).fetchone() or {}) for c in d["copias"]}
                apont = {c: [r[0] for r in con.execute("SELECT codigo FROM item WHERE duplicata_de=?", (c,))] for c in d["copias"]}
                con.execute(f"SAVEPOINT l{k}")
                try:
                    duplicatas._marcar(con, proj, duplicatas.Decisao(**d), ATOR)
                    con.execute(f"RELEASE l{k}")
                    feitos += [{"copia": c, "original": d["original"], "antes": antes[c], "apontavam": apont[c]} for c in d["copias"]]
                except HTTPException as e:
                    con.execute(f"ROLLBACK TO l{k}"); con.execute(f"RELEASE l{k}")
                    erros.append({"original": d["original"], "copias": d["copias"], "erro": e.detail})
            for c, h in (x.get("guardar_phash") or {}).items():   # dado de máquina: só preenche o que está vazio
                con.execute("UPDATE item SET phash=? WHERE codigo=? AND projeto_codigo=? AND COALESCE(phash,'')=''", (h, c, proj))
            for c, h in (x.get("guardar_md5") or {}).items():
                con.execute("UPDATE item SET md5=? WHERE codigo=? AND projeto_codigo=? AND COALESCE(md5,'')=''", (h, c, proj))
            if feitos or erros:
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                            (proj, "duplicatas_formato_limpas", ATOR, json.dumps({"copias_marcadas": len(feitos), "recusadas": erros, "plano": desfazer["plano"],
                                                                                 "backup": copia}, ensure_ascii=False)))
            desfazer["projetos"][proj] = feitos
            marcadas += len(feitos); falhas += len(erros)
            print(f"{proj}: {len(feitos)} cópia(s) marcada(s)" + (f"; {len(erros)} decisão(ões) recusada(s): " + "; ".join(e["erro"] for e in erros) if erros else ""))
        from app.problemas import fechar_resolvidos
        fechar_resolvidos(con, ATOR)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    arq = Path(a.plano).with_suffix(".desfazer.json")
    arq.write_text(json.dumps(desfazer, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nFEITO: {marcadas} folha(s) viraram cópia" + (f"; {falhas} decisão(ões) recusada(s) (o banco mudou nelas)" if falhas else "") + ".")
    print(f"Nenhuma folha nem arquivo foi apagado. Backup: {copia}")
    print(f"Para DESFAZER: PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer {arq}            (mostra)")
    print(f"               PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer {arq} --aplicar  (volta)")
    return 0


# ----------------------------------------------------------------- desfazer
def desfazer(a, db: str) -> int:
    from fastapi import HTTPException
    from app import duplicatas
    dados = json.loads(Path(a.desfazer).read_text(encoding="utf-8"))
    if dados.get("tipo") != "desfazer_limpeza_formatos":
        sys.exit("ERRO: este arquivo não é o de desfazer da limpeza de formatos.")
    if str(Path(dados.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: a limpeza foi feita no banco {dados.get('banco')}, e este é {db}.")
    con = abrir(db, escrita=a.aplicar)
    volta, mudou = [], []
    for proj, lista in dados["projetos"].items():
        for e in lista:
            r = con.execute("SELECT duplicata_de, duplicata_conferida_por FROM item WHERE codigo=?", (e["copia"],)).fetchone()
            (volta if r and r["duplicata_de"] == e["original"] and r["duplicata_conferida_por"] == ATOR else mudou).append((proj, e))
    print(f"{'DESFAZENDO' if a.aplicar else 'SIMULAÇÃO do desfazer (nada é gravado)'}: {len(volta)} folha(s) voltam a ser folhas separadas"
          + (f"; {len(mudou)} mudaram depois da limpeza (uma pessoa mexeu) e ficam como estão: " + ", ".join(d_curto(e["copia"]) for _, e in mudou) if mudou else ""))
    if not a.aplicar:
        for proj, e in volta[:a.listar]:
            print(f"   {proj} {d_curto(e['copia'])} deixa de ser cópia de {d_curto(e['original'])}")
        con.close()
        print("Para desfazer de verdade, repita com --aplicar.")
        return 0
    con.close()
    copia = _backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = abrir(db, escrita=True)
    feitas = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        for k, (proj, e) in enumerate(volta):
            con.execute(f"SAVEPOINT u{k}")
            try:
                duplicatas._nao_e(con, proj, duplicatas.Decisao(acao="nao_e", codigo=e["copia"]), ATOR)
                antes = {c: e["antes"].get(c) for c in CAMPOS_DESFAZER if c in e["antes"]}
                if antes:      # volta exatamente como estava antes da limpeza (conferência, revisão, pendências, situação)
                    con.execute("UPDATE item SET " + ", ".join(f"{c}=?" for c in antes) + " WHERE codigo=?", (*antes.values(), e["copia"]))
                for ap in e.get("apontavam") or []:
                    con.execute("UPDATE item SET duplicata_de=? WHERE codigo=? AND duplicata_de=?", (e["copia"], ap, e["original"]))
                con.execute(f"RELEASE u{k}")
                feitas += 1
            except HTTPException as x:
                con.execute(f"ROLLBACK TO u{k}"); con.execute(f"RELEASE u{k}")
                print(f"   {d_curto(e['copia'])}: não voltou ({x.detail})")
        for proj in dados["projetos"]:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "duplicatas_formato_desfeitas", ATOR, json.dumps({"arquivo": str(Path(a.desfazer).resolve()), "backup": copia}, ensure_ascii=False)))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print(f"FEITO: {feitas} folha(s) voltaram como estavam antes da limpeza. Backup: {copia}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db")
    ap.add_argument("--fundo", default="F001")
    ap.add_argument("--projeto", action="append", help="só este(s) projeto(s)")
    ap.add_argument("--plano", help="simular: onde gravar o plano · aplicar: o plano a aplicar")
    ap.add_argument("--aplicar", action="store_true", help="aplica o --plano (ou, com --desfazer, desfaz de verdade)")
    ap.add_argument("--desfazer", help="arquivo .desfazer.json gravado ao aplicar")
    ap.add_argument("--sem-imagens", action="store_true", help="não lê as prévias (só md5, nome e posição)")
    ap.add_argument("--listar", type=int, default=8, help="quantos grupos de exemplo mostrar por projeto (padrão 8)")
    a = ap.parse_args()
    db = caminho_db(a)
    if a.desfazer:
        return desfazer(a, db)
    if a.aplicar:
        return aplicar(a, db)
    return simular(a, db)


if __name__ == "__main__":
    sys.exit(main())
