"""Cartão 152: Qualidade do CAMP Vision (só admin): quanto ele acerta por campo e por versão, e quanto custa cada lote.
Fonte: revisao_campo (o que a revisão fez com cada campo lido) e lista_processamento.execucao_json (o bloco 'execucao' do pacote)."""
import csv
import io
import json
import re

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["qualidade"])
ROTULO_CAMPO = {"titulo": "Título", "tipo_documento": "Tipo", "folha": "Folha", "escala": "Escala", "ano_folha": "Ano da folha"}


RESPOSTA_QUEBRADA = "valor descartado: resposta do modelo quebrada"      # o texto que o CAMP Vision põe por campo (UX-37/UX-60, saneamento.RESSALVA)
_CAMPO_QUEBRADO = re.compile(re.escape(RESPOSTA_QUEBRADA) + r"\s*\(([^),]+)")


def folhas_resposta_quebrada(con, limite: int = 300) -> dict:
    """UX-60 (parte do painel): folhas que ficaram sem leitura (algum campo descartado) porque a resposta do modelo veio quebrada.
    Conta pelo que o painel JÁ recebe: os avisos por campo com esse texto (tabela erro, qualquer situação) e as ressalvas guardadas
    na folha (item.pendencias). Uma folha conta uma vez, com os campos juntos. Só leitura."""
    folhas: dict[str, dict] = {}

    def anota(cod, texto, existe=None, revisao=None):
        cod = str(cod or "").strip()
        if cod.count("-") < 4:
            return
        f = folhas.setdefault(cod, {"codigo": cod, "projeto_codigo": cod[:10], "campos": [], "existe": False, "revisao": None})
        for c in _CAMPO_QUEBRADO.findall(texto or ""):
            if c.strip() not in f["campos"]:
                f["campos"].append(c.strip())
        if existe:
            f["existe"], f["revisao"] = True, revisao
    padrao = f"%{RESPOSTA_QUEBRADA}%"
    for r in con.execute("SELECT codigo, descricao FROM erro WHERE descricao LIKE ?", (padrao,)):
        anota(r["codigo"], r["descricao"])
    for r in con.execute("SELECT codigo, pendencias, revisao FROM item WHERE pendencias LIKE ?", (padrao,)):
        anota(r["codigo"], r["pendencias"], True, r["revisao"])
    if folhas:
        cods = list(folhas)
        for i in range(0, len(cods), 400):
            parte = cods[i:i + 400]
            for r in con.execute(f"SELECT codigo, revisao FROM item WHERE codigo IN ({','.join('?' * len(parte))})", parte):
                folhas[r["codigo"]].update(existe=True, revisao=r["revisao"])
    lista = sorted(folhas.values(), key=lambda f: f["codigo"])
    return {"folhas": len(lista), "projetos": len({f["projeto_codigo"] for f in lista}), "lista": lista[:limite]}


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
        return {"por_campo": campos, "por_lote": lotes, "por_versao": sorted(versoes.values(), key=lambda x: x["versao"], reverse=True),
                "resposta_quebrada": folhas_resposta_quebrada(con)}      # UX-60 (campo novo, opcional)
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
        from .rotas_gestao import site_em_cache
        # UX-07: o estado de AGORA, das mesmas medições da tela Máquinas (o site pela última sonda, sem esperar a rede);
        # "Verificar agora" mede o site de novo e grava o estado (o e-mail sai pela mesma regra)
        agora_ = {k: {**v, "assunto": k, "ligado": al.ligado(con, k)} for k, v in al.avaliar(con, medir_site=lambda url: site_em_cache(url) or {"nao_medido": "o site ainda não foi verificado desde que o painel ligou; use Verificar agora"}).items()}
        return {"agora": agora_,
                "estado": [dict(r) for r in con.execute("SELECT * FROM alerta_estado ORDER BY assunto")],
                "envios": [dict(r) for r in con.execute("SELECT * FROM alerta_envio ORDER BY id DESC LIMIT 50")],
                "resumo": al.resumo_estado(con)}
    finally:
        con.close()


@router.get("/alertas/preferencias")
def alertas_preferencias(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cartão "Notificações": cada assunto de aviso, se está ligado e quem recebe (vazio = a lista geral avisos.email)."""
    from . import alertas as al
    con = connect()
    try:
        return al.preferencias(con)
    finally:
        con.close()


@router.put("/alertas/preferencias")
def alertas_preferencias_salvar(d: dict = Body(...), u: dict = Depends(auth.exige("admin"))) -> dict:
    """Só admin. Grava liga/desliga e destinatários por assunto (as mesmas chaves avisos.* das Configurações, com registro na Auditoria)."""
    from . import alertas as al
    con = connect()
    try:
        return al.salvar_preferencias(con, d if isinstance(d, dict) else {}, u["email"])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
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
        est = replica.estado(con)
        replica.registrar_marca(con, est)          # UX-02: guarda a última cópia válida vista
        con.commit()
        return {**est, "ultima_valida": replica.ultima_valida(con), "preservacao": replica.preservacao(con, est)}
    finally:
        con.close()


@router.get("/campvision/relatorio")
def relatorio_cv(dias: int = 30, u: dict = Depends(auth.exige("admin"))) -> dict:
    """02/11: o que o CAMP Vision fez (dia a dia, com os projetos) e quanto gastou; por fundo. Fonte: o diário dele (cv_eventos)."""
    from . import cv_eventos
    con = connect()
    try:
        return cv_eventos.resumo(con, dias)
    finally:
        con.close()


@router.get("/fundos/{codigo}/gasto-cv")
def gasto_cv_fundo(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """02/11: quanto o CAMP Vision já gastou lendo este fundo (total, por mês, por prancha)."""
    from . import cv_eventos
    con = connect()
    try:
        return cv_eventos.gasto_fundo(con, codigo.strip().upper())
    finally:
        con.close()
