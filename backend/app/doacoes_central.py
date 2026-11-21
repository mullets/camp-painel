"""Central de cada doação de acervo (CAMP-DOA-CENTRAL, 21/11/2026). Rafael: "Acho que deveria ficar listado lá como doações de acervo, né?
Pra eu poder ver … ir lá e tomar decisões … ter controle total sobre o acervo. Status, o que já aconteceu, o que não aconteceu, informações
internas e etc. Que nem agora esse do Cassol que foi assinado, eu preciso deixar claro que vamos cotar frete, comprar insumo para embalar e etc."

Tudo aqui é INTERNO do painel (o contrato com o site não muda; só admin e master, como a tela):
- Linha de etapas (`passos`): de "Intenção recebida" a "Fundo criado", cada passo feito (com data), o próximo, pendente ou pulado. As datas
  vêm do registro do site (aprovada_em, contrato_enviado_em, assinado_em, cobrança/pago_em, histórico "etapa A → B") e do painel (fundo).
- Próximos passos (`doacao_tarefa`): título, responsável, prazo, situação, valor (R$) e nota; "Usar roteiro de logística" põe a lista padrão
  (frete, insumos de embalagem, retirada, embalar, transporte, conferir, higienização, catalogação) sem repetir títulos. Com o contrato
  assinado (ou a contribuição paga) e nenhuma tarefa, a tela sugere o roteiro (não insere sozinha). Soma os custos previstos e os feitos.
- Arquivos (`doacao_anexo`): orçamento, nota fiscal, foto, contrato… (PDF, JPG, PNG, WEBP, XLSX, DOCX; até 15 MB; tipo conferido pela
  extensão E pelos primeiros bytes). Ficam na pasta ao lado do banco (doacoes_anexos/<site_id>/; CAMP_DOACOES_ANEXOS_DIR muda), nunca no repo.
- Contrato assinado: quando a Autentique diz que todos assinaram, o painel baixa o PDF assinado (`files { signed }`) e guarda como arquivo
  "Contrato assinado" (uma vez por documento: origem 'autentique:<id>'). "Baixar contrato assinado agora" faz o mesmo para os já assinados.
- Histórico único (`linha_do_tempo`): histórico e notas do site, e-mails, Autentique, tarefas, arquivos e o fundo, do mais novo ao mais antigo.
- LGPD (apagar pessoa): os NOMES dos arquivos e o detalhe dos eventos de arquivo viram "(removido)"; os arquivos e as tarefas (custos) ficam,
  porque são o registro do que a CAMP fez e pagou (o contrato assinado é documento da doação). Ver docs/COMO_FUNCIONA.md.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, autentique as aut
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/doacoes-acervo", tags=["doacoes_acervo"])

BR = ZoneInfo("America/Sao_Paulo")
SITUACOES = {"a_fazer": "A fazer", "fazendo": "Fazendo", "feita": "Feita", "nao_se_aplica": "Não se aplica"}
ABERTA = ("a_fazer", "fazendo")
ROTEIRO = ["Cotar frete", "Comprar insumos de embalagem", "Agendar retirada/visita de embalagem", "Embalar o acervo", "Transporte",
           "Receber e conferir na CAMP", "Higienização/acondicionamento", "Catalogação inicial"]
TIPOS_ANEXO = {"contrato_assinado": "Contrato assinado", "contrato": "Contrato (minuta ou outro)", "orcamento": "Orçamento",
               "nota_fiscal": "Nota fiscal ou recibo", "foto": "Foto", "documento": "Outro documento"}
MAX_ANEXO = 15 * 1024 * 1024
EXT_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
PASSOS = [("recebida", "Intenção recebida"), ("em_analise", "Em análise"), ("visita", "Visita"), ("aprovada", "Aprovada"),
          ("contrato_enviado", "Contrato enviado"), ("contrato_assinado", "Contrato assinado"), ("cobranca", "Cobrança enviada"),
          ("paga", "Contribuição paga"), ("recebido", "Acervo recebido"), ("fundo", "Fundo criado")]
# posição de cada etapa do site na linha (info = ainda em análise)
POS = {"em_analise": 1, "info": 1, "visita": 2, "aprovada": 3, "contrato_enviado": 4, "contrato_assinado": 5, "cobranca": 6, "paga": 7, "recebido": 8}
PROXIMO = {"em_analise": "Analisar a proposta", "visita": "Visitar o acervo", "aprovada": "Decidir a aprovação", "contrato_enviado": "Enviar o contrato",
           "contrato_assinado": "Aguardar a assinatura do contrato", "cobranca": "Gerar a cobrança", "paga": "Aguardar o pagamento",
           "recebido": "Receber o acervo", "fundo": "Criar o fundo"}
FINAIS = ("recebido", "nao_aprovada", "arquivada")
RE_LOG = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC · (.*)$", re.S)
RE_ETAPA = re.compile(r"etapa (.+?) → (.+)$")
SISTEMA = ("confirmação ao proponente", "e-mail", "contribuição paga", "intenção recebida", "dados pessoais", "amigo da camp", "não consegui", "cobrança")


# ---------------------------------------------------------------- utilidades
def pasta_anexos() -> Path:
    p = Path(os.environ.get("CAMP_DOACOES_ANEXOS_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "doacoes_anexos")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hoje() -> str:
    return datetime.now(BR).strftime("%Y-%m-%d")


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _ev(con, sid: int, tipo: str, ator: str, det: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,?,?,?)",
                (str(int(sid)), tipo, ator, json.dumps(det, ensure_ascii=False)))


def _ator(u: dict) -> str:
    return _txt((u or {}).get("email") or (u or {}).get("nome") or "painel", 120)


def _existe(con, sid: int):
    r = con.execute("SELECT * FROM doacao_acervo WHERE site_id=?", (int(sid),)).fetchone()
    if not r:
        raise HTTPException(404, "Intenção de doação não encontrada no painel")
    return r


def _iso_utc(s: str) -> str:
    """'AAAA-MM-DD HH:MM[:SS]' (UTC, do sqlite ou do histórico do site) ou ISO → 'AAAA-MM-DDTHH:MM:SSZ'."""
    s = str(s or "").strip()
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nota_utc(em: str) -> str:
    """A data da nota do site ('dd/mm/AAAA HH:MM', horário de Brasília) → ISO UTC."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2})", str(em or ""))
    if not m:
        return ""
    d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=BR)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dia(iso: str) -> str:
    """ISO (UTC ou com fuso) ou AAAA-MM-DD → AAAA-MM-DD no horário de Brasília."""
    s = str(iso or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    u = _iso_utc(s)
    if not u:
        return ""
    return datetime.fromisoformat(u.replace("Z", "+00:00")).astimezone(BR).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- linha de etapas
def _datas(d: dict, fundo: dict | None) -> dict:
    """A primeira data de cada passo, juntando campos do registro, o histórico do site e o painel."""
    from .doacoes_acervo import ETAPAS
    por_nome = {v: k for k, v in ETAPAS.items()}
    out: dict[str, str] = {}

    def pos(k, v):
        v = _dia(v)
        if v and (k not in out or v < out[k]):
            out[k] = v
    pos("recebida", d.get("recebida_em"))
    pos("aprovada", d.get("aprovada_em"))
    pos("contrato_enviado", d.get("contrato_enviado_em"))
    pos("contrato_assinado", d.get("assinado_em"))
    cob = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else None
    if cob and cob.get("pago_em"):
        pos("paga", cob.get("pago_em"))
    for h in d.get("historico") or []:
        m = RE_LOG.match(str(h))
        if not m:
            continue
        quando, msg = m.group(1), m.group(2)
        me = RE_ETAPA.search(msg)
        if me and por_nome.get(me.group(2).strip()):
            k = por_nome[me.group(2).strip()]
            pos("em_analise" if k == "info" else k, quando)
        elif "contrato enviado para assinatura" in msg:
            pos("contrato_enviado", quando)
        elif "cobrança aberta no Mercado Pago" in msg:
            pos("cobranca", quando)
        elif msg.startswith("contribuição paga"):
            pos("paga", quando)
    if fundo and fundo.get("criado_em"):
        pos("fundo", fundo.get("criado_em"))
    return out


def passos(d: dict, fundo: dict | None = None) -> dict:
    """{passos: [{chave, nome, estado (feito|atual|pendente|pulado), data}], proximo: frase ou ""}."""
    etapa = str(d.get("etapa") or "em_analise")
    datas = _datas(d, fundo)
    cob = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else None
    evid = set(datas)
    if cob:
        evid.add("cobranca")
        if cob.get("situacao") == "paga":
            evid.add("paga")
    if fundo or re.fullmatch(r"F\d{3}", str(d.get("fundo") or "").upper()):
        evid.add("fundo")
    p = POS.get(etapa)
    out = []
    for i, (k, nome) in enumerate(PASSOS):
        if k == "recebida":
            est = "feito"
        elif k == "em_analise" and etapa in ("em_analise", "info"):
            est = "atual"
            if etapa == "info":
                nome = "Em análise · aguardando informações"
        elif k in evid:
            est = "feito"
        elif p is not None and i <= p:
            est = "pulado" if k == "visita" else "feito"
        else:
            est = "pendente"
        out.append({"chave": k, "nome": nome, "estado": est, "data": datas.get(k, "")})
    if etapa in ("nao_aprovada", "arquivada"):
        for x in out:
            if x["estado"] in ("pendente", "atual"):
                x["estado"] = "pulado"
        from .doacoes_acervo import ETAPAS
        out.append({"chave": etapa, "nome": ETAPAS.get(etapa, etapa), "estado": "feito", "data": ""})
        return {"passos": out, "proximo": ""}
    if not any(x["estado"] == "atual" for x in out):
        for x in out:
            if x["estado"] == "pendente":
                x["estado"] = "atual"
                break
    at = next((x for x in out if x["estado"] == "atual"), None)
    return {"passos": out, "proximo": PROXIMO.get(at["chave"], at["nome"]) if at else ""}


# ---------------------------------------------------------------- tarefas
def _tarefa(r) -> dict:
    hoje = _hoje()
    return {"id": r["id"], "titulo": r["titulo"], "responsavel": r["responsavel"] or "", "prazo": r["prazo"] or "", "situacao": r["situacao"],
            "situacao_nome": SITUACOES.get(r["situacao"], r["situacao"]), "valor": r["valor"], "nota": r["nota"] or "",
            "atrasada": bool(r["prazo"] and r["prazo"] < hoje and r["situacao"] in ABERTA),
            "criado_em": r["criado_em"], "criado_por": r["criado_por"] or "", "alterado_em": r["alterado_em"], "alterado_por": r["alterado_por"] or ""}


def tarefas(con, sid: int) -> list[dict]:
    try:
        rows = con.execute("SELECT * FROM doacao_tarefa WHERE site_id=? ORDER BY ordem, id", (int(sid),)).fetchall()
    except Exception:  # noqa: BLE001  (banco sem a migração 238)
        return []
    return [_tarefa(r) for r in rows]


def totais(ts: list[dict]) -> dict:
    vale = [t for t in ts if t["situacao"] != "nao_se_aplica"]
    previsto = round(sum(t["valor"] or 0 for t in vale), 2)
    feito = round(sum(t["valor"] or 0 for t in vale if t["situacao"] == "feita"), 2)
    return {"total": len(ts), "feitas": sum(1 for t in ts if t["situacao"] == "feita"), "abertas": sum(1 for t in ts if t["situacao"] in ABERTA),
            "atrasadas": sum(1 for t in ts if t["atrasada"]), "custo_previsto": previsto, "custo_feito": feito, "custo_a_fazer": round(previsto - feito, 2)}


def resumo_tarefas(con) -> dict:
    """Para a lista: {site_id: {abertas, atrasadas}} numa consulta só."""
    hoje = _hoje()
    try:
        rows = con.execute("""SELECT site_id, SUM(situacao IN ('a_fazer','fazendo')) AS abertas,
                                     SUM(situacao IN ('a_fazer','fazendo') AND prazo IS NOT NULL AND prazo<>'' AND prazo<?) AS atrasadas
                              FROM doacao_tarefa GROUP BY site_id""", (hoje,)).fetchall()
    except Exception:  # noqa: BLE001
        return {}
    return {int(r["site_id"]): {"abertas": int(r["abertas"] or 0), "atrasadas": int(r["atrasadas"] or 0)} for r in rows}


class Tarefa(BaseModel):
    titulo: str | None = None
    responsavel: str | None = None
    prazo: str | None = None
    situacao: str | None = None
    valor: str | float | None = None
    nota: str | None = None


def _validar(b: Tarefa, nova: bool) -> dict:
    out, erros = {}, []
    if b.titulo is not None or nova:
        t = _txt(b.titulo, 160)
        if len(t) < 2:
            erros.append("Escreva o que precisa ser feito (título).")
        out["titulo"] = t
    if b.responsavel is not None:
        out["responsavel"] = _txt(b.responsavel, 120) or None
    if b.prazo is not None:
        pz = str(b.prazo).strip()
        if pz and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pz):
            erros.append("Prazo: use uma data (dia/mês/ano).")
        out["prazo"] = pz or None
    if b.situacao is not None:
        if b.situacao not in SITUACOES:
            erros.append("Situação: a fazer, fazendo, feita ou não se aplica.")
        out["situacao"] = b.situacao
    if b.valor is not None:
        v = str(b.valor).strip().replace("R$", "").strip()
        if v in ("", "__limpar__"):
            out["valor"] = None
        else:
            if "," in v:
                v = v.replace(".", "").replace(",", ".")
            try:
                f = round(float(v), 2)
                if f < 0 or f > 10_000_000:
                    raise ValueError
                out["valor"] = f
            except ValueError:
                erros.append("Valor: um número em reais (ex.: 1.250,00).")
    if b.nota is not None:
        out["nota"] = str(b.nota or "").strip()[:2000] or None
    if erros:
        raise HTTPException(400, " ".join(erros))
    return out


def _completo(con, sid: int) -> dict:
    from .doacoes_acervo import _completo as det
    return det(con, int(sid))


@router.post("/{sid}/tarefas")
def tarefa_criar(sid: int, b: Tarefa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _existe(con, sid)
        c = _validar(b, True)
        ordem = (con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM doacao_tarefa WHERE site_id=?", (sid,)).fetchone()[0])
        ator = _ator(u)
        cur = con.execute("""INSERT INTO doacao_tarefa (site_id, titulo, responsavel, prazo, situacao, valor, nota, ordem, criado_por, alterado_por)
                             VALUES (?,?,?,?,?,?,?,?,?,?)""", (sid, c["titulo"], c.get("responsavel"), c.get("prazo"), c.get("situacao") or "a_fazer",
                                                             c.get("valor"), c.get("nota"), ordem, ator, ator))
        _ev(con, sid, "tarefa_criada", ator, {"tarefa": cur.lastrowid, "titulo": c["titulo"]})
        con.commit()
        return _completo(con, sid)
    finally:
        con.close()


@router.post("/{sid}/tarefas/roteiro")
def tarefa_roteiro(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Põe o roteiro de logística, sem repetir o que já existe (pelo título, sem acento e sem caixa)."""
    from .doacoes_acervo import _norm
    con = connect()
    try:
        _existe(con, sid)
        tem = {_norm(r[0]) for r in con.execute("SELECT titulo FROM doacao_tarefa WHERE site_id=?", (sid,))}
        ordem = con.execute("SELECT COALESCE(MAX(ordem),0) FROM doacao_tarefa WHERE site_id=?", (sid,)).fetchone()[0]
        ator, novas = _ator(u), []
        for t in ROTEIRO:
            if _norm(t) in tem:
                continue
            ordem += 1
            con.execute("INSERT INTO doacao_tarefa (site_id, titulo, ordem, criado_por, alterado_por) VALUES (?,?,?,?,?)", (sid, t, ordem, ator, ator))
            novas.append(t)
        if novas:
            _ev(con, sid, "tarefa_roteiro", ator, {"titulos": novas})
        con.commit()
        x = _completo(con, sid)
        x["roteiro"] = {"criadas": len(novas), "mensagem": f"Roteiro de logística: {len(novas)} tarefa(s) nova(s)." if novas else "O roteiro de logística já estava todo na lista."}
        return x
    finally:
        con.close()


@router.put("/{sid}/tarefas/{tid}")
def tarefa_mudar(sid: int, tid: int, b: Tarefa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM doacao_tarefa WHERE id=? AND site_id=?", (tid, sid)).fetchone()
        if not r:
            raise HTTPException(404, "Tarefa não encontrada")
        c = _validar(b, False)
        mud = {k: v for k, v in c.items() if r[k] != v}
        if mud:
            ator = _ator(u)
            con.execute(f"UPDATE doacao_tarefa SET {', '.join(k + '=?' for k in mud)}, alterado_em=datetime('now'), alterado_por=? WHERE id=?",
                        (*mud.values(), ator, tid))
            det = {"tarefa": tid, "titulo": c.get("titulo") or r["titulo"], "campos": sorted(mud)}
            if "situacao" in mud:
                det["situacao"] = mud["situacao"]
            _ev(con, sid, "tarefa_alterada", ator, det)
            con.commit()
        return _completo(con, sid)
    finally:
        con.close()


@router.delete("/{sid}/tarefas/{tid}")
def tarefa_apagar(sid: int, tid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM doacao_tarefa WHERE id=? AND site_id=?", (tid, sid)).fetchone()
        if not r:
            raise HTTPException(404, "Tarefa não encontrada")
        con.execute("DELETE FROM doacao_tarefa WHERE id=?", (tid,))
        con.execute("UPDATE doacao_anexo SET tarefa_id=NULL WHERE tarefa_id=?", (tid,))
        _ev(con, sid, "tarefa_apagada", _ator(u), {"tarefa": tid, "titulo": r["titulo"], "valor": r["valor"]})
        con.commit()
        return _completo(con, sid)
    finally:
        con.close()


# ---------------------------------------------------------------- arquivos
def _ext(nome: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", nome or "")
    return m.group(1).lower() if m else ""


def tipo_pelos_bytes(dados: bytes, ext: str) -> bool:
    """Os primeiros bytes batem com a extensão? (não confia só no nome)"""
    if ext == "pdf":
        return dados.startswith(b"%PDF-")
    if ext in ("jpg", "jpeg"):
        return dados.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return dados.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "webp":
        return len(dados) > 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP"
    if ext in ("xlsx", "docx"):
        if not dados.startswith(b"PK\x03\x04"):
            return False
        import io
        import zipfile
        try:
            nomes = zipfile.ZipFile(io.BytesIO(dados)).namelist()
        except Exception:  # noqa: BLE001
            return False
        return any(n.startswith("xl/" if ext == "xlsx" else "word/") for n in nomes)
    return False


def nome_limpo(nome: str, ext: str) -> str:
    base = os.path.basename(str(nome or "").replace("\\", "/"))
    base = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", base)
    base = re.sub(r"[^\w .()\-]", "_", base, flags=re.U).strip(" ._") or "arquivo"
    return f"{base[:100]}.{ext}"


def _anexo(r) -> dict:
    return {"id": r["id"], "tipo": r["tipo"], "tipo_nome": TIPOS_ANEXO.get(r["tipo"], r["tipo"]), "nome": r["nome"], "mime": r["mime"] or "",
            "tamanho": r["tamanho"] or 0, "tarefa_id": r["tarefa_id"], "automatico": str(r["origem"] or "").startswith("autentique:"),
            "criado_em": r["criado_em"], "criado_por": r["criado_por"] or ""}


def anexos(con, sid: int) -> list[dict]:
    try:
        rows = con.execute("SELECT * FROM doacao_anexo WHERE site_id=? ORDER BY tipo='contrato_assinado' DESC, id DESC", (int(sid),)).fetchall()
    except Exception:  # noqa: BLE001  (banco sem a migração 238)
        return []
    return [_anexo(r) for r in rows]


def guardar_anexo(con, sid: int, nome: str, dados: bytes, tipo: str, ator: str, tarefa_id: int | None = None, origem: str = "equipe") -> int:
    """Valida, grava o arquivo e a linha. Não faz commit. Levanta HTTPException(400) com a frase."""
    ext = _ext(nome)
    if ext not in EXT_MIME:
        raise HTTPException(400, "Tipo de arquivo não aceito: PDF, JPG, PNG, WEBP, XLSX ou DOCX.")
    if not dados:
        raise HTTPException(400, "O arquivo chegou vazio: escolha de novo.")
    if len(dados) > MAX_ANEXO:
        raise HTTPException(400, "O arquivo passa de 15 MB: diminua ou divida.")
    if not tipo_pelos_bytes(dados, ext):
        raise HTTPException(400, f"O conteúdo do arquivo não é {ext.upper()} de verdade (a extensão não bate com o arquivo).")
    if tipo not in TIPOS_ANEXO:
        tipo = "documento"
    if tarefa_id is not None and not con.execute("SELECT 1 FROM doacao_tarefa WHERE id=? AND site_id=?", (tarefa_id, sid)).fetchone():
        tarefa_id = None
    sha = hashlib.sha256(dados).hexdigest()
    pasta = pasta_anexos() / str(int(sid))
    pasta.mkdir(parents=True, exist_ok=True)
    nm = nome_limpo(nome, "jpg" if ext == "jpeg" else ext)
    cur = con.execute("INSERT INTO doacao_anexo (site_id, tipo, nome, arquivo, mime, tamanho, sha256, tarefa_id, origem, criado_por) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (int(sid), tipo, nm, "", EXT_MIME[ext], len(dados), sha, tarefa_id, origem, ator))
    aid = cur.lastrowid
    rel = f"{int(sid)}/{aid}-{sha[:12]}.{'jpg' if ext == 'jpeg' else ext}"
    (pasta_anexos() / rel).write_bytes(dados)
    con.execute("UPDATE doacao_anexo SET arquivo=? WHERE id=?", (rel, aid))
    _ev(con, sid, "anexo_adicionado", ator, {"anexo": aid, "nome": nm, "tipo": tipo, "tamanho": len(dados), "automatico": origem != "equipe"})
    return aid


class Anexo(BaseModel):
    nome: str
    base64: str
    tipo: str = "documento"
    tarefa_id: int | None = None


@router.post("/{sid}/anexos")
def anexo_enviar(sid: int, b: Anexo, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _existe(con, sid)
        try:
            dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", b.base64 or "").strip(), validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
        guardar_anexo(con, sid, b.nome, dados, b.tipo, _ator(u), b.tarefa_id)
        con.commit()
        registrar(logging.INFO, "doacao_anexo", "Arquivo anexado à doação de acervo", site_id=int(sid))
        return _completo(con, sid)
    finally:
        con.close()


def _arquivo(con, sid: int, aid: int):
    r = con.execute("SELECT * FROM doacao_anexo WHERE id=? AND site_id=?", (aid, sid)).fetchone()
    if not r:
        raise HTTPException(404, "Arquivo não encontrado")
    return r


@router.get("/{sid}/anexos/{aid}")
def anexo_baixar(sid: int, aid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        r = _arquivo(con, sid, aid)
    finally:
        con.close()
    f = (pasta_anexos() / r["arquivo"]).resolve()
    if not r["arquivo"] or pasta_anexos().resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "O arquivo não está mais na pasta do painel")
    return FileResponse(str(f), media_type=r["mime"] or "application/octet-stream", filename=r["nome"],
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.delete("/{sid}/anexos/{aid}")
def anexo_apagar(sid: int, aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = _arquivo(con, sid, aid)
        con.execute("DELETE FROM doacao_anexo WHERE id=?", (aid,))
        _ev(con, sid, "anexo_apagado", _ator(u), {"anexo": aid, "nome": r["nome"], "tipo": r["tipo"]})
        con.commit()
        try:
            f = (pasta_anexos() / r["arquivo"]).resolve()
            if r["arquivo"] and pasta_anexos().resolve() in f.parents and f.is_file():
                f.unlink()
        except OSError:
            pass
        return _completo(con, sid)
    finally:
        con.close()


# ---------------------------------------------------------------- contrato assinado (Autentique)
def contrato_assinado(con, sid: int) -> dict | None:
    """O arquivo do contrato assinado desta doação (o baixado da Autentique ou um anexado como "Contrato assinado"), se houver."""
    try:
        r = con.execute("SELECT id, nome FROM doacao_anexo WHERE site_id=? AND tipo='contrato_assinado' ORDER BY origem LIKE 'autentique:%' DESC, id DESC LIMIT 1",
                        (int(sid),)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return {"id": r["id"], "nome": r["nome"]} if r else None


def guardar_assinado(con, sid: int, ator: str = "sistema") -> dict:
    """Baixa da Autentique o PDF assinado do documento assinado mais recente e guarda como arquivo (uma vez por documento).
    Levanta aut.ErroAutentique (frase pronta) ou HTTPException."""
    v = con.execute("SELECT * FROM doacao_autentique WHERE site_id=? AND situacao='assinado' ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
    if not v:
        raise HTTPException(409, "Esta doação não tem contrato assinado por todos na Autentique.")
    origem = f"autentique:{v['documento_id']}"
    tem = con.execute("SELECT id, nome FROM doacao_anexo WHERE origem=?", (origem,)).fetchone()
    if tem:
        return {"id": tem["id"], "nome": tem["nome"], "novo": False, "mensagem": "O contrato assinado já estava guardado nos arquivos."}
    tk = aut.token(con)
    _, url = aut.consultar_doc(tk, v["documento_id"])
    if not url:
        raise aut.ErroAutentique("A Autentique ainda não tem o PDF assinado deste documento. Tente de novo mais tarde.")
    pdf = aut.baixar_assinado(tk, url)
    r = con.execute("SELECT protocolo FROM doacao_acervo WHERE site_id=?", (int(sid),)).fetchone()
    nome = f"Contrato assinado {(r['protocolo'] if r and r['protocolo'] else sid)}.pdf"
    sha = hashlib.sha256(pdf).hexdigest()
    pasta = pasta_anexos() / str(int(sid))
    pasta.mkdir(parents=True, exist_ok=True)
    cur = con.execute("INSERT INTO doacao_anexo (site_id, tipo, nome, arquivo, mime, tamanho, sha256, origem, criado_por) VALUES (?,?,?,?,?,?,?,?,?)",
                      (int(sid), "contrato_assinado", nome_limpo(nome, "pdf"), "", "application/pdf", len(pdf), sha, origem, ator))
    aid = cur.lastrowid
    rel = f"{int(sid)}/{aid}-{sha[:12]}.pdf"
    (pasta_anexos() / rel).write_bytes(pdf)
    con.execute("UPDATE doacao_anexo SET arquivo=? WHERE id=?", (rel, aid))
    _ev(con, sid, "anexo_adicionado", ator, {"anexo": aid, "nome": nome_limpo(nome, "pdf"), "tipo": "contrato_assinado", "tamanho": len(pdf), "automatico": True})
    con.commit()
    registrar(logging.INFO, "doacao_contrato_assinado", "Contrato assinado baixado da Autentique", site_id=int(sid))
    return {"id": aid, "nome": nome_limpo(nome, "pdf"), "novo": True, "mensagem": "Contrato assinado baixado da Autentique e guardado nos arquivos."}


def tentar_guardar_assinado(con, sid: int, ator: str = "sistema") -> None:
    """Depois que a Autentique diz "todos assinaram": tenta baixar o PDF. Nunca levanta (falhou → fica o botão "Baixar contrato assinado agora")."""
    try:
        guardar_assinado(con, sid, ator)
    except Exception as e:  # noqa: BLE001
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        registrar(logging.WARNING, "doacao_contrato_assinado", "Não baixei o contrato assinado da Autentique agora", site_id=int(sid), erro=type(e).__name__)


@router.post("/{sid}/contrato-assinado")
def baixar_contrato_agora(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _existe(con, sid)
        try:
            res = guardar_assinado(con, sid, _ator(u))
        except aut.ErroAutentique as e:
            raise HTTPException(502, str(e)) from e
        x = _completo(con, sid)
        x["contrato_baixado"] = res
        return x
    finally:
        con.close()


# ---------------------------------------------------------------- histórico único
CAT_EVENTO = {"email_enviado": "email", "email_falhou": "email", "autentique_criado": "autentique", "autentique_enviado": "autentique",
              "autentique_assinado": "autentique", "autentique_recusado": "autentique", "tarefa_criada": "tarefa", "tarefa_alterada": "tarefa",
              "tarefa_apagada": "tarefa", "tarefa_roteiro": "tarefa", "anexo_adicionado": "anexo", "anexo_apagado": "anexo", "fundo_vinculado": "fundo"}


def _texto_evento(tipo: str, d: dict) -> str:
    sit = SITUACOES.get(str(d.get("situacao") or ""), "")
    if tipo == "email_enviado":
        return "E-mail enviado pelo Sender: " + " · ".join(x for x in (d.get("template"), d.get("nome_modelo") or d.get("modelo"), d.get("etapa_nome")) if x)
    if tipo == "email_falhou":
        return "E-mail não saiu: " + " · ".join(x for x in (d.get("template"), d.get("nome_modelo") or d.get("modelo"), d.get("erro")) if x)
    if tipo == "autentique_criado":
        return "Contrato criado na Autentique"
    if tipo == "autentique_enviado":
        return "Link de assinatura da Autentique enviado (TR30)"
    if tipo == "autentique_assinado":
        return "Contrato assinado por todos na Autentique" + (f" em {d['assinado_em'][8:10]}/{d['assinado_em'][5:7]}/{d['assinado_em'][:4]}" if d.get("assinado_em") else "")
    if tipo == "autentique_recusado":
        return "Alguém recusou o contrato na Autentique"
    if tipo == "tarefa_criada":
        return f"Tarefa criada: {d.get('titulo', '')}"
    if tipo == "tarefa_roteiro":
        return "Roteiro de logística: " + ", ".join(d.get("titulos") or [])
    if tipo == "tarefa_alterada":
        return f"Tarefa {d.get('titulo', '')}: " + (f"agora {sit.lower()}" if sit else "alterada (" + ", ".join(d.get("campos") or []) + ")")
    if tipo == "tarefa_apagada":
        return f"Tarefa apagada: {d.get('titulo', '')}"
    if tipo == "anexo_adicionado":
        return ("Contrato assinado baixado da Autentique: " if d.get("automatico") else "Arquivo anexado: ") + str(d.get("nome") or "")
    if tipo == "anexo_apagado":
        return f"Arquivo apagado: {d.get('nome', '')}"
    if tipo == "fundo_vinculado":
        return f"Fundo {d.get('fundo', '')} " + ("criado" if d.get("fundo_criado") else "vinculado") + " por esta doação"
    return tipo


def linha_do_tempo(con, x: dict) -> list[dict]:
    """[{quando (ISO UTC), categoria (nota|etapa|email|autentique|tarefa|anexo|fundo|site), quem, texto}], do mais novo ao mais antigo."""
    itens = []
    for h in x.get("historico") or []:
        m = RE_LOG.match(str(h))
        if not m:
            continue
        msg = m.group(2)
        if msg.endswith(": nota interna"):
            continue                                      # a nota aparece inteira (abaixo), não só "nota interna"
        m2 = re.match(r"^([^:]{1,60}): (.+)$", msg, re.S)
        if m2 and not m2.group(1).lower().startswith(SISTEMA):
            quem, txt = m2.group(1), m2.group(2)
        else:
            quem, txt = "", msg
        low = txt.lower()
        cat = "etapa" if RE_ETAPA.search(txt) else ("email" if "e-mail" in low or "confirmação ao proponente" in low else "site")
        itens.append({"quando": _iso_utc(m.group(1)), "categoria": cat, "quem": quem, "texto": txt})
    for n in x.get("notas") or []:
        itens.append({"quando": _nota_utc(n.get("em")), "categoria": "nota", "quem": str(n.get("quem") or ""), "texto": str(n.get("texto") or "")})
    try:
        evs = con.execute("SELECT quando, tipo, ator, detalhe FROM evento WHERE entidade='doacao_acervo' AND codigo=? ORDER BY id DESC LIMIT 300",
                          (str(int(x["id"])),)).fetchall()
    except Exception:  # noqa: BLE001
        evs = []
    for e in evs:
        cat = CAT_EVENTO.get(e["tipo"])
        if not cat:
            continue
        try:
            d = json.loads(e["detalhe"] or "{}")
        except ValueError:
            d = {}
        itens.append({"quando": _iso_utc(e["quando"]), "categoria": cat, "quem": str(e["ator"] or ""), "texto": _texto_evento(e["tipo"], d)})
    itens.sort(key=lambda i: i["quando"] or "", reverse=True)
    return itens


# ---------------------------------------------------------------- juntar no detalhe e na lista
def extras(con, x: dict) -> dict:
    """O que a central acrescenta ao detalhe (campos novos, opcionais)."""
    ts = tarefas(con, x["id"])
    ps = passos(x, x.get("fundo_vinculo"))
    assinado = x.get("etapa") in ("contrato_assinado", "paga") or bool(x.get("assinado_em"))
    aut_info = x.get("autentique") or {}
    return {"passos": ps["passos"], "proximo": ps["proximo"], "tarefas": ts, "tarefas_totais": totais(ts), "situacoes_tarefa": SITUACOES,
            "roteiro": ROTEIRO, "sugerir_roteiro": bool(assinado and not ts and x.get("etapa") not in FINAIS),
            "anexos": anexos(con, x["id"]), "tipos_anexo": TIPOS_ANEXO, "max_anexo": MAX_ANEXO,
            "contrato_assinado_arquivo": contrato_assinado(con, x["id"]),
            "pode_baixar_assinado": bool(aut_info.get("situacao") == "assinado" and aut.token(con)),
            "linha_do_tempo": linha_do_tempo(con, x)}


def anonimizar(con, sid: int) -> None:
    """LGPD: nomes dos arquivos e detalhe dos eventos de arquivo viram "(removido)". Os arquivos e as tarefas ficam. Não faz commit."""
    try:
        for r in con.execute("SELECT id, nome FROM doacao_anexo WHERE site_id=?", (int(sid),)).fetchall():
            con.execute("UPDATE doacao_anexo SET nome=? WHERE id=?", (f"arquivo-{r['id']}.{_ext(r['nome']) or 'bin'}", r["id"]))
        con.execute("""UPDATE evento SET detalhe=json_set(COALESCE(detalhe,'{}'), '$.nome', '(removido)')
                       WHERE entidade='doacao_acervo' AND codigo=? AND tipo IN ('anexo_adicionado','anexo_apagado')""", (str(int(sid)),))
    except Exception:  # noqa: BLE001  (banco sem a migração 238)
        pass
