"""Cartão 152: Qualidade do CAMP Vision (só admin): quanto ele acerta por campo e por versão, e quanto custa cada lote.
Fonte: revisao_campo (o que a revisão fez com cada campo lido) e lista_processamento.execucao_json (o bloco 'execucao' do pacote)."""
import csv
import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["qualidade"])
ROTULO_CAMPO = {"titulo": "Título", "tipo_documento": "Tipo", "folha": "Folha", "escala": "Escala", "ano_folha": "Ano da folha"}


@router.get("/qualidade-cv")
def qualidade(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        campos = []
        for r in con.execute("""SELECT COALESCE(versao_cv2,'(sem versão)') AS versao, campo, COUNT(*) AS total,
                                       SUM(resultado='igual') AS iguais, SUM(resultado='corrigido') AS corrigidos, SUM(resultado='preenchido') AS preenchidos
                                  FROM revisao_campo GROUP BY 1, 2 ORDER BY 1 DESC, 2"""):
            campos.append({**dict(r), "rotulo": ROTULO_CAMPO.get(r["campo"], r["campo"]), "pct_aceito": round(100 * r["iguais"] / r["total"]) if r["total"] else None})
        lotes = []
        for r in con.execute("""SELECT l.id, l.nome, l.projeto_codigo, l.execucao_json, l.aprovado_em,
                                       (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id) AS folhas
                                  FROM lista_processamento l WHERE l.execucao_json IS NOT NULL ORDER BY l.id DESC LIMIT 200"""):
            try:
                ex = json.loads(r["execucao_json"] or "{}")
            except ValueError:
                ex = {}
            lotes.append({"id": r["id"], "nome": r["nome"], "projeto_codigo": r["projeto_codigo"], "folhas": r["folhas"], "aprovado": bool(r["aprovado_em"]),
                          "versao_cv2": ex.get("versao_cv2"), "modelo": ex.get("modelo"), "custo_usd": ex.get("custo_usd"), "tempo_s": ex.get("tempo_s"), "chamadas": ex.get("chamadas")})
        versoes = {}
        for c in campos:
            v = versoes.setdefault(c["versao"], {"versao": c["versao"], "total": 0, "iguais": 0, "custo_usd": 0.0, "folhas": 0, "lotes": 0})
            v["total"] += c["total"]; v["iguais"] += c["iguais"]
        for l in lotes:
            v = versoes.setdefault(l["versao_cv2"] or "(sem versão)", {"versao": l["versao_cv2"] or "(sem versão)", "total": 0, "iguais": 0, "custo_usd": 0.0, "folhas": 0, "lotes": 0})
            v["custo_usd"] += float(l["custo_usd"] or 0); v["folhas"] += l["folhas"]; v["lotes"] += 1
        for v in versoes.values():
            v["pct_aceito"] = round(100 * v["iguais"] / v["total"]) if v["total"] else None
            v["custo_por_folha"] = round(v["custo_usd"] / v["folhas"], 4) if v["folhas"] else None
            v["custo_usd"] = round(v["custo_usd"], 4)
        return {"por_campo": campos, "por_lote": lotes, "por_versao": sorted(versoes.values(), key=lambda x: x["versao"], reverse=True)}
    finally:
        con.close()


@router.get("/qualidade-cv/gabarito.csv")
def gabarito(u: dict = Depends(auth.exige("admin"))) -> Response:
    """Para o vigia.py --avaliar do CV2: colunas arquivo_origem, campo e valor_correto (nomes EXATOS), mais valor_lido, revisado_por e data.
    Só folhas de lotes APROVADOS."""
    con = connect()
    try:
        rows = con.execute("""SELECT i.arquivo_origem, rc.campo, rc.valor_lido, rc.valor_final, rc.por, rc.em
                                FROM revisao_campo rc JOIN item i ON i.codigo=rc.item_codigo JOIN lista_processamento l ON l.id=i.lote_id
                               WHERE l.aprovado_em IS NOT NULL ORDER BY i.codigo, rc.campo""").fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["arquivo_origem", "campo", "valor_lido", "valor_correto", "revisado_por", "data"])
    for r in rows:
        w.writerow([r["arquivo_origem"] or "", r["campo"], r["valor_lido"] or "", r["valor_final"] or "", r["por"], r["em"]])
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="gabarito.csv"'})


@router.get("/alertas")
def alertas_estado(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cartão 151: o estado de cada alerta crítico e os últimos envios por e-mail."""
    con = connect()
    try:
        from . import alertas as al
        return {"estado": [dict(r) for r in con.execute("SELECT * FROM alerta_estado ORDER BY assunto")],
                "envios": [dict(r) for r in con.execute("SELECT * FROM alerta_envio ORDER BY id DESC LIMIT 50")],
                "resumo": al.resumo_estado(con)}
    finally:
        con.close()


@router.post("/alertas/resumo")
def alertas_resumo_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cartão 151: manda o resumo de hoje AGORA (para conferir o e-mail), mesmo fora das 18h ou desligado."""
    from . import alertas as al
    con = connect()
    try:
        r = al.resumo_diario(con, forcar=True)
        return {"enviado": r["enviado"], "para": r.get("para"), "erro": r.get("erro"), "numeros": r.get("numeros")}
    finally:
        con.close()


@router.post("/alertas/verificar")
def alertas_verificar(u: dict = Depends(auth.exige("admin"))) -> dict:
    from . import alertas as al
    con = connect()
    try:
        return {"envios": al.verificar(con)}
    finally:
        con.close()


@router.get("/replica")
def replica_estado(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Cartão 149: a cópia do acervo (réplica) — data da última cópia e o nível (ok/aviso/critico)."""
    from . import replica
    con = connect()
    try:
        return replica.estado(con)
    finally:
        con.close()
