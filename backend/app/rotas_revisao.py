"""Revisão pós-CAMP Vision: importar as folhas do lote, conferir/corrigir, e o admin aprovar. Ler: leitura; revisar: operador; aprovar: admin."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ajuste_imagem as ajuste, auth, giro_imagem as imagens
from .db import connect
from .importador_lote import importar_lote, ler_pacote, tirar_projeto_divergente
from .rotas_operacao import _qnap_prontos_raiz

router = APIRouter(prefix="/api", tags=["revisao"])


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _lote(con, lote_id: int):
    l = con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
    if not l:
        raise HTTPException(404, "Lote não existe")
    return l


@router.get("/projetos/{codigo}/proximo-passo")
def proximo_passo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Em que ponto está o trabalho deste projeto e qual é o próximo passo (a MESMA fase da Fila: filas_fase). Escolhe a lista mais recente que ainda não foi publicada."""
    from .filas_fase import fase_da_lista
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        lotes = []
        for l in con.execute("""SELECT l.id, l.nome, l.etapa, l.aprovado_em, l.aprovado_por, l.atualizado_em, l.folhas_esperadas, l.folhas_encontradas,
                                       (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id) AS itens_total,
                                       (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.revisao='pendente') AS itens_pendentes
                                FROM lista_processamento l WHERE l.projeto_codigo=? ORDER BY l.id DESC""", (codigo,)):
            d = dict(l)
            d["itens_conferidos"] = d["itens_total"] - d["itens_pendentes"]
            d["fase"] = fase_da_lista(d["etapa"], d["itens_total"], d["itens_pendentes"], d["aprovado_em"])
            lotes.append(d)
        lote = next((x for x in lotes if x["fase"] != "publicado"), lotes[0] if lotes else None)
        return {"lote": lote, "lotes": len(lotes), "pode_operar": u["papel"] in ("operador", "admin", "master"), "pode_agir": u["papel"] in ("admin", "master")}
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


@router.post("/filas/importar-todas")
def importar_todas(u: dict = Depends(auth.exige("operador"))):
    """#97 + H4: "Importar todas (N)" da Fila vira UMA tarefa: importa, um por um, os lotes que esperam importação
    (as mesmas regras de /api/filas), com "3 de 14", o lote atual e o que falhou."""
    from . import pendencias, tarefas
    con = connect()
    try:
        alvo = [(l["id"], l["projeto_codigo"]) for l in pendencias.lotes(con) if l["fase"] == "importar"]
    finally:
        con.close()
    if not alvo:
        raise HTTPException(400, "Nenhum lote esperando importação")

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
        return {"ok": not falhas, "falhas": falhas, "lotes": ok, "folhas": folhas,
                "mensagem": f"{ok} de {len(alvo)} lote(s) importado(s), {folhas} folha(s) no painel" + (f"; {len(falhas)} não {'importou' if len(falhas) == 1 else 'importaram'}" if falhas else "") + ". Próximo passo: conferir."}
    return tarefas.iniciar("importar_todas", "filas", u, rodar, titulo=f"Importar {len(alvo)} lote(s) da Fila")


def _contagem(con, lote_id: int) -> dict:
    c = {"total": 0, "pendente": 0, "conferida": 0, "corrigida": 0, "bloqueadas": 0, "retidas": 0}
    c["retidas"] = con.execute("SELECT COUNT(*) FROM item WHERE lote_id=? AND retida=1", (lote_id,)).fetchone()[0]
    for r in con.execute("SELECT revisao, status_site, COUNT(*) FROM item WHERE lote_id=? GROUP BY revisao, status_site", (lote_id,)):
        c["total"] += r[2]
        c[r[0]] += r[2]
        if r[1] == "bloqueado":
            c["bloqueadas"] += r[2]
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
            if acessivel:
                try:
                    p = ler_pacote(pasta)
                except HTTPException:
                    p = None
                if p is not None:
                    docs = p.get("documentos") if isinstance(p.get("documentos"), list) else (p.get("itens") or [])
                    pacote.update({"existe": True, "documentos": len(docs), "retirados": len(p.get("retirados") or []), "teste": bool(p.get("teste"))})
            c = _contagem(con, l["id"])
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
            lotes.append({"id": l["id"], "nome": l["nome"], "etapa": l["etapa"], "aprovado_por": l["aprovado_por"], "aprovado_em": l["aprovado_em"], "pacote": pacote,
                          "itens": c, "importacao": importacao, "pode_aprovar": motivo is None, "motivo": motivo})
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


@router.post("/itens/{codigo}/revisao")
def revisar(codigo: str, d: RevisaoItem, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.estado not in ("pendente", "conferida", "corrigida"):
        raise HTTPException(400, "estado deve ser pendente, conferida ou corrigida")
    con = connect()
    try:
        i = con.execute("SELECT i.revisao, i.status_site, i.lote_id, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        fechado = "lote_aprovado" if i["aprovado_em"] else ("no_site" if i["status_site"] in ("rascunho", "no_ar") else None)
        if fechado and d.estado == "pendente":       # reabrir continua protegido
            raise HTTPException(409, "O lote desta folha já foi aprovado: reabra a revisão para mudar" if fechado == "lote_aprovado"
                                else "Esta folha já está no site: a revisão do lote não se aplica")
        if fechado:
            # 19/10 ("muito chato"): corrigir uma folha de lote aprovado (ou já no site) dava "os dados foram salvos, mas a revisão não mudou".
            # A correção (PATCH) já é o que importa; "conferida/corrigida" aqui só confirma: registra o que mudou e responde ok, sem reabrir nada.
            registrar_campos_revisados(con, codigo, d.estado, u["email"])
            con.commit()
            return {"ok": True, "revisao": i["revisao"], "sem_mudanca": fechado}
        con.execute("UPDATE item SET revisao=?, revisado_por=?, revisado_em=CASE WHEN ?='pendente' THEN NULL ELSE datetime('now') END, atualizado_em=datetime('now') WHERE codigo=?",
                    (d.estado, None if d.estado == "pendente" else u["email"], d.estado, codigo))
        _evento(con, "item", codigo, "revisao", u["email"], {"de": i["revisao"], "para": d.estado})
        registrar_campos_revisados(con, codigo, d.estado, u["email"])
        con.commit()
        return {"ok": True, "revisao": d.estado}
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
            raise HTTPException(404, "Folha não existe")
        try:
            pend = json.loads(i["pendencias"] or "{}")
        except ValueError:
            pend = {}
        if not isinstance(pend, dict):
            pend = {}
        sinais, bloqueios = tirar_projeto_divergente(pend)
        mudou = bool(sinais or bloqueios)
        out = {"ok": True, "mudou": mudou, "sinais_tirados": sinais, "bloqueios_tirados": bloqueios, "situacao_liberada": False, "problemas_fechados": 0}
        status = i["status_site"]
        if mudou:
            con.execute("UPDATE item SET pendencias=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
            if status == "bloqueado" and not pend["bloqueios"] and not i["autoria_divergente"]:
                con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))
                status, out["situacao_liberada"] = "nao_publicado", True
            out["problemas_fechados"] = con.execute(
                """UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'), resolucao=?
                    WHERE codigo=? AND categoria='projeto_errado' AND origem='campvision' AND situacao IN ('aberto','em_correcao')""",
                (f"É deste projeto: {u['email']} confirmou no painel (o CAMP Vision errou).", codigo)).rowcount
            _evento(con, "item", codigo, "projeto_confirmado", u["email"], {k: out[k] for k in ("sinais_tirados", "bloqueios_tirados", "situacao_liberada", "problemas_fechados")})
        con.commit()
        return {**out, "status_site": status, "bloqueios_restantes": pend.get("bloqueios") or [], "pendencias": pend}
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
    """Reter a folha: ela continua no painel (conferida), mas NUNCA vai ao site (nem pela publicação do projeto, nem do fundo, nem pelo lote). Liberar a devolve para conferir."""
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
        return {"ok": True, "retida": d.retida}
    finally:
        con.close()


@router.get("/lotes/{lote_id}/saidas-cv")
def saidas_cv(lote_id: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Tudo o que o CAMP Vision gravou em catalogacao/ deste lote (avisos, relatório, retiradas, propostas, decisões, orientação, sugestões, releituras)."""
    from .saidas_cv import ler_saidas
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo, pasta_qnap FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
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
        resp = {f"{r['tipo']}:{r['chave']}": {"acao": r["acao"], "por": r["por"], "em": r["em"], "motivo": r["motivo"], "valor": r["valor"]}
                for r in con.execute("SELECT * FROM cv_resposta WHERE lote_id=?", (lote_id,))}
    finally:
        con.close()
    return {"lote_id": lote_id, "projeto_codigo": l["projeto_codigo"], **ler_saidas(pasta, dict(p) if p else {}, resp)}


class RespostaCV(BaseModel):
    tipo: str
    chave: str
    acao: str
    valor: str | None = None
    motivo: str | None = None


_COLUNA_CV = {"titulo": "titulo", "ano": "ano", "cidade": "cidade", "cliente": "cliente", "endereco": "endereco_obra"}


@router.post("/lotes/{lote_id}/saidas-cv/resposta")
def responder_cv(lote_id: int, d: RespostaCV, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Uma pessoa responde ao CAMP Vision. sugestao: usar (grava SÓ se o campo ainda estiver vazio ou com título provisório) | ignorar.
    proposta: aceitar | recusar (só registra; nada é aplicado sozinho). retirado: devolver (admin, motivo obrigatório; entra na próxima importação)."""
    import re as _re
    validas = {"sugestao": ("usar", "ignorar"), "proposta": ("aceitar", "recusar"), "retirado": ("devolver",)}
    if d.tipo not in validas or d.acao not in validas[d.tipo]:
        raise HTTPException(400, "Resposta inválida")
    if d.tipo == "retirado":
        if u["papel"] not in ("admin", "master"):
            raise HTTPException(403, "Só um admin devolve à revisão uma folha retirada pelo CAMP Vision")
        if len((d.motivo or "").strip()) < 3:
            raise HTTPException(400, "Explique por que a folha volta para a revisão")
    con = connect()
    try:
        l = con.execute("SELECT id, projeto_codigo FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        if con.execute("SELECT 1 FROM cv_resposta WHERE lote_id=? AND tipo=? AND chave=?", (lote_id, d.tipo, d.chave)).fetchone():
            raise HTTPException(409, "Isso já foi respondido")
        valor = (d.valor or "").strip()[:300] or None
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
                con.execute(f"UPDATE projeto SET {col}=?, atualizado_em=datetime('now') WHERE codigo=?", (valor, l["projeto_codigo"]))
        con.execute("INSERT INTO cv_resposta (lote_id, projeto_codigo, tipo, chave, acao, valor, motivo, por) VALUES (?,?,?,?,?,?,?,?)",
                    (lote_id, l["projeto_codigo"], d.tipo, d.chave[:200], d.acao, valor, (d.motivo or "").strip()[:300] or None, u["email"]))
        _evento(con, "projeto", l["projeto_codigo"], f"cv_{d.tipo}_{d.acao}", u["email"], {"lote": lote_id, "chave": d.chave, "valor": valor, "motivo": d.motivo})
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
        for i in con.execute("SELECT codigo, titulo, status_site, pendencias FROM item WHERE lote_id=? AND revisao='pendente'", (lote_id,)).fetchall():
            try:
                p = json.loads(i["pendencias"] or "{}")
            except ValueError:
                p = {"bloqueios": ["pendências ilegíveis"]}
            if i["status_site"] == "bloqueado" or not (i["titulo"] or "").strip() or p.get("bloqueios") or p.get("ressalvas") or p.get("sinais"):
                continue
            con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (u["email"], i["codigo"]))
            marcadas += 1
        restam = con.execute("SELECT COUNT(*) FROM item WHERE lote_id=? AND revisao='pendente'", (lote_id,)).fetchone()[0]
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", u["email"], {"lote_id": lote_id, "conferidas": marcadas, "restam": restam})
        con.commit()
        return {"conferidas": marcadas, "restam": restam}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/lotes/{lote_id}/conferir-todas")
def conferir_todas(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca TODAS as folhas ainda pendentes do lote como conferidas (inclusive as que o CAMP Vision apontou: o botão existe para quando a pessoa já olhou).
    Devolve quantas tinham algo apontado, para a tela dizer. Não aprova o lote: isso continua sendo do admin."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        marcadas = apontadas = 0
        for i in con.execute("SELECT codigo, status_site, pendencias FROM item WHERE lote_id=? AND revisao='pendente' AND status_site NOT IN ('rascunho','no_ar')", (lote_id,)).fetchall():
            try:
                p = json.loads(i["pendencias"] or "{}")
            except ValueError:
                p = {}
            if i["status_site"] == "bloqueado" or p.get("bloqueios") or p.get("ressalvas") or p.get("sinais"):
                apontadas += 1
            con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (u["email"], i["codigo"]))
            marcadas += 1
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", u["email"], {"lote_id": lote_id, "todas": True, "conferidas": marcadas, "com_algo_apontado": apontadas})
        con.commit()
        return {"conferidas": marcadas, "com_pendencia": apontadas, "restam": 0}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class Giro(BaseModel):
    graus: int      # 90 (horário), -90 (anti-horário) ou 180


@router.post("/itens/{codigo}/girar")
def girar(codigo: str, d: Giro, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Vira a prévia da folha (e a imagem que vai ao site). A tela e o site mostram a folha já virada; o arquivo original no QNAP não é tocado.
    Folha JÁ no site (rascunho ou publicada): só admin. O painel troca o arquivo da imagem no WordPress mantendo o ID do anexo e só grava
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
        if no_site and u["papel"] not in ("admin", "master"):
            raise HTTPException(409, "Esta folha já está no site: só um admin pode girar a imagem de lá. Peça a um admin")
        novo = ((i["giro_manual"] or 0) + d.graus) % 360
        rec, ang = ajuste.depois_do_giro(*ajuste.ler(i), d.graus)       # 19/10: com recorte, a caixa gira junto
        site = None
        if no_site:                                   # primeiro o site; o painel só grava se o site aceitou
            from . import publicador
            try:
                site = publicador.girar_imagem_no_site(codigo, novo, (rec, ang))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(502, f"O site não aceitou a imagem girada, e nada foi mudado no painel: {str(e)[:240]}")
        con.execute("UPDATE item SET giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, codigo))
        _regravar_ajuste(con, i, novo, imagens.espelho_efetivo(i), rec, ang)
        if site:
            _evento(con, "item", codigo, "giro_no_site", u["email"], {"de": i["giro_manual"], "para": novo, "anexo": site["media_id"]})
        else:
            _evento(con, "item", codigo, "giro", u["email"], {"de": i["giro_manual"], "para": novo})
        con.commit()
        return {"giro_manual": novo, "no_site": bool(site)}
    finally:
        con.close()


@router.post("/itens/{codigo}/espelhar")
def espelhar(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
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
        if i["status_site"] in ("rascunho", "no_ar"):
            raise HTTPException(409, "Esta folha já está no site: a imagem lá não muda por aqui")
        antes = imagens.espelho_efetivo(i)
        novo, giro = (0 if antes else 1), (-(i["giro_manual"] or 0)) % 360
        con.execute("UPDATE item SET espelho_manual=?, giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, giro, codigo))
        _regravar_ajuste(con, i, giro, bool(novo), *ajuste.depois_do_espelho(*ajuste.ler(i)))      # 19/10: com recorte, a caixa espelha junto
        _evento(con, "item", codigo, "espelho", u["email"], {"de": int(antes), "para": novo, "giro": giro})
        con.commit()
        return {"espelhar": bool(novo), "giro_manual": giro}
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
            raise HTTPException(400, "Importe as folhas do lote antes de aprovar")
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
    """O JPG da folha (item.arquivo_jpg, relativo à raiz dos prontos) se existir e estiver DENTRO da raiz; senão None. Serve de prévia quando o CAMP Vision não gravou preview."""
    if not rel or str(rel).startswith("http"):
        return None
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
    if alvo is None:
        raise HTTPException(404, "Sem prévia")
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
def ajustar(codigo: str, d: Ajuste, u: dict = Depends(auth.exige("operador"))) -> dict:
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
        if no_site and u["papel"] not in ("admin", "master"):
            raise HTTPException(409, "Esta folha já está no site: só um admin pode mudar a imagem de lá. Peça a um admin")
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
        if no_site:                                   # a imagem do site acompanha; se o site recusar, o painel grava e fica a pendência
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
