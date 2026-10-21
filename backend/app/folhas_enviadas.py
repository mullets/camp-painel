"""Folhas enviadas direto pelo painel, na página do projeto (21/10/2026).

Pedido (Rafa): "e se eu quiser subir algo direto pelo admin na pagina de projeto? como faço isso?" → "sim, sobe" (na pasta do painel).

- Um arquivo por pedido: POST /api/projetos/{codigo}/folhas/enviar?serie=S03&nome=foto.jpg[&titulo=…][&ano=1992] com a imagem no corpo
  (JPEG, PNG ou TIFF; até LIMITE_BYTES). Só admin. A tela manda um por vez e mostra o andamento.
- O arquivo fica numa pasta DO PAINEL (CAMP_FOLHAS_ENVIADAS_DIR, senão <pasta do banco>/folhas_enviadas/<projeto>/), nunca no QNAP:
  não mexe no material das estações nem no que o CAMP Vision lê. PNG/TIFF ganham um JPG ao lado (é o que a prévia e o site usam);
  o original fica guardado (item.arquivo_tif).
- Código: o painel é a fonte dos códigos. As folhas enviadas usam a faixa D90001+ do projeto, que o CAMP Vision não usa: nunca colidem
  com o que chega pelas estações. Ano no código = o do projeto (0000 sem ano), como em mover folha.
- A folha entra como conferida por quem enviou (é ela que escolheu o arquivo), origem 'manual', e segue o caminho de sempre
  (revisão, publicação). A mesma imagem (md5) duas vezes no projeto: recusa (409).
- ATENÇÃO: o backup do painel copia só o banco. Estes arquivos ficam só nesta pasta; vale guardar o original também no QNAP.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from . import auth
from .config import settings
from .db import connect

router = APIRouter(prefix="/api", tags=["folhas_enviadas"])

LIMITE_BYTES = 80 * 1024 * 1024
FAIXA_PAINEL = 90000                      # D90001 em diante: só o painel
TIPO_DA_SERIE = {"S03": "Fotografia", "S04": "Negativo", "S05": "Slide"}
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/tiff": ".tif"}


def pasta() -> Path:
    p = Path(os.environ.get("CAMP_FOLHAS_ENVIADAS_DIR") or Path(settings.CAMP_DB_PATH).parent / "folhas_enviadas")
    p.mkdir(parents=True, exist_ok=True)
    return p


def dentro(caminho) -> Path | None:
    """O arquivo, se estiver DENTRO da pasta das folhas enviadas e existir; senão None (a prévia nunca serve nada de fora)."""
    if not caminho or str(caminho).startswith("http"):
        return None
    try:
        base = pasta().resolve()
        alvo = Path(str(caminho)).resolve()
        if base in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
            return alvo
    except OSError:
        return None
    return None


def tipo_imagem(b: bytes) -> str | None:
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None


def titulo_do_nome(nome: str) -> str:
    """'IMG_0042-fachada_sul.JPG' → 'IMG 0042 fachada sul' (o título que a pessoa pode corrigir depois)."""
    base = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", os.path.basename(nome or "")).strip()
    return " ".join(re.sub(r"[_\-]+", " ", base).split())[:300]


def _jpg_de(original: Path, destino: Path) -> None:
    from PIL import Image  # noqa: PLC0415
    with Image.open(original) as im:
        im.seek(0)
        if im.mode in ("I;16", "I;16B", "I;16L", "I"):
            im = im.point(lambda x: x * (1 / 256)).convert("L")
        im = im.convert("RGB")
        im.save(destino, "JPEG", quality=92, optimize=True)


@router.post("/projetos/{codigo}/folhas/enviar")
async def enviar_folha(codigo: str, request: Request, serie: str, nome: str = "", titulo: str | None = None, ano: int | None = None,
                       u: dict = Depends(auth.exige("admin"))) -> dict:
    dados = await request.body()
    if not dados:
        raise HTTPException(400, "O arquivo veio vazio.")
    if len(dados) > LIMITE_BYTES:
        raise HTTPException(413, f"Arquivo grande demais (máximo {LIMITE_BYTES // (1024 * 1024)} MB).")
    tipo = tipo_imagem(dados)
    if not tipo:
        raise HTTPException(400, "Envie a imagem em JPEG, PNG ou TIFF.")
    if ano is not None and ano != 0 and not (1800 <= ano <= 2100):
        raise HTTPException(400, "Ano inválido.")
    md5 = hashlib.md5(dados).hexdigest()  # noqa: S324  (identifica arquivo repetido, não é segurança)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        p = con.execute("SELECT codigo, ano, mesclado_em, descartado_em FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if p["mesclado_em"] or p["descartado_em"]:
            raise HTTPException(409, "Este projeto foi " + ("mesclado" if p["mesclado_em"] else "descartado") + ": envie no projeto certo.")
        s = con.execute("SELECT codigo FROM serie WHERE codigo=?", ((serie or "").upper(),)).fetchone()
        if not s:
            raise HTTPException(400, f"Tipo de material (série) '{serie}' não existe.")
        serie = s[0]
        ja = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND md5=?", (codigo, md5)).fetchone()
        if ja:
            raise HTTPException(409, f"Esta imagem já está no projeto: {ja[0]}.")
        seq = max(FAIXA_PAINEL, con.execute("SELECT COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=? AND sequencial>?",
                                            (codigo, FAIXA_PAINEL)).fetchone()[0]) + 1
        a_cod = int(p["ano"]) if p["ano"] else 0
        cod = f"{codigo}-{a_cod:04d}-{serie}-D{seq:05d}"
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (cod,)).fetchone():
            raise HTTPException(409, f"O código {cod} já existe; tente de novo.")
        dest_dir = pasta() / codigo
        dest_dir.mkdir(parents=True, exist_ok=True)
        original = dest_dir / (cod + _EXT[tipo])
        original.write_bytes(dados)
        jpg = original
        if tipo != "image/jpeg":
            try:
                jpg = dest_dir / (cod + ".jpg")
                _jpg_de(original, jpg)
            except Exception as e:  # noqa: BLE001
                original.unlink(missing_ok=True)
                raise HTTPException(400, f"Não consegui ler a imagem ({str(e)[:120]}). Envie em JPEG.") from e
        tit = (titulo or "").strip()[:300] or titulo_do_nome(nome) or None
        pend = {"previa": "@jpg", "enviada_pelo_painel": {"arquivo": os.path.basename(nome or "")[:200], "bytes": len(dados), "por": u["email"]}}
        con.execute("""INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, ano_folha, arquivo_jpg, arquivo_tif,
                                         md5, origem, revisao, revisado_por, revisado_em, pendencias)
                       VALUES (?,?,?,?,?,?,?,?,?,?,'manual','conferida',?,datetime('now'),?)""",
                    (cod, codigo, serie, seq, tit, TIPO_DA_SERIE.get(serie), ano or None, str(jpg),
                     str(original) if original != jpg else None, md5, u["email"], json.dumps(pend, ensure_ascii=False)))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'folha_enviada_pelo_painel',?,?)",
                    (cod, u["email"], json.dumps({"arquivo": os.path.basename(nome or ""), "bytes": len(dados), "tipo": tipo, "md5": md5}, ensure_ascii=False)))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'folha_enviada_pelo_painel',?,?)",
                    (codigo, u["email"], json.dumps({"folha": cod}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "codigo": cod, "titulo": tit, "serie": serie, "bytes": len(dados)}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()
