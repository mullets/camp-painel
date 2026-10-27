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


# ---------------------------------------------------------------- UX-44 · recorte automático nas imagens que JÁ estão no site
def candidatos_recorte(con, fundo: str | None = None, projeto: str | None = None) -> list:
    """Folhas no site cuja imagem subiu antes desta versão do recorte automático (item.site_imagem_recorte diferente da versão atual)."""
    from .recorte_auto import VERSAO
    sql = """SELECT i.*, p.fundo_codigo FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
              WHERE i.tainacan_item_id IS NOT NULL AND i.site_media_id IS NOT NULL AND i.duplicata_de IS NULL
                AND COALESCE(i.retida,0)=0 AND (i.site_imagem_recorte IS NULL OR i.site_imagem_recorte <> ?)"""
    args: list = [VERSAO]
    if fundo:
        sql += " AND p.fundo_codigo=?"; args.append(fundo)
    if projeto:
        sql += " AND i.projeto_codigo=?"; args.append(projeto)
    return con.execute(sql + " ORDER BY i.codigo", args).fetchall()


def recorte_automatico(aplicar: bool = False, limite: int = 0, incluir_cor: bool = False, fundo: str | None = None, projeto: str | None = None,
                       ator: str = "script", prog=None) -> dict:
    """SIMULA por padrão: para cada folha no site (ainda sem esta versão), o que o derivado público levaria. Grupos:
    recorte (o fundo do scanner sai), cor (só branco/contraste), incerto (não recorta; conferir), igual (sem fundo e cor desligada,
    recusado ou desligado), manual (recorte manual: só cor), sem_imagem. aplicar=True reenvia 'recorte' (e 'cor', se incluir_cor), até `limite`."""
    from pathlib import Path
    from .db import connect
    from . import ajuste_imagem, recorte_auto
    from .giro_imagem import espelho_efetivo
    from .imagem_site import imagem_para_o_site
    con = connect()
    try:
        linhas = candidatos_recorte(con, fundo, projeto)
        if prog:
            prog.total(len(linhas))
        grupos: dict[str, list[str]] = {k: [] for k in ("recorte", "cor", "incerto", "manual", "igual", "sem_imagem")}
        for r in linhas:
            if prog:
                prog.passo("Analisando as imagens", r["codigo"])
            cam = imagem_para_o_site(con, r)
            if not cam or not Path(cam).is_file():
                grupos["sem_imagem"].append(r["codigo"])
            else:
                rec, ang = ajuste_imagem.ler(r)
                try:
                    pl = recorte_auto.plano(con, r, Path(cam), r["giro_manual"] or 0, espelho_efetivo(r), rec, ang)
                except Exception:  # noqa: BLE001  (arquivo corrompido)
                    pl = {"situacao": "erro", "recorte_auto": None, "cor": False}
                if pl["recorte_auto"]:
                    grupos["recorte"].append(r["codigo"])
                elif pl["situacao"] == "incerto":
                    grupos["incerto"].append(r["codigo"])
                elif pl["situacao"] == "manual":
                    grupos["manual" if not pl["cor"] else "cor"].append(r["codigo"])
                elif pl["cor"]:
                    grupos["cor"].append(r["codigo"])
                else:
                    grupos["igual"].append(r["codigo"])
            if prog:
                prog.feita()
    finally:
        con.close()
    contagem = {k: len(v) for k, v in grupos.items()}
    alvo = grupos["recorte"] + (grupos["cor"] if incluir_cor else [])
    out = {"ok": True, "simulacao": not aplicar, "analisadas": len(linhas), "contagem": contagem, "mudariam": len(alvo),
           "codigos": {k: v[:500] for k, v in grupos.items()}}
    if not aplicar:
        out["mensagem"] = (f"SIMULAÇÃO: {len(alvo)} de {len(linhas)} folha(s) no site mudariam ({contagem['recorte']} com recorte, "
                           f"{contagem['cor']} só cor{'' if incluir_cor else ', fora do reenvio'}; {contagem['incerto']} incerta(s) para conferir). Nada foi enviado.")
        return out
    feitas, falhas = [], []
    for cod in alvo[: limite or None]:
        res = reenviar(cod, ator)
        (feitas if res["ok"] else falhas).append(res if not res["ok"] else cod)
        if prog:
            prog.log(f"{cod}: {'ok' if res['ok'] else res.get('erro')}")
    out.update({"reenviadas": len(feitas), "falhas": falhas, "mensagem": f"Reenviadas: {len(feitas)} · falhas: {len(falhas)} · restam: {max(0, len(alvo) - len(feitas) - len(falhas))}"})
    return out
