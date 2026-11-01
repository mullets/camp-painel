"""Entrega de pedido de alta resolução por e-mail (01/11/2026).

Rafael: "quando recebemos uma solicitação de envio de material em alta, poder aprovar pelo sistema e já enviar o que ele pediu pelo
próprio sistema". Fluxo:

1. Prévia (`previa`): o que vai no pacote (o arquivo de cada folha pedida, já achado no QNAP), o que fica de fora e o texto do e-mail.
2. Aprovar e enviar (`aprovar_e_enviar`): cria um link de download com prazo (`entrega.validade_dias`), prepara os arquivos e manda
   o e-mail à pessoa. Canal (`entrega.canal`):
   - `sender`: e-mail transacional do Sender.net com o layout pronto (`sender.token` + `sender.campanha_entrega`), com as variáveis
     {{nome}}, {{link}} (o .zip com tudo), {{link_pagina}}, {{tamanho}}, {{validade}}, {{pedido}}, {{quantidade}}, {{lista}}, {{mensagem}};
   - `site`: o e-mail do próprio site (rota `POST /wp-json/camp/v1/painel/pedido/enviar`, que usa o SMTP configurado no site).
   Só depois do envio aceito o pedido vira "entregue". Se o envio falhar, o link é cancelado e nada muda no pedido.
3. Download: o link do e-mail baixa TUDO num .zip (/entrega/<token>/tudo.zip, montado na hora, sem cópia em disco); a página
   /entrega/<token> lista os arquivos um a um. Rotas públicas do painel, sem login, até a validade.

Os arquivos NÃO vão anexados (um TIFF tem centenas de MB). O TIFF e o JPG em resolução original saem direto do QNAP; o JPG de 3000 px
(e o JPG pedido de uma folha que só tem TIFF) é gerado na pasta do painel (`<pasta do banco>/entregas/<link>/`). O token só existe no
e-mail; o banco guarda o hash. Nada do QNAP é apagado ou alterado.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import HTTPException

from .config import settings
from .email_envio import ENDERECO

SENDER_URL = os.environ.get("CAMP_SENDER_URL", "https://api.sender.net/v2")
CANAIS = {"sender": "Sender.net", "site": "e-mail do site"}
LADO_3000 = 3000
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,80}$")


class EnvioErro(Exception):
    """Falha de envio, com mensagem já segura para mostrar (o token nunca aparece)."""


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    v = (r[0] if r and r[0] is not None else "") or ""
    return v.strip() or padrao


def pasta() -> Path:
    p = Path(os.environ.get("CAMP_ENTREGAS_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "entregas")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validade_dias(con) -> int:
    v = _cfg(con, "entrega.validade_dias", "14")
    return max(1, min(90, int(v))) if v.isdigit() else 14


def canal_configurado(con) -> dict:
    """Os canais que funcionam agora e o escolhido em Configurações (cai no outro se o escolhido não está pronto)."""
    sender_ok = bool(_cfg(con, "sender.token") and _cfg(con, "sender.campanha_entrega"))
    site_ok = bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))
    prontos = [c for c, ok in (("sender", sender_ok), ("site", site_ok)) if ok]
    escolhido = _cfg(con, "entrega.canal", "sender")
    if escolhido not in prontos:
        escolhido = prontos[0] if prontos else ""
    return {"canal": escolhido, "prontos": prontos, "rotulos": CANAIS}


# ---------------------------------------------------------------- o que entra no pacote
def _raizes_permitidas(con) -> list[Path]:
    from . import ajuste_imagem, exportacao, folhas_enviadas
    out = []
    for p in (exportacao.raiz_qnap(con), Path(_cfg(con, "qnap.raiz", settings.CAMP_QNAP_ROOT)), pasta(), ajuste_imagem.pasta(), folhas_enviadas.pasta()):
        try:
            out.append(p.resolve())
        except OSError:
            pass
    return out


def _permitido(con, caminho: str | Path) -> Path | None:
    """O arquivo, só se existir e estiver DENTRO do QNAP ou das pastas do painel (o link público nunca serve nada de fora)."""
    try:
        alvo = Path(str(caminho)).resolve()
    except OSError:
        return None
    if not alvo.is_file():
        return None
    return alvo if any(r in alvo.parents for r in _raizes_permitidas(con)) else None


def _jpg_qnap(con, raiz: Path, item) -> Path | None:
    from . import folhas_enviadas
    jpg = item["arquivo_jpg"]
    if not jpg or str(jpg).startswith("http"):
        return None
    if folhas_enviadas.dentro(jpg):
        return folhas_enviadas.dentro(jpg)
    try:
        c = Path(str(jpg))
        alvo = c.resolve() if c.is_absolute() else (raiz / c).resolve()
        if raiz.resolve() in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
            return alvo
    except OSError:
        return None
    return None


def _origem(con, raiz: Path, item, formato: str) -> tuple[Path | None, str, bool]:
    """(arquivo de origem, motivo se não achou, precisa gerar JPG). TIFF: o do QNAP. JPG: o corrigido na revisão (recorte/alinhamento),
    senão o JPG do QNAP, senão gerado do TIFF."""
    from . import ajuste_imagem, exportacao
    if formato == "tif":
        t = exportacao._tif_no_qnap(raiz, item["arquivo_tif"])
        return (t, "", False) if t else (None, "o TIFF não está no QNAP", False)
    if formato in ("jpg_original", "jpg_3000"):
        k = item.keys()
        corr = ajuste_imagem.caminho_gravado(item["imagem_corrigida"]) if "imagem_corrigida" in k else None
        j = corr or _jpg_qnap(con, raiz, item)
        if j:
            return j, "", formato == "jpg_3000"
        t = exportacao._tif_no_qnap(raiz, item["arquivo_tif"])
        return (t, "", True) if t else (None, "nem JPG nem TIFF no QNAP", False)
    return None, "PDF não sai pelo envio automático: mande à parte", False


def montar(con, sid: int) -> dict:
    """O pacote (de rotas_pedidos.pacote) com o arquivo real de cada linha, o tamanho e o que fica de fora."""
    from . import exportacao
    from .rotas_pedidos import FORMATOS, pacote
    p = pacote(con, sid)
    raiz = exportacao.raiz_qnap(con)
    arquivos, fora = [], list(p["faltam"])
    pdf_vistos = set()
    for l in p["linhas"]:
        if l["formato"] == "pdf":            # PDF pedido do projeto inteiro: uma linha só em "fica de fora", não uma por folha
            if l["pedido"] not in pdf_vistos:
                pdf_vistos.add(l["pedido"])
                fora.append({"codigo": l["pedido"], "formato": "pdf", "motivo": "PDF não sai pelo envio automático: mande à parte"})
            continue
        item = con.execute("SELECT * FROM item WHERE codigo=?", (l["codigo"],)).fetchone()
        origem, motivo, gerar = _origem(con, raiz, item, l["formato"]) if item else (None, "folha não encontrada", False)
        if origem is None:
            fora.append({"codigo": l["codigo"], "formato": l["formato"], "motivo": motivo})
            continue
        ext = "tif" if l["formato"] == "tif" else "jpg"
        arquivos.append({"codigo": l["codigo"], "titulo": l["titulo"] or "", "formato": l["formato"], "resolucao": FORMATOS[l["formato"]],
                         "origem": str(origem), "gerar": gerar, "nome": f"{l['codigo']}.{ext}",
                         "tamanho": origem.stat().st_size if not gerar else None})
    return {"pacote": p, "arquivos": arquivos, "fora": fora}


def _gerar_jpg(origem: Path, destino: Path, lado: int | None) -> int:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = None          # folha grande digitalizada em alta passa do limite de "bomba de pixels" do Pillow
    with Image.open(origem) as im:
        im = ImageOps.exif_transpose(im) or im
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if lado and max(im.size) > lado:
            im.thumbnail((lado, lado), Image.LANCZOS)
        tmp = destino.with_suffix(".tmp")
        im.save(tmp, "JPEG", quality=92, optimize=True, subsampling=0)
    os.replace(tmp, destino)
    return destino.stat().st_size


# ---------------------------------------------------------------- texto do e-mail
def _fmt_tamanho(n: int | None) -> str:
    if not n:
        return ""
    return f"{n / 1024 / 1024:.0f} MB".replace(".", ",") if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def _data_br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def link_base(con) -> str:
    return _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")


def textos(con, s, arquivos: list[dict], link_pagina: str, expira_em: str, mensagem: str) -> dict:
    """`link` (o principal, 01/11 Rafael: "o ideal é o link de download ser um zip de todo aquele projeto") baixa tudo num .zip;
    `link_pagina` abre a página com os arquivos um a um."""
    link = f"{link_pagina}/tudo.zip"
    total = sum(a.get("tamanho") or 0 for a in arquivos)
    nome = (s["solicitante"] or "").strip() or "olá"
    primeiro = nome.split()[0]
    lista = "\n".join(f"- {a['codigo']}{' · ' + a['titulo'] if a['titulo'] else ''} ({a['resolucao']})" for a in arquivos)
    validade = _data_br(expira_em)
    assunto = f"CAMP · seu pedido de material em alta resolução (pedido #{s['id']})"
    corpo = (f"Olá, {primeiro},\n\n"
             "Seu pedido de material em alta resolução ao acervo da CAMP foi aprovado.\n\n"
             + (f"{mensagem}\n\n" if mensagem else "")
             + f"Baixe tudo num só arquivo .zip{' (' + _fmt_tamanho(total) + ')' if total else ''}, por este link temporário (vale até {validade}):\n{link}\n\n"
             f"Se preferir baixar arquivo por arquivo:\n{link_pagina}\n\n"
             f"O que está no pacote ({len(arquivos)} arquivo(s)):\n{lista}\n\n"
             "Ao publicar ou expor este material, cite a fonte: Acervo CAMP (camp.arq.br).\n"
             "Se tiver qualquer dúvida, é só responder este e-mail.\n\n"
             "Equipe CAMP\n")
    variaveis = {"nome": primeiro, "nome_completo": nome, "link": link, "link_pagina": link_pagina, "tamanho": _fmt_tamanho(total),
                 "validade": validade, "pedido": str(s["id"]),
                 "quantidade": str(len(arquivos)), "lista": lista, "mensagem": mensagem or ""}
    return {"assunto": assunto, "texto": corpo, "variaveis": variaveis}


# ---------------------------------------------------------------- envio
def _enviar_sender(con, para: str, nome: str, variaveis: dict) -> str:
    token, campanha = _cfg(con, "sender.token"), _cfg(con, "sender.campanha_entrega")
    if not token or not campanha:
        raise EnvioErro("O Sender.net não está configurado (sender.token e sender.campanha_entrega em Configurações)")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", campanha):
        raise EnvioErro("sender.campanha_entrega não parece um ID do Sender.net")
    try:
        r = httpx.post(f"{SENDER_URL}/message/{campanha}/send", timeout=30,
                       headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
                       json={"to": {"email": para, "name": nome}, "variables": variaveis})
    except httpx.HTTPError as e:
        raise EnvioErro(f"Não consegui falar com o Sender.net ({type(e).__name__})")
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    if r.status_code >= 400 or (isinstance(corpo, dict) and corpo.get("success") is False):
        msg = ""
        if isinstance(corpo, dict):
            msg = str(corpo.get("message") or corpo.get("error") or corpo.get("errors") or "")
        raise EnvioErro(f"O Sender.net recusou o envio ({r.status_code}){': ' + msg[:200].replace(token, '***') if msg else ''}")
    return str((corpo.get("data") or {}).get("emailId") or corpo.get("emailId") or "") if isinstance(corpo, dict) else ""


def _enviar_site(con, para: str, nome: str, assunto: str, texto: str, responder: str, pedido_site_id: int | None) -> str:
    from .wp import WP
    try:
        r = WP().enviar_email_pedido(para=para, nome=nome, assunto=assunto, texto=texto, responder_para=responder or None,
                                     pedido_site_id=pedido_site_id)
    except RuntimeError as e:
        raise EnvioErro(str(e)[:240])
    except httpx.HTTPError as e:
        raise EnvioErro(f"Não consegui falar com o site ({type(e).__name__})")
    return str(r.get("id") or "")


def enviar(con, canal: str, para: str, nome: str, t: dict, responder: str, pedido_site_id: int | None) -> str:
    if canal == "sender":
        return _enviar_sender(con, para, nome, t["variaveis"])
    if canal == "site":
        return _enviar_site(con, para, nome, t["assunto"], t["texto"], responder, pedido_site_id)
    raise EnvioErro("Nenhum canal de e-mail configurado: preencha o Sender.net ou a senha do site em Configurações")


# ---------------------------------------------------------------- aprovar e enviar
def _solicitacao(con, sid: int):
    s = con.execute("SELECT * FROM solicitacao WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Pedido não existe")
    return s


def _pedido_site_id(con, sid: int) -> int | None:
    r = con.execute("SELECT site_id FROM pedido_site WHERE destino='solicitacao' AND destino_id=? ORDER BY site_id LIMIT 1", (sid,)).fetchone()
    return int(r[0]) if r else None


def previa(con, sid: int, mensagem: str = "") -> dict:
    s = _solicitacao(con, sid)
    m = montar(con, sid)
    expira = (datetime.now(timezone.utc) + timedelta(days=validade_dias(con))).strftime("%Y-%m-%d %H:%M:%S")
    t = textos(con, s, m["arquivos"], f"{link_base(con)}/entrega/…", expira, mensagem)
    c = canal_configurado(con)
    return {"id": sid, "para": s["email"] or "", "nome": s["solicitante"] or "", "email_valido": bool(ENDERECO.match(s["email"] or "")),
            "situacao": s["situacao"], "arquivos": [{k: v for k, v in a.items() if k not in ("origem", "gerar")} for a in m["arquivos"]],
            "fora": m["fora"], "assunto": t["assunto"], "texto": t["texto"], "validade": _data_br(expira), "validade_dias": validade_dias(con),
            **c}


def aprovar_e_enviar(con, sid: int, ator: dict, mensagem: str = "", canal: str | None = None, teste: bool = False) -> dict:
    """Cria o link, prepara os arquivos, manda o e-mail e, só se o envio foi aceito, marca o pedido como entregue.
    `teste`: manda para quem aprovou (link de 1 dia) e não muda o pedido."""
    s = _solicitacao(con, sid)
    if not teste and s["situacao"] in ("entregue", "recusada"):
        raise HTTPException(409, "Este pedido já foi entregue." if s["situacao"] == "entregue" else "Este pedido foi recusado.")
    para = (ator.get("email") if teste else s["email"]) or ""
    if not ENDERECO.match(para):
        raise HTTPException(409, "O e-mail de quem pediu não é válido: corrija o pedido antes de enviar.")
    c = canal_configurado(con)
    canal = canal or c["canal"]
    if not c["prontos"]:
        raise HTTPException(409, "Nenhum canal de e-mail configurado: preencha o Sender.net (sender.token e sender.campanha_entrega) em Configurações.")
    if canal not in c["prontos"]:
        raise HTTPException(409, f"O envio por {CANAIS.get(canal, canal)} não está configurado. Preencha em Configurações.")
    mensagem = " ".join((mensagem or "").split())[:1000]
    m = montar(con, sid)
    if not m["arquivos"]:
        raise HTTPException(409, "Nenhum arquivo deste pedido foi achado no QNAP. Veja o que ficou de fora no pacote.")
    token = secrets.token_urlsafe(32)
    dias = 1 if teste else validade_dias(con)
    expira = (datetime.now(timezone.utc) + timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    lid = con.execute("INSERT INTO entrega_link (solicitacao_id, token_hash, arquivos, para, canal, teste, criado_por, expira_em) VALUES (?,?,?,?,?,?,?,?)",
                      (sid, _hash(token), "[]", para, canal, int(teste), ator.get("email"), expira)).lastrowid
    con.commit()
    dest = pasta() / str(lid)
    try:
        arquivos = []
        for n, a in enumerate(m["arquivos"], 1):
            origem = Path(a["origem"])
            if a["gerar"]:
                dest.mkdir(parents=True, exist_ok=True)
                alvo = dest / a["nome"]
                tam = _gerar_jpg(origem, alvo, LADO_3000 if a["formato"] == "jpg_3000" else None)
            else:
                alvo, tam = origem, origem.stat().st_size
            arquivos.append({"n": n, "codigo": a["codigo"], "titulo": a["titulo"], "formato": a["formato"], "resolucao": a["resolucao"],
                             "nome": a["nome"], "caminho": str(alvo), "tamanho": tam})
        con.execute("UPDATE entrega_link SET arquivos=? WHERE id=?", (json.dumps(arquivos, ensure_ascii=False), lid))
        con.commit()
        link = f"{link_base(con)}/entrega/{token}"
        t = textos(con, s, arquivos, link, expira, mensagem)
        responder = _cfg(con, "entrega.responder_para")
        envio_id = enviar(con, canal, para, s["solicitante"] or "", t, responder, None if teste else _pedido_site_id(con, sid))
    except (EnvioErro, OSError) as e:
        con.execute("UPDATE entrega_link SET revogado_em=datetime('now') WHERE id=?", (lid,))
        con.commit()
        shutil.rmtree(dest, ignore_errors=True)
        msg = str(e) if isinstance(e, EnvioErro) else f"Não consegui preparar os arquivos ({type(e).__name__})"
        raise HTTPException(502, f"{msg}. Nada foi enviado e o pedido não mudou.")
    total = sum(a["tamanho"] or 0 for a in arquivos)
    resumo = f"{len(arquivos)} arquivo(s), {_fmt_tamanho(total)} · enviado por e-mail ({CANAIS[canal]}) para {para} · link até {_data_br(expira)}"
    if not teste:
        con.execute("UPDATE solicitacao SET situacao='entregue', entregue_em=datetime('now'), entrega=? WHERE id=?", (resumo, sid))
        entregues = {(a["codigo"], a["formato"]) for a in arquivos}
        for cod, fmt in con.execute("SELECT codigo, formato FROM solicitacao_item WHERE solicitacao_id=?", (sid,)).fetchall():
            if (cod, fmt) in entregues or any(x[1] == fmt and x[0].startswith(cod + "-") for x in entregues):
                con.execute("UPDATE solicitacao_item SET entregue=1 WHERE solicitacao_id=? AND codigo=? AND formato=?", (sid, cod, fmt))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,?,?,?)",
                (str(sid), "envio_teste" if teste else "entregue_por_email", ator.get("email"),
                 json.dumps({"canal": canal, "para": para, "arquivos": len(arquivos), "fora": len(m["fora"]), "link_ate": expira,
                             "envio_id": envio_id or None, "folhas": [a["codigo"] for a in arquivos][:200]}, ensure_ascii=False)))
    con.commit()
    return {"ok": True, "teste": teste, "canal": canal, "para": para, "arquivos": len(arquivos), "fora": m["fora"],
            "validade": _data_br(expira), "entrega": resumo, "link": t["variaveis"]["link"]}


def links(con, sid: int) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM entrega_link WHERE solicitacao_id=? ORDER BY id DESC", (sid,)).fetchall():
        venceu = r["expira_em"] < datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        out.append({"id": r["id"], "para": r["para"], "canal": r["canal"], "teste": bool(r["teste"]), "criado_em": r["criado_em"],
                    "criado_por": r["criado_por"], "expira_em": r["expira_em"], "downloads": r["downloads"], "ultimo_download_em": r["ultimo_download_em"],
                    "situacao": "cancelado" if r["revogado_em"] else "vencido" if venceu else "ativo"})
    return out


def cancelar_links(con, sid: int, ator: dict) -> int:
    n = con.execute("UPDATE entrega_link SET revogado_em=datetime('now') WHERE solicitacao_id=? AND revogado_em IS NULL", (sid,)).rowcount
    if n:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'link_cancelado',?,?)",
                    (str(sid), ator.get("email"), json.dumps({"links": n})))
    con.commit()
    return n


# ---------------------------------------------------------------- download público
def achar(con, token: str):
    """(link, motivo). Motivo: '' (vale), 'inexistente', 'cancelado' ou 'vencido'."""
    if not _TOKEN.match(token or ""):
        return None, "inexistente"
    r = con.execute("SELECT * FROM entrega_link WHERE token_hash=?", (_hash(token),)).fetchone()
    if not r:
        return None, "inexistente"
    if r["revogado_em"]:
        return r, "cancelado"
    if r["expira_em"] < datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
        return r, "vencido"
    return r, ""


def arquivo(con, token: str, n: int) -> tuple[Path, str]:
    r, motivo = achar(con, token)
    if motivo:
        raise HTTPException(410 if motivo in ("cancelado", "vencido") else 404, "Este link não vale mais." if r else "Link não encontrado.")
    a = next((x for x in json.loads(r["arquivos"] or "[]") if x.get("n") == n), None)
    alvo = _permitido(con, a["caminho"]) if a else None
    if alvo is None:
        raise HTTPException(404, "Arquivo não encontrado. Responda o e-mail da CAMP que a equipe manda de novo.")
    con.execute("UPDATE entrega_link SET downloads=downloads+1, ultimo_download_em=datetime('now') WHERE id=?", (r["id"],))
    con.commit()
    return alvo, a["nome"]


def contar_download(con, link_id: int) -> None:
    con.execute("UPDATE entrega_link SET downloads=downloads+1, ultimo_download_em=datetime('now') WHERE id=?", (link_id,))
    con.commit()


def arquivos_do_zip(con, r) -> list[tuple[Path, str]]:
    """(arquivo, nome dentro do zip) de cada arquivo do link que ainda existe e está em lugar permitido; pasta = código do projeto."""
    out = []
    for a in json.loads(r["arquivos"] or "[]"):
        alvo = _permitido(con, a.get("caminho", ""))
        if alvo is not None:
            nome = a["nome"]
            out.append((alvo, f"{nome[:10]}/{nome}" if re.match(r"^F\d{3}-P\d{4}", nome) else nome))
    return out


class _Cano:
    """Destino de escrita do zip que só acumula; o gerador entrega os pedaços conforme o zip é escrito (nada em disco)."""
    def __init__(self) -> None:
        self.pedacos: list[bytes] = []
        self.pos = 0

    def write(self, b) -> int:
        self.pedacos.append(bytes(b))
        self.pos += len(b)
        return len(b)

    def tell(self) -> int:
        return self.pos

    def flush(self) -> None:
        pass

    def tirar(self) -> bytes:
        b, self.pedacos = b"".join(self.pedacos), []
        return b


def zip_em_pedacos(arquivos: list[tuple[Path, str]], bloco: int = 1024 * 1024):
    """O .zip (sem compressão: TIFF e JPG já são comprimidos; ZIP64 para pacote acima de 4 GB) gerado aos pedaços."""
    import zipfile
    cano = _Cano()
    with zipfile.ZipFile(cano, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for origem, nome in arquivos:
            info = zipfile.ZipInfo.from_file(origem, nome)
            info.compress_type = zipfile.ZIP_STORED
            with origem.open("rb") as f, z.open(info, "w", force_zip64=True) as dst:
                while True:
                    b = f.read(bloco)
                    if not b:
                        break
                    dst.write(b)
                    if cano.pos:
                        yield cano.tirar()
            yield cano.tirar()
    yield cano.tirar()
