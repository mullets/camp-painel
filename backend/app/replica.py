"""Cópia do acervo (cartão 149): a data da última réplica do ACERVOS_CAMP, lida da sentinela que o CAMP Vision grava em
ACERVOS_CAMP/_campvision/sentinela.json ({"gravado_em": ISO, "versao": ...}, nucleo/quarentena.py do CV2) — conforme ela aparece NA RÉPLICA.
Verde abaixo de 36 h, amarelo até 72 h, vermelho acima disso ou sem sentinela. É a ÚNICA regra (Estações e alerta por e-mail usam esta)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SENTINELA = Path("_campvision") / "sentinela.json"


def estado(con, agora: datetime | None = None) -> dict:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='replica.raiz'").fetchone()
    return estado_de((r[0] if r else "") or "", agora)


def estado_de(raiz: str, agora: datetime | None = None) -> dict:
    """A mesma regra, a partir do caminho (sem banco): a tela Máquinas a roda como sonda em segundo plano (lê arquivo no QNAP)."""
    if not raiz.strip():
        return {"configurada": False, "nivel": None, "texto": "Ainda não há réplica do acervo configurada (Configurações → replica.raiz)."}
    agora = agora or datetime.now(timezone.utc)
    try:
        dados = json.loads((Path(raiz) / SENTINELA).read_text(encoding="utf-8"))
        em = datetime.fromisoformat(dados["gravado_em"])
        if em.tzinfo is None:
            em = em.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return {"configurada": True, "raiz": raiz, "nivel": "critico", "gravado_em": None, "idade_horas": None,
                "texto": "Não encontrei a marca da última cópia na réplica do acervo (sentinela). A cópia pode ter parado: confira a réplica no QNAP."}
    horas = round((agora - em).total_seconds() / 3600, 1)
    nivel = "ok" if horas < 36 else ("aviso" if horas <= 72 else "critico")
    texto = {"ok": f"A réplica do acervo está em dia: última cópia há {horas} h.",
             "aviso": f"A réplica do acervo está atrasada: última cópia há {horas} h (o esperado é menos de 36 h).",
             "critico": f"A réplica do acervo parou: última cópia há {horas} h. O acervo está com uma cópia só; confira a réplica no QNAP."}[nivel]
    return {"configurada": True, "raiz": raiz, "nivel": nivel, "gravado_em": em.isoformat(timespec="seconds"), "idade_horas": horas, "versao": dados.get("versao"), "texto": texto}


# ---------------- UX-02: a última cópia válida e o bloco "Preservação" ----------------
def ultima_valida(con) -> dict | None:
    """A última cópia VÁLIDA que o painel já viu (a marca da sentinela lida com sucesso), mesmo que a sentinela suma depois."""
    try:
        r = con.execute("SELECT gravado_em, versao, visto_em FROM replica_marca WHERE id=1").fetchone()
    except Exception:  # noqa: BLE001  (banco sem a migração 073)
        return None
    return dict(r) if r and r["gravado_em"] else None


def registrar_marca(con, est: dict) -> None:
    """Guarda a data da última cópia válida (só quando a sentinela foi lida e mudou). Não faz commit."""
    if not est.get("gravado_em"):
        return
    try:
        atual = ultima_valida(con)
        if atual and atual["gravado_em"] == est["gravado_em"]:
            return
        con.execute("""INSERT INTO replica_marca (id, gravado_em, versao, visto_em) VALUES (1, ?, ?, datetime('now'))
                       ON CONFLICT(id) DO UPDATE SET gravado_em=excluded.gravado_em, versao=excluded.versao, visto_em=excluded.visto_em""",
                    (est["gravado_em"], est.get("versao")))
    except Exception:  # noqa: BLE001  (banco sem a migração 073: segue sem guardar)
        pass


def medir_destino(est: dict) -> float | None:
    """% livre do disco do destino da cópia (só quando a sentinela abriu agora há pouco). Mexe no disco: em /api/estacoes roda na sonda."""
    if not (est.get("configurada") and est.get("gravado_em")):
        return None
    import shutil
    try:
        du = shutil.disk_usage(est["raiz"])
        return round(100 * du.free / du.total, 1) if du.total else None
    except OSError:
        return None


def medir(raiz: str) -> dict:
    """A sonda da tela Máquinas (UX-12: em segundo plano): o estado da réplica e o espaço livre do destino."""
    est = estado_de(raiz)
    return {**est, "destino_livre_pct": medir_destino(est)}


def preservacao(con, est: dict | None = None) -> dict:
    """O bloco "Preservação" do topo de Máquinas: quantas cópias as imagens têm, em linguagem simples.
    nivel: ok (verde: réplica em dia) | atencao (âmbar: atrasada) | critico (vermelho: sem réplica configurada ou parada).
    Configurar o destino (replica.raiz) e a rotina de cópia é decisão do Rafael: aqui só se MOSTRA o estado."""
    from . import qnap_coletor as qc
    est = est or estado(con)
    ult = ultima_valida(con)
    snap = qc.ultima(con) or {}
    nivel_q, pct = qc.nivel_espaco(con, snap.get("total_gb"), snap.get("livre_gb"))
    _, dias = qc._tendencia(con, snap.get("livre_gb"))
    if not est.get("configurada"):
        nivel, titulo = "critico", "Suas imagens têm só uma cópia"
        texto = ("As digitalizações estão só no QNAP: se o disco falhar, os originais digitais se perdem. A cópia de segurança do painel "
                 "guarda o banco de dados, não as imagens. Falta definir onde fica a segunda cópia (Configurações → replica.raiz).")
    elif not est.get("nivel"):                        # a sonda da réplica ainda não voltou (UX-12): nem verde nem vermelho
        nivel, titulo, texto = None, "Medindo a cópia das imagens", "A leitura da cópia do acervo corre em segundo plano; a tela atualiza sozinha."
    elif est.get("nivel") == "ok":
        nivel, titulo, texto = "ok", "Suas imagens têm duas cópias", est.get("texto") or ""
    elif est.get("nivel") == "aviso":
        nivel, titulo, texto = "atencao", "A segunda cópia das imagens está atrasada", est.get("texto") or ""
    else:
        nivel, titulo, texto = "critico", "Suas imagens podem estar com uma cópia só", est.get("texto") or ""
    destino_pct = est.get("destino_livre_pct") if "destino_livre_pct" in est else medir_destino(est)
    if destino_pct is not None and destino_pct < 5:
        nivel, titulo = "critico", "O disco da segunda cópia está quase cheio"
        texto = f"O destino da cópia está com {destino_pct:g}% livre: a próxima cópia pode não caber. " + texto
    return {"nivel": nivel, "destino_livre_pct": destino_pct, "titulo": titulo, "texto": texto, "configurada": bool(est.get("configurada")),
            "ultima_copia": est.get("gravado_em") or (ult or {}).get("gravado_em"), "ultima_copia_horas": est.get("idade_horas"),
            "ultima_valida": ult, "qnap": {"nivel": nivel_q, "livre_pct": pct, "dias_ate_encher": dias}}
