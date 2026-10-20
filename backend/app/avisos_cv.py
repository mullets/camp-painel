"""CAMP-122 (P1, 20/10, F026-P0009 CRASA): "erro" do CAMP Vision que é só aviso [Minor] do exiftool.

O CV2 gravou status.json "erro" com a mensagem `F026-P0009-1978-S01-D00034.tif Warning: [Minor] IPTC:By-line exceeds length limit (truncated)`:
o nome do autor passou do limite do campo IPTC e foi cortado. Nada se perdeu. O painel mostrava "Lote parado por erro do CAMP Vision" e
"Nada foi importado deste lote" num projeto com 34 folhas conferidas e publicado.

Regra: se a mensagem do erro é SÓ avisos [Minor] (linhas `<arquivo> Warning: [Minor] …`) e o lote tem folhas importadas ou o pacote do CAMP Vision
existe, o lote NÃO está parado: volta à etapa em que estaria (revisão; publicado se já aprovado e o projeto está no site) e cada aviso vira um
problema "aviso" (não impede publicar) na folha, com um texto para pessoas. Qualquer outra coisa na mensagem = erro de verdade (continua vermelho).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_EXT = r"(?:tiff?|jpe?g|png|dng|psd)"
_ITEM = re.compile(r"(?:(?P<arq>[^\s:;,]+\." + _EXT + r")\s*[:\-]?\s*)?Warning:\s*\[Minor\]\s*(?P<msg>[^;|\n]+?)\s*(?=[;|]|[^\s:;,]+\." + _EXT + r"\s*[:\-]?\s*(?:Warning|Error)\b|$)",
                   re.I | re.M)
# o que pode sobrar em volta dos avisos sem virar "erro de verdade" (prefixos que o CV2 ou o exiftool põem)
_SOBRA_OK = re.compile(r"(?i)^[\s;,.|:\-–—]*(?:(?:exiftool|exif|avisos?|warnings?)[\s;,.|:\-–—]*)*$")
CHAVE = "campvision:aviso-menor:"

_TRADUZ = (
    (re.compile(r"IPTC:By-line exceeds length limit", re.I), "o nome do autor era longo demais para o campo IPTC e foi cortado"),
    (re.compile(r"IPTC:(\S+) exceeds length limit", re.I), "o campo IPTC {0} era longo demais e foi cortado"),
    (re.compile(r"Duplicate .* tag", re.I), "uma etiqueta de metadados veio repetida no arquivo"),
)


def avisos_menores(texto) -> list[dict] | None:
    """[{arquivo, msg}] se a mensagem é SÓ avisos [Minor] do exiftool; None se há qualquer outra coisa (erro de verdade) ou nada."""
    t = str(texto or "").strip()
    if not t or "[minor]" not in t.lower():
        return None
    achados, resto, fim = [], [], 0
    for m in _ITEM.finditer(t):
        resto.append(t[fim:m.start()]); fim = m.end()
        achados.append({"arquivo": (m.group("arq") or "").strip(), "msg": " ".join(m.group("msg").split())})
    resto.append(t[fim:])
    if not achados or not _SOBRA_OK.match("".join(resto)):
        return None
    return achados


def texto_humano(aviso: dict) -> tuple[str | None, str]:
    """(código da folha ou None, frase para pessoas). Ex.: ("F026-P0009-1978-S01-D00034", "1 arquivo (D00034): o nome do autor … Não impede publicar.")"""
    from .importador_lote import CODIGO_DOCUMENTO
    arq = Path(aviso.get("arquivo") or "").stem
    cod = arq if CODIGO_DOCUMENTO.match(arq or "") else None
    msg = aviso.get("msg") or ""
    frase = None
    for rx, txt in _TRADUZ:
        m = rx.search(msg)
        if m:
            frase = txt.format(*m.groups())
            break
    frase = frase or f"aviso menor do exiftool ({msg})"
    onde = f"1 arquivo ({cod.rsplit('-', 1)[-1]})" if cod else (f"1 arquivo ({arq})" if arq else "O CAMP Vision")
    return cod, f"{onde}: {frase}. Não impede publicar."


def motivo_completo(resultado) -> str | None:
    """A mensagem inteira (sem cortar) que o CAMP Vision deixou no status.json, guardada em lista_processamento.resultado."""
    try:
        j = json.loads(resultado or "{}") if isinstance(resultado, str) else (resultado or {})
    except ValueError:
        return None
    if not isinstance(j, dict):
        return None
    fontes = [j] + ([j["status"]] if isinstance(j.get("status"), dict) else [])
    for f in fontes:
        for k in ("erro", "mensagem_erro", "motivo", "mensagem", "detalhe", "error", "message"):
            v = f.get(k)
            if isinstance(v, dict):
                v = v.get("mensagem") or v.get("message") or v.get("detalhe")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def registrar(con, projeto: str, avisos: list[dict]) -> int:
    """Cada aviso vira um problema 'aviso' (não impede publicar) na folha. Idempotente: a chave nasce do conteúdo; quem já marcou como visto não volta."""
    novos = 0
    for a in avisos:
        cod, frase = texto_humano(a)
        chave = CHAVE + hashlib.sha1(f"{projeto}|{a.get('arquivo')}|{a.get('msg')}".encode("utf-8")).hexdigest()[:20]
        novos += con.execute("""INSERT OR IGNORE INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, chave)
                                VALUES ('aviso', 'metadado', 'campvision', ?, ?, 'CAMP Vision', ?)""", (cod or projeto, frase, chave)).rowcount
    return novos


def curar_lote(con, lote_id: int) -> str | None:
    """Lote em 'erro' cuja mensagem é só aviso [Minor] e que tem folhas (ou pacote): sai de 'erro'. Devolve a etapa nova (ou None se não mexeu)."""
    l = con.execute("""SELECT l.id, l.etapa, l.aprovado_em, l.resultado, l.pasta_qnap, l.projeto_codigo, p.status_site,
                              (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id) AS itens
                         FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo WHERE l.id=?""", (lote_id,)).fetchone()
    if not l:
        return None
    av = avisos_menores(motivo_completo(l["resultado"]))
    if not av:
        return None
    if l["etapa"] != "erro":                        # lote já publicado/aprovado nunca regride: o aviso só entra em Problemas
        registrar(con, l["projeto_codigo"], av)
        return None
    pacote = Path(l["pasta_qnap"] or "") / "catalogacao" / "pacote_tainacan.json"
    try:
        tem_pacote = pacote.is_file()
    except OSError:
        tem_pacote = False
    if not l["itens"] and not tem_pacote:
        return None                                  # nada importado e nada para importar: continua erro (pede releitura)
    nova = "publicado" if (l["aprovado_em"] and l["status_site"] == "no_ar") else "revisao"
    con.execute("UPDATE lista_processamento SET etapa=?, atualizado_em=datetime('now') WHERE id=?", (nova, l["id"]))
    registrar(con, l["projeto_codigo"], av)
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista', ?, 'erro_cv_so_avisos', 'painel', ?)",
                (str(l["id"]), json.dumps({"avisos": av, "etapa": nova}, ensure_ascii=False)))
    return nova


def curar_lotes(con, projeto: str | None = None) -> int:
    """Todos os lotes em 'erro' (de um projeto ou da base) que são só aviso menor. Para a base que já está assim (ex.: F026-P0009)."""
    w, par = ("AND projeto_codigo=?", (projeto,)) if projeto else ("", ())
    n = 0
    for (lid,) in con.execute(f"SELECT id FROM lista_processamento WHERE etapa='erro' AND descartado_em IS NULL {w}", par).fetchall():
        n += bool(curar_lote(con, lid))
    return n


def avisos_abertos(con, projeto: str) -> list[dict]:
    """Os avisos menores do CAMP Vision ainda não vistos deste projeto (para a página: 'Marcar como visto')."""
    return [dict(r) for r in con.execute("""SELECT id, codigo, descricao FROM erro WHERE chave LIKE ? AND situacao IN ('aberto','em_correcao')
                                             AND (codigo=? OR codigo LIKE ?) ORDER BY id""", (CHAVE + "%", projeto, projeto + "-%"))]
