"""CAMP-008 · Reconciliação noturna entre o QNAP (material final do CAMP Vision) e o painel.

O aviso do CV2 (POST /api/campvision/aviso) cobre uma pasta de cada vez; se algum se perder (painel parado, rede), a varredura da raiz final recoloca
na Fila o que faltar e lê o erros.json de cada lote (`_ler_pasta` faz as duas coisas). Uma vez por noite (`qnap.reconciliacao_hora`, padrão 3; -1 desliga),
em segundo plano. Se o QNAP não está montado, tenta de novo daqui a 1 hora. Nunca roda dentro de uma requisição."""
from __future__ import annotations

import json
import logging
from datetime import datetime


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return ((r[0] if r else None) or padrao).strip()


def hora_configurada(con) -> int:
    v = _cfg(con, "qnap.reconciliacao_hora", "3")
    try:
        return int(v)
    except ValueError:
        return 3


def devido(con, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now()
    h = hora_configurada(con)
    if h < 0 or h > 23 or agora.hour < h:
        return False
    if _cfg(con, "qnap.reconciliacao_ultima") == agora.date().isoformat():
        return False
    t = _cfg(con, "qnap.reconciliacao_tentativa")
    if t:
        try:
            if (agora - datetime.fromisoformat(t)).total_seconds() < 3600:      # falhou há pouco: espera 1 hora
                return False
        except ValueError:
            pass
    return True


def rodar(con, agora: datetime | None = None, varrer=None) -> dict:
    """Faz a reconciliação (a varredura da raiz final). Nunca levanta. Devolve {ok, novas, atualizadas, erro?}."""
    agora = agora or datetime.now()
    if varrer is None:
        from .rotas_operacao import _varrer_qnap as varrer
    con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.reconciliacao_tentativa'", (agora.isoformat(timespec="seconds"),))
    con.commit()
    try:
        r = varrer() or {}
        out = {"ok": True, "novas": r.get("novas", 0), "atualizadas": r.get("atualizadas", 0), "com_erro": r.get("com_erro", 0), "processando": r.get("processando", 0)}
        con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.reconciliacao_ultima'", (agora.date().isoformat(),))
    except Exception as e:  # noqa: BLE001  (inclui HTTPException: QNAP não montado)
        out = {"ok": False, "erro": str(getattr(e, "detail", None) or e)[:200]}
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('qnap','qnap','qnap_reconciliacao','rotina',?)", (json.dumps(out, ensure_ascii=False),))
    con.commit()
    try:
        from .log_tecnico import registrar
        registrar(logging.INFO if out["ok"] else logging.WARNING, "qnap_reconciliacao", "Reconciliação noturna do QNAP" + ("" if out["ok"] else ": não concluiu"),
                  **{k: v for k, v in out.items() if isinstance(v, (int, str))})
    except Exception:  # noqa: BLE001
        pass
    return out
