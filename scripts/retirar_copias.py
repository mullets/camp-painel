#!/usr/bin/env python3
"""CAMP-DUP (10/11/2026) · Retirar do sistema as CÓPIAS de uma prancha, deixando só a JPG original.

Pedido do Rafael (F001 Arnaldo Martino): "Não quero que fique cópias! Deixe só as JPGs originais, o que não era ignore e tire do sistema AGORA."
A mesma prancha entrou várias vezes, uma por formato (subpastas TIFF / DNG / JPG / JPG LIMPO; "fotos em alta" / "fotos para internet").

PADRÃO = SIMULAR: abre o banco SÓ LEITURA, mostra por projeto o que seria feito e grava o plano (JSON). Nada muda.

No servidor do painel:
  cd ~/camp-painel && source .venv/bin/activate
  PYTHONPATH=backend python scripts/retirar_copias.py --fundo F001 --plano ~/plano_retirar_f001.json > ~/sim_retirar.txt   # simula
  PYTHONPATH=backend python scripts/retirar_copias.py --aplicar --plano ~/plano_retirar_f001.json
        aplica EXATAMENTE o plano lido (RECUSADO se o banco mudou desde a simulação), depois de um backup do banco
  PYTHONPATH=backend python scripts/retirar_copias.py --desfazer ~/plano_retirar_f001.desfazer.json            # mostra o que voltaria
  PYTHONPATH=backend python scripts/retirar_copias.py --desfazer ~/plano_retirar_f001.desfazer.json --aplicar  # volta como estava
  Outras opções: --projeto F001-P0013 (pode repetir) · --db caminho.db · --sem-imagens · --listar N

Os grupos ("a mesma prancha") são os da limpeza de formatos (app.folhas_repetidas.agrupar, a mesma regra dura: só junta pastas de FORMATO
diferentes) somados às marcas "cópia de" que já existem (a cadeia até a principal), menos as marcas suspeitas (duas folhas da mesma pasta).
Os INCERTOS e as marcas suspeitas só são listados: nada acontece com eles.

Em cada grupo:
  1. FICA a JPG original: pasta/formato "JPG" (não o JPG LIMPO); "fotos em alta" antes de "fotos para internet". Sem JPG simples, fica o
     JPG LIMPO; sem JPG nenhum, fica a principal de hoje (listado como "sem JPG").
  2. A que fica vira a principal (sem "cópia de"). Se ela herda da principal antiga título/tipo quando os dela estão vazios.
     Se outra folha do grupo está NO SITE e a JPG está no ar: a do site sai do público (fica PRIVADA, nada é apagado; a mesma rotina do
     painel: publicador.esconder_folha_no_site) com redirecionamento 301 para a JPG (redir_site.registrar) e é retirada.
     Se a JPG ainda NÃO está no ar: "precisa publicar a JPG antes" — a do site fica (como cópia da JPG, ainda publicada) até alguém
     publicar a JPG pelo painel; rode a simulação de novo depois e ela sai com 301.
  3. As outras saem do painel: a linha inteira vai para a tabela item_retirado (lápide, com o que dependia dela: revisão, problemas,
     localização…), e a folha some de listas, contagens, grade, filas, problemas e publicação. O número D NUNCA é reusado e a
     importação/releitura do CAMP Vision não a traz de volta (app.retirados). Os arquivos no QNAP NÃO são tocados.
  O desfazer devolve as linhas, reapontamentos e marcas como estavam, republica no site o que saiu e tira o 301.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import folhas_repetidas as fr  # noqa: E402
import limpar_duplicatas_formato as ldf  # noqa: E402

ATOR = "retirar cópias"
MOTIVO_301 = "cópia da mesma prancha em outro formato: fica a JPG original (retirar cópias)"
DEPENDENTES = (("item_agente", "item_codigo", ""), ("item_localizacao", "item_codigo", ""), ("revisao_campo", "item_codigo", ""),
               ("fila_correcao_site", "item_codigo", ""), ("erro", "codigo", ""), ("divergencia_site", "codigo", " AND entidade='item'"))
PRENDEM = (("emprestimo_item", "item_codigo", "empréstimo"), ("pedido_releitura", "item_codigo", "pedido de releitura"))
HERDA = ("titulo", "tipo_documento", "tipos_documento")
d_curto = ldf.d_curto


# ----------------------------------------------------------------- regra: qual fica
def rank_jpg(origem) -> tuple | None:
    """JPG simples (0) antes de JPG LIMPO (1); "em alta" antes de "sem indicação" antes de "para internet". None: não é JPG."""
    f, r = fr.rank_formato(origem)
    return (0, r) if f == 3 else ((1, r) if f == 2 else None)


def escolher(g: list[str], pc: dict) -> tuple[str, str]:
    """(a que fica, por quê): a JPG original; sem JPG, a principal de hoje (g já vem ordenado pela chave da principal)."""
    jpgs = [c for c in g if rank_jpg(pc[c]["arquivo_origem"])]
    if not jpgs:
        return g[0], "sem_jpg"
    k = min(jpgs, key=lambda c: (rank_jpg(pc[c]["arquivo_origem"]), pc[c]["sequencial"] or 0))
    return k, "jpg" if rank_jpg(pc[k]["arquivo_origem"])[0] == 0 else "jpg_limpo"


def _tem_tabela(con, t: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def carimbo(con, proj: str) -> str:
    """Impressão digital do projeto (todas as colunas das folhas menos horários, e as lápides): mudou entre simular e aplicar = plano velho."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(item)") if not r[1].endswith("_em")]
    linhas = [list(r) for r in con.execute(f"SELECT {', '.join(cols)} FROM item WHERE projeto_codigo=? ORDER BY codigo", (proj,))]
    if _tem_tabela(con, "item_retirado"):
        linhas += [["retirado", r[0]] for r in con.execute("SELECT codigo FROM item_retirado WHERE projeto_codigo=? ORDER BY codigo", (proj,))]
    return hashlib.sha256(json.dumps(linhas, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


def grupos_com_cadeias(an: dict) -> tuple[list[list[str]], list[dict]]:
    """Os grupos de agrupar() + as marcas 'cópia de' que já existem no projeto (não suspeitas), respeitando a regra dura (no máximo uma
    folha por pasta/formato no grupo). Devolve (grupos ordenados pela chave da principal, marcas que não deu para juntar)."""
    pc = an["por_cod"]
    uf, membros = fr._UF(), {}
    for g in an["r"]["grupos"]:
        for c in g:
            uf.achar(c)
        for c in g[1:]:
            uf.unir(c, g[0])
    for c in pc:
        membros.setdefault(uf.achar(c), []).append(c)
    sus = {x["codigo"] for x in an["suspeitas"]}
    m5 = lambda c: (pc[c]["md5"] or "").strip().lower()  # noqa: E731
    nao = []
    for c, i in pc.items():
        de = i["duplicata_de"]
        if not de or de not in pc or c in sus:
            continue
        ra, rb = uf.achar(c), uf.achar(de)
        if ra == rb:
            continue
        barra = next((q for x in membros[ra] for y in membros[rb]
                      for q in [fr.conflito(pc[x]["arquivo_origem"], pc[y]["arquivo_origem"], bool(m5(x)) and m5(x) == m5(y))] if q), None)
        if barra:
            nao.append({"codigo": c, "de": de, "porque": barra})
            continue
        uf.unir(c, de)
        membros[rb] = membros[rb] + membros.pop(ra)
    grupos = [sorted(m, key=lambda c: fr.chave_principal(pc[c])) for m in membros.values() if len(m) > 1]
    grupos.sort(key=lambda g: pc[g[0]]["sequencial"] or 0)
    return grupos, nao


# ----------------------------------------------------------------- análise (só leitura)
def analisar(con, proj: str, raiz, usar: bool) -> dict | None:
    an = ldf.analisar(con, proj, raiz, usar)
    if not an:
        return None
    pc = {r["codigo"]: dict(r) for r in con.execute("SELECT * FROM item WHERE projeto_codigo=?", (proj,))}
    an["por_cod"] = pc
    grupos, nao = grupos_com_cadeias(an)
    decisoes = []
    for g in grupos:
        fica, como = escolher(g, pc)
        k = pc[fica]
        k_no_ar = k["status_site"] == "no_ar" and bool(k["tainacan_item_id"])
        principal = g[0]
        herda = {}
        if principal != fica:
            for campo in HERDA:
                if campo in k and not (k[campo] or "").strip() and (pc[principal].get(campo) or "").strip():
                    herda[campo] = pc[principal][campo]
        d = {"fica": fica, "como": como, "principal_antes": principal, "herda": herda, "retirar": [], "retirar_301": [], "ficam_como_copia": []}
        for c in g:
            if c == fica:
                continue
            i = pc[c]
            presa = next((rotulo for t, col, rotulo in PRENDEM if _tem_tabela(con, t)
                          and con.execute(f"SELECT 1 FROM {t} WHERE {col}=?", (c,)).fetchone()), None)
            if presa:
                d["ficam_como_copia"].append({"codigo": c, "porque": f"tem {presa} registrado: não retiro (fica como cópia de {d_curto(fica)})"})
            elif fr.no_site(i):
                if k_no_ar and i["tainacan_item_id"]:
                    d["retirar_301"].append({"codigo": c, "site_id": i["tainacan_item_id"], "estava": i["status_site"]})
                else:
                    d["ficam_como_copia"].append({"codigo": c, "porque": "precisa publicar a JPG antes", "site_id": i["tainacan_item_id"],
                                                  "fica_situacao": k["status_site"] or "nao_publicado"})
            else:
                d["retirar"].append(c)
        decisoes.append(d)
    return {"titulo": an["titulo"], "folhas": an["folhas"], "por_cod": pc, "decisoes": decisoes, "incertos": an["r"]["incertos"],
            "suspeitas": an["suspeitas"], "marcas_nao_juntadas": nao, "carimbo": carimbo(con, proj), "lidas": an["lidas"]}


def fmt(pc, c, extra="") -> str:
    return f"{d_curto(c)} ({fr.rotulo_formato(pc[c]['arquivo_origem'])}{extra})"


def mostrar(proj: str, a: dict, listar: int) -> None:
    pc = a["por_cod"]
    nome = proj.split("-")[-1]
    print("\n" + "─" * 100)
    print(f"{nome} {a['titulo'] or ''}".rstrip() + f": {a['folhas']} folhas; {len(a['decisoes'])} prancha(s) com cópias")
    if not a["decisoes"]:
        print("   nenhuma cópia.")
    for d in a["decisoes"]:
        partes = [fmt(pc, c) for c in d["retirar"]] + [fmt(pc, x["codigo"], " · sai do site, 301") for x in d["retirar_301"]]
        linha = f"{nome}: fica {fmt(pc, d['fica'], ' · no site' if fr.no_site(pc[d['fica']]) else '')}"
        linha += (" · retira " + ", ".join(partes)) if partes else ""
        if d["como"] == "sem_jpg":
            linha += "  [sem JPG: fica a principal de hoje]"
        elif d["como"] == "jpg_limpo":
            linha += "  [sem JPG simples: fica o JPG LIMPO]"
        print("   " + linha)
        for x in d["ficam_como_copia"]:
            if x["porque"] == "precisa publicar a JPG antes":
                print(f"        PRECISA PUBLICAR A JPG ANTES: {fmt(pc, x['codigo'], ' · no site')} fica (como cópia de {d_curto(d['fica'])}) até"
                      f" {d_curto(d['fica'])} ({x['fica_situacao']}) ser publicada no painel; depois simule de novo e ela sai com 301.")
            else:
                print(f"        {fmt(pc, x['codigo'])}: {x['porque']}")
        if d["herda"]:
            print(f"        {d_curto(d['fica'])} herda de {d_curto(d['principal_antes'])}: " + ", ".join(f"{k}='{v}'" for k, v in d["herda"].items()))
    if a["marcas_nao_juntadas"]:
        print(f"   MARCAS 'cópia de' QUE NÃO JUNTEI (juntariam duas folhas da mesma pasta/formato; não mexo): {len(a['marcas_nao_juntadas'])}")
        for x in a["marcas_nao_juntadas"][:listar]:
            print(f"     {d_curto(x['codigo'])} → {d_curto(x['de'])}: {x['porque']}")
    if a["suspeitas"]:
        print(f"   MARCAS ANTIGAS SUSPEITAS (mesma pasta; não mexo): " + ", ".join(f"{d_curto(x['codigo'])}→{d_curto(x['de'])}" for x in a["suspeitas"][:listar]))
    if a["incertos"]:
        print(f"   INCERTOS (não mexo): {len(a['incertos'])}")
        for x, y, m in a["incertos"][:listar]:
            print(f"     {d_curto(x)} ~ {d_curto(y)}: {m}")


# ----------------------------------------------------------------- simular
def simular(a, db: str) -> int:
    con = ldf.abrir(db, escrita=False)
    print(f"SIMULAÇÃO (nada é gravado no banco). Banco, só leitura: {db}")
    if not _tem_tabela(con, "item_retirado"):
        print("AVISO: o banco ainda não tem a tabela item_retirado (migração 220): atualize o painel (./atualizar.sh) antes de aplicar.")
    raiz = ldf.raiz_prontos(con)
    usar = not a.sem_imagens
    if usar and not (raiz and raiz.is_dir()):
        print(f"AVISO: a pasta do acervo no QNAP ({raiz}) não está acessível: sigo SEM as imagens (só md5, nome e posição).")
        usar = False
    fundo = a.fundo.upper()
    projetos = [p.upper() for p in a.projeto] if a.projeto else [r[0] for r in con.execute(
        "SELECT DISTINCT projeto_codigo FROM item WHERE projeto_codigo LIKE ? ORDER BY 1", (fundo + "-%",))]
    plano = {"tipo": "retirar_copias", "versao": 1, "gerado_em": datetime.now().isoformat(timespec="seconds"), "banco": db, "com_imagens": usar,
             "aviso": "PROPOSTA. Nada foi aplicado. Para aplicar: --aplicar --plano <este arquivo>.", "projetos": {}}
    tot = dict.fromkeys(("grupos", "ficam", "retiradas", "s301", "publicar", "sem_jpg", "jpg_limpo", "incertos", "suspeitas", "nao_juntadas", "presas"), 0)
    for proj in projetos:
        an = analisar(con, proj, raiz, usar)
        if not an:
            continue
        mostrar(proj, an, a.listar)
        ds = an["decisoes"]
        tot["grupos"] += len(ds); tot["ficam"] += len(ds)
        tot["retiradas"] += sum(len(d["retirar"]) + len(d["retirar_301"]) for d in ds)
        tot["s301"] += sum(len(d["retirar_301"]) for d in ds)
        tot["publicar"] += sum(1 for d in ds if any(x["porque"] == "precisa publicar a JPG antes" for x in d["ficam_como_copia"]))
        tot["presas"] += sum(1 for d in ds for x in d["ficam_como_copia"] if x["porque"] != "precisa publicar a JPG antes")
        tot["sem_jpg"] += sum(1 for d in ds if d["como"] == "sem_jpg"); tot["jpg_limpo"] += sum(1 for d in ds if d["como"] == "jpg_limpo")
        tot["incertos"] += len(an["incertos"]); tot["suspeitas"] += len(an["suspeitas"]); tot["nao_juntadas"] += len(an["marcas_nao_juntadas"])
        plano["projetos"][proj] = {"titulo": an["titulo"], "carimbo": an["carimbo"], "decisoes": ds,
                                   "incertos": [{"a": x, "b": y, "motivo": m} for x, y, m in an["incertos"]],
                                   "marcas_suspeitas": an["suspeitas"], "marcas_nao_juntadas": an["marcas_nao_juntadas"]}
    con.close()
    print("\n" + "═" * 100)
    print(f"TOTAL: {tot['grupos']} prancha(s) com cópias → ficam {tot['ficam']} (a JPG original), retiram-se {tot['retiradas']} cópia(s)"
          f" ({tot['s301']} saem do site com 301) · {tot['publicar']} precisam publicar a JPG antes · {tot['sem_jpg']} grupo(s) sem JPG"
          f" (fica a principal de hoje) · {tot['jpg_limpo']} só com JPG LIMPO · {tot['incertos']} incerto(s) intocado(s)"
          f" · {tot['suspeitas']} marca(s) suspeita(s) intocada(s)" + (f" · {tot['nao_juntadas']} marca(s) não juntada(s)" if tot["nao_juntadas"] else "")
          + (f" · {tot['presas']} cópia(s) presa(s) (empréstimo/pedido)" if tot["presas"] else ""))
    arq = Path(a.plano) if a.plano else Path.cwd() / f"plano_retirar_copias_{datetime.now():%Y%m%d-%H%M%S}.json"
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nPlano gravado em {arq}. NADA foi aplicado.")
    print(f"Para aplicar (depois de conferir): PYTHONPATH=backend python scripts/retirar_copias.py --aplicar --plano {arq}")
    return 0


# ----------------------------------------------------------------- aplicar
def _linha(con, cod: str) -> dict | None:
    r = con.execute("SELECT * FROM item WHERE codigo=?", (cod,)).fetchone()
    return dict(r) if r else None


def _esconder(db: str, proj: str, d: dict) -> tuple[list[dict], list[str]]:
    """Fase de rede (fora de transação): as cópias no site saem do público (privadas) antes de serem retiradas. A que falhar fica."""
    from fastapi import HTTPException
    from app import publicador
    feitas, nao = [], []
    for e in d["retirar_301"]:
        c, fica = e["codigo"], d["fica"]
        con = ldf.abrir(db, escrita=True)
        try:
            ic, io = _linha(con, c), _linha(con, fica)
        finally:
            con.close()
        if not ic or ic["projeto_codigo"] != proj or ic["status_site"] not in ("no_ar", "rascunho") or str(ic["tainacan_item_id"]) != str(e["site_id"]):
            nao.append(f"{d_curto(c)} mudou desde a simulação (não mexo)"); continue
        if not io or io["status_site"] != "no_ar" or not io["tainacan_item_id"]:
            nao.append(f"{d_curto(c)}: publique {d_curto(fica)} antes"); continue
        try:
            ok = publicador.esconder_folha_no_site(c, ATOR, f"cópia de {fica} (a mesma prancha em outro formato): sai do site com 301")
        except HTTPException as err:
            nao.append(f"{d_curto(c)}: {err.detail}"); continue
        if not ok:
            nao.append(f"{d_curto(c)}: nada a tirar do site"); continue
        feitas.append({**e, "estava": ic["status_site"]})
    return feitas, nao


def _retirar(con, c: str, fica: str, motivo: str, plano: str, site: dict | None, linha: dict) -> dict:
    """Lápide + apaga a folha e o que só existe por causa dela (transação de quem chama). `linha`: a folha como estava ANTES de qualquer
    mudança do grupo (a cópia de uma cópia é reapontada no caminho). Devolve o registro para o desfazer."""
    deps, reap = {}, {"duplicata_de": [], "capa": []}
    for t, col, extra in DEPENDENTES:
        if _tem_tabela(con, t):
            deps[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t} WHERE {col}=?{extra}", (c,))]
    for (x,) in con.execute("SELECT codigo FROM item WHERE duplicata_de=? AND codigo<>?", (c, c)).fetchall():
        reap["duplicata_de"].append(x)
        con.execute("UPDATE item SET duplicata_de=? WHERE codigo=?", (None if x == fica else fica, x))
    for (p,) in con.execute("SELECT codigo FROM projeto WHERE capa_item=?", (c,)).fetchall():
        reap["capa"].append(p)
        con.execute("UPDATE projeto SET capa_item=? WHERE codigo=?", (fica, p))
    for t, col, extra in DEPENDENTES:
        if t in deps and deps[t]:
            con.execute(f"DELETE FROM {t} WHERE {col}=?{extra}", (c,))
    dependentes = {"linhas": deps, "reapontadas": reap}
    con.execute("""INSERT INTO item_retirado (codigo, projeto_codigo, sequencial, md5, arquivo_origem, fica, motivo, linha, dependentes, site, plano, retirado_por)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c, linha["projeto_codigo"], linha["sequencial"], linha.get("md5"), linha.get("arquivo_origem"), fica, motivo,
                 json.dumps(linha, ensure_ascii=False, default=str), json.dumps(dependentes, ensure_ascii=False, default=str),
                 json.dumps(site, ensure_ascii=False, default=str) if site else None, plano, ATOR))
    con.execute("DELETE FROM item WHERE codigo=?", (c,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                (c, "folha_retirada", ATOR, json.dumps({"fica": fica, "motivo": motivo, "saiu_do_site": bool(site), "plano": plano}, ensure_ascii=False)))
    return {"codigo": c, "fica": fica, "site": site}


def aplicar(a, db: str) -> int:
    from app import redir_site
    if not a.plano or not Path(a.plano).is_file():
        sys.exit("ERRO: --aplicar precisa de --plano <arquivo> gerado pela simulação (rode sem --aplicar primeiro).")
    plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
    if plano.get("tipo") != "retirar_copias":
        sys.exit("ERRO: este arquivo não é um plano de retirar cópias.")
    if str(Path(plano.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: o plano foi feito no banco {plano.get('banco')}, e este é {db}. Simule de novo neste banco.")
    projs = plano["projetos"]
    n_301 = sum(len(d["retirar_301"]) for x in projs.values() for d in x["decisoes"])
    n_tudo = sum(1 for x in projs.values() for d in x["decisoes"])
    con = ldf.abrir(db, escrita=True)
    if not _tem_tabela(con, "item_retirado"):
        con.close()
        sys.exit("ERRO: o banco não tem a tabela item_retirado (migração 220). Atualize o painel (./atualizar.sh) e simule de novo.")
    velhos = [p for p, x in projs.items() if carimbo(con, p) != x["carimbo"]]
    con.close()
    if velhos:
        print("RECUSADO: o banco mudou desde a simulação nestes projetos: " + ", ".join(velhos) + ".")
        print("Nada foi aplicado. Rode a simulação de novo, confira e aplique o plano novo.")
        return 3
    if not n_tudo:
        print("O plano não tem nada a aplicar.")
        return 0
    if n_301 and not ldf._mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: tirar do site usa a rotina do painel, que grava no banco do painel (CAMP_DB_PATH); este é {db}. Nada foi aplicado.")
    copia = ldf._backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    arq = Path(a.plano).with_suffix(".desfazer.json")
    desf = {"tipo": "desfazer_retirar_copias", "banco": db, "plano": str(Path(a.plano).resolve()), "backup": copia,
            "aplicado_em": datetime.now().isoformat(timespec="seconds"), "projetos": {}}
    gravar = lambda: arq.write_text(json.dumps(desf, ensure_ascii=False, indent=1, default=str), encoding="utf-8")  # noqa: E731
    tot = {"ficam": 0, "retiradas": 0, "s301": 0, "publicar": 0}
    avisos = []
    for proj, x in projs.items():
        escondidas = {}
        for d in x["decisoes"]:                    # rede primeiro (fora de transação); a que não saiu do site não é retirada
            feitas, nao = _esconder(db, proj, d) if d["retirar_301"] else ([], [])
            escondidas[d["fica"]] = {e["codigo"]: e for e in feitas}
            avisos += [f"{proj} {m}" for m in nao]
        con = ldf.abrir(db, escrita=True)
        reg = []
        try:
            con.execute("BEGIN IMMEDIATE")
            for d in x["decisoes"]:
                fica = d["fica"]
                k = _linha(con, fica)
                if not k:
                    avisos.append(f"{proj}: {d_curto(fica)} não existe mais (grupo pulado)"); continue
                esc = escondidas.get(fica, {})
                ficam = [e["codigo"] for e in d["ficam_como_copia"]] + [e["codigo"] for e in d["retirar_301"] if e["codigo"] not in esc]
                retirar = [c for c in d["retirar"] if _linha(con, c)] + list(esc)
                antes = {c: _linha(con, c) for c in [fica, *ficam] if _linha(con, c)}
                linhas_antes = {c: _linha(con, c) for c in retirar}
                upd = {"duplicata_de": None, "tipo_duplicata": None}
                for campo, v in (d.get("herda") or {}).items():
                    if not (k.get(campo) or "").strip():
                        upd[campo] = v
                con.execute("UPDATE item SET " + ", ".join(f"{c_}=?" for c_ in upd) + " WHERE codigo=?", (*upd.values(), fica))
                for c in ficam:
                    if c in antes:
                        con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata='mesma_folha' WHERE codigo=?", (fica, c))
                feitos = []
                for c in retirar:
                    site = None
                    if c in esc:
                        redir_antes = con.execute("SELECT * FROM redirecionamento WHERE codigo_antigo=?", (c,)).fetchone()
                        apont = [r[0] for r in con.execute("SELECT codigo_antigo FROM redirecionamento WHERE codigo_novo=?", (c,))]
                        redir_site.registrar(con, c, fica, "item", MOTIVO_301, ATOR)
                        site = {"site_id": esc[c]["site_id"], "estava": esc[c]["estava"], "redir_antes": dict(redir_antes) if redir_antes else None,
                                "redir_apontavam": apont}
                    feitos.append(_retirar(con, c, fica, f"cópia de {fica} ({d['como']})", desf["plano"], site, linhas_antes[c]))
                depois = {c: _linha(con, c) for c in antes}
                reg.append({"fica": fica, "antes": antes, "depois": depois, "retirados": feitos})
                tot["ficam"] += 1; tot["retiradas"] += len(feitos); tot["s301"] += len(esc)
                tot["publicar"] += 1 if any(e["porque"] == "precisa publicar a JPG antes" for e in d["ficam_como_copia"]) else 0
                print(f"{proj}: fica {d_curto(fica)}" + (" · retirada(s) " + ", ".join(d_curto(f["codigo"]) + (" (301)" if f["site"] else "") for f in feitos) if feitos else "")
                      + (" · fica(m) como cópia: " + ", ".join(d_curto(c) for c in ficam) if ficam else ""))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "copias_retiradas", ATOR, json.dumps({"retiradas": sum(len(r_["retirados"]) for r_ in reg), "plano": desf["plano"], "backup": copia}, ensure_ascii=False)))
            from app.problemas import fechar_resolvidos
            fechar_resolvidos(con, ATOR)
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        desf["projetos"][proj] = reg
        gravar()
    print(f"\nFEITO: ficam {tot['ficam']} folha(s) (a JPG original); {tot['retiradas']} cópia(s) retirada(s) do sistema"
          f" ({tot['s301']} saíram do site com 301; o coletor de 10 min envia o 301 ao site); {tot['publicar']} grupo(s) precisam publicar a JPG antes.")
    for m in avisos:
        print(f"   {m}")
    print(f"Nenhum arquivo do QNAP foi tocado. As folhas retiradas estão em item_retirado. Backup: {copia}")
    print(f"Para DESFAZER: PYTHONPATH=backend python scripts/retirar_copias.py --desfazer {arq}            (mostra)")
    print(f"               PYTHONPATH=backend python scripts/retirar_copias.py --desfazer {arq} --aplicar  (volta)")
    return 0


# ----------------------------------------------------------------- desfazer
def _inserir(con, tabela: str, linha: dict) -> None:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")]
    ks = [k for k in linha if k in cols]
    con.execute(f"INSERT OR REPLACE INTO {tabela} ({', '.join(ks)}) VALUES ({', '.join('?' * len(ks))})", [linha[k] for k in ks])


def desfazer(a, db: str) -> int:
    dados = json.loads(Path(a.desfazer).read_text(encoding="utf-8"))
    if dados.get("tipo") != "desfazer_retirar_copias":
        sys.exit("ERRO: este arquivo não é o de desfazer de retirar cópias.")
    if str(Path(dados.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: a retirada foi feita no banco {dados.get('banco')}, e este é {db}.")
    con = ldf.abrir(db, escrita=a.aplicar)
    volta, mudou, site = [], [], []
    for proj, grupos in dados["projetos"].items():
        for g in grupos:
            for f in g["retirados"]:
                ok = con.execute("SELECT 1 FROM item_retirado WHERE codigo=?", (f["codigo"],)).fetchone() and not _linha(con, f["codigo"])
                (volta if ok else mudou).append((proj, g, f))
                if ok and f.get("site"):
                    site.append((proj, f))
    print(f"{'DESFAZENDO' if a.aplicar else 'SIMULAÇÃO do desfazer (nada é gravado)'}: {len(volta)} folha(s) voltam ao painel"
          + (f" ({len(site)} voltam ao site e perdem o 301)" if site else "")
          + (f"; {len(mudou)} não (já voltaram ou o código existe de novo): " + ", ".join(d_curto(f["codigo"]) for _, _, f in mudou) if mudou else ""))
    if not a.aplicar:
        for proj, g, f in volta[:a.listar]:
            print(f"   {proj} {d_curto(f['codigo'])} volta (cópia de {d_curto(g['fica'])})")
        con.close()
        print("Para desfazer de verdade, repita com --aplicar.")
        return 0
    con.close()
    if site and not ldf._mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: republicar usa a conexão do painel (CAMP_DB_PATH), e este banco é {db}. Nada foi desfeito.")
    copia = ldf._backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = ldf.abrir(db, escrita=True)
    avisos, feitas = [], 0
    voltam = {f["codigo"] for _, _, f in volta}
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys = ON")     # uma cópia pode apontar para outra que também volta
        for proj, g, f in volta:
            t = con.execute("SELECT * FROM item_retirado WHERE codigo=?", (f["codigo"],)).fetchone()
            _inserir(con, "item", json.loads(t["linha"]))
            dep = json.loads(t["dependentes"] or "{}")
            for tabela, linhas in (dep.get("linhas") or {}).items():
                for ln in linhas:
                    _inserir(con, tabela, ln)
            for x in (dep.get("reapontadas") or {}).get("duplicata_de") or []:
                if x not in voltam:
                    con.execute("UPDATE item SET duplicata_de=? WHERE codigo=? AND (duplicata_de=? OR duplicata_de IS NULL)", (f["codigo"], x, f["fica"]))
            for p in (dep.get("reapontadas") or {}).get("capa") or []:
                con.execute("UPDATE projeto SET capa_item=? WHERE codigo=? AND capa_item=?", (f["codigo"], p, f["fica"]))
            s = f.get("site")
            if s:
                con.execute("DELETE FROM redirecionamento WHERE codigo_antigo=? AND codigo_novo=? AND criado_por=?", (f["codigo"], f["fica"], ATOR))
                if s.get("redir_antes"):
                    _inserir(con, "redirecionamento", s["redir_antes"])
                for ap in s.get("redir_apontavam") or []:
                    con.execute("UPDATE redirecionamento SET codigo_novo=?, aplicado_no_site=0, sem_site=0 WHERE codigo_antigo=? AND codigo_novo=?", (f["codigo"], ap, f["fica"]))
            con.execute("DELETE FROM item_retirado WHERE codigo=?", (f["codigo"],))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                        (f["codigo"], "folha_devolvida", ATOR, json.dumps({"via": "desfazer de retirar cópias", "arquivo": str(Path(a.desfazer).resolve())}, ensure_ascii=False)))
            feitas += 1
        cols = [r[1] for r in con.execute("PRAGMA table_info(item)")]
        for proj, grupos in dados["projetos"].items():         # a que ficou e as que ficaram como cópia voltam como eram
            for g in grupos:
                for c, antes in (g.get("antes") or {}).items():
                    agora, depois = _linha(con, c), (g.get("depois") or {}).get(c)
                    if not agora or not antes:
                        continue
                    if json.dumps(agora, default=str, sort_keys=True) == json.dumps(depois, default=str, sort_keys=True):
                        ks = [k for k in antes if k in cols and k != "codigo"]
                    else:
                        ks = ["duplicata_de", "tipo_duplicata"]
                        avisos.append(f"{d_curto(c)} mudou depois da retirada: só a marca 'cópia de' voltou")
                    con.execute("UPDATE item SET " + ", ".join(f"{k}=?" for k in ks) + " WHERE codigo=?", (*[antes[k] for k in ks], c))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "copias_devolvidas", ATOR, json.dumps({"arquivo": str(Path(a.desfazer).resolve()), "backup": copia}, ensure_ascii=False)))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    rep = 0
    if site:
        from app import publicador
        from app.publicacao import persistir_resultado
        for proj, f in site:
            s = f["site"]
            wid, estava = int(s["site_id"]), s.get("estava") or "no_ar"
            wp_status = "publish" if estava == "no_ar" else "draft"
            try:
                publicador.WP().atualizar_status_item(publicador.COL_ACERVO, wid, wp_status)
            except Exception as x:  # noqa: BLE001
                avisos.append(f"{d_curto(f['codigo'])}: o site não voltou o item {wid} ({str(x)[:160]}); a folha voltou ao painel, mas continua privada lá.")
                continue
            persistir_resultado([("item", f["codigo"], wid)], estava, wp_status, "item", f["codigo"], "site_folha_republicada", ATOR,
                                {"via": "desfazer de retirar cópias", "fica": f["fica"]})
            rep += 1
    print(f"FEITO: {feitas} folha(s) voltaram ao painel como estavam" + (f"; {rep} de volta ao site, sem o 301" if site else "") + f". Backup: {copia}")
    for m in avisos:
        print(f"   {m}")
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
    ap.add_argument("--listar", type=int, default=20, help="quantos incertos/marcas mostrar por projeto (padrão 20)")
    a = ap.parse_args()
    db = ldf.caminho_db(a)
    if a.desfazer:
        return desfazer(a, db)
    if a.aplicar:
        return aplicar(a, db)
    return simular(a, db)


if __name__ == "__main__":
    sys.exit(main())
