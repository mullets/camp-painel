"""UX-34 · "Quem" no Histórico de ações, com nomes legíveis.

O `evento.ator` guarda o que cada parte do sistema escreveu: e-mail de quem fez, IP ou "estacao@IP" das máquinas,
"Nome (estacao@IP)" do operador numa estação, "importacao", "sistema", "migração 140", "script marcar_giro_publicado"…
O filtro principal NÃO mostra isso cru: agrupa em
  - Pessoas  (nome do usuário do painel; operador de estação pelo nome que digitou),
  - Máquinas (nome da estação pela configuração estacao.*.ip ou pelo heartbeat; CAMP Vision; IP desconhecido vira
              "Máquina da rede não identificada" / "Acesso de fora da rede" — nunca o número),
  - Sistema  (Rotinas automáticas, Migrações do banco, Scripts de manutenção, Sincronização com o site).
Cada opção tem uma chave (p:/m:/s:) que o servidor traduz de volta para os atores crus (`ator IN (...)`).
Só leitura: nada no banco muda.
"""
from __future__ import annotations

import re
import unicodedata

_IP = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_ESTACAO_IP = re.compile(r"^estacao@(\d{1,3}(?:\.\d{1,3}){3})$", re.I)
_OPERADOR = re.compile(r"^(.+?)\s*\(estacao@(\d{1,3}(?:\.\d{1,3}){3})\)$", re.I)
_DESC_IP = re.compile(r"^IP d[aoe]s?\s+(.+?)(?:\s*\(|\s+na rede|$)", re.I)

GRUPOS = (("pessoas", "Pessoas"), ("maquinas", "Máquinas"), ("sistema", "Sistema"))
SISTEMA = {"migracoes": "Migrações do banco", "scripts": "Scripts de manutenção", "site": "Sincronização com o site",
           "rotinas": "Rotinas automáticas"}


def _sa(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower().strip()


def _privado(ip: str) -> bool:
    return ip.startswith(("10.", "192.168.", "127.")) or bool(re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip))


def _contexto(con) -> dict:
    usuarios_email, usuarios_nome = {}, {}
    for r in con.execute("SELECT nome, email FROM usuario"):
        if r[1]:
            usuarios_email[r[1].lower()] = r[0] or r[1]
        if r[0]:
            usuarios_nome[_sa(r[0])] = r[0]
    ips: dict[str, str] = {}
    try:
        for r in con.execute("SELECT estacao_id, hostname, ip_local, recebido_de_ip FROM estacao_heartbeat"):
            nome = (r[1] or r[0] or "").strip()
            for ip in (r[2], r[3]):
                if ip and nome:
                    ips.setdefault(ip.strip(), nome)
    except Exception:  # noqa: BLE001 — banco sem a tabela (antigo): sem nomes do heartbeat
        pass
    for r in con.execute("SELECT valor, descricao FROM configuracao WHERE chave LIKE '%.ip' AND COALESCE(valor,'')<>''"):
        m = _DESC_IP.match(r[1] or "")
        if m:
            ips[r[0].strip()] = m.group(1).strip()          # a configuração (nome dado pela equipe) vale mais que o hostname
    ids = {}
    try:
        for r in con.execute("SELECT estacao_id, hostname FROM estacao_heartbeat"):
            ids[_sa(r[0])] = (r[1] or r[0]).strip()
    except Exception:  # noqa: BLE001
        pass
    return {"email": usuarios_email, "nome": usuarios_nome, "ips": ips, "ids": ids}


def _maquina_ip(ip: str, ctx: dict) -> tuple[str, str]:
    if ip in ctx["ips"]:
        return f"m:{_sa(ctx['ips'][ip])}", ctx["ips"][ip]
    return ("m:~rede", "Máquina da rede não identificada") if _privado(ip) else ("m:~fora", "Acesso de fora da rede")


def classificar(ator: str | None, ctx: dict) -> list[tuple[str, str, str]]:
    """[(grupo, chave, rótulo)] — um ator pode cair em dois (operador numa estação: a pessoa E a máquina)."""
    a = (ator or "").strip()
    s = _sa(a)
    if not a:
        return [("sistema", "s:rotinas", SISTEMA["rotinas"])]
    m = _OPERADOR.match(a)
    if m:
        nome = m.group(1).strip()
        pessoa = ctx["email"].get(nome.lower()) or ctx["nome"].get(_sa(nome)) or nome
        return [("pessoas", f"p:{_sa(pessoa)}", pessoa), ("maquinas", *_maquina_ip(m.group(2), ctx))]
    m = _ESTACAO_IP.match(a)
    if m or _IP.match(a):
        return [("maquinas", *_maquina_ip(m.group(1) if m else a, ctx))]
    if "@" in a and " " not in a:
        nome = ctx["email"].get(a.lower())
        return [("pessoas", f"p:{_sa(nome) if nome else a.lower()}", nome or a.lower())]
    if s in ctx["nome"]:
        return [("pessoas", f"p:{s}", ctx["nome"][s])]
    if "vision" in s or s in ("cv", "cv2", "campvision", "importacao"):
        return [("maquinas", "m:campvision", "CAMP Vision")]
    if s in ctx["ids"] or s.startswith("estacao"):
        nome = ctx["ids"].get(s) or "Estação (sem nome)"
        return [("maquinas", f"m:{_sa(nome)}", nome)]
    if "migra" in s:
        return [("sistema", "s:migracoes", SISTEMA["migracoes"])]
    if "script" in s:
        return [("sistema", "s:scripts", SISTEMA["scripts"])]
    if s in ("site", "wordpress", "tainacan", "wp", "sync", "sincronizacao") or s.startswith(("site ", "site:", "site_")):
        return [("sistema", "s:site", SISTEMA["site"])]
    return [("sistema", "s:rotinas", SISTEMA["rotinas"])]


def facetas(con, limite_atores: int = 2000) -> tuple[list[dict], dict[str, list[str]]]:
    """(grupos para a tela, chave -> atores crus). Contagem por opção = soma dos eventos dos atores."""
    ctx = _contexto(con)
    opcoes: dict[str, dict] = {}
    mapa: dict[str, list[str]] = {}
    for ator, n in con.execute("SELECT ator, COUNT(*) FROM evento GROUP BY ator ORDER BY COUNT(*) DESC LIMIT ?", (limite_atores,)):
        for grupo, chave, rotulo in classificar(ator, ctx):
            o = opcoes.setdefault(chave, {"valor": chave, "rotulo": rotulo, "grupo": grupo, "n": 0})
            o["n"] += n
            mapa.setdefault(chave, []).append(ator if ator is not None else "")
    grupos = []
    for g, rot in GRUPOS:
        itens = sorted((o for o in opcoes.values() if o["grupo"] == g), key=lambda o: (-o["n"], o["rotulo"]))
        if itens:
            grupos.append({"grupo": g, "rotulo": rot, "itens": [{k: o[k] for k in ("valor", "rotulo", "n")} for o in itens]})
    return grupos, mapa


def atores_de(con, chave: str) -> list[str]:
    return facetas(con)[1].get(chave, [])
