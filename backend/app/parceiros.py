"""Escritórios parceiros / projetos complementares da folha (19/10/2026).

Pedido: "na descrição dos documentos, espaço para identificação de escritórios parceiros no desenvolvimento de projetos,
principalmente consultoria / projetos complementares (engenharia, instalações, paisagismo etc.)".

- Guardado em item.parceiros (JSON, migração 138): [{"escritorio": "...", "disciplina": "Estrutura"}, ...]; NULL = nenhum.
- Disciplina: uma da lista fixa (DISCIPLINAS) ou "Outra" com o texto (guardado como o próprio texto).
- Gravado pelo PATCH /api/itens/{c} (operador+), com antes/depois no histórico (evento 'editado').
- Sugestões de nomes já usados (do fundo primeiro): GET /api/parceiros/sugestoes.
- Copiar para outras folhas: POST /api/itens/{c}/parceiros/copiar (pendentes do lote, o lote, o projeto ou as escolhidas).
- Site: NÃO se cria metadado. Se a coleção do site já tiver um metadado de texto com um dos NOMES_NO_SITE, a publicação da folha
  envia "Escritório (Disciplina); ..." para ele; senão os parceiros ficam só no painel (e na exportação EAD).
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["parceiros"])

DISCIPLINAS = ("Estrutura", "Fundações", "Instalações elétricas", "Instalações hidráulicas", "Ar-condicionado/climatização",
               "Luminotécnica", "Acústica", "Paisagismo", "Interiores", "Comunicação visual", "Engenharia (geral)", "Consultoria", "Outra")
LIM_ESCRITORIO = 200
LIM_DISCIPLINA = 80
MAX_PARCEIROS = 30
# metadados que o site PODE já ter para isso (procura por nome, sem diferenciar maiúsculas); o painel nunca cria metadado no site
NOMES_NO_SITE = ("Escritórios parceiros", "Projetos complementares", "Parceiros", "Consultores", "Colaboradores", "Colaborador")


def _limpo(v) -> str:
    return " ".join(str(v or "").split())


def ler(texto) -> list[dict]:
    """item.parceiros (texto JSON) -> lista; qualquer coisa estranha vira lista vazia (nunca derruba a tela)."""
    if not texto:
        return []
    try:
        v = json.loads(texto) if isinstance(texto, str) else texto
    except ValueError:
        return []
    out = []
    for p in v if isinstance(v, list) else []:
        if isinstance(p, dict) and _limpo(p.get("escritorio")):
            out.append({"escritorio": _limpo(p.get("escritorio")), "disciplina": _limpo(p.get("disciplina"))})
    return out


def normalizar(lista) -> list[dict]:
    """Valida o que veio da tela. Cada linha: {"escritorio", "disciplina", "outra"?}. Linha totalmente vazia é ignorada;
    repetida (mesmo escritório e disciplina) entra uma vez. Erro -> HTTPException 400 com a mensagem para a pessoa."""
    if lista is None:
        return []
    if not isinstance(lista, list):
        raise HTTPException(400, "Escritórios parceiros: formato inválido (esperada uma lista)")
    fixas = {d.casefold(): d for d in DISCIPLINAS}
    out, vistos = [], set()
    for p in lista:
        if not isinstance(p, dict):
            raise HTTPException(400, "Escritórios parceiros: cada linha precisa de escritório e disciplina")
        esc, dis, outra = _limpo(p.get("escritorio")), _limpo(p.get("disciplina")), _limpo(p.get("outra"))
        if not esc and not dis and not outra:
            continue
        if not esc:
            raise HTTPException(400, f"Escritórios parceiros: falta o nome do escritório na linha de {outra or dis}")
        if len(esc) > LIM_ESCRITORIO:
            raise HTTPException(400, f"Escritórios parceiros: nome com mais de {LIM_ESCRITORIO} caracteres ({esc[:40]}…)")
        if not dis:
            raise HTTPException(400, f"Escritórios parceiros: escolha a disciplina de {esc}")
        d = fixas.get(dis.casefold())
        if d == "Outra":
            if not outra:
                raise HTTPException(400, f"Escritórios parceiros: escreva qual é a outra disciplina de {esc}")
            d = outra
        elif d is None:
            raise HTTPException(400, f"Escritórios parceiros: disciplina '{dis}' não está na lista (use Outra e escreva qual)")
        if len(d) > LIM_DISCIPLINA:
            raise HTTPException(400, f"Escritórios parceiros: disciplina com mais de {LIM_DISCIPLINA} caracteres")
        chave = (esc.casefold(), d.casefold())
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append({"escritorio": esc, "disciplina": d})
    if len(out) > MAX_PARCEIROS:
        raise HTTPException(400, f"Escritórios parceiros: no máximo {MAX_PARCEIROS} por folha")
    return out


def para_coluna(lista: list[dict]) -> str | None:
    return json.dumps(lista, ensure_ascii=False) if lista else None


def juntar(atual: list[dict], novos: list[dict]) -> list[dict]:
    out, vistos = [], set()
    for p in [*atual, *novos]:
        k = (p["escritorio"].casefold(), p["disciplina"].casefold())
        if k not in vistos:
            vistos.add(k); out.append(p)
    return out


def texto(lista: list[dict]) -> str:
    """"Escritório A (Estrutura); Escritório B (Paisagismo)" — o que vai ao site e à leitura."""
    return "; ".join(f"{p['escritorio']} ({p['disciplina']})" if p.get("disciplina") else p["escritorio"] for p in lista)


def metadado_no_site(con, colecao_id: int):
    """(id, nome) do metadado de TEXTO que a coleção do site já tem para parceiros, pelo espelho (wp_metadado); senão (None, None).
    Taxonomia/relação ficam de fora: o painel não cria termo nem item no site para isso."""
    for nome in NOMES_NO_SITE:
        r = con.execute("SELECT id, nome, tipo FROM wp_metadado WHERE colecao_id=? AND lower(nome)=lower(?)", (colecao_id, nome)).fetchone()
        if r and not any(t in (r["tipo"] or "") for t in ("Taxonomy", "Relationship", "Compound")):
            return r["id"], r["nome"]
    return None, None


def resumo_projeto(con, projeto: str) -> list[dict]:
    """Parceiros distintos das folhas do projeto: [{escritorio, disciplinas[], folhas}], mais folhas primeiro."""
    acc: dict = {}
    for (txt,) in con.execute("SELECT parceiros FROM item WHERE projeto_codigo=? AND parceiros IS NOT NULL AND duplicata_de IS NULL", (projeto,)):
        vistos = set()
        for p in ler(txt):
            k = p["escritorio"].casefold()
            a = acc.setdefault(k, {"escritorio": p["escritorio"], "disciplinas": [], "folhas": 0})
            if p["disciplina"] and p["disciplina"] not in a["disciplinas"]:
                a["disciplinas"].append(p["disciplina"])
            if k not in vistos:
                vistos.add(k); a["folhas"] += 1
    return sorted(acc.values(), key=lambda x: (-x["folhas"], x["escritorio"].casefold()))


@router.get("/parceiros/sugestoes")
def sugestoes(fundo: str | None = None, q: str | None = None, limite: int = 100, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Nomes de escritórios já usados no painel, para o autocompletar. Os do fundo indicado vêm primeiro; depois os demais.
    Leve: só lê a coluna parceiros das folhas que têm algum."""
    limite = max(1, min(int(limite or 100), 300))
    termo = _limpo(q).casefold()
    con = connect()
    try:
        acc: dict = {}
        for r in con.execute("""SELECT i.parceiros, p.fundo_codigo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
                                 WHERE i.parceiros IS NOT NULL AND i.parceiros<>''"""):
            for x in ler(r["parceiros"]):
                k = x["escritorio"].casefold()
                if termo and termo not in k:
                    continue
                a = acc.setdefault(k, {"nome": x["escritorio"], "disciplinas": [], "folhas": 0, "do_fundo": False})
                a["folhas"] += 1
                if x["disciplina"] and x["disciplina"] not in a["disciplinas"]:
                    a["disciplinas"].append(x["disciplina"])
                if fundo and r["fundo_codigo"] == fundo:
                    a["do_fundo"] = True
        nomes = sorted(acc.values(), key=lambda a: (not a["do_fundo"], -a["folhas"], a["nome"].casefold()))[:limite]
        return {"nomes": nomes, "disciplinas": list(DISCIPLINAS)}
    finally:
        con.close()


@router.get("/itens/{codigo}/parceiros/folhas")
def folhas_para_copiar(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """As outras folhas do projeto (para escolher onde copiar): código, título, tipo, lote, revisão e quantos parceiros já têm."""
    con = connect()
    try:
        i = con.execute("SELECT codigo, projeto_codigo, lote_id, parceiros FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        folhas = [{"codigo": r["codigo"], "titulo": r["titulo"], "tipo": r["tipo"], "lote_id": r["lote_id"], "revisao": r["revisao"],
                   "mesmo_lote": bool(i["lote_id"]) and r["lote_id"] == i["lote_id"], "parceiros": len(ler(r["parceiros"]))}
                  for r in con.execute("""SELECT codigo, titulo, COALESCE(tipos_documento, tipo_documento) AS tipo, lote_id, revisao, parceiros
                                            FROM item WHERE projeto_codigo=? AND codigo<>? AND duplicata_de IS NULL
                                           ORDER BY serie_codigo, sequencial""", (i["projeto_codigo"], codigo))]
        return {"origem": codigo, "parceiros": ler(i["parceiros"]), "lote_id": i["lote_id"], "folhas": folhas}
    finally:
        con.close()


class CopiarParceiros(BaseModel):
    alvo: str = "itens"            # itens | lote_pendentes | lote | projeto
    itens: list[str] | None = None
    modo: str = "acrescentar"      # acrescentar (padrão: não apaga o que a outra folha já tem) | substituir


@router.post("/itens/{codigo}/parceiros/copiar")
def copiar(codigo: str, d: CopiarParceiros, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Aplica os parceiros SALVOS desta folha a outras do mesmo projeto (o mesmo calculista em todas as pranchas de estrutura).
    Como o consenso do lote: a resposta diz quais mudaram e quais ficaram de fora (com o motivo); cada folha mudada ganha
    um 'editado' no histórico com antes/depois e de onde veio."""
    if d.alvo not in ("itens", "lote_pendentes", "lote", "projeto"):
        raise HTTPException(400, "Alvo inválido: use itens, lote_pendentes, lote ou projeto")
    if d.modo not in ("acrescentar", "substituir"):
        raise HTTPException(400, "Modo inválido: use acrescentar ou substituir")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        o = con.execute("SELECT codigo, projeto_codigo, lote_id, parceiros FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not o:
            raise HTTPException(404, "Folha não existe")
        fonte = ler(o["parceiros"])
        if not fonte:
            raise HTTPException(409, "Esta folha ainda não tem escritórios parceiros salvos: salve antes de copiar")
        sql = "SELECT codigo, projeto_codigo, lote_id, revisao, duplicata_de, parceiros FROM item WHERE projeto_codigo=? AND codigo<>?"
        par: list = [o["projeto_codigo"], codigo]
        if d.alvo in ("lote_pendentes", "lote"):
            if not o["lote_id"]:
                raise HTTPException(400, "Esta folha não é de um lote: escolha as folhas ou o projeto inteiro")
            sql += " AND lote_id=?"; par.append(o["lote_id"])
            if d.alvo == "lote_pendentes":
                sql += " AND revisao='pendente'"
        if d.alvo != "itens":
            sql += " AND duplicata_de IS NULL"
        linhas = {r["codigo"]: r for r in con.execute(sql + " ORDER BY serie_codigo, sequencial", par)}
        alvo = list(linhas) if d.alvo != "itens" else list(dict.fromkeys(d.itens or []))
        if not alvo:
            raise HTTPException(400, "Nenhuma folha escolhida")
        aplicadas, ignoradas = [], []
        for cod in alvo:
            r = linhas.get(cod)
            if not r:
                ignoradas.append({"codigo": cod, "motivo": "não é deste projeto" if cod != codigo else "é a própria folha"}); continue
            antes = ler(r["parceiros"])
            depois = fonte if d.modo == "substituir" else juntar(antes, fonte)
            if depois == antes:
                ignoradas.append({"codigo": cod, "motivo": "já tinha esses parceiros"}); continue
            con.execute("UPDATE item SET parceiros=?, atualizado_em=datetime('now') WHERE codigo=?", (para_coluna(depois), cod))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (cod, u["email"], json.dumps({"antes": {"parceiros": antes}, "depois": {"parceiros": depois},
                                                      "copiado_de": codigo, "modo": d.modo}, ensure_ascii=False)))
            aplicadas.append(cod)
        con.commit()
        return {"ok": True, "parceiros": fonte, "aplicadas": aplicadas, "ignoradas": ignoradas}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class DesfazerCopia(BaseModel):
    itens: list[str]


@router.post("/itens/{codigo}/parceiros/copiar/desfazer")
def desfazer_copia(codigo: str, d: DesfazerCopia, u: dict = Depends(auth.exige("operador"))) -> dict:
    """CAMP-087: desfaz "Copiar para outras folhas". Cada folha volta ao que tinha ANTES da última cópia vinda desta folha (o 'antes' do histórico),
    só se ninguém mexeu nos parceiros dela depois (senão fica como está e a resposta diz por quê). Grava no histórico."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        voltaram, ficaram = [], []
        for cod in dict.fromkeys(d.itens or []):
            ev = None
            for r in con.execute("SELECT detalhe FROM evento WHERE entidade='item' AND codigo=? AND tipo='editado' ORDER BY id DESC LIMIT 20", (cod,)):
                try:
                    det = json.loads(r["detalhe"] or "{}")
                except ValueError:
                    continue
                if "parceiros" in (det.get("depois") or {}):
                    ev = det
                    break
            atual = con.execute("SELECT parceiros FROM item WHERE codigo=?", (cod,)).fetchone()
            if not atual or not ev or ev.get("copiado_de") != codigo:
                ficaram.append({"codigo": cod, "motivo": "a última mudança de parceiros não foi esta cópia"}); continue
            if ler(atual["parceiros"]) != ev["depois"]["parceiros"]:
                ficaram.append({"codigo": cod, "motivo": "os parceiros mudaram depois da cópia"}); continue
            antes = ev["antes"]["parceiros"]
            con.execute("UPDATE item SET parceiros=?, atualizado_em=datetime('now') WHERE codigo=?", (para_coluna(antes), cod))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (cod, u["email"], json.dumps({"antes": {"parceiros": ev["depois"]["parceiros"]}, "depois": {"parceiros": antes},
                                                      "copia_desfeita_de": codigo}, ensure_ascii=False)))
            voltaram.append(cod)
        con.commit()
        return {"ok": True, "voltaram": voltaram, "ficaram": ficaram}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()
