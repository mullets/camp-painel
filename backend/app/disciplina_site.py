"""Separação por disciplina das folhas de desenho também no site (contrato painel ↔ site 1.38, campo novo e OPCIONAL).

Rafael (25/11/2026): "selecionar várias e colocar o escritório que fez, e que ficasse a separação do tipo elétrica, engenharia, fundação,
desenhos etc., tanto aqui quanto no site". A disciplina de cada folha vem de parceiros.disciplina_grupo (escritório parceiro → tipo →
"Arquitetura"). Só as séries de desenho (S01 Desenhos e pranchas, S08 Redesenhos); as outras séries não mudam.

Rota do site (plugin camp-acervo-auto-pages 1.47.0): POST /wp-json/camp/v1/painel/disciplinas-folhas
    {"projeto": <id do dossiê no site>, "folhas": {"<id da folha no site>": {"disciplina": "Estrutura", "escritorio": "X Ltda."}, ...}}
- "escritorio" pode faltar (disciplina inferida do tipo, ou Arquitetura); "__limpar__" no lugar do objeto apaga a disciplina da folha;
- folha que não vem no corpo não muda no site. Site antigo (404 rest_no_route): nada quebra; a pendência fica com "atualize o site".
O site guarda junto com o projeto (folha movida não leva a disciplina antiga) e, na página do projeto, separa os desenhos por disciplina
quando há duas ou mais; sem nada recebido, a página é exatamente a de antes.

Quando vai (mesmo esquema da ordem das folhas, ordem_site.py): ao mudar escritórios em lote (POST /api/projetos/{p}/parceiros/lote), ao
salvar parceiros ou tipo de uma folha que está no site, ao criar a folha no site; falhou: pendência `pendente_disciplinas_no_site` do
projeto e a rodada de reenvio (reenvio_pendencias) refaz com o estado de agora.
"""
from __future__ import annotations

import json
import threading

from .db import connect

CAMPO = "pendente_disciplinas_no_site"
LIMPAR = "__limpar__"
SEM_ROTA = "O site ainda não tem a separação por disciplina (plugin da CAMP 1.47.0): atualize o site; ela vai quando ele tiver"
_TRAVA = threading.Lock()


def _da_linha(r) -> dict:
    from .parceiros import disciplina_grupo
    disc, esc = disciplina_grupo(r["parceiros"], r["tipo_documento"], r["tipos_documento"], r["tipo_lido"])
    return {"disciplina": disc, **({"escritorio": esc} if esc else {})}


def mapa(con, projeto: str, so: list[str] | None = None) -> tuple[int | None, dict]:
    """(id do dossiê no site, {id da folha no site: {"disciplina", "escritorio"?}}) das folhas de desenho do projeto que já estão no site."""
    from .parceiros import SERIES_DESENHO
    p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (projeto,)).fetchone()
    dossie = int(p[0]) if p and p[0] else None
    folhas = {}
    for r in con.execute("""SELECT codigo, tainacan_item_id, serie_codigo, parceiros, tipo_documento, tipos_documento, tipo_lido FROM item
                             WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL""", (projeto,)):
        if so is not None and r["codigo"] not in so:
            continue
        if r["serie_codigo"] not in SERIES_DESENHO:
            continue
        folhas[str(int(r["tainacan_item_id"]))] = _da_linha(r)
    return dossie, folhas


def tem_folha_no_site(con, projeto: str) -> bool:
    return bool(con.execute("SELECT 1 FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL AND duplicata_de IS NULL LIMIT 1",
                            (projeto,)).fetchone())


def marcar(con, projeto: str) -> bool:
    """Dentro da transação que muda escritório/tipo: deixa a pendência (o envio vem depois, fora da requisição). True = há o que enviar."""
    if not tem_folha_no_site(con, projeto):
        return False
    from .publicador import _pendencia
    _pendencia(con, "projeto", projeto, CAMPO, "A separação por disciplina das folhas ainda não chegou ao site")
    return True


def _enviar(wp, dossie: int, folhas: dict) -> dict:
    """CAMP-SITE-CARGA: em lotes de `site.envio_lote` folhas (padrão 25), um lote por requisição (o portão do site espaça)."""
    from .portao_site import lote
    tam = lote()
    itens = list(folhas.items())
    gravados: list = []
    r: dict = {"ok": True}
    for i in range(0, len(itens), tam):
        r = wp.gravar_disciplinas_folhas(dossie, dict(itens[i:i + tam]))
        if r is None:
            raise RuntimeError(SEM_ROTA)
        erros = r.get("erros") or []
        if erros or not r.get("ok", False):
            raise RuntimeError("O site não confirmou a separação por disciplina: " + json.dumps(erros, ensure_ascii=False)[:200])
        gravados += list(r.get("gravados") or [])
    return {**r, "gravados": gravados}


def enviar(projeto: str, ator: str) -> dict:
    """Manda ao site a disciplina de AGORA das folhas de desenho do projeto que já estão lá. Nunca levanta: {"ok"} / {"nada"} / {"erro"}.
    Sucesso (ou nada a mandar) fecha a pendência; falha a mantém, com o motivo."""
    from .publicador import WP, _pendencia, _resolver_pendencia
    with _TRAVA:
        con = connect()
        try:
            dossie, folhas = mapa(con, projeto)
        finally:
            con.close()
        out: dict = {"projeto": projeto, "folhas": len(folhas)}
        if not dossie or not folhas:
            out["nada"] = True
        else:
            try:
                r = _enviar(WP(), dossie, folhas)
                out.update(ok=True, gravadas=len(r.get("gravados") or []))
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
                    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_disciplinas',?,?)",
                                (projeto, ator, json.dumps(out, ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
        return out


def enviar_depois(projeto: str, ator: str) -> None:
    """Segundo plano. Respeita `site.enviar_correcoes_sozinho` (desligado: a pendência espera o reenvio). Nunca levanta."""
    try:
        from .alteracoes_site import enviar_sozinho
        if not enviar_sozinho():
            return
        # CAMP-SITE-CARGA (26/11): "Definir tipo" em 50 folhas criava 50 envios do projeto INTEIRO. Agora pedidos repetidos do mesmo
        # projeto viram um só: se já há um envio rodando, só marca "de novo" e ele manda o estado mais novo uma vez ao terminar.
        with _JUNTAR:
            if projeto in _RODANDO:
                _DE_NOVO.add(projeto)
                return
            _RODANDO.add(projeto)
        try:
            while True:
                enviar(projeto, ator)
                with _JUNTAR:
                    if projeto in _DE_NOVO:
                        _DE_NOVO.discard(projeto)
                        continue
                    _RODANDO.discard(projeto)
                    break
        except BaseException:
            with _JUNTAR:
                _RODANDO.discard(projeto)
                _DE_NOVO.discard(projeto)
            raise
    except Exception:  # noqa: BLE001
        pass


_JUNTAR = threading.Lock()
_RODANDO: set = set()
_DE_NOVO: set = set()


def depois_de_editar_folha(codigo: str, ator: str) -> None:
    """PATCH da folha mudou parceiros ou tipo: se ela está no site e é de desenho, pendência + envio do projeto. Nunca levanta."""
    try:
        from .parceiros import SERIES_DESENHO
        con = connect()
        try:
            r = con.execute("SELECT projeto_codigo, serie_codigo, tainacan_item_id FROM item WHERE codigo=?", (codigo,)).fetchone()
            if not r or not r["tainacan_item_id"] or r["serie_codigo"] not in SERIES_DESENHO:
                return
            ok = marcar(con, r["projeto_codigo"])
            con.commit()
        finally:
            con.close()
        if ok:
            enviar_depois(r["projeto_codigo"], ator)
    except Exception:  # noqa: BLE001
        pass


def na_criacao_da_folha(con, wp, codigo: str, iid: int, out: dict) -> None:
    """publicador.criar_folha_no_site: a folha de desenho leva a disciplina junto. Falha não impede a folha: deixa a pendência do projeto."""
    try:
        from .parceiros import SERIES_DESENHO
        r = con.execute("""SELECT i.projeto_codigo, i.serie_codigo, i.parceiros, i.tipo_documento, i.tipos_documento, i.tipo_lido, p.tainacan_item_id AS dossie
                             FROM item i LEFT JOIN projeto p ON p.codigo=i.projeto_codigo WHERE i.codigo=?""", (codigo,)).fetchone()
        if not r or r["serie_codigo"] not in SERIES_DESENHO or not r["dossie"]:
            return
        try:
            _enviar(wp, int(r["dossie"]), {str(int(iid)): _da_linha(r)})
            out["disciplina"] = "enviada"
        except Exception as e:  # noqa: BLE001
            from .publicador import _pendencia
            _pendencia(con, "projeto", r["projeto_codigo"], CAMPO, str(e)[:200])
            out["disciplina"] = "pendente"
    except Exception:  # noqa: BLE001
        pass
