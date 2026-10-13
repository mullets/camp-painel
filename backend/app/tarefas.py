"""H4 · Ação longa vira TAREFA em segundo plano, o mesmo mecanismo da publicação (P0-10).

A rota recebe ?tarefa=1, chama iniciar() e devolve 202 {tarefa_id} na hora; a função roda numa thread e conta o andamento
pelo objeto Progresso. A tela acompanha por GET /api/tarefas/{id}, o chip do topo lista o que está rodando (GET /api/tarefas)
e fechar a aba não para nada. Uma tarefa do mesmo tipo e alvo que já está rodando não começa de novo: devolve a que existe.
"""
import json
import threading
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .db import connect
from .rotas_publicar_tudo import _THREADS, _agora, _atualizar, _log

TITULOS = {
    "publicar": "Publicar no site",
    "enviar_folhas": "Enviar folhas ao site",
    "varrer_qnap": "Ler as pastas do QNAP",
    "backup": "Backup agora",
    "sincronizar": "Sincronizar com o site",
    "puxar_uso": "Buscar pedidos no site",
    "importar_todas": "Importar os lotes da Fila",
    "bagit": "Gerar pacote BagIt",
}


class Progresso:
    """O que a função da tarefa usa para contar o andamento. Grava no banco no máximo a cada 0,5 s (o fim grava sempre)."""

    def __init__(self, tid: int):
        self.tid, self.feitas, self._t = tid, 0, 0.0

    def total(self, n: int) -> None:
        _atualizar(self.tid, total=int(n))

    def passo(self, texto: str, atual: str | None = None) -> None:
        _atualizar(self.tid, etapa=texto[:120], folha_atual=atual)

    def feita(self, n: int = 1, texto: str | None = None) -> None:
        self.feitas += n
        if texto:
            _log(self.tid, texto)
        if time.monotonic() - self._t >= 0.5:
            self._t = time.monotonic()
            _atualizar(self.tid, feitas=self.feitas)

    def log(self, texto: str) -> None:
        _log(self.tid, texto)


def _rodar(tid: int, fn) -> None:
    p = Progresso(tid)
    try:
        r = fn(p) or {}
        ok = r.get("ok", True) is not False and not r.get("erro")
        if not ok and not r.get("mensagem"):
            r["mensagem"] = str(r.get("erro") or "Não terminou.")
        _atualizar(tid, estado="ok" if ok else "falhou", etapa="fim", folha_atual=None, feitas=p.feitas, terminada_em=_agora(),
                   resultado=json.dumps(r, ensure_ascii=False, default=str), falhas=json.dumps(r.get("falhas") or [], ensure_ascii=False))
    except HTTPException as e:
        _atualizar(tid, estado="falhou", etapa="fim", folha_atual=None, feitas=p.feitas, terminada_em=_agora(),
                   resultado=json.dumps({"ok": False, "mensagem": str(e.detail)}, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        _atualizar(tid, estado="falhou", etapa="fim", folha_atual=None, feitas=p.feitas, terminada_em=_agora(),
                   resultado=json.dumps({"ok": False, "mensagem": str(e)[:240]}, ensure_ascii=False))
    finally:
        _THREADS.pop(tid, None)


def iniciar(tipo: str, alvo: str, u: dict, fn, titulo: str | None = None) -> JSONResponse:
    """Começa a tarefa (ou devolve a que já está rodando para o mesmo tipo e alvo). fn(progresso) -> {ok, mensagem, ...}."""
    con = connect()
    try:
        ativa = con.execute("SELECT id FROM tarefa_publicacao WHERE tipo=? AND projeto_codigo=? AND estado='rodando' ORDER BY id DESC LIMIT 1",
                            (tipo, alvo)).fetchone()
        if ativa and _THREADS.get(ativa[0]) and _THREADS[ativa[0]].is_alive():
            return JSONResponse(status_code=200, content={"tarefa_id": ativa[0], "ja_rodando": True})
        tid = con.execute("INSERT INTO tarefa_publicacao (projeto_codigo, ator, estado, etapa, tipo, titulo) VALUES (?,?, 'rodando', 'Começando…', ?, ?)",
                          (alvo, u["email"], tipo, titulo or TITULOS.get(tipo, tipo))).lastrowid
        con.commit()
    finally:
        con.close()
    th = threading.Thread(target=_rodar, args=(tid, fn), daemon=True, name=f"tarefa-{tipo}-{tid}")
    _THREADS[tid] = th
    th.start()
    return JSONResponse(status_code=202, content={"tarefa_id": tid})
