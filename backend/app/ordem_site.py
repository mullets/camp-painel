"""Ordem das folhas escolhida no painel (item.ordem_manual, PR #134) também vale no site (contrato painel ↔ site 1.8).

Rota do site (plugin camp-acervo-auto-pages 1.23.21): POST /wp-json/camp/v1/painel/ordem-folhas
    {"projeto": <id do dossiê no site>, "ordem": {"<id da folha no site>": 0, "<id>": "__limpar__", ...}}
- número = posição escolhida (0, 1, 2…); "__limpar__" = a folha volta à ordem de sempre (mesma convenção do hub);
- folha que não vem no corpo não muda no site.
O site guarda a posição junto com o projeto (folha movida para outro projeto não leva a posição antiga). Sem posição em
nenhuma folha, o site mostra exatamente como sempre mostrou (nº de folha / código, blocos das fotos).

Quando vai:
- ao gravar ou limpar a ordem (PUT/DELETE /api/projetos/{p}/ordem-folhas): a pendência `pendente_ordem_folhas_no_site` do projeto
  entra no MESMO commit da ordem nova e o envio sai em segundo plano, com o estado de agora (todas as folhas do projeto que já
  estão no site: posição ou "__limpar__"). Se o site recusar, a pendência fica e a rodada de reenvio (reenvio_pendencias) refaz;
- ao criar uma folha no site (publicador.criar_folha_no_site): só se ela tem posição (sem posição, nada é mandado).
Site antigo (404 `rest_no_route`): nada quebra; a pendência fica com "atualize o site" e vai quando o site tiver a rota.
"""
from __future__ import annotations

import json
import threading

from .db import connect

CAMPO = "pendente_ordem_folhas_no_site"
LIMPAR = "__limpar__"          # o mesmo publicador.HUB_LIMPAR
SEM_ROTA = "O site ainda não tem a rota da ordem das folhas (plugin da CAMP 1.23.21): atualize o site; a ordem vai quando ele tiver"
_TRAVA = threading.Lock()      # um envio de ordem por vez (dois arrastos seguidos nunca chegam fora de ordem)


def mapa(con, projeto: str, so: list[str] | None = None) -> tuple[int | None, dict]:
    """(id do dossiê no site, {id da folha no site: posição | "__limpar__"}) das folhas do projeto que já estão no site."""
    p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (projeto,)).fetchone()
    dossie = int(p[0]) if p and p[0] else None
    sql = "SELECT codigo, tainacan_item_id, ordem_manual FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL"
    ordem = {}
    for r in con.execute(sql, (projeto,)):
        if so is not None and r["codigo"] not in so:
            continue
        ordem[str(int(r["tainacan_item_id"]))] = int(r["ordem_manual"]) if r["ordem_manual"] is not None else LIMPAR
    return dossie, ordem


def tem_folha_no_site(con, projeto: str) -> bool:
    return bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL LIMIT 1",
                            (projeto,)).fetchone())


def marcar(con, projeto: str) -> bool:
    """Chamada dentro da transação que muda a ordem: deixa a pendência (o envio vem depois, fora da requisição). True = há o que enviar."""
    if not tem_folha_no_site(con, projeto):
        return False
    from .publicador import _pendencia
    _pendencia(con, "projeto", projeto, CAMPO, "A ordem das folhas escolhida no painel ainda não chegou ao site")
    return True


def _enviar(wp, dossie: int, ordem: dict) -> dict:
    """Uma chamada ao site. Levanta RuntimeError(SEM_ROTA) no site antigo e RuntimeError quando o site não confirma."""
    r = wp.gravar_ordem_folhas(dossie, ordem)
    if r is None:
        raise RuntimeError(SEM_ROTA)
    erros = r.get("erros") or []
    if erros or not r.get("ok", False):
        raise RuntimeError("O site não confirmou a ordem das folhas: " + json.dumps(erros, ensure_ascii=False)[:200])
    return r


def enviar(projeto: str, ator: str) -> dict:
    """Manda ao site a ordem de AGORA das folhas do projeto que já estão lá. Nunca levanta: devolve {"ok"} / {"nada"} / {"erro"}.
    Sucesso (ou nada a mandar) fecha a pendência; falha a mantém, com o motivo."""
    from .publicador import WP, _pendencia, _resolver_pendencia
    with _TRAVA:
        con = connect()
        try:
            dossie, ordem = mapa(con, projeto)
        finally:
            con.close()
        out: dict = {"projeto": projeto, "folhas": len(ordem)}
        if not dossie or not ordem:
            out["nada"] = True
        else:
            try:
                r = _enviar(WP(), dossie, ordem)
                out.update(ok=True, gravadas=len(r.get("gravados") or []), limpas=len(r.get("limpos") or []))
            except Exception as e:  # noqa: BLE001
                out["erro"] = str(e)[:300]
        con = connect()
        try:
            if out.get("erro"):
                _pendencia(con, "projeto", projeto, CAMPO, out["erro"])
                con.execute("UPDATE divergencia_site SET valor_painel=? WHERE entidade='projeto' AND codigo=? AND campo=? AND resolvida=0",
                            (out["erro"][:300], projeto, CAMPO))
            else:
                _resolver_pendencia(con, "projeto", projeto, CAMPO)
                if out.get("ok"):
                    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_ordem_folhas',?,?)",
                                (projeto, ator, json.dumps(out, ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
        return out


def enviar_depois(projeto: str, ator: str) -> None:
    """Segundo plano, logo depois de gravar/limpar a ordem. Respeita `site.enviar_correcoes_sozinho` (desligado: a pendência espera o
    botão de reenvio). Nunca levanta."""
    try:
        from .alteracoes_site import enviar_sozinho
        if enviar_sozinho():
            enviar(projeto, ator)
    except Exception:  # noqa: BLE001
        pass


def na_criacao_da_folha(con, wp, i, iid: int, out: dict) -> None:
    """publicador.criar_folha_no_site: a folha que tem posição leva a posição junto. Sem posição: não manda nada (como antes).
    Falha não impede a folha: deixa a pendência do projeto (o reenvio manda a ordem do projeto inteiro)."""
    if "ordem_manual" not in i.keys() or i["ordem_manual"] is None or not i["dossie_id"]:
        return
    try:
        _enviar(wp, int(i["dossie_id"]), {str(int(iid)): int(i["ordem_manual"])})
        out["ordem_no_projeto"] = int(i["ordem_manual"])
    except Exception as e:  # noqa: BLE001
        from .publicador import _pendencia
        _pendencia(con, "projeto", i["projeto_codigo"], CAMPO, str(e)[:300])
