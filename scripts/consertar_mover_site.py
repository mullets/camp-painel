#!/usr/bin/env python3
"""15/11/2026 · Consertar o que o mover lote/folhas deixou no site e no painel.

Pedido do Rafael: "Movi um lote inteiro de um projeto para outro; no antigo ficaram as imagens no site, e no painel ficam como 'só no site'.
Devia tirar de ambos." O painel novo já faz isso a cada mover (app.mover_site); este script arruma o que foi movido ANTES:
  (a) folhas FANTASMA no painel: a importação do site recriou no projeto antigo, como folha "só no site" (origem 'importado'), o registro
      antigo de uma folha que foi movida (ou recodificada). Saem do painel como LÁPIDE em item_retirado (a linha inteira, com o que
      dependia dela), com desfazer; o número D não é reusado e a importação não as traz de volta. Folha fantasma com empréstimo ou pedido
      de releitura só é listada.
  (b) registros ANTIGOS no site de folhas movidas que ainda estão públicos (ou rascunho): ficam PRIVADOS no site (nada é apagado). O 301
      (código antigo → novo) já existe; se faltar, é registrado. Todos entram em site_registro_antigo (o mapa que a importação respeita);
      o que o site recusar fica pendente lá e o painel tenta de novo sozinho.
Tudo listado por projeto (o projeto ANTIGO, de onde as folhas saíram).

PADRÃO = SIMULAR: abre o banco SÓ LEITURA, mostra o que seria feito e grava o plano (JSON). Nada muda, nem no site.

No servidor do painel:
  cd ~/camp-painel && source .venv/bin/activate
  PYTHONPATH=backend python scripts/consertar_mover_site.py --fundo F001 --plano ~/plano_mover_site.json        # simula (um fundo)
  PYTHONPATH=backend python scripts/consertar_mover_site.py --plano ~/plano_mover_site.json                     # simula (tudo)
  PYTHONPATH=backend python scripts/consertar_mover_site.py --aplicar --plano ~/plano_mover_site.json
        aplica EXATAMENTE o plano lido (RECUSADO se o banco mudou desde a simulação), depois de um backup do banco
  PYTHONPATH=backend python scripts/consertar_mover_site.py --desfazer ~/plano_mover_site.desfazer.json             # mostra o que voltaria
  PYTHONPATH=backend python scripts/consertar_mover_site.py --desfazer ~/plano_mover_site.desfazer.json --aplicar   # volta como estava
  Outras opções: --projeto F001-P0013 (pode repetir; o projeto antigo) · --db caminho.db · --listar N
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
from app import mover_site as ms  # noqa: E402
import limpar_duplicatas_formato as ldf  # noqa: E402

ATOR = "consertar mover site"
MOTIVO_301 = "folha movida para outro projeto (consertar mover site)"
DEPENDENTES = (("item_agente", "item_codigo", ""), ("item_localizacao", "item_codigo", ""), ("revisao_campo", "item_codigo", ""),
               ("fila_correcao_site", "item_codigo", ""), ("erro", "codigo", ""), ("divergencia_site", "codigo", " AND entidade='item'"))
PRENDEM = (("emprestimo_item", "item_codigo", "empréstimo"), ("pedido_releitura", "item_codigo", "pedido de releitura"))
STATUS_VOLTA = {"publish": "publish", "draft": "draft", "pending": "draft"}


def _tem(con, t: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _prefixos(a) -> list[str]:
    if a.projeto:
        return [p.strip().upper() + "-" for p in a.projeto]
    if a.fundo:
        return [a.fundo.strip().upper() + "-"]
    return [""]


# ----------------------------------------------------------------- análise (só leitura)
def analisar(con, prefixos: list[str]) -> dict:
    """{projeto antigo: {fantasmas, presos, site, redir, registrar, ligados}} — o que está errado hoje, sem mudar nada."""
    dentro = lambda c: any(str(c or "").startswith(p) for p in prefixos)  # noqa: E731
    mapa = {w: {"de": x["de"], "para": x["para"], "na_tabela": False, "escondido_em": None} for w, x in ms.ids_de_eventos(con).items()}
    if ms.tem_tabela(con):
        for r in con.execute("SELECT wp_id, codigo_antigo, codigo_novo, escondido_em FROM site_registro_antigo"):
            mapa[int(r[0])] = {"de": r[1], "para": r[2], "na_tabela": True, "escondido_em": r[3]}
    redirs = {r[0]: r[1] for r in con.execute(
        "SELECT codigo_antigo, codigo_novo FROM redirecionamento WHERE entidade='item' AND codigo_novo IS NOT NULL AND codigo_novo<>codigo_antigo")}
    existe = lambda c: bool(c) and bool(con.execute("SELECT 1 FROM item WHERE codigo=?", (c,)).fetchone())  # noqa: E731
    ligados = lambda w: [r[0] for r in con.execute("SELECT codigo FROM item WHERE tainacan_item_id=? ORDER BY codigo", (w,))]  # noqa: E731
    espelho = lambda w: (con.execute("SELECT status FROM wp_item WHERE id=?", (w,)).fetchone() or [None])[0]  # noqa: E731
    out: dict[str, dict] = {}
    proj = lambda p: out.setdefault(p, {"fantasmas": [], "presos": [], "site": [], "redir": [], "registrar": [], "ligados": []})  # noqa: E731

    # (a) fantasmas: folha importada do site que é, na verdade, o registro antigo de uma folha que mudou de código
    fantasmas = set()
    for g in con.execute("""SELECT codigo, projeto_codigo, tainacan_item_id, status_site, titulo FROM item
                            WHERE origem='importado' AND tainacan_item_id IS NOT NULL ORDER BY codigo""").fetchall():
        if not dentro(g["codigo"]):
            continue
        w = int(g["tainacan_item_id"])
        outros = [c for c in ligados(w) if c != g["codigo"]]
        if w in mapa:
            motivo, fica = f"registro antigo de {mapa[w]['de'] or g['codigo']}, movida para {mapa[w]['para']}", mapa[w]["para"]
        elif outros:
            motivo, fica = f"o item {w} do site é da folha {outros[0]}", outros[0]
        elif g["codigo"] in redirs:
            motivo, fica = f"o código redireciona para {redirs[g['codigo']]}", redirs[g["codigo"]]
        else:
            continue
        presa = next((rot for t, col, rot in PRENDEM if _tem(con, t) and con.execute(f"SELECT 1 FROM {t} WHERE {col}=?", (g["codigo"],)).fetchone()), None)
        e = {"codigo": g["codigo"], "wp_id": w, "status_site": g["status_site"], "titulo": g["titulo"], "motivo": motivo,
             "fica": fica if existe(fica) else None}
        if presa:
            proj(g["projeto_codigo"])["presos"].append({**e, "porque": f"tem {presa} registrado: não retiro"})
            continue
        fantasmas.add(g["codigo"])
        proj(g["projeto_codigo"])["fantasmas"].append(e)
        if w not in mapa and not outros:            # registro antigo sem evento (só o 301): também sai do público
            mapa[w] = {"de": g["codigo"], "para": redirs[g["codigo"]], "na_tabela": False, "escondido_em": None, "so_redir": True}

    # (b) registros antigos no site ainda não privados; 301 que falta; linhas que faltam no mapa explícito
    for w in sorted(mapa):
        x = mapa[w]
        if not dentro(x["de"]):
            continue
        p = proj(str(x["de"])[:10])
        reais = [c for c in ligados(w) if c not in fantasmas]
        if reais:                                   # outra folha do painel usa este item do site: não mexo
            p["ligados"].append({"wp_id": w, "de": x["de"], "folha": reais[0]})
            continue
        st = espelho(w)
        if not x["na_tabela"]:
            p["registrar"].append({"wp_id": w, "de": x["de"], "para": x["para"], "privado": st == "private"})
        if not x["escondido_em"] and st != "private":
            p["site"].append({"wp_id": w, "de": x["de"], "para": x["para"], "espelho": st})
        if x["de"] and x["para"] and not con.execute("SELECT 1 FROM redirecionamento WHERE codigo_antigo=?", (x["de"],)).fetchone():
            p["redir"].append({"de": x["de"], "para": x["para"]})
    return {k: v for k, v in sorted(out.items()) if any(v[c] for c in ("fantasmas", "presos", "site", "redir", "registrar", "ligados"))}


def carimbo(projetos: dict) -> str:
    return hashlib.sha256(json.dumps(projetos, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:24]


def mostrar(projetos: dict, listar: int) -> dict:
    tot = dict.fromkeys(("fantasmas", "presos", "site", "redir", "registrar", "ligados"), 0)
    for p, x in projetos.items():
        print("\n" + "─" * 100)
        print(f"{p}: {len(x['fantasmas'])} folha(s) fantasma no painel · {len(x['site'])} registro(s) antigo(s) ainda no público/rascunho no site"
              f" · {len(x['redir'])} 301 a registrar")
        for e in x["fantasmas"][:listar]:
            print(f"   FANTASMA {e['codigo']} (\"só no site\", item {e['wp_id']}): {e['motivo']} → sai do painel (lápide; desfazer volta)")
        for e in x["presos"][:listar]:
            print(f"   {e['codigo']}: {e['motivo']} · {e['porque']}")
        for e in x["site"][:listar]:
            print(f"   SITE item {e['wp_id']} ({e['de']} → {e['para']}; espelho: {e['espelho'] or 'não está no espelho'}) → fica privado no site")
        for e in x["redir"][:listar]:
            print(f"   301 {e['de']} → {e['para']} (faltava)")
        for e in x["ligados"][:listar]:
            print(f"   item {e['wp_id']} ({e['de']}): é da folha {e['folha']} → não mexo")
        for k in tot:
            tot[k] += len(x[k])
        resto = max(0, max((len(x[k]) for k in ("fantasmas", "site", "redir")), default=0) - listar)
        if resto:
            print(f"   … e mais {resto} (use --listar N para ver todos)")
    return tot


# ----------------------------------------------------------------- simular
def simular(a, db: str) -> int:
    con = ldf.abrir(db, escrita=False)
    print(f"SIMULAÇÃO (nada é gravado no banco nem no site). Banco, só leitura: {db}")
    if not ms.tem_tabela(con):
        print("AVISO: o banco ainda não tem a tabela site_registro_antigo (migração 222): atualize o painel (./atualizar.sh) antes de aplicar.")
    pref = _prefixos(a)
    projetos = analisar(con, pref)
    con.close()
    tot = mostrar(projetos, a.listar)
    print("\n" + "═" * 100)
    print(f"TOTAL: {len(projetos)} projeto(s) · {tot['fantasmas']} folha(s) fantasma saem do painel · {tot['site']} registro(s) antigo(s) ficam"
          f" privados no site · {tot['redir']} 301 a registrar · {tot['registrar']} entram no mapa de registros antigos"
          + (f" · {tot['presos']} fantasma(s) presa(s) (empréstimo/pedido), intocada(s)" if tot["presos"] else "")
          + (f" · {tot['ligados']} item(ns) ligado(s) a outra folha, intocado(s)" if tot["ligados"] else ""))
    plano = {"tipo": "consertar_mover_site", "versao": 1, "gerado_em": datetime.now().isoformat(timespec="seconds"), "banco": db,
             "prefixos": pref, "aviso": "PROPOSTA. Nada foi aplicado. Para aplicar: --aplicar --plano <este arquivo>.",
             "carimbo": carimbo(projetos), "projetos": projetos}
    arq = Path(a.plano) if a.plano else Path.cwd() / f"plano_mover_site_{datetime.now():%Y%m%d-%H%M%S}.json"
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\nPlano gravado em {arq}. NADA foi aplicado.")
    print(f"Para aplicar (depois de conferir): PYTHONPATH=backend python scripts/consertar_mover_site.py --aplicar --plano {arq}")
    return 0


# ----------------------------------------------------------------- aplicar
def _retirar(con, c: str, fica: str | None, motivo: str, plano: str, site: dict | None) -> dict:
    """Lápide da folha fantasma + apaga ela e o que só existia por causa dela (transação de quem chama)."""
    linha = dict(con.execute("SELECT * FROM item WHERE codigo=?", (c,)).fetchone())
    deps, reap = {}, {"duplicata_de": [], "capa": []}
    for t, col, extra in DEPENDENTES:
        if _tem(con, t):
            deps[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t} WHERE {col}=?{extra}", (c,))]
    for (x,) in con.execute("SELECT codigo FROM item WHERE duplicata_de=? AND codigo<>?", (c, c)).fetchall():
        reap["duplicata_de"].append(x)
        con.execute("UPDATE item SET duplicata_de=? WHERE codigo=?", (None if x == fica else fica, x))
    for (p,) in con.execute("SELECT codigo FROM projeto WHERE capa_item=?", (c,)).fetchall():
        reap["capa"].append(p)
        con.execute("UPDATE projeto SET capa_item=? WHERE codigo=?", (fica if fica and fica.startswith(p + "-") else None, p))
    for t, col, extra in DEPENDENTES:
        if deps.get(t):
            con.execute(f"DELETE FROM {t} WHERE {col}=?{extra}", (c,))
    con.execute("""INSERT INTO item_retirado (codigo, projeto_codigo, sequencial, md5, arquivo_origem, fica, motivo, linha, dependentes, site, plano, retirado_por)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c, linha["projeto_codigo"], linha["sequencial"], linha.get("md5"), linha.get("arquivo_origem"), fica, motivo,
                 json.dumps(linha, ensure_ascii=False, default=str), json.dumps({"linhas": deps, "reapontadas": reap}, ensure_ascii=False, default=str),
                 json.dumps(site, ensure_ascii=False, default=str) if site else None, plano, ATOR))
    con.execute("DELETE FROM item WHERE codigo=?", (c,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                (c, "folha_retirada", ATOR, json.dumps({"fica": fica, "motivo": motivo, "plano": plano}, ensure_ascii=False)))
    return {"codigo": c, "fica": fica}


def aplicar(a, db: str) -> int:
    from app import redir_site
    if not a.plano or not Path(a.plano).is_file():
        sys.exit("ERRO: --aplicar precisa de --plano <arquivo> gerado pela simulação (rode sem --aplicar primeiro).")
    plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
    if plano.get("tipo") != "consertar_mover_site":
        sys.exit("ERRO: este arquivo não é um plano de consertar mover site.")
    if str(Path(plano.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: o plano foi feito no banco {plano.get('banco')}, e este é {db}. Simule de novo neste banco.")
    con = ldf.abrir(db, escrita=False)
    falta = [t for t in ("site_registro_antigo", "item_retirado") if not _tem(con, t)]
    agora = analisar(con, plano["prefixos"]) if not falta else None
    con.close()
    if falta:
        sys.exit(f"ERRO: o banco não tem {', '.join(falta)} (migrações 220/222). Atualize o painel (./atualizar.sh) e simule de novo.")
    if carimbo(agora) != plano["carimbo"]:
        mud = sorted(set(agora) ^ set(plano["projetos"]) | {p for p in agora if p in plano["projetos"] and agora[p] != plano["projetos"][p]})
        print("RECUSADO: o banco mudou desde a simulação" + (f" nestes projetos: {', '.join(mud)}" if mud else "") + ".")
        print("Nada foi aplicado. Rode a simulação de novo, confira e aplique o plano novo.")
        return 3
    projs = plano["projetos"]
    if not projs:
        print("O plano não tem nada a aplicar.")
        return 0
    n_site = sum(len(x["site"]) for x in projs.values())
    if n_site and not ldf._mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: tirar do site usa a conexão do painel (CAMP_DB_PATH), e este banco é {db}. Nada foi aplicado.")
    copia = ldf._backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    arq = Path(a.plano).with_suffix(".desfazer.json")
    desf = {"tipo": "desfazer_consertar_mover_site", "banco": db, "plano": str(Path(a.plano).resolve()), "backup": copia,
            "aplicado_em": datetime.now().isoformat(timespec="seconds"), "projetos": {}}
    tot = {"fantasmas": 0, "privados": 0, "pendentes": 0, "redir": 0}
    avisos = []
    for proj, x in projs.items():
        # 1) rede primeiro (fora de transação): o registro antigo fica privado no site; o que falhar fica pendente para o painel repetir
        res = {}
        for e in x["site"]:
            try:
                ms._um(int(e["wp_id"]))
                res[e["wp_id"]] = None
            except Exception as err:  # noqa: BLE001
                res[e["wp_id"]] = str(err)[:300] or type(err).__name__
                avisos.append(f"{proj} item {e['wp_id']} ({e['de']}): o site não deixou privado ({res[e['wp_id']][:120]}); fica pendente e o painel tenta de novo")
        # 2) banco, numa transação
        con = ldf.abrir(db, escrita=True)
        reg = {"site": [], "tabela": [], "redir": [], "fantasmas": []}
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("PRAGMA defer_foreign_keys = ON")
            linhas = {int(e["wp_id"]): e for e in x["registrar"]}
            for e in x["site"]:
                linhas.setdefault(int(e["wp_id"]), {"wp_id": e["wp_id"], "de": e["de"], "para": e["para"]})
            for w, e in linhas.items():
                antes = con.execute("SELECT * FROM site_registro_antigo WHERE wp_id=?", (w,)).fetchone()
                erro = res.get(e["wp_id"], "nao_tentado") if any(int(s["wp_id"]) == w for s in x["site"]) else None
                escondido = (erro is None)                  # escondido agora, ou já estava privado no espelho
                con.execute("""INSERT INTO site_registro_antigo (wp_id, codigo_antigo, codigo_novo, motivo, ator, escondido_em, ultimo_erro)
                               VALUES (?,?,?,?,?,CASE WHEN ? THEN datetime('now') END,?)
                               ON CONFLICT(wp_id) DO UPDATE SET escondido_em=COALESCE(site_registro_antigo.escondido_em, excluded.escondido_em),
                                    ultimo_erro=excluded.ultimo_erro, proxima_em=NULL""",
                            (w, e["de"] or "", e["para"], MOTIVO_301, ATOR, 1 if escondido else 0, None if escondido else erro))
                reg["tabela"].append({"wp_id": w, "antes": dict(antes) if antes else None})
            for e in x["site"]:
                if res.get(e["wp_id"]) is None:
                    con.execute("UPDATE wp_item SET status='private' WHERE id=?", (int(e["wp_id"]),))
                    reg["site"].append({"wp_id": int(e["wp_id"]), "de": e["de"], "espelho": e["espelho"]})
                    tot["privados"] += 1
                else:
                    tot["pendentes"] += 1
            for e in x["redir"]:
                if not con.execute("SELECT 1 FROM redirecionamento WHERE codigo_antigo=?", (e["de"],)).fetchone():
                    redir_site.registrar(con, e["de"], e["para"], "item", MOTIVO_301, ATOR)
                    reg["redir"].append(e)
                    tot["redir"] += 1
            for e in x["fantasmas"]:
                if not con.execute("SELECT 1 FROM item WHERE codigo=? AND tainacan_item_id=?", (e["codigo"], e["wp_id"])).fetchone():
                    avisos.append(f"{proj} {e['codigo']}: não existe mais como estava (pulada)")
                    continue
                reg["fantasmas"].append(_retirar(con, e["codigo"], e["fica"], f"fantasma \"só no site\": {e['motivo']}", desf["plano"], {"wp_id": e["wp_id"]}))
                tot["fantasmas"] += 1
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "mover_site_consertado", ATOR, json.dumps({"fantasmas": len(reg["fantasmas"]), "privados": len(reg["site"]),
                                                                          "redir": len(reg["redir"]), "plano": desf["plano"], "backup": copia}, ensure_ascii=False)))
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        desf["projetos"][proj] = reg
        arq.write_text(json.dumps(desf, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"{proj}: {len(reg['fantasmas'])} fantasma(s) fora do painel · {len(reg['site'])} privado(s) no site · {len(reg['redir'])} 301 registrado(s)")
    print(f"\nFEITO: {tot['fantasmas']} folha(s) fantasma saíram do painel (lápide em item_retirado) · {tot['privados']} registro(s) antigo(s)"
          f" ficaram privados no site · {tot['pendentes']} pendente(s) (o painel tenta de novo sozinho) · {tot['redir']} 301 registrado(s)"
          " (o coletor de 10 min envia ao site).")
    for m in avisos:
        print(f"   {m}")
    print(f"Backup: {copia}")
    print(f"Para DESFAZER: PYTHONPATH=backend python scripts/consertar_mover_site.py --desfazer {arq}            (mostra)")
    print(f"               PYTHONPATH=backend python scripts/consertar_mover_site.py --desfazer {arq} --aplicar  (volta)")
    return 0


# ----------------------------------------------------------------- desfazer
def _inserir(con, tabela: str, linha: dict) -> None:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")]
    ks = [k for k in linha if k in cols]
    con.execute(f"INSERT OR REPLACE INTO {tabela} ({', '.join(ks)}) VALUES ({', '.join('?' * len(ks))})", [linha[k] for k in ks])


def desfazer(a, db: str) -> int:
    dados = json.loads(Path(a.desfazer).read_text(encoding="utf-8"))
    if dados.get("tipo") != "desfazer_consertar_mover_site":
        sys.exit("ERRO: este arquivo não é o de desfazer de consertar mover site.")
    if str(Path(dados.get("banco") or "").resolve()) != db:
        sys.exit(f"ERRO: o conserto foi feito no banco {dados.get('banco')}, e este é {db}.")
    con = ldf.abrir(db, escrita=False)
    volta, mudou = [], []
    for proj, reg in dados["projetos"].items():
        for f in reg["fantasmas"]:
            ok = con.execute("SELECT 1 FROM item_retirado WHERE codigo=?", (f["codigo"],)).fetchone() and \
                not con.execute("SELECT 1 FROM item WHERE codigo=?", (f["codigo"],)).fetchone()
            (volta if ok else mudou).append(f["codigo"])
    con.close()
    n_site = sum(len(r["site"]) for r in dados["projetos"].values())
    n_redir = sum(len(r["redir"]) for r in dados["projetos"].values())
    print(f"{'DESFAZENDO' if a.aplicar else 'SIMULAÇÃO do desfazer (nada é gravado)'}: {len(volta)} folha(s) fantasma voltam ao painel · "
          f"{n_site} registro(s) antigo(s) voltam a como estavam no site · {n_redir} 301 saem"
          + (f"; {len(mudou)} não voltam (já voltaram ou o código existe de novo): " + ", ".join(mudou) if mudou else ""))
    if not a.aplicar:
        print("Para desfazer de verdade, repita com --aplicar.")
        return 0
    if n_site and not ldf._mesmo_banco_do_painel(db):
        sys.exit(f"ERRO: voltar o site usa a conexão do painel (CAMP_DB_PATH), e este banco é {db}. Nada foi desfeito.")
    copia = ldf._backup(db)
    print(f"Backup do banco feito antes de mexer: {copia}")
    con = ldf.abrir(db, escrita=True)
    voltam = set(volta)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys = ON")
        for proj, reg in dados["projetos"].items():
            for f in reg["fantasmas"]:
                if f["codigo"] not in voltam:
                    continue
                t = con.execute("SELECT * FROM item_retirado WHERE codigo=?", (f["codigo"],)).fetchone()
                _inserir(con, "item", json.loads(t["linha"]))
                dep = json.loads(t["dependentes"] or "{}")
                for tabela, linhas in (dep.get("linhas") or {}).items():
                    for ln in linhas:
                        _inserir(con, tabela, ln)
                for x in (dep.get("reapontadas") or {}).get("duplicata_de") or []:
                    con.execute("UPDATE item SET duplicata_de=? WHERE codigo=? AND (duplicata_de=? OR duplicata_de IS NULL)", (f["codigo"], x, f["fica"]))
                for p in (dep.get("reapontadas") or {}).get("capa") or []:
                    con.execute("UPDATE projeto SET capa_item=? WHERE codigo=?", (f["codigo"], p))
                con.execute("DELETE FROM item_retirado WHERE codigo=?", (f["codigo"],))
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,?,?,?)",
                            (f["codigo"], "folha_devolvida", ATOR, json.dumps({"via": "desfazer de consertar mover site"}, ensure_ascii=False)))
            for e in reg["redir"]:
                con.execute("DELETE FROM redirecionamento WHERE codigo_antigo=? AND criado_por=?", (e["de"], ATOR))
            for t in reg["tabela"]:
                if t["antes"]:
                    _inserir(con, "site_registro_antigo", t["antes"])
                else:
                    con.execute("DELETE FROM site_registro_antigo WHERE wp_id=? AND ator=?", (t["wp_id"], ATOR))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                        (proj, "mover_site_conserto_desfeito", ATOR, json.dumps({"arquivo": str(Path(a.desfazer).resolve()), "backup": copia}, ensure_ascii=False)))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    avisos, rep = [], 0
    if n_site:
        from app import publicador
        for proj, reg in dados["projetos"].items():
            for s in reg["site"]:
                alvo = STATUS_VOLTA.get(s.get("espelho") or "")
                if not alvo:
                    avisos.append(f"item {s['wp_id']} ({s['de']}): não sei como estava (não estava no espelho); continua privado no site")
                    continue
                try:
                    publicador.WP().atualizar_status_item(publicador.COL_ACERVO, int(s["wp_id"]), alvo)
                except Exception as x:  # noqa: BLE001
                    avisos.append(f"item {s['wp_id']} ({s['de']}): o site não voltou a '{alvo}' ({str(x)[:160]}); continua privado")
                    continue
                c2 = ldf.abrir(db, escrita=True)
                try:
                    c2.execute("UPDATE wp_item SET status=? WHERE id=?", (s["espelho"], int(s["wp_id"])))
                    c2.commit()
                finally:
                    c2.close()
                rep += 1
    print(f"FEITO: {len(volta)} folha(s) voltaram ao painel · {rep} registro(s) antigo(s) voltaram a como estavam no site. Backup: {copia}")
    for m in avisos:
        print(f"   {m}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db")
    ap.add_argument("--fundo", help="só este fundo (ex.: F001); sem --fundo nem --projeto: todos")
    ap.add_argument("--projeto", action="append", help="só este(s) projeto(s) antigo(s) (de onde as folhas saíram)")
    ap.add_argument("--plano", help="simular: onde gravar o plano · aplicar: o plano a aplicar")
    ap.add_argument("--aplicar", action="store_true", help="aplica o --plano (ou, com --desfazer, desfaz de verdade)")
    ap.add_argument("--desfazer", help="arquivo .desfazer.json gravado ao aplicar")
    ap.add_argument("--listar", type=int, default=50, help="quantas linhas mostrar por tipo e projeto (padrão 50)")
    a = ap.parse_args()
    db = ldf.caminho_db(a)
    if a.desfazer:
        return desfazer(a, db)
    if a.aplicar:
        return aplicar(a, db)
    return simular(a, db)


if __name__ == "__main__":
    sys.exit(main())
