"""Fotos enviadas pelo painel vão para o QNAP na hora e o CAMP Vision as lê e legenda (28/10/2026).

Pedido (Rafael): "subi fotos pelo próprio painel, ele tem que enviar na HORA para o QNAP na pasta certa" e "devia automaticamente já
mandar, quando terminar de enviar pro QNAP, para ler elas e já legendar como faz com todas".

Antes (21/10) o arquivo ficava só numa pasta do painel (folhas_enviadas.py). Agora, logo depois do envio (em segundo plano, nunca dentro
da requisição), o painel:
1. grava o arquivo na pasta do projeto no acervo (qnap.prontos_raiz), no padrão do CAMP Vision:
   <F0xx - Fundo>/01 - Projetos/<F0xx-P0yyy - Nome>/<série>/<FORMATO>/<código>.<ext> (original + JPG quando o original não é JPG).
   A pasta do projeto é achada pelo código; se não existe, é criada com "<código> - <título>" (como o CAMP Vision cria);
2. pede ao CAMP Vision a releitura DESTA folha (pedido_releitura de folha, como o botão "Ler dados agora");
3. quando a releitura volta (rotas_releitura.concluido), aplica_leitura() preenche a folha com o que foi lido (título, tipo, folha,
   escala, ano, o que o carimbo diz), SÓ se a folha ainda está "para conferir" (nunca sobrescreve o que uma pessoa revisou).
O código D90001+ é a faixa do painel: o CAMP Vision não numera a partir dela (campvision-new, estrutura.FAIXA_PAINEL).
Se o QNAP não responde, a folha fica com "qnap_pendente" e a coleta do QNAP (qnap_coletor, em segundo plano) tenta de novo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from .db import connect

FAIXA_PAINEL = 90000
PASTA_PROJETOS = "01 - Projetos"
SERIES = {"S01": "01 - Desenhos e pranchas", "S02": "02 - Documentos textuais", "S03": "03 - Fotografias", "S04": "04 - Negativos",
          "S05": "05 - Slides", "S06": "06 - Materiais e especificações", "S07": "07 - Publicações", "S08": "08 - Redesenhos",
          "S99": "99 - Não identificado"}
FORMATO = {".tif": "TIF", ".tiff": "TIF", ".jpg": "JPG", ".jpeg": "JPG", ".png": "PNG"}
MOTIVO_RELEITURA = "foto enviada pelo painel: ler e legendar"
_RE_D = re.compile(r"-D(\d{5})$")


def e_do_painel(codigo: str) -> bool:
    m = _RE_D.search(codigo or "")
    return bool(m) and int(m.group(1)) > FAIXA_PAINEL


def _limpar(nome: str, limite: int = 110) -> str:
    t = re.sub(r'[\\/:*?"<>|]+', " ", str(nome or "")).strip()
    return " ".join(t.split())[:limite].rstrip(" .")


def _raiz(con) -> Path | None:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='qnap.prontos_raiz'").fetchone()
    return Path(r[0]) if r and r[0] else None


def pasta_do_projeto(raiz: Path, fundo: str, codigo: str, titulo: str | None, criar: bool = True) -> Path:
    """A pasta do projeto no acervo (pelo código). Levanta FileNotFoundError se o QNAP/fundo não está acessível."""
    if not raiz.is_dir():
        raise FileNotFoundError(f"a pasta do acervo ({raiz}) não está acessível: o QNAP está montado?")
    fundos = sorted(p for p in raiz.iterdir() if p.is_dir() and p.name.upper().startswith(fundo.upper()))
    if not fundos:
        raise FileNotFoundError(f"a pasta do fundo {fundo} não existe no acervo")
    for pf in fundos:
        base = pf / PASTA_PROJETOS
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_dir() and re.match(rf"^{re.escape(codigo)}\b", p.name, re.I):
                    return p
    if not criar:
        raise FileNotFoundError(f"a pasta do projeto {codigo} não existe no acervo")
    nova = fundos[0] / PASTA_PROJETOS / _limpar(f"{codigo} - {titulo}" if titulo else codigo)
    nova.mkdir(parents=True, exist_ok=True)
    return nova


def _copiar(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    shutil.copyfile(origem, tmp)
    if tmp.stat().st_size != origem.stat().st_size:
        tmp.unlink(missing_ok=True)
        raise OSError(f"a cópia de {origem.name} chegou incompleta ao QNAP")
    os.replace(tmp, destino)


def _pend(row) -> dict:
    try:
        return json.loads(row["pendencias"] or "{}") or {}
    except (ValueError, TypeError):
        return {}


def enviar(codigo: str, ator: str) -> dict:
    """Grava a folha enviada pelo painel na pasta do projeto no QNAP e pede a releitura dela. Nunca levanta: devolve {ok, ...}."""
    con = connect()
    try:
        i = con.execute("""SELECT i.*, p.fundo_codigo, p.titulo AS projeto_titulo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
                           WHERE i.codigo=?""", (codigo,)).fetchone()
        if not i or not e_do_painel(codigo):
            return {"ok": False, "erro": "não é uma folha enviada pelo painel"}
        pend = _pend(i)
        try:
            raiz = _raiz(con)
            if not raiz:
                raise FileNotFoundError("a pasta do acervo no QNAP não está configurada (qnap.prontos_raiz)")
            pasta = pasta_do_projeto(raiz, i["fundo_codigo"], i["projeto_codigo"], i["projeto_titulo"])
            serie_dir = pasta / SERIES.get(i["serie_codigo"], SERIES["S99"])
            arquivos = []
            for cam in dict.fromkeys(x for x in (i["arquivo_tif"], i["arquivo_jpg"]) if x):
                o = Path(cam)
                if not o.is_file():
                    raise FileNotFoundError(f"o arquivo enviado não está mais no painel ({o.name})")
                ext = o.suffix.lower()
                d = serie_dir / FORMATO.get(ext, ext.lstrip(".").upper()) / f"{codigo}{'.jpg' if ext == '.jpeg' else ext}"
                _copiar(o, d)
                arquivos.append(str(d))
        except Exception as e:  # noqa: BLE001
            ant = pend.get("qnap_pendente") or {}
            pend["qnap_pendente"] = {"erro": str(e)[:240], "tentativas": int(ant.get("tentativas") or 0) + 1}
            con.execute("UPDATE item SET pendencias=? WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
            con.commit()
            return {"ok": False, "erro": str(e)[:240]}
        pend.pop("qnap_pendente", None)
        pend["qnap"] = {"pasta_projeto": str(pasta), "arquivos": arquivos}
        con.execute("UPDATE item SET pendencias=?, atualizado_em=datetime('now') WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), codigo))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_gravada_no_qnap',?,?)",
                    (codigo, ator, json.dumps({"arquivos": arquivos}, ensure_ascii=False)))
        # Fotos enviadas antes desta mudança entravam "conferidas" por quem enviou. Se ninguém mexeu nelas depois (o título ainda é o do nome
        # do arquivo e não estão no site), voltam para conferir, para a leitura do CAMP Vision poder preenchê-las como as outras.
        env = pend.get("enviada_pelo_painel") or {}
        from .folhas_enviadas import titulo_do_nome
        if (i["revisao"] == "conferida" and i["status_site"] not in ("rascunho", "no_ar") and env.get("por") and i["revisado_por"] == env.get("por")
                and (i["titulo"] or "") == (titulo_do_nome(env.get("arquivo") or "") or "")):
            con.execute("UPDATE item SET revisao='pendente', revisado_por=NULL, revisado_em=NULL WHERE codigo=?", (codigo,))
        pedido = None
        if not con.execute("SELECT 1 FROM pedido_releitura WHERE projeto_codigo=? AND estado IN ('pedido','em_andamento') AND (item_codigo IS NULL OR item_codigo=?)",
                           (i["projeto_codigo"], codigo)).fetchone():
            pedido = con.execute("INSERT INTO pedido_releitura (projeto_codigo, item_codigo, motivo, pedido_por) VALUES (?,?,?,?)",
                                 (i["projeto_codigo"], codigo, MOTIVO_RELEITURA, ator)).lastrowid
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'releitura_pedida',?,?)",
                        (codigo, ator, json.dumps({"pedido": pedido, "motivo": MOTIVO_RELEITURA}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "arquivos": arquivos, "pedido_releitura": pedido}
    finally:
        con.close()


def pendentes(con, limite: int = 20) -> list[str]:
    """Folhas do painel que ainda não estão no QNAP (nunca tentadas ou que falharam)."""
    return [r[0] for r in con.execute(f"""SELECT codigo FROM item WHERE origem='manual' AND sequencial>{FAIXA_PAINEL} AND duplicata_de IS NULL
                                            AND (pendencias IS NULL OR NOT json_valid(pendencias) OR json_extract(pendencias,'$.qnap') IS NULL)
                                          ORDER BY criado_em LIMIT ?""", (limite,))]


def enviar_pendentes(ator: str = "painel") -> int:
    """A coleta do QNAP (segundo plano) chama: tenta de novo o que não chegou ao QNAP. Devolve quantas foram."""
    con = connect()
    try:
        cods = pendentes(con)
    finally:
        con.close()
    return sum(1 for c in cods if enviar(c, ator).get("ok"))


def aplicar_leitura(con, codigo: str) -> dict | None:
    """Releitura da folha do painel concluída: o CAMP Vision regravou o pacote do projeto. Preenche a folha com o que foi lido, SÓ se ela
    ainda está para conferir; campo lido vazio não apaga o que já há. Não faz commit. Devolve o que mudou (ou None)."""
    i = con.execute("SELECT * FROM item WHERE codigo=?", (codigo,)).fetchone()
    if not i or not e_do_painel(codigo):
        return None
    pend = _pend(i)
    pasta = (pend.get("qnap") or {}).get("pasta_projeto")
    if not pasta:
        return {"aplicado": False, "motivo": "a folha não está no QNAP"}
    from .importador_lote import ler_pacote, tipo_do_painel
    try:
        pacote = ler_pacote(Path(pasta)) or {}
    except Exception:  # noqa: BLE001
        pacote = {}
    docs = [d for d in (pacote.get("documentos") or []) + (pacote.get("retirados") or []) if isinstance(d, dict)]
    d = next((x for x in docs if str(x.get("codigo") or "").upper() == codigo.upper()), None)
    if not d:
        return {"aplicado": False, "motivo": "o pacote do CAMP Vision não trouxe esta folha"}
    if i["revisao"] != "pendente":
        return {"aplicado": False, "motivo": "a folha já foi revisada por uma pessoa: nada foi trocado"}
    tipos = {n.lower(): n for (n,) in con.execute("SELECT nome FROM tipo_documento")}
    tipo_lido = str(d.get("tipo_de_desenho") or d.get("tipo") or "").strip()
    ano = str(d.get("ano") or "").strip()
    carimbo = d.get("carimbo") if isinstance(d.get("carimbo"), dict) else {}
    novos = {"titulo": (d.get("titulo") or "").strip() or None, "tipo_documento": tipo_do_painel(tipo_lido, tipos) if tipo_lido else None,
             "tipo_lido": tipo_lido or None, "folha": str(d.get("folha") or "").strip() or None, "escala": str(d.get("escala") or "").strip() or None,
             "ano_folha": int(ano) if ano.isdigit() and 1800 <= int(ano) <= 2100 else None,
             "projeto_carimbo": str(carimbo.get("obra") or "").strip() or None, "autor_carimbo": str(carimbo.get("arquiteto") or "").strip() or None}
    mudou = {k: v for k, v in novos.items() if v not in (None, "") and v != i[k]}
    lido = {k: novos[k] for k in ("titulo", "tipo_documento", "folha", "escala", "ano_folha")}
    lido.update({"carimbo": carimbo or None, "leitura": d.get("lido") if isinstance(d.get("lido"), dict) else None})
    pend["titulo_lido"] = d.get("titulo_lido") or pend.get("titulo_lido") or ""
    pend["ressalvas"] = list(d.get("ressalvas") or [])
    sets = {**mudou, "lido_json": json.dumps(lido, ensure_ascii=False), "pendencias": json.dumps(pend, ensure_ascii=False)}
    con.execute("UPDATE item SET " + ", ".join(f"{k}=?" for k in sets) + ", atualizado_em=datetime('now') WHERE codigo=?", (*sets.values(), codigo))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'foto_lida_pelo_cv',?,?)",
                (codigo, "campvision", json.dumps({"campos": sorted(mudou)}, ensure_ascii=False)))
    return {"aplicado": True, "campos": sorted(mudou)}
