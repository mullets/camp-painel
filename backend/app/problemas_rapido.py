"""Decisões rápidas na lista de Problemas (CAMP-PROB-RAPIDO, 22/11/2026).

Rafael, olhando a Central com os dados reais: "Decisões simples e rápidas podem ser clicks aí mesmo para resolver, não?"

- **Na própria linha**, sem painel: "Folha pode ser de outro projeto" (É deste projeto · Mover para <sugerido> · Escolher outro projeto…),
  duplicata (É a mesma folha · São diferentes), dado simples faltando (ano, título: campo + Salvar) e "Não é problema" com motivo pronto.
- **Cada ação rápida** resolve pelo MESMO fluxo da Central (`central_problemas.mudar_fase`): a conclusão vem do modelo de decisão do tipo
  (`erro_modelo`, editável depois) e a justificativa é a própria ação ("Ação rápida na lista de problemas: É deste projeto (modelo …)"), então a
  regra "resolver exige conclusão + evidência ou justificativa" continua valendo; quem e quando ficam gravados; os pontos são os da Home
  (`home_trabalho.eventos_validados`, recontados do estado: desfez, o ponto some). O efeito na folha usa o código que já existia: "É deste
  projeto" (`rotas_revisao.deste_projeto`), marcar cópia (`rotas_mesclar.marcar_duplicata_em`), desmarcar (`liberar_bloqueios_de_duplicata`),
  editar a folha (`rotas_itens.editar_item`) e **mover pela rota de mover de sempre** (`rotas_mesclar.mover_itens`, só admin, com simulação antes).
- **Desfazer** (8 s no aviso da tela, 30 min no servidor): o mesmo `erro_desfazer` das ações em massa (só quem fez ou um admin, uma vez). Guarda o
  problema (situação, fase, conclusão), os campos da folha que a ação mudou e a devolução criada; o mover volta pela mesma rota de mover
  (simulação primeiro) e o problema reabre seguindo a folha.
- **Tipos sensíveis** (autoria, crédito e, com a revisão por outra pessoa ligada, os tipos dela) não têm resolução rápida: só o painel.
- **Agrupar**: o mesmo projeto + o mesmo tipo viram UMA linha ("Residência X · 8 folhas podem ser de outro projeto"); as contagens continuam
  contando problemas, nunca grupos.
Só lê e grava o banco (nunca varre o QNAP)."""
from __future__ import annotations

import json
import re
import unicodedata

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from . import central_problemas as cp
from .db import connect

router = APIRouter(prefix="/api/problemas/rapido", tags=["problemas"])

FASES_RAPIDAS = ("novo", "triagem", "em_analise", "reaberto", "devolvido")   # as que podem ir direto para Resolvido/Inválido
TIPOS_SENSIVEIS = ("autoria_divergente", "credito")                          # autoria e crédito: fonte obrigatória, sempre pelo painel
MAX_IDS = 200
# ação -> (categoria do modelo, título do modelo, texto padrão se o modelo foi desativado)
MODELO = {
    "deste_projeto": ("projeto_errado", "É deste projeto", "Conferido: a folha é deste projeto; o aviso de projeto divergente saiu da folha."),
    "mover": ("projeto_errado", "Movida para o projeto certo", "A folha foi movida para o projeto certo (mesmo fundo)."),
    "mesma_folha": ("duplicata", "Marcada como cópia", "A folha foi marcada como cópia da original; só a original vai ao site."),
    "diferentes": ("duplicata", "Não é repetida", "Conferido lado a lado: as folhas são diferentes."),
    "metadado": ("metadado", "Dado corrigido", "O dado foi corrigido conforme o documento."),
    # CAMP-PROB-REAL: a folha que o CAMP Vision deixou fora do lote é mesmo de outro projeto (o mesmo "É de outro projeto…" da página do projeto)
    "fica_fora": ("projeto_errado", "Fica fora deste projeto", "Conferido: a folha é de outro projeto e fica fora deste (a retirada do CAMP Vision está certa). "
                  "Para levá-la ao projeto certo, o CAMP Vision precisa reidentificar o lote."),
}
MOTIVOS_NAO = {"sem_efeito": "Conferido na lista: o aviso não muda nada na folha.",
               "ja_certo": "Conferido na lista: a folha já está certa.",
               "repetido": "Conferido na lista: é o mesmo caso de outro problema já tratado."}
ROTULO_ACAO = {"deste_projeto": "É deste projeto", "mover": "Mover para outro projeto", "mesma_folha": "É a mesma folha",
               "diferentes": "São diferentes", "metadado": "Salvar o dado", "nao_e_problema": "Não é problema", "fica_fora": "É de outro projeto (fica fora)"}
CAMPOS = {"ano_folha": "Ano da folha", "titulo": "Título da folha"}
ACOES = ("deste_projeto", "mesma_folha", "diferentes", "metadado", "nao_e_problema", "fica_fora")
_DOC = re.compile(r"^(F\d{3})-(P\d{4})-(\d{4})-(S0[1-8]|S99)-D(\d{4,6})$")     # o mesmo CODIGO_DOCUMENTO do importador
MINI_LADO = 240
MOVER_FORA = ("esta folha ainda não entrou no painel (o CAMP Vision a deixou fora do lote), então não dá para mover: \"É deste projeto\" a devolve ao lote; "
              "se for de outro projeto, ela fica fora e o CAMP Vision precisa reidentificar o lote para levá-la ao projeto certo")
_CARIMBO = re.compile(r"carimbo diz\s*:?\s*[\"'“‘«]([^\"'”’»]{2,160})", re.I)
_FOLHA = re.compile(r"\bF\d{3}-P\d{4}-\d{4}-S\d{2}-D\d{5}\b")


def _sem_acento(t) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(ch) != "Mn").lower()


def carimbo_de(descricao) -> str | None:
    """O que o carimbo diz, quando o CAMP Vision escreveu ("projeto divergente: o carimbo diz 'SIERNA 3 · BAIRRO DO LIMÃO'")."""
    m = _CARIMBO.search(str(descricao or ""))
    return m.group(1).strip() if m else None


def campo_metadado(descricao) -> str | None:
    """O dado simples que falta, pela descrição ("Documento sem data identificada" → ano da folha; "sem título" → título)."""
    t = _sem_acento(descricao)
    if re.search(r"\b(data|ano|datad[oa])\b", t):
        return "ano_folha"
    if re.search(r"\b(titulo|sem nome)\b", t):
        return "titulo"
    return None


def texto_modelo(con, acao: str) -> tuple[str, str]:
    cat, tit, padrao = MODELO[acao]
    r = con.execute("SELECT texto FROM erro_modelo WHERE categoria=? AND titulo=? AND ativo=1", (cat, tit)).fetchone()
    return ((r[0] or "").strip() or padrao) if r else padrao, tit


def tipo_rapido(x: dict) -> str | None:
    from .importador_lote import fala_de_projeto_divergente
    cat = x.get("categoria")
    if cat == "projeto_errado" or (x.get("origem") == "campvision" and fala_de_projeto_divergente(x.get("descricao"))):
        if x.get("folha") and (x.get("folha_existe") or fora_do_painel(x)):
            return "outro_projeto"
        return None
    if cat == "duplicata" and x.get("folha_existe"):
        return "duplicata"
    if cat == "metadado" and x.get("folha_existe") and campo_metadado(x.get("descricao")):
        return "metadado"
    return None


def fora_do_painel(x: dict) -> bool:
    """CAMP-PROB-REAL: a folha que o CAMP Vision RETIROU do lote ("fora da publicação até decisão") não está na tabela de folhas. Na produção ela
    tem DOIS problemas abertos: o da retirada (chave campvision:retirado:<folha>, 'corrigir') e o do erros.json (código = a folha, 'bloqueia',
    chave campvision:erros:…). Antes só o primeiro tinha ação: o filtro Críticos mostrava só o segundo, sem nenhum botão. "É deste projeto"
    vale para os dois (`rotas_revisao._deste_projeto_retirada` procura por código OU chave)."""
    f = x.get("folha")
    if not f or x.get("folha_existe") or x.get("folha_atual") or not _DOC.match(str(f)):
        return False
    return x.get("tipo") == "retirada" or x.get("origem") == "campvision"


def motivo_sensivel(con, categoria: str) -> str | None:
    if categoria in TIPOS_SENSIVEIS:
        return "Autoria e crédito pedem fonte: resolva pelo painel (Analisar)."
    if cp.precisa_revisao(con, categoria):
        return "Este tipo precisa da revisão de outra pessoa: resolva pelo painel (Enviar para revisão)."
    return None


def url_previa(codigo: str, item=None, lado: int = 0) -> str | None:
    """CAMP-PROB-REAL: a imagem da folha pela MESMA rota que o resto do painel usa (`GET /api/itens/{c}/previa`: a prévia do CAMP Vision em
    _campvision/preview, o JPG da folha no QNAP (`arquivo_jpg`) ou, para a folha retirada que não está no painel, a prévia do pacote / o JPG
    da pasta do lote). Antes só havia URL com `pendencias.previa` preenchido ou `arquivo_jpg` http(s): na produção `arquivo_jpg` é caminho
    do QNAP e a prévia muitas vezes vem vazia, então TODA miniatura era "sem imagem". Não abre arquivo nenhum aqui (nada de QNAP na listagem):
    None só quando é certo que não há imagem (folha no painel sem prévia e sem JPG); o resto a tela mostra e, se a rota não achar, o aviso neutro."""
    if not codigo:
        return None
    q = f"?t={lado}" if lado else ""
    if item is None:
        return f"/api/itens/{codigo}/previa{q}" if _DOC.match(str(codigo)) else None
    try:
        pend = json.loads(item["pendencias"] or "{}") if isinstance(item["pendencias"], str) else {}
    except ValueError:
        pend = {}
    pend = pend if isinstance(pend, dict) else {}
    jpg = str(item["arquivo_jpg"] or "")
    if not pend.get("previa") and jpg.startswith(("http://", "https://")):
        return jpg
    if pend.get("previa") or jpg:
        return f"/api/itens/{codigo}/previa{q}"
    from .importador_lote import fala_de_projeto_divergente
    if any(fala_de_projeto_divergente(t) for k in ("sinais", "bloqueios") for t in (pend.get(k) or []) if isinstance(pend.get(k), list)):
        return f"/api/itens/{codigo}/previa{q}"     # a rota procura a imagem na pasta do lote (CAMP-069)
    return None


def miniaturas(con, folhas, lado: int = MINI_LADO) -> dict:
    """A miniatura de cada folha (`url_previa`): as que estão no painel e as que o CAMP Vision deixou fora do lote."""
    out = {}
    folhas = [f for f in dict.fromkeys(folhas) if f]
    achadas = set()
    for i in range(0, len(folhas), 400):
        parte = folhas[i:i + 400]
        for r in con.execute(f"SELECT codigo, arquivo_jpg, pendencias FROM item WHERE codigo IN ({','.join('?' * len(parte))})", parte):
            achadas.add(r["codigo"])
            u = url_previa(r["codigo"], r, lado)
            if u:
                out[r["codigo"]] = u
    for f in folhas:
        if f not in achadas:
            u = url_previa(f, None, lado)
            if u:
                out[f] = u
    return out


class _Sugestoes:
    """O projeto do MESMO fundo cujo nome combina com o que o carimbo diz (a nota do UX-01: nome da pasta × título). Só sugere com uma
    vencedora clara (≥ 0,5, sem empate) e que combine mais do que o projeto atual; quem decide é a pessoa (mover pede confirmação)."""

    def __init__(self, con):
        self.con, self.projs, self.cache = con, {}, {}

    def __call__(self, fundo: str | None, atual: str | None, carimbo: str | None) -> dict | None:
        if not (fundo and atual and carimbo):
            return None
        k = (fundo, atual, carimbo)
        if k in self.cache:
            return self.cache[k]
        from .destino_lote import LIMIAR_PASTA, nota
        if fundo not in self.projs:
            self.projs[fundo] = [dict(r) for r in self.con.execute(
                "SELECT codigo, titulo, identificacao_original FROM projeto WHERE fundo_codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL", (fundo,))]
        notas, minha = [], 0.0
        for p in self.projs[fundo]:
            n = nota(carimbo, p) or 0.0
            if p["codigo"] == atual:
                minha = n
            elif n >= LIMIAR_PASTA:
                notas.append((n, p))
        notas.sort(key=lambda t: (-t[0], t[1]["codigo"]))
        s = None
        if notas and notas[0][0] > minha and (len(notas) == 1 or notas[1][0] < notas[0][0]):
            p = notas[0][1]
            s = {"codigo": p["codigo"], "titulo": p["titulo"], "nota": round(notas[0][0], 2)}
        self.cache[k] = s
        return s


def anotar(con, itens: list[dict], u: dict, sug: _Sugestoes | None = None) -> None:
    """Acrescenta a cada problema aberto (campos novos, opcionais) `miniatura` e `rapido`: o tipo de decisão rápida, as ações que ESTA pessoa
    pode fazer na linha, o que o carimbo diz, a sugestão de projeto, a original da duplicata ou o campo que falta. Tipo sensível: `sensivel`."""
    papel = u.get("papel")
    pode, admin = papel in ("operador", "admin", "master"), papel in ("admin", "master")
    sug = sug or _Sugestoes(con)
    mini = miniaturas(con, [x.get("folha") for x in itens if x.get("folha") and (x.get("folha_existe") or fora_do_painel(x))])
    dups = {}
    fl = [x["folha"] for x in itens if x.get("categoria") == "duplicata" and x.get("folha_existe")]
    if fl:
        dups = {r[0]: r[1] for r in con.execute(f"SELECT codigo, duplicata_de FROM item WHERE codigo IN ({','.join('?' * len(fl))})", fl)}
    for x in itens:
        x["miniatura"] = mini.get(x.get("folha"))
        x["rapido_motivo"] = None
        if not x.get("aberto"):
            x["rapido"] = None
            continue
        sens = motivo_sensivel(con, x.get("categoria"))
        if sens:
            x["rapido"] = {"sensivel": True, "motivo": sens, "acoes": [], "nao_e_problema": False}
            x["rapido_motivo"] = sens
            continue
        if x.get("fase") not in FASES_RAPIDAS:
            x["rapido"] = None
            x["rapido_motivo"] = f"Está em “{x.get('fase_rotulo') or x.get('fase')}”: continue pelo painel ({x.get('cta') or 'Continuar'})."
            continue
        t = tipo_rapido(x)
        r = {"tipo": t, "acoes": [], "nao_e_problema": pode}
        if t == "outro_projeto":
            car = carimbo_de(x.get("descricao"))
            r.update(carimbo=car, sem_identificacao="sem identificacao" in _sem_acento(x.get("descricao")), acoes=["deste_projeto"], sugestao=None)
            if x.get("folha_existe"):
                if admin:
                    r["acoes"] += ["mover", "escolher"]
                else:
                    r["mover_porque_nao"] = "mover a folha para outro projeto é com um admin"
                r["sugestao"] = sug(x.get("fundo_codigo"), x.get("projeto_codigo"), car)
            else:          # CAMP-PROB-REAL: retirada pelo CAMP Vision, fora do painel: devolver ao lote ou deixar fora (mover não existe para ela)
                r["fora_do_painel"] = True
                r["acoes"] += ["fica_fora"]
                r["mover_porque_nao"] = MOVER_FORA
        elif t == "duplicata":
            orig = dups.get(x["folha"])
            if not orig:
                outros = [c for c in _FOLHA.findall(str(x.get("descricao") or "")) if c != x["folha"]]
                orig = outros[0] if outros and con.execute("SELECT 1 FROM item WHERE codigo=?", (outros[0],)).fetchone() else None
            r.update(original=orig, original_miniatura=miniaturas(con, [orig]).get(orig) if orig else None,
                     acoes=(["mesma_folha"] if orig else []) + ["diferentes"])
        elif t == "metadado":
            c_ = campo_metadado(x.get("descricao"))
            r.update(campo=c_, campo_rotulo=CAMPOS[c_], acoes=["metadado"])
        if not pode:
            r["acoes"], r["nao_e_problema"] = [], False
        x["rapido"] = r
        if not r["acoes"]:
            x["rapido_motivo"] = por_que_sem_acao(x, t, pode)


def por_que_sem_acao(x: dict, t: str | None, pode: bool) -> str:
    """CAMP-PROB-REAL (diagnóstico): por que esta linha não tem decisão rápida. Nenhuma linha fica sem ação sem dizer por quê."""
    if not pode:
        return "Seu acesso é só de leitura: quem resolve é a equipe (operador ou admin)."
    cat, f = x.get("categoria"), x.get("folha")
    from .importador_lote import fala_de_projeto_divergente
    if cat == "projeto_errado" or (x.get("origem") == "campvision" and fala_de_projeto_divergente(x.get("descricao"))):
        if not f:
            return "O problema é do projeto inteiro (não diz qual folha): abra o projeto e confira as folhas."
        if x.get("folha_atual"):
            return f"A folha mudou de código (agora é {x['folha_atual']}): abra o problema para conferir."
        if not _DOC.match(str(f)):
            return f"O código da folha ({f}) não está no formato do painel: abra o problema."
        return "Esta folha não está no painel e não foi o CAMP Vision que a retirou: abra o problema para conferir."
    if cat == "duplicata":
        return "A folha não está no painel: abra o problema." if not x.get("folha_existe") else "Escolha no painel qual é a original."
    if cat == "metadado" and x.get("folha_existe"):
        return "O dado que falta não é ano nem título: abra o problema e corrija na folha."
    rot = (x.get("tipo_rotulo") or "este tipo").lower()
    return f"“{x.get('tipo_rotulo') or 'Este tipo'}” ainda não tem decisão rápida na lista: abra o problema (Analisar)." if rot else "Abra o problema (Analisar)."


def agrupar_linhas(itens: list[dict], minimo: int = 2) -> list[dict]:
    """O mesmo projeto + o mesmo tipo (e o mesmo jeito: retirada, recusada, comum) viram UMA linha, no lugar do primeiro (o mais prioritário).
    Só abertos com projeto; menos de `minimo`, ficam soltos. A linha do grupo leva os problemas inteiros em `membros` (a tela mostra as miniaturas
    e "Ver uma a uma")."""
    chave = lambda x: (x.get("projeto_codigo"), x.get("categoria"), x.get("tipo")) if x.get("aberto") and x.get("projeto_codigo") else None
    conta = {}
    for x in itens:
        k = chave(x)
        if k:
            conta[k] = conta.get(k, 0) + 1
    linhas, grupos = [], {}
    for x in itens:
        k = chave(x)
        if not k or conta[k] < minimo:
            linhas.append(x)
            continue
        if k not in grupos:
            g = {"grupo": True, "chave": "|".join(str(p) for p in k), "projeto_codigo": x.get("projeto_codigo"), "projeto_titulo": x.get("projeto_titulo"),
                 "fundo_codigo": x.get("fundo_codigo"), "fundo_titulo": x.get("fundo_titulo"), "categoria": x.get("categoria"), "tipo": x.get("tipo"),
                 "titulo": x.get("titulo"), "tipo_rotulo": x.get("tipo_rotulo"), "severidade": x.get("severidade"), "severidade_rotulo": x.get("severidade_rotulo"),
                 "gravidade": x.get("gravidade"), "prioridade": x.get("prioridade"), "aberto": True, "membros": [], "id": "g:" + "|".join(str(p) for p in k)}
            grupos[k] = g
            linhas.append(g)
        grupos[k]["membros"].append(x)
    for g in grupos.values():
        m = g["membros"]
        g["n"] = len(m)
        g["ids"] = [x["id"] for x in m]
        g["idade_dias"] = max((x.get("idade_dias") or 0) for x in m)
        g["criticos"] = sum(1 for x in m if x.get("gravidade") == "bloqueia")
    return linhas


def rapido_do_grupo(g: dict, u: dict) -> None:
    """As ações do grupo inteiro (a partir das de cada membro): só "Folha pode ser de outro projeto" tem ação para todas; o resto, "Ver uma a uma"."""
    m = g["membros"]
    rs = [x.get("rapido") or {} for x in m]
    g["miniaturas"] = [x.get("miniatura") for x in m[:8]]
    if all(r.get("tipo") == "outro_projeto" for r in rs) and rs:
        acoes = [a for a in ("deste_projeto", "fica_fora", "mover") if all(a in r.get("acoes", []) for r in rs)]
        sugs = {json.dumps(r.get("sugestao"), sort_keys=True) for r in rs}
        fora = sum(1 for r in rs if r.get("fora_do_painel"))
        nota = None
        if "mover" not in acoes:   # CAMP-PROB-REAL: diz por que não há "Mover todas para…" (antes o grupo só tinha "Ver uma a uma")
            nota = ("Mover: " + MOVER_FORA.replace("esta folha ainda não entrou", "estas folhas ainda não entraram").replace("a deixou", "as deixou")
                    .replace("a devolve", "as devolve").replace("ela fica", "elas ficam").replace("levá-la", "levá-las")) if fora == len(rs) else \
                   (f"Mover: {fora} das {len(rs)} folhas ainda não entraram no painel; mova uma a uma as que estão no painel." if fora else
                    ("Mover: " + (rs[0].get("mover_porque_nao") or "não vale para todas") + "."))
        g["rapido"] = {"tipo": "outro_projeto", "acoes": acoes, "sugestao": rs[0].get("sugestao") if len(sugs) == 1 and "mover" in acoes else None,
                       "carimbos": sorted({r.get("carimbo") for r in rs if r.get("carimbo")})[:5], "fora_do_painel": fora == len(rs), "nota": nota}
        if not acoes:
            g["rapido"]["motivo"] = next((x.get("rapido_motivo") for x in m if x.get("rapido_motivo")), "As folhas do grupo pedem decisões diferentes: veja uma a uma.")
    else:
        sem = [x for x in m if not (x.get("rapido") or {}).get("acoes")]
        mot = next((x.get("rapido_motivo") for x in sem if x.get("rapido_motivo")), None)
        g["rapido"] = {"tipo": None, "acoes": [], "motivo": ("Sem decisão para o grupo inteiro: " + (mot or "cada problema pede a sua.")) if mot or sem else
                       "Cada problema tem a sua decisão: veja uma a uma."}


# ---------------- guardar o antes (para o Desfazer) ----------------
ERRO_CAMPOS = ("situacao", "resolucao", "resolvido_em", "fechado_por", "fase", "fase_em", "motivo_pendencia")


def _snap_erros(con, ids: list[int], folhas: list[str]) -> dict:
    """Os problemas que a ação pode mexer: os escolhidos e os abertos das mesmas folhas (o "É deste projeto" fecha os do CAMP Vision da folha)."""
    w, p = [f"id IN ({','.join('?' * len(ids))})"], list(ids)
    fl = [f for f in dict.fromkeys(folhas) if f]
    if fl:
        w.append(f"(situacao IN ('aberto','em_correcao') AND (codigo IN ({','.join('?' * len(fl))}) OR chave IN ({','.join('?' * len(fl))})))")
        p += fl + [f"campvision:retirado:{f}" for f in fl]
    return {r["id"]: dict(r) for r in con.execute(f"SELECT id, {', '.join(ERRO_CAMPOS)} FROM erro WHERE " + " OR ".join(w), p)}


def _entradas_erros(con, antes: dict) -> list[dict]:
    out = []
    for i, a in antes.items():
        r = con.execute(f"SELECT {', '.join(ERRO_CAMPOS)} FROM erro WHERE id=?", (i,)).fetchone()
        if r and any(r[c] != a[c] for c in ERRO_CAMPOS):
            out.append({"id": i, **{c: a[c] for c in ERRO_CAMPOS}, "depois": r["situacao"]})
    return out


def _snap_itens(con, codigos: list[str]) -> dict:
    from .rotas_operacao import ITEM_CAMPOS_DESFAZER
    cods = [c for c in dict.fromkeys(codigos) if c]
    if not cods:
        return {}
    q = ",".join("?" * len(cods))
    rows = con.execute(f"SELECT codigo, {', '.join(ITEM_CAMPOS_DESFAZER)} FROM item WHERE codigo IN ({q}) OR duplicata_de IN ({q})", cods + cods).fetchall()
    return {r["codigo"]: {c: r[c] for c in ITEM_CAMPOS_DESFAZER} for r in rows}


def _entradas_itens(con, antes: dict) -> list[dict]:
    from .rotas_operacao import ITEM_CAMPOS_DESFAZER
    out = []
    for c, a in antes.items():
        r = con.execute(f"SELECT {', '.join(ITEM_CAMPOS_DESFAZER)} FROM item WHERE codigo=?", (c,)).fetchone()
        if not r:
            continue
        mud = [k for k in ITEM_CAMPOS_DESFAZER if r[k] != a[k]]
        if mud:
            out.append({"item": c, "campos": {k: a[k] for k in mud}, "depois": {k: r[k] for k in mud}})
    return out


# ---------------- carregar e conferir ----------------
def _carregar(con, ids: list[int], u: dict) -> list[dict]:
    ids = list(dict.fromkeys(int(i) for i in ids))
    if not ids:
        raise HTTPException(400, "Escolha pelo menos um problema")
    if len(ids) > MAX_IDS:
        raise HTTPException(400, f"No máximo {MAX_IDS} de uma vez")
    rows = con.execute(f"SELECT * FROM erro WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    if len(rows) != len(ids):
        raise HTTPException(404, f"{len(ids) - len(rows)} dos problemas escolhidos não existem mais: atualize a lista")
    itens = cp.enriquecer(con, rows, u)
    anotar(con, itens, u)
    ordem = {i: k for k, i in enumerate(ids)}
    return sorted(itens, key=lambda x: ordem[x["id"]])


def _por_que_nao(x: dict, acao: str) -> str | None:
    """None = esta ação rápida vale para este problema; senão, o porquê (vai para a tela)."""
    r = x.get("rapido")
    if not x.get("aberto"):
        return "já está fechado"
    if r and r.get("sensivel"):
        return r["motivo"]
    if r is None:
        return f"está em \"{x.get('fase_rotulo')}\": continue pelo painel"
    if acao == "nao_e_problema":
        return None if r.get("nao_e_problema") else "você não pode fechar problemas"
    if acao not in (r.get("acoes") or []):
        return "esta decisão não vale para este problema"
    return None


def _resolver(con, x: dict, acao: str, u: dict, detalhe: str = "") -> None:
    texto, tit = texto_modelo(con, acao)
    cp.mudar_fase(con, x["id"], cp.MudarFase(fase="resolvido", conclusao=(texto + detalhe)[:2000],
                                              justificativa=f"Ação rápida na lista de problemas: {ROTULO_ACAO[acao]} (modelo “{tit}”)."),
                  u, extra={"rapido": acao, "modelo": tit})


def _onde(x: dict) -> str:
    return f" ({x.get('projeto_codigo')} · {x.get('projeto_titulo')})" if x.get("projeto_codigo") and x.get("projeto_titulo") else ""


def _aplicar_um(con, x: dict, acao: str, d, u: dict, extras: list[dict]) -> None:
    """Resolve UM problema pela ação rápida (transação aberta por quem chama). O problema é resolvido ANTES do efeito na folha: o efeito
    (que fecha os outros problemas da mesma folha) não mexe mais nele."""
    folha = x.get("folha")
    if acao == "nao_e_problema":
        just = MOTIVOS_NAO.get(d.motivo or "") or MOTIVOS_NAO["sem_efeito"]
        cp.mudar_fase(con, x["id"], cp.MudarFase(fase="invalido", justificativa=just), u, extra={"rapido": acao, "motivo": d.motivo or "sem_efeito"})
        return
    if acao == "deste_projeto":
        _resolver(con, x, acao, u, f" Fica em {x.get('projeto_codigo')}" + (f" · {x.get('projeto_titulo')}" if x.get("projeto_titulo") else "") + ".")
        from .rotas_revisao import deste_projeto
        ult_cv = (con.execute("SELECT MAX(id) FROM cv_resposta").fetchone()[0] or 0)
        ult_ev = (con.execute("SELECT MAX(id) FROM evento").fetchone()[0] or 0)
        deste_projeto(con, folha, u)
        for r in con.execute("SELECT id FROM cv_resposta WHERE id>? AND chave=?", (ult_cv, folha)):
            extras.append({"cv_resposta": r[0]})
        if con.execute("SELECT 1 FROM evento WHERE id>? AND entidade='item' AND codigo=? AND tipo='projeto_confirmado'", (ult_ev, folha)).fetchone():
            extras.append({"evento": {"entidade": "item", "codigo": folha, "tipo": "projeto_confirmado_desfeito",
                                      "detalhe": {"desfeito_por": "Desfazer da ação rápida", "erro": x["id"]}}})
        return
    if acao == "fica_fora":
        # o mesmo efeito do "É de outro projeto…" da página do projeto (fpOutro): a folha continua fora; os problemas do CAMP Vision sobre ela fecham
        _resolver(con, x, acao, u, f" Fica fora de {x.get('projeto_codigo')}" + (f" · {x.get('projeto_titulo')}" if x.get("projeto_titulo") else "") + ".")
        from .importador_lote import fala_de_projeto_divergente
        texto, _tit = texto_modelo(con, acao)
        for r in con.execute("""SELECT id, categoria, descricao, chave FROM erro WHERE origem='campvision' AND situacao IN ('aberto','em_correcao') AND id<>?
                                AND (codigo=? OR chave=?)""", (x["id"], folha, f"campvision:retirado:{folha}")).fetchall():
            if r["chave"] == f"campvision:retirado:{folha}" or r["categoria"] == "projeto_errado" or fala_de_projeto_divergente(r["descricao"]):
                con.execute("""UPDATE erro SET situacao='corrigido', fase='resolvido', fase_em=datetime('now'), resolvido_em=datetime('now'), resolucao=?,
                               fechado_por=?, motivo_pendencia=NULL WHERE id=?""", (f"É de outro projeto: {texto}"[:2000], u["email"], r["id"]))
                cp._evento(con, r["id"], "fase", u["email"], {"de": None, "para": "resolvido", "rapido": acao, "junto_de": x["id"], "credito": u["email"]})
        return
    if acao == "mesma_folha":
        orig = (x.get("rapido") or {}).get("original")
        _resolver(con, x, acao, u, f" Cópia de {orig}.")
        from .rotas_mesclar import marcar_duplicata_em
        marcar_duplicata_em(con, folha, orig, "mesma_folha", u)
        return
    if acao == "diferentes":
        _resolver(con, x, acao, u)
        a = con.execute("SELECT duplicata_de, tipo_duplicata, status_site, pendencias, autoria_divergente FROM item WHERE codigo=?", (folha,)).fetchone()
        if a and a["duplicata_de"]:
            from .rotas_mesclar import liberar_bloqueios_de_duplicata
            liberou = liberar_bloqueios_de_duplicata(con, folha, a, u["email"])
            con.execute("""UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?,
                           duplicata_conferida_de=?, atualizado_em=datetime('now') WHERE codigo=?""", (u["email"], a["duplicata_de"], folha))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_desmarcada',?,?)",
                        (folha, u["email"], json.dumps({"era_de": a["duplicata_de"], "tipo": a["tipo_duplicata"], "rapido": True, **liberou}, ensure_ascii=False)))
        else:      # uma pessoa conferiu: não volta como sugestão de cópia (a mesma marca da tela Duplicatas)
            con.execute("""UPDATE item SET duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?, duplicata_conferida_de=NULL, atualizado_em=datetime('now')
                           WHERE codigo=?""", (u["email"], folha))
        return
    raise HTTPException(400, "Ação inválida")


class Rapida(BaseModel):
    ids: list[int]
    acao: str
    motivo: str | None = None      # "Não é problema": sem_efeito · ja_certo · repetido
    valor: str | None = None       # dado simples (ano ou título)


def _guardar(con, ator: str, acao: str, sit: str, antes: list[dict]) -> int | None:
    from .rotas_operacao import _guardar_desfazer
    return _guardar_desfazer(con, ator, "rapido:" + acao, sit, antes)


@router.post("")
def rota_rapida(d: Rapida, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Uma ação rápida para um ou vários problemas (o grupo). O que não vale para algum deles fica de fora e a resposta diz por quê
    (`pulados`); se nenhum vale, 409 e nada muda. Erro no meio = nada muda (tudo numa transação). Devolve o token do Desfazer."""
    if d.acao not in ACOES:
        raise HTTPException(400, "Ação inválida")
    con = connect()
    try:
        itens = _carregar(con, d.ids, u)
        pulados = [{"id": x["id"], "motivo": m} for x in itens if (m := _por_que_nao(x, d.acao))]
        validos = [x for x in itens if not _por_que_nao(x, d.acao)]
        if not validos:
            raise HTTPException(409, "Sem decisão rápida aqui: " + pulados[0]["motivo"] if pulados else "Nada a fazer")
        if d.acao == "nao_e_problema" and d.motivo and d.motivo not in MOTIVOS_NAO:
            raise HTTPException(400, "Motivo inválido")
        extras: list[dict] = []
        if d.acao == "metadado":
            if len(validos) != 1:
                raise HTTPException(400, "O dado se corrige um problema por vez")
            extras.append(_salvar_dado(con, validos[0], d.valor, tarefas, u))
        folhas = [x.get("folha") for x in validos]
        con.execute("BEGIN IMMEDIATE")
        try:
            antes_e = _snap_erros(con, [x["id"] for x in validos], folhas)
            antes_i = _snap_itens(con, folhas + [(x.get("rapido") or {}).get("original") for x in validos])
            for x in validos:
                if d.acao == "metadado":
                    r = (x.get("rapido") or {})
                    _resolver(con, x, "metadado", u, f" {r.get('campo_rotulo')}: {extras[0]['metadado']['depois']}.")
                else:
                    _aplicar_um(con, x, d.acao, d, u, extras)
            entradas_e = _entradas_erros(con, antes_e)
            antes = entradas_e + _entradas_itens(con, antes_i) + extras
            tok = _guardar(con, u["email"], d.acao, "corrigido" if d.acao != "nao_e_problema" else "ignorado", antes)
            con.commit()
        except Exception:
            con.rollback()
            raise
        n = len(validos)
        # curto e neutro (Rafael: "não quero que fique infantil o sistema, é algo bem sério"): "Resolvido." / "3 resolvidos."
        msg = ("Fechado: não é problema." if n == 1 else f"{n} fechados: não é problema.") if d.acao == "nao_e_problema" else ("Resolvido." if n == 1 else f"{n} resolvidos.")
        # `fechados` (campo novo, opcional): todos os problemas que a ação fechou, inclusive os da mesma folha (a tela tira as linhas deles também)
        return {"ok": True, "acao": d.acao, "resolvidos": [x["id"] for x in validos], "pulados": pulados, "desfazer": tok, "mensagem": msg,
                "fechados": sorted({e["id"] for e in entradas_e if e.get("depois") not in ("aberto", "em_correcao")})}
    finally:
        con.close()


def _salvar_dado(con, x: dict, valor: str | None, tarefas: BackgroundTasks, u: dict) -> dict:
    """O dado simples pela rota de editar a folha de sempre (PATCH /api/itens/{c}: valida, grava e manda ao site se a folha está lá)."""
    from .rotas_itens import EdicaoItem, editar_item
    campo = (x.get("rapido") or {}).get("campo")
    v = (valor or "").strip()
    if campo == "ano_folha":
        if not re.fullmatch(r"\d{4}", v) or not (1800 <= int(v) <= 2100):
            raise HTTPException(400, "Escreva o ano com 4 algarismos (ex.: 1971)")
        novo = int(v)
    elif campo == "titulo":
        if len(v) < 2:
            raise HTTPException(400, "Escreva o título da folha")
        novo = v
    else:
        raise HTTPException(400, "Este problema não tem um dado simples para preencher aqui")
    antigo = con.execute(f"SELECT {campo} FROM item WHERE codigo=?", (x["folha"],)).fetchone()[0]
    editar_item(x["folha"], EdicaoItem(**{campo: novo}), tarefas, u)
    return {"metadado": {"folha": x["folha"], "campo": campo, "antes": antigo, "depois": novo}}


# ---------------- mover (só admin; pela rota de mover de sempre, simulação primeiro) ----------------
class MoverRapido(BaseModel):
    ids: list[int]
    destino: str
    simular: bool = True


@router.post("/mover")
def rota_mover(d: MoverRapido, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Mover para <projeto>" (uma folha ou o grupo): PRIMEIRO a simulação (`simular`, o padrão) pela rota de mover de sempre
    (`POST /api/itens/mover` com simular: códigos novos, cópias, recusas), DEPOIS o mover de verdade pela mesma rota (mesmas regras: só admin, só o
    mesmo fundo; o registro antigo sai do público no site e o 301 vai ao site). Cada problema fica Resolvido com a conclusão do modelo
    "Movida para o projeto certo" e os pontos da Home. Desfazer: a folha volta pela mesma rota (simulação primeiro) e o problema reabre."""
    from .rotas_mesclar import MoverItens, mover_itens
    destino = (d.destino or "").strip().upper()
    if not re.fullmatch(r"F\d{3}-P\d{4}", destino):
        raise HTTPException(400, "Escolha o projeto de destino (código F000-P0000)")
    con = connect()
    try:
        itens = _carregar(con, d.ids, u)
        pulados = [{"id": x["id"], "motivo": m} for x in itens if (m := _por_que_nao(x, "mover"))]
        validos = [x for x in itens if not _por_que_nao(x, "mover")]
        mesmos = [x for x in validos if x.get("projeto_codigo") == destino]
        if mesmos:
            raise HTTPException(400, "A folha já está nesse projeto: escolha outro (ou \"É deste projeto\")")
        if not validos:
            raise HTTPException(409, "Sem decisão rápida aqui: " + pulados[0]["motivo"] if pulados else "Nada a mover")
        dest = con.execute("SELECT codigo, titulo FROM projeto WHERE codigo=?", (destino,)).fetchone()
        folhas = [x["folha"] for x in validos]
        antes_e = _snap_erros(con, [x["id"] for x in validos], folhas)
    finally:
        con.close()
    motivo = f"Problema nº {', '.join(str(x['id']) for x in validos[:20])}: a folha é de {destino}" + (" (ação rápida na lista de problemas)")
    sim = mover_itens(MoverItens(itens=folhas, destino=destino, motivo=motivo, simular=True), tarefas, u)   # recusa (400/409) aqui, antes de mudar algo
    base = {"destino": {"codigo": destino, "titulo": dest["titulo"] if dest else None}, "problemas": [x["id"] for x in validos], "pulados": pulados,
            "movidos": sim.get("movidos") or [], "duplicatas": sim.get("duplicatas") or [], "ignorados": sim.get("ignorados") or []}
    if d.simular:
        return {"ok": True, "simulado": True, **base}
    r = mover_itens(MoverItens(itens=folhas, destino=destino, motivo=motivo, simular=False), tarefas, u)
    novo = {m["de"]: m["para"] for m in r.get("movidos") or []}
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        texto, tit = texto_modelo(con, "mover")
        for x in validos:
            para = novo.get(x["folha"])
            conc = (texto + (f" Agora é {para} ({destino}" + (f" · {dest['titulo']}" if dest and dest["titulo"] else "") + ")." if para else f" ({destino})."))[:2000]
            just = f"Ação rápida na lista de problemas: {ROTULO_ACAO['mover']} (modelo “{tit}”)."
            e = con.execute("SELECT situacao, fase, resolucao, duplicado_de FROM erro WHERE id=?", (x["id"],)).fetchone()
            if e["situacao"] in ("aberto", "em_correcao"):          # o mover não fechou sozinho (ex.: virou cópia de uma folha do destino): resolve pelo fluxo
                cp.mudar_fase(con, x["id"], cp.MudarFase(fase="resolvido", conclusao=conc, justificativa=just), u, extra={"rapido": "mover", "modelo": tit})
            else:                                                   # fechou sozinho ao mover ("Resolvido sozinho: …"): fica a conclusão do modelo e quem fez
                cp._add_evidencia(con, x["id"], just, None, u["email"], tipo="justificativa")
                con.execute("UPDATE erro SET situacao='corrigido', fase='resolvido', fase_em=datetime('now'), resolucao=?, fechado_por=?, motivo_pendencia=NULL WHERE id=?",
                            (conc, u["email"], x["id"]))
                cp._evento(con, x["id"], "fase", u["email"], {"de": x.get("fase"), "para": "resolvido", "conclusao": conc, "credito": u["email"],
                                                               "rapido": "mover", "modelo": tit, "validado_por_revisao": False})
        antes = _entradas_erros(con, antes_e) + [{"mover": {"de": x["folha"], "para": novo.get(x["folha"]), "origem": x.get("projeto_codigo"), "erro": x["id"]}}
                                                 for x in validos if novo.get(x["folha"])]
        tok = _guardar(con, u["email"], "mover", "corrigido", antes)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    n = len(validos)
    return {"ok": True, "simulado": False, **base, "movidos": r.get("movidos") or [], "duplicatas": r.get("duplicatas") or [],
            "site_antigo": r.get("site_antigo"), "resolvidos": [x["id"] for x in validos], "desfazer": tok,
            "mensagem": (f"Movida para {destino}. Resolvido." if n == 1 else f"{n} movidas para {destino}. {n} resolvidos.")}


# ---------------- Desfazer ----------------
class Desfazer(BaseModel):
    simular: bool = False          # mover: True mostra para onde cada folha volta (nada muda)


@router.post("/desfazer/{token}")
def rota_desfazer(token: int, tarefas: BackgroundTasks, d: Desfazer | None = None, u: dict = Depends(auth.exige("operador"))) -> dict:
    """O Desfazer da ação rápida: o mesmo `erro_desfazer` (só quem fez ou um admin, uma vez, até 30 min). Problema e folha voltam ao que
    eram (o que alguém mexeu depois fica como está, e a resposta diz quantos). Mover: a folha volta pela rota de mover de sempre (admin;
    `simular` mostra antes para onde) e o problema reabre seguindo a folha."""
    from .rotas_operacao import DESFAZER_MINUTOS, desfazer_antes
    d = d or Desfazer()
    con = connect()
    try:
        r = con.execute("SELECT * FROM erro_desfazer WHERE id=?", (token,)).fetchone()
        if not r:
            raise HTTPException(404, "Não há o que desfazer")
        if r["ator"] != u["email"] and u["papel"] not in ("admin", "master"):
            raise HTTPException(403, "Só quem fez (ou um admin) pode desfazer")
        if r["desfeito_em"]:
            raise HTTPException(409, "Já foi desfeito")
        if con.execute("SELECT datetime(?, ?) < datetime('now')", (r["criado_em"], f"+{DESFAZER_MINUTOS} minutes")).fetchone()[0]:
            raise HTTPException(409, f"Passou o prazo de {DESFAZER_MINUTOS} minutos para desfazer: reabra pelo painel do problema")
        acao = str(r["acao"] or "")
        antes = json.loads(r["antes"] or "[]")
        if acao == "rapido:mover":
            return _desfazer_mover(con, token, r, antes, d.simular, tarefas, u)
        if d.simular:
            return {"ok": True, "simulado": True, "problemas": sum(1 for a in antes if "id" in a)}
        for a in antes:              # o dado da folha volta pela rota de editar a folha (só se ninguém mexeu depois)
            m = a.get("metadado")
            if m:
                atual = con.execute(f"SELECT {m['campo']} FROM item WHERE codigo=?", (m["folha"],)).fetchone()
                if atual and atual[0] == m["depois"]:
                    from .rotas_itens import EdicaoItem, editar_item
                    editar_item(m["folha"], EdicaoItem(**{m["campo"]: (m["antes"] if m["antes"] is not None else (0 if m["campo"] == "ano_folha" else ""))}), tarefas, u)
        con.execute("BEGIN IMMEDIATE")
        voltaram, ficaram = desfazer_antes(con, [a for a in antes if "metadado" not in a], r["situacao"], acao, u["email"])
        con.execute("UPDATE erro_desfazer SET desfeito_em=datetime('now') WHERE id=?", (token,))
        con.commit()
        return {"ok": True, "voltaram": voltaram, "ficaram": ficaram}
    finally:
        con.close()


def _desfazer_mover(con, token: int, r, antes: list, simular: bool, tarefas: BackgroundTasks, u: dict) -> dict:
    from .problemas import MOTIVO_VOLTA
    from .rotas_mesclar import MoverItens, mover_itens
    if u.get("papel") not in ("admin", "master"):
        raise HTTPException(403, "Mover folhas é de admin: peça a um admin para desfazer")
    movs = [a["mover"] for a in antes if "mover" in a]
    voltam, ficaram = {}, 0
    for m in movs:
        it = con.execute("SELECT projeto_codigo FROM item WHERE codigo=?", (m["para"],)).fetchone()
        if not it or not m.get("origem"):
            ficaram += 1                  # a folha mudou de novo depois: fica como está
            continue
        voltam.setdefault(m["origem"], []).append(m)
    con.close()
    plano = []
    for origem, ms in voltam.items():
        s = mover_itens(MoverItens(itens=[m["para"] for m in ms], destino=origem, motivo=MOTIVO_VOLTA, simular=True), tarefas, u)
        plano += [{"de": x["de"], "para": x["para"], "origem": origem} for x in s.get("movidos") or []]
    if simular:
        return {"ok": True, "simulado": True, "voltam": plano, "ficaram": ficaram}
    novos = {}
    for origem, ms in voltam.items():
        nums = ", ".join(str(m["erro"]) for m in ms[:20])
        s = mover_itens(MoverItens(itens=[m["para"] for m in ms], destino=origem, motivo=f"{MOTIVO_VOLTA} (problema nº {nums})", simular=False), tarefas, u)
        novos.update({x["de"]: x["para"] for x in s.get("movidos") or []})
    c2 = connect()
    try:
        c2.execute("BEGIN IMMEDIATE")
        reab = 0
        por_erro = {m["erro"]: novos.get(m["para"]) for m in movs}
        for a in antes:
            if "id" not in a or "mover" in a:
                continue
            cod = por_erro.get(a["id"])
            sets, vals = "situacao=?, resolucao=?, resolvido_em=?, fechado_por=?, fase=?, fase_em=?, motivo_pendencia=?", [a["situacao"], a["resolucao"], a["resolvido_em"], a.get("fechado_por"), a["fase"], a.get("fase_em"), a.get("motivo_pendencia")]
            if cod:
                sets += ", codigo=?"; vals.append(cod)          # o problema segue a folha (código novo no projeto de origem)
            n = c2.execute(f"UPDATE erro SET {sets} WHERE id=? AND situacao='corrigido'", (*vals, a["id"])).rowcount
            if n:
                reab += 1
                cp._evento(c2, a["id"], "desfeito", u["email"], {"situacao": a["situacao"], "acao": "rapido:mover", "codigo_novo": cod})
        c2.execute("UPDATE erro_desfazer SET desfeito_em=datetime('now') WHERE id=?", (token,))
        c2.commit()
    except Exception:
        c2.rollback()
        raise
    finally:
        c2.close()
    return {"ok": True, "voltaram": reab, "ficaram": ficaram, "folhas_voltaram": [{"de": k, "para": v} for k, v in novos.items()]}


# ---------------- procurar projeto (o "Escolher outro projeto…" da linha) ----------------
@router.get("/projetos")
def rota_projetos(fundo: str, q: str = "", u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    """Projetos do MESMO fundo para o "Escolher outro projeto…" (código ou nome; no máximo 8). Só lê."""
    f = (fundo or "").strip().upper()
    if not re.fullmatch(r"F\d{3}", f):
        raise HTTPException(400, "Fundo inválido")
    t = (q or "").strip()
    con = connect()
    try:
        w, p = ["fundo_codigo=?", "mesclado_em IS NULL", "descartado_em IS NULL"], [f]
        if t:
            w.append("(lower(codigo) LIKE ? OR lower(titulo) LIKE ? OR lower(coalesce(identificacao_original,'')) LIKE ?)"); p += ["%" + t.lower() + "%"] * 3
        return [dict(r) for r in con.execute(f"SELECT codigo, titulo, ano FROM projeto WHERE {' AND '.join(w)} ORDER BY codigo LIMIT 8", p)]
    finally:
        con.close()
