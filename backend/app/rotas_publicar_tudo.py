"""Publicar com um clique: o plano (leitura) e a execução (admin). A lógica está em publicacao_guiada.py."""
import json
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from . import auth, publicacao_guiada
from .db import connect

router = APIRouter(prefix="/api", tags=["publicacao"])


@router.get("/projetos/{codigo}/publicar/plano")
def plano(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        return {**publicacao_guiada.plano(con, p), "pode_agir": u["papel"] in ("admin", "master")}
    finally:
        con.close()


_THREADS: dict = {}          # tarefa_id -> Thread (para saber se a tarefa ainda está viva)


def _agora() -> str:
    """UTC, como o resto do banco (a tela converte para o horário de São Paulo)."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _atualizar(tid: int, **campos) -> None:
    if not campos:
        return
    con = connect()
    try:
        con.execute(f"UPDATE tarefa_publicacao SET {', '.join(k + '=?' for k in campos)} WHERE id=?", (*campos.values(), tid))
        con.commit()
    finally:
        con.close()


def _log(tid: int, texto: str) -> None:
    con = connect()
    try:
        r = con.execute("SELECT log FROM tarefa_publicacao WHERE id=?", (tid,)).fetchone()
        linhas = json.loads(r[0] or "[]") if r else []
        linhas.append({"em": _agora(), "texto": texto})
        con.execute("UPDATE tarefa_publicacao SET log=? WHERE id=?", (json.dumps(linhas[-200:], ensure_ascii=False), tid))
        con.commit()
    finally:
        con.close()


def _rodar_tarefa(tid: int, codigo: str, u: dict) -> None:
    estado = {"total": None, "feitas": 0, "falhas": []}

    def cb(ev: dict) -> None:
        e = ev.get("evento")
        if e == "inicio" and estado["total"] is None:
            estado["total"] = ev.get("total", 0); _atualizar(tid, total=estado["total"], etapa="dossie")
        elif e == "dossie":
            _atualizar(tid, etapa="folhas"); _log(tid, "Dossiê criado no site")
        elif e == "folha":
            _atualizar(tid, etapa="folhas", folha_atual=ev.get("codigo"))
        elif e == "folha_ok":
            estado["feitas"] += 1; _atualizar(tid, feitas=estado["feitas"]); _log(tid, f"Folha {ev.get('codigo')} enviada")
        elif e == "folha_falhou":
            estado["falhas"].append({"codigo": ev.get("codigo"), "erro": ev.get("erro")}); _log(tid, f"Folha {ev.get('codigo')} NÃO subiu: {ev.get('erro')}")
        elif e == "autorizar":
            _atualizar(tid, etapa="autorizar", folha_atual=None); _log(tid, "Projeto liberado para publicação")
        elif e == "publicar":
            _atualizar(tid, etapa="publicar"); _log(tid, "Publicando…")
    try:
        while True:
            r = publicacao_guiada.executar(codigo, u, progresso=cb)
            if not r.get("parcial"):
                break
        _atualizar(tid, estado="ok" if r.get("ok") else "falhou", etapa="fim", folha_atual=None, terminada_em=_agora(), resultado=json.dumps(r, ensure_ascii=False),
                   falhas=json.dumps(r.get("falhas") or estado["falhas"], ensure_ascii=False))
    except HTTPException as e:
        _atualizar(tid, estado="falhou", etapa="fim", folha_atual=None, terminada_em=_agora(), resultado=json.dumps({"ok": False, "mensagem": str(e.detail)}, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        _atualizar(tid, estado="falhou", etapa="fim", folha_atual=None, terminada_em=_agora(), resultado=json.dumps({"ok": False, "mensagem": str(e)[:240]}, ensure_ascii=False))
    finally:
        _THREADS.pop(tid, None)


def _ler(tid: int) -> dict | None:
    con = connect()
    try:
        r = con.execute("SELECT * FROM tarefa_publicacao WHERE id=?", (tid,)).fetchone()
        if not r:
            return None
        t = dict(r)
    finally:
        con.close()
    if t["estado"] == "rodando" and not (_THREADS.get(tid) and _THREADS[tid].is_alive()):      # o servidor reiniciou no meio: não fica "rodando" para sempre
        _atualizar(tid, estado="falhou", etapa="fim", terminada_em=_agora(),
                   resultado=json.dumps({"ok": False, "mensagem": "A publicação foi interrompida (o servidor reiniciou). O que já subiu não se repete: clique em Publicar de novo."}, ensure_ascii=False))
        t.update(estado="falhou", etapa="fim", terminada_em=_agora(), resultado=json.dumps({"ok": False, "mensagem": "A publicação foi interrompida (o servidor reiniciou). O que já subiu não se repete: clique em Publicar de novo."}, ensure_ascii=False))
    for k in ("falhas", "log", "resultado"):
        try:
            t[k] = json.loads(t[k]) if t[k] else ([] if k != "resultado" else None)
        except ValueError:
            t[k] = [] if k != "resultado" else None
    ini = datetime.strptime(t["iniciada_em"], "%Y-%m-%d %H:%M:%S") if t.get("iniciada_em") else None
    fim = datetime.strptime(t["terminada_em"], "%Y-%m-%d %H:%M:%S") if t.get("terminada_em") else datetime.utcnow()
    t["decorrido_s"] = max(0, int((fim - ini).total_seconds())) if ini else None
    t["s_por_folha"] = round(t["decorrido_s"] / t["feitas"]) if t["decorrido_s"] is not None and t["feitas"] else None
    t["faltam_s"] = round(t["s_por_folha"] * (t["total"] - t["feitas"])) if t["s_por_folha"] and t["estado"] == "rodando" and t["total"] > t["feitas"] else None
    return t


def _iniciar_tarefa(codigo: str, u: dict):
    con = connect()
    try:
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        ativa = con.execute("SELECT id FROM tarefa_publicacao WHERE projeto_codigo=? AND estado='rodando' ORDER BY id DESC LIMIT 1", (codigo,)).fetchone()
        if ativa and _THREADS.get(ativa[0]) and _THREADS[ativa[0]].is_alive():
            return JSONResponse(status_code=200, content={"tarefa_id": ativa[0], "ja_rodando": True})
        pl = publicacao_guiada.plano(con, p)
        if pl["bloqueios"]:                                       # algo que só uma pessoa resolve: nem começa
            return JSONResponse(status_code=400, content={"detail": "Não dá para publicar ainda: " + " | ".join(b["detalhe"] or b["texto"] for b in pl["bloqueios"]), "plano": pl})
        cur = con.execute("INSERT INTO tarefa_publicacao (projeto_codigo, ator, estado, etapa, total) VALUES (?,?, 'rodando', 'dossie', ?)", (codigo, u["email"], pl["folhas_a_enviar"]))
        tid = cur.lastrowid
        con.commit()
    finally:
        con.close()
    th = threading.Thread(target=_rodar_tarefa, args=(tid, codigo, u), daemon=True, name=f"publicar-{codigo}")
    _THREADS[tid] = th
    th.start()
    return JSONResponse(status_code=202, content={"tarefa_id": tid})


@router.get("/tarefas/{tid}")
def tarefa(tid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    t = _ler(tid)
    if not t:
        raise HTTPException(404, "Tarefa não existe")
    return t


@router.get("/projetos/{codigo}/tarefa")
def tarefa_do_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """A tarefa de publicação mais recente deste projeto (rodando, ou terminada há pouco). None quando não há nada para acompanhar."""
    con = connect()
    try:
        r = con.execute("""SELECT id FROM tarefa_publicacao WHERE projeto_codigo=? AND (estado='rodando' OR terminada_em >= datetime('now','-10 minutes'))
                           ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    finally:
        con.close()
    return {"tarefa": _ler(r[0]) if r else None}


@router.post("/projetos/{codigo}/publicar-tudo")
def publicar_tudo(codigo: str, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    if tarefa:
        return _iniciar_tarefa(codigo, u)
    try:
        return publicacao_guiada.executar(codigo, u)
    except HTTPException as e:
        if e.status_code != 400:
            raise
        con = connect()                                  # 400 = algo que só uma pessoa resolve: devolve o plano para a tela mostrar
        try:
            p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            pl = publicacao_guiada.plano(con, p) if p else None
        finally:
            con.close()
        return JSONResponse(status_code=400, content={"detail": e.detail, "plano": pl})
