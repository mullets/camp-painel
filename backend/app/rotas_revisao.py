"""Revisão pós-CAMP Vision: importar as folhas do lote, conferir/corrigir, e o admin aprovar. Ler: leitura; revisar: operador; aprovar: admin."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ajuste_imagem as ajuste, auth, giro_imagem as imagens
from .db import connect
from .publicador import CREDITO_AUTORIA_NAO_CONFIRMADA
from .importador_lote import CODIGO_DOCUMENTO, fala_de_projeto_divergente, importar_lote, ler_pacote, tirar_projeto_divergente
from .rotas_operacao import _qnap_prontos_raiz

router = APIRouter(prefix="/api", tags=["revisao"])


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _lote(con, lote_id: int):
    l = con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
    if not l:
        raise HTTPException(404, "Lote não existe")
    return l


def _pode_importar(con, l, pacote: dict | None = None) -> tuple[bool, str | None]:
    """CAMP-067 (20/10, "o botão de importar não funciona sempre"): o painel só oferece "Importar" quando a importação pode dar certo;
    senão diz POR QUE, em português, no lugar do botão. As mesmas condições em que POST /lotes/{id}/importar recusaria
    (pasta, pacote, projeto do pacote, aprovado), mais lote descartado e folhas do lote já movidas para outro projeto."""
    if l["descartado_em"]:
        return False, "Este lote foi descartado: não há o que importar."
    if l["aprovado_em"]:
        return False, "O lote já foi aprovado: reabra a revisão para importar de novo."
    if con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (l["id"],)).fetchone():
        return False, "As folhas deste lote já foram importadas (e movidas para outro projeto)."
    pasta = Path(l["pasta_qnap"] or "")
    if not pasta.is_dir():
        return False, "O painel não acha a pasta do lote no QNAP (o QNAP está montado?). Avise quem cuida do servidor."
    if pacote is None:
        try:
            pacote = ler_pacote(pasta)
        except HTTPException as e:
            return False, str(e.detail)
    if pacote is None:
        if l["etapa"] in ("enviado", "processando"):
            return False, "O CAMP Vision ainda está lendo este lote. O botão Importar aparece quando ele terminar."
        if l["etapa"] == "erro":
            return False, "O CAMP Vision parou com erro neste lote e não gravou as folhas. Peça a releitura."
        return False, "O CAMP Vision não gravou o pacote deste lote (catalogacao/pacote_tainacan.json). Peça a releitura."
    if pacote.get("projeto_codigo") and pacote.get("projeto_codigo") != l["projeto_codigo"]:
        return False, f"O pacote da pasta é do projeto {pacote.get('projeto_codigo')}, e o lote é de {l['projeto_codigo']}. Peça a releitura."
    documentos = pacote.get("documentos") if isinstance(pacote.get("documentos"), list) else pacote.get("itens")
    if not isinstance(documentos, list):
        return False, "O CV2 não entregou uma lista de documentos válida. Preserve os arquivos e confira o manifesto."
    if not documentos:
        if pacote.get("retirados"):
            return False, "O CAMP Vision retirou as folhas deste lote. Um admin pode trazê-las para conferência, sem aceitar a exclusão da máquina."
        return False, "O pacote não contém folhas para importar. Confira o lote no QNAP; não precisa reimportar as folhas de outros lotes."
    from .destino_lote import bloqueio as _bloqueio_destino
    motivo_destino = _bloqueio_destino(con, l)            # UX-01: a pasta não parece deste projeto
    if motivo_destino:
        return False, motivo_destino
    return True, None


@router.get("/projetos/{codigo}/proximo-passo")
def proximo_passo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Em que ponto está o trabalho deste projeto e qual é o próximo passo (a MESMA fase da Fila: filas_fase). Escolhe a lista mais recente que ainda não foi publicada."""
    from .filas_fase import fase_da_lista, escolher_lote_ativo
    from .rotas_operacao import _erro_do_cv, _erro_do_cv_explicado
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        from .avisos_cv import avisos_abertos, curar_lotes, resumo_avisos_cv
        if curar_lotes(con, codigo):                     # CAMP-122 (P1): "erro" que é só aviso [Minor] não para o lote
            con.commit()
        lotes = []
        for l in con.execute("""SELECT l.id, l.nome, l.etapa, l.aprovado_em, l.aprovado_por, l.atualizado_em, l.folhas_esperadas, l.folhas_encontradas, l.status_json, l.resultado,
                                       (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo) AS itens_total,
                                       (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo AND i.revisao='pendente') AS itens_pendentes
                                FROM lista_processamento l WHERE l.projeto_codigo=? AND l.descartado_em IS NULL ORDER BY l.id DESC""", (codigo,)):
            # CAMP-078 (20/10, exaustão): lote descartado não é trabalho (a Fila já o tirava); o cartão Folhas continuava "o CAMP Vision está lendo"
            d = dict(l)
            d["itens_conferidos"] = d["itens_total"] - d["itens_pendentes"]
            d["fase"] = fase_da_lista(d["etapa"], d["itens_total"], d["itens_pendentes"], d["aprovado_em"], d.get("resultado"))
            # 19/10 (F026-P0009): lote parado por erro do CAMP Vision: o motivo vai junto (campo novo, opcional), para a Situação do lote dizer o porquê
            d["erro_cv"] = _erro_do_cv(d) if d["etapa"] == "erro" else None
            d["erro_cv_explicado"] = _erro_do_cv_explicado(d) if d["etapa"] == "erro" else None   # UX-08 (campo novo, opcional)
            d.pop("status_json", None); d.pop("resultado", None)
            lotes.append(d)
        lote = escolher_lote_ativo(lotes)
        if lote and lote["fase"] == "importar":       # CAMP-067: campo novo, opcional
            pode, motivo = _pode_importar(con, con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote["id"],)).fetchone())
            lote["importar_motivo"] = None if pode else motivo
            from .destino_lote import avaliar as _avaliar_destino   # UX-01: campo novo, opcional
            dl = _avaliar_destino(con, con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote["id"],)).fetchone(), completo=False)
            lote["destino_suspeito"] = dl["suspeito"] and not dl["liberado"]
        if lote and lote["fase"] == "conferir":       # UX-11: campo novo, opcional — as folhas a conferir SEM nenhum aviso (o número do botão)
            lote["itens_sem_aviso"] = contar_sem_aviso(con, lote["id"])
        av = avisos_abertos(con, codigo)
        return {"lote": lote, "lotes": len(lotes), "avisos_cv": av, "avisos_cv_resumo": resumo_avisos_cv(con, codigo, av), "pode_operar": u["papel"] in ("operador", "admin", "master"), "pode_agir": u["papel"] in ("admin", "master")}
    finally:
        con.close()


@router.post("/lotes/{lote_id}/importar")
def importar(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para importar de novo")
        r = importar_lote(con, lote_id, u["email"])
        con.commit()
        return r
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------- UX-01 · Verificar destino: a pasta não parece deste projeto ----------------
@router.get("/lotes/{lote_id}/destino")
def ver_destino(lote_id: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """A comparação lado a lado (pasta × projeto), as sugestões do mesmo fundo e 3 folhas da pasta (códigos do pacote: a prévia
    vem de /api/itens/{c}/previa, que acha o JPG na pasta do lote)."""
    from .destino_lote import avaliar
    con = connect()
    try:
        l = _lote(con, lote_id)
        try:
            pacote = ler_pacote(Path(l["pasta_qnap"] or "")) if Path(l["pasta_qnap"] or "").is_dir() else None
        except HTTPException:
            pacote = None
        a = avaliar(con, l, pacote)
        a["lote_id"] = lote_id
        a["pode_confirmar"] = u["papel"] in ("operador", "admin", "master")
        return a
    finally:
        con.close()


class EscolhaDestino(BaseModel):
    acao: str                          # confirmar ("É deste projeto") | decisao ("Mover para…" com destino, ou "Criar decisão")
    justificativa: str = ""
    destino: str | None = None


@router.post("/lotes/{lote_id}/destino")
def escolher_destino(lote_id: int, d: EscolhaDestino, u: dict = Depends(auth.exige("operador"))) -> dict:
    from .destino_lote import abrir_decisao, avaliar, confirmar
    just = " ".join((d.justificativa or "").split())[:500]
    if len(just) < 3:
        raise HTTPException(400, "Escreva a justificativa (por que esta pasta é, ou não é, deste projeto). Ela fica no Histórico.")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["descartado_em"] or l["aprovado_em"]:
            raise HTTPException(409, "Este lote já foi encerrado.")
        a = avaliar(con, l, completo=False)
        if not a["suspeito"]:
            raise HTTPException(409, "Este lote não precisa verificar destino: o nome da pasta combina com o projeto.")
        if d.acao == "confirmar":
            if a["confirmado"]:
                raise HTTPException(409, "Uma pessoa já confirmou que esta pasta é deste projeto.")
            confirmar(con, l, u["email"], just)
            r = {"ok": True, "acao": "confirmar", "mensagem": f"Anotado no Histórico: a pasta é de {l['projeto_codigo']}. Já dá para importar."}
        elif d.acao == "decisao":
            destino = (d.destino or "").strip().upper() or None
            if destino:
                fundo = con.execute("SELECT fundo_codigo FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()[0]
                if destino == l["projeto_codigo"] or not con.execute("SELECT 1 FROM projeto WHERE codigo=? AND fundo_codigo=?", (destino, fundo)).fetchone():
                    raise HTTPException(400, "O projeto sugerido não existe neste fundo")
            did = abrir_decisao(con, l, u["email"], just, destino)
            r = {"ok": True, "acao": "decisao", "decisao_id": did,
                 "mensagem": f"Pergunta aberta em Decisões (decisão {did}). O lote não importa até um admin decidir."
                             + (" Mudar a pasta de projeto depende de o CAMP Vision reidentificar os arquivos." if destino else "")}
        else:
            raise HTTPException(400, "acao deve ser 'confirmar' ou 'decisao'")
        con.commit()
        return r
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class TrazerRetiradas(BaseModel):
    confirmar: bool = False


@router.post("/lotes/{lote_id}/trazer-retiradas")
def trazer_retiradas(lote_id: int, d: TrazerRetiradas, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Decisão humana: incluir documentos retirados pelo CV2 na revisão, sem publicar."""
    if not d.confirmar:
        raise HTTPException(400, "Confirme que deseja trazer as folhas retiradas para conferência")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["descartado_em"] or l["aprovado_em"]:
            raise HTTPException(409, "Este lote já foi encerrado. Reabra a revisão antes de acrescentar folhas")
        pasta = Path(l["pasta_qnap"] or "")
        if not pasta.is_dir():
            raise HTTPException(409, "A pasta deste lote não está acessível no QNAP")
        pacote = ler_pacote(pasta)
        if not pacote or pacote.get("projeto_codigo") != l["projeto_codigo"]:
            raise HTTPException(409, "O pacote não existe ou não corresponde ao projeto cadastrado no painel")
        candidatas = [r for r in pacote.get("retirados") or [] if isinstance(r, dict)]
        if not candidatas:
            raise HTTPException(409, "Este lote não contém folhas retiradas pelo CAMP Vision")
        ja = {r[0] for r in con.execute(
            "SELECT chave FROM cv_resposta WHERE lote_id=? AND tipo='retirado' AND acao='devolver'", (lote_id,))}
        aceitas, ignoradas = [], []
        for folha in candidatas:
            codigo = str(folha.get("codigo") or "").strip()
            if not CODIGO_DOCUMENTO.fullmatch(codigo) or not codigo.startswith(l["projeto_codigo"] + "-"):
                ignoradas.append({"codigo": codigo, "motivo": "código de outro projeto ou inválido"})
                continue
            if codigo in ja:
                continue
            if not (folha.get("arquivos") or folha.get("arquivo_origem")):
                ignoradas.append({"codigo": codigo, "motivo": "sem arquivo de origem no manifesto"})
                continue
            # A decisão é humana e fica na trilha cv_resposta. O importador só
            # devolve as folhas escolhidas para revisão, nunca para publicação.
            _responder_cv(con, l, RespostaCV(
                tipo="retirado", chave=codigo, acao="devolver",
                motivo="Trazer à conferência; a exclusão do CV2 não é decisão final"), u)
            aceitas.append(codigo)
        if not aceitas:
            raise HTTPException(409, "Nenhuma nova folha com código e origem válidos para trazer. Confira o manifesto.")
        resultado = importar_lote(con, lote_id, u["email"])
        # A decisão de tentar recuperar uma retirada não prova que o arquivo
        # entrou na revisão. Colisões e códigos inválidos ainda podem impedir
        # sua entrada: informar as duas contagens separadamente.
        marca = ",".join("?" for _ in aceitas)
        importadas = [r[0] for r in con.execute(
            f"SELECT codigo FROM item WHERE codigo IN ({marca}) AND lote_id=? AND projeto_codigo=?",
            (*aceitas, lote_id, l["projeto_codigo"]))]
        nao_importadas = [c for c in aceitas if c not in set(importadas)]
        _evento(con, "projeto", l["projeto_codigo"], "retiradas_trazidas_para_conferencia",
                u["email"], {"lote_id": lote_id, "solicitadas": aceitas,
                              "importadas": importadas, "nao_importadas": nao_importadas,
                              "ignoradas": ignoradas, "criadas": resultado.get("criadas", 0)})
        con.commit()
        mensagem = ("Folhas trazidas à conferência. Confira cada aviso antes de publicar."
                    if importadas else
                    "Nenhuma folha entrou na revisão. Verifique colisões, arquivos e a situação do manifesto.")
        return {"ok": bool(importadas), "solicitadas": len(aceitas), "trazidas": len(importadas),
                "codigos": importadas, "nao_importadas": nao_importadas,
                "ignoradas": ignoradas, "importacao": resultado, "mensagem": mensagem}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/filas/importar-todas")
def importar_todas(u: dict = Depends(auth.exige("operador"))):
    """#97 + H4: "Importar todas (N)" da Fila vira UMA tarefa: importa, um por um, os lotes que esperam importação
    (as mesmas regras de /api/filas), com "3 de 14", o lote atual e o que falhou."""
    from . import pendencias, tarefas
    con = connect()
    try:
        from .destino_lote import bloqueio as _bloqueio_destino
        alvo, fora = [], []                                  # UX-01: "Verificar destino" fica de fora (e a mensagem diz quantos)
        for l in pendencias.lotes(con):
            if l["fase"] != "importar":
                continue
            lr = con.execute("SELECT * FROM lista_processamento WHERE id=?", (l["id"],)).fetchone()
            (fora if _bloqueio_destino(con, lr) else alvo).append((l["id"], l["projeto_codigo"]))
    finally:
        con.close()
    if not alvo:
        if fora:
            raise HTTPException(400, f"Nenhum lote para importar: {len(fora)} {'espera' if len(fora) == 1 else 'esperam'} Verificar destino (a pasta não parece do projeto).")
        raise HTTPException(400, "Nenhum lote esperando importação")
    nota_fora = f" {len(fora)} lote(s) ficaram de fora: Verificar destino ({', '.join(pj for _, pj in fora)})." if fora else ""

    def rodar(p) -> dict:
        p.total(len(alvo))
        folhas, falhas = 0, []
        for lid, pj in alvo:
            p.passo("Importando as folhas", atual=pj)
            try:
                r = importar(lid, u)
                folhas += r.get("criadas") or 0
                p.feita(1, f"{pj}: {r.get('criadas') or 0} folha(s) importada(s)")
            except HTTPException as e:
                falhas.append({"codigo": pj, "erro": str(e.detail)}); p.log(f"{pj} NÃO importou: {e.detail}")
        ok = len(alvo) - len(falhas)
        return {"ok": not falhas, "falhas": falhas, "lotes": ok, "folhas": folhas, "fora": [{"lote_id": i, "codigo": pj} for i, pj in fora],
                "mensagem": f"{ok} de {len(alvo)} lote(s) importado(s), {folhas} folha(s) no painel" + (f"; {len(falhas)} não {'importou' if len(falhas) == 1 else 'importaram'}" if falhas else "") + ". Próximo passo: conferir." + nota_fora}
    return tarefas.iniciar("importar_todas", "filas", u, rodar, titulo=f"Importar {len(alvo)} lote(s) da Fila")


# 19/10: a folha movida para outro projeto ("É de outro projeto…") leva o lote_id junto (o lote é do projeto de origem). Ela não conta mais
# nem é conferida em lote pelo lote de origem: antes "a conferir" não diminuía depois de mover e a folha que saiu travava "Aprovar o lote".
_DO_LOTE = "item.lote_id=? AND item.projeto_codigo=(SELECT l.projeto_codigo FROM lista_processamento l WHERE l.id=item.lote_id)"


def _contagem(con, lote_id: int) -> dict:
    c = {"total": 0, "pendente": 0, "conferida": 0, "corrigida": 0, "bloqueadas": 0, "retidas": 0}
    # CAMP-130 (20/10, F026-P0009): "12 conferidas · 22 corrigidas · 3 retidas" somava 37 num lote de 34 (a retida também conta como
    # conferida ou corrigida). `partes` (campo novo, opcional) divide as folhas sem sobrepor e soma o total: a retida conta só como retida.
    partes = {"pendente": 0, "sem_mudanca": 0, "corrigida": 0, "retida": 0}
    for r in con.execute(f"SELECT revisao, status_site, COALESCE(retida,0), COUNT(*) FROM item WHERE {_DO_LOTE} GROUP BY revisao, status_site, COALESCE(retida,0)", (lote_id,)):
        c["total"] += r[3]
        c[r[0]] += r[3]
        if r[1] == "bloqueado":
            c["bloqueadas"] += r[3]
        if r[2]:
            c["retidas"] += r[3]
            partes["retida"] += r[3]
        else:
            partes[{"conferida": "sem_mudanca"}.get(r[0], r[0])] += r[3]
    c["partes"] = partes
    return c


@router.get("/projetos/{codigo}/revisao")
def resumo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        lotes = []
        for l in con.execute("SELECT * FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,)):
            pasta = Path(l["pasta_qnap"] or "")
            acessivel = pasta.is_dir()
            pacote = {"acessivel": acessivel, "existe": False, "documentos": 0, "retirados": 0, "teste": False}
            p = None
            if acessivel:
                try:
                    p = ler_pacote(pasta)
                except HTTPException:
                    p = None
                if p is not None:
                    docs = p.get("documentos") if isinstance(p.get("documentos"), list) else (p.get("itens") or [])
                    pacote.update({"existe": True, "documentos": len(docs), "retirados": len(p.get("retirados") or []), "teste": bool(p.get("teste"))})
            c = _contagem(con, l["id"])
            imp_ok, imp_motivo = _pode_importar(con, l, p) if c["total"] == 0 else (False, None)
            motivo = None
            if l["aprovado_em"]:
                motivo = "Já aprovado"
            elif c["total"] == 0:
                motivo = "Importe as folhas do lote antes"
            elif c["pendente"]:
                motivo = f"Faltam conferir {c['pendente']} folha(s)"
            try:
                importacao = json.loads(l["resultado"] or "{}").get("importacao")
            except ValueError:
                importacao = None
            from .pendencias import identificador_lote, _e_complemento
            lotes.append({"id": l["id"], "nome": l["nome"], "identificador": identificador_lote(l["nome"], l["criado_em"], _e_complemento(l["resultado"])), "etapa": l["etapa"], "aprovado_por": l["aprovado_por"], "aprovado_em": l["aprovado_em"], "criado_em": l["criado_em"], "pacote": pacote,
                          "itens": c, "importacao": importacao, "pode_aprovar": motivo is None, "motivo": motivo,
                          "descartado": bool(l["descartado_em"]), "pode_importar": imp_ok, "importar_motivo": imp_motivo,
                          "destino_suspeito": bool(imp_motivo and imp_motivo.startswith("Verificar destino"))})   # CAMP-067: campos novos, opcionais
        return {"lotes": lotes}
    finally:
        con.close()


class RevisaoItem(BaseModel):
    estado: str     # conferida (está certo) | corrigida (a pessoa editou) | pendente (volta para conferir)


def registrar_campos_revisados(con, codigo: str, estado: str, por: str) -> None:
    """Cartão 152: compara, campo a campo, o que o CV2 leu (item.lido_json) com o que ficou depois da revisão.
    igual = aceito sem correção; corrigido = a pessoa mudou; preenchido = o CV2 leu vazio e a pessoa preencheu. Voltar a 'pendente' apaga o registro."""
    if estado == "pendente":
        con.execute("DELETE FROM revisao_campo WHERE item_codigo=?", (codigo,)); return
    it = con.execute("SELECT titulo, tipo_documento, folha, escala, ano_folha, lido_json, versao_cv2 FROM item WHERE codigo=?", (codigo,)).fetchone()
    if not it or not it["lido_json"]:
        return
    try:
        lido = json.loads(it["lido_json"])
    except ValueError:
        return
    norm = lambda v: "" if v is None else str(v).strip()  # noqa: E731
    for campo, v_lido in ((c, lido.get(c)) for c in ("titulo", "tipo_documento", "folha", "escala", "ano_folha") if c in lido):   # o resto (carimbo, leitura) é rastreio
        a, b = norm(v_lido), norm(it[campo])
        if not a and not b:
            continue
        res = "igual" if a == b else ("preenchido" if not a else "corrigido")
        con.execute("INSERT OR REPLACE INTO revisao_campo (item_codigo, campo, valor_lido, valor_final, resultado, versao_cv2, por) VALUES (?,?,?,?,?,?,?)",
                    (codigo, campo, a or None, b or None, res, it["versao_cv2"], por))


# CAMP-068 (20/10, "as marcações de problemas não somem ao corrigir, na etapa de conferir"): conferir é olhar a folha e dizer que está certa.
# O que a conferência resolve DE FATO some junto, gravado no banco (não só na tela): o espelho que o CAMP Vision aplicou fica confirmado,
# e os problemas automáticos do CAMP Vision que são "olhe esta folha" (giro, espelho, dado lido) fecham com registro de quem conferiu.
# Duplicata, outro projeto, autoria e retirada têm ação própria e NÃO fecham por conferir.
CATEGORIAS_FECHADAS_AO_CONFERIR = ("orientacao", "espelhado", "metadado")
# 20/10 (print da F026-P0009: "se eu resolvo um problema ele tem que sair da lista"): o aviso "série incerta na triagem … conferir na folha de
# contatos" chega com categoria fora da lista do painel (fica 'outro'; a tabela erro tem CHECK) e não fechava ao conferir. Os avisos do CAMP Vision que só pedem
# "olhe esta folha" fecham pela categoria OU pelo texto (o que já está na base com 'outro' também).
_OLHE_A_FOLHA = ("conferir na folha de contatos", "serie incerta", "orientacao incerta", "espelhad")


def pede_so_olhar_a_folha(descricao) -> bool:
    import unicodedata
    t = "".join(ch for ch in unicodedata.normalize("NFD", str(descricao or "")) if unicodedata.category(ch) != "Mn").lower()
    return any(x in t for x in _OLHE_A_FOLHA)


def resolver_ao_conferir(con, codigo: str, estado: str, ator: str) -> dict:
    out = {"espelho_confirmado": False, "problemas_fechados": []}
    if estado not in ("conferida", "corrigida"):
        return out
    i = con.execute("SELECT espelhado, espelho_manual FROM item WHERE codigo=?", (codigo,)).fetchone()
    if i and i["espelhado"] and i["espelho_manual"] is None:
        con.execute("UPDATE item SET espelho_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (int(i["espelhado"]), codigo))
        out["espelho_confirmado"] = True
    ids = [r["id"] for r in con.execute("""SELECT id, categoria, gravidade, descricao FROM erro WHERE codigo=? AND origem='campvision'
                                              AND situacao IN ('aberto','em_correcao')""", (codigo,))
           if r["categoria"] in CATEGORIAS_FECHADAS_AO_CONFERIR
           or (r["categoria"] == "outro" and r["gravidade"] != "bloqueia" and pede_so_olhar_a_folha(r["descricao"]))]
    if ids:
        quem = "corrigiu" if estado == "corrigida" else "conferiu"
        con.execute(f"UPDATE erro SET situacao='corrigido', resolvido_em=datetime('now'), resolucao=? WHERE id IN ({','.join('?' * len(ids))})",
                    (f"Resolvido na conferência: {ator} {quem} a folha no painel.", *ids))
        for eid in ids:
            _evento(con, "erro", str(eid), "fechado_na_conferencia", ator, {"codigo": codigo, "revisao": estado})
        out["problemas_fechados"] = ids
    if out["espelho_confirmado"] or ids:
        _evento(con, "item", codigo, "conferencia_resolveu", ator, out)
    return out


def reabrir_ao_desfazer(con, codigo: str, ator: str) -> dict:
    """CAMP-091 (decisão de 20/10): desfazer a conferência ("Desfazer" do aviso ou "Voltar para a conferir") reabre o que ELA fechou
    (resolver_ao_conferir: giro, espelho, dado lido) e devolve o espelho a "a confirmar" se foi ela que confirmou. Só some o que foi resolvido."""
    out = {"problemas_reabertos": [], "espelho_reaberto": False}
    ids = [r[0] for r in con.execute("""SELECT id FROM erro WHERE codigo=? AND origem='campvision' AND situacao='corrigido'
                                         AND resolucao LIKE 'Resolvido na conferência:%'""", (codigo,))]
    if ids:
        con.execute(f"UPDATE erro SET situacao='aberto', resolvido_em=NULL, resolucao=NULL WHERE id IN ({','.join('?' * len(ids))})", ids)
        out["problemas_reabertos"] = ids
    ult = con.execute("""SELECT tipo, detalhe FROM evento WHERE entidade='item' AND codigo=? AND tipo IN ('conferencia_resolveu','conferencia_desfeita')
                         ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    if ult and ult["tipo"] == "conferencia_resolveu":
        try:
            det = json.loads(ult["detalhe"] or "{}")
        except ValueError:
            det = {}
        if det.get("espelho_confirmado"):
            con.execute("UPDATE item SET espelho_manual=NULL, atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
            out["espelho_reaberto"] = True
    if ids or out["espelho_reaberto"]:
        _evento(con, "item", codigo, "conferencia_desfeita", ator, out)
    return out


@router.post("/itens/{codigo}/revisao")
def revisar(codigo: str, d: RevisaoItem, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.estado not in ("pendente", "conferida", "corrigida"):
        raise HTTPException(400, "estado deve ser pendente, conferida ou corrigida")
    con = connect()
    try:
        i = con.execute("SELECT i.revisao, i.status_site, i.lote_id, i.titulo, i.tipo_documento, i.tipos_documento, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        fechado = "lote_aprovado" if i["aprovado_em"] else ("no_site" if i["status_site"] in ("rascunho", "no_ar") else None)
        if d.estado in ("conferida", "corrigida") and not fechado:
            from .revisao_politica import falta_titulo_para_conferencia
            if falta_titulo_para_conferencia(i):
                sem_tipo = not str(i["tipos_documento"] or i["tipo_documento"] or "").strip()
                campos = "título e tipo documental" if sem_tipo else "título"
                raise HTTPException(409, f"Antes de marcar a folha como conferida, preencha {campos}. A leitura do CAMP Vision pode estar incompleta; confirme os dados no painel.")

        if fechado and d.estado == "pendente":       # reabrir continua protegido
            raise HTTPException(409, "O lote desta folha já foi aprovado: reabra a revisão para mudar" if fechado == "lote_aprovado"
                                else "Esta folha já está no site: a revisão do lote não se aplica")
        if fechado:
            # 19/10 ("muito chato"): corrigir uma folha de lote aprovado (ou já no site) dava "os dados foram salvos, mas a revisão não mudou".
            # A correção (PATCH) já é o que importa; "conferida/corrigida" aqui só confirma: registra o que mudou e responde ok, sem reabrir nada.
            registrar_campos_revisados(con, codigo, d.estado, u["email"])
            res = resolver_ao_conferir(con, codigo, d.estado, u["email"])
            con.commit()
            return {"ok": True, "revisao": i["revisao"], "sem_mudanca": fechado, "resolvidos": res}
        con.execute("UPDATE item SET revisao=?, revisado_por=?, revisado_em=CASE WHEN ?='pendente' THEN NULL ELSE datetime('now') END, atualizado_em=datetime('now') WHERE codigo=?",
                    (d.estado, None if d.estado == "pendente" else u["email"], d.estado, codigo))
        _evento(con, "item", codigo, "revisao", u["email"], {"de": i["revisao"], "para": d.estado})
        registrar_campos_revisados(con, codigo, d.estado, u["email"])
        res = resolver_ao_conferir(con, codigo, d.estado, u["email"])
        reab = reabrir_ao_desfazer(con, codigo, u["email"]) if d.estado == "pendente" and i["revisao"] != "pendente" else None
        con.commit()
        return {"ok": True, "revisao": d.estado, "resolvidos": res, **({"reabertos": reab} if reab else {})}   # 'reabertos': campo novo, opcional
    finally:
        con.close()


@router.post("/itens/{codigo}/deste-projeto")
def confirmar_deste_projeto(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """19/10 (Clube Sírio): "É deste projeto (o CAMP Vision errou)". Tira o sinal "projeto divergente" e os bloqueios que falam de outro projeto;
    se não sobrar outro bloqueio, a folha sai de 'bloqueado' e volta a 'nao_publicado'; fecha o problema automático "folha de outro projeto"
    que o CAMP Vision abriu para ela. Fica no histórico com quem fez. Repetir não muda nada (nem grava de novo)."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        i = con.execute("SELECT status_site, pendencias, autoria_divergente FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i:
            out = _deste_projeto_retirada(con, codigo, u)        # 20/10 (CAMP-069): a folha que o CAMP Vision retirou por "ser de outra obra"
            con.commit()
            return out
        try:
            pend = json.loads(i["pendencias"] or "{}")
        except ValueError:
            pend = {}
        if not isinstance(pend, dict):
            pend = {}
        sinais, bloqueios = tirar_projeto_divergente(pend)
        # fluxo real (20/10): o CAMP Vision também manda o caso como problema em erros.json ("D00007 com identificação para outra pasta … — fora da
        # publicação até resolver", categoria "projeto" → 'outro', gravidade bloqueia). Antes só fechava a categoria projeto_errado: esse ficava aberto
        # e a publicação continuava travada, mesmo sem sinal na folha. Agora fecha todo problema do CAMP Vision desta folha que fala de outro projeto.
        alvo = [r["id"] for r in con.execute("""SELECT id, categoria, descricao FROM erro WHERE codigo=? AND origem='campvision' AND situacao IN ('aberto','em_correcao')""", (codigo,))
                if r["categoria"] == "projeto_errado" or fala_de_projeto_divergente(r["descricao"])]
        mudou = bool(sinais or bloqueios or alvo)
        out = {"ok": True, "mudou": mudou, "sinais_tirados": sinais, "bloqueios_tirados": bloqueios, "situacao_liberada": False, "problemas_fechados": 0}
        status = i["status_site"]
        if mudou:
            con.execute("UPDATE item SET pendencias=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
            if status == "bloqueado" and not pend["bloqueios"] and not i["autoria_divergente"]:
                con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))
                status, out["situacao_liberada"] = "nao_publicado", True
            for eid in alvo:
                out["problemas_fechados"] += con.execute("UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'), resolucao=? WHERE id=?",
                                                         (f"É deste projeto: {u['email']} confirmou no painel (o CAMP Vision errou).", eid)).rowcount
            _evento(con, "item", codigo, "projeto_confirmado", u["email"], {k: out[k] for k in ("sinais_tirados", "bloqueios_tirados", "situacao_liberada", "problemas_fechados")})
        con.commit()
        return {**out, "status_site": status, "bloqueios_restantes": pend.get("bloqueios") or [], "pendencias": pend}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/itens/{codigo}/autoria-confirmada")
def confirmar_autoria_da_folha(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """CAMP-068: na conferência, "A autoria é do titular do fundo". Tira o aviso "autoria não confirmada" da folha e fecha os problemas de
    autoria abertos dela (antes o botão só aparecia se houvesse um problema aberto; sem ele, a marca não tinha como sair). Fica no histórico."""
    con = connect()
    try:
        i = con.execute("SELECT autoria_divergente FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        # CAMP-092: o crédito "Autoria não confirmada" (posto pelo importador) sai junto; vazio = o crédito padrão do fundo
        con.execute("UPDATE item SET autoria_divergente=0, credito=CASE WHEN credito=? THEN NULL ELSE credito END, atualizado_em=datetime('now') WHERE codigo=?",
                    (CREDITO_AUTORIA_NAO_CONFIRMADA, codigo))
        ids = [r[0] for r in con.execute("SELECT id FROM erro WHERE codigo=? AND categoria='autoria_divergente' AND situacao IN ('aberto','em_correcao')", (codigo,))]
        if ids:
            con.execute(f"UPDATE erro SET situacao='corrigido', resolvido_em=datetime('now'), resolucao=? WHERE id IN ({','.join('?' * len(ids))})",
                        (f"Conferido na revisão por {u['email']}: a autoria é do titular do fundo.", *ids))
        if i["autoria_divergente"] or ids:
            _evento(con, "item", codigo, "autoria_confirmada", u["email"], {"problemas_fechados": ids})
        con.commit()
        return {"ok": True, "mudou": bool(i["autoria_divergente"] or ids), "problemas_fechados": ids}
    finally:
        con.close()


class LiberarBloqueio(BaseModel):
    motivo: str


@router.post("/itens/{codigo}/bloqueio-resolvido")
def bloqueio_resolvido(codigo: str, d: LiberarBloqueio, u: dict = Depends(auth.exige("operador"))) -> dict:
    """CAMP-068: o CAMP Vision prendeu a folha ("bloqueada") por um motivo que a pessoa conferiu e resolveu. Tira esses bloqueios
    (os de duplicata e de outro projeto têm ação própria e ficam), guarda o que saiu em pendencias.bloqueios_resolvidos com quem e por quê,
    e, se não sobrar bloqueio nem autoria pendente, a folha sai de 'bloqueado'. Exige dizer o que foi feito."""
    from .importador_lote import fala_de_projeto_divergente
    from .rotas_mesclar import _e_de_duplicata
    motivo = (d.motivo or "").strip()[:300]
    if not motivo:
        raise HTTPException(400, "Diga o que foi feito para resolver")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        i = con.execute("SELECT status_site, pendencias, autoria_divergente FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        try:
            pend = json.loads(i["pendencias"] or "{}")
        except ValueError:
            pend = {}
        if not isinstance(pend, dict):
            pend = {}
        bloq = [b for b in (pend.get("bloqueios") or []) if b]
        tirar = [b for b in bloq if not fala_de_projeto_divergente(b) and not _e_de_duplicata(b)]
        status = i["status_site"]
        if tirar:
            pend["bloqueios"] = [b for b in bloq if b not in tirar]
            pend.setdefault("bloqueios_resolvidos", []).append({"bloqueios": tirar, "por": u["email"], "motivo": motivo})
            con.execute("UPDATE item SET pendencias=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
            if status == "bloqueado" and not pend["bloqueios"] and not i["autoria_divergente"]:
                con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))
                status = "nao_publicado"
            _evento(con, "item", codigo, "bloqueio_resolvido", u["email"], {"bloqueios": tirar, "motivo": motivo})
        con.commit()
        return {"ok": True, "mudou": bool(tirar), "bloqueios_tirados": tirar, "bloqueios_restantes": pend.get("bloqueios") or [], "status_site": status, "pendencias": pend}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------- 20/10 · CAMP-069: folha "de outro projeto" que nem entrou no painel; desfazer "É deste projeto" ----------------
def _retirada_no_pacote(con, codigo: str):
    """(lote_id, entrada em `retirados`, pasta do lote) da folha que o CAMP Vision retirou. Lê só o pacote de cada lote do projeto (um arquivo; nunca varre o QNAP).
    Primeiro o lote cujo resumo da importação cita a folha."""
    for l in con.execute("SELECT id, pasta_qnap FROM lista_processamento WHERE projeto_codigo=? ORDER BY (COALESCE(resultado,'') LIKE ?) DESC, id DESC LIMIT 12",
                         (codigo[:10], f'%"{codigo}"%')):
        pasta = Path(l["pasta_qnap"] or "")
        try:
            pac = ler_pacote(pasta) if pasta.is_dir() else None
        except (HTTPException, OSError):
            pac = None
        for r in (pac or {}).get("retirados") or []:
            if isinstance(r, dict) and r.get("codigo") == codigo:
                return l["id"], r, pasta
    return None, None, None


def _fala_de_outro_projeto(pendencias) -> bool:
    try:
        p = json.loads(pendencias or "{}")
    except ValueError:
        return False
    return isinstance(p, dict) and any(fala_de_projeto_divergente(x) for k in ("sinais", "bloqueios") for x in (p.get(k) or []) if isinstance(p.get(k), list))


def _imagem_da_folha_fora_do_painel(con, codigo: str):
    """A imagem de uma folha que não está na tabela de folhas (o CAMP Vision a retirou do lote): a prévia do pacote, o JPG listado em `arquivos`
    ou <pasta do lote>/<série>/JPG/<código>.jpg. Só serve arquivo de dentro da raiz dos prontos ou da pasta do lote."""
    if not CODIGO_DOCUMENTO.match(codigo):
        return None
    raiz = _qnap_prontos_raiz()
    _, r, pasta = _retirada_no_pacote(con, codigo)
    if r:
        rel = str(r.get("preview") or "")
        if rel and raiz:
            try:
                cand = (raiz / rel).resolve()
                if (raiz / "_campvision" / "preview").resolve() in cand.parents and cand.suffix.lower() in (".jpg", ".jpeg") and cand.stem == codigo and cand.is_file():
                    return cand
            except OSError:
                pass
        for a in r.get("arquivos") or []:
            if str(a).lower().endswith((".jpg", ".jpeg")) and raiz:
                alvo = jpg_da_folha_no_qnap(raiz, str(a))
                if alvo:
                    return alvo
    pastas = [pasta] if pasta else [Path(x[0] or "") for x in con.execute("SELECT pasta_qnap FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 6", (codigo[:10],))]
    for p in pastas:
        try:
            if not p.is_dir():
                continue
            base = p.resolve()
            for sub in [p, *sorted(x for x in p.iterdir() if x.is_dir())][:40]:
                for cand in (sub / "JPG" / f"{codigo}.jpg", sub / f"{codigo}.jpg"):
                    c = cand.resolve()
                    if (c.parent == base or base in c.parents) and c.is_file():
                        return c
        except OSError:
            continue
    return None


def _deste_projeto_retirada(con, codigo: str, u: dict) -> dict:
    """"É deste projeto" numa folha que o CAMP Vision RETIROU por achar que é de outra obra (ou sem identificação): devolve a folha ao lote
    (como o "Devolver à revisão" do admin, mas só para esse motivo, que é decisão de quem confere), fecha os problemas do CAMP Vision sobre ela
    e grava no histórico. A folha entra no painel na próxima importação do lote (a tela importa logo em seguida)."""
    if not CODIGO_DOCUMENTO.match(codigo):
        raise HTTPException(404, "Folha não existe")
    erros = con.execute("""SELECT id, categoria, descricao, chave FROM erro WHERE origem='campvision' AND situacao IN ('aberto','em_correcao')
                            AND (codigo=? OR chave=?)""", (codigo, f"campvision:retirado:{codigo}")).fetchall()
    lote_id, r, _ = _retirada_no_pacote(con, codigo)
    txt = " ".join([str(x) for x in ((r or {}).get("bloqueios") or [])] + [str((r or {}).get("motivo") or "")])
    de_outro = bool(r) and bool(r.get("projeto_divergente") or r.get("sem_identificacao") or fala_de_projeto_divergente(txt))
    de_outro = de_outro or any(e["categoria"] == "projeto_errado" or fala_de_projeto_divergente(e["descricao"]) for e in erros)
    if not r and not erros:
        raise HTTPException(404, "Folha não existe")
    if not de_outro:
        raise HTTPException(409, "O CAMP Vision retirou esta folha por outro motivo (não por ser de outro projeto). Só um admin a devolve, em Problemas.")
    if lote_id is None:
        l = con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY (COALESCE(resultado,'') LIKE ?) DESC, id DESC LIMIT 1",
                        (codigo[:10], f'%"{codigo}"%')).fetchone()
        if not l:
            raise HTTPException(409, "Não achei o lote desta folha: importe o lote do CAMP Vision antes.")
        lote_id = l["id"]
    ja = con.execute("SELECT 1 FROM cv_resposta WHERE lote_id=? AND tipo='retirado' AND chave=?", (lote_id, codigo)).fetchone()
    if not ja:
        con.execute("INSERT INTO cv_resposta (lote_id, projeto_codigo, tipo, chave, acao, motivo, por) VALUES (?,?,'retirado',?,'devolver',?,?)",
                    (lote_id, codigo[:10], codigo, "É deste projeto (o CAMP Vision errou)", u["email"]))
    alvo = [e["id"] for e in erros if e["chave"] == f"campvision:retirado:{codigo}" or e["categoria"] == "projeto_errado" or fala_de_projeto_divergente(e["descricao"])]
    fechados = 0
    for eid in alvo:
        fechados += con.execute("UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'), resolucao=? WHERE id=?",
                                (f"É deste projeto: {u['email']} confirmou no painel (o CAMP Vision errou).", eid)).rowcount
    mudou = not ja or bool(fechados)
    if mudou:
        _evento(con, "item", codigo, "projeto_confirmado", u["email"], {"retirada": True, "lote": lote_id, "problemas_fechados": fechados,
                                                                         "sinais_tirados": [], "bloqueios_tirados": [], "situacao_liberada": False})
    return {"ok": True, "mudou": mudou, "retirada": True, "lote_id": lote_id, "problemas_fechados": fechados, "situacao_liberada": False,
            "sinais_tirados": [], "bloqueios_tirados": [], "status_site": None, "bloqueios_restantes": [], "pendencias": None}


_AVISO_DESFEITO = "projeto divergente: uma pessoa desfez o \"É deste projeto\" no painel"


@router.post("/itens/{codigo}/deste-projeto/desfazer")
def desfazer_deste_projeto(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """20/10 (CAMP-069, "refazer a ação"): desfaz o último "É deste projeto" da folha. O aviso do CAMP Vision volta (o mesmo texto que saiu; se não
    houver registro, um aviso genérico de projeto divergente), a folha volta a 'bloqueado' se tinha sido liberada por isso, os problemas que a decisão
    fechou reabrem e a folha retirada deixa de ser devolvida ao lote. A próxima importação respeita (o aviso não some de novo). Folha no site: despublique antes."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        ev = con.execute("""SELECT id, detalhe FROM evento e WHERE entidade='item' AND codigo=? AND tipo='projeto_confirmado'
                             AND NOT EXISTS (SELECT 1 FROM evento d WHERE d.entidade='item' AND d.codigo=e.codigo AND d.tipo='projeto_confirmado_desfeito' AND d.id>e.id)
                             ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
        if not ev:
            raise HTTPException(409, "Não há \"É deste projeto\" para desfazer nesta folha.")
        try:
            det = json.loads(ev["detalhe"] or "{}") or {}
        except ValueError:
            det = {}
        i = con.execute("SELECT status_site, pendencias FROM item WHERE codigo=?", (codigo,)).fetchone()
        out = {"ok": True, "status_site": None, "pendencias": None, "problemas_reabertos": 0, "devolucao_cancelada": False}
        if i:
            if i["status_site"] in ("rascunho", "no_ar"):
                raise HTTPException(409, "Esta folha já está no site. Despublique pela página da folha antes de desfazer.")
            try:
                pend = json.loads(i["pendencias"] or "{}")
            except ValueError:
                pend = {}
            pend = pend if isinstance(pend, dict) else {}
            for chave in ("sinais", "bloqueios"):
                atual = [x for x in (pend.get(chave) or []) if x] if isinstance(pend.get(chave), list) else []
                pend[chave] = atual + [x for x in (det.get(chave + "_tirados") or []) if x not in atual]
            if not any(fala_de_projeto_divergente(x) for x in pend["sinais"] + pend["bloqueios"]):
                pend["bloqueios"].append(_AVISO_DESFEITO)
            status = i["status_site"]
            if pend["bloqueios"] and status == "nao_publicado":
                status = "bloqueado"
            con.execute("UPDATE item SET pendencias=?, status_site=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), status, codigo))
            out.update(status_site=status, pendencias=pend)
        if det.get("retirada"):
            out["devolucao_cancelada"] = con.execute("DELETE FROM cv_resposta WHERE tipo='retirado' AND acao='devolver' AND chave=? AND motivo='É deste projeto (o CAMP Vision errou)'",
                                                     (codigo,)).rowcount > 0
        out["problemas_reabertos"] = con.execute("""UPDATE erro SET situacao='aberto', resolvido_em=NULL, resolucao=NULL
                                                    WHERE (codigo=? OR chave=?) AND situacao='ignorado' AND resolucao LIKE 'É deste projeto:%'""",
                                                 (codigo, f"campvision:retirado:{codigo}")).rowcount
        _evento(con, "item", codigo, "projeto_confirmado_desfeito", u["email"], {k: out[k] for k in ("status_site", "problemas_reabertos", "devolucao_cancelada")})
        con.commit()
        return out
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class RetencaoItem(BaseModel):
    retida: bool
    motivo: str | None = None


@router.post("/itens/{codigo}/retencao")
def reter(codigo: str, d: RetencaoItem, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Reter a folha: ela continua no painel (conferida), mas NUNCA vai ao site (nem pela publicação do projeto, nem do fundo, nem pelo lote). Liberar a devolve para conferir.
    Devolve a revisão da folha depois da mudança (a tela usa no "Desfazer": no lote aprovado ela continua conferida)."""
    con = connect()
    try:
        i = con.execute("SELECT i.revisao, i.status_site, i.retida, i.lote_id, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        # 19/10: lote aprovado NÃO trava mais (o Rafa: "isso tá me irritando muito"); o que trava é a folha estar no site
        if i["status_site"] in ("rascunho", "no_ar"):
            raise HTTPException(409, "Esta folha já está no site. Despublique pela página da folha antes de retê-la.")
        motivo = (d.motivo or "").strip()[:300] or None
        if d.retida:
            con.execute("""UPDATE item SET retida=1, retida_motivo=?, retida_por=?, retida_em=datetime('now'),
                           revisao=CASE WHEN revisao='pendente' THEN 'conferida' ELSE revisao END,
                           revisado_por=CASE WHEN revisao='pendente' THEN ? ELSE revisado_por END, revisado_em=CASE WHEN revisao='pendente' THEN datetime('now') ELSE revisado_em END,
                           atualizado_em=datetime('now') WHERE codigo=?""", (motivo, u["email"], u["email"], codigo))
        else:
            if i["aprovado_em"]:                       # lote aprovado: volta a publicar, conferida (o lote não reabre por isso)
                con.execute("UPDATE item SET retida=0, retida_motivo=NULL, retida_por=NULL, retida_em=NULL, atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
            else:
                con.execute("""UPDATE item SET retida=0, retida_motivo=NULL, retida_por=NULL, retida_em=NULL, revisao='pendente', revisado_por=NULL, revisado_em=NULL,
                           atualizado_em=datetime('now') WHERE codigo=?""", (codigo,))
        _evento(con, "item", codigo, "folha_retida" if d.retida else "folha_liberada", u["email"], {"motivo": motivo})
        con.commit()
        rev = con.execute("SELECT revisao FROM item WHERE codigo=?", (codigo,)).fetchone()[0]
        return {"ok": True, "retida": d.retida, "revisao": rev}
    finally:
        con.close()


@router.get("/lotes/{lote_id}/saidas-cv")
def saidas_cv(lote_id: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Tudo o que o CAMP Vision gravou em catalogacao/ deste lote (avisos, relatório, retiradas, propostas, decisões, orientação, sugestões, releituras)."""
    from .saidas_cv import ler_saidas, conferencia_do_lote
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo, pasta_qnap, aprovado_em FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
    finally:
        con.close()
    pasta = Path(l["pasta_qnap"] or "")
    if not pasta.is_absolute():
        pasta = _qnap_prontos_raiz() / pasta
    con = connect()
    try:
        resp = {}
        for r in con.execute("SELECT * FROM cv_resposta WHERE lote_id=?", (lote_id,)):
            if r["tipo"] == "proposta" and r["chave"] == "obras:decisao":     # CAMP-126: ver _responder_cv
                resp["obras:decisao"] = {"acao": r["valor"], "por": r["por"], "em": r["em"], "motivo": r["motivo"], "valor": r["valor"]}
            else:
                resp[f"{r['tipo']}:{r['chave']}"] = {"acao": r["acao"], "por": r["por"], "em": r["em"], "motivo": r["motivo"], "valor": r["valor"]}
        conf = conferencia_do_lote(con, lote_id)   # o aceite é uma foto da leitura: o que já foi conferido no painel resolve o que pede olho humano
    finally:
        con.close()
    out = ler_saidas(pasta, dict(p) if p else {}, resp, conf)
    ac = out.get("aceite")
    if ac and ac.get("situacao") == "reprovado" and p and p["status_site"] == "no_ar":
        ac["situacao"] = "historico"   # 19/10: projeto JÁ publicado: o aceite da leitura vira só registro (nunca "não pode ser publicado" no que está publicado)
    # CAMP-130: a tela diz se o aceite que falta importa (lote já aprovado por uma pessoa: não importa) — campo novo, opcional
    return {"lote_id": lote_id, "projeto_codigo": l["projeto_codigo"], "lote_aprovado_em": l["aprovado_em"], **out}


class RespostaCV(BaseModel):
    tipo: str
    chave: str
    acao: str
    valor: str | None = None
    motivo: str | None = None


_COLUNA_CV = {"titulo": "titulo", "ano": "ano", "cidade": "cidade", "uf": "uf", "cliente": "cliente", "endereco": "endereco_obra"}
# 20/10 (CAMP-126): "obras": a decisão sobre as obras distintas que o CAMP Vision achou na pasta (chave "decisao").
_RESPOSTAS_CV = {"sugestao": ("usar", "ignorar"), "proposta": ("aceitar", "recusar"), "retirado": ("devolver",), "releitura": ("aceitar", "ignorar"), "obras": ("mesmo_conjunto", "separar")}


def _responder_cv(con, l, d: RespostaCV, u: dict) -> None:
    """Grava UMA resposta ao CAMP Vision (a conexão é de quem chama; não faz commit). Levanta HTTPException com a mensagem para a pessoa."""
    import re as _re
    if d.tipo not in _RESPOSTAS_CV or d.acao not in _RESPOSTAS_CV[d.tipo]:
        raise HTTPException(400, "Resposta inválida")
    if d.tipo == "retirado":
        if u["papel"] not in ("admin", "master"):
            raise HTTPException(403, "Só um admin devolve à revisão uma folha retirada pelo CAMP Vision")
        if len((d.motivo or "").strip()) < 3:
            raise HTTPException(400, "Explique por que a folha volta para a revisão")
    # a tabela cv_resposta só aceita os tipos antigos (CHECK): a decisão das obras fica como uma "proposta" de chave própria ("obras:decisao",
    # aceitar = mesmo conjunto, recusar = separar; o valor guarda a ação), e /saidas-cv a devolve como "obras:decisao". Nenhuma tabela é recriada.
    # CAMP-131: pelo mesmo motivo, a resposta à releitura vai como 'proposta' com a chave 'releitura:…'
    if d.tipo == "obras":
        tipo_db, chave_db, acao_db = "proposta", "obras:decisao", ("aceitar" if d.acao == "mesmo_conjunto" else "recusar")
    elif d.tipo == "releitura":
        tipo_db, chave_db, acao_db = "proposta", "releitura:" + d.chave, d.acao
    else:
        tipo_db, chave_db, acao_db = d.tipo, d.chave, d.acao
    if con.execute("SELECT 1 FROM cv_resposta WHERE lote_id=? AND tipo=? AND chave=?", (l["id"], tipo_db, chave_db[:200])).fetchone():
        raise HTTPException(409, "Isso já foi respondido")
    valor = (d.acao if d.tipo == "obras" else (d.valor or "").strip()[:300]) or None
    if d.tipo == "releitura" and d.acao == "aceitar":         # CAMP-131 (P10): aplicar UMA mudança que a releitura trouxe (o valor vem do arquivo, não da tela)
        valor = _aplicar_mudanca_releitura(con, l, d.chave, u["email"])
    if d.tipo == "sugestao" and d.acao == "usar":
        col = _COLUNA_CV.get(d.chave)
        if not col or not valor:
            raise HTTPException(400, "Este campo não pode ser preenchido por sugestão")
        atual = con.execute(f"SELECT {col} FROM projeto WHERE codigo=?", (l["projeto_codigo"],)).fetchone()[0]
        atual_txt = "" if atual in (None, 0, "0") else str(atual).strip()
        if atual_txt and not (d.chave == "titulo" and _re.fullmatch(r"P\d{4}", atual_txt)):
            raise HTTPException(409, f"O campo já foi preenchido por uma pessoa ('{atual_txt}'): a sugestão não substitui")
        if col == "ano":
            if not _re.fullmatch(r"\d{4}", valor):
                raise HTTPException(400, "Ano sugerido inválido")
            con.execute("UPDATE projeto SET ano=?, atualizado_em=datetime('now') WHERE codigo=?", (int(valor), l["projeto_codigo"]))
        else:
            if col == "uf":
                valor = valor.upper()
                if not _re.fullmatch(r"[A-Z]{2}", valor):
                    raise HTTPException(400, "UF sugerida inválida (use a sigla, ex.: SP)")
            con.execute(f"UPDATE projeto SET {col}=?, atualizado_em=datetime('now') WHERE codigo=?", (valor, l["projeto_codigo"]))
    con.execute("INSERT INTO cv_resposta (lote_id, projeto_codigo, tipo, chave, acao, valor, motivo, por) VALUES (?,?,?,?,?,?,?,?)",
                (l["id"], l["projeto_codigo"], tipo_db, chave_db[:200], acao_db, valor, (d.motivo or "").strip()[:300] or None, u["email"]))
    _evento(con, "projeto", l["projeto_codigo"], f"cv_{d.tipo}_{d.acao}", u["email"], {"lote": l["id"], "chave": d.chave, "valor": valor, "motivo": d.motivo})


@router.post("/lotes/{lote_id}/saidas-cv/resposta")
def responder_cv(lote_id: int, d: RespostaCV, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Uma pessoa responde ao CAMP Vision. sugestao: usar (grava SÓ se o campo ainda estiver vazio ou com título provisório) | ignorar.
    proposta: aceitar | recusar (só registra; nada é aplicado sozinho). retirado: devolver (admin, motivo obrigatório; entra na próxima importação).
    obras (chave "decisao"): mesmo_conjunto (fecha o aviso das obras distintas; fica no histórico) | separar (registra; as folhas são movidas pelo
    "Mover folhas", que continua só para admin e só dentro do fundo)."""
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        _responder_cv(con, l, d, u)
        fechados = []
        if d.tipo == "retirado":                                   # 19/10: devolver à revisão resolve o problema "o CAMP Vision retirou esta folha"
            from .problemas import fechar_resolvidos
            fechados = fechar_resolvidos(con, u["email"])
        con.commit()
        if fechados:
            return {"ok": True, "problemas_fechados": len(fechados)}
        return {"ok": True}
    finally:
        con.close()


from .saidas_cv import CAMPO_RELEITURA_FOLHA as _CAMPO_RELEITURA, normalizar_comparacao as _normalizar_comparacao   # CAMP-134: formato real do CV2


def _aplicar_mudanca_releitura(con, l, chave: str, ator: str) -> str:
    """chave = "<quando>|<código da folha>|<campo>": lê catalogacao/releituras/<quando>/comparacao.json da pasta do lote e grava o "agora" na folha."""
    try:
        quando, cod, campo = chave.split("|", 2)
    except ValueError:
        raise HTTPException(400, "Mudança inválida")
    if not re.fullmatch(r"[\w.\-]+", quando or ""):
        raise HTTPException(400, "Mudança inválida")
    col = _CAMPO_RELEITURA.get(campo)
    if not col:
        raise HTTPException(400, f"O campo '{campo}' não se aplica sozinho: corrija na própria folha")
    it = con.execute("SELECT codigo FROM item WHERE codigo=? AND projeto_codigo=?", (cod, l["projeto_codigo"])).fetchone()
    if not it:
        raise HTTPException(404, "Folha não existe neste projeto")
    lp = con.execute("SELECT pasta_qnap FROM lista_processamento WHERE id=?", (l["id"],)).fetchone()
    pasta = Path(lp["pasta_qnap"] or "")
    if not pasta.is_absolute():
        pasta = _qnap_prontos_raiz() / pasta
    try:
        comp = json.loads((pasta / "catalogacao" / "releituras" / quando / "comparacao.json").read_text(encoding="utf-8"))
        agora = ((_normalizar_comparacao(comp).get(str(cod).upper()) or {}).get(campo) or {}).get("agora")
    except (OSError, ValueError, AttributeError):
        agora = None
    if agora in (None, ""):
        raise HTTPException(409, "O painel não acha mais esta mudança na pasta do lote (a releitura foi refeita?)")
    agora = str(agora).strip()[:300]
    if col == "ano_folha":
        if not re.fullmatch(r"\d{4}", agora):
            raise HTTPException(400, "Ano inválido na releitura")
        con.execute("UPDATE item SET ano_folha=?, atualizado_em=datetime('now') WHERE codigo=?", (int(agora), cod))
    elif col == "tipo_documento":
        # 23/10 (erro 500 em "Aceitar"): o CV2 lê vários tipos juntos ("Planta / Corte / Detalhe"), e tipo_documento é ligado ao vocabulário
        # (chave estrangeira). Mesma regra de editar a folha: cada tipo tem de existir; o primeiro em tipo_documento, a lista em tipos_documento.
        from .importador_lote import _ALIAS_TIPO
        from .tipos_documento import juntar
        tipos = {n.lower(): n for (n,) in con.execute("SELECT nome FROM tipo_documento")}
        lista = []
        for parte in re.split(r"\s*;\s*|\s+/\s+", " ".join(agora.split())):
            p_ = parte.strip().lower()
            if not p_:
                continue
            nome = tipos.get(_ALIAS_TIPO.get(p_, "").lower()) if p_ in _ALIAS_TIPO else tipos.get(p_)
            if not nome:
                raise HTTPException(400, f"O tipo “{parte.strip()}” que o CAMP Vision leu não existe no vocabulário: escolha o tipo na própria folha")
            if nome not in lista:
                lista.append(nome)
        if not lista:
            raise HTTPException(400, "A releitura não trouxe um tipo válido")
        agora = juntar(lista)
        con.execute("UPDATE item SET tipo_documento=?, tipos_documento=?, atualizado_em=datetime('now') WHERE codigo=?",
                    (lista[0], agora if len(lista) > 1 else None, cod))
    else:
        con.execute(f"UPDATE item SET {col}=?, atualizado_em=datetime('now') WHERE codigo=?", (agora, cod))
    _evento(con, "item", cod, "releitura_aceita", ator, {"campo": campo, "valor": agora, "quando": quando})
    return agora


class RespostasCV(BaseModel):
    respostas: list[RespostaCV]


@router.post("/lotes/{lote_id}/saidas-cv/respostas")
def responder_cv_em_lote(lote_id: int, d: RespostasCV, u: dict = Depends(auth.exige("operador"))) -> dict:
    """20/10 (CAMP-125): várias respostas de uma vez ("Aceitar todas onde hoje está vazio", "Recusar as restantes", "Usar todas").
    Cada uma segue as mesmas regras da resposta única (sugestão nunca troca o que alguém escreveu); a que não puder ser gravada é
    pulada e volta em `puladas` com o motivo, e as outras ficam gravadas. Devolução de folha retirada não entra em lote."""
    if len(d.respostas) > 500:
        raise HTTPException(400, "Respostas demais de uma vez")
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        feitas, puladas = 0, []
        for r in d.respostas:
            if r.tipo == "retirado":
                puladas.append({"chave": r.chave, "motivo": "devolver folha retirada é uma de cada vez"})
                continue
            try:
                con.execute("SAVEPOINT r1")
                _responder_cv(con, l, r, u)
                con.execute("RELEASE r1")
                feitas += 1
            except HTTPException as e:
                con.execute("ROLLBACK TO r1"); con.execute("RELEASE r1")
                puladas.append({"tipo": r.tipo, "chave": r.chave, "motivo": e.detail})
        con.commit()
        return {"ok": True, "feitas": feitas, "puladas": puladas}
    finally:
        con.close()


@router.post("/lotes/{lote_id}/conferir-sem-pendencia")
def conferir_sem_pendencia(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca como conferida só a folha SEM nada que o CAMP Vision tenha apontado (bloqueio, ressalva, sinal) e com título preenchido. O resto fica para um olho humano."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        marcadas = 0
        for i in con.execute(f"SELECT codigo, titulo, status_site, pendencias, duplicata_de, autoria_divergente, espelhado, espelho_manual FROM item WHERE {_DO_LOTE} AND revisao='pendente'", (lote_id,)).fetchall():
            if _aviso_da_folha(con, i):
                continue
            con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (u["email"], i["codigo"]))
            marcadas += 1
        restam = con.execute(f"SELECT COUNT(*) FROM item WHERE {_DO_LOTE} AND revisao='pendente'", (lote_id,)).fetchone()[0]
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", u["email"], {"lote_id": lote_id, "conferidas": marcadas, "restam": restam})
        con.commit()
        return {"conferidas": marcadas, "restam": restam}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


def _aviso_da_folha(con, i) -> str | None:
    """Uma mesma política protege a conferência manual e automática."""
    from .revisao_politica import motivo_para_conferir
    motivo = motivo_para_conferir(dict(i))
    if motivo:
        return motivo
    if con.execute("SELECT 1 FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao') LIMIT 1", (i["codigo"],)).fetchone():
        return "problema aberto"
    if "retida" in i.keys() and i["retida"]:      # UX-11: folha retida conta em "Com problema" na tela; em massa não se confere
        return "retida"
    return None

AUTOMATICO = "painel (sem aviso: conferida sozinha)"


def conferir_so_avisos() -> bool:
    """CAMP-150: configuração revisao.conferir_so_avisos (sem a chave ou 0: desligado, como antes)."""
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='revisao.conferir_so_avisos'").fetchone()
    finally:
        con.close()
    return bool(r) and str(r[0]).strip() == "1"


def _pendentes_do_lote(con, lote_id: int):
    return con.execute(f"""SELECT codigo, titulo, status_site, pendencias, duplicata_de, autoria_divergente, espelhado, espelho_manual, retida FROM item
                           WHERE {_DO_LOTE} AND revisao='pendente' AND status_site NOT IN ('rascunho','no_ar') ORDER BY codigo""", (lote_id,)).fetchall()


def contar_sem_aviso(con, lote_id: int) -> int:
    """UX-11: quantas folhas a conferir do lote NÃO têm nenhum aviso (o número do botão "Conferir só sem avisos"). Mesma regra de conferir_sem_aviso."""
    return sum(1 for i in _pendentes_do_lote(con, lote_id) if not _aviso_da_folha(con, i))


def conferir_sem_aviso(con, lote_id: int, ator: str, automatico: bool = False, pular=None) -> dict:
    """Marca como conferidas as folhas pendentes do lote que NÃO têm nada para ver (regra do CAMP-094). Não faz commit.
    automatico=True (CAMP-150, ao importar): o histórico diz "conferida automaticamente" e lista as folhas.
    pular (UX-11): códigos que a tela mostra com aviso (ex.: orientação incerta da lista orientacao.txt do CAMP Vision, que o servidor
    não lê numa requisição): ficam para revisão manual mesmo que a regra do servidor não veja aviso. Só soma cautela, nunca tira."""
    l = _lote(con, lote_id)
    pular = {str(x) for x in (pular or [])}
    marcadas, ficaram, conferidas = 0, [], []
    for i in _pendentes_do_lote(con, lote_id):
        motivo = _aviso_da_folha(con, i) or ("aviso na tela" if i["codigo"] in pular else None)
        if motivo:
            ficaram.append({"codigo": i["codigo"], "motivo": motivo})
            continue
        con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (ator, i["codigo"]))
        marcadas += 1; conferidas.append(i["codigo"])
    restam = con.execute(f"SELECT COUNT(*) FROM item WHERE {_DO_LOTE} AND revisao='pendente'", (lote_id,)).fetchone()[0]
    if automatico:
        if marcadas:
            _evento(con, "projeto", l["projeto_codigo"], "conferida_automaticamente", ator, {"lote_id": lote_id, "conferidas": conferidas,
                                                                                          "ficaram_para_conferir": [x["codigo"] for x in ficaram]})
    else:
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", ator, {"lote_id": lote_id, "todas": True, "conferidas": marcadas,
                                                                              "ficaram_para_conferir": [x["codigo"] for x in ficaram]})
    return {"conferidas": marcadas, "com_pendencia": len(ficaram), "ficaram": ficaram, "restam": restam, "codigos": conferidas}   # 'codigos': campo novo, opcional (UX-11: Desfazer)


class ConferirTodas(BaseModel):
    pular: list[str] = []


class DesfazerConferirTodas(BaseModel):
    codigos: list[str]


@router.post("/lotes/{lote_id}/conferir-todas")
def conferir_todas(lote_id: int, d: ConferirTodas | None = None, u: dict = Depends(auth.exige("operador"))) -> dict:
    """"Aprovar todas": marca como conferidas as folhas pendentes do lote que NÃO têm nada para ver.
    CAMP-094 (decisão de 20/10): não fecha aviso que ninguém viu. A folha com aviso ou problema aberto (bloqueio, duplicata, autoria, espelho a
    confirmar, sinal do CAMP Vision, problema na lista) fica "a conferir" e volta em `ficaram` (código e motivo), para conferir uma a uma.
    Não aprova o lote: isso continua sendo do admin."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        r = conferir_sem_aviso(con, lote_id, u["email"], pular=(d.pular if d else None))
        con.commit()
        return r
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/lotes/{lote_id}/conferir-todas/desfazer")
def desfazer_conferir_todas(lote_id: int, d: DesfazerConferirTodas, u: dict = Depends(auth.exige("operador"))) -> dict:
    """UX-11: "Desfazer" do "Conferir só sem avisos". Volta para "a conferir" só as folhas da lista que ainda estão como esta pessoa
    as deixou (conferida por ela, no lote, fora do site). A folha que alguém mexeu depois fica como está. Lote aprovado: recusa."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        voltaram, ficaram = [], []
        for cod in dict.fromkeys(str(x) for x in d.codigos):
            i = con.execute(f"SELECT codigo FROM item WHERE codigo=? AND {_DO_LOTE} AND revisao='conferida' AND revisado_por=? AND status_site NOT IN ('rascunho','no_ar')",
                            (cod, lote_id, u["email"])).fetchone()
            if not i:
                ficaram.append(cod)
                continue
            con.execute("UPDATE item SET revisao='pendente', revisado_por=NULL, revisado_em=NULL, atualizado_em=datetime('now') WHERE codigo=?", (cod,))
            voltaram.append(cod)
        if voltaram:
            _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote_desfeita", u["email"], {"lote_id": lote_id, "voltaram": voltaram})
        restam = con.execute(f"SELECT COUNT(*) FROM item WHERE {_DO_LOTE} AND revisao='pendente'", (lote_id,)).fetchone()[0]
        con.commit()
        return {"voltaram": len(voltaram), "ficaram": ficaram, "restam": restam}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class Giro(BaseModel):
    graus: int      # 90 (horário), -90 (anti-horário) ou 180


@router.post("/itens/{codigo}/girar")
def girar(codigo: str, d: Giro, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Vira a prévia da folha (e a imagem que vai ao site). A tela e o site mostram a folha já virada; o arquivo original no QNAP não é tocado.
    Folha JÁ no site (rascunho ou publicada): só admin. O painel troca o arquivo da imagem no site mantendo o ID do anexo e só grava
    o giro se o site aceitar; se o site falhar, nada muda no painel."""
    if d.graus not in (90, -90, 180):
        raise HTTPException(400, "graus deve ser 90, -90 ou 180")
    if not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh e tente de novo")
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE}, i.status_site, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        no_site = i["status_site"] in ("rascunho", "no_ar")
        adm = u["papel"] in ("admin", "master")
        novo = ((i["giro_manual"] or 0) + d.graus) % 360
        rec, ang = ajuste.depois_do_giro(*ajuste.ler(i), d.graus)       # 19/10: com recorte, a caixa gira junto
        site = None
        if no_site and not adm:                       # 19/10: operador gira no painel; a imagem do site fica pendente até um admin clicar "Atualizar imagem no site"
            con.execute("UPDATE item SET giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, codigo))
            _regravar_ajuste(con, i, novo, imagens.espelho_efetivo(i), rec, ang)
            _imagem_site_pendente(con, codigo)
            _site_logo_depois(tarefas, codigo, u)     # 21/10: a imagem nova vai sozinha ao site
            _evento(con, "item", codigo, "giro", u["email"], {"de": i["giro_manual"], "para": novo, "site": "pendente"})
            con.commit()
            from .alteracoes_site import enviar_sozinho
            return {"giro_manual": novo, "no_site": False, "site_pendente": True, "site_automatico": enviar_sozinho()}   # 21/10: campo novo, opcional
        if no_site:                                   # admin: primeiro o site; o painel só grava se o site aceitou
            from . import publicador
            try:
                site = publicador.girar_imagem_no_site(codigo, novo, (rec, ang))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(502, f"O site não aceitou a imagem girada, e nada foi mudado no painel: {str(e)[:240]}")
        con.execute("UPDATE item SET giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, codigo))
        _regravar_ajuste(con, i, novo, imagens.espelho_efetivo(i), rec, ang)
        if site:
            _imagem_site_resolvida(con, codigo)
            _evento(con, "item", codigo, "giro_no_site", u["email"], {"de": i["giro_manual"], "para": novo, "anexo": site["media_id"]})
        else:
            _evento(con, "item", codigo, "giro", u["email"], {"de": i["giro_manual"], "para": novo})
        con.commit()
        return {"giro_manual": novo, "no_site": bool(site)}
    finally:
        con.close()


@router.post("/itens/{codigo}/espelhar")
def espelhar(codigo: str, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Espelha (ou desespelha) a prévia da folha e a imagem que vai ao site: para a folha digitalizada pelo verso, com o texto ao contrário.
    Espelha o que a pessoa VÊ: com a folha deitada (giro 90/270), o giro é trocado pelo oposto para o espelho continuar sendo esquerda-direita na tela.
    O arquivo original no QNAP não é tocado."""
    if not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh e tente de novo")
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE}, i.status_site, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        no_site = i["status_site"] in ("rascunho", "no_ar")   # 19/10: espelha no painel; a imagem do site fica pendente ("Atualizar imagem no site")
        antes = imagens.espelho_efetivo(i)
        novo, giro = (0 if antes else 1), (-(i["giro_manual"] or 0)) % 360
        con.execute("UPDATE item SET espelho_manual=?, giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, giro, codigo))
        _regravar_ajuste(con, i, giro, bool(novo), *ajuste.depois_do_espelho(*ajuste.ler(i)))      # 19/10: com recorte, a caixa espelha junto
        _evento(con, "item", codigo, "espelho", u["email"], {"de": int(antes), "para": novo, "giro": giro, **({"site": "pendente"} if no_site else {})})
        if no_site:
            _imagem_site_pendente(con, codigo)
            _site_logo_depois(tarefas, codigo, u)     # 21/10: a imagem nova vai sozinha ao site
        con.commit()
        from .alteracoes_site import enviar_sozinho
        return {"espelhar": bool(novo), "giro_manual": giro, "site_pendente": no_site, "site_automatico": bool(no_site) and enviar_sozinho()}
    finally:
        con.close()


@router.post("/lotes/{lote_id}/aprovar")
def aprovar(lote_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "Este lote já foi aprovado")
        c = _contagem(con, lote_id)
        if c["total"] == 0:
            outras = con.execute("""SELECT COUNT(*) FROM item
                  WHERE projeto_codigo=? AND lote_id<>?""", (l["projeto_codigo"], lote_id)).fetchone()[0]
            detalhe = (f" Este projeto já tem {outras} folha(s) em outro(s) lote(s). "
                       "Abra o lote que tem folhas conferidas ou clique em Publicar o projeto."
                       if outras else " Importe primeiro as folhas deste lote, ou traga as retidas para conferência.")
            raise HTTPException(409, "Este lote não possui folhas para aprovar." + detalhe)
        if c["pendente"]:
            raise HTTPException(400, f"Faltam conferir {c['pendente']} folha(s)")
        con.execute("UPDATE lista_processamento SET aprovado_por=?, aprovado_em=datetime('now'), atualizado_em=datetime('now') WHERE id=?", (u["email"], lote_id))
        _evento(con, "projeto", l["projeto_codigo"], "revisao_aprovada", u["email"], {"lote_id": lote_id, "folhas": c["total"], "bloqueadas": c["bloqueadas"]})
        con.commit()
        return {"ok": True, **c}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/lotes/{lote_id}/reabrir")
def reabrir(lote_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if not l["aprovado_em"]:
            raise HTTPException(409, "Este lote não está aprovado")
        if l["etapa"] in ("rascunho", "publicado"):
            raise HTTPException(409, "O lote já foi para o site: não dá para reabrir a revisão")
        con.execute("UPDATE lista_processamento SET aprovado_por=NULL, aprovado_em=NULL, atualizado_em=datetime('now') WHERE id=?", (lote_id,))
        _evento(con, "projeto", l["projeto_codigo"], "revisao_reaberta", u["email"], {"lote_id": lote_id})
        con.commit()
        return {"ok": True}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


def jpg_da_folha_no_qnap(raiz, rel):
    """O JPG da folha (item.arquivo_jpg, relativo à raiz dos prontos) se existir e estiver DENTRO da raiz; senão None. Serve de prévia quando o CAMP Vision não gravou preview.
    21/10: ou o JPG de uma folha enviada pelo painel (só de dentro da pasta das folhas enviadas)."""
    if not rel or str(rel).startswith("http"):
        return None
    from .folhas_enviadas import dentro
    env = dentro(rel)
    if env:
        return env
    try:
        c = Path(str(rel))
        alvo = c.resolve() if c.is_absolute() else (raiz / str(rel)).resolve()
        if raiz.resolve() in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
            return alvo
    except OSError:
        return None
    return None


@router.get("/itens/{codigo}/previa")
def previa(codigo: str, t: int = 0, o: int = 0, u: dict = Depends(auth.exige("leitura"))) -> FileResponse:
    """Prévia (~3000 px, já girada) que o CAMP Vision grava em ACERVOS_CAMP/_campvision/preview/. O caminho vem do pacote (de fora): só serve de dentro dessa pasta.
    19/10: folha com recorte/alinhamento serve o JPG corrigido do painel (o = 1: sem o ajuste, para a tela de recortar)."""
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE.replace('i.', '')} FROM item WHERE codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    try:
        rel = (json.loads(i["pendencias"] or "{}") if i else {}).get("previa") or ""
    except ValueError:
        rel = ""
    raiz = _qnap_prontos_raiz()
    alvo = None
    if rel and rel != "@jpg":
        base = (raiz / "_campvision" / "preview").resolve()
        cand = (raiz / rel).resolve()
        if base in cand.parents and cand.suffix.lower() in (".jpg", ".jpeg") and cand.stem == codigo and cand.is_file():
            alvo = cand
    if alvo is None:                                   # lote anterior ao preview do CAMP Vision: o JPG da folha no QNAP (sempre DENTRO da raiz dos prontos)
        alvo = jpg_da_folha_no_qnap(raiz, i["arquivo_jpg"] if i else None)
    if alvo is None and (not i or _fala_de_outro_projeto(i["pendencias"])):   # 20/10 (CAMP-069): folha retirada/"de outro projeto": ver antes de decidir
        c2 = connect()
        try:
            alvo = _imagem_da_folha_fora_do_painel(c2, codigo)
        finally:
            c2.close()
    if alvo is None:
        raise HTTPException(404, "Sem prévia" if i else "Sem imagem: a folha não está no painel e não achei o JPG dela no lote")
    giro, lado = (i["giro_manual"] if i else 0), (t if 120 <= t <= 1600 else 0)     # t = miniatura (lado maior em px); 0 = tamanho da prévia
    esp = bool(i) and imagens.espelho_efetivo(i)
    rec, ang = ajuste.ler(i) if i and not o else (None, 0.0)
    if (giro or esp or ajuste.tem_ajuste(rec, ang)) and not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh")
    if ajuste.tem_ajuste(rec, ang):                    # o JPG corrigido (gera de novo se sumiu ou se a origem mudou)
        try:
            alvo, rel = ajuste.garantir(codigo, alvo, giro, esp, ang, rec)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"Não consegui preparar a imagem recortada: {str(e)[:120]}")
        giro, esp = 0, False
        if rel != i["imagem_corrigida"]:
            c2 = connect()
            try:
                c2.execute("UPDATE item SET imagem_corrigida=? WHERE codigo=?", (rel, codigo)); c2.commit()
            finally:
                c2.close()
    if (giro or lado or esp) and imagens.disponivel():
        try:
            alvo = imagens.jpeg_girado(alvo, giro, lado or None, esp)
        except Exception as e:  # noqa: BLE001  (arquivo corrompido, disco cheio...)
            raise HTTPException(500, f"Não consegui preparar a imagem: {str(e)[:120]}")
    return FileResponse(alvo, headers={"Cache-Control": "private, max-age=3600"})


# ---------------- 19/10 · recorte e alinhamento manual ----------------
_COLS_AJUSTE = ("i.codigo, i.pendencias, i.giro_manual, i.arquivo_jpg, i.espelhado, i.espelho_manual, i.recorte, i.alinhamento, i.imagem_corrigida")


def _regravar_ajuste(con, i, giro: int, esp: bool, rec, ang) -> str | None:
    """Grava recorte/ângulo e (re)gera o JPG corrigido para o giro/espelho novos. Sem ajuste: limpa tudo (a folha volta à imagem do CAMP Vision)."""
    rel = None
    if ajuste.tem_ajuste(rec, ang):
        origem = ajuste.origem_da_folha(_qnap_prontos_raiz(), i)
        if origem is not None:
            rel = ajuste.garantir(i["codigo"], origem, giro, esp, ang, rec)[1]
    con.execute("UPDATE item SET recorte=?, alinhamento=?, imagem_corrigida=? WHERE codigo=?", (ajuste.para_gravar(rec), ang or 0, rel, i["codigo"]))
    return rel


class Ajuste(BaseModel):
    recorte: dict | None = None     # {"x","y","w","h"} em frações (0–1); None = a imagem inteira
    angulo: float = 0               # -10 a +10, positivo = horário


@router.post("/itens/{codigo}/ajuste")
def ajustar(codigo: str, d: Ajuste, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Recorta e/ou endireita a folha. Guarda os parâmetros na folha e GERA o JPG corrigido (diretório de dados do painel), que passa a
    ser a imagem da folha na prévia, nas miniaturas, nos pedidos em JPG e no site. O TIF e os arquivos do CAMP Vision não mudam.
    Recorte inteiro e ângulo 0 = desfazer (volta à imagem do CAMP Vision). Mesmas regras do giro: lote aprovado recusa; folha no site,
    só admin, e a imagem do site é trocada (mesmo anexo); se o site recusar, o painel grava e fica uma pendência para reenviar."""
    if not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh e tente de novo")
    try:
        rec, ang = ajuste.normalizar(d.recorte, d.angulo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE}, i.status_site, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        no_site = i["status_site"] in ("rascunho", "no_ar")
        so_painel = no_site and u["papel"] not in ("admin", "master")   # 19/10: operador ajusta no painel; o site fica pendente
        antes = ajuste.ler(i)
        reenviar = no_site and con.execute("SELECT 1 FROM divergencia_site WHERE entidade='item' AND codigo=? AND campo='pendente_imagem_ajustada' AND resolvida=0", (codigo,)).fetchone()
        if (rec, ang) == antes and not reenviar:      # nada mudou (com pendência no site, aplicar de novo reenvia)
            return {"recorte": rec, "angulo": ang, "imagem_corrigida": bool(i["imagem_corrigida"]), "no_site": False, "mudou": False}
        giro, esp = i["giro_manual"] or 0, imagens.espelho_efetivo(i)
        if ajuste.tem_ajuste(rec, ang):
            origem = ajuste.origem_da_folha(_qnap_prontos_raiz(), i)
            if origem is None:
                raise HTTPException(404, "A imagem desta folha não está no QNAP: sem ela não dá para recortar")
            try:
                ajuste.garantir(codigo, origem, giro, esp, ang, rec)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(500, f"Não consegui gerar a imagem recortada: {str(e)[:160]}")
        site, pendencia = None, None
        if so_painel:
            _imagem_site_pendente(con, codigo)
            _site_logo_depois(tarefas, codigo, u)     # 21/10: a imagem nova vai sozinha ao site
            pendencia = "O site recebe a imagem recortada em seguida"
        elif no_site:                                 # a imagem do site acompanha; se o site recusar, o painel grava e fica a pendência
            from . import publicador
            try:
                site = publicador.girar_imagem_no_site(codigo, giro, (rec, ang))
            except Exception as e:  # noqa: BLE001
                pendencia = f"A imagem nova não foi para o site: {str(e)[:200]}"
                publicador._pendencia(con, "item", codigo, "pendente_imagem_ajustada", pendencia + ". Aplique de novo para reenviar")
        rel = _regravar_ajuste(con, i, giro, esp, rec, ang)
        con.execute("UPDATE item SET atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
        if site:
            con.execute("UPDATE divergencia_site SET resolvida=1 WHERE entidade='item' AND codigo=? AND campo='pendente_imagem_ajustada' AND resolvida=0", (codigo,))
        det = {"de": {"recorte": antes[0], "angulo": antes[1]}, "para": {"recorte": rec, "angulo": ang}}
        if rel:
            det["arquivo"] = rel
        if site:
            det["anexo"] = site["media_id"]
        if pendencia:
            det["site"] = pendencia
        _evento(con, "item", codigo, "ajuste_imagem" if ajuste.tem_ajuste(rec, ang) else "ajuste_desfeito", u["email"], det)
        con.commit()
        return {"recorte": rec, "angulo": ang, "imagem_corrigida": bool(rel), "no_site": bool(site), "pendencia": pendencia, "mudou": True}
    finally:
        con.close()


PEND_IMAGEM = "pendente_imagem_ajustada"


def _site_logo_depois(tarefas, codigo: str, u: dict) -> None:
    """21/10 (Rafa: "ao alterar aí, já altere no site automaticamente"): depois de responder, a folha já no site recebe a imagem nova.
    Se o site recusar, continua a pendência "Atualizar imagem no site" (como antes)."""
    from .alteracoes_site import enviar_folhas_agora
    tarefas.add_task(enviar_folhas_agora, [codigo], u["email"])


def _imagem_site_pendente(con, codigo: str) -> None:
    from . import publicador
    publicador._pendencia(con, "item", codigo, PEND_IMAGEM, "A imagem no site ainda é a antiga: use “Atualizar imagem no site”")


def _imagem_site_resolvida(con, codigo: str) -> None:
    con.execute("UPDATE divergencia_site SET resolvida=1 WHERE entidade='item' AND codigo=? AND campo=? AND resolvida=0", (codigo, PEND_IMAGEM))


def imagem_site_pendente(con, codigo: str) -> bool:
    return bool(con.execute("SELECT 1 FROM divergencia_site WHERE entidade='item' AND codigo=? AND campo=? AND resolvida=0", (codigo, PEND_IMAGEM)).fetchone())


@router.post("/itens/{codigo}/imagem/atualizar-site")
def atualizar_imagem_no_site(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """19/10: folha já no site que foi girada/espelhada/recortada no painel: troca o arquivo da imagem no site pela de agora
    (mesmo anexo, o endereço não muda). Se o site recusar, nada muda e a pendência continua."""
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE}, i.status_site FROM item i WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        if i["status_site"] not in ("rascunho", "no_ar"):
            raise HTTPException(409, "Esta folha não está no site: a imagem nova vai junto quando ela for publicada")
        giro = i["giro_manual"] or 0
    finally:
        con.close()
    from . import publicador
    try:
        site = publicador.girar_imagem_no_site(codigo, giro)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"O site não aceitou a imagem nova; a do site continua a antiga: {str(e)[:240]}")
    con = connect()
    try:
        _imagem_site_resolvida(con, codigo)
        _evento(con, "item", codigo, "imagem_atualizada_no_site", u["email"], {"anexo": site["media_id"], "giro": giro})
        con.commit()
        return {"ok": True, "anexo": site["media_id"]}
    finally:
        con.close()


@router.get("/itens/{codigo}/ajuste")
def ver_ajuste(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """O recorte/ângulo gravados e a orientação (giro/espelho) da folha: a tela de recortar parte daqui (o giro pode ter mudado a caixa)."""
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE} FROM item i WHERE i.codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    if not i:
        raise HTTPException(404, "Folha não existe")
    rec, ang = ajuste.ler(i)
    return {"recorte": rec, "angulo": ang, "giro_manual": i["giro_manual"] or 0, "espelhar": imagens.espelho_efetivo(i), "imagem_corrigida": bool(i["imagem_corrigida"])}


@router.get("/itens/{codigo}/ajuste/sugerir")
def sugerir_ajuste(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """"Endireitar automaticamente": sugere o ângulo fino (não grava nada; a pessoa confere e aplica)."""
    if not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh e tente de novo")
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE} FROM item i WHERE i.codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    if not i:
        raise HTTPException(404, "Folha não existe")
    origem = ajuste.origem_da_folha(_qnap_prontos_raiz(), i)
    if origem is None:
        raise HTTPException(404, "A imagem desta folha não está no QNAP")
    try:
        return {"angulo": ajuste.sugerir_angulo(origem, i["giro_manual"] or 0, imagens.espelho_efetivo(i))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Não consegui analisar a imagem: {str(e)[:120]}")


@router.get("/itens/{codigo}/imagem-corrigida")
def baixar_corrigida(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> FileResponse:
    """O JPG corrigido da folha em tamanho cheio, para baixar (pedidos em JPG). Folha sem recorte/alinhamento: 404."""
    con = connect()
    try:
        i = con.execute(f"SELECT {_COLS_AJUSTE} FROM item i WHERE i.codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    rec, ang = ajuste.ler(i) if i else (None, 0.0)
    if not ajuste.tem_ajuste(rec, ang):
        raise HTTPException(404, "Esta folha não tem imagem corrigida (não foi recortada nem alinhada)")
    origem = ajuste.origem_da_folha(_qnap_prontos_raiz(), i)
    alvo = ajuste.caminho_gravado(i["imagem_corrigida"])
    if origem is not None:
        alvo = ajuste.garantir(codigo, origem, i["giro_manual"] or 0, imagens.espelho_efetivo(i), ang, rec)[0]
    if alvo is None:
        raise HTTPException(404, "A imagem desta folha não está no QNAP")
    return FileResponse(alvo, media_type="image/jpeg", filename=f"{codigo}.jpg")
