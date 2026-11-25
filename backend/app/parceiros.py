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
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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


# CAMP-FICHA (25/11/2026). Rafael, na conferência de uma folha de estrutura cujo carimbo só tinha o escritório de cálculo ("DAPA LIMA
# OTERO ENGENHARIA LTDA. S/C." lido como Cliente): "ver se outras folhas desse projeto têm algum escritório e já sugerir". Tudo do BANCO
# (nada de QNAP): os escritórios das OUTRAS folhas do projeto, a disciplina que a própria folha indica (tipo lido / título) e o aviso de
# que o "cliente" lido parece ser o escritório complementar. Nada grava sozinho: a tela só sugere; quem confere clica e salva.
_RE_FIRMA = re.compile(r"\b(engenharia|projetos?|arquitetura|construtora|construcoes|ltda|s\s*/\s*c|s\.\s*a\.?|s/a|escritorio tecnico|calculos?"
                       r"|instalacoes|consultoria|eireli|epp)\b")
# a ordem importa: o primeiro que casa decide (tipo lido antes do título; ver disciplina_da_folha)
_DISC_PALAVRAS = (
    ("Ar-condicionado/climatização", r"ar[\s-]?condicionado|climatiza|ventilacao mecanica|exaust"),
    ("Paisagismo", r"paisag|jardim|jardins"),
    ("Luminotécnica", r"luminotec"),
    ("Acústica", r"acustic"),
    ("Instalações elétricas", r"eletric|luz e forca|forca e luz|telefon|para[\s-]?raios|spda"),
    ("Instalações hidráulicas", r"hidraul|hidro[\s-]?sanit|sanitari|esgoto|agua fria|agua quente|aguas pluviais|pluvia|incendio"),
    ("Fundações", r"fundac|estaca|sapata|tubulao|tubuloes"),
    ("Estrutura", r"estrutur|concreto armado|armacao|armadura|ferragem|formas?\b|viga|pilar|laje|calculo estrutural"),
)


def _sa(t) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(t or "").casefold()) if not unicodedata.combining(ch))


def disciplina_da_folha(tipo_lido=None, *titulos) -> str | None:
    """Disciplina complementar que a folha indica: primeiro pelo tipo lido ("Detalhe / Estrutura"), depois pelo título. Só valores de
    DISCIPLINAS (a lista do painel); None quando não indica nenhuma (planta de arquitetura, por exemplo)."""
    for fonte in (tipo_lido, " ".join(str(t or "") for t in titulos)):
        txt = _sa(fonte)
        if not txt.strip():
            continue
        for disc, rx in _DISC_PALAVRAS:
            if re.search(rx, txt):
                return disc
    return None


def chave_firma(nome) -> str:
    """Nome sem acento, pontuação e o tipo de sociedade: "DAPA LIMA OTERO ENGENHARIA LTDA. S/C." e "DAPA Lima Otero Engenharia" batem."""
    t = re.sub(r"[^a-z0-9 ]+", " ", _sa(nome).replace("s/c", " ").replace("s/a", " "))
    t = re.sub(r"\b(ltda|ltd|s c|s a|sa|sc|me|epp|eireli|cia)\b", " ", t)
    return " ".join(t.split())


def parece_firma(nome) -> bool:
    return bool(_RE_FIRMA.search(_sa(nome)))


# CAMP-FICHA (25/11/2026). Rafael, na página do projeto: "selecionar várias e colocar o escritório que fez, e que ficasse a separação do
# tipo elétrica, engenharia, fundação, desenhos etc., tanto aqui quanto no site". A disciplina de cada folha, para AGRUPAR (as séries
# S01–S08 continuam como estão; é um agrupamento a mais, dentro dos desenhos): a do escritório parceiro da folha; senão a que o tipo indica
# (Estrutura, "Detalhe / Estrutura", instalações…); senão "Arquitetura" (os desenhos do próprio arquiteto).
ARQUITETURA = "Arquitetura"
SERIES_DESENHO = ("S01", "S08")      # Desenhos e pranchas, Redesenhos: onde o agrupamento por disciplina vale (painel e site)


def disciplina_grupo(parceiros=None, tipo_documento=None, tipos_documento=None, tipo_lido=None) -> tuple[str, str | None]:
    """(disciplina, escritório | None) para agrupar a folha. Só valores de DISCIPLINAS (ou o texto de "Outra" que a equipe escreveu no
    parceiro); sem nada, "Arquitetura"."""
    lista = parceiros if isinstance(parceiros, list) else ler(parceiros)
    for p in lista:
        if p.get("disciplina"):
            return p["disciplina"], p.get("escritorio") or None
    d = disciplina_da_folha(tipos_documento or tipo_documento) or disciplina_da_folha(tipo_lido)
    return (d or ARQUITETURA), None


def ordem_disciplina(nome: str) -> tuple:
    """Arquitetura primeiro; depois a ordem da lista do painel; as outras (texto livre) por nome."""
    if nome == ARQUITETURA:
        return (0, 0, "")
    try:
        return (1, DISCIPLINAS.index(nome), "")
    except ValueError:
        return (2, 0, nome.casefold())


class LoteParceiros(BaseModel):
    itens: list[str]
    escritorio: str
    disciplina: str = ""
    outra: str | None = None
    acao: str = "adicionar"      # adicionar | tirar
    simular: bool = True


@router.post("/projetos/{projeto}/parceiros/lote")
def parceiros_em_lote(projeto: str, d: LoteParceiros, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Escritório parceiro em várias folhas do projeto de uma vez (as escolhidas na grade).
    - adicionar: o escritório + disciplina entra em cada folha (as que já têm ficam como estão);
    - tirar: sai de cada folha (o mesmo escritório, com ou sem LTDA/maiúsculas; com disciplina, só nessa disciplina).
    simular=true (padrão) só diz o que vai mudar ("vai adicionar a N folhas (M já têm)"). Aplicar: cada folha mudada ganha um 'editado'
    no histórico com antes/depois (e "lote"); repetir não muda nada. Folhas já no site: a separação por disciplina vai ao site depois."""
    if d.acao not in ("adicionar", "tirar"):
        raise HTTPException(400, "Ação inválida: use adicionar ou tirar")
    esc = _limpo(d.escritorio)
    if not esc:
        raise HTTPException(400, "Diga o escritório parceiro")
    novo = None
    if d.acao == "adicionar":
        novo = normalizar([{"escritorio": esc, "disciplina": d.disciplina, "outra": d.outra}])[0]
    disc_tirar = None
    if d.acao == "tirar" and _limpo(d.disciplina):
        fixas = {x.casefold(): x for x in DISCIPLINAS}
        disc_tirar = (fixas.get(_limpo(d.disciplina).casefold()) or _limpo(d.disciplina))
        if disc_tirar == "Outra":
            disc_tirar = _limpo(d.outra) or None
    alvo = list(dict.fromkeys(x for x in (d.itens or []) if x))
    if not alvo:
        raise HTTPException(400, "Nenhuma folha escolhida")
    if len(alvo) > 2000:
        raise HTTPException(400, "No máximo 2000 folhas de uma vez")
    chave = chave_firma(esc)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        q = ",".join("?" * len(alvo))
        linhas = {r["codigo"]: r for r in con.execute(
            f"SELECT codigo, parceiros, tainacan_item_id FROM item WHERE projeto_codigo=? AND codigo IN ({q})", (projeto, *alvo))}
        mudam, ja, fora = [], [], []
        site = False
        for cod in alvo:
            r = linhas.get(cod)
            if not r:
                fora.append({"codigo": cod, "motivo": "não é deste projeto"}); continue
            antes = ler(r["parceiros"])
            if d.acao == "adicionar":
                tem = any(chave_firma(p["escritorio"]) == chave and p["disciplina"].casefold() == novo["disciplina"].casefold() for p in antes)
                depois = antes if tem else juntar(antes, [novo])
            else:
                depois = [p for p in antes if not (chave_firma(p["escritorio"]) == chave and (not disc_tirar or p["disciplina"].casefold() == disc_tirar.casefold()))]
            if depois == antes:
                ja.append(cod); continue
            mudam.append(cod)
            if d.simular:
                continue
            con.execute("UPDATE item SET parceiros=?, atualizado_em=datetime('now') WHERE codigo=?", (para_coluna(depois), cod))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (cod, u["email"], json.dumps({"antes": {"parceiros": antes}, "depois": {"parceiros": depois},
                                                      "lote": d.acao, "escritorio": esc}, ensure_ascii=False)))
            site = site or bool(r["tainacan_item_id"])
        if not d.simular and site:
            from . import disciplina_site
            site = disciplina_site.marcar(con, projeto)
        con.commit()
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()
    if not d.simular and site:
        from . import disciplina_site
        tarefas.add_task(disciplina_site.enviar_depois, projeto, u["email"])
    chave_res = "vai_mudar" if d.simular else "mudaram"
    return {"ok": True, "simulado": d.simular, "acao": d.acao, "escritorio": esc,
            "disciplina": (novo or {}).get("disciplina") or disc_tirar, chave_res: mudam, "ja_estavam": ja, "fora": fora,
            "site": bool(site) and not d.simular}


@router.get("/itens/{codigo}/parceiros/projeto")
def sugestoes_do_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Sugestões para a ficha desta folha, tiradas das OUTRAS folhas do mesmo projeto:
    - escritorios: [{escritorio, disciplina, folhas, combina}] (par escritório + disciplina, mais folhas primeiro; os da disciplina que
      esta folha indica vêm antes, com combina=true); os que esta folha já tem ficam de fora;
    - disciplina: a que esta folha indica pelo tipo lido / título (ou null);
    - cliente: o cliente mais escrito nas outras folhas (que não parece escritório), com quantas folhas;
    - cliente_e_escritorio: quando o Cliente lido desta folha parece um escritório (LTDA, ENGENHARIA, S/C…) E a folha é de projeto
      complementar: {nome, disciplina, ja_escritorio_folhas} — a tela oferece "mover para Escritórios parceiros"."""
    con = connect()
    try:
        i = con.execute("SELECT codigo, projeto_codigo, parceiros, cliente_folha, tipo_lido, titulo, pendencias FROM item WHERE codigo=?",
                        (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        try:
            titulo_lido = (json.loads(i["pendencias"] or "{}") or {}).get("titulo_lido")
        except (ValueError, TypeError, AttributeError):
            titulo_lido = None
        disc = disciplina_da_folha(i["tipo_lido"], i["titulo"], titulo_lido)
        meus = {(p["escritorio"].casefold(), p["disciplina"].casefold()) for p in ler(i["parceiros"])}
        meus_nomes = {e for e, _ in meus}
        pares: dict = {}
        por_nome: dict = {}
        clientes: dict = {}
        for r in con.execute("""SELECT parceiros, cliente_folha FROM item WHERE projeto_codigo=? AND codigo<>? AND duplicata_de IS NULL""",
                             (i["projeto_codigo"], codigo)):
            vistos = set()
            lista = ler(r["parceiros"])
            for p in {chave_firma(p["escritorio"]): p for p in lista}.values():
                k0 = chave_firma(p["escritorio"])
                n0, _ = por_nome.get(k0, (0, p["escritorio"]))
                por_nome[k0] = (n0 + 1, p["escritorio"])
            for p in lista:
                k = (p["escritorio"].casefold(), p["disciplina"].casefold())
                if k in vistos:
                    continue
                vistos.add(k)
                a = pares.setdefault(k, {"escritorio": p["escritorio"], "disciplina": p["disciplina"], "folhas": 0})
                a["folhas"] += 1
            c = _limpo(r["cliente_folha"])
            if c and not parece_firma(c):
                b = clientes.setdefault(c.casefold(), {"nome": c, "folhas": 0})
                b["folhas"] += 1
        esc = [dict(a, combina=bool(disc) and a["disciplina"] == disc) for k, a in pares.items() if k not in meus and k[0] not in meus_nomes]
        esc.sort(key=lambda a: (not a["combina"], -a["folhas"], a["escritorio"].casefold()))
        cli = max(clientes.values(), key=lambda b: (b["folhas"], b["nome"]), default=None)
        lido = _limpo(i["cliente_folha"])
        mover = None
        if lido and disc and parece_firma(lido):
            n0, grafia = por_nome.get(chave_firma(lido), (0, None))
            # o nome como já está escrito nas outras folhas (se houver): "Mover" usa essa grafia
            mover = {"nome": lido, "escritorio": grafia or lido, "disciplina": disc, "ja_escritorio_folhas": n0}
            if cli and cli["nome"].casefold() == lido.casefold():
                cli = None
        return {"codigo": codigo, "disciplina": disc, "escritorios": esc[:6], "cliente": cli, "cliente_e_escritorio": mover}
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


class AutoriaParceiro(BaseModel):
    escritorio: str
    disciplina: str = ""
    itens: list[str] | None = None   # sem lista: todas as folhas do projeto com "autoria não confirmada" que já têm esse parceiro


@router.post("/projetos/{projeto}/autoria-parceiro")
def autoria_parceiro(projeto: str, d: AutoriaParceiro, u: dict = Depends(auth.exige("operador"))) -> dict:
    """CAMP-127 (20/10, F026-P0009): o carimbo das pranchas de estrutura é do calculista (AC Vasconcelos), não do titular do fundo, e a folha
    ficava "autoria não confirmada" — enquanto "Parceiros neste projeto" já sabia que ele é o parceiro de estrutura. Em lote, nas folhas
    escolhidas: o escritório entra (ou continua) como parceiro com a disciplina, a autoria fica do titular do fundo (sai o crédito
    "Autoria não confirmada") e os problemas de autoria da folha fecham. Cada folha ganha um evento no histórico."""
    esc = _limpo(d.escritorio)[:LIM_ESCRITORIO]
    if not esc:
        raise HTTPException(400, "Diga o escritório parceiro")
    disc = _limpo(d.disciplina)[:LIM_DISCIPLINA]
    novo = {"escritorio": esc, "disciplina": disc}
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        linhas = {r["codigo"]: r for r in con.execute(
            "SELECT codigo, parceiros, autoria_divergente FROM item WHERE projeto_codigo=? AND autoria_divergente=1", (projeto,))}
        if d.itens is None:
            alvo = [c for c, r in linhas.items() if any(p["escritorio"].casefold() == esc.casefold() for p in ler(r["parceiros"]))]
        else:
            alvo = list(dict.fromkeys(d.itens))
        if not alvo:
            raise HTTPException(400, "Nenhuma folha com autoria não confirmada para esse parceiro")
        feitas, ignoradas = [], []
        for cod in alvo:
            r = linhas.get(cod)
            if not r:
                ignoradas.append({"codigo": cod, "motivo": "não é deste projeto ou a autoria já está confirmada"}); continue
            antes = ler(r["parceiros"])
            depois = antes if any(p["escritorio"].casefold() == esc.casefold() for p in antes) else juntar(antes, [novo])
            con.execute("UPDATE item SET autoria_divergente=0, parceiros=?, atualizado_em=datetime('now') WHERE codigo=?", (para_coluna(depois), cod))
            ids = [x[0] for x in con.execute("SELECT id FROM erro WHERE codigo=? AND categoria='autoria_divergente' AND situacao IN ('aberto','em_correcao')", (cod,))]
            if ids:
                con.execute(f"UPDATE erro SET situacao='corrigido', resolvido_em=datetime('now'), resolucao=? WHERE id IN ({','.join('?' * len(ids))})",
                            (f"Autoria confirmada por {u['email']}: o carimbo é de {texto([novo])}, parceiro; a autoria é do titular do fundo.", *ids))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'autoria_parceiro',?,?)",
                        (cod, u["email"], json.dumps({"parceiro": novo, "antes": {"parceiros": antes}, "depois": {"parceiros": depois},
                                                      "problemas_fechados": ids}, ensure_ascii=False)))
            feitas.append(cod)
        con.commit()
        return {"ok": True, "parceiro": novo, "confirmadas": feitas, "ignoradas": ignoradas}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


# CAMP-FICHA (25/11/2026). Rafael viu o mesmo escritório com duas grafias (leitura do carimbo): "DAPA LIMA OTERO ENGENHARIA LTDA. S/C." e
# "DAFRA- LIMA OTERO ENGENHARIA LTDA. S/C.". Nomes QUASE iguais: palavras sem as jurídicas/genéricas, cada uma casando com outra igual ou
# com até 2 letras de diferença (mesma inicial, 4+ letras); semelhança = casadas / maior número de palavras >= 0,8. Nunca unifica sozinho:
# a tela oferece "Unificar nomes" (prévia; histórico em cada folha).
_GENERICAS = {"sociedade", "civil", "de", "da", "do", "das", "dos", "e", "engenharia", "escritorio", "tecnico", "projetos", "projeto", "ltda", "ltd",
              "sc", "sa", "me", "epp", "eireli", "cia", "companhia", "arquitetura", "consultoria", "construtora", "construcoes", "comercio", "servicos"}


def _palavras(nome) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9 ]+", " ", _sa(nome).replace("s/c", " ").replace("s/a", " ")).split() if w not in _GENERICAS]


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    ant = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(ant[j] + 1, cur[j - 1] + 1, ant[j - 1] + (ca != cb)))
        ant = cur
    return ant[-1]


def _casa(a: str, b: str) -> bool:
    return a == b or (len(a) >= 4 and len(b) >= 4 and a[0] == b[0] and _lev(a, b) <= 2)


def semelhanca(a, b) -> float:
    A, B = _palavras(a), _palavras(b)
    if not A or not B:
        return 0.0
    livres, n = list(B), 0
    for w in A:
        k = next((i for i, x in enumerate(livres) if _casa(w, x)), None)
        if k is not None:
            n += 1
            livres.pop(k)
    return n / max(len(A), len(B))


def quase_iguais(nomes: list[dict]) -> list[list[dict]]:
    """[[{escritorio, folhas}, ...], ...]: grupos de nomes diferentes (chave_firma diferente) que parecem o mesmo escritório."""
    grupos: list[list[dict]] = []
    for x in nomes:
        g = next((g for g in grupos if any(chave_firma(y["escritorio"]) != chave_firma(x["escritorio"]) and semelhanca(y["escritorio"], x["escritorio"]) >= 0.8
                                           for y in g)), None)
        if g is not None:
            g.append(x)
        else:
            grupos.append([x])
    return [sorted(g, key=lambda y: -y.get("folhas", 0)) for g in grupos if len({chave_firma(y["escritorio"]) for y in g}) > 1]


@router.get("/projetos/{projeto}/parceiros/semelhantes")
def semelhantes(projeto: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        nomes = resumo_projeto(con, projeto)
    finally:
        con.close()
    return {"grupos": [{"nomes": g, "sugerido": g[0]["escritorio"]} for g in quase_iguais(nomes)]}


class Unificar(BaseModel):
    de: list[str]
    para: str
    simular: bool = True


@router.post("/projetos/{projeto}/parceiros/unificar")
def unificar(projeto: str, d: Unificar, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Troca as grafias `de` pelo nome `para` em todas as folhas do projeto (a disciplina de cada uma fica). simular=true (padrão) só conta."""
    para = _limpo(d.para)
    if not para:
        raise HTTPException(400, "Diga o nome que fica")
    chaves = {chave_firma(x) for x in d.de if _limpo(x)} - {chave_firma(para)}
    if not chaves:
        raise HTTPException(400, "Escolha os nomes que vão ser trocados")
    con = connect()
    site, mudam = False, []
    try:
        con.execute("BEGIN IMMEDIATE")
        for r in con.execute("SELECT codigo, parceiros, tainacan_item_id FROM item WHERE projeto_codigo=? AND parceiros IS NOT NULL", (projeto,)).fetchall():
            antes = ler(r["parceiros"])
            if not any(chave_firma(p["escritorio"]) in chaves for p in antes):
                continue
            depois: list[dict] = []
            for p in antes:
                q = {**p, "escritorio": para} if chave_firma(p["escritorio"]) in chaves else p
                if not any(chave_firma(x["escritorio"]) == chave_firma(q["escritorio"]) and x["disciplina"].casefold() == q["disciplina"].casefold() for x in depois):
                    depois.append(q)
            mudam.append(r["codigo"])
            if d.simular:
                continue
            con.execute("UPDATE item SET parceiros=?, atualizado_em=datetime('now') WHERE codigo=?", (para_coluna(depois), r["codigo"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (r["codigo"], u["email"], json.dumps({"antes": {"parceiros": antes}, "depois": {"parceiros": depois}, "unificar": True,
                                                              "para": para}, ensure_ascii=False)))
            site = site or bool(r["tainacan_item_id"])
        if not d.simular and site:
            from . import disciplina_site
            site = disciplina_site.marcar(con, projeto)
        con.commit()
    finally:
        con.close()
    if not d.simular and site:
        from . import disciplina_site
        tarefas.add_task(disciplina_site.enviar_depois, projeto, u["email"])
    return {"ok": True, "simulado": d.simular, "para": para, ("vai_mudar" if d.simular else "mudaram"): mudam, "site": bool(site) and not d.simular}


# CAMP-FICHA (25/11/2026). Rafael: "falta elétrica, hidráulica, paisagismo.." — tipos complementares (migração 263). Pela disciplina que a
# folha indica (tipo lido do CAMP Vision, depois o título), o tipo de documento a SUGERIR na conferência. Nunca é aplicado sozinho.
TIPO_POR_DISCIPLINA = {"Instalações elétricas": "Elétrica", "Instalações hidráulicas": "Hidráulica", "Paisagismo": "Paisagismo", "Fundações": "Fundação"}


def tipo_sugerido(tipo_lido=None, *titulos) -> str | None:
    d = disciplina_da_folha(tipo_lido, *titulos)
    return TIPO_POR_DISCIPLINA.get(d) if d else None
