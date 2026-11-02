"""Entrega de pedido de alta resolução por e-mail (01/11/2026).

Rafael: "quando recebemos uma solicitação de envio de material em alta, poder aprovar pelo sistema e já enviar o que ele pediu pelo
próprio sistema". Fluxo:

1. Prévia (`previa`): o que vai no pacote (o arquivo de cada folha pedida, já achado no QNAP), o que fica de fora e o texto do e-mail.
2. Aprovar e enviar (`aprovar_e_enviar`): cria um link de download com prazo (`entrega.validade_dias`), prepara os arquivos e manda
   o e-mail à pessoa. Canal (`entrega.canal`):
   - `sender`: e-mail transacional do Sender.net com o layout pronto (`sender.token` + `sender.campanha_entrega`, o TR09
     "material_download"), com as variáveis {{nome}}, {{link}} (o .zip com tudo), {{link_pagina}}, {{tamanho}}, {{validade}} (texto
     longo, igual ao fim real do link), {{validade_curta}}, {{material}}, {{protocolo}}, {{pedido}}, {{quantidade}}, {{lista}}, {{mensagem}};
   - `site`: o e-mail do próprio site (rota `POST /wp-json/camp/v1/painel/pedido/enviar`, que usa o SMTP configurado no site).
   Só depois do envio aceito o pedido vira "entregue". Se o envio falhar, o link é cancelado e nada muda no pedido.
3. Download: o link do e-mail abre /entrega/<token> com o TERMO DE USO (uso não comercial; comercial = R$ por folha, Lei 9.610/98).
   Só depois do aceite (nome + "Li e aceito"; guardado como prova) a página libera o .zip com tudo (/entrega/<token>/tudo.zip,
   montado na hora, sem cópia em disco) e os arquivos um a um. Rotas públicas do painel, sem login, até a validade.

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
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import HTTPException

from .config import settings
from .email_envio import ENDERECO

SENDER_URL = os.environ.get("CAMP_SENDER_URL", "https://api.sender.net/v2")
CANAIS = {"sender": "Sender.net", "site": "e-mail do site"}
LADO_3000 = 3000
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
MATERIAL_MAX = 160
try:
    from zoneinfo import ZoneInfo
    FUSO_SP = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001 — servidor sem a base de fusos: o Brasil não tem horário de verão desde 2019
    FUSO_SP = timezone(timedelta(hours=-3), "America/Sao_Paulo")


# 02/11 (Rafael): o termo que a pessoa aceita antes de baixar. Editável em Configurações (entrega.termo); {preco} = valor por folha.
TERMO_PADRAO = """Termo de uso do material do Acervo CAMP

1. Uso não comercial. Este material é cedido somente para uso não comercial: estudo, pesquisa, ensino, trabalhos acadêmicos e
maquetes didáticas, na finalidade informada no pedido.

2. Uso comercial é cobrado. Qualquer uso comercial (livros e revistas à venda, publicidade, produtos, projetos ou exposições com
fins lucrativos, entre outros) depende de autorização prévia e por escrito da CAMP e custa R$ {preco} por folha.

3. Crédito obrigatório. Toda reprodução deve citar a fonte: "Acervo CAMP – Casa da Arquitetura Moderna Paulista" e o autor do projeto.

4. Direitos autorais. Os desenhos e documentos são protegidos pela Lei de Direitos Autorais (Lei nº 9.610/1998). Não é permitido
vender, ceder ou repassar os arquivos a terceiros, nem alterá-los de forma a atribuir a outra pessoa a autoria da obra.

5. Responsabilidade. O uso em desacordo com este termo sujeita o responsável às sanções civis e penais previstas em lei, além da
cobrança do valor do uso comercial.

Ao marcar "Li e aceito" e clicar em "Aceitar e baixar", declaro que li este termo, que o uso será não comercial e que concordo com
estas condições."""


def preco_comercial(con) -> str:
    v = _cfg(con, "entrega.preco_comercial_folha", "150").replace(",", ".")
    try:
        n = float(v)
    except ValueError:
        n = 150.0
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def termo(con) -> str:
    return (_cfg(con, "entrega.termo") or TERMO_PADRAO).replace("{preco}", preco_comercial(con))


def aceitar(con, token: str, nome: str, ip: str) -> None:
    """Registra o aceite do termo (prova: quando, nome digitado, IP e o texto exato). Só a primeira vez conta."""
    r, motivo = achar(con, token)
    if motivo:
        raise HTTPException(410 if r else 404, "Este link não vale mais.")
    if r["aceite_em"]:
        return
    nome = " ".join((nome or "").split())[:160]
    if len(nome) < 3:
        raise HTTPException(400, "Escreva seu nome completo.")
    con.execute("UPDATE entrega_link SET aceite_em=datetime('now'), aceite_nome=?, aceite_ip=?, aceite_termo=? WHERE id=? AND aceite_em IS NULL",
                (nome, (ip or "")[:64], termo(con), r["id"]))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'termo_aceito',?,?)",
                (str(r["solicitacao_id"]), r["para"] or "público", json.dumps({"nome": nome, "link": r["id"]}, ensure_ascii=False)))
    con.commit()


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


def calcular_expira_em(dias: int, agora: datetime | None = None) -> str:
    """Fim do link (UTC, 'AAAA-MM-DD HH:MM:SS', como o banco compara): 23h59 de São Paulo do último dia que vale (hoje + `dias`).
    O texto `validade` do e-mail ("15 de novembro de 2026, às 23h59") sai deste mesmo valor: o link para exatamente nesse minuto."""
    agora = agora or datetime.now(timezone.utc)
    dia = agora.astimezone(FUSO_SP).date() + timedelta(days=dias)
    fim = datetime.combine(dia, time(23, 59), tzinfo=FUSO_SP)
    return fim.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _em_sp(iso_utc: str) -> datetime:
    return datetime.strptime(iso_utc[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(FUSO_SP)


def validade_longa(iso_utc: str) -> str:
    """'15 de novembro de 2026, às 23h59' (hora de São Paulo) a partir do `expira_em` gravado (UTC)."""
    d = _em_sp(iso_utc)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}, às {d.hour}h{d.minute:02d}"


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
    """dd/mm/aaaa do `expira_em` (UTC) no dia de São Paulo (23h59 de SP já é o dia seguinte em UTC)."""
    try:
        return _em_sp(iso).strftime("%d/%m/%Y")
    except ValueError:
        return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def protocolo(con, s) -> str:
    """Protocolo do pedido nos e-mails transacionais (CAMP-AAAA-NNNNNN). Pedido que veio do site: o mesmo do site, CAMP-<ano do pedido
    no site>-<id do pedido no site com 6 dígitos>, para a pessoa ver o mesmo número que recebeu no "pedido recebido" (TR04). Pedido
    registrado só no painel: CAMP-<ano>-P<id do painel com 6 dígitos> (o "P" evita confundir com um número do site)."""
    r = con.execute("SELECT site_id, criado_no_site FROM pedido_site WHERE destino='solicitacao' AND destino_id=? ORDER BY site_id LIMIT 1",
                    (s["id"],)).fetchone()
    k = s.keys()
    recebida = str((s["recebida_em"] if "recebida_em" in k else "") or "")
    if r:
        ano = str(r[1] or "")[:4]
        ano = ano if ano.isdigit() else (recebida[:4] if recebida[:4].isdigit() else str(datetime.now(FUSO_SP).year))
        return f"CAMP-{ano}-{int(r[0]):06d}"
    ano = recebida[:4] if recebida[:4].isdigit() else str(datetime.now(FUSO_SP).year)
    return f"CAMP-{ano}-P{int(s['id']):06d}"


def material(arquivos: list[dict]) -> str:
    """Resumo curto do pacote para o {{material}} do TR09: "12 arquivos em alta resolução — F009-P0018, F009-P0020" (projetos; um
    arquivo só: a folha). Até MATERIAL_MAX caracteres, com "…" quando a lista não cabe."""
    n = len(arquivos)
    cab = f"{n} arquivo{'s' if n != 1 else ''} em alta resolução"
    if n == 1:
        cods = [arquivos[0]["codigo"]]
    else:
        cods = list(dict.fromkeys((a["codigo"][:10] if re.match(r"^F\d{3}-P\d{4}", a["codigo"]) else a["codigo"]) for a in arquivos))
    texto = f"{cab} — {', '.join(cods)}" if cods else cab
    if len(texto) <= MATERIAL_MAX:
        return texto
    out = f"{cab} — "
    for i, c_ in enumerate(cods):
        prox = (", " if i else "") + c_
        if len(out) + len(prox) + 3 > MATERIAL_MAX:
            return out + (", …" if i else "…")
        out += prox
    return out


def link_base(con) -> str:
    return _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/")


def textos(con, s, arquivos: list[dict], link_pagina: str, expira_em: str, mensagem: str) -> dict:
    """`link` (o principal, 01/11 Rafael: "o ideal é o link de download ser um zip de todo aquele projeto") baixa tudo num .zip;
    `link_pagina` abre a página com os arquivos um a um."""
    link = link_pagina                      # 02/11: o link abre o termo de uso; aceito, a página libera o .zip e os arquivos
    total = sum(a.get("tamanho") or 0 for a in arquivos)
    nome = (s["solicitante"] or "").strip() or "olá"
    primeiro = nome.split()[0]
    lista = "\n".join(f"- {a['codigo']}{' · ' + a['titulo'] if a['titulo'] else ''} ({a['resolucao']})" for a in arquivos)
    validade = validade_longa(expira_em)
    assunto = f"CAMP · seu pedido de material em alta resolução (pedido #{s['id']})"
    corpo = (f"Olá, {primeiro},\n\n"
             "Seu pedido de material em alta resolução ao acervo da CAMP foi aprovado.\n\n"
             + (f"{mensagem}\n\n" if mensagem else "")
             + f"Abra este link temporário (vale até {validade}), aceite o termo de uso e baixe tudo num só arquivo .zip"
             f"{' (' + _fmt_tamanho(total) + ')' if total else ''}:\n{link}\n\n"
             f"O material é cedido só para uso não comercial. Uso comercial depende de autorização da CAMP e custa R$ {preco_comercial(con)} por folha.\n\n"
             f"O que está no pacote ({len(arquivos)} arquivo(s)):\n{lista}\n\n"
             "Ao usar este material, cite a fonte: Acervo CAMP – Casa da Arquitetura Moderna Paulista.\n"
             "Se tiver qualquer dúvida, é só responder este e-mail.\n\n"
             "Equipe CAMP\n")
    # TR09 (material_download, Sender.net): nome, material, protocolo, validade (texto longo = o minuto em que o link para), link.
    # As outras variáveis continuam (layouts antigos); a data curta antiga (dd/mm/aaaa) passou para `validade_curta`.
    variaveis = {"nome": primeiro, "nome_completo": nome, "link": link, "link_pagina": link_pagina, "tamanho": _fmt_tamanho(total),
                 "preco_comercial": preco_comercial(con),
                 "validade": validade, "validade_curta": _data_br(expira_em), "pedido": str(s["id"]),
                 "material": material(arquivos), "protocolo": protocolo(con, s),
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
                       json={"to": {"email": para, "name": nome}, "variables": variaveis,
                             **({"headers": {"X-CAMP-Protocolo": variaveis["protocolo"]}} if variaveis.get("protocolo") else {})})
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
    expira = calcular_expira_em(validade_dias(con))
    t = textos(con, s, m["arquivos"], f"{link_base(con)}/entrega/…", expira, mensagem)
    c = canal_configurado(con)
    itens = [{"codigo": r[0], "formato": r[1], "titulo": (con.execute("SELECT titulo FROM item WHERE codigo=?", (r[0],)).fetchone() or con.execute(
                  "SELECT titulo FROM projeto WHERE codigo=?", (r[0],)).fetchone() or [""])[0] or ""}
             for r in con.execute("SELECT codigo, formato FROM solicitacao_item WHERE solicitacao_id=? ORDER BY codigo, formato", (sid,))]
    k = s.keys()
    return {"id": sid, "para": s["email"] or "", "itens": itens, "condicoes_uso": (s["condicoes_uso"] if "condicoes_uso" in k else "") or "",
            "entrega": s["entrega"] if "entrega" in k else None, "entregue_em": s["entregue_em"] if "entregue_em" in k else None, "nome": s["solicitante"] or "", "email_valido": bool(ENDERECO.match(s["email"] or "")),
            "situacao": s["situacao"], "arquivos": [{k: v for k, v in a.items() if k not in ("origem", "gerar")} for a in m["arquivos"]],
            "fora": m["fora"], "assunto": t["assunto"], "texto": t["texto"], "validade": validade_longa(expira), "validade_dias": validade_dias(con),
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
    expira = calcular_expira_em(dias)
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
                    "aceite_em": r["aceite_em"], "aceite_nome": r["aceite_nome"],
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
    if not r["aceite_em"]:
        raise HTTPException(403, "Aceite o termo de uso antes de baixar.")
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
