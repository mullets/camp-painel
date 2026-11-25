"""Arquivos originais de um projeto do acervo (CAMP-ENTREGA, 25/11/2026).

Rafael: "Dentro de um projeto, no painel preciso conseguir baixar o arquivo em TIFF em alguma aba, ou o seu original em alta. Além disso,
caso alguém solicite acesso a algum, fazer uma resposta para download com link temporário e uma cobrança, além de justificar o porquê da
cobrança ou ausência dela."

- GET  /api/projetos/{codigo}/originais                lista as folhas com o que o painel SABE que existe (caminho do TIFF / JPG guardado
                                                        pelo coletor). Não abre o QNAP aqui: listar centenas de arquivos pelo SMB trava.
- GET  /api/projetos/{codigo}/originais/{folha}?formato=tif|jpg_original   o arquivo da folha, direto do QNAP (o mesmo achado da entrega
                                                        por e-mail: entrega._origem), só dentro das raízes permitidas, nunca lixeira/oculto.
- GET  /api/projetos/{codigo}/originais.zip?formato=…&folhas=A,B           as escolhidas num .zip montado na hora (nada em disco).
- POST /api/projetos/{codigo}/originais/pedido          cria um pedido de alta resolução feito no painel (a pessoa pediu por e-mail ou
                                                        pessoalmente) com as folhas escolhidas; a tela abre o envio de sempre (link
                                                        temporário + cobrança ou não, com a justificativa).

Papel: operador ou mais (o mesmo que entrega um pedido; leitura não baixa original). Cada download fica no histórico do projeto
(quem, o quê, quando).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import auth, entrega
from .db import connect

router = APIRouter(prefix="/api/projetos", tags=["originais"])

FORMATOS = {"tif": "TIFF", "jpg_original": "JPG original"}
MAX_ZIP = 500
_RE_PROJ = re.compile(r"^F\d{3}-P\d{4}$")
FINALIDADES = ("publicacao", "pesquisa", "editorial", "familia", "exposicao", "outro")


def _projeto(con, codigo: str):
    codigo = (codigo or "").upper()
    if not _RE_PROJ.match(codigo) or not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
        raise HTTPException(404, "Projeto não encontrado")
    return codigo


def _folhas(con, codigo: str):
    return con.execute("""SELECT * FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL
                          ORDER BY serie_codigo, sequencial, codigo""", (codigo,)).fetchall()


def _tem_jpg(i) -> bool:
    k = i.keys()
    return bool((i["arquivo_jpg"] and not str(i["arquivo_jpg"]).startswith("http")) or ("imagem_corrigida" in k and i["imagem_corrigida"]))


def _oculto(con, alvo: Path) -> bool:
    """Lixeira (@Recycle, #recycle) e pastas ocultas do QNAP: nunca saem, mesmo dentro da raiz."""
    for r in entrega._raizes_permitidas(con):
        if r in alvo.parents:
            return any(p.startswith((".", "@", "#")) for p in alvo.relative_to(r).parts)
    return True


def _arquivo(con, item, formato: str) -> Path | None:
    """O arquivo original da folha (TIFF ou JPG em resolução original), só se existir e estiver num lugar permitido."""
    from . import exportacao
    origem, _motivo, gerar = entrega._origem(con, exportacao.raiz_qnap(con), item, formato)
    if origem is None or gerar:            # "JPG original" de folha que só tem TIFF: aqui não se gera nada (baixe o TIFF)
        return None
    alvo = entrega._permitido(con, origem)
    if alvo is None or _oculto(con, alvo):
        return None
    return alvo


def _registrar(con, codigo: str, ator: dict, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'original_baixado',?,?)",
                (codigo, ator.get("email"), json.dumps(detalhe, ensure_ascii=False)))
    con.commit()


@router.get("/{codigo}/originais")
def listar(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        codigo = _projeto(con, codigo)
        folhas = [{"codigo": i["codigo"], "titulo": i["titulo"] or "", "serie": i["serie_codigo"] or "",
                   "tif": bool(i["arquivo_tif"]), "jpg": _tem_jpg(i)} for i in _folhas(con, codigo)]
        baix = [{"quando": e["quando"], "ator": e["ator"], "detalhe": json.loads(e["detalhe"] or "{}")}
                for e in con.execute("""SELECT quando, ator, detalhe FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='original_baixado'
                                        ORDER BY id DESC LIMIT 20""", (codigo,))]
        return {"projeto": codigo, "folhas": folhas, "com_tif": sum(f["tif"] for f in folhas), "com_jpg": sum(f["jpg"] for f in folhas),
                "downloads": baix, "max_zip": MAX_ZIP}
    finally:
        con.close()


@router.get("/{codigo}/originais.zip")
def baixar_zip(codigo: str, folhas: str = "", formato: str = "tif", u: dict = Depends(auth.exige("operador"))):
    if formato not in FORMATOS:
        raise HTTPException(400, "Formato: tif ou jpg_original")
    con = connect()
    try:
        codigo = _projeto(con, codigo)
        pedidas = [c.strip().upper() for c in folhas.split(",") if c.strip()]
        if not pedidas:
            raise HTTPException(400, "Escolha as folhas")
        if len(pedidas) > MAX_ZIP:
            raise HTTPException(400, f"No máximo {MAX_ZIP} folhas por .zip")
        itens = {i["codigo"]: i for i in _folhas(con, codigo)}
        arquivos, fora = [], []
        for c in dict.fromkeys(pedidas):
            alvo = _arquivo(con, itens[c], formato) if c in itens else None
            if alvo is None:
                fora.append(c)
            else:
                arquivos.append((alvo, f"{codigo}/{c}{alvo.suffix.lower()}"))
        if not arquivos:
            raise HTTPException(404, "Nenhum arquivo dessas folhas foi achado no QNAP")
        _registrar(con, codigo, u, {"formato": formato, "zip": True, "folhas": [Path(n).stem for _, n in arquivos][:200],
                                    "quantidade": len(arquivos), "fora": fora[:200]})
    finally:
        con.close()
    nome = f"{codigo}-{'TIFF' if formato == 'tif' else 'JPG-original'}.zip"
    return StreamingResponse(entrega.zip_em_pedacos(arquivos), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store",
                                      **({"X-Camp-Fora": ",".join(fora)[:900]} if fora else {})})


@router.get("/{codigo}/originais/{folha}")
def baixar(codigo: str, folha: str, formato: str = "tif", u: dict = Depends(auth.exige("operador"))):
    if formato not in FORMATOS:
        raise HTTPException(400, "Formato: tif ou jpg_original")
    con = connect()
    try:
        codigo = _projeto(con, codigo)
        folha = (folha or "").upper()
        item = con.execute("SELECT * FROM item WHERE codigo=? AND projeto_codigo=?", (folha, codigo)).fetchone()
        alvo = _arquivo(con, item, formato) if item else None
        if alvo is None:
            raise HTTPException(404, "Arquivo não encontrado no QNAP" + (": esta folha só tem TIFF" if item and formato != "tif" and item["arquivo_tif"] else ""))
        _registrar(con, codigo, u, {"formato": formato, "folha": folha, "tamanho": alvo.stat().st_size})
    finally:
        con.close()
    tipo = "image/tiff" if alvo.suffix.lower() in (".tif", ".tiff") else "image/jpeg"
    return FileResponse(alvo, media_type=tipo, filename=f"{folha}{alvo.suffix.lower()}", headers={"Cache-Control": "no-store"})


class PedidoPainel(BaseModel):
    nome: str
    email: str
    instituicao: str | None = None
    finalidade: str = "outro"
    detalhe: str | None = None
    folhas: list[str]
    formato: str = "tif"


@router.post("/{codigo}/originais/pedido")
def criar_pedido(codigo: str, b: PedidoPainel, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Pedido de alta resolução registrado no painel (a pessoa pediu por e-mail ou pessoalmente). Depois a tela abre o envio de sempre."""
    from .email_envio import ENDERECO
    nome = " ".join((b.nome or "").split())[:160]
    email = (b.email or "").strip().lower()[:200]
    if len(nome) < 2:
        raise HTTPException(400, "Informe o nome de quem pediu")
    if not ENDERECO.match(email):
        raise HTTPException(400, "E-mail inválido")
    if b.finalidade not in FINALIDADES:
        raise HTTPException(400, "Escolha a finalidade")
    if b.formato not in ("tif", "jpg_original", "jpg_3000"):
        raise HTTPException(400, "Formato: TIFF, JPG original ou JPG 3000 px")
    con = connect()
    try:
        codigo = _projeto(con, codigo)
        validas = {i["codigo"] for i in _folhas(con, codigo)}
        folhas = [c for c in dict.fromkeys(x.strip().upper() for x in b.folhas) if c in validas]
        if not folhas:
            raise HTTPException(400, "Escolha ao menos uma folha deste projeto")
        det = " ".join((b.detalhe or "").split())[:1000]
        sid = con.execute("""INSERT INTO solicitacao (solicitante, email, instituicao, finalidade, detalhe, origem, situacao)
                             VALUES (?,?,?,?,?,'email','em_preparacao')""",
                          (nome, email, " ".join((b.instituicao or "").split())[:200] or None, b.finalidade,
                           (f"Pedido registrado no painel a partir do projeto {codigo}." + (f" {det}" if det else "")))).lastrowid
        con.executemany("INSERT OR IGNORE INTO solicitacao_item (solicitacao_id, codigo, formato) VALUES (?,?,?)",
                        [(sid, c, b.formato) for c in folhas])
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'criado_no_painel',?,?)",
                    (str(sid), u.get("email"), json.dumps({"projeto": codigo, "folhas": len(folhas), "formato": b.formato}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": sid, "folhas": len(folhas)}
    finally:
        con.close()
