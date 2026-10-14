"""Dashboard "Tarefas de hoje": qualidade da base (tarefas, índice por fundo, retrato diário), melhorias por pessoa e o "Agora não".

Fonte ÚNICA destas regras: /api/hoje (fila com prioridade), /api/painel (grupo "Melhorar a base" de "O que fazer agora")
e a página do fundo usam as funções daqui, para os números nunca divergirem entre as telas.

Regras:
- tarefas da base, cada uma levando à tela onde se corrige:
    fundo sem sigla (página do fundo) · projeto sem ano ou sem cidade (página do projeto) ·
    folhas sem título (a folha, se é uma só; senão o projeto) · arquiteto sem fonte da biografia (a ficha do arquiteto);
  prioridade por impacto: o que já está publicado vem antes, e dentro do mesmo tipo, o que atinge mais folhas/projetos;
- índice de qualidade de um fundo = média de 4 percentuais sobre as folhas dele:
    com imagem (JPG ou TIFF no painel, imagem já enviada ao site, ou o item do site tem imagem) · com código completo (F000-P0000-AAAA-S00-D0000, ano diferente de 0000) ·
    com título · com direitos definidos (a situação dos direitos do fundo não é "não definida");
  o geral usa todas as folhas juntas. Projeto mesclado e lote de teste não contam;
- retrato diário em qualidade_retrato: a seta compara o índice de hoje com o do retrato de 7 dias atrás (ou o mais recente antes disso);
- melhorias de uma pessoa = eventos feitos por ela (ator = e-mail de um usuário) em fundo, projeto, folha ou arquiteto, exceto criar/importar;
- "Agora não" esconde a tarefa só para quem clicou, por 7 dias (tarefa_adiada).
"""
from __future__ import annotations

from datetime import datetime, timedelta

DIAS_ADIAR = 7
POR_TIPO = 3                         # na fila do dia, no máximo 3 de cada tipo (o resto aparece no total)


def agora() -> datetime:
    """Relógio da regra (horário local do servidor). Os testes trocam esta função para simular a passagem dos dias."""
    return datetime.now()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------- "Agora não" ----------------
def adiadas(con, usuario_id: int | None) -> set[str]:
    if not usuario_id:
        return set()
    try:
        return {r[0] for r in con.execute("SELECT tarefa_id FROM tarefa_adiada WHERE usuario_id=? AND ate>?", (usuario_id, _iso(agora())))}
    except Exception:  # noqa: BLE001  (banco sem a migração 105: nada adiado)
        return set()


def adiar(con, usuario_id: int, tarefa_id: str, dias: int = DIAS_ADIAR) -> str:
    ate = _iso(agora() + timedelta(days=dias))
    con.execute("""INSERT INTO tarefa_adiada (usuario_id, tarefa_id, ate, criado_em) VALUES (?,?,?,?)
                   ON CONFLICT(usuario_id, tarefa_id) DO UPDATE SET ate=excluded.ate, criado_em=excluded.criado_em""",
                (usuario_id, tarefa_id, ate, _iso(agora())))
    return ate


# ---------------- tarefas de qualidade da base ----------------
def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _nome(tipo: str, nome: str | None) -> str:
    """'Projeto Casa X', sem repetir a palavra quando o nome já começa com ela ('Projeto de teste…')."""
    nome = (nome or "").strip()
    return nome if nome.lower().startswith(tipo.lower()) else f"{tipo} {nome}"


def tarefas_qualidade(con, usuario_id: int | None = None) -> list[dict]:
    """Todas as tarefas da base, da mais importante para a menos, sem as que a pessoa adiou."""
    out: list[dict] = []
    # 1) fundo sem sigla: a sigla vai no nome dos arquivos; sem ela, o material do fundo não anda
    for f in con.execute("""SELECT f.codigo, f.titulo, f.status_site,
                                   (SELECT COUNT(*) FROM projeto p WHERE p.fundo_codigo=f.codigo AND p.mesclado_em IS NULL) AS projetos
                              FROM fundo f WHERE f.ativo=1 AND COALESCE(TRIM(f.sigla),'')=''"""):
        out.append({"id": "q_sigla_" + f["codigo"], "tipo": "fundo_sem_sigla", "prioridade": 55, "impacto": f["projetos"] or 0,
                    "rota": "fundo/" + f["codigo"], "codigo": f["codigo"], "rotulo": "Dar a sigla",
                    "titulo": f"{_nome('Fundo', f['titulo'])} sem sigla",
                    "detalhe": "A sigla de 3 letras vai no nome dos arquivos" + (f" · {_plural(f['projetos'], 'projeto', 'projetos')}" if f["projetos"] else "")})
    # 2) projeto sem ano ou sem cidade
    for p in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.status_site,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                              FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo
                             WHERE f.ativo=1 AND p.mesclado_em IS NULL AND p.lote_teste=0
                               AND (COALESCE(p.ano,0)=0 OR COALESCE(TRIM(p.cidade),'')='')"""):
        falta = [x for x, vazio in (("ano", not p["ano"]), ("cidade", not (p["cidade"] or "").strip())) if vazio]
        pub = p["status_site"] == "no_ar"
        out.append({"id": "q_proj_" + p["codigo"], "tipo": "projeto_sem_ano_cidade", "prioridade": 50 if pub else 25, "impacto": p["folhas"] or 0,
                    "rota": "projeto/" + p["codigo"], "codigo": p["codigo"], "rotulo": "Completar",
                    "titulo": f"{_nome('Projeto', p['titulo'])} sem {' e sem '.join(falta)}",
                    "detalhe": ("Já está publicado no site" if pub else "Ainda não publicado") + (f" · {_plural(p['folhas'], 'folha', 'folhas')}" if p["folhas"] else "")})
    # 3) folhas sem título, juntas por projeto (uma tarefa por projeto)
    for r in con.execute("""SELECT p.codigo, p.titulo, p.status_site, COUNT(*) AS n, MIN(i.codigo) AS primeira
                              FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                             WHERE f.ativo=1 AND p.mesclado_em IS NULL AND p.lote_teste=0 AND COALESCE(TRIM(i.titulo),'')=''
                             GROUP BY p.codigo"""):
        pub = r["status_site"] == "no_ar"
        out.append({"id": "q_titulo_" + r["codigo"], "tipo": "folha_sem_titulo", "prioridade": 45 if pub else 22, "impacto": r["n"],
                    "rota": ("item/" + r["primeira"]) if r["n"] == 1 else ("projeto/" + r["codigo"]),
                    "codigo": r["primeira"] if r["n"] == 1 else r["codigo"], "rotulo": "Dar título",
                    "titulo": f"{_plural(r['n'], 'folha sem título', 'folhas sem título')} em {r['titulo']}",
                    "detalhe": "O projeto já está publicado no site" if pub else "Leia o título no carimbo da folha"})
    # 4) arquiteto sem fonte da biografia
    for a in con.execute("""SELECT a.id, a.forma_autorizada, a.status_site, a.historia,
                                   (SELECT COUNT(*) FROM fundo_agente fa WHERE fa.agente_id=a.id) AS fundos
                              FROM agente a WHERE COALESCE(TRIM(a.fonte_historia),'')=''"""):
        pub = a["status_site"] == "no_ar"
        out.append({"id": f"q_agente_{a['id']}", "tipo": "agente_sem_fonte", "prioridade": 35 if pub else 20, "impacto": a["fundos"] or 0,
                    "rota": f"arquitetos/{a['id']}", "codigo": None, "rotulo": "Citar a fonte",
                    "titulo": f"{_nome('Arquiteto', a['forma_autorizada'])} sem fonte",
                    "detalhe": "Toda biografia precisa dizer de onde veio a informação" + (" · a página dele já está publicada" if pub else "")})
    esconder = adiadas(con, usuario_id)
    out = [t for t in out if t["id"] not in esconder]
    out.sort(key=lambda t: (-t["prioridade"], -t["impacto"], t["id"]))
    return out


TIPOS = {"fundo_sem_sigla": ("fundo sem sigla", "fundos sem sigla"), "projeto_sem_ano_cidade": ("projeto sem ano ou sem cidade", "projetos sem ano ou sem cidade"),
         "folha_sem_titulo": ("projeto com folhas sem título", "projetos com folhas sem título"), "agente_sem_fonte": ("arquiteto sem fonte", "arquitetos sem fonte")}


def fila_do_dia(tarefas: list[dict], por_tipo: int = POR_TIPO) -> list[dict]:
    """As primeiras de cada tipo (no máximo por_tipo), na ordem de prioridade: a fila não vira só um tipo."""
    vistos: dict[str, int] = {}
    fila = []
    for t in tarefas:
        if vistos.get(t["tipo"], 0) < por_tipo:
            vistos[t["tipo"]] = vistos.get(t["tipo"], 0) + 1
            fila.append(t)
    return fila


def resumo_tipos(tarefas: list[dict]) -> list[dict]:
    n: dict[str, int] = {}
    for t in tarefas:
        n[t["tipo"]] = n.get(t["tipo"], 0) + 1
    return [{"tipo": k, "rotulo": TIPOS[k][0 if n[k] == 1 else 1], "n": n[k]} for k in TIPOS if n.get(k)]


# ---------------- índice de qualidade por fundo ----------------
GLOB_CODIGO = "F[0-9][0-9][0-9]-P[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]-S0[1-9]-D[0-9][0-9][0-9][0-9]*"
CRITERIOS = ("com_imagem", "com_codigo", "com_titulo", "com_direitos")


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def _completar(d: dict) -> dict:
    n = d["folhas"]
    d["pct"] = {c: _pct(d[c], n) for c in CRITERIOS}
    d["indice"] = round(sum(d["pct"].values()) / len(CRITERIOS), 1) if n else None
    return d


def indices(con) -> dict:
    """{'geral': {...}, 'fundos': [{codigo, sigla, titulo, folhas, com_*, pct, indice}]} calculado agora."""
    fundos = []
    for r in con.execute(f"""SELECT f.codigo, f.sigla, f.titulo, COUNT(i.codigo) AS folhas,
               COALESCE(SUM(CASE WHEN COALESCE(i.arquivo_jpg,'')!='' OR COALESCE(i.arquivo_tif,'')!='' OR i.site_media_id IS NOT NULL
                         OR EXISTS (SELECT 1 FROM wp_item w WHERE w.id=i.tainacan_item_id AND (COALESCE(w.documento_url,'')!='' OR COALESCE(w.thumb_url,'')!='')) THEN 1 ELSE 0 END),0) AS com_imagem,
               COALESCE(SUM(CASE WHEN i.codigo GLOB '{GLOB_CODIGO}' AND i.codigo NOT GLOB '*-P[0-9][0-9][0-9][0-9]-0000-*' THEN 1 ELSE 0 END),0) AS com_codigo,
               COALESCE(SUM(CASE WHEN COALESCE(TRIM(i.titulo),'')!='' THEN 1 ELSE 0 END),0) AS com_titulo,
               CASE WHEN COALESCE(d.situacao,'nao_definida')!='nao_definida' THEN COUNT(i.codigo) ELSE 0 END AS com_direitos
          FROM fundo f
          LEFT JOIN direitos_fundo d ON d.fundo_codigo=f.codigo
          LEFT JOIN projeto p ON p.fundo_codigo=f.codigo AND p.mesclado_em IS NULL AND p.lote_teste=0
          LEFT JOIN item i ON i.projeto_codigo=p.codigo
         WHERE f.ativo=1 GROUP BY f.codigo ORDER BY f.codigo"""):
        fundos.append(_completar(dict(r)))
    geral = {"codigo": "*", "folhas": sum(f["folhas"] for f in fundos), **{c: sum(f[c] for f in fundos) for c in CRITERIOS}}
    return {"geral": _completar(geral), "fundos": fundos}


def gravar_retrato(con, ind: dict | None = None) -> dict:
    """Grava (ou regrava) o retrato de HOJE. Devolve os índices usados."""
    ind = ind or indices(con)
    dia = agora().date().isoformat()
    for d in [ind["geral"], *ind["fundos"]]:
        con.execute("""INSERT INTO qualidade_retrato (dia, fundo_codigo, folhas, com_imagem, com_codigo, com_titulo, com_direitos, indice, gravado_em)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(dia, fundo_codigo) DO UPDATE SET folhas=excluded.folhas, com_imagem=excluded.com_imagem, com_codigo=excluded.com_codigo,
                         com_titulo=excluded.com_titulo, com_direitos=excluded.com_direitos, indice=excluded.indice, gravado_em=excluded.gravado_em""",
                    (dia, d["codigo"], d["folhas"], d["com_imagem"], d["com_codigo"], d["com_titulo"], d["com_direitos"], d["indice"], _iso(agora())))
    con.commit()
    return ind


def tendencia(con, fundo_codigo: str, indice_hoje: float | None) -> dict:
    """Compara com o retrato de 7 dias atrás (ou o mais recente antes disso). seta: sobe | desce | igual | None (sem retrato antigo)."""
    limite = (agora().date() - timedelta(days=7)).isoformat()
    r = con.execute("SELECT dia, indice FROM qualidade_retrato WHERE fundo_codigo=? AND dia<=? AND indice IS NOT NULL ORDER BY dia DESC LIMIT 1",
                    (fundo_codigo, limite)).fetchone()
    if not r or indice_hoje is None:
        return {"seta": None, "antes": None, "dia_antes": None, "diferenca": None}
    dif = round(indice_hoje - r["indice"], 1)
    return {"seta": "sobe" if dif > 0 else "desce" if dif < 0 else "igual", "antes": r["indice"], "dia_antes": r["dia"], "diferenca": dif}


def _indices_com_retrato(con) -> dict:
    """Índices de agora; grava o retrato do dia só se ainda não houver (a tarefa de hora em hora o mantém em dia).
    Abrir o painel não deve virar uma escrita no banco a cada visita."""
    ind = indices(con)
    if not con.execute("SELECT 1 FROM qualidade_retrato WHERE dia=? LIMIT 1", (agora().date().isoformat(),)).fetchone():
        gravar_retrato(con, ind)
    return ind


def visao_geral(con) -> dict:
    """Índices de agora (e o retrato do dia, se faltar), com a tendência de cada um. Fundos sem folhas ficam de fora da lista."""
    ind = _indices_com_retrato(con)
    ind["geral"]["tendencia"] = tendencia(con, "*", ind["geral"]["indice"])
    for f in ind["fundos"]:
        f["tendencia"] = tendencia(con, f["codigo"], f["indice"])
    ind["fundos"] = sorted([f for f in ind["fundos"] if f["folhas"]], key=lambda f: (f["indice"], f["codigo"]))
    return ind


def do_fundo(con, codigo: str) -> dict | None:
    ind = _indices_com_retrato(con)
    f = next((x for x in ind["fundos"] if x["codigo"] == codigo), None)
    if not f:
        return None
    f["tendencia"] = tendencia(con, codigo, f["indice"])
    desde = (agora().date() - timedelta(days=30)).isoformat()
    f["historico"] = [dict(r) for r in con.execute("SELECT dia, indice FROM qualidade_retrato WHERE fundo_codigo=? AND dia>=? ORDER BY dia", (codigo, desde))]
    return f


# ---------------- melhorias de hoje, por pessoa ----------------
TIPOS_NAO_CONTAM = ("criado", "criada", "importado", "sincronizado")


def melhorias(con) -> dict:
    hoje = agora().date()
    semana = hoje - timedelta(days=6)
    marcas = ",".join("?" * len(TIPOS_NAO_CONTAM))
    linhas = con.execute(f"""SELECT u.nome, u.email,
                SUM(CASE WHEN date(e.quando,'localtime')=? THEN 1 ELSE 0 END) AS hoje,
                COUNT(*) AS semana
           FROM evento e JOIN usuario u ON lower(u.email)=lower(e.ator)
          WHERE e.entidade IN ('fundo','projeto','item','agente') AND e.tipo NOT IN ({marcas})
            AND date(e.quando,'localtime') BETWEEN ? AND ?
          GROUP BY u.id ORDER BY hoje DESC, semana DESC, u.nome""",
                         (hoje.isoformat(), *TIPOS_NAO_CONTAM, semana.isoformat(), hoje.isoformat())).fetchall()
    pessoas = [{"nome": r["nome"], "email": r["email"], "hoje": r["hoje"] or 0, "semana": r["semana"] or 0} for r in linhas]
    return {"dia": hoje.isoformat(), "desde": semana.isoformat(), "pessoas": pessoas,
            "total_hoje": sum(p["hoje"] for p in pessoas), "total_semana": sum(p["semana"] for p in pessoas)}

