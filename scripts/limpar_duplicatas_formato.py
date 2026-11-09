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
  --despublicar     cópias JÁ PUBLICADAS (grupo certo): na simulação mostra o plano; com --aplicar, deixa a cópia privada no site
                    (a mesma rotina do painel: publicador.esconder_folha_no_site) e grava o redirecionamento 301 cópia → a que fica
                    (redir_site.registrar; o coletor de 10 min envia ao site). Só se a que fica estiver PUBLICADA (senão: "publique antes").
                    Também a "cópia já marcada ainda no site" (duplicata_de de CAMP Vision, limpeza ou pessoa, mas publicada): 301 para a
                    raiz da cadeia; a marca suspeita (mesma pasta) fica de fora.
  --corrigir-marcas marcas antigas de MÁQUINA (CAMP Vision) que ligam duas folhas da MESMA pasta: na simulação entram no plano como
                    "Não é duplicata" (ação nao_e da tela Duplicatas); com --aplicar --corrigir-marcas, são desfeitas. Marca de pessoa: nunca.

REGRA DURA (04/11/2026, depois da simulação real): só junta folhas de pastas de FORMATO/VERSÃO diferentes (TIFF × DNG × JPG × JPG LIMPO,
"em alta" × "para internet"); da mesma pasta, nunca (vira incerto) — exceto o MESMO nome de arquivo em outro formato (IMG_0012.jpg ×
IMG_0012.dng × IMG_0012.tif na mesma pasta, 09/11/2026). As marcas antigas "já é cópia de X" não juntam pranchas, só informam.

O que faz ao aplicar: cada cópia vira "duplicata de" a folha que fica (tipo 'mesma_folha', conferida, com evento no histórico),
pela MESMA função da tela Duplicatas do projeto (app.duplicatas._marcar), com o ator "limpeza de formatos". NUNCA apaga folha nem
arquivo, nunca mexe em folha que está no site (lista à parte: precisa despublicar e redirecionar 301), e o que só casou pela ordem
na subpasta (sem a imagem confirmar) não entra (--despublicar e --corrigir-marcas são as únicas exceções, sempre pelo plano simulado).
Tudo vai para o histórico e para o arquivo de desfazer (republica a cópia, tira o 301, volta a marca). Também guarda o md5/dHash das folhas analisadas (para a importação reconhecer
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
          tipo_duplicata, revisao, status_site, tainacan_item_id, lote_id, duplicata_conferida_em, duplicata_conferida_por, duplicata_conferida_de"""
CAMPOS_DESFAZER = ("duplicata_conferida_em", "duplicata_conferida_por", "duplicata_conferida_de", "revisao", "revisado_por", "revisado_em",
                   "pendencias", "status_site")
CAMPOS_MARCA = ("duplicata_de", "tipo_duplicata", *CAMPOS_DESFAZER)
MOTIVO_301 = "a mesma prancha em outro formato (limpeza de formatos)"


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


def situacao(i, grupo=None) -> str:
    if i["duplicata_de"]:
        fora = grupo is not None and i["duplicata_de"] not in grupo
        return f"já é cópia de {d_curto(i['duplicata_de'])}" + (" — marca antiga, fora deste grupo" if fora else "")
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
    decisoes, publicadas, pulados, ja_copias, despublicar, principal_antes = [], [], [], [], [], []
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
                x = {"copia": c, "fica": orig, "situacao": por_cod[c]["status_site"], "site_id": por_cod[c]["tainacan_item_id"]}
                publicadas.append(x)
                o = por_cod[orig]                  # --despublicar: só se a que fica já está PUBLICADA (o 301 tem para onde ir)
                if o["status_site"] == "no_ar" and o["tainacan_item_id"] and x["site_id"]:
                    despublicar.append({**x, "fica_site_id": o["tainacan_item_id"]})
                else:
                    principal_antes.append({**x, "fica_situacao": o["status_site"] or "nao_publicado"})
            else:
                livres.append(c)
        if livres:
            decisoes.append({"acao": "marcar", "original": orig, "copias": livres})
    viram = sum(len(d["copias"]) for d in decisoes)
    suspeitas = r["marcas_suspeitas"]
    # CAMP-DUP (09/11/2026): a folha JÁ marcada como cópia (CAMP Vision, esta limpeza ou uma pessoa) que continua publicada no site.
    # Com --despublicar sai do site com 301 para a RAIZ da cadeia (raiz_da_cadeia), só se a raiz estiver no ar; marca suspeita não entra.
    sus_cods = {x["codigo"] for x in suspeitas}
    marcadas_no_site = []
    for i in itens:
        c = i["codigo"]
        if not i["duplicata_de"] or not fr.no_site(i) or not i["tainacan_item_id"] or c in sus_cods:
            continue
        raiz = fr.raiz_da_cadeia(con, c)
        if raiz == c:
            continue
        o = con.execute("SELECT status_site, tainacan_item_id, duplicata_de FROM item WHERE codigo=?", (raiz,)).fetchone()
        x = {"copia": c, "fica": raiz, "situacao": i["status_site"], "site_id": i["tainacan_item_id"], "ja_marcada": True, "marcada_de": i["duplicata_de"]}
        marcadas_no_site.append(x)
        if o and o["status_site"] == "no_ar" and o["tainacan_item_id"] and not o["duplicata_de"]:
            despublicar.append({**x, "fica_site_id": o["tainacan_item_id"]})
        else:
            principal_antes.append({**x, "fica_situacao": (o["status_site"] if o else None) or "nao_publicado"})
    return {"titulo": p["titulo"] if p else "", "itens": itens, "por_cod": por_cod, "r": r, "decisoes": decisoes, "publicadas": publicadas,
            "pulados": pulados, "ja_copias": ja_copias, "folhas": len(itens), "pranchas": len(itens) - sum(len(g) - 1 for g in r["grupos"]),
            "viram_copia": viram, "lidas": lidas, "falhas": falhas, "guardar_md5": guardar_md5, "guardar_phash": guardar_phash,
            "carimbo": carimbo(con, proj), "despublicar": despublicar, "principal_antes": principal_antes, "suspeitas": suspeitas,
            "marcadas_no_site": marcadas_no_site}


def mostrar(proj: str, a: dict, listar: int, despublicar: bool = False, corrigir_marcas: bool = False) -> None:
    pc, r = a["por_cod"], a["r"]
    nome = f"{proj.split('-')[-1]} {a['titulo'] or ''}".strip()
    ficam = a["folhas"] - a["viram_copia"] - len(a["ja_copias"])
    print("\n" + "─" * 100)
    print(f"{nome}: {a['folhas']} folhas → {a['pranchas']} pranchas; ficam {ficam}, {a['viram_copia']} viram cópia"
          + (f"; {len(a['ja_copias'])} já eram cópia" if a["ja_copias"] else "")
          + (f" (das que ficam, {len(a['publicadas'])} repetida(s) já no site: ver abaixo)" if a["publicadas"] else "")
          + (f"; {len(a['marcadas_no_site'])} cópia(s) já marcada(s) ainda no site" if a["marcadas_no_site"] else "")
          + (f"; {len(a['suspeitas'])} MARCA(S) ANTIGA(S) SUSPEITA(S)" if a["suspeitas"] else "")
          + (f"; {len(r['incertos'])} incerto(s)" if r["incertos"] else ""))
    if not r["grupos"]:
        print("   nenhuma prancha repetida.")
    def fmt(c, g=None):
        rot, sp = fr.rotulo_formato(pc[c]["arquivo_origem"]), fr.subpasta(pc[c]["arquivo_origem"])
        return f"{d_curto(c)} ({rot}{'' if fr.norm(sp) == fr.norm(rot) else ' · pasta ' + sp} · {situacao(pc[c], g)})"
    for k, g in enumerate(r["grupos"]):
        if k >= listar:
            print(f"   … e mais {len(r['grupos']) - listar} prancha(s) repetida(s) (use --listar {len(r['grupos'])} para ver todas)")
            break
        mot = sorted({m for x in g for y in g if x < y for m in r["motivos"].get(frozenset((x, y)), ())})
        print(f"   fica {fmt(g[0], g)}\n        ← " + "\n        ← ".join(fmt(c, g) for c in g[1:]) + f"\n        por quê: {'; '.join(mot)}")
    if a["publicadas"] and not despublicar:
        print("   JÁ NO SITE e repetidas — NÃO mexo nelas. Para limpar: despublicar a cópia e redirecionar (301) para a que fica"
              " (simule com --despublicar para ver o plano):")
        for x in a["publicadas"]:
            print(f"     {d_curto(x['copia'])} ({x['situacao']}, item {x['site_id'] or '?'} do site) → redirecionar para {x['fica']}")
    if a["marcadas_no_site"] and not despublicar:
        print(f"   CÓPIA JÁ MARCADA AINDA NO SITE: {len(a['marcadas_no_site'])} — NÃO mexo (simule com --despublicar para tirar do site com 301 para a principal):")
        for x in a["marcadas_no_site"]:
            print(f"     {d_curto(x['copia'])} ({x['situacao']}, item {x['site_id']} do site; cópia de {d_curto(x['marcada_de'])}) → redirecionar para {x['fica']}")
    if despublicar and (a["publicadas"] or a["marcadas_no_site"]):
        if a["despublicar"]:
            print(f"   --despublicar (só com --aplicar): {len(a['despublicar'])} cópia(s) JÁ NO SITE saem do site (ficam privadas) e redirecionam (301) para a que fica:")
            for x in a["despublicar"]:
                print(f"     {d_curto(x['copia'])} ({x['situacao']}, item {x['site_id']} do site" + ("; cópia já marcada ainda no site" if x.get("ja_marcada") else "")
                      + f") → 301 para {x['fica']} (no ar, item {x['fica_site_id']})")
        if a["principal_antes"]:
            print(f"   PUBLIQUE A PRINCIPAL ANTES: {len(a['principal_antes'])} cópia(s) no site cuja folha que fica NÃO está no ar (não despublico):")
            for x in a["principal_antes"]:
                print(f"     {d_curto(x['copia'])} ({x['situacao']}, item {x['site_id'] or '?'} do site" + ("; cópia já marcada" if x.get("ja_marcada") else "")
                      + f"): publique {x['fica']} ({x['fica_situacao']}) antes")
    for g in a["pulados"]:
        print(f"   grupo só de cópias ({', '.join(d_curto(c) for c in g)}): não mexo; confira na tela Duplicatas do projeto.")
    if a["suspeitas"]:
        print(f"   MARCAS ANTIGAS SUSPEITAS (mesma pasta; revise na tela Duplicatas — não desfaço sozinho): {len(a['suspeitas'])}")
        for x in a["suspeitas"][:listar]:
            print(f"     {d_curto(x['codigo'])} está marcada ({x['quem']}{', ' + x['tipo'] if x['tipo'] else ''}) como cópia de {d_curto(x['de'])},"
                  f" mas as duas estão na pasta '{x['pasta']}'" + (" → com --corrigir-marcas: 'Não é duplicata' ao aplicar" if corrigir_marcas else ""))
        if len(a["suspeitas"]) > listar:
            print(f"     … e mais {len(a['suspeitas']) - listar} (use --listar {len(a['suspeitas'])})")
    if r["incertos"]:
        print(f"   INCERTOS (não entram no plano; confira na tela Duplicatas se quiser): {len(r['incertos'])}")
        for x, y, m in r["incertos"][:listar]:
            print(f"     {d_curto(x)} [{fr.subpasta(pc[x]['arquivo_origem'])}] ~ {d_curto(y)} [{fr.subpasta(pc[y]['arquivo_origem'])}]: {m}")
        if len(r["incertos"]) > listar:
            print(f"     … e mais {len(r['incertos']) - listar} (use --listar {len(r['incertos'])})")


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
    plano = {"tipo": "limpeza_formatos", "versao": 2, "gerado_em": datetime.now().isoformat(timespec="seconds"), "banco": db,
             "com_imagens": usar, "despublicar": bool(a.despublicar), "corrigir_marcas": bool(a.corrigir_marcas),
             "aviso": "PROPOSTA. Nada foi aplicado. Para aplicar: --aplicar --plano <este arquivo>.", "projetos": {}}
    tot = {"marcadas_no_site": 0, "folhas": 0, "pranchas": 0, "viram": 0, "publicadas": 0, "incertos": 0, "sem_imagem": 0, "suspeitas": 0, "despublicar": 0, "principal_antes": 0}
    for proj in projetos:
        an = analisar(con, proj, raiz, usar)
        if not an:
            continue
        mostrar(proj, an, a.listar, a.despublicar, a.corrigir_marcas)
        r = an["r"]
        tot["folhas"] += an["folhas"]; tot["pranchas"] += an["pranchas"]; tot["viram"] += an["viram_copia"]
        tot["publicadas"] += len(an["publicadas"]); tot["marcadas_no_site"] += len(an["marcadas_no_site"]); tot["incertos"] += len(r["incertos"]); tot["sem_imagem"] += r["incertos_sem_imagem"]
        tot["suspeitas"] += len(an["suspeitas"]); tot["despublicar"] += len(an["despublicar"]); tot["principal_antes"] += len(an["principal_antes"])
        plano["projetos"][proj] = {
            "titulo": an["titulo"], "carimbo": an["carimbo"], "folhas": an["folhas"], "pranchas": an["pranchas"],
            "decisoes": an["decisoes"], "publicadas_despublicar_e_301": an["publicadas"], "copias_marcadas_no_site": an["marcadas_no_site"],
            "incertos": [{"a": x, "b": y, "motivo": m} for x, y, m in r["incertos"]],
            "despublicar": an["despublicar"] if a.despublicar else [], "publique_a_principal_antes": an["principal_antes"],
            "marcas_suspeitas": an["suspeitas"],
            "revisar_marcas": [{"acao": "nao_e", "codigo": x["codigo"], "era_de": x["de"]} for x in an["suspeitas"]] if a.corrigir_marcas else [],
            "guardar_md5": an["guardar_md5"], "guardar_phash": an["guardar_phash"]}
    con.close()
    print("\n" + "═" * 100)
    print(f"TOTAL: {tot['folhas']} folhas → {tot['pranchas']} pranchas; {tot['viram']} viram cópia ao aplicar"
          + (f" · {tot['publicadas']} repetida(s) já no site (não mexo)" if not a.despublicar else
             f" · {tot['publicadas']} repetida(s) já no site: {tot['despublicar']} saem do site com 301 ao aplicar com --despublicar,"
             f" {tot['principal_antes']} esperam a principal ser publicada")
          + (f" · {tot['marcadas_no_site']} cópia(s) já marcada(s) ainda no site" if tot["marcadas_no_site"] else "")
          + f" · {tot['suspeitas']} marca(s) antiga(s) suspeita(s)" + (" (viram 'Não é duplicata' ao aplicar com --corrigir-marcas)" if a.corrigir_marcas and tot["suspeitas"] else "")
          + f" · {tot['incertos']} par(es) incerto(s) (não entram)")
    if not usar:
        print(f"SEM IMAGENS: {tot['sem_imagem']} par(es) ficaram de fora só por falta de imagem para confirmar.")
    arq = Path(a.plano) if a.plano else Path.cwd() / f"plano_limpeza_formatos_{datetime.now():%Y%m%d-%H%M%S}.json"
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nPlano gravado em {arq}. NADA foi aplicado.")
    extra = (" --despublicar" if a.despublicar else "") + (" --corrigir-marcas" if a.corrigir_marcas else "")
    print(f"Para aplicar (depois de conferir): PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --aplicar --plano {arq}{extra}")
    return 0


# ----------------------------------------------------------------- aplicar
def _backup(db: str) -> str:
    from app import backup as bk
    try:
        r = bk.fazer_backup(origem=db)
    except bk.BackupErro as e:
        sys.exit(f"ERRO: o backup do banco falhou ({e}). Nada foi aplicado.")
    return str(bk.PASTA / r["arquivo"])


def _mesmo_banco_do_painel(db: str) -> bool:
    """A rotina de despublicar do painel grava pelo banco do painel (app.db.connect): só uso se for este mesmo banco."""
    from app.config import settings
    return str(Path(settings.CAMP_DB_PATH).resolve()) == db


def _linha(con, cod: str, cols) -> dict:
    r = con.execute(f"SELECT {', '.join(cols)} FROM item WHERE codigo=?", (cod,)).fetchone()
    return dict(r) if r else {}


def _erros_duplicata(con, cod: str) -> list[dict]:
    return [dict(r) for r in con.execute("""SELECT id, situacao, resolvido_em, resolucao FROM erro WHERE codigo=? AND categoria='duplicata'
                                            AND situacao IN ('aberto','em_correcao')""", (cod,))]


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
    projs = plano["projetos"]
    n_dec = sum(len(d["copias"]) for x in projs.values() for d in x["decisoes"])
    n_marcas = sum(len(x.get("revisar_marcas") or []) for x in projs.values())
    n_desp = sum(len(x.get("despublicar") or []) for x in projs.values())
    if n_marcas and not a.corrigir_marcas:
        print(f"O plano propõe desfazer {n_marcas} marca(s) antiga(s) suspeita(s): só com --corrigir-marcas. Não mexo nelas agora.")
    if n_desp and not a.despublicar:
        print(f"O plano tem {n_desp} cópia(s) publicada(s) para despublicar com 301: só com --despublicar. Não mexo nelas agora.")
    if a.despublicar and not plano.get("despublicar"):
        print("--despublicar: este plano foi simulado SEM --despublicar; simule de novo com --despublicar para ver e gravar esse plano.")
    if a.corrigir_marcas and not plano.get("corrigir_marcas"):
        print("--corrigir-marcas: este plano foi simulado SEM --corrigir-marcas; simule de novo com --corrigir-marcas para ver e gravar esse plano.")
    n_marcas = n_marcas if a.corrigir_marcas else 0
    n_desp = n_desp if a.despublicar else 0
    if n_desp and not _mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: --despublicar usa a rotina do painel, que grava no banco do painel (CAMP_DB_PATH); este é {db}. Nada foi aplicado.")
    con = abrir(db, escrita=True)
    velhos = [p for p, x in projs.items() if carimbo(con, p) != x["carimbo"]]
    if velhos:
        con.close()
        print("RECUSADO: o banco mudou desde a simulação nestes projetos: " + ", ".join(velhos) + ".")
        print("Nada foi aplicado. Rode a simulação de novo, confira e aplique o plano novo.")
        return 3
    if not (n_dec or n_marcas or n_desp):
        con.close()
        print("O plano não tem nada a aplicar.")
        return 0
    con.close()
    copia = _backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = abrir(db, escrita=True)
    desfazer = {"tipo": "desfazer_limpeza_formatos", "banco": db, "plano": str(Path(a.plano).resolve()), "backup": copia,
                "aplicado_em": datetime.now().isoformat(timespec="seconds"), "projetos": {}, "marcas": {}, "despublicadas": {}}
    arq = Path(a.plano).with_suffix(".desfazer.json")
    gravar = lambda: arq.write_text(json.dumps(desfazer, ensure_ascii=False, indent=1), encoding="utf-8")  # noqa: E731
    marcadas = falhas = soltas = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        if [p for p, x in projs.items() if carimbo(con, p) != x["carimbo"]]:   # mudou durante o backup
            con.rollback()
            print("RECUSADO: o banco mudou durante o backup. Nada foi aplicado; simule de novo.")
            return 3
        for proj, x in projs.items():
            feitos, erros, marcas = [], [], []
            # 1º as marcas antigas suspeitas (--corrigir-marcas), depois as decisões: o _marcar reaponta quem apontava para a cópia
            for k, m in enumerate((x.get("revisar_marcas") or []) if a.corrigir_marcas else []):
                linha = con.execute(f"SELECT {COLS} FROM item WHERE codigo=? AND projeto_codigo=?", (m["codigo"], proj)).fetchone()
                if not linha or linha["duplicata_de"] != m["era_de"] or fr.marca_de_pessoa(linha):
                    erros.append({"marca": m["codigo"], "erro": "a marca mudou ou é de uma pessoa: não mexo"})
                    continue
                antes = _linha(con, m["codigo"], CAMPOS_MARCA)
                apont = [r[0] for r in con.execute("SELECT codigo FROM item WHERE duplicata_de=?", (m["codigo"],))]
                errs = _erros_duplicata(con, m["codigo"])
                con.execute(f"SAVEPOINT m{k}")
                try:
                    duplicatas._nao_e(con, proj, duplicatas.Decisao(acao="nao_e", codigo=m["codigo"]), ATOR)
                    for ap in apont:               # o nao_e passa quem apontava para esta à antiga original; aqui a marca errada é SÓ esta
                        con.execute("UPDATE item SET duplicata_de=? WHERE codigo=? AND duplicata_de=?", (m["codigo"], ap, m["era_de"]))
                    con.execute(f"RELEASE m{k}")
                    marcas.append({"codigo": m["codigo"], "era_de": m["era_de"], "antes": antes, "apontavam": apont, "erros": errs})
                except HTTPException as e:
                    con.execute(f"ROLLBACK TO m{k}"); con.execute(f"RELEASE m{k}")
                    erros.append({"marca": m["codigo"], "erro": e.detail})
            for k, d in enumerate(x["decisoes"]):
                antes = {c: _linha(con, c, CAMPOS_DESFAZER) for c in d["copias"]}
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
            if feitos or erros or marcas:
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                            (proj, "duplicatas_formato_limpas", ATOR, json.dumps({"copias_marcadas": len(feitos), "marcas_desfeitas": [m["codigo"] for m in marcas],
                                                                                 "recusadas": erros, "plano": desfazer["plano"], "backup": copia}, ensure_ascii=False)))
            desfazer["projetos"][proj] = feitos
            if marcas:
                desfazer["marcas"][proj] = marcas
            marcadas += len(feitos); falhas += len(erros); soltas += len(marcas)
            print(f"{proj}: {len(feitos)} cópia(s) marcada(s)" + (f"; {len(marcas)} marca(s) antiga(s) desfeita(s) ('Não é duplicata')" if marcas else "")
                  + (f"; {len(erros)} recusada(s): " + "; ".join(str(e["erro"]) for e in erros) if erros else ""))
        from app.problemas import fechar_resolvidos
        fechar_resolvidos(con, ATOR)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    gravar()
    tiradas, nao = 0, []
    if n_desp:
        tiradas, nao = _despublicar(projs, desfazer, gravar)
    print(f"\nFEITO: {marcadas} folha(s) viraram cópia" + (f"; {soltas} marca(s) antiga(s) desfeita(s)" if soltas else "")
          + (f"; {falhas} decisão(ões) recusada(s) (o banco mudou nelas)" if falhas else "") + ".")
    if n_desp:
        print(f"DESPUBLICAR: {tiradas} cópia(s) saíram do site (privadas) com 301 para a que fica; o coletor de 10 min envia o 301 ao site."
              + (f" {len(nao)} não: " + "; ".join(nao) if nao else ""))
    print(f"Nenhuma folha nem arquivo foi apagado. Backup: {copia}")
    print(f"Para DESFAZER: PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer {arq}            (mostra)")
    print(f"               PYTHONPATH=backend python scripts/limpar_duplicatas_formato.py --desfazer {arq} --aplicar  (volta)")
    return 0


def _despublicar(projs: dict, desfazer: dict, gravar) -> tuple[int, list[str]]:
    """Cópias JÁ PUBLICADAS de um grupo certo: a mesma rotina do painel que tira uma folha do público (publicador.esconder_folha_no_site:
    o item fica PRIVADO no site, nada é apagado; rede fora de qualquer transação) e o redirecionamento 301 cópia → a que fica
    (redir_site.registrar, a fila que o coletor envia ao site). Cada uma é conferida de novo antes e registrada no desfazer na hora."""
    from fastapi import HTTPException
    from app import publicador, redir_site
    tiradas, nao = 0, []
    for proj, x in projs.items():
        for e in x.get("despublicar") or []:
            c, fica = e["copia"], e["fica"]
            ja = bool(e.get("ja_marcada"))         # cópia JÁ marcada que continua no site: a marca e a raiz têm de ser as mesmas da simulação
            con = abrir(desfazer["banco"], escrita=True)
            try:
                ic = _linha(con, c, ("status_site", "tainacan_item_id", "duplicata_de", "projeto_codigo"))
                io = _linha(con, fica, ("status_site", "tainacan_item_id", "duplicata_de", "projeto_codigo"))
                raiz_agora = fr.raiz_da_cadeia(con, c) if ja else None
            finally:
                con.close()
            marca_mudou = (ic.get("duplicata_de") != e.get("marcada_de") or raiz_agora != fica) if ja else bool(ic.get("duplicata_de"))
            if not ic or ic["projeto_codigo"] != proj or marca_mudou or ic["status_site"] not in ("no_ar", "rascunho") or str(ic["tainacan_item_id"]) != str(e["site_id"]):
                nao.append(f"{d_curto(c)} mudou desde a simulação (não mexo)"); continue
            if not io or io["status_site"] != "no_ar" or not io["tainacan_item_id"] or io["duplicata_de"]:
                nao.append(f"{d_curto(c)}: publique {d_curto(fica)} antes"); continue
            try:
                escondeu = publicador.esconder_folha_no_site(c, ATOR, f"cópia de {fica} (mesma prancha em outro formato): sai do site com 301")
            except HTTPException as err:
                nao.append(f"{d_curto(c)}: {err.detail}"); continue
            if not escondeu:
                nao.append(f"{d_curto(c)}: nada a tirar do site"); continue
            con = abrir(desfazer["banco"], escrita=True)
            try:
                con.execute("BEGIN IMMEDIATE")
                redir_antes = con.execute("SELECT * FROM redirecionamento WHERE codigo_antigo=?", (c,)).fetchone()
                apontavam = [r[0] for r in con.execute("SELECT codigo_antigo FROM redirecionamento WHERE codigo_novo=?", (c,))]
                redir_site.registrar(con, c, fica, "item", MOTIVO_301, ATOR)
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                            (c, "duplicata_formato_despublicada", ATOR, json.dumps({"fica": fica, "site_id": e["site_id"], "estava": ic["status_site"], "ja_marcada": ja,
                                                                                   "redirecionamento": f"{c} → {fica} (301)"}, ensure_ascii=False)))
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()
            desfazer["despublicadas"].setdefault(proj, []).append({"copia": c, "fica": fica, "site_id": e["site_id"], "estava": ic["status_site"], "ja_marcada": ja,
                                                                   "redir_antes": dict(redir_antes) if redir_antes else None, "redir_apontavam": apontavam})
            gravar()
            tiradas += 1
            print(f"   {proj} {d_curto(c)}: saiu do site (privada) · 301 → {fica}")
    return tiradas, nao


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
    volta, mudou, mvolta, mmudou, dvolta, dmudou = [], [], [], [], [], []
    for proj, lista in dados["projetos"].items():
        for e in lista:
            r = con.execute("SELECT duplicata_de, duplicata_conferida_por FROM item WHERE codigo=?", (e["copia"],)).fetchone()
            (volta if r and r["duplicata_de"] == e["original"] and r["duplicata_conferida_por"] == ATOR else mudou).append((proj, e))
    for proj, lista in (dados.get("marcas") or {}).items():          # marcas antigas desfeitas com --corrigir-marcas
        for e in lista:
            r = con.execute("SELECT duplicata_de, duplicata_conferida_por, duplicata_conferida_de FROM item WHERE codigo=?", (e["codigo"],)).fetchone()
            (mvolta if r and not r["duplicata_de"] and r["duplicata_conferida_por"] == ATOR and r["duplicata_conferida_de"] == e["era_de"] else mmudou).append((proj, e))
    for proj, lista in (dados.get("despublicadas") or {}).items():   # cópias tiradas do site com --despublicar
        for e in lista:
            r = con.execute("SELECT status_site, tainacan_item_id FROM item WHERE codigo=?", (e["copia"],)).fetchone()
            (dvolta if r and r["status_site"] == "fora_do_ar" and str(r["tainacan_item_id"]) == str(e["site_id"]) else dmudou).append((proj, e))
    print(f"{'DESFAZENDO' if a.aplicar else 'SIMULAÇÃO do desfazer (nada é gravado)'}: {len(volta)} folha(s) voltam a ser folhas separadas"
          + (f"; {len(mudou)} mudaram depois da limpeza (uma pessoa mexeu) e ficam como estão: " + ", ".join(d_curto(e["copia"]) for _, e in mudou) if mudou else ""))
    if mvolta or mmudou:
        print(f"   marcas antigas: {len(mvolta)} voltam a ser cópia como eram" + (f"; {len(mmudou)} mudaram e ficam: " + ", ".join(d_curto(e["codigo"]) for _, e in mmudou) if mmudou else ""))
    if dvolta or dmudou:
        print(f"   despublicadas: {len(dvolta)} voltam ao site como estavam e perdem o 301" + (f"; {len(dmudou)} mudaram e ficam: " + ", ".join(d_curto(e["copia"]) for _, e in dmudou) if dmudou else ""))
    if not a.aplicar:
        for proj, e in volta[:a.listar]:
            print(f"   {proj} {d_curto(e['copia'])} deixa de ser cópia de {d_curto(e['original'])}")
        for proj, e in mvolta[:a.listar]:
            print(f"   {proj} {d_curto(e['codigo'])} volta a ser cópia de {d_curto(e['era_de'])} (marca antiga)")
        for proj, e in dvolta[:a.listar]:
            print(f"   {proj} {d_curto(e['copia'])} volta ao site ({e['estava']}); sai o 301 → {e['fica']}")
        con.close()
        print("Para desfazer de verdade, repita com --aplicar.")
        return 0
    con.close()
    if dvolta and not _mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: republicar usa a conexão do painel (CAMP_DB_PATH), e este banco é {db}. Nada foi desfeito.")
    copia = _backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = abrir(db, escrita=True)
    feitas = mfeitas = 0
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
        for proj, e in mvolta:            # a marca antiga volta exatamente como era (duplicata_de, tipo, conferência, pendências, situação, problemas)
            antes = {c: e["antes"].get(c) for c in CAMPOS_MARCA if c in e["antes"]}
            con.execute("UPDATE item SET " + ", ".join(f"{c}=?" for c in antes) + " WHERE codigo=?", (*antes.values(), e["codigo"]))
            for er in e.get("erros") or []:
                con.execute("UPDATE erro SET situacao=?, resolvido_em=?, resolucao=? WHERE id=?", (er["situacao"], er["resolvido_em"], er["resolucao"], er["id"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                        (e["codigo"], "duplicata_marca_restaurada", ATOR, json.dumps({"de": e["era_de"], "via": "desfazer da limpeza de formatos"}, ensure_ascii=False)))
            mfeitas += 1
        for proj in dados["projetos"]:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "duplicatas_formato_desfeitas", ATOR, json.dumps({"arquivo": str(Path(a.desfazer).resolve()), "backup": copia}, ensure_ascii=False)))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    dfeitas, dnao = _republicar(db, dvolta) if dvolta else (0, [])
    print(f"FEITO: {feitas} folha(s) voltaram como estavam antes da limpeza" + (f"; {mfeitas} marca(s) antiga(s) restaurada(s)" if mvolta else "")
          + (f"; {dfeitas} cópia(s) de volta ao site, sem o 301" if dvolta else "") + f". Backup: {copia}")
    for m in dnao:
        print(f"   {m}")
    return 0


def _republicar(db: str, dvolta: list) -> tuple[int, list[str]]:
    """Desfaz o --despublicar: o item volta ao status que tinha no site (publish/draft) pelo mesmo cliente do site do painel e o 301
    cópia → a que fica sai da fila (volta o que havia antes). Um 301 que o site JÁ recebeu fica lá: o contrato não tem rota para apagar."""
    from app import publicador
    from app.publicacao import persistir_resultado
    feitas, avisos = 0, []
    for proj, e in dvolta:
        wid, estava = int(e["site_id"]), e.get("estava") or "no_ar"
        wp_status = "publish" if estava == "no_ar" else "draft"
        try:
            publicador.WP().atualizar_status_item(publicador.COL_ACERVO, wid, wp_status)
        except Exception as x:  # noqa: BLE001
            avisos.append(f"{d_curto(e['copia'])}: o site não voltou o item {wid} ({str(x)[:160]}); o 301 continua. Tente de novo.")
            continue
        persistir_resultado([("item", e["copia"], wid)], estava, wp_status, "item", e["copia"], "site_folha_republicada", ATOR,
                            {"via": "desfazer da limpeza de formatos", "fica": e["fica"]})
        con = abrir(db, escrita=True)
        try:
            con.execute("BEGIN IMMEDIATE")
            r = con.execute("SELECT aplicado_no_site FROM redirecionamento WHERE codigo_antigo=? AND codigo_novo=? AND criado_por=?", (e["copia"], e["fica"], ATOR)).fetchone()
            if r and r[0]:
                avisos.append(f"{d_curto(e['copia'])}: o 301 → {e['fica']} já tinha ido ao site; o painel tirou o seu, mas peça para tirar no site (o contrato não tem rota de apagar).")
            con.execute("DELETE FROM redirecionamento WHERE codigo_antigo=? AND codigo_novo=? AND criado_por=?", (e["copia"], e["fica"], ATOR))
            ant = e.get("redir_antes")
            if ant:
                cols = list(ant)
                con.execute(f"INSERT OR REPLACE INTO redirecionamento ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [ant[c] for c in cols])
            for ap in e.get("redir_apontavam") or []:
                con.execute("UPDATE redirecionamento SET codigo_novo=?, aplicado_no_site=0, sem_site=0 WHERE codigo_antigo=? AND codigo_novo=?", (e["copia"], ap, e["fica"]))
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        feitas += 1
    return feitas, avisos


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
    ap.add_argument("--despublicar", action="store_true", help="cópias JÁ PUBLICADAS: saem do site (privadas) com 301 para a que fica (só com --aplicar)")
    ap.add_argument("--corrigir-marcas", action="store_true", help="marcas antigas de máquina entre folhas da MESMA pasta: 'Não é duplicata' (só com --aplicar)")
    a = ap.parse_args()
    db = caminho_db(a)
    if a.desfazer:
        return desfazer(a, db)
    if a.aplicar:
        return aplicar(a, db)
    return simular(a, db)


if __name__ == "__main__":
    sys.exit(main())
