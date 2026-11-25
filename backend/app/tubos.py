"""Nome dos tubos no padrão TB001-01 (CAMP-ESTANTE, 25/11/2026).

Rafael: "TB001-01". Leitura adotada: TB + número do GRUPO de tubos (3 dígitos, sequência geral da CAMP, o próximo livre) + "-" + a PARTE
(2 dígitos). Um grupo = um conjunto de tubos de um lote/projeto; quando o mesmo lote não cabe num tubo só, o próximo tubo continua o
grupo (TB001-01, TB001-02…); outro projeto ganha um grupo novo (TB002-01). O padrão fica em `estante.padrao_tubo`
("TB{grupo:03d}-{parte:02d}") para mudar fácil se a leitura estiver errada.

- `opcoes(con, projeto)`: o que o "Guardar em…" oferece: continuar o grupo do projeto (se ele já tem tubo no padrão) e o grupo novo.
- `tubos_antigos` / `renomear_antigos`: os tubos criados no padrão anterior (TB-F035-P0001.1, do #219) viram o novo padrão, um grupo
  por projeto e as partes na ordem do volume. Simula por padrão; aplicar só renomeia o identificador (as folhas continuam no mesmo tubo)
  e registra no histórico do lugar. Etiqueta impressa antes precisa ser reimpressa (a resposta diz quais).
"""
from __future__ import annotations

import json
import re

PADRAO_PADRAO = "TB{grupo:03d}-{parte:02d}"
RE_ANTIGO = re.compile(r"^TB-(F\d{3}-P\d{4})\.(\d+)$")
RE_CAMPO = re.compile(r"\{(grupo|parte)(?::0?(\d+)d)?\}")


def padrao(con) -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='estante.padrao_tubo'").fetchone()
    p = (r[0] if r else "") or ""
    p = str(p).strip().upper().replace("{GRUPO", "{grupo").replace("{PARTE", "{parte").replace("D}", "d}")
    return p if ("{grupo" in p and "{parte" in p) else PADRAO_PADRAO


def formatar(p: str, grupo: int, parte: int) -> str:
    try:
        return p.format(grupo=grupo, parte=parte)
    except (KeyError, ValueError, IndexError):
        return PADRAO_PADRAO.format(grupo=grupo, parte=parte)


def regex(p: str) -> re.Pattern:
    """"TB{grupo:03d}-{parte:02d}" → ^TB(?P<grupo>\\d+)\\-(?P<parte>\\d+)$ (casa também números com mais dígitos: TB1000-01)."""
    partes, pos = [], 0
    for m in RE_CAMPO.finditer(p):
        partes.append(re.escape(p[pos:m.start()]))
        partes.append(f"(?P<{m.group(1)}>\\d+)")
        pos = m.end()
    partes.append(re.escape(p[pos:]))
    return re.compile("^" + "".join(partes) + "$", re.I)


def e_tubo(con, ident: str) -> bool:
    i = str(ident or "").strip().upper()
    return bool(regex(padrao(con)).match(i) or RE_ANTIGO.match(i))


def _no_padrao(con) -> list[tuple[int, int, int, str]]:
    """(id, grupo, parte, identificador) de cada tubo cujo nome segue o padrão."""
    rx = regex(padrao(con))
    out = []
    for r in con.execute("SELECT id, identificador FROM localizacao_fisica"):
        m = rx.match(str(r[1] or "").strip())
        if m:
            out.append((r[0], int(m.group("grupo")), int(m.group("parte")), r[1]))
    return out


def grupo_do_projeto(con, projeto: str, tubos: list | None = None) -> int | None:
    """O grupo mais recente com folhas deste projeto, ou criado para ele (histórico do lugar)."""
    tubos = _no_padrao(con) if tubos is None else tubos
    if not tubos:
        return None
    por_id = {t[0]: t for t in tubos}
    ids = set(r[0] for r in con.execute("""SELECT DISTINCT il.localizacao_id FROM item_localizacao il JOIN item i ON i.codigo=il.item_codigo
                                             WHERE i.projeto_codigo=?""", (projeto,)))
    for r in con.execute("SELECT codigo, detalhe FROM evento WHERE entidade='localizacao' AND tipo='criada'"):
        try:
            if json.loads(r[1] or "{}").get("projeto") == projeto:
                ids.add(int(r[0]))
        except (ValueError, TypeError):
            continue
    grupos = [por_id[i][1] for i in ids if i in por_id]
    return max(grupos) if grupos else None


def opcoes(con, projeto: str) -> dict:
    p = padrao(con)
    tubos = _no_padrao(con)
    g = grupo_do_projeto(con, projeto, tubos)
    novo_g = (max(t[1] for t in tubos) + 1) if tubos else 1
    continuar = None
    if g is not None:
        parte = max(t[2] for t in tubos if t[1] == g) + 1
        continuar = {"grupo": g, "parte": parte, "identificador": formatar(p, g, parte), "grupo_nome": formatar(p, g, 1).rsplit("-", 1)[0]}
    return {"padrao": p, "continuar": continuar,
            "novo_grupo": {"grupo": novo_g, "parte": 1, "identificador": formatar(p, novo_g, 1)}}


def proximo(con, projeto: str, modo: str = "") -> str:
    o = opcoes(con, projeto)
    if modo == "novo_grupo" or not o["continuar"]:
        return o["novo_grupo"]["identificador"]
    return o["continuar"]["identificador"]


def tubos_antigos(con) -> list[dict]:
    out = []
    for r in con.execute("SELECT id, identificador, fundo_codigo FROM localizacao_fisica ORDER BY id"):
        m = RE_ANTIGO.match(str(r[1] or "").strip().upper())
        if m:
            out.append({"id": r[0], "identificador": r[1], "projeto": m.group(1), "volume": int(m.group(2)), "fundo": r[2]})
    return out


def renomear_antigos(con, aplicar: bool, ator: str) -> dict:
    """Simula (padrão) ou aplica a troca dos nomes antigos. Um grupo novo por projeto, na ordem do primeiro tubo criado."""
    p = padrao(con)
    antigos = tubos_antigos(con)
    tubos = _no_padrao(con)
    prox = (max(t[1] for t in tubos) + 1) if tubos else 1
    usados = {str(r[0]).upper() for r in con.execute("SELECT identificador FROM localizacao_fisica")}
    por_proj: dict[str, list[dict]] = {}
    for a in antigos:
        por_proj.setdefault(a["projeto"], []).append(a)
    plano = []
    for proj in sorted(por_proj, key=lambda k: min(x["id"] for x in por_proj[k])):
        g = grupo_do_projeto(con, proj, tubos)
        if g is None:
            g, prox = prox, prox + 1
        parte = max([t[2] for t in tubos if t[1] == g] or [0])
        for a in sorted(por_proj[proj], key=lambda x: x["volume"]):
            parte += 1
            novo = formatar(p, g, parte)
            while novo.upper() in usados:
                parte += 1
                novo = formatar(p, g, parte)
            usados.add(novo.upper())
            n = con.execute("SELECT COUNT(*) FROM item_localizacao WHERE localizacao_id=?", (a["id"],)).fetchone()[0]
            impressa = con.execute("SELECT 1 FROM etiqueta_impressao WHERE upper(codigo)=upper(?) OR codigo=? LIMIT 1",
                                   (a["identificador"], str(a["id"]))).fetchone() is not None
            plano.append({"id": a["id"], "de": a["identificador"], "para": novo, "projeto": proj, "folhas": n, "reimprimir": impressa})
    if aplicar:
        for x in plano:
            con.execute("UPDATE localizacao_fisica SET identificador=? WHERE id=? AND identificador=?", (x["para"], x["id"], x["de"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'renomeada',?,?)",
                        (str(x["id"]), ator, json.dumps({"de": x["de"], "para": x["para"], "motivo": "tubos no padrão TB001-01"}, ensure_ascii=False)))
        con.commit()
    return {"simulacao": not aplicar, "padrao": p, "tubos": plano, "total": len(plano)}
