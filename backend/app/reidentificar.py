"""CAMP-009 · O CAMP Vision corrige o que entrou no projeto errado (`vigia.py --reidentificar`) usando as MESMAS regras de mesclar/mover do painel.

As rotas de mesclar/mover (rotas_mesclar.py) exigem login de admin; o CV2 não tem login, tem o token da estação. Esta rota é a porta do CV2:

    POST /api/campvision/reidentificar          (rede local ou X-Camp-Token, igual /aviso)
    {"simular": true,                          # PADRÃO: só devolve o plano; nada é gravado
     "motivo": "reidentificar F026",
     "movimentos": [{"itens": ["F026-P0236-1972-S01-D00001", ...], "destino": "F026-P0002"},
                    {"lote_id": 41, "destino": "F026-P0002"}],        # lote inteiro (folhas + lote)
     "mesclar":    [{"origem": "F026-P0236", "destino": "F026-P0002"}]}

- Simular roda a operação inteira numa transação e DESFAZ no fim: o plano devolvido é exatamente o que aconteceria.
- Aplicar (`simular: false`) só é aceito com a configuração `campvision.reidentificar_aplicar` = 1 (nasce 0). Sem ela: 403 com `mensagem`.
- Tudo ou nada: se um movimento falhar ao aplicar, nada é gravado (409 com o plano e o erro de cada movimento).
- Idempotente: folha já movida (o código antigo está em `codigo_anterior` do destino) volta como `ja_movido`, sem erro e sem duplicar.
- Folha pública no site continua recusada (409): despublique antes. Redirecionamentos antigo → novo entram na fila do site (CAMP-014) só quando aplica.
- `mapa` = {código antigo: código novo} de tudo o que mudou, para o CV2 renomear/mover os arquivos no QNAP e refazer os pacotes.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from .db import connect
from .rede import exigir_estacao

router = APIRouter(prefix="/api", tags=["campvision-reidentificar"])

ATOR = "CAMP Vision (reidentificar)"
CFG_APLICAR = "campvision.reidentificar_aplicar"


def aplicar_liberado(con) -> bool:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (CFG_APLICAR,)).fetchone()
    return bool(r) and str(r[0] or "").strip().lower() in ("1", "sim", "true", "aplicar")


def _lista(v) -> list[str]:
    return [str(x).strip() for x in (v or []) if str(x).strip()] if isinstance(v, list) else []


def _separar_ja_movidos(con, codigos: list[str], destino: str) -> tuple[list[str], list[dict]]:
    """Folha que não existe mais com esse código mas foi movida para o destino (codigo_anterior) = já feito: idempotência."""
    a_mover, ja = [], []
    for c in dict.fromkeys(codigos):
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (c,)).fetchone():
            a_mover.append(c)
            continue
        n = con.execute("SELECT codigo FROM item WHERE codigo_anterior=? AND projeto_codigo=? ORDER BY atualizado_em DESC LIMIT 1", (c, destino)).fetchone()
        if n:
            ja.append({"de": c, "para": n[0]})
        else:
            a_mover.append(c)                      # não existe em lugar nenhum: o _mover responde 404 com o nome da folha
    return a_mover, ja


def executar(con, corpo: dict, ator: str = ATOR) -> dict:
    """Roda os movimentos na transação já aberta. Devolve {operacoes, mapa, erros}; não faz commit nem rollback."""
    from . import rotas_mesclar as rm
    motivo = (str(corpo.get("motivo") or "").strip() or "reidentificar (CAMP Vision)")[:300]
    ops, mapa, erros = [], {}, 0

    def rodar(tipo: str, ref: dict, fn):
        nonlocal erros
        con.execute("SAVEPOINT op")
        try:
            r = fn()
            con.execute("RELEASE op")
            for m in r.get("movidos", []) + r.get("ja_movidos", []):
                mapa[m["de"]] = m["para"]
            ops.append({"tipo": tipo, **ref, "ok": True, **r})
        except HTTPException as e:
            con.execute("ROLLBACK TO op"); con.execute("RELEASE op")
            erros += 1
            ops.append({"tipo": tipo, **ref, "ok": False, "status": e.status_code, "erro": str(e.detail)})

    for m in corpo.get("movimentos") or []:
        destino = str(m.get("destino") or "").strip()
        if m.get("lote_id") is not None:
            try:
                lid = int(m["lote_id"])
            except (TypeError, ValueError):
                lid = -1
            rodar("mover_lote", {"lote_id": lid, "destino": destino}, lambda lid=lid, destino=destino: rm._mover_lote(con, lid, destino, ator, motivo))
            continue
        itens = _lista(m.get("itens"))
        if not itens or not destino:
            erros += 1
            ops.append({"tipo": "mover_itens", "destino": destino, "ok": False, "status": 400, "erro": "Informe `itens` e `destino` (ou `lote_id` e `destino`)."})
            continue

        def mover(itens=itens, destino=destino):
            a_mover, ja = _separar_ja_movidos(con, itens, destino)
            r = rm._mover(con, a_mover, destino, ator, motivo) if a_mover else {"movidos": [], "duplicatas": [], "ignorados": []}
            return {**r, "ja_movidos": ja}
        rodar("mover_itens", {"destino": destino, "itens": len(itens)}, mover)

    for m in corpo.get("mesclar") or []:
        origem, destino = str(m.get("origem") or "").strip(), str(m.get("destino") or "").strip()
        if not origem or not destino or origem == destino:
            erros += 1
            ops.append({"tipo": "mesclar", "origem": origem, "destino": destino, "ok": False, "status": 400, "erro": "Informe `origem` e `destino` diferentes."})
            continue

        def mesclar(origem=origem, destino=destino):
            o = con.execute("SELECT mesclado_em FROM projeto WHERE codigo=?", (origem,)).fetchone()
            if o and o["mesclado_em"] == destino:        # já mesclado nesse destino: idempotente
                return {"movidos": [], "duplicatas": [], "ignorados": [], "ja_movidos": [], "ja_mesclado": True, "origem": origem, "destino": destino}
            return {**rm._mesclar(con, origem, destino, ator, motivo), "ja_movidos": []}
        rodar("mesclar", {"origem": origem, "destino": destino}, mesclar)
    return {"operacoes": ops, "mapa": mapa, "erros": erros}


@router.post("/campvision/reidentificar")
async def reidentificar(request: Request, tarefas: BackgroundTasks):
    exigir_estacao(request)
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001
        corpo = None
    if not isinstance(corpo, dict) or not (corpo.get("movimentos") or corpo.get("mesclar")):
        raise HTTPException(400, "Corpo esperado: {simular, motivo, movimentos:[...], mesclar:[...]}.")
    simular = corpo.get("simular", True) is not False          # só `false` de verdade aplica
    con = connect()
    try:
        if not simular and not aplicar_liberado(con):
            return JSONResponse(status_code=403, content={"ok": False, "aplicado": False, "mensagem":
                f"Aplicar está desligado no painel ({CFG_APLICAR} = 0). Rode com simular: true, revise o plano e peça ao admin para ligar a configuração."})
        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys = ON")
        try:
            r = executar(con, corpo)
            if simular or r["erros"]:
                con.execute("ROLLBACK")
            else:
                con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
            raise
    finally:
        con.close()
    aplicado = (not simular) and not r["erros"]
    if aplicado:
        from .rotas_mesclar import _enviar_redirecionamentos
        tarefas.add_task(_enviar_redirecionamentos)
    saida = {"ok": r["erros"] == 0, "simulado": simular, "aplicado": aplicado, **r}
    if not simular and r["erros"]:
        saida["mensagem"] = "Nada foi gravado: um ou mais movimentos falharam (veja `operacoes`)."
        return JSONResponse(status_code=409, content=saida)
    return saida
