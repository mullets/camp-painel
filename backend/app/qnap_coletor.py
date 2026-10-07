"""Coleta de informações do QNAP em SEGUNDO PLANO (padrão: docs/padroes.md §1).

NUNCA varrer o QNAP dentro de uma requisição: por SMB uma varredura é lenta e, com a montagem travada, trava o painel.
O coletor mede com limite de tempo, guarda o resultado (e o histórico, que dá a tendência de espaço) e a tela só lê o guardado.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .db import connect

ORCAMENTO_S = 25          # tempo máximo de uma coleta inteira
RETENCAO_DIAS = 90
IGNORAR = ("@", ".")      # lixeira/miniaturas do QNAP (@Recycle, .@__thumb...) e arquivos ocultos
_lock = threading.Lock()
_atual: threading.Thread | None = None


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return r[0] if r and r[0] not in (None, "") else padrao


def _ts(mt: float) -> str:
    return datetime.fromtimestamp(mt, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _lotes(prontos: Path, prazo: float) -> tuple[int, tuple[float, str], bool]:
    """Conta as pastas com info_projeto.json ou status.json (um lote por pasta; não entra DENTRO de um lote).
    Devolve (quantidade, (mtime, nome) do lote mais recente, parcial). Para no prazo e avisa que ficou parcial."""
    pilha, n, recente, parcial = [str(prontos)], 0, (0.0, ""), False
    while pilha:
        if time.monotonic() > prazo:
            parcial = True
            break
        d = pilha.pop()
        try:
            with os.scandir(d) as it:
                entradas = list(it)
        except OSError:
            continue
        nomes = {e.name for e in entradas}
        achou = [x for x in ("info_projeto.json", "status.json") if x in nomes]
        if achou:
            n += 1
            try:
                mt = max(os.stat(os.path.join(d, x)).st_mtime for x in achou)
            except OSError:
                mt = 0.0
            if mt > recente[0]:
                rel = os.path.relpath(d, prontos)
                recente = (mt, os.path.basename(d) if rel == "." else rel)
            continue
        for e in entradas:
            if e.name.startswith(IGNORAR):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    pilha.append(e.path)
            except OSError:
                pass
    return n, recente, parcial


def _medir(raiz: Path, entrada: Path | None, prontos: Path, dias_parado: int, prazo: float) -> dict:
    from .rotas_gestao import _estado_qnap   # import tardio: evita ciclo entre módulos
    r: dict = {}
    t = time.monotonic()
    montado, motivo = _estado_qnap(raiz)
    r["latencia_ms"] = round((time.monotonic() - t) * 1000)
    r["montado"], r["motivo"] = int(montado), motivo
    if not montado:
        return r
    try:
        du = shutil.disk_usage(raiz)
        r["total_gb"], r["livre_gb"] = round(du.total / 1e9, 1), round(du.free / 1e9, 1)
    except OSError:
        pass
    recente = (0.0, "")
    if entrada is not None and entrada.is_dir():
        limite, n, parados = time.time() - dias_parado * 86400, 0, 0
        try:
            with os.scandir(entrada) as it:
                for e in it:
                    if e.name.startswith(IGNORAR):
                        continue
                    n += 1
                    try:
                        mt = e.stat().st_mtime
                    except OSError:
                        continue
                    parados += mt < limite
                    if mt > recente[0]:
                        recente = (mt, e.name)
        except OSError:
            pass
        r["entrada_bruta"], r["parados"] = n, int(parados)
    if prontos is not None and prontos.is_dir():
        n, rec, parcial = _lotes(prontos, prazo)
        r["prontos"], r["prontos_parcial"] = n, int(parcial)
        if rec[0] > recente[0]:
            recente = rec
    if recente[0]:
        r["ultimo_material_em"], r["ultimo_material_nome"] = _ts(recente[0]), recente[1][:200]
    return r


COLUNAS = ("montado", "motivo", "latencia_ms", "total_gb", "livre_gb", "entrada_bruta", "parados", "prontos", "prontos_parcial",
           "ultimo_material_em", "ultimo_material_nome", "erro")


def _gravar(dados: dict, duracao_ms: int) -> dict:
    con = connect()
    try:
        cols = [c for c in COLUNAS if c in dados]
        con.execute(f"INSERT INTO qnap_snapshot ({','.join(cols + ['duracao_ms'])}) VALUES ({','.join('?' * (len(cols) + 1))})",
                    [dados[c] for c in cols] + [duracao_ms])
        con.execute("DELETE FROM qnap_snapshot WHERE coletado_em < datetime('now', ?)", (f"-{RETENCAO_DIAS} days",))
        con.commit()
    finally:
        con.close()
    return {**dados, "duracao_ms": duracao_ms}


def coletar() -> dict:
    """Uma coleta, com limite de tempo. Nunca levanta exceção e nunca fica pendurada esperando o QNAP."""
    global _atual
    if not _lock.acquire(blocking=False):
        return {"ocupada": True}
    try:
        if _atual is not None and _atual.is_alive():
            return _gravar({"erro": "a coleta anterior ainda está presa: o QNAP não está respondendo"}, 0)
        con = connect()
        try:
            raiz = Path(_cfg(con, "qnap.raiz", settings.CAMP_QNAP_ROOT))
            entrada_txt, prontos_txt = _cfg(con, "qnap.entrada_captura"), _cfg(con, "qnap.prontos_raiz")
            dias = _cfg(con, "qnap.dias_parado", "3")
        finally:
            con.close()
        entrada = Path(entrada_txt) if entrada_txt else None
        prontos = Path(prontos_txt) if prontos_txt else raiz
        dias_parado = int(dias) if str(dias).isdigit() else 3
        saida: dict = {}
        t0 = time.monotonic()

        def alvo() -> None:
            try:
                saida.update(_medir(raiz, entrada, prontos, dias_parado, t0 + max(1, ORCAMENTO_S - 3)))
            except Exception as e:  # noqa: BLE001
                saida["erro"] = f"falha ao medir: {str(e)[:160]}"

        _atual = threading.Thread(target=alvo, daemon=True)
        _atual.start()
        _atual.join(ORCAMENTO_S)
        if _atual.is_alive():
            saida = {"erro": f"tempo esgotado ({ORCAMENTO_S}s): o QNAP não respondeu a tempo"}
        return _gravar(dict(saida), round((time.monotonic() - t0) * 1000))
    finally:
        _lock.release()


def em_andamento() -> bool:
    return _lock.locked() or (_atual is not None and _atual.is_alive())


def ultima(con) -> dict | None:
    r = con.execute("SELECT * FROM qnap_snapshot ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def _tendencia(con, livre: float | None) -> tuple[float | None, int | None]:
    """GB usados por dia (regressão linear dos últimos 7 dias) e dias até encher. Sem dados suficientes: (None, None)."""
    pts = con.execute("""SELECT julianday(coletado_em), total_gb - livre_gb FROM qnap_snapshot
                          WHERE coletado_em >= datetime('now','-7 days') AND livre_gb IS NOT NULL AND total_gb IS NOT NULL
                          ORDER BY id""").fetchall()
    if len(pts) < 3 or pts[-1][0] - pts[0][0] < 0.25:
        return None, None
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den <= 0:
        return None, None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / den
    dias = round(livre / slope) if (livre and slope > 0.5) else None
    return round(slope, 1), dias


def resumo(con) -> dict:
    snap = ultima(con)
    idade = None
    if snap:
        idade = con.execute("SELECT CAST((julianday('now') - julianday(?)) * 86400 AS INTEGER)", (snap["coletado_em"],)).fetchone()[0]
    cresc, dias = _tendencia(con, snap["livre_gb"] if snap else None)
    pontos = con.execute("""SELECT coletado_em, livre_gb FROM qnap_snapshot WHERE coletado_em >= datetime('now','-7 days')
                             AND livre_gb IS NOT NULL ORDER BY id""").fetchall()
    passo = max(1, -(-len(pontos) // 60))
    return {"coleta": snap, "idade_s": idade, "crescimento_gb_dia": cresc, "dias_ate_encher": dias,
            "serie": [{"em": p[0], "livre_gb": p[1]} for p in pontos[::passo]], "coletando": em_andamento(),
            "config": {"coleta_min": int(_cfg(con, "qnap.coleta_min", "10") or 10) if str(_cfg(con, "qnap.coleta_min", "10")).isdigit() else 10,
                       "dias_parado": int(_cfg(con, "qnap.dias_parado", "3")) if str(_cfg(con, "qnap.dias_parado", "3")).isdigit() else 3}}
