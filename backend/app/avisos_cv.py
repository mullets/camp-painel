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


# UX-08: o resumo em UMA frase ("4 imagens têm o nome do autor longo demais no EXIF; ele foi cortado. Não impede publicar.").
# Agrupa pelo tipo do aviso: a mensagem crua do exiftool (msg) ou a frase já gravada na folha (descricao do problema).
_GRUPO_MSG = ((re.compile(r"IPTC:By-line exceeds length limit", re.I), "autor"), (re.compile(r"IPTC:(\S+) exceeds length limit", re.I), "campo"),
              (re.compile(r"Duplicate .* tag", re.I), "repetida"))
_GRUPO_FRASE = ((re.compile(r"nome do autor era longo demais", re.I), "autor"), (re.compile(r"o campo IPTC (\S+) era longo demais", re.I), "campo"),
                (re.compile(r"etiqueta de metadados veio repetida", re.I), "repetida"))


def _grupo(texto: str, regras) -> tuple:
    for rx, k in regras:
        m = rx.search(texto or "")
        if m:
            return (k, m.group(1)) if k == "campo" else (k, None)
    return ("outro", None)


def _frase_grupo(chave: tuple, n: int) -> str:
    tem = "imagem tem" if n == 1 else "imagens têm"
    k, campo = chave
    if k == "autor":
        return f"{n} {tem} o nome do autor longo demais no EXIF; ele foi cortado"
    if k == "campo":
        return f"{n} {tem} o campo {campo} longo demais no EXIF; ele foi cortado"
    if k == "repetida":
        return f"{n} {tem} uma etiqueta de metadados repetida no EXIF"
    return f"{n} {'aviso menor' if n == 1 else 'avisos menores'} do exiftool (o programa que grava os dados dentro do arquivo)"


def _juntar(contagem: dict) -> str | None:
    if not contagem:
        return None
    partes = [_frase_grupo(k, n) for k, n in contagem.items()]
    t = "; ".join(partes)
    return t[0].upper() + t[1:] + ". Não impede publicar."


def resumo_avisos(avisos: list[dict] | None) -> str | None:
    """UX-08: os avisos [Minor] (crus, de avisos_menores) numa frase só, contando as imagens por tipo de aviso."""
    cont: dict = {}
    for a in avisos or []:
        k = _grupo(a.get("msg") or "", _GRUPO_MSG)
        cont[k] = cont.get(k, 0) + 1
    return _juntar(cont)


def resumo_descricoes(descricoes: list[str] | None) -> str | None:
    """UX-08: o mesmo resumo a partir dos problemas 'aviso' já gravados nas folhas (descricao de registrar)."""
    cont: dict = {}
    for d in descricoes or []:
        k = _grupo(d or "", _GRUPO_FRASE)
        cont[k] = cont.get(k, 0) + 1
    return _juntar(cont)


_EXIF_PARCIAL = re.compile(r"EXIF conferido em (\d+) de (\d+)", re.I)


def _arquivos_em(fontes) -> list[dict]:
    """Se o CAMP Vision mandou a lista dos arquivos (qualquer chave com "exif" no nome cujo valor é uma lista), devolve-a como
    [{arquivo, motivo}]. O contrato não exige essa lista: sem ela, a tela diz que o CAMP Vision não informou quais faltaram."""
    out = []
    for f in fontes or []:
        if not isinstance(f, dict):
            continue
        for k, v in f.items():
            if "exif" not in str(k).lower() or not isinstance(v, list):
                continue
            for x in v[:500]:
                if isinstance(x, dict):
                    arq = str(x.get("arquivo") or x.get("nome") or x.get("codigo") or "").strip()
                    mot = str(x.get("motivo") or x.get("erro") or x.get("mensagem") or "").strip()
                else:
                    arq, mot = str(x).strip(), ""
                if arq:
                    out.append({"arquivo": arq[:200], "motivo": mot[:300] or None})
    return out


def explicar_erro(texto, fontes=None) -> dict | None:
    """UX-08: o erro que o CAMP Vision deixou, em linguagem de gente. Devolve {tipo, texto, o_que_fazer, detalhes, arquivos}
    ou None (sem mensagem). tipo: 'aviso_menor' (só [Minor] do exiftool) | 'exif_parcial' ("EXIF conferido em 6 de 48") | 'erro' (o resto,
    mostrado como veio). 'detalhes' é a mensagem técnica inteira, para "Ver detalhes técnicos". Só leitura: não muda o lote."""
    t = str(texto or "").strip()
    if not t:
        return None
    detalhes = t[:4000]
    av = avisos_menores(t)
    if av:
        return {"tipo": "aviso_menor", "texto": resumo_avisos(av), "detalhes": detalhes, "arquivos": [],
                "o_que_fazer": "O CAMP Vision ainda não entregou as folhas desta pasta. Peça para ler de novo esta pasta."}
    m = _EXIF_PARCIAL.search(t)
    if m:
        feito, total = int(m.group(1)), int(m.group(2))
        falta = max(total - feito, 0)
        arqs = _arquivos_em(fontes)
        return {"tipo": "exif_parcial", "detalhes": detalhes, "arquivos": arqs,
                "texto": f"O CAMP Vision conferiu os dados gravados dentro dos arquivos (EXIF) de só {feito} de {total} arquivos; "
                         f"{falta} {'ficou' if falta == 1 else 'ficaram'} sem conferir."
                         + ("" if arqs else " Ele não informou quais arquivos nem o motivo."),
                "o_que_fazer": "Peça para ler de novo esta pasta. Se o número não mudar, avise quem cuida do CAMP Vision."}
    return {"tipo": "erro", "texto": " ".join(t.split())[:240], "detalhes": detalhes if len(t) > 240 else None, "arquivos": [],
            "o_que_fazer": "Peça para ler de novo esta pasta. Se o erro voltar, avise quem cuida do CAMP Vision."}


def avisos_abertos(con, projeto: str) -> list[dict]:
    """Os avisos menores do CAMP Vision ainda não vistos deste projeto (para a página: 'Marcar como visto')."""
    return [dict(r) for r in con.execute("""SELECT id, codigo, descricao FROM erro WHERE chave LIKE ? AND situacao IN ('aberto','em_correcao')
                                             AND (codigo=? OR codigo LIKE ?) ORDER BY id""", (CHAVE + "%", projeto, projeto + "-%"))]


def resumo_avisos_cv(con, projeto: str, abertos: list[dict] | None = None) -> dict | None:
    """UX-08 (campo novo, opcional, só da tela): {texto, detalhes} dos avisos menores ainda não vistos do projeto. 'texto' conta as imagens por
    tipo; 'detalhes' são as linhas cruas do exiftool que o CAMP Vision deixou nos lotes do projeto (para "Ver detalhes técnicos")."""
    abertos = avisos_abertos(con, projeto) if abertos is None else abertos
    if not abertos:
        return None
    linhas = []
    for (res,) in con.execute("SELECT resultado FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL ORDER BY id DESC", (projeto,)):
        for a in avisos_menores(motivo_completo(res)) or []:
            ln = f"{a['arquivo']} Warning: [Minor] {a['msg']}".strip()
            if ln not in linhas:
                linhas.append(ln)
    return {"texto": resumo_descricoes([a.get("descricao") or "" for a in abertos]), "detalhes": "\n".join(linhas[:200]) or None}
