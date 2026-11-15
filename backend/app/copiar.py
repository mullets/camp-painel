"""COPIAR folhas para outro projeto, e criar o projeto de destino na hora (15/11/2026, pedido do Rafael:
"Preciso criar uma opção de copiar para outro lote, e ter a opção de criar esse lote, seja no mesmo arquiteto ou em outro").

Regras (docs/padroes.md, docs/CONTRATO_UNICO.md):
- A original NÃO muda. A cópia é uma folha NOVA e independente no projeto de destino, com código NOVO do destino (o prefixo vem do
  fundo do destino: copiar entre fundos é permitido, ao contrário de mover). O número D da cópia sai da FAIXA DO PAINEL (D90001+,
  a mesma das folhas enviadas pelo painel): o CAMP Vision nunca numera ali, então a cópia nunca colide com uma folha que ele ainda vai
  mandar para o destino. O maior D conta as folhas retiradas e os códigos que já existiram no destino (código anterior de folha movida,
  redirecionamentos): número nunca é reusado.
- O painel NÃO copia arquivo no QNAP (nunca grava lá): a cópia aponta para a MESMA imagem da original (arquivo_jpg e a prévia do
  CAMP Vision; a prévia vale para a cópia porque o nome dela é o código da original, guardado em item.copiada_de).
- Vai junto o que é catálogo (título, tipo, série, datas, carimbo, dados da foto, parceiros, autoria, giro/espelho/recorte). NÃO vai:
  vínculo com o site (registro, publicação, imagem no site: a cópia nasce "não publicado"), conferência (a cópia nasce "a conferir":
  uma pessoa olha no projeto novo), marca de duplicata, retenção, lote (a cópia não é de nenhum lote do CAMP Vision) e ordem manual.
- Folha que é cópia (duplicata) de outra não é copiada (copie a original). Copiar de novo a mesma folha para o mesmo destino não cria
  outra cópia (volta em `ignorados`, com o código da cópia que já existe).
- Histórico nos dois lados: evento 'folha_copiada' na cópia (de onde veio) e 'copiada_para' na original (para onde foi).
- Projeto novo ("Novo projeto…" no destino): o próximo P do fundo pelo mesmo caminho da reserva das estações
  (projetos_novos.criar_projeto: contador do painel, nunca reusa número), com a mesma conferência de parecidos do "Novo projeto".
  Para MOVER, o projeto novo tem de ser do mesmo fundo (fundos não se misturam); para COPIAR, pode ser de qualquer fundo.
- Muitas folhas (?tarefa=1): roda em segundo plano (tarefas.py), com andamento no topo.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["copiar"])

FAIXA_PAINEL = 90000          # D90001 em diante: só o painel numera (folhas_enviadas.FAIXA_PAINEL, campvision-new estrutura.FAIXA_PAINEL)
TAREFA_A_PARTIR = 40          # a tela pede ?tarefa=1 a partir daqui (a rota aceita os dois jeitos)

# o que vai da original para a cópia (catálogo e imagem); o resto nasce zerado
CAMPOS_COPIADOS = ("serie_codigo", "titulo", "tipo_documento", "folha", "escala", "ano_folha", "dimensoes", "suporte", "projeto_carimbo",
                   "escritorio_carimbo", "autor_carimbo", "arquivo_tif", "arquivo_jpg", "md5", "phash", "rotacao_aplicada", "espelhado",
                   "autoria_divergente", "outlier_campos", "credito", "origem", "tipo_lido", "pendencias", "giro_manual", "arquivo_origem",
                   "versao_cv2", "versao_prompt", "modelo_cv", "lido_json", "espelho_manual", "endereco_folha", "cliente_folha",
                   "tipos_documento", "recorte", "alinhamento", "parceiros", "foto_ano", "foto_estagio", "foto_fotografo", "sem_recorte_auto")


class NovoDestino(BaseModel):
    fundo_codigo: str
    titulo: str
    ano: int | None = 0
    cidade: str | None = None
    confirmar_novo: bool = False      # a pessoa viu os parecidos do fundo e quer criar um NOVO mesmo assim


class CopiarItens(BaseModel):
    itens: list[str]
    destino: str | None = None        # projeto que já existe, ou
    novo_projeto: NovoDestino | None = None   # cria o projeto antes de copiar (o mesmo clique)
    motivo: str | None = None
    simular: bool = False             # mostra os códigos novos; nada é gravado


class CopiarLote(BaseModel):
    projeto_codigo: str | None = None
    novo_projeto: NovoDestino | None = None
    motivo: str | None = None
    simular: bool = False


class MoverNovo(BaseModel):
    itens: list[str]
    novo_projeto: NovoDestino
    motivo: str | None = None


class MoverLoteNovo(BaseModel):
    novo_projeto: NovoDestino
    motivo: str | None = None


def _colunas(con, tabela: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def proximo_d_do_painel(con, destino: str) -> int:
    """O maior D já usado na faixa do painel do destino (>= 90000): folhas, folhas retiradas e códigos que já existiram lá
    (código anterior de folha movida/recodificada, redirecionamentos). Nunca devolve um número que já foi de alguma folha."""
    from .retirados import maior_sequencial
    m = max(FAIXA_PAINEL, maior_sequencial(con, destino, FAIXA_PAINEL))
    padrao = re.compile(rf"^{re.escape(destino)}-\d{{4}}-[^-]+-D(\d+)$")
    antigos = [r[0] for r in con.execute("SELECT codigo_anterior FROM item WHERE codigo_anterior LIKE ?", (destino + "-%",))]
    antigos += [r[0] for r in con.execute("SELECT codigo_antigo FROM redirecionamento WHERE codigo_antigo LIKE ?", (destino + "-%",))]
    for cod in antigos:
        mm = padrao.match(cod or "")
        if mm:
            m = max(m, int(mm.group(1)))
    return m


def _ano(con, destino_ano, it) -> int:
    if destino_ano:
        return int(destino_ano)
    from .rotas_mesclar import _ano_da_folha
    return _ano_da_folha(con, it)


def copiar(con, codigos: list[str], destino: str, ator: str, motivo: str | None) -> dict:
    """Copia as folhas para o destino (transação já aberta por quem chama). Devolve {copiadas: [{de, para}], ignorados: [{codigo, motivo}]}."""
    from .rotas_mesclar import _destino_valido
    d = _destino_valido(con, destino)
    cols = _colunas(con, "item")
    campos = [c for c in CAMPOS_COPIADOS if c in cols]
    seq = proximo_d_do_painel(con, destino)
    linhas = []
    for c in dict.fromkeys(codigos):
        it = con.execute("SELECT * FROM item WHERE codigo=?", (c,)).fetchone()
        if not it:
            raise HTTPException(404, f"A folha {c} não existe.")
        linhas.append(it)
    linhas.sort(key=lambda r: (r["projeto_codigo"], r["serie_codigo"], r["sequencial"]))
    copiadas, ignorados = [], []
    for it in linhas:
        c = it["codigo"]
        if it["duplicata_de"]:
            ignorados.append({"codigo": c, "motivo": f"é cópia de {it['duplicata_de']}: copie a original"}); continue
        ja = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND copiada_de=?", (destino, c)).fetchone()
        if ja:
            ignorados.append({"codigo": c, "motivo": f"já foi copiada para este projeto ({ja[0]})", "copia": ja[0]}); continue
        seq += 1
        novo = f"{destino}-{_ano(con, d['ano'], it):04d}-{it['serie_codigo']}-D{seq:05d}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (novo,)).fetchone():
            raise HTTPException(409, f"O código {novo} já existe; nada foi copiado.")
        status = "bloqueado" if it["status_site"] == "bloqueado" else "nao_publicado"
        nomes = ["codigo", "projeto_codigo", "sequencial", "status_site", "revisao", "copiada_de", *campos]
        valores = [novo, destino, seq, status, "pendente", c, *[it[x] for x in campos]]
        con.execute(f"INSERT INTO item ({','.join(nomes)}) VALUES ({','.join('?' * len(nomes))})", valores)
        con.execute("INSERT OR IGNORE INTO item_agente (item_codigo, agente_id, papel, fonte) SELECT ?, agente_id, papel, fonte FROM item_agente WHERE item_codigo=?",
                    (novo, c))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_copiada',?,?)",
                    (novo, ator, json.dumps({"de": c, "para": novo, "motivo": motivo}, ensure_ascii=False)))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'copiada_para',?,?)",
                    (c, ator, json.dumps({"de": c, "para": novo, "motivo": motivo}, ensure_ascii=False)))
        copiadas.append({"de": c, "para": novo})
    if copiadas:
        de = sorted({x["de"][:10] for x in copiadas})
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'folhas_copiadas',?,?)",
                    (destino, ator, json.dumps({"de": de, "folhas": len(copiadas), "motivo": motivo}, ensure_ascii=False)))
    return {"copiadas": copiadas, "ignorados": ignorados, "destino": destino, "fundo": d["fundo_codigo"]}


def criar_destino(con, n: NovoDestino, u: dict, fundo_obrigatorio: str | None = None, para: str = "copiar") -> dict:
    """Cria o projeto de destino (transação aberta por quem chama): o próximo P do fundo pelo caminho da reserva (nunca reusa número).
    Parecido no fundo sem confirmar_novo: 409 com a lista. fundo_obrigatorio: mover só cria projeto no MESMO fundo."""
    from .projetos_novos import criar_projeto
    from .rotas_projetos import mensagem_titulo_tecnico
    from .similaridade import buscar_parecidos
    fundo = (n.fundo_codigo or "").strip().upper()
    if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (fundo,)).fetchone():
        raise HTTPException(404, f"O fundo {fundo} não existe.")
    if fundo_obrigatorio and fundo != fundo_obrigatorio:
        raise HTTPException(409, f"Fundos não se misturam: para mover, o projeto novo tem de ser do fundo {fundo_obrigatorio}. "
                                 f"Para levar as folhas a outro fundo, use Copiar.")
    titulo = (n.titulo or "").strip()
    if not titulo:
        raise HTTPException(400, "Escreva o nome do projeto novo.")
    msg = mensagem_titulo_tecnico(titulo)
    if msg:
        raise HTTPException(422, msg)
    if not n.confirmar_novo:
        parecidos = buscar_parecidos(con, fundo, titulo, n.ano, n.cidade, None)
        if parecidos:
            raise _Parecidos(parecidos, fundo)
    novo = criar_projeto(con, fundo, titulo, n.ano or 0, (n.cidade or "").strip() or None, None, u["email"],
                         {"titulo": titulo, "origem": "painel", "criado_para": para}, reservado_por=u.get("id"))
    return novo


class _Parecidos(HTTPException):
    def __init__(self, parecidos: list, fundo: str):
        super().__init__(409, f"Já existe projeto parecido no fundo {fundo} ({parecidos[0]['codigo']}): confirme se é um projeto novo.")
        self.parecidos = parecidos


def _resposta_erro(e: HTTPException):
    if isinstance(e, _Parecidos):
        return JSONResponse(status_code=409, content={"detail": e.detail, "parecidos": e.parecidos})
    raise e


def _executar(fn, simular: bool = False):
    """Uma transação só (criar o projeto + copiar/mover: ou tudo, ou nada). Parecidos viram 409 com a lista."""
    from .rotas_mesclar import _transacao
    try:
        return _transacao(fn, simular=simular)
    except _Parecidos as e:
        return _resposta_erro(e)


def _destino_de(con, destino: str | None, novo: NovoDestino | None, u: dict, para: str) -> tuple[str, dict | None]:
    if novo is not None:
        p = criar_destino(con, novo, u, para=para)
        return p["codigo"], p
    if not destino:
        raise HTTPException(400, "Escolha o projeto de destino (ou crie um projeto novo).")
    return destino.strip().upper(), None


@router.post("/itens/copiar")
def copiar_itens(d: CopiarItens, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    """Copia as folhas escolhidas para outro projeto (de qualquer fundo), com códigos novos do destino. A original não muda."""
    if not d.itens:
        raise HTTPException(400, "Escolha pelo menos uma folha.")

    def fazer(con, itens=None, destino=None):
        criado = None
        if destino is None:
            destino, criado = _destino_de(con, d.destino, d.novo_projeto, u, "copiar")
        r = copiar(con, itens if itens is not None else d.itens, destino, u["email"], d.motivo)
        return {**r, "projeto_criado": criado}

    if tarefa and not d.simular:
        r0 = _executar(lambda con: fazer(con), simular=True)          # confere antes (parecido, destino, folha que não existe): erro na hora
        if isinstance(r0, JSONResponse):
            return r0
        from . import tarefas as _tarefas

        def rodar(p):
            # em partes de 25 folhas, cada uma numa transação (o andamento é gravado ENTRE elas: dentro da transação travaria o banco);
            # a 1ª parte cria o projeto novo. Repetir é seguro: folha já copiada para o destino não é copiada de novo.
            p.total(len(d.itens))
            tudo, destino, criado = {"copiadas": [], "ignorados": []}, None, None
            for k in range(0, len(d.itens), 25):
                parte = d.itens[k:k + 25]
                p.passo("Copiando as folhas", parte[0])
                r = _executar(lambda con: fazer(con, parte, destino))
                if not isinstance(r, dict):          # apareceu um projeto parecido entre a conferência e a tarefa
                    return {"ok": False, "mensagem": "Apareceu um projeto parecido no fundo agora: confira de novo. Nada foi copiado."}
                destino, criado = r["destino"], criado or r.get("projeto_criado")
                tudo["copiadas"] += r["copiadas"]; tudo["ignorados"] += r["ignorados"]
                p.feita(len(parte))
            return {**tudo, "destino": destino, "projeto_criado": criado, "ok": True,
                    "mensagem": f"{len(tudo['copiadas'])} folha(s) copiada(s) para {destino}"}
        return _tarefas.iniciar("copiar_folhas", r0["destino"] if not d.novo_projeto else "novo:" + d.novo_projeto.fundo_codigo, u, rodar,
                                titulo=f"Copiar {len(d.itens)} folha(s)")
    r = _executar(lambda con: fazer(con), simular=d.simular)
    if isinstance(r, dict) and d.simular:
        r["simulado"] = True
    return r


@router.post("/filas/{lid}/copiar-para")
def copiar_lote(lid: int, d: CopiarLote, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    """Copia TODAS as folhas do lote para outro projeto (de qualquer fundo). O lote e as folhas dele ficam onde estão."""
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo, descartado_em FROM lista_processamento WHERE id=?", (lid,)).fetchone()
        cods = [r[0] for r in con.execute("SELECT codigo FROM item WHERE lote_id=? AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (lid,))]
    finally:
        con.close()
    if not l:
        raise HTTPException(404, "Lote não existe")
    if l["descartado_em"]:
        raise HTTPException(409, "Este lote foi descartado.")
    if not cods:
        raise HTTPException(409, "Este lote não tem folhas no painel para copiar.")
    corpo = CopiarItens(itens=cods, destino=d.projeto_codigo, novo_projeto=d.novo_projeto, motivo=d.motivo or f"lote {lid} copiado", simular=d.simular)
    r = copiar_itens(corpo, tarefa, u)
    if isinstance(r, dict) and "copiadas" in r:
        r["lote"] = lid
    return r


@router.post("/itens/mover-novo-projeto")
def mover_para_novo(d: MoverNovo, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))):
    """Cria o projeto (no MESMO fundo das folhas; fundos não se misturam) e move as folhas para ele, numa transação só.
    Folha publicada: a mesma regra do mover (o registro antigo sai do público no site depois do commit, rotas_mesclar._depois_de_mover)."""
    from .rotas_mesclar import _depois_de_mover, _mover
    from .publicador import CONVIDADO
    if not d.itens:
        raise HTTPException(400, "Escolha pelo menos uma folha.")
    con = connect()
    try:
        fundos = {r[0] for r in con.execute(f"SELECT p.fundo_codigo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE i.codigo IN ({','.join('?' * len(d.itens))})",
                                            list(d.itens))}
    finally:
        con.close()
    fundos.discard(CONVIDADO)              # folha do Convidado pode ir a qualquer fundo (28/10)
    if len(fundos) > 1:
        raise HTTPException(409, "As folhas escolhidas são de fundos diferentes.")
    obrig = next(iter(fundos), None)

    def fazer(con):
        p = criar_destino(con, d.novo_projeto, u, fundo_obrigatorio=obrig, para="mover")
        r = _mover(con, d.itens, p["codigo"], u["email"], d.motivo or "movida para projeto novo", soltar_lote=True, publicada_ok=True)
        return {**r, "projeto_criado": p, "destino": p["codigo"]}
    r = _executar(fazer)
    return _depois_de_mover(r, u["email"], tarefas) if isinstance(r, dict) else r


@router.post("/filas/{lid}/mover-novo-projeto")
def mover_lote_para_novo(lid: int, d: MoverLoteNovo, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))):
    """Cria o projeto (no MESMO fundo do lote) e passa o lote e as folhas dele para ele, numa transação só."""
    from .rotas_mesclar import _depois_de_mover, _mover_lote
    from .publicador import CONVIDADO
    con = connect()
    try:
        l = con.execute("SELECT p.fundo_codigo FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo WHERE l.id=?", (lid,)).fetchone()
    finally:
        con.close()
    if not l:
        raise HTTPException(404, "Lote não existe")
    obrig = None if l[0] == CONVIDADO else l[0]

    def fazer(con):
        p = criar_destino(con, d.novo_projeto, u, fundo_obrigatorio=obrig, para="mover lote")
        return {**_mover_lote(con, lid, p["codigo"], u["email"], d.motivo, publicada_ok=True), "projeto_criado": p}
    r = _executar(fazer)
    return _depois_de_mover(r, u["email"], tarefas) if isinstance(r, dict) else r
