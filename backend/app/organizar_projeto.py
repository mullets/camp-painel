"""Organizar as folhas de um projeto do acervo: ordem pelo nome, PDF dos TIFF, .zip por categoria e onde cada folha está guardada.
(CAMP-PROJETO / CAMP-ESTANTE, 25/11/2026.) Rafael:
  "organizar automaticamente as folhas pelo nome, poder arrastar para organizar elas e poder exportar um pdf feito em cima dos tifs em alta
   qualidade, seleciono quais quero e exporto, ou escolho a categoria (desenho, fotos, estrutura) … ou se eu quiser um zip só com os tiffs"
  "preciso escolher quais vão em cada etiqueta, por exemplo um lote de estrutura total não cabe num tubo só, então vai em vários.. e
   preciso dizer quem tá em cada e quais faltam.."

Rotas (prefixo /api/projetos):
- GET  /{p}/ordem-folhas/por-nome     a ordem proposta pelo nome da folha (Folha 2 < 10 < 16A < 16B; sem número no fim). Não grava: a tela
                                       mostra a prévia e grava pela rota de sempre (PUT /ordem-folhas, que também leva a ordem ao site).
- GET  /{p}/categorias                as categorias das folhas: nos desenhos (S01/S08), a disciplina (#218: Arquitetura, Estrutura…); nas
                                       outras séries, o nome da série (Fotografias, Documentos textuais…). Com quantas têm TIFF.
- POST /{p}/exportar-pdf/estimar      o que vai entrar e o tamanho aproximado (mede os TIFF no QNAP com limite de tempo).
- POST /{p}/exportar-pdf?tarefa=1     monta o PDF em segundo plano (tarefas.iniciar): uma página por TIFF, sem perda (pdf_tiff).
- GET  /{p}/exportacoes               os PDFs ainda guardados; GET /{p}/exportacoes/{id}/arquivo baixa (apaga os vencidos ao listar).
- GET  /{p}/guardados                 onde estão as folhas: cada recipiente (tubo, caixa, mapoteca…) com as folhas DESTE projeto, e as que
                                       faltam guardar.
- POST /{p}/guardar-em                guarda as escolhidas num lugar que existe ou num tubo novo (TB-<projeto>.<n>, o próximo volume).
                                       Folha que já estava em outro lugar MUDA de lugar (é o pedido: dividir um lote em vários tubos), e a
                                       mudança fica no histórico de cada folha.
Papel: operador ou mais (o mesmo de baixar original e de guardar).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth
from .db import connect, settings

router = APIRouter(prefix="/api/projetos", tags=["organizar"])

_RE_PROJ = re.compile(r"^F\d{3}-P\d{4}$")
_RE_COD_FOLHA = re.compile(r"^\s*(folha\s+)?F\d{2,4}\s*-\s*[A-Z]\d{3,}", re.I)   # o mesmo RE_FOLHA_CODIGO da tela: "folha" que é um código
_RE_D = re.compile(r"^\s*D\d{4,}\s*$", re.I)                                     # "D00002": código, não nome
_PALAVRAS = re.compile(r"^(folha|fl|prancha|pr|desenho|des)\b\.?\s*", re.I)
MAX_PDF = 500
TIPOS_LOCAL = ("caixa", "gaveta", "tubo", "mapoteca", "estante")


def _projeto(con, codigo: str) -> dict:
    codigo = (codigo or "").upper()
    p = con.execute("SELECT codigo, titulo, fundo_codigo FROM projeto WHERE codigo=?", (codigo,)).fetchone() if _RE_PROJ.match(codigo) else None
    if not p:
        raise HTTPException(404, "Projeto não encontrado")
    return dict(p)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


# ---------------- 1. ordem pelo nome ----------------
def chave_nome(folha, codigo: str = "") -> tuple:
    """Chave da ordem natural pelo nome da folha. (grupo, partes, código):
    grupo 0 = começa com número ("16A", "5/6", '36 "A'); 1 = letra e número ("C-3F", "G07"); 2 = sem número (ou "folha" que é um código).
    Número compara como número (2 < 10); letras depois do número na ordem alfabética (16 < 16A < 16B)."""
    t = str(folha or "").strip()
    if not t or _RE_COD_FOLHA.match(t) or _RE_D.match(t):
        return (2, (), codigo)
    t = _PALAVRAS.sub("", _sem_acento(t).lower()).strip()
    partes = re.findall(r"\d+|[a-z]+", t)
    if not any(p.isdigit() for p in partes):
        return (2, tuple((1, p) for p in partes), codigo)
    grupo = 0 if partes and partes[0].isdigit() else 1
    return (grupo, tuple((0, int(p)) if p.isdigit() else (1, p) for p in partes), codigo)


def ordem_por_nome(itens: list[dict]) -> list[str]:
    """Códigos na ordem pelo nome. Cópias (duplicata) e retidas ficam no fim, na ordem em que estavam."""
    fim = [i for i in itens if i.get("duplicata_de") or i.get("retida")]
    meio = [i for i in itens if not (i.get("duplicata_de") or i.get("retida"))]
    return [i["codigo"] for i in sorted(meio, key=lambda i: chave_nome(i.get("folha"), i["codigo"]))] + [i["codigo"] for i in fim]


@router.get("/{codigo}/ordem-folhas/por-nome")
def proposta_por_nome(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    from .rotas_projetos import ORDEM_FOLHAS_SQL
    con = connect()
    try:
        p = _projeto(con, codigo)
        atual = [r[0] for r in con.execute(ORDEM_FOLHAS_SQL, (p["codigo"],))]
        info = {r["codigo"]: dict(r) for r in con.execute("""SELECT codigo, folha, titulo, duplicata_de, COALESCE(retida,0) AS retida,
                                                                    serie_codigo FROM item WHERE projeto_codigo=?""", (p["codigo"],))}
        tem_manual = bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND ordem_manual IS NOT NULL LIMIT 1", (p["codigo"],)).fetchone())
        no_site = bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL LIMIT 1",
                                   (p["codigo"],)).fetchone())
    finally:
        con.close()
    nova = ordem_por_nome([info[c] for c in atual if c in info])
    pos = {c: k for k, c in enumerate(atual)}
    mudam = sum(1 for k, c in enumerate(nova) if pos.get(c) != k)
    sem_numero = [c for c in nova if chave_nome(info[c].get("folha"), c)[0] == 2 and not info[c].get("duplicata_de")]
    return {"projeto": p["codigo"], "ordem": nova, "mudam_de_lugar": mudam, "tinha_ordem_manual": tem_manual, "vai_ao_site": no_site,
            "sem_numero": sem_numero,
            "lista": [{"codigo": c, "folha": info[c].get("folha") or "", "de": pos.get(c, 0) + 1, "para": k + 1} for k, c in enumerate(nova)]}


# ---------------- 2. categorias (disciplina nos desenhos, série nas outras) ----------------
def _series(con) -> dict:
    try:
        return {r[0]: r[1] for r in con.execute("SELECT codigo, nome FROM serie")}
    except Exception:  # noqa: BLE001
        return {}


def categorias_do_projeto(con, projeto: str) -> list[dict]:
    from .parceiros import SERIES_DESENHO, disciplina_grupo, ordem_disciplina
    nomes = _series(con)
    grupos: dict[str, dict] = {}
    for r in con.execute("""SELECT codigo, serie_codigo, parceiros, tipo_documento, tipos_documento, tipo_lido, arquivo_tif, folha, ordem_manual,
                                   sequencial FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL
                             ORDER BY (ordem_manual IS NULL), ordem_manual, serie_codigo, sequencial, codigo""", (projeto,)):
        if r["serie_codigo"] in SERIES_DESENHO:
            d, esc = disciplina_grupo(r["parceiros"], r["tipo_documento"], r["tipos_documento"], r["tipo_lido"])
            chave, rotulo, ordem = "disc:" + d, d, (0,) + ordem_disciplina(d)
        else:
            s = r["serie_codigo"] or "SEM_SERIE"
            chave, rotulo, ordem, esc = "serie:" + s, nomes.get(s) or ("Sem série" if s == "SEM_SERIE" else s), (1, s), None
        g = grupos.setdefault(chave, {"chave": chave, "rotulo": rotulo, "escritorio": esc, "folhas": [], "com_tif": 0, "_ordem": ordem})
        g["folhas"].append(r["codigo"])
        g["com_tif"] += 1 if r["arquivo_tif"] else 0
        if esc and not g["escritorio"]:
            g["escritorio"] = esc
    out = sorted(grupos.values(), key=lambda g: g["_ordem"])
    for g in out:
        g.pop("_ordem")
    return out


@router.get("/{codigo}/categorias")
def categorias(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        p = _projeto(con, codigo)
        cats = categorias_do_projeto(con, p["codigo"])
        total = con.execute("SELECT COUNT(*), SUM(arquivo_tif IS NOT NULL AND arquivo_tif<>'') FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL",
                            (p["codigo"],)).fetchone()
    finally:
        con.close()
    return {"projeto": p["codigo"], "categorias": cats, "total": total[0] or 0, "com_tif": total[1] or 0}


def resolver_folhas(con, projeto: str, folhas: list[str] | None, categoria: str | None, todas: bool) -> tuple[list[str], str]:
    """(códigos na ordem da grade, rótulo). Exatamente um: folhas escolhidas, uma categoria ou o projeto inteiro."""
    ordem = [r[0] for r in con.execute("""SELECT codigo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL
                                           ORDER BY (ordem_manual IS NULL), ordem_manual, serie_codigo, sequencial, codigo""", (projeto,))]
    if folhas:
        pedidas = {str(c).strip().upper() for c in folhas if str(c).strip()}
        fora = sorted(pedidas - set(ordem))
        if fora:
            raise HTTPException(400, f"{'Estas folhas não são' if len(fora) > 1 else 'Esta folha não é'} deste projeto: {', '.join(fora[:5])}")
        sel = [c for c in ordem if c in pedidas]
        return sel, f"{len(sel)} folha{'s' if len(sel) != 1 else ''} escolhida{'s' if len(sel) != 1 else ''}"
    if categoria:
        g = next((g for g in categorias_do_projeto(con, projeto) if g["chave"] == categoria), None)
        if not g:
            raise HTTPException(400, "Essa categoria não existe neste projeto")
        return g["folhas"], g["rotulo"]
    if todas:
        return ordem, "Projeto inteiro"
    raise HTTPException(400, "Escolha as folhas, uma categoria ou o projeto inteiro")


# ---------------- 3. PDF dos TIFF ----------------
class PedidoPDF(BaseModel):
    folhas: list[str] = []
    categoria: str | None = None
    todas: bool = False
    capa: bool = True
    usar_jpg: bool = False          # sem TIFF: usar o JPG em resolução original (se houver)


def pasta_exportacoes() -> Path:
    p = Path(os.environ.get("CAMP_EXPORTACOES_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "exportacoes_pdf")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _validade(con) -> int:
    from .entrega import _cfg
    try:
        return max(1, min(90, int(_cfg(con, "exportacao_pdf.validade_dias", "7"))))
    except ValueError:
        return 7


def _arquivo_folha(con, item, usar_jpg: bool) -> tuple[Path | None, str, str]:
    """(arquivo, formato, motivo). Só TIFF por padrão; JPG original só com usar_jpg. Sempre dentro das raízes permitidas, nunca lixeira."""
    from .originais import _arquivo
    t = _arquivo(con, item, "tif") if item["arquivo_tif"] else None
    if t:
        return t, "TIFF", ""
    if usar_jpg:
        j = _arquivo(con, item, "jpg_original")
        if j:
            return j, "JPG original", ""
        return None, "", "sem TIFF e sem JPG original no QNAP"
    return None, "", "sem TIFF registrado" if not item["arquivo_tif"] else "o TIFF não foi achado no QNAP"


def limpar_vencidas(con) -> int:
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    base, n = pasta_exportacoes(), 0
    for r in con.execute("SELECT id, arquivo FROM exportacao_pdf WHERE apagado_em IS NULL AND expira_em < ?", (agora,)).fetchall():
        alvo = base / Path(r["arquivo"]).name
        try:
            alvo.unlink(missing_ok=True)
        except OSError:
            continue
        con.execute("UPDATE exportacao_pdf SET apagado_em=datetime('now') WHERE id=?", (r["id"],))
        n += 1
    if n:
        con.commit()
    return n


@router.post("/{codigo}/exportar-pdf/estimar")
def estimar_pdf(codigo: str, d: PedidoPDF, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Quantas páginas e o tamanho aproximado (soma dos TIFF: o PDF sem perda fica parecido, às vezes maior). Mede no QNAP com limite de
    3 s: passou disso, a estimativa é parcial e a tela diz."""
    con = connect()
    try:
        p = _projeto(con, codigo)
        cods, rotulo = resolver_folhas(con, p["codigo"], d.folhas, d.categoria, d.todas)
        itens = {r["codigo"]: r for r in con.execute(f"SELECT * FROM item WHERE codigo IN ({','.join('?' * len(cods))})", cods)} if cods else {}
        com, sem, medidos, total_b, t0 = [], [], 0, 0, time.monotonic()
        parcial = False
        for c in cods:
            it = itens[c]
            if time.monotonic() - t0 > 3:
                parcial = True
                if it["arquivo_tif"] or d.usar_jpg:
                    com.append(c)
                else:
                    sem.append({"codigo": c, "motivo": "sem TIFF registrado"})
                continue
            arq, fmt, motivo = _arquivo_folha(con, it, d.usar_jpg)
            if arq:
                com.append(c)
                try:
                    total_b += arq.stat().st_size
                    medidos += 1
                except OSError:
                    pass
            else:
                sem.append({"codigo": c, "motivo": motivo})
    finally:
        con.close()
    est = int(total_b / medidos * len(com)) if medidos else 0
    return {"projeto": p["codigo"], "rotulo": rotulo, "paginas": len(com) + (1 if d.capa and com else 0), "folhas": com, "puladas": sem,
            "bytes_estimados": est, "parcial": parcial, "max": MAX_PDF}


def montar_pdf(projeto: str, cods: list[str], rotulo: str, capa: bool, usar_jpg: bool, ator: str, progresso=None) -> dict:
    """Monta o PDF (chamado na thread da tarefa). Nada do QNAP é alterado; o PDF vai para exportacoes_pdf/."""
    from .pdf_tiff import EscritorPDF
    con = connect()
    try:
        p = con.execute("SELECT codigo, titulo, fundo_codigo FROM projeto WHERE codigo=?", (projeto,)).fetchone()
        fundo = con.execute("SELECT titulo FROM fundo WHERE codigo=?", (p["fundo_codigo"],)).fetchone() if p else None
        itens = {r["codigo"]: r for r in con.execute(f"SELECT * FROM item WHERE codigo IN ({','.join('?' * len(cods))})", cods)}
        planos, puladas = [], []
        for c in cods:
            arq, fmt, motivo = _arquivo_folha(con, itens[c], usar_jpg)
            if arq:
                planos.append((c, arq, fmt, itens[c]["folha"] or ""))
            else:
                puladas.append({"codigo": c, "motivo": motivo})
        validade = _validade(con)
        limpar_vencidas(con)
    finally:
        con.close()
    if not planos:
        return {"ok": False, "mensagem": "Nenhuma das folhas tem TIFF no QNAP: nada para montar.", "puladas": puladas}
    if progresso:
        progresso.total(len(planos))
        progresso.passo("Montando o PDF a partir dos TIFF")
    nome = f"{projeto}-{re.sub(r'[^A-Za-z0-9]+', '-', _sem_acento(rotulo)).strip('-')[:40] or 'folhas'}-{secrets.token_hex(4)}.pdf"
    destino = pasta_exportacoes() / nome
    w = EscritorPDF(destino)
    notas = []
    try:
        if capa:
            linhas = [(20, (p["titulo"] or projeto) if p else projeto), (11, f"{projeto} · {fundo['titulo'] if fundo else ''}".strip(" ·")),
                      (11, f"{rotulo} · {len(planos)} página{'s' if len(planos) != 1 else ''} · a partir dos arquivos originais (sem perda)"),
                      (9, f"Gerado pelo painel da CAMP em {datetime.now().strftime('%d/%m/%Y %H:%M')}"), (9, "")]
            linhas += [(9, f"{k:>3}. {c}  {f}") for k, (c, _a, _f, f) in enumerate(planos, 1)]
            if puladas:
                linhas += [(9, ""), (9, f"Fora deste PDF ({len(puladas)}):")] + [(9, f"     {x['codigo']}: {x['motivo']}") for x in puladas]
            w.capa(linhas)
        for c, arq, fmt, _f in planos:
            if progresso:
                progresso.passo("Montando o PDF a partir dos TIFF", c)
            try:
                r = w.imagem(arq)
            except Exception as e:  # noqa: BLE001  (arquivo corrompido: a folha sai, o resto continua)
                puladas.append({"codigo": c, "motivo": f"não deu para ler o arquivo ({str(e)[:80]})"})
                continue
            if r["nota"]:
                notas.append(f"{c}: {r['nota']}")
            if fmt != "TIFF":
                notas.append(f"{c}: sem TIFF, entrou o {fmt}")
            if progresso:
                progresso.feita(1)
        tam = w.fechar(f"{(p['titulo'] if p else '') or projeto} · {rotulo}")
    except Exception:
        w.abortar()
        destino.unlink(missing_ok=True)
        raise
    paginas = len(planos) - sum(1 for x in puladas if x["motivo"].startswith("não deu"))
    expira = (datetime.now(timezone.utc) + timedelta(days=validade)).strftime("%Y-%m-%d %H:%M:%S")
    con = connect()
    try:
        eid = con.execute("""INSERT INTO exportacao_pdf (projeto_codigo, arquivo, rotulo, folhas, puladas, paginas, bytes, ator, expira_em)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                          (projeto, nome, rotulo, json.dumps([c for c, *_ in planos]), json.dumps(puladas, ensure_ascii=False), paginas, tam, ator, expira)).lastrowid
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'pdf_exportado',?,?)",
                    (projeto, ator, json.dumps({"exportacao": eid, "rotulo": rotulo, "paginas": paginas, "bytes": tam, "puladas": len(puladas)},
                                               ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    msg = f"PDF pronto: {paginas} página{'s' if paginas != 1 else ''} ({_fmt_b(tam)})" + (f"; {len(puladas)} folha(s) ficaram de fora" if puladas else "")
    return {"ok": True, "mensagem": msg, "exportacao_id": eid, "arquivo": f"/api/projetos/{projeto}/exportacoes/{eid}/arquivo",
            "paginas": paginas, "bytes": tam, "puladas": puladas, "notas": notas[:50], "expira_em": expira}


def _fmt_b(n: int) -> str:
    for u_, d in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return f"{n / d:.1f} {u_}".replace(".", ",")
    return f"{n} bytes"


@router.post("/{codigo}/exportar-pdf")
def exportar_pdf(codigo: str, d: PedidoPDF, tarefa: int = 0, u: dict = Depends(auth.exige("operador"))):
    from . import tarefas
    con = connect()
    try:
        p = _projeto(con, codigo)
        cods, rotulo = resolver_folhas(con, p["codigo"], d.folhas, d.categoria, d.todas)
    finally:
        con.close()
    if not cods:
        raise HTTPException(400, "Nenhuma folha para exportar")
    if len(cods) > MAX_PDF:
        raise HTTPException(400, f"No máximo {MAX_PDF} folhas por PDF: escolha uma categoria ou parte das folhas")
    if not tarefa:
        return montar_pdf(p["codigo"], cods, rotulo, d.capa, d.usar_jpg, u["email"])
    return tarefas.iniciar("exportar_pdf", p["codigo"], u, lambda pr: montar_pdf(p["codigo"], cods, rotulo, d.capa, d.usar_jpg, u["email"], pr),
                           titulo=f"Exportar PDF · {rotulo}")


@router.get("/{codigo}/exportacoes")
def exportacoes(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        p = _projeto(con, codigo)
        limpar_vencidas(con)
        rows = con.execute("""SELECT id, rotulo, paginas, bytes, ator, criado_em, expira_em, puladas FROM exportacao_pdf
                               WHERE projeto_codigo=? AND apagado_em IS NULL ORDER BY id DESC LIMIT 20""", (p["codigo"],)).fetchall()
    finally:
        con.close()
    return {"exportacoes": [{**{k: r[k] for k in ("id", "rotulo", "paginas", "bytes", "ator", "criado_em", "expira_em")},
                             "puladas": len(json.loads(r["puladas"] or "[]")), "arquivo": f"/api/projetos/{p['codigo']}/exportacoes/{r['id']}/arquivo"}
                            for r in rows]}


@router.get("/{codigo}/exportacoes/{eid}/arquivo")
def baixar_exportacao(codigo: str, eid: int, u: dict = Depends(auth.exige("operador"))):
    con = connect()
    try:
        p = _projeto(con, codigo)
        r = con.execute("SELECT arquivo, rotulo FROM exportacao_pdf WHERE id=? AND projeto_codigo=? AND apagado_em IS NULL", (eid, p["codigo"])).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(404, "Esse PDF não existe mais (venceu ou foi apagado). Exporte de novo.")
    alvo = (pasta_exportacoes() / Path(r["arquivo"]).name).resolve()
    if alvo.parent != pasta_exportacoes().resolve() or not alvo.is_file():
        raise HTTPException(404, "Esse PDF não existe mais (venceu ou foi apagado). Exporte de novo.")
    return FileResponse(alvo, media_type="application/pdf", filename=f"{p['codigo']}-{r['rotulo'] or 'folhas'}.pdf",
                        headers={"Cache-Control": "no-store"})


# ---------------- 4. onde estão as folhas (tubos, caixas…) ----------------
def guardados_do_projeto(con, projeto: str) -> dict:
    folhas = [dict(r) for r in con.execute("""SELECT i.codigo, i.folha, i.titulo, i.serie_codigo, il.localizacao_id
                                                FROM item i LEFT JOIN item_localizacao il ON il.item_codigo=i.codigo
                                               WHERE i.projeto_codigo=? AND i.duplicata_de IS NULL
                                               ORDER BY (i.ordem_manual IS NULL), i.ordem_manual, i.serie_codigo, i.sequencial, i.codigo""", (projeto,))]
    ids = sorted({f["localizacao_id"] for f in folhas if f["localizacao_id"]})
    locs = {r["id"]: dict(r) for r in con.execute(
        f"""SELECT l.id, l.identificador, l.tipo, l.fundo_codigo, l.descricao,
                   (SELECT COUNT(*) FROM item_localizacao x JOIN item i2 ON i2.codigo=x.item_codigo
                     WHERE x.localizacao_id=l.id AND i2.projeto_codigo<>?) AS de_outros
              FROM localizacao_fisica l WHERE l.id IN ({','.join('?' * len(ids)) or 'NULL'})""", (projeto, *ids))}
    recip = []
    for lid in ids:
        l = locs.get(lid)
        if not l:
            continue
        fs = [{"codigo": f["codigo"], "folha": f["folha"] or ""} for f in folhas if f["localizacao_id"] == lid]
        recip.append({**l, "folhas": fs, "quantidade": len(fs)})
    recip.sort(key=lambda l: (TIPOS_LOCAL.index(l["tipo"]) if l["tipo"] in TIPOS_LOCAL else 9, _nat(l["identificador"])))
    faltam = [{"codigo": f["codigo"], "folha": f["folha"] or ""} for f in folhas if not f["localizacao_id"]]
    return {"projeto": projeto, "total": len(folhas), "guardadas": len(folhas) - len(faltam), "recipientes": recip, "faltam": faltam,
            "proximo_tubo": proximo_tubo(con, projeto)}


def _nat(t: str) -> tuple:
    return tuple((0, int(x)) if x.isdigit() else (1, x) for x in re.findall(r"\d+|\D+", str(t or "")))


def proximo_tubo(con, projeto: str) -> str:
    """TB-<projeto>.<n>: o próximo volume livre (TB-F035-P0001.1, .2…). O prefixo TB- faz o leitor de etiqueta achar o TUBO (não o projeto)."""
    base = f"TB-{projeto}."
    usados = [int(r[0][len(base):]) for r in con.execute("SELECT identificador FROM localizacao_fisica WHERE upper(identificador) LIKE ?", (base + "%",))
              if r[0][len(base):].isdigit()]
    return f"{base}{(max(usados) + 1) if usados else 1}"


@router.get("/{codigo}/guardados")
def guardados(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        p = _projeto(con, codigo)
        return guardados_do_projeto(con, p["codigo"])
    finally:
        con.close()


class GuardarEm(BaseModel):
    itens: list[str]
    localizacao_id: int | None = None
    novo_tubo: bool = False
    descricao: str | None = None


@router.post("/{codigo}/guardar-em")
def guardar_em(codigo: str, d: GuardarEm, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        p = _projeto(con, codigo)
        pedidas = list(dict.fromkeys(str(c).strip().upper() for c in d.itens if str(c).strip()))
        if not pedidas:
            raise HTTPException(400, "Escolha as folhas")
        do_proj = {r[0]: r[1] for r in con.execute("""SELECT i.codigo, il.localizacao_id FROM item i LEFT JOIN item_localizacao il ON il.item_codigo=i.codigo
                                                       WHERE i.projeto_codigo=?""", (p["codigo"],))}
        fora = [c for c in pedidas if c not in do_proj]
        if fora:
            raise HTTPException(400, f"{'Estas folhas não são' if len(fora) > 1 else 'Esta folha não é'} deste projeto: {', '.join(fora[:5])}. Nada foi guardado.")
        criada = False
        if d.novo_tubo:
            ident = proximo_tubo(con, p["codigo"])
            desc = (d.descricao or "").strip()[:120] or None
            lid = con.execute("INSERT INTO localizacao_fisica (fundo_codigo, tipo, identificador, descricao) VALUES (?,?,?,?)",
                              (p["fundo_codigo"], "tubo", ident, desc)).lastrowid
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'criada',?,?)",
                        (str(lid), u["email"], json.dumps({"identificador": ident, "fundo": p["fundo_codigo"], "projeto": p["codigo"]}, ensure_ascii=False)))
            tipo, criada = "tubo", True
        else:
            l = con.execute("SELECT id, identificador, tipo FROM localizacao_fisica WHERE id=?", (d.localizacao_id or 0,)).fetchone()
            if not l:
                raise HTTPException(404, "Esse lugar não existe. Escolha outro ou crie um tubo novo.")
            lid, ident, tipo = l["id"], l["identificador"], l["tipo"]
        nomes = {r[0]: r[1] for r in con.execute("SELECT id, identificador FROM localizacao_fisica")}
        novas, movidas, ja = 0, 0, 0
        for c in pedidas:
            antes = do_proj.get(c)
            if antes == lid:
                ja += 1
                continue
            con.execute("INSERT OR REPLACE INTO item_localizacao (item_codigo, localizacao_id) VALUES (?,?)", (c, lid))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'guardada',?,?)",
                        (c, u["email"], json.dumps({"de": nomes.get(antes) if antes else None, "para": ident, "localizacao_id": lid}, ensure_ascii=False)))
            if antes:
                movidas += 1
            else:
                novas += 1
        if novas or movidas:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'alocacao',?,?)",
                        (str(lid), u["email"], json.dumps({"itens": novas + movidas, "projeto": p["codigo"], "mudaram_de_lugar": movidas}, ensure_ascii=False)))
        con.commit()
        r = guardados_do_projeto(con, p["codigo"])
    finally:
        con.close()
    partes = []
    if novas:
        partes.append(f"{novas} folha{'s' if novas != 1 else ''} guardada{'s' if novas != 1 else ''} em {ident}")
    if movidas:
        partes.append(f"{movidas} mudou de lugar para {ident}" if movidas == 1 else f"{movidas} mudaram de lugar para {ident}")
    if ja:
        partes.append(f"{ja} já estava{'m' if ja != 1 else ''} em {ident}")
    msg = "; ".join(partes) + (f" ({ident} foi criado)" if criada else "")
    if r["faltam"]:
        msg += f". Faltam guardar {len(r['faltam'])}."
    return {"ok": True, "localizacao_id": lid, "identificador": ident, "tipo": tipo, "criada": criada, "guardadas": novas, "movidas": movidas,
            "ja_estavam": ja, "mensagem": msg, "guardados": r}
