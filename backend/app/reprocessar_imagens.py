"""CAMP-048 · Imagens públicas acima de 1920 px: achar e reenviar.
Folha que subiu ao site antes do limite (site_imagem_lado NULL = tamanho desconhecido) ou com lado maior que 1920 px é candidata.
O reenvio troca o ARQUIVO do anexo no site (mesmo ID, links e capa continuam valendo) pelo derivado público (JPEG q85 sRGB, lado <= 1920)."""
from __future__ import annotations

from .giro_imagem import LADO_PUBLICO


def candidatos(con, fundo: str | None = None, projeto: str | None = None) -> list[dict]:
    sql = """SELECT i.codigo, i.projeto_codigo, p.fundo_codigo, i.site_media_id, i.site_imagem_lado, i.giro_manual, i.arquivo_jpg, i.pendencias, i.espelhado, i.espelho_manual
               FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
              WHERE i.tainacan_item_id IS NOT NULL AND i.site_media_id IS NOT NULL AND i.duplicata_de IS NULL
                AND (i.site_imagem_lado IS NULL OR i.site_imagem_lado > ?)"""
    args: list = [LADO_PUBLICO]
    if fundo:
        sql += " AND p.fundo_codigo=?"; args.append(fundo)
    if projeto:
        sql += " AND i.projeto_codigo=?"; args.append(projeto)
    from .imagem_site import imagem_para_o_site
    out = []
    for r in con.execute(sql + " ORDER BY i.codigo", args):
        out.append({"codigo": r["codigo"], "projeto": r["projeto_codigo"], "fundo": r["fundo_codigo"], "media_id": r["site_media_id"],
                    "lado_no_site": r["site_imagem_lado"], "tem_imagem_local": bool(imagem_para_o_site(con, r))})
    return out


def reenviar(codigo: str, ator: str = "script") -> dict:
    """Reenvia uma folha. Devolve {codigo, ok, lado_px | erro}; nunca levanta (o script segue para a próxima)."""
    from .db import connect
    from . import publicador
    con = connect()
    try:
        r = con.execute("SELECT giro_manual FROM item WHERE codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    try:
        m = publicador.girar_imagem_no_site(codigo, (r["giro_manual"] or 0) if r else 0)
        con = connect()
        try:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'imagem_publica_reenviada',?,?)", (codigo, ator, '{"lado_px": %s}' % (m.get("lado_px") or "null")))
            con.commit()
        finally:
            con.close()
        return {"codigo": codigo, "ok": True, "lado_px": m.get("lado_px")}
    except Exception as e:  # noqa: BLE001
        return {"codigo": codigo, "ok": False, "erro": str(e)[:200]}
