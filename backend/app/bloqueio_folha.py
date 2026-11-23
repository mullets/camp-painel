"""CAMP-BLOQUEIO (23/11/2026): o motivo do bloqueio em frase clara e a decisão na própria folha.

Rafael, olhando F010-P0174 (Concurso Público/Votorantim), Folha 1/7 com a marca vermelha "bloqueada" e, no "Revisar folha", só a pílula
"ficha de documentação (não é obra)": "não entendi por que tá bloqueado". Aprovou o conserto: "sim, arrume sim".

- **Uma frase** para cada motivo de bloqueio: o que o sistema acha, por quê e o que fazer. Vale para os bloqueios que o CAMP Vision escreve na
  folha (`pendencias.bloqueios`, texto livre do `pacote_tainacan.json`: `campvision-new/nucleo/projeto.py`) e para os problemas que bloqueiam
  (`erro.gravidade='bloqueia'`, por categoria). A tela usa `bloqueio_motivos` (campo novo e opcional de cada folha em `/detalhe`) e
  `frase_bloqueio` (campo novo e opcional de cada problema na lista de Problemas). Sem esses campos (painel antigo), a tela mostra o texto de antes.
- **Decidir na própria folha** (`POST /api/itens/{codigo}/bloqueio/decidir`): "É prancha do projeto · liberar" (tira o bloqueio; com a caixa
  "trocar o tipo para Planta", o tipo "Documento" vira "Planta" pela rota de editar a folha de sempre) e "É ficha · deixar fora" (retém a folha
  pela rota de reter de sempre: fica no painel e não vai ao site; se já está no site, fica privada lá). A conclusão vem do modelo de decisão
  (`erro_modelo`, migração 246, editável em Problemas); problema aberto da folha sobre o mesmo motivo é resolvido pelo fluxo da Central
  (`central_problemas.mudar_fase`: quem, quando, pontos da Home). **Desfazer**: o mesmo `erro_desfazer` das ações rápidas
  (`POST /api/problemas/rapido/desfazer/{token}`: só quem fez ou um admin, uma vez, até 30 min; o tipo volta pela rota de editar a folha).
- Os bloqueios "de outro projeto" e "duplicata" têm frase aqui, mas a decisão continua nas ações que já existiam (É deste projeto / É de outro
  projeto…; Ver lado a lado / Não é duplicata). "Lote de teste" não se libera na folha: o CAMP Vision precisa ler a pasta de novo.

Achado (não mexe no CAMP Vision): "ficha de documentação" nasce de `derivacao.e_documento(titulo)`, uma lista de palavras no TÍTULO lido do
carimbo (documento, memorial, caderno, pasta, contrato, ofício, recorte, correspondência, currículo), só na série S01. Prancha de concurso com
"MEMORIAL" no título cai nela. `PALAVRAS_FICHA` abaixo é a mesma lista, só para a frase dizer qual palavra disparou; se o CAMP Vision mudar a
regra e a palavra não for achada, a frase diz "pelo título lido".
"""
from __future__ import annotations

import json
import re
import unicodedata

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["revisao"])

# a mesma lista de `campvision-new/nucleo/derivacao.py` (TERMOS_DOCUMENTO), só para explicar; quem decide o bloqueio é o CAMP Vision
PALAVRAS_FICHA = re.compile(r"\b(documento\w*|curriculo\w*|caderno\w*|pasta\w*|recortes?|correspondenc\w*|memorial\w*|contrato\w*|oficios?)\b")
_CARIMBO = re.compile(r"carimbo diz\s*:?\s*[\"'“‘«]([^\"'”’»]{1,160})", re.I)
_FOLHA = re.compile(r"\bF\d{3}-P\d{4}-\d{4}-S\d{2}-D(\d{4,6})\b")
_RETIRADO = re.compile(r"^retirad[oa] por decis[aã]o de\s*([^:]*):\s*(.*)$", re.I | re.S)

# tipo -> (selo curto do cartão, a decisão vale na folha?)
TIPOS = {
    "ficha": ("ficha?", True),
    "capa": ("não é prancha?", True),
    "retirada": ("retirada", True),
    "outro": ("bloqueada", True),
    "teste": ("lote de teste", False),
    "outro_projeto": ("outro projeto?", False),
    "sem_identificacao": ("sem identificação", False),
    "duplicata": ("cópia?", False),
}
# (tipo, ação) -> (título do modelo de decisão, texto padrão se o modelo foi desativado, rótulo do botão)
MODELOS = {
    ("ficha", "liberar"): ("É prancha do projeto", "Conferido na folha: é prancha do projeto, não ficha de documentação. O bloqueio do CAMP Vision saiu.",
                           "É prancha do projeto · liberar"),
    ("ficha", "deixar_fora"): ("É ficha: fica fora do site", "Conferido na folha: é ficha de documentação, não prancha do projeto. Fica no painel e não vai ao site.",
                               "É ficha · deixar fora"),
    ("capa", "liberar"): ("É prancha do projeto", "Conferido na folha: é prancha do projeto, não ficha de documentação. O bloqueio do CAMP Vision saiu.",
                          "É prancha do projeto · liberar"),
    ("capa", "deixar_fora"): ("Fica fora do site", "Conferido na folha: o bloqueio do CAMP Vision está certo. A folha fica no painel e não vai ao site.",
                              "Não é prancha · deixar fora"),
}
for _t in ("retirada", "outro"):
    MODELOS[(_t, "liberar")] = ("Pode ir ao site", "Conferido na folha: o motivo do bloqueio do CAMP Vision não vale mais. A folha pode ir ao site.", "Pode ir ao site · liberar")
    MODELOS[(_t, "deixar_fora")] = ("Fica fora do site", "Conferido na folha: o bloqueio do CAMP Vision está certo. A folha fica no painel e não vai ao site.", "Deixar fora do site")
ACOES = ("liberar", "deixar_fora")
TIPO_PLANTA, TIPO_DOCUMENTO = "Planta", "Documento"


def _sem_acento(t) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(ch) != "Mn").lower()


def classificar(texto) -> str:
    """O tipo do bloqueio pelo texto que o CAMP Vision escreveu (`nucleo/projeto.py`)."""
    from .importador_lote import fala_de_projeto_divergente
    t = _sem_acento(texto)
    if "sem identificacao" in t:
        return "sem_identificacao"
    if fala_de_projeto_divergente(texto):
        return "outro_projeto"
    if "duplicat" in t:
        return "duplicata"
    if "ficha de documentacao" in t or "nao e obra" in t:
        return "ficha"
    if "nao e prancha" in t:
        return "capa"
    if "lote de teste" in t:
        return "teste"
    if t.startswith(("retirado por decisao", "retirada por decisao")):
        return "retirada"
    return "outro"


def palavra_da_ficha(titulo_lido) -> str | None:
    m = PALAVRAS_FICHA.search(_sem_acento(titulo_lido))
    return m.group(1) if m else None


def _tem_documento(tipo) -> bool:
    from .tipos_documento import separar
    return any(_sem_acento(x) == "documento" for x in separar(tipo))


def explicar(texto, titulo_lido=None, tipo=None, status_site=None) -> dict:
    """Um bloqueio do CAMP Vision em frase: {tipo, texto (o original), curto (o selo do cartão), frase, decide (a decisão vale na folha),
    acoes ([{acao, rotulo}]), trocar_tipo (oferecer "trocar o tipo para Planta")}."""
    k = classificar(texto)
    curto, decide = TIPOS[k]
    raw = str(texto or "").strip()
    no_site = status_site in ("rascunho", "no_ar")
    if k == "ficha":
        p = palavra_da_ficha(titulo_lido)
        porque = [f'o título lido tem a palavra "{p}"' if p else "pelo título lido"]
        if _tem_documento(tipo):
            porque.append('o tipo é "Documento"')
        frase = ("Bloqueada: o CAMP Vision acha que esta folha é uma ficha de documentação, não uma prancha do projeto ("
                 + " e ".join(porque) + "). Se for prancha, libere; se for ficha, deixe fora do site.")
    elif k == "capa":
        qual = raw.split(":", 1)[0].strip() or "capa"
        frase = (f'Bloqueada: o CAMP Vision acha que esta folha é {qual.lower()}, não uma prancha do projeto. '
                 "Se for prancha, libere; se não for, deixe fora do site.")
    elif k == "retirada":
        m = _RETIRADO.match(raw)
        quem, mot = ((m.group(1).strip() or "alguém"), m.group(2).strip()) if m else ("alguém", "")
        frase = (f"Bloqueada: {quem} tirou esta folha da publicação no CAMP Vision" + (f' ("{mot}")' if mot else "")
                 + ". Se ela pode ir ao site, libere; se não, deixe fora do site.")
    elif k == "teste":
        frase = ("Bloqueada: a folha veio de um lote de teste do CAMP Vision, que nunca vai ao site. "
                 "Para publicar, o CAMP Vision precisa ler a pasta de novo fora do teste.")
    elif k == "outro_projeto":
        m = _CARIMBO.search(raw)
        frase = ("Bloqueada: " + (f'o carimbo diz "{m.group(1).strip()}", e ' if m else "") + "o CAMP Vision acha que esta folha é de outro projeto. "
                 'Se for deste, use "É deste projeto"; se não for, mova para o projeto certo.')
    elif k == "sem_identificacao":
        frase = ("Bloqueada: a pasta tem várias obras e a folha não diz de qual é. "
                 'Se for deste projeto, use "É deste projeto"; se não for, mova para o projeto certo.')
    elif k == "duplicata":
        m = _FOLHA.search(raw)
        frase = ("Bloqueada: o CAMP Vision acha que esta folha é cópia de " + (f"D{m.group(1)}" if m else "outra folha")
                 + " (a mesma imagem duas vezes); só uma vai ao site. Confira lado a lado.")
    else:
        frase = f'Bloqueada pelo CAMP Vision: "{raw}". Se você conferiu e não vale mais, libere; se vale, deixe fora do site.'
    if decide and no_site:
        frase += " Ela já foi ao site: deixar fora a deixa privada lá."
    acoes = [{"acao": a, "rotulo": MODELOS[(k, a)][2]} for a in ACOES] if decide else []
    return {"tipo": k, "texto": raw, "curto": curto, "frase": frase, "decide": decide, "acoes": acoes,
            "trocar_tipo": k in ("ficha", "capa") and _tem_documento(tipo)}


def motivos_da_folha(item: dict) -> list[dict]:
    """`bloqueio_motivos` de uma folha (dict com `pendencias` já lido ou em texto, `tipo_documento`, `status_site`)."""
    pend = item.get("pendencias")
    if isinstance(pend, str):
        try:
            pend = json.loads(pend or "{}")
        except ValueError:
            pend = {}
    if not isinstance(pend, dict):
        return []
    tipo = item.get("tipos_documento") or item.get("tipo_documento")
    return [explicar(b, pend.get("titulo_lido"), tipo, item.get("status_site")) for b in (pend.get("bloqueios") or []) if b]


# problemas que bloqueiam (lista de Problemas): por categoria
_FRASE_ERRO = {
    "projeto_errado": "o CAMP Vision acha que {pron} é de outro projeto{carimbo}. Diga se é deste projeto ou mova para o projeto certo.",
    "duplicata": "parece cópia de outra folha; só uma vai ao site. Confira lado a lado e diga se é a mesma folha.",
    "metadado": "falta um dado obrigatório ou ele está errado. Corrija na folha e resolva o problema.",
    "arquivo_corrompido": "o arquivo da imagem está danificado e não abre. Peça para o CAMP Vision ler de novo ou digitalize outra vez.",
    "codigo": "o código não bate com o do painel. Confira a pasta e o código antes de publicar.",
    "orientacao": "a folha está virada. Gire na revisão e confira.",
    "espelhado": "a folha foi digitalizada pelo verso. Espelhe na revisão e confira.",
    "credito": "o crédito está errado ou faltando. Corrija com a fonte.",
    "outro": "alguém registrou um problema que trava {alvo}. Leia a descrição e resolva.",
}


def frase_erro(e: dict) -> str | None:
    """A frase de um problema que BLOQUEIA (None para os outros). `e` é a linha do problema (categoria, codigo, descricao)."""
    if e.get("gravidade") != "bloqueia" or e.get("categoria") == "autoria_divergente":
        return None
    folha = len(str(e.get("codigo") or "")) > 10
    alvo = "esta folha" if folha else "este projeto"
    m = _CARIMBO.search(str(e.get("descricao") or ""))
    corpo = _FRASE_ERRO.get(e.get("categoria") or "outro", _FRASE_ERRO["outro"]).format(
        alvo=alvo, pron="ela" if folha else "ele", carimbo=f' (o carimbo diz "{m.group(1).strip()}")' if m else "")
    return ("Impede publicar esta folha: " if folha else "Impede publicar o projeto: ") + corpo


# ---------------- decidir na própria folha ----------------
class Decidir(BaseModel):
    acao: str                       # liberar · deixar_fora
    tipo: str | None = None         # o tipo do bloqueio decidido (ficha, capa, retirada, outro); vazio = todos os que se decidem na folha
    trocar_tipo: bool = False       # "trocar o tipo para Planta" (só ficha/capa com o tipo "Documento")


def _modelo(con, k: str, acao: str) -> tuple[str, str]:
    tit, padrao, _ = MODELOS[(k, acao)]
    r = con.execute("SELECT texto FROM erro_modelo WHERE categoria='outro' AND titulo=? AND ativo=1", (tit,)).fetchone()
    return ((r[0] or "").strip() or padrao) if r else padrao, tit


def _item(con, codigo: str):
    return con.execute("SELECT codigo, pendencias, status_site, autoria_divergente, tipo_documento, tipos_documento, retida, retida_motivo, revisao "
                       "FROM item WHERE codigo=?", (codigo,)).fetchone()


def _pend(i) -> dict:
    try:
        p = json.loads(i["pendencias"] or "{}")
    except ValueError:
        p = {}
    return p if isinstance(p, dict) else {}


def _saida(con, codigo: str) -> dict:
    i = _item(con, codigo)
    d = dict(i)
    d["pendencias"] = _pend(i)
    d["tipo_documento"] = i["tipos_documento"] or i["tipo_documento"]
    d.pop("tipos_documento", None)
    d["bloqueio_motivos"] = motivos_da_folha({**d})
    return d


@router.post("/itens/{codigo}/bloqueio/decidir")
def decidir(codigo: str, d: Decidir, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """"É prancha do projeto · liberar" ou "É ficha · deixar fora", na própria folha. Ver o topo do módulo."""
    from . import central_problemas as cp
    from .problemas_rapido import _entradas_erros, _entradas_itens, _guardar, _snap_erros, _snap_itens
    if d.acao not in ACOES:
        raise HTTPException(400, "Ação inválida")
    if d.tipo and (d.tipo not in TIPOS or not TIPOS[d.tipo][1]):
        raise HTTPException(409, "Este bloqueio não se decide na folha: use a ação dele (É deste projeto, Não é duplicata) ou leia a pasta de novo")
    con = connect()
    try:
        i = _item(con, codigo)
        if not i:
            raise HTTPException(404, "Folha não existe")
        pend = _pend(i)
        alvo = [b for b in (pend.get("bloqueios") or []) if b and TIPOS[classificar(b)][1] and (not d.tipo or classificar(b) == d.tipo)]
        if not alvo:
            raise HTTPException(409, "Esta folha não tem mais esse bloqueio: alguém já decidiu. Atualize a página.")
        k = d.tipo or classificar(alvo[0])
        texto, tit = _modelo(con, k, d.acao)
        # problemas abertos da folha sobre o mesmo motivo (o CAMP Vision às vezes também o manda em erros.json): resolvem pelo fluxo da Central
        erros = [r["id"] for r in con.execute("""SELECT id, descricao FROM erro WHERE codigo=? AND origem='campvision' AND situacao IN ('aberto','em_correcao')
                                                 AND categoria NOT IN ('projeto_errado','duplicata','autoria_divergente')""", (codigo,))
                 if classificar(r["descricao"]) == k and k != "outro"]
        antes_e = _snap_erros(con, erros, []) if erros else {}
        antes_i = _snap_itens(con, [codigo])
        trocar = d.acao == "liberar" and d.trocar_tipo and k in ("ficha", "capa") and _tem_documento(i["tipos_documento"] or i["tipo_documento"])
        planta = con.execute("SELECT nome FROM tipo_documento WHERE nome=?", (TIPO_PLANTA,)).fetchone() if trocar else None
    finally:
        con.close()
    extras: list[dict] = []
    if trocar and planta:              # o tipo pela rota de editar a folha de sempre (valida, grava, manda ao site se a folha está lá)
        from .rotas_itens import EdicaoItem, editar_item
        from .tipos_documento import juntar, separar
        antigo = i["tipos_documento"] or i["tipo_documento"]
        novo = []
        for x in separar(antigo):
            x = TIPO_PLANTA if _sem_acento(x) == "documento" else x
            if x not in novo:
                novo.append(x)
        editar_item(codigo, EdicaoItem(tipo_documento=juntar(novo)), tarefas, u)
        con = connect()
        try:
            depois = con.execute("SELECT tipo_documento FROM item WHERE codigo=?", (codigo,)).fetchone()[0]
        finally:
            con.close()
        extras.append({"metadado": {"folha": codigo, "campo": "tipo_documento", "antes": antigo, "depois": depois}})
    escondida = False
    if d.acao == "deixar_fora" and not i["retida"]:   # a folha fica fora pela rota de reter de sempre (no site: fica privada; site recusou = nada muda)
        from .rotas_revisao import RetencaoItem, reter
        escondida = bool(reter(codigo, RetencaoItem(retida=True, motivo=texto[:300]), u).get("escondida_no_site"))
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            i2 = _item(con, codigo)
            pend = _pend(i2)
            bloq = [b for b in (pend.get("bloqueios") or []) if b]
            tirar = [b for b in bloq if b in alvo]
            pend["bloqueios"] = [b for b in bloq if b not in tirar]
            pend.setdefault("bloqueios_resolvidos", []).append({"bloqueios": tirar, "por": u["email"], "motivo": texto, "decisao": d.acao, "modelo": tit})
            con.execute("UPDATE item SET pendencias=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
            # CAMP-046: autoria não confirmada é aviso, não bloqueio; sem bloqueio na folha, ela sai de 'bloqueado' (o CAMP-068 ainda esperava a autoria)
            if i2["status_site"] == "bloqueado" and not pend["bloqueios"]:
                con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'bloqueio_resolvido',?,?)",
                        (codigo, u["email"], json.dumps({"bloqueios": tirar, "motivo": texto, "decisao": d.acao, "modelo": tit, "na_folha": True,
                                                        **({"tipo_trocado": extras[0]["metadado"]} if extras else {})}, ensure_ascii=False)))
            rot = MODELOS[(k, d.acao)][2]
            for eid in erros:
                cp.mudar_fase(con, eid, cp.MudarFase(fase="resolvido", conclusao=texto[:2000], justificativa=f"Decisão na própria folha: {rot} (modelo “{tit}”)."),
                              u, extra={"na_folha": d.acao, "modelo": tit})
            entradas_e = _entradas_erros(con, antes_e) if antes_e else []
            tok = _guardar(con, u["email"], "bloqueio:" + d.acao, "corrigido", entradas_e + _entradas_itens(con, antes_i) + extras)
            con.commit()
        except Exception:
            con.rollback()
            raise
        return {"ok": True, "acao": d.acao, "tipo": k, "mensagem": "Resolvido.", "desfazer": tok, "conclusao": texto,
                "fechados": sorted({e["id"] for e in entradas_e if e.get("depois") not in ("aberto", "em_correcao")}),
                "tipo_trocado": bool(extras), **({"escondida_no_site": True} if escondida else {}), "item": _saida(con, codigo)}
    finally:
        con.close()
