"""CAMP-024 · Desligar o legado do painel, só o que é seguro, atrás de configuração e com contador de uso.

Peças (chave `legado.*`, 1 = ainda aceita, que é o padrão):
- status_antigos: `campvision_concluido` e `pronto_campvision2` (valores velhos do CV2). `enviado_windows` NÃO é legado: é a marca de fim de lote
  do Windows (contrato C1) e continua aceita sempre. `etapa` no status.json também é lida sempre (C1).
- nomes_de_teste: pasta chamada `asd` / `sei la`. O jeito certo é `"teste": true` no info_projeto.json.
- fundos_json: GET /api/fundos.json (estação Windows antiga). O jeito certo é /api/estacoes/contexto.
Cada uso do legado é contado em `legado_uso` (quantas vezes, última vez, detalhe). GET /api/legado (admin) mostra tudo e diz se é seguro desligar
(nenhum uso nos últimos N dias); `simular` mostra o efeito sem mudar nada. Nada é apagado: religar é trocar a configuração.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["legado"])

PECAS = {
    "status_antigos": "Status antigos do CV2 (campvision_concluido, pronto_campvision2)",
    "nomes_de_teste": "Pastas de teste pelo nome (asd, sei la)",
    "fundos_json": "GET /api/fundos.json (estações antigas)",
}
DIAS_SEM_USO = 30


def ligado(con, peca: str) -> bool:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (f"legado.{peca}",)).fetchone()
    return not r or str(r[0] or "1").strip().lower() not in ("0", "nao", "não", "false", "desligado")


def ligado_agora(peca: str) -> bool:
    """Para quem não tem conexão aberta. Em qualquer erro, assume LIGADO (o comportamento antigo)."""
    try:
        con = connect()
        try:
            return ligado(con, peca)
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return True


_SQL_USO = """INSERT INTO legado_uso (chave, vezes, ultimo_detalhe) VALUES (?,1,?)
               ON CONFLICT(chave) DO UPDATE SET vezes=vezes+1, ultima_em=datetime('now'), ultimo_detalhe=excluded.ultimo_detalhe"""


def registrar_uso(peca: str, detalhe: str = "", con=None) -> None:
    """Conta um uso do legado. Nunca levanta (não pode atrapalhar a rota).

    Quem já tem uma conexão com escrita aberta (a leitura de pasta do lote) PASSA `con`: abrir outra conexão e escrever esperava o
    busy_timeout inteiro (30 s) por chamada e nem contava o uso. Sem `con`, a espera é curta (1 s) e o uso pode se perder, a rota não."""
    try:
        if con is not None:
            con.execute(_SQL_USO, (peca, (detalhe or "")[:200]))
            return
        c = connect()
        try:
            c.execute("PRAGMA busy_timeout = 1000")
            c.execute(_SQL_USO, (peca, (detalhe or "")[:200]))
            c.commit()
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        pass


def relatorio(con) -> list[dict]:
    out = []
    for peca, nome in PECAS.items():
        u = con.execute("SELECT vezes, primeira_em, ultima_em, ultimo_detalhe, (julianday('now')-julianday(ultima_em)) AS dias FROM legado_uso WHERE chave=?", (peca,)).fetchone()
        sem_uso = (not u) or (u["dias"] is not None and u["dias"] >= DIAS_SEM_USO)
        out.append({"chave": peca, "nome": nome, "ligado": ligado(con, peca), "usos": u["vezes"] if u else 0,
                    "ultimo_uso": u["ultima_em"] if u else None, "ultimo_detalhe": u["ultimo_detalhe"] if u else None,
                    "seguro_desligar": bool(sem_uso), "motivo": ("nenhum uso nos últimos %d dias" % DIAS_SEM_USO) if sem_uso else "ainda foi usado há menos de %d dias" % DIAS_SEM_USO})
    return out


@router.get("/legado")
def ver_legado(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"pecas": relatorio(con), "dias_sem_uso": DIAS_SEM_USO}
    finally:
        con.close()


class Desligar(BaseModel):
    ligado: bool
    simular: bool = True


@router.post("/legado/{peca}")
def mudar_legado(peca: str, d: Desligar, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Liga/desliga uma peça do legado. `simular` (padrão) só diz o que aconteceria; desligar peça ainda em uso exige simular=false de propósito (e fica no histórico)."""
    if peca not in PECAS:
        raise HTTPException(404, "Peça de legado desconhecida.")
    con = connect()
    try:
        info = next(p for p in relatorio(con) if p["chave"] == peca)
        efeito = f"Com `legado.{peca}` = {'1' if d.ligado else '0'}: " + ("volta a aceitar." if d.ligado else "o painel deixa de aceitar. " + ("Ninguém usou recentemente." if info["seguro_desligar"] else f"ATENÇÃO: usado {info['usos']}x, último uso {info['ultimo_uso']}."))
        if d.simular:
            return {"simulado": True, "aplicado": False, "peca": info, "efeito": efeito}
        con.execute("UPDATE configuracao SET valor=? WHERE chave=?", ("1" if d.ligado else "0", f"legado.{peca}"))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('sistema',?,'legado_alterado',?,?)",
                    (peca, u["email"], f'{{"ligado": {str(d.ligado).lower()}, "seguro": {str(info["seguro_desligar"]).lower()}}}'))
        con.commit()
        return {"simulado": False, "aplicado": True, "peca": next(p for p in relatorio(con) if p["chave"] == peca), "efeito": efeito}
    finally:
        con.close()
