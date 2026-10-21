"""Cartão #156: despublicar um projeto e descartar um lote duplicado. Nada é apagado: tudo deixa rastro (quem, quando, por quê)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["mesclar"])


@router.post("/projetos/{codigo}/despublicar")
def despublicar(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Tira o projeto do ar: itens e página do projeto viram 'private' no Tainacan e o status vira fora_do_ar. É o 'tirar_do_ar' do Publicar, com o nome certo.
    A regra de quem pode é a mesma do Publicar: despublicar o que está PÚBLICO exige o admin master."""
    from .rotas_projetos import Publicacao, publicar
    con = connect()
    try:
        p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if not p["tainacan_item_id"] and not con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (codigo,)).fetchone():
            raise HTTPException(409, "Este projeto não tem nada no site para despublicar.")
    finally:
        con.close()
    r = publicar(codigo, Publicacao(acao="tirar_do_ar"), u)
    if r.get("ok") and not r.get("alterados"):
        raise HTTPException(409, r.get("mensagem") or "Este projeto não tem nada publicado no site para despublicar.")
    return r


class Descarte(BaseModel):
    motivo: str
    duplicata_de: int | None = None


@router.post("/filas/{lid}/descartar")
def descartar_lote(lid: int, d: Descarte, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Descarta um lote que é subpasta ou repetição de outro: some da Fila e dos contadores. NÃO apaga nada no QNAP nem no banco."""
    motivo = (d.motivo or "").strip()
    if len(motivo) < 3:
        raise HTTPException(400, "Explique o motivo (pelo menos 3 letras).")
    con = connect()
    try:
        l = con.execute("SELECT id, etapa, aprovado_em, descartado_em FROM lista_processamento WHERE id=?", (lid,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não existe")
        if l["descartado_em"]:
            raise HTTPException(409, "Este lote já foi descartado.")
        if l["aprovado_em"] or l["etapa"] == "publicado":
            raise HTTPException(409, "Este lote já foi aprovado ou publicado: não dá para descartar.")
        if con.execute("SELECT COUNT(*) FROM item WHERE lote_id=?", (lid,)).fetchone()[0]:
            raise HTTPException(409, "Este lote já tem folhas importadas. Use Mover ou Mesclar projetos em vez de descartar.")
        if d.duplicata_de is not None:
            if d.duplicata_de == lid or not con.execute("SELECT 1 FROM lista_processamento WHERE id=?", (d.duplicata_de,)).fetchone():
                raise HTTPException(400, "O lote indicado como original não existe.")
        con.execute("UPDATE lista_processamento SET descartado_em=datetime('now'), descartado_por=?, descartado_motivo=?, descartado_duplicata_de=?, atualizado_em=datetime('now') WHERE id=?",
                    (u["email"], motivo[:300], d.duplicata_de, lid))
        import json
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'lote_descartado',?,?)",
                    (str(lid), u["email"], json.dumps({"motivo": motivo[:300], "duplicata_de": d.duplicata_de}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": lid}
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------------------------------
# MOVER folhas e MESCLAR projetos. O código da folha é a chave primária ({projeto}-{ano}-{série}-D{seq}) e aparece em
# item_agente, item_localizacao, pedido_releitura, item.duplicata_de e erro.codigo: tudo é trocado numa transação só,
# com a checagem de chave estrangeira adiada até o fim. Ou move tudo, ou não move nada.
# Folha PÚBLICA no site (no_ar) não é movida: despublique antes. Folha que já tinha registro no site (rascunho/privado)
# é movida e perde o vínculo (o registro antigo fica privado no site; ao publicar o destino, ela sobe com o código novo).
# ---------------------------------------------------------------------------------------------------------------------
import json as _json
import re


class MoverItens(BaseModel):
    itens: list[str]
    destino: str
    motivo: str | None = None
    simular: bool = False          # só mostra o que aconteceria (códigos novos, duplicatas, recusas); nada é gravado


class Destino(BaseModel):
    destino: str
    motivo: str | None = None


class MoverLote(BaseModel):
    projeto_codigo: str
    motivo: str | None = None


class DuplicataDe(BaseModel):
    codigo_original: str
    tipo: str = "mesma_folha"


def _destino_valido(con, destino: str):
    d = con.execute("SELECT codigo, ano, mesclado_em, descartado_em, fundo_codigo FROM projeto WHERE codigo=?", (destino,)).fetchone()
    if not d:
        raise HTTPException(404, f"O projeto de destino {destino} não existe.")
    if d["descartado_em"]:
        raise HTTPException(409, f"O projeto {destino} foi descartado (era uma pasta de arquivos, não uma obra): escolha outro destino.")
    if d["mesclado_em"]:
        raise HTTPException(409, f"O projeto {destino} já foi mesclado em {d['mesclado_em']}: use esse como destino.")
    return d


def _mesmo_fundo(con, projeto_origem: str, d, oque: str) -> None:
    """Regra de 14/10: fundos não se misturam. Mover folha, lote ou mesclar projeto só dentro do MESMO fundo (409 se não)."""
    o = con.execute("SELECT fundo_codigo FROM projeto WHERE codigo=?", (projeto_origem,)).fetchone()
    fo, fd = (o["fundo_codigo"] if o else None), d["fundo_codigo"]
    if fo and fd and fo != fd:
        raise HTTPException(409, f"Fundos não se misturam: {oque} é do fundo {fo} e o projeto {d['codigo']} é do fundo {fd}. "
                                 f"Escolha um projeto do fundo {fo}; nada foi movido.")


def _trocar_codigo(con, antigo: str, novo: str) -> None:
    con.execute("UPDATE item_agente SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE item_localizacao SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE pedido_releitura SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (novo, antigo))
    con.execute("UPDATE item SET duplicata_conferida_de=? WHERE duplicata_conferida_de=?", (novo, antigo))   # a conferência da duplicata acompanha
    con.execute("UPDATE erro SET codigo=? WHERE codigo=?", (novo, antigo))
    con.execute("UPDATE revisao_campo SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE emprestimo_item SET item_codigo=? WHERE item_codigo=?", (novo, antigo))
    con.execute("UPDATE projeto SET capa_item=? WHERE capa_item=?", (novo, antigo))
    con.execute("UPDATE reserva SET projeto_codigo=? WHERE projeto_codigo=?", (novo, antigo))     # a reserva repetida devolve o código NOVO


def _status_velho(con, codigo: str, ator: str) -> None:
    """Folha marcada no_ar mas sem registro no site (o despublicar responde "nada no site"): corrige para nao_publicado."""
    con.execute("UPDATE item SET status_site='nao_publicado', atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'status_site_corrigido',?,?)",
                (codigo, ator, _json.dumps({"de": "no_ar", "para": "nao_publicado", "motivo": "sem registro no site"}, ensure_ascii=False)))


def _ano_da_folha(con, it) -> int:
    """Destino sem ano: mantém o ano do projeto de origem, ou o que já estava no código da folha (nunca 0000 se havia ano)."""
    o = con.execute("SELECT ano FROM projeto WHERE codigo=?", (it["projeto_codigo"],)).fetchone()
    if o and o["ano"]:
        return int(o["ano"])
    m = re.search(r"-(\d{4})-[^-]+-D\d+$", it["codigo"])
    return int(m.group(1)) if m else 0


def _mover(con, codigos: list[str], destino: str, ator: str, motivo: str | None, soltar_lote: bool = False) -> dict:
    """Move as folhas para o destino (transação já aberta por quem chama). Devolve o que foi movido, as duplicatas e o que foi ignorado.
    `soltar_lote` (CAMP-098, folha movida por uma pessoa): a folha deixa o lote do projeto de origem (lote_id fica no histórico). Antes ela
    continuava contando no lote de lá ("Faltam conferir 1 de 7") e o lote nunca podia ser aprovado. Mover o LOTE inteiro não solta."""
    d = _destino_valido(con, destino)
    ano = int(d["ano"] or 0)
    seq = con.execute("SELECT COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=?", (destino,)).fetchone()[0]
    movidos, duplicatas, ignorados = [], [], []
    linhas = []
    for c in dict.fromkeys(codigos):                                   # sem repetir, na ordem dada
        it = con.execute("SELECT * FROM item WHERE codigo=?", (c,)).fetchone()
        if not it:
            raise HTTPException(404, f"A folha {c} não existe.")
        linhas.append(it)
    linhas.sort(key=lambda r: (r["serie_codigo"], r["sequencial"]))
    for it in linhas:
        c = it["codigo"]
        if it["projeto_codigo"] == destino:
            ignorados.append({"codigo": c, "motivo": "já está no destino"}); continue
        _mesmo_fundo(con, it["projeto_codigo"], d, f"a folha {c}")
        if it["status_site"] == "no_ar":
            if it["tainacan_item_id"]:
                raise HTTPException(409, f"A folha {c} está publicada no site. Despublique esta folha (ou o projeto) antes de mover; as outras folhas podem ser movidas.")
            _status_velho(con, c, ator)                                # marcada como publicada mas sem registro no site: status velho, não trava
        igual = None
        if it["titulo"] and it["folha"]:
            igual = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND titulo=? AND folha=? AND duplicata_de IS NULL LIMIT 1",
                                (destino, it["titulo"], it["folha"])).fetchone()
        if igual:                                                      # a mesma folha já existe no destino: marca, não copia
            con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata='mesma_folha', atualizado_em=datetime('now') WHERE codigo=?", (igual[0], c))
            duplicatas.append({"codigo": c, "duplicata_de": igual[0]}); continue
        seq += 1
        novo = f"{destino}-{(ano or _ano_da_folha(con, it)):04d}-{it['serie_codigo']}-D{seq:05d}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (novo,)).fetchone():
            raise HTTPException(409, f"O código {novo} já existe; nada foi movido.")
        tinha_site = it["tainacan_item_id"]
        if tinha_site:      # CAMP-014: a folha tinha registro no site: o endereço antigo precisa redirecionar para o novo
            from . import redir_site
            redir_site.registrar(con, c, novo, "item", motivo or "folha movida", ator)
        con.execute("""UPDATE item SET codigo=?, projeto_codigo=?, sequencial=?, codigo_anterior=?,
                       tainacan_item_id=NULL, status_site=CASE WHEN tainacan_item_id IS NOT NULL THEN 'nao_publicado' ELSE status_site END,
                       atualizado_em=datetime('now') WHERE codigo=?""", (novo, destino, seq, c, c))
        lote_antigo = it["lote_id"] if soltar_lote and it["lote_id"] and con.execute(
            "SELECT 1 FROM lista_processamento WHERE id=? AND projeto_codigo<>?", (it["lote_id"], destino)).fetchone() else None
        if lote_antigo:
            con.execute("UPDATE item SET lote_id=NULL WHERE codigo=?", (novo,))
        _trocar_codigo(con, c, novo)
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_movida',?,?)",
                    (novo, ator, _json.dumps({"de": c, "para": novo, "motivo": motivo, "tainacan_item_id_antigo": tinha_site,
                                              **({"lote_id_antigo": lote_antigo} if lote_antigo else {})}, ensure_ascii=False)))
        movidos.append({"de": c, "para": novo, "tinha_registro_no_site": bool(tinha_site)})
    if movidos:                                                    # 19/10: "folha de outro projeto" fecha quando a folha é movida (com registro no histórico)
        from .problemas import fechar_resolvidos
        fechar_resolvidos(con, ator)                               # a resposta não muda: _mover também serve à rota do CAMP Vision (reidentificar)
    return {"movidos": movidos, "duplicatas": duplicatas, "ignorados": ignorados}


def _transacao(fn, simular: bool = False):
    con = connect()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys = ON")
        r = fn(con)
        con.execute("ROLLBACK" if simular else "COMMIT")
        return r
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        con.close()


def _enviar_redirecionamentos() -> None:
    """Segundo plano: envia ao site o que a fila de redirecionamentos tem. Nunca levanta."""
    try:
        from . import redir_site
        redir_site.enviar_pendentes()
    except Exception:  # noqa: BLE001
        pass


@router.get("/site/redirecionamentos")
def status_redirecionamentos(u: dict = Depends(auth.exige("operador"))) -> dict:
    """CAMP-014 · quantos redirecionamentos já estão no site, quantos faltam e quantos falharam."""
    from . import redir_site
    con = connect()
    try:
        return redir_site.status(con)
    finally:
        con.close()


@router.post("/site/redirecionamentos/enviar")
def enviar_redirecionamentos(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Envia agora ao site o que está na fila de redirecionamentos (o coletor de 10 min também repete)."""
    from . import redir_site
    return redir_site.enviar_pendentes()


@router.post("/itens/mover")
def mover_itens(d: MoverItens, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Move as folhas escolhidas para outro projeto, renumerando no destino (D continua de onde o destino parou)."""
    if not d.itens:
        raise HTTPException(400, "Escolha pelo menos uma folha.")
    r = _transacao(lambda con: _mover(con, d.itens, d.destino, u["email"], d.motivo, soltar_lote=True), simular=d.simular)
    if d.simular:
        return {**r, "simulado": True}
    tarefas.add_task(_enviar_redirecionamentos)
    return r


def _mesclar(con, origem: str, destino: str, ator: str, motivo: str | None) -> dict:
    """Mescla o projeto de origem no destino (transação já aberta por quem chama). Usada pela rota e pelo CAMP Vision (CAMP-009)."""
    o = con.execute("SELECT codigo, status_site, mesclado_em, descartado_em FROM projeto WHERE codigo=?", (origem,)).fetchone()
    if not o:
        raise HTTPException(404, f"O projeto {origem} não existe.")
    if o["descartado_em"]:
        raise HTTPException(409, f"O projeto {origem} já foi descartado.")
    if o["mesclado_em"]:
        raise HTTPException(409, f"O projeto {origem} já foi mesclado em {o['mesclado_em']}.")
    if o["status_site"] == "no_ar":
        tem_site = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (origem,)).fetchone()[0] or \
            con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (origem,)).fetchone()
        if tem_site:
            raise HTTPException(409, f"O projeto {origem} está público no site. Despublique antes de mesclar.")
    _mesmo_fundo(con, origem, _destino_valido(con, destino), f"o projeto {origem}")
    cods = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (origem,))]
    r = _mover(con, cods, destino, ator, motivo or f"mesclado em {destino}") if cods else {"movidos": [], "duplicatas": [], "ignorados": []}
    lotes = [x[0] for x in con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=?", (origem,))]
    con.execute("UPDATE lista_processamento SET projeto_codigo=?, atualizado_em=datetime('now') WHERE projeto_codigo=?", (destino, origem))
    con.execute("UPDATE pedido_releitura SET projeto_codigo=? WHERE projeto_codigo=?", (destino, origem))
    con.execute("UPDATE projeto SET mesclado_em=?, mesclado_por=?, mesclado_quando=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (destino, ator, origem))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'projeto_mesclado',?,?)",
                (origem, ator, _json.dumps({"destino": destino, "folhas": len(r["movidos"]), "duplicatas": len(r["duplicatas"]), "lotes": lotes, "motivo": motivo}, ensure_ascii=False)))
    from . import redir_site
    redir_site.registrar(con, origem, destino, "projeto", motivo or f"mesclado em {destino}", ator)     # CAMP-014: o endereço do projeto de origem passa ao destino
    return {**r, "lotes": lotes, "origem": origem, "destino": destino}


@router.post("/projetos/{origem}/mesclar-em")
def mesclar_em(origem: str, d: Destino, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Move TODAS as folhas e os lotes da origem para o destino. A origem não é apagada: fica marcada 'mesclado em' e some das listas."""
    if origem == d.destino:
        raise HTTPException(400, "Origem e destino são o mesmo projeto.")

    res = _transacao(lambda con: _mesclar(con, origem, d.destino, u["email"], d.motivo))
    tarefas.add_task(_enviar_redirecionamentos)
    return res


def _mover_lote(con, lid: int, destino: str, ator: str, motivo: str | None) -> dict:
    """Passa o lote e as folhas dele para outro projeto (transação já aberta por quem chama)."""
    l = con.execute("SELECT id, projeto_codigo, descartado_em FROM lista_processamento WHERE id=?", (lid,)).fetchone()
    if not l:
        raise HTTPException(404, "Lote não existe")
    if l["descartado_em"]:
        raise HTTPException(409, "Este lote foi descartado.")
    if l["projeto_codigo"] == destino:
        raise HTTPException(400, "O lote já está nesse projeto.")
    _mesmo_fundo(con, l["projeto_codigo"], _destino_valido(con, destino), f"o lote {lid}")
    cods = [r[0] for r in con.execute("SELECT codigo FROM item WHERE lote_id=?", (lid,))]
    r = _mover(con, cods, destino, ator, motivo or f"lote {lid} movido") if cods else {"movidos": [], "duplicatas": [], "ignorados": []}
    con.execute("UPDATE lista_processamento SET projeto_codigo=?, atualizado_em=datetime('now') WHERE id=?", (destino, lid))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'lote_movido',?,?)",
                (str(lid), ator, _json.dumps({"de": l["projeto_codigo"], "para": destino, "folhas": len(r["movidos"]), "motivo": motivo}, ensure_ascii=False)))
    return {**r, "lote": lid, "de": l["projeto_codigo"], "para": destino}


@router.post("/filas/{lid}/mover-para")
def mover_lote(lid: int, d: MoverLote, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    """O lote caiu no projeto errado: passa o lote e as folhas dele para o projeto certo."""
    res = _transacao(lambda con: _mover_lote(con, lid, d.projeto_codigo, u["email"], d.motivo))
    tarefas.add_task(_enviar_redirecionamentos)
    return res


@router.post("/itens/{codigo}/duplicata-de")
def marcar_duplicata(codigo: str, d: DuplicataDe, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca a folha como duplicata de outra (nada é apagado; só a original vai ao site)."""
    if d.tipo not in ("exata", "perceptual", "mesma_folha"):
        raise HTTPException(400, "Tipo de duplicata inválido.")
    if codigo == d.codigo_original:
        raise HTTPException(400, "Uma folha não pode ser duplicata dela mesma.")
    con = connect()
    try:
        a = con.execute("SELECT codigo, status_site FROM item WHERE codigo=?", (codigo,)).fetchone()
        o = con.execute("SELECT codigo, duplicata_de FROM item WHERE codigo=?", (d.codigo_original,)).fetchone()
        if not a or not o:
            raise HTTPException(404, "Folha não existe.")
        troca = o["duplicata_de"] == codigo                      # "qual publica": a original passa a ser a cópia e vice-versa
        if o["duplicata_de"] and not troca:
            raise HTTPException(409, f"{d.codigo_original} já é duplicata de {o['duplicata_de']}: aponte para a original.")
        if a["status_site"] == "no_ar" and con.execute("SELECT tainacan_item_id FROM item WHERE codigo=?", (codigo,)).fetchone()[0]:
            raise HTTPException(409, "Esta folha está pública no site. Despublique antes.")
        if troca:
            con.execute("UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, atualizado_em=datetime('now') WHERE codigo=?", (d.codigo_original,))
        con.execute("""UPDATE item SET duplicata_de=?, tipo_duplicata=?, duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?, duplicata_conferida_de=?,
                       atualizado_em=datetime('now') WHERE codigo=?""", (d.codigo_original, d.tipo, u["email"], d.codigo_original, codigo))   # foi uma pessoa: já conta como conferida (tela Duplicatas)
        con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (d.codigo_original, codigo))   # quem apontava para esta passa a apontar para a original
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_marcada',?,?)",
                    (codigo, u["email"], _json.dumps({"original": d.codigo_original, "tipo": d.tipo, "trocou": troca}, ensure_ascii=False)))
        from .problemas import fechar_resolvidos
        fechados = fechar_resolvidos(con, u["email"])                  # 19/10: o problema de duplicata desta folha fecha (com registro)
        con.commit()
        return {"ok": True, "trocou": troca, **({"problemas_fechados": len(fechados)} if fechados else {})}
    finally:
        con.close()


@router.delete("/itens/{codigo}/duplicata-de")
def desmarcar_duplicata(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Desfaz a marcação ("Não é duplicata"): a folha deixa de ser duplicata e volta a poder ir ao site. Fica registrado de quem ela era cópia.
    Também solta o que o CAMP Vision prendeu por causa da duplicata: o aviso de duplicata entre os bloqueios da folha, a situação
    'bloqueado' (quando a duplicata era o único bloqueio) e os problemas de duplicata em aberto desta folha."""
    con = connect()
    try:
        a = con.execute("SELECT duplicata_de, tipo_duplicata, status_site, pendencias, autoria_divergente FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not a:
            raise HTTPException(404, "Folha não existe.")
        if not a["duplicata_de"]:
            raise HTTPException(409, "Esta folha não está marcada como duplicata.")
        liberou = liberar_bloqueios_de_duplicata(con, codigo, a, u["email"])
        con.execute("""UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?, duplicata_conferida_de=?,
                       atualizado_em=datetime('now') WHERE codigo=?""", (u["email"], a["duplicata_de"], codigo))   # uma pessoa disse que não é: não volta como sugestão
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'duplicata_desmarcada',?,?)",
                    (codigo, u["email"], _json.dumps({"era_de": a["duplicata_de"], "tipo": a["tipo_duplicata"], **liberou}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "era_de": a["duplicata_de"], **liberou}
    finally:
        con.close()


def _e_de_duplicata(texto) -> bool:
    return "duplicat" in str(texto or "").lower()


def liberar_bloqueios_de_duplicata(con, codigo: str, a, ator: str) -> dict:
    """Tira o que prendia a folha só por ser duplicata. Não faz commit. Devolve o que foi solto (vai para o evento e para a tela)."""
    out = {"bloqueios_tirados": [], "situacao_liberada": False, "problemas_fechados": 0}
    try:
        pend = _json.loads(a["pendencias"] or "{}") or {}
    except ValueError:
        pend = {}
    bloq = list(pend.get("bloqueios") or []) if isinstance(pend, dict) else []
    tirar = [b for b in bloq if _e_de_duplicata(b)]
    if tirar:
        pend["bloqueios"] = [b for b in bloq if not _e_de_duplicata(b)]
        con.execute("UPDATE item SET pendencias=? WHERE codigo=?", (_json.dumps(pend, ensure_ascii=False), codigo))
        out["bloqueios_tirados"] = tirar
    if a["status_site"] == "bloqueado" and not (pend.get("bloqueios") if isinstance(pend, dict) else None) and not a["autoria_divergente"]:
        con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (codigo,))     # o CAMP Vision bloqueou por causa da duplicata
        out["situacao_liberada"] = True
    out["problemas_fechados"] = con.execute(
        """UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'),
                  resolucao=? WHERE codigo=? AND categoria='duplicata' AND situacao IN ('aberto','em_correcao')""",
        (f"Não é duplicata: desmarcada por {ator} no painel.", codigo)).rowcount
    return out


# ---------------- B7 · duplicados já cadastrados: varredura por fundo ----------------
class ParNao(BaseModel):
    a: str
    b: str


@router.get("/fundos/{codigo}/duplicados")
def duplicados_do_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Pares de projetos do mesmo fundo que parecem ser o mesmo (nome, ano, cidade, identificação original), do mais para o menos parecido.
    Os pares que alguém marcou "não são o mesmo" não voltam."""
    from .similaridade import nivel, pontuar
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Fundo não existe")
        ps = [dict(r) for r in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.identificacao_original, p.status_site,
                                                     (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                                                FROM projeto p WHERE p.fundo_codigo=? AND p.mesclado_em IS NULL ORDER BY p.codigo""", (codigo,))]
        nao = {(r[0], r[1]) for r in con.execute("SELECT a, b FROM par_nao_duplicado")}
        pares = []
        for i, x in enumerate(ps):
            for y in ps[i + 1:]:
                if (x["codigo"], y["codigo"]) in nao:
                    continue
                score, motivos = pontuar(x, y)
                n = nivel(score)
                if n:
                    pares.append({"a": x, "b": y, "score": score, "nivel": n, "motivos": motivos})
        pares.sort(key=lambda p: (-p["score"], p["a"]["codigo"]))
        return {"fundo": codigo, "projetos": len(ps), "total": len(pares), "pares": pares[:200]}
    finally:
        con.close()


@router.post("/fundos/{codigo}/duplicados/nao-sao")
def marcar_nao_duplicado(codigo: str, d: ParNao, u: dict = Depends(auth.exige("operador"))) -> dict:
    a, b = sorted([d.a.strip().upper(), d.b.strip().upper()])
    if a == b or not (a.startswith(codigo + "-") and b.startswith(codigo + "-")):
        raise HTTPException(400, "Informe dois projetos diferentes deste fundo")
    con = connect()
    try:
        con.execute("INSERT OR IGNORE INTO par_nao_duplicado (a, b, por) VALUES (?,?,?)", (a, b, u["email"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'nao_duplicado',?,?)",
                    (a, u["email"], _json.dumps({"outro": b}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------------
# Sobras #9 · RECODIFICAR um projeto (ex.: o número P errado): F014-P0004 → F014-P0009, no MESMO fundo.
# Mesma regra do mover: uma transação só, com a checagem de chave estrangeira adiada até o fim (ou troca tudo, ou nada).
# Cada folha ganha o código novo ({novo}-{ano}-{série}-D{seq}, mesmo ano/série/sequencial) e guarda o antigo em codigo_anterior;
# o projeto e cada folha entram na tabela redirecionamento (codigo_antigo → codigo_novo, já prevista no schema), que o site lê em GET /api/redirecionamentos para o 301.
# O número antigo continua reservado (numero_p): nunca é reusado. A pasta no QNAP não é renomeada.
# ---------------------------------------------------------------------------------------------------------------------
_COD_PROJETO = re.compile(r"^F\d{3}-P\d{4}$")


class Recodificar(BaseModel):
    novo: str
    motivo: str | None = None


def _prefixo(con, tabela: str, coluna: str, antigo: str, novo: str, onde: str = "") -> int:
    """Troca o prefixo `antigo` por `novo` na coluna (o próprio código do projeto e os das folhas, que começam por 'antigo-')."""
    n = len(antigo)
    return con.execute(f"UPDATE {tabela} SET {coluna} = ? || substr({coluna}, ?) WHERE ({coluna} = ? OR substr({coluna}, 1, ?) = ?){onde}",
                       (novo, n + 1, antigo, n + 1, antigo + "-")).rowcount


def _recodificar(con, antigo: str, novo: str, ator: str, motivo: str | None) -> dict:
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (antigo,)).fetchone()
    if not p:
        raise HTTPException(404, f"O projeto {antigo} não existe.")
    if p["mesclado_em"]:
        raise HTTPException(409, f"O projeto {antigo} já foi mesclado em {p['mesclado_em']}: mude o código de lá, se precisar.")
    if not novo.startswith(p["fundo_codigo"] + "-"):
        raise HTTPException(400, f"O código novo tem que ser do mesmo fundo ({p['fundo_codigo']}-P….). Fundos não se misturam.")
    if con.execute("SELECT 1 FROM projeto WHERE codigo=?", (novo,)).fetchone():
        raise HTTPException(409, f"O código {novo} já é de outro projeto. Escolha um número livre (ou use Mesclar, se for o mesmo projeto).")
    numero = int(novo[-4:])
    if numero < 1:
        raise HTTPException(400, "O número P tem que ser 0001 ou maior.")
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,NULL)", (p["fundo_codigo"], numero))
    con.execute("UPDATE projeto SET codigo=?, numero=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, numero, antigo))
    folhas = []
    for it in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY serie_codigo, sequencial", (antigo,)).fetchall():
        c = it["codigo"]
        nc = novo + c[len(antigo):] if c.startswith(antigo + "-") else f"{novo}-{c.split('-', 2)[-1]}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (nc,)).fetchone():
            raise HTTPException(409, f"O código {nc} já existe; nada foi mudado.")
        con.execute("UPDATE item SET codigo=?, projeto_codigo=?, codigo_anterior=?, atualizado_em=datetime('now') WHERE codigo=?", (nc, novo, c, c))
        _trocar_codigo(con, c, nc)                                     # item_agente, localização, releitura, duplicata_de, erro, revisão
        folhas.append({"de": c, "para": nc})
    # endereço público que o espelho do site conhecia ANTES de o código mudar (depois o wp_item passa a ter só o código novo)
    from . import redir_site
    urls_antigas = {antigo: redir_site._url_conhecida(con, "projeto", antigo)}
    urls_antigas.update({f["de"]: redir_site._url_conhecida(con, "item", f["de"]) for f in folhas})
    # o que aponta para o PROJETO (e, por prefixo, para as folhas) fora das chaves estrangeiras
    for tabela, coluna in (("lista_processamento", "projeto_codigo"), ("pedido_releitura", "projeto_codigo"), ("decisao", "projeto_codigo"),
                           ("cv_resposta", "projeto_codigo"), ("tarefa_publicacao", "projeto_codigo"), ("tarefa_publicacao", "folha_atual"),
                           ("uso_download", "projeto_codigo"), ("uso_download", "material_codigo"), ("estacao_heartbeat", "projeto_codigo"),
                           ("solicitacao_item", "codigo"), ("etiqueta_impressao", "codigo"), ("divergencia_site", "codigo"), ("erro", "codigo"),
                           ("projeto", "capa_item"), ("projeto", "mesclado_em"), ("reserva", "projeto_codigo")):
        _prefixo(con, tabela, coluna, antigo, novo)
    _prefixo(con, "cv_resposta", "chave", antigo, novo, " AND tipo='retirado'")
    _prefixo(con, "wp_item", "codigo_detectado", antigo, novo)        # espelho do site: sem isso o redirecionamento das folhas fica 'sem_url'
    _prefixo(con, "wp_item", "projeto_detectado", antigo, novo)
    _prefixo(con, "evento", "codigo", antigo, novo, " AND entidade IN ('projeto','item')")   # o histórico acompanha o projeto
    for r in con.execute("SELECT a, b, por, em FROM par_nao_duplicado WHERE a=? OR b=?", (antigo, antigo)).fetchall():
        a, b = sorted([novo if r["a"] == antigo else r["a"], novo if r["b"] == antigo else r["b"]])
        con.execute("DELETE FROM par_nao_duplicado WHERE a=? AND b=?", (r["a"], r["b"]))
        con.execute("INSERT OR IGNORE INTO par_nao_duplicado (a, b, por, em) VALUES (?,?,?,?)", (a, b, r["por"], r["em"]))
    # mapa antigo → novo: quem já apontava para o antigo passa a apontar para o novo (sem cadeia), e entra o que mudou agora
    _prefixo(con, "redirecionamento", "codigo_novo", antigo, novo)
    con.execute("UPDATE redirecionamento SET aplicado_no_site=0, sem_site=0 WHERE codigo_novo = ? OR substr(codigo_novo, 1, ?) = ?", (novo, len(novo) + 1, novo + "-"))
    con.execute("DELETE FROM redirecionamento WHERE codigo_antigo = codigo_novo")
    mot = (motivo or "").strip()[:300] or "código do projeto corrigido"
    for de, para, tipo in [(antigo, novo, "projeto")] + [(f["de"], f["para"], "item") for f in folhas]:
        con.execute("""INSERT INTO redirecionamento (codigo_antigo, codigo_novo, entidade, motivo, criado_por) VALUES (?,?,?,?,?)
                       ON CONFLICT(codigo_antigo) DO UPDATE SET codigo_novo=excluded.codigo_novo, entidade=excluded.entidade, motivo=excluded.motivo,
                                                                criado_por=excluded.criado_por, criado_em=datetime('now'), aplicado_no_site=0, sem_site=0""", (de, para, tipo, mot, ator))
    for cod_antigo, url in urls_antigas.items():
        if url:
            con.execute("UPDATE redirecionamento SET url_antiga=? WHERE codigo_antigo=?", (url, cod_antigo))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'projeto_recodificado',?,?)",
                (novo, ator, _json.dumps({"de": antigo, "para": novo, "folhas": len(folhas), "motivo": mot}, ensure_ascii=False)))
    no_site = bool(p["tainacan_item_id"] or p["wp_page_id"]) or bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (novo,)).fetchone())
    avisos = []
    if no_site:
        avisos.append("O projeto já tem registro no site: publique de novo para o site mostrar o código novo. Os endereços antigos redirecionam quando o site ler o mapa de redirecionamentos.")
    if p["pasta_qnap"]:
        avisos.append("A pasta no QNAP continua com o nome antigo; renomeie lá se quiser.")
    return {"ok": True, "de": antigo, "para": novo, "folhas": folhas, "no_site": no_site, "avisos": avisos}


def _enviar_codigos_ao_site(folhas: list[dict], ator: str) -> dict:
    """Folhas recodificadas que já estão no site: manda o "Código do documento" novo (melhor esforço; falha vira pendência
    'pendente_codigo_no_site', nunca desfaz o local). Mesmo caminho do serie_s08."""
    from . import publicador
    out = {"atualizadas": 0, "falhas": []}
    con = connect()
    try:
        alvo = []
        for f in folhas:
            row = con.execute("SELECT tainacan_item_id FROM item WHERE codigo=?", (f["para"],)).fetchone()
            if row and row[0]:
                alvo.append((f["para"], row[0]))
        if not alvo:
            return out
        try:
            wp = publicador.WP()
        except Exception as e:  # noqa: BLE001
            for novo_, _ in alvo:
                publicador._pendencia(con, "item", novo_, "pendente_codigo_no_site", f"código novo não enviado ao site: {e}")
                out["falhas"].append(novo_)
            con.commit()
            return out
        mid, _ = publicador._meta(con, publicador.COL_ACERVO, "Código do documento")
        for novo_, iid in alvo:
            try:
                if mid:
                    wp.definir_metadado(int(iid), mid, novo_)
                out["atualizadas"] += 1
            except Exception as e:  # noqa: BLE001
                publicador._pendencia(con, "item", novo_, "pendente_codigo_no_site", str(e)[:200])
                out["falhas"].append(novo_)
        con.commit()
    finally:
        con.close()
    return out


@router.post("/projetos/{codigo}/recodificar")
def recodificar(codigo: str, d: Recodificar, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Muda o código do projeto e de todas as folhas dele. Só admin. O antigo fica guardado e vira redirecionamento."""
    antigo, novo = codigo.strip().upper(), (d.novo or "").strip().upper()
    if not _COD_PROJETO.match(novo):
        raise HTTPException(400, "Use o código completo do projeto, ex.: F014-P0009.")
    if novo == antigo:
        raise HTTPException(400, "O código novo é igual ao atual.")
    r = _transacao(lambda con: _recodificar(con, antigo, novo, u["email"], d.motivo))
    tarefas.add_task(_enviar_codigos_ao_site, r["folhas"], u["email"])   # o metadado "Código do documento" no site (falha vira pendência)
    tarefas.add_task(_enviar_redirecionamentos)          # CAMP-014: manda o mapa ao site (falha não desfaz o local; o coletor repete)
    return r


@router.get("/redirecionamentos")
def redirecionamentos(tipo: str | None = None, desde: str | None = None) -> dict:
    """PÚBLICA (sem login), para o site responder 301: só códigos antigo → novo, nada além. Ver docs/pedidos-do-site.md."""
    sql, p = "SELECT codigo_antigo AS antigo, codigo_novo AS novo, entidade AS tipo, criado_em FROM redirecionamento WHERE 1=1", []
    if tipo in ("fundo", "projeto", "item"):
        sql += " AND entidade=?"; p.append(tipo)
    if desde and re.match(r"^\d{4}-\d{2}-\d{2}", desde):
        sql += " AND criado_em >= ?"; p.append(desde[:19].replace("T", " "))
    con = connect()
    try:
        itens = [dict(r) for r in con.execute(sql + " ORDER BY criado_em, rowid", p)]
    finally:
        con.close()
    return {"total": len(itens), "itens": itens}


# ---------------------------------------------------------------------------------------------------------------------
# Projetos com NOME DE PASTA DO SISTEMA ("01 - Arquivo Arquivístico (TIFF)", "JPG"…): o CAMP Vision criou o projeto a partir de
# uma subpasta (F009-P0114, F022-P0009, F026-P0237). A reserva da estação já recusa esses nomes (422); aqui o admin limpa os
# que já existem: junta ao projeto certo (mesclar-em, SÓ dentro do mesmo fundo) ou, sem folhas, descarta (nada é apagado).
# ---------------------------------------------------------------------------------------------------------------------
_P_NA_PASTA = re.compile(r"(?<![A-Za-z0-9])P\s*0*(\d{1,4})(?!\d)", re.I)


def _pasta_do_projeto(pasta: str | None) -> str | None:
    """Sobe a partir da pasta do lote enquanto o nome for de subpasta do sistema: o que sobra é a pasta da obra."""
    from .similaridade import nome_de_subpasta
    partes = (pasta or "").replace("\\", "/").rstrip("/").split("/")
    subiu = False
    while partes and nome_de_subpasta(partes[-1]):
        partes.pop()
        subiu = True
    return "/".join(partes) if subiu and partes and partes[-1] else None


def _sugerir_destino(con, p, pastas: list[str]) -> dict | None:
    """O projeto real do MESMO fundo cuja pasta contém a subpasta. Fundos não se misturam (decisão de 14/10)."""
    from .similaridade import NIVEL_FORTE, nome_de_subpasta, normalizar, pontuar
    fundo, codigo = p["fundo_codigo"], p["codigo"]

    def vivo(cod: str | None, saltos: int = 0):
        if not cod or cod == codigo or saltos > 5:
            return None
        r = con.execute("""SELECT codigo, titulo, ano, cidade, mesclado_em FROM projeto
                            WHERE codigo=? AND fundo_codigo=? AND descartado_em IS NULL""", (cod, fundo)).fetchone()
        if r and r["mesclado_em"]:                       # o projeto da pasta já foi juntado a outro: segue para o destino final
            return vivo(r["mesclado_em"], saltos + 1)
        return r if r and not nome_de_subpasta(r["titulo"]) else None

    for pasta in pastas:
        pai = _pasta_do_projeto(pasta)
        if not pai:
            continue
        nome_pai = pai.split("/")[-1]
        # 1) outro projeto do fundo cuja pasta (do projeto ou de um lote dele) é exatamente a pasta-mãe
        for (cod,) in con.execute("""SELECT codigo FROM projeto WHERE fundo_codigo=? AND rtrim(pasta_qnap,'/')=?
                                      UNION SELECT l.projeto_codigo FROM lista_processamento l JOIN projeto x ON x.codigo=l.projeto_codigo
                                       WHERE x.fundo_codigo=? AND rtrim(l.pasta_qnap,'/')=?""", (fundo, pai, fundo, pai)).fetchall():
            r = vivo(cod)
            if r:
                return {"codigo": r["codigo"], "titulo": r["titulo"], "pasta": pai, "como": "achado pela pasta do projeto, que é a pasta-mãe"}
        # 2) o número P no nome da pasta-mãe ("P0060 - SESI — Marília - 1984")
        m = _P_NA_PASTA.search(nome_pai)
        if m:
            r = vivo(f"{fundo}-P{int(m.group(1)):04d}")
            if r:
                return {"codigo": r["codigo"], "titulo": r["titulo"], "pasta": pai, "como": f"achado pelo número P{int(m.group(1)):04d} no nome da pasta-mãe"}
        # 3) pelo nome: a pasta-mãe sem o "P0060 - " do começo e sem o " - 1984" do fim
        nome = re.sub(r"^\s*P\s*\d{1,4}\s*[-–—._]\s*", "", nome_pai, flags=re.I)
        ano_m = re.search(r"((?:18|19|20)\d{2})\)?\s*$", nome)
        nome = re.sub(r"\s*[-–—_(]?\s*(?:18|19|20)\d{2}\)?\s*$", "", nome).strip(" -–—_")
        alvo, melhor = normalizar(nome), None
        if not alvo:
            continue
        for r in con.execute("""SELECT codigo, titulo, ano, cidade FROM projeto
                                 WHERE fundo_codigo=? AND codigo<>? AND mesclado_em IS NULL AND descartado_em IS NULL""", (fundo, codigo)).fetchall():
            if nome_de_subpasta(r["titulo"]):
                continue
            if normalizar(r["titulo"]) == alvo:
                melhor = (2.0, r)
                break
            nota, _ = pontuar({"titulo": nome, "ano": int(ano_m.group(1)) if ano_m else 0, "cidade": None},
                              {"titulo": r["titulo"], "ano": r["ano"], "cidade": r["cidade"]})
            if nota >= NIVEL_FORTE and (not melhor or nota > melhor[0]):
                melhor = (nota, r)
        if melhor:
            r = melhor[1]
            return {"codigo": r["codigo"], "titulo": r["titulo"], "pasta": pai, "como": "achado pelo nome da pasta-mãe"}
    return None


def _projetos_nome_de_pasta(con) -> list[dict]:
    from .rotas_decisoes import _resumo_projetos
    from .similaridade import nome_de_subpasta
    out = []
    for p in con.execute("""SELECT p.codigo, p.titulo, p.fundo_codigo, f.titulo AS fundo_titulo, p.pasta_qnap, p.status_site, p.tainacan_item_id, p.wp_page_id,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo AND i.tainacan_item_id IS NOT NULL) AS folhas_no_site
                              FROM projeto p LEFT JOIN fundo f ON f.codigo=p.fundo_codigo
                             WHERE p.mesclado_em IS NULL AND p.descartado_em IS NULL ORDER BY p.fundo_codigo, p.codigo""").fetchall():
        if not nome_de_subpasta(p["titulo"]):
            continue
        lotes = [dict(l) for l in con.execute("""SELECT id, nome, pasta_qnap, etapa, descartado_em FROM lista_processamento
                                                  WHERE projeto_codigo=? ORDER BY id""", (p["codigo"],))]
        pastas = [l["pasta_qnap"] for l in lotes if l["pasta_qnap"]] + ([p["pasta_qnap"]] if p["pasta_qnap"] else [])
        tem_site = bool(p["tainacan_item_id"] or p["wp_page_id"] or p["folhas_no_site"])
        capa = (_resumo_projetos(con, {p["codigo"]}).get(p["codigo"]) or {}).get("capa") if p["folhas"] else None
        out.append({"codigo": p["codigo"], "titulo": p["titulo"], "fundo_codigo": p["fundo_codigo"], "fundo_titulo": p["fundo_titulo"],
                    "folhas": p["folhas"], "lotes": lotes, "tem_no_site": tem_site, "status_site": p["status_site"],
                    "pasta_qnap": pastas[0] if pastas else None, "capa": capa,
                    "sugestao": _sugerir_destino(con, p, pastas),
                    "pode_descartar": not p["folhas"] and not tem_site})
    return out


@router.get("/projetos/nome-de-pasta")
def projetos_nome_de_pasta(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Projetos cujo título é nome de subpasta do sistema, com a sugestão do projeto certo (mesmo fundo)."""
    con = connect()
    try:
        itens = _projetos_nome_de_pasta(con)
        return {"total": len(itens), "itens": itens}
    finally:
        con.close()


class DescarteProjeto(BaseModel):
    motivo: str | None = None


@router.post("/projetos/{codigo}/descartar")
def descartar_projeto(codigo: str, d: DescarteProjeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Descarta um projeto que não é nada (pasta do sistema, teste, cadastro errado): some das listas. Não apaga nada; o número P nunca é reusado.
    19/10: vale para qualquer projeto sem registro no site (antes, só nome de pasta do sistema e sem folhas). As folhas dele, se houver
    (nenhuma pode estar no site), ficam retidas: nunca vão ao site."""
    from .similaridade import nome_de_subpasta
    motivo = (d.motivo or "").strip()[:300]

    def fazer(con):
        p = con.execute("SELECT codigo, titulo, mesclado_em, descartado_em, tainacan_item_id, wp_page_id FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if p["descartado_em"]:
            raise HTTPException(409, "Este projeto já foi descartado.")
        if p["mesclado_em"]:
            raise HTTPException(409, f"Este projeto já foi juntado a {p['mesclado_em']}.")
        mot = motivo or ("nome de pasta do sistema, não é uma obra" if nome_de_subpasta(p["titulo"]) else "")
        if len(mot) < 3:
            raise HTTPException(400, "Explique por que este projeto é descartado.")
        if p["tainacan_item_id"] or p["wp_page_id"]:
            raise HTTPException(409, "Este projeto tem registro no site: despublique e junte ao projeto certo em vez de descartar.")
        no_site = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND (tainacan_item_id IS NOT NULL OR status_site IN ('no_ar','rascunho'))", (codigo,)).fetchone()[0]
        if no_site:
            raise HTTPException(409, f"{no_site} folha(s) deste projeto estão no site: despublique-as antes de descartar.")
        folhas = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (codigo,))]
        if folhas:
            con.execute("UPDATE item SET retida=1, retida_motivo=?, atualizado_em=datetime('now') WHERE projeto_codigo=?", (f"projeto descartado: {mot}"[:300], codigo))
        lotes = [r[0] for r in con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL", (codigo,))]
        con.execute("""UPDATE lista_processamento SET descartado_em=datetime('now'), descartado_por=?, descartado_motivo=?, atualizado_em=datetime('now')
                        WHERE projeto_codigo=? AND descartado_em IS NULL""", (u["email"], f"projeto {codigo} descartado: {mot}"[:300], codigo))
        con.execute("UPDATE projeto SET descartado_em=datetime('now'), descartado_por=?, descartado_motivo=?, atualizado_em=datetime('now') WHERE codigo=?",
                    (u["email"], mot, codigo))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'projeto_descartado',?,?)",
                    (codigo, u["email"], _json.dumps({"titulo": p["titulo"], "motivo": mot, "lotes": lotes, "folhas": folhas}, ensure_ascii=False)))
        return {"ok": True, "codigo": codigo, "lotes": lotes, "folhas": len(folhas)}

    return _transacao(fazer)
