"""Fundo sem legendas nas imagens do site (contrato painel ↔ site 1.9, 10/11/2026; pedido do Rafael para o fundo da Chu Ming Silveira).

O painel decide (coluna fundo.sem_legendas, migração 219) e manda pela rota do hub do site (POST /painel/hub/{termo}, a mesma do
"Enviar fundo ao site"), num campo NOVO e OPCIONAL:
    {"meta": {"_camp_sem_legendas": "1"}}           ligado
    {"meta": {"_camp_sem_legendas": "__limpar__"}}  desligado depois de ligado (vazio nunca apaga no hub)
NULL (nunca escolhido) não manda nada: os outros fundos recebem exatamente o mesmo de antes.
O site (plugin camp-acervo-auto-pages 1.23.24) guarda no termo do fundo e tira a legenda descritiva das imagens dos projetos e
folhas do fundo (o texto alternativo e o crédito obrigatório da foto ficam). Site antigo devolve a chave em "ignorados": nada
quebra, a pendência fica com "atualize o site" e o valor vai quando o site tiver o plugin novo.

Quando vai:
- ao mudar a caixa no fundo (PATCH /api/fundos/{codigo}): a pendência `pendente_sem_legendas_no_site` entra no MESMO commit e o
  envio sai em segundo plano (respeita site.enviar_correcoes_sozinho); falhou, a rodada de reenvio (reenvio_pendencias) refaz;
- junto do "Enviar fundo ao site" (fundo_site.enviar_fundo), quando há valor escolhido.
"""
from __future__ import annotations

import json

from .db import connect

CAMPO = "pendente_sem_legendas_no_site"
CHAVE = "_camp_sem_legendas"
LIMPAR = "__limpar__"          # o mesmo publicador.HUB_LIMPAR
SEM_SUPORTE = "O site ainda não conhece \"sem legendas\" (plugin da CAMP 1.23.24): atualize o site; vai quando ele tiver"


def valor_hub(sem_legendas) -> dict:
    """{CHAVE: "1" | "__limpar__"} ou {} (NULL: nunca escolhido, nada vai)."""
    if sem_legendas is None:
        return {}
    return {CHAVE: "1" if int(sem_legendas) else LIMPAR}


def do_fundo(con, codigo: str) -> dict:
    r = con.execute("SELECT sem_legendas FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    return valor_hub(r["sem_legendas"]) if r else {}


def marcar(con, codigo: str) -> bool:
    """Dentro da transação que muda a caixa: deixa a pendência (o envio vem depois). True = o fundo está no site (há o que enviar)."""
    f = con.execute("SELECT tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f or not f[0]:
        return False                     # fundo ainda não está no site: vai junto do "Enviar fundo ao site"
    from .publicador import _pendencia
    _pendencia(con, "fundo", codigo, CAMPO, "\"Sem legendas nas imagens do site\" ainda não chegou ao site")
    return True


def conferir_resposta(r) -> None:
    """Site antigo ignora a chave (não a conhece): levanta RuntimeError(SEM_SUPORTE)."""
    if isinstance(r, dict) and CHAVE in (r.get("ignorados") or []):
        raise RuntimeError(SEM_SUPORTE)


def enviar(codigo: str, ator: str) -> dict:
    """Manda ao site o valor de AGORA. Nunca levanta: {"ok"} / {"nada"} / {"erro"}. Sucesso (ou nada) fecha a pendência; falha a mantém."""
    from .publicador import WP, CONVIDADO, _pendencia, _resolver_pendencia
    con = connect()
    try:
        f = con.execute("SELECT tainacan_term_id, sem_legendas FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    out: dict = {"fundo": codigo}
    meta = valor_hub(f["sem_legendas"]) if f else {}
    if not f or not f["tainacan_term_id"] or not meta or str(codigo).upper().startswith(CONVIDADO):
        out["nada"] = True
    else:
        try:
            r = WP().gravar_hub(int(f["tainacan_term_id"]), meta)
            conferir_resposta(r)
            out.update(ok=True, valor=meta[CHAVE])
        except Exception as e:  # noqa: BLE001
            out["erro"] = str(e)[:300]
    con = connect()
    try:
        if out.get("erro"):
            _pendencia(con, "fundo", codigo, CAMPO, out["erro"])
            con.execute("UPDATE divergencia_site SET valor_painel=? WHERE entidade='fundo' AND codigo=? AND campo=? AND resolvida=0",
                        (out["erro"][:300], codigo, CAMPO))
        else:
            _resolver_pendencia(con, "fundo", codigo, CAMPO)
            if out.get("ok"):
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'site_sem_legendas',?,?)",
                            (codigo, ator, json.dumps(out, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return out


def enviar_depois(codigo: str, ator: str) -> None:
    """Segundo plano, logo depois de mudar a caixa. Respeita `site.enviar_correcoes_sozinho` (desligado: a pendência espera o botão
    de reenvio). Nunca levanta."""
    try:
        from .alteracoes_site import enviar_sozinho
        if enviar_sozinho():
            enviar(codigo, ator)
    except Exception:  # noqa: BLE001
        pass
