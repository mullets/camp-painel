"""Uso do acervo: traz as entradas do formulário de download do site (Fluent Forms) para o painel.

Dados pessoais (LGPD): só admin/master veem (rotas_uso). Não se guarda IP. "Apagar pessoa" anonimiza (nome, e-mail, telefone,
instituição e as respostas somem; o uso e o material ficam para as contagens) e a linha anonimizada NUNCA é importada de novo.
O "uso" é sempre o DECLARADO pela pessoa. "Pediu para baixar" não é "baixou": ver docs/uso-do-acervo.md.
"""
from __future__ import annotations

import json
import re

from .sondagem_fluentforms import PADRAO_MATERIAL, PADRAO_USO, _get, _json_ou_dict, _lista, _total

CODIGO = re.compile(r"F\d{3}-P\d{4}(?:-\d{4}-S\d{2}-D\d{5})?", re.I)
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
POR_PAGINA = 100
ENDPOINTS = ("/wp-json/fluentform/v1/submissions", "/wp-json/fluentform/v1/forms/{fid}/submissions")


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return " ".join(t for t in (_txt(x) for x in v.values()) if t).strip()
    if isinstance(v, list):
        return ", ".join(t for t in (_txt(x) for x in v) if t)
    return str(v).strip()


def derivar(resp, pagina: str | None = None) -> dict:
    """Extrai nome, e-mail, telefone, instituição, uso e material de uma resposta (as chaves são os nomes dos campos do formulário)."""
    out = {"nome": None, "email": None, "telefone": None, "instituicao": None, "uso": None,
           "material_codigo": None, "material_origem": None, "projeto_codigo": None, "fundo_codigo": None}
    resp = resp if isinstance(resp, dict) else {}
    for k, v in resp.items():
        kl, t = str(k).lower(), _txt(v)
        if not t:
            continue
        if "mail" in kl and EMAIL.fullmatch(t) and not out["email"]:
            out["email"] = t.lower()
        elif re.search(r"tel|fone|phone|whats|celular", kl) and not out["telefone"]:
            out["telefone"] = t
        elif re.search(r"universidade|empresa|institui|organiza|escola|faculdade", kl) and not out["instituicao"]:
            out["instituicao"] = t
        elif PADRAO_USO.search(kl) and not out["uso"]:
            out["uso"] = t
        elif re.search(r"nome|name", kl) and not out["nome"]:
            out["nome"] = t
    if not out["email"]:
        for v in resp.values():
            t = _txt(v)
            if EMAIL.fullmatch(t):
                out["email"] = t.lower()
                break
    achado = None
    for k, v in resp.items():                      # 1) campo com nome de material (campo oculto com o código)
        m = CODIGO.search(_txt(v)) if PADRAO_MATERIAL.search(str(k)) else None
        if m:
            achado = (m.group(0), "campo")
            break
    if not achado:                                 # 2) qualquer valor com um código CAMP
        for v in resp.values():
            m = CODIGO.search(_txt(v))
            if m:
                achado = (m.group(0), "valor")
                break
    if not achado and pagina:                      # 3) a ficha de onde o modal foi aberto (endereço da página)
        m = CODIGO.search(pagina)
        if m:
            achado = (m.group(0), "pagina")
    if achado:
        cod = achado[0].upper()
        partes = cod.split("-")
        out.update(material_codigo=cod, material_origem=achado[1], fundo_codigo=partes[0], projeto_codigo="-".join(partes[:2]))
    return out


def achar_form(h, con) -> tuple[int | None, str | None, str | None]:
    """(id, título, erro). Usa uso.form_id; senão procura 'download' (de preferência) ou 'material' no título."""
    cfg = con.execute("SELECT valor FROM configuracao WHERE chave='uso.form_id'").fetchone()
    fid = int(cfg[0]) if cfg and str(cfg[0]).strip().isdigit() else None
    st, dados = _get(h, "/wp-json/fluentform/v1/forms", per_page=100)
    if st in (401, 403):
        return None, None, f"o site recusou a lista de formulários (HTTP {st}): o usuário do painel no WordPress precisa ser administrador do Fluent Forms"
    forms = _lista(dados)
    if st != 200 or not forms:
        return None, None, f"não consegui listar os formulários do site (HTTP {st})"
    if fid:
        f = next((x for x in forms if str(x.get("id")) == str(fid)), None)
        return (fid, (f or {}).get("title"), None) if f else (None, None, f"o formulário {fid} (uso.form_id) não existe no site")
    for padrao in (r"download", r"material"):
        f = next((x for x in forms if re.search(padrao, str(x.get("title", "")), re.I)), None)
        if f:
            return int(f["id"]), f.get("title"), None
    return None, None, "nenhum formulário com 'download' ou 'material' no título; informe o id em Configurações (uso.form_id)"


def puxar(h, con, completo: bool = False, form_id: int | None = None) -> dict:
    """Traz as entradas. completo=True lê TODO o histórico; senão para na primeira página só com entradas já conhecidas."""
    r = {"form_id": None, "form_titulo": None, "endpoint": None, "lidas": 0, "novas": 0, "puladas": 0, "total_remoto": None, "erro": None, "completo": completo}
    try:
        fid, titulo, erro = (form_id, None, None) if form_id else achar_form(h, con)
        r["form_id"], r["form_titulo"] = fid, titulo
        if erro or not fid:
            r["erro"] = erro
            return r
        conhecidos = {x[0] for x in con.execute("SELECT origem_id FROM uso_download WHERE form_id=?", (fid,))}
        vistos: set[int] = set()
        pagina, st, caminho = 1, None, None
        for modelo in ENDPOINTS:                   # acha o endereço das entradas que responde
            c = modelo.format(fid=fid)
            st, d = _get(h, c, form_id=fid, per_page=POR_PAGINA, page=1)
            if st == 200 and (_lista(d) or _total(d) is not None):
                caminho = c
                break
        if not caminho:
            r["erro"] = f"não consegui ler as entradas do formulário {fid} (HTTP {st})"
            return r
        r["endpoint"] = caminho
        while pagina <= 200:
            if pagina > 1:
                st, d = _get(h, caminho, form_id=fid, per_page=POR_PAGINA, page=pagina)
                if st != 200:
                    r["erro"] = f"a página {pagina} das entradas respondeu HTTP {st}"
                    break
            itens = _lista(d)
            if r["total_remoto"] is None:
                r["total_remoto"] = _total(d)
            novos_ids = {int(e["id"]) for e in itens if str(e.get("id", "")).isdigit()} - vistos
            if not itens or not novos_ids:         # acabou, ou o servidor ignora o número da página
                break
            tudo_conhecido = True
            for e in itens:
                if not str(e.get("id", "")).isdigit():
                    continue
                oid = int(e["id"])
                vistos.add(oid)
                r["lidas"] += 1
                if str(e.get("status", "")).lower() in ("trashed", "spam"):
                    r["puladas"] += 1
                    continue
                if oid in conhecidos:
                    continue
                tudo_conhecido = False
                resp = _json_ou_dict(e.get("response") if "response" in e else e)
                pag = e.get("source_url") or e.get("source") or None
                dv = derivar(resp, pag)
                con.execute("""INSERT OR IGNORE INTO uso_download (form_id, origem_id, recebida_em, nome, email, telefone, instituicao, uso,
                                  material_codigo, material_origem, projeto_codigo, fundo_codigo, pagina, resposta_json)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (fid, oid, str(e.get("created_at") or e.get("date") or "") or None, dv["nome"], dv["email"], dv["telefone"], dv["instituicao"],
                             dv["uso"], dv["material_codigo"], dv["material_origem"], dv["projeto_codigo"], dv["fundo_codigo"], pag,
                             json.dumps(resp, ensure_ascii=False)))
                conhecidos.add(oid)
                r["novas"] += 1
            if not completo and tudo_conhecido:
                break
            if r["total_remoto"] and len(vistos) >= r["total_remoto"]:
                break
            pagina += 1
    except Exception as e:  # noqa: BLE001  (a coleta nunca derruba o painel; o erro fica registrado)
        r["erro"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        con.execute("INSERT INTO uso_coleta (form_id, endpoint, lidas, novas, completo, erro) VALUES (?,?,?,?,?,?)",
                    (r["form_id"], r["endpoint"], r["lidas"], r["novas"], int(completo), r["erro"]))
        con.commit()
    return r


def reprocessar(con) -> int:
    """Refaz as colunas (nome, material...) a partir das respostas guardadas, sem ir ao site."""
    n = 0
    for u in con.execute("SELECT id, resposta_json, pagina FROM uso_download WHERE anonimizada=0 AND apagada=0 AND resposta_json IS NOT NULL").fetchall():
        dv = derivar(_json_ou_dict(u["resposta_json"]), u["pagina"])
        con.execute("""UPDATE uso_download SET nome=?, email=?, telefone=?, instituicao=?, uso=?, material_codigo=?, material_origem=?,
                          projeto_codigo=?, fundo_codigo=? WHERE id=?""",
                    (dv["nome"], dv["email"], dv["telefone"], dv["instituicao"], dv["uso"], dv["material_codigo"], dv["material_origem"],
                     dv["projeto_codigo"], dv["fundo_codigo"], u["id"]))
        n += 1
    con.commit()
    return n


def anonimizar_pessoa(con, email: str) -> int:
    """Apaga os dados pessoais de todas as entradas com este e-mail (a pedido da pessoa). Mantém uso e material para as contagens."""
    cur = con.execute("""UPDATE uso_download SET nome='(removido)', email=NULL, telefone=NULL, instituicao=NULL, resposta_json=NULL, anonimizada=1
                          WHERE lower(email)=lower(?) AND anonimizada=0 AND apagada=0""", (email.strip(),))
    con.commit()
    return cur.rowcount


def apagar_ids(con, ids: list[int]) -> int:
    """Apaga entradas DE VERDADE: remove todos os dados (pessoais e de uso) e deixa só a marca (form_id, origem_id) com apagada=1.
    A marca impede que uma coleta futura traga a entrada de volta; ela some de listas, contagens e exportações."""
    n = 0
    ids = sorted({int(i) for i in ids})
    for k in range(0, len(ids), 500):
        parte = ids[k:k + 500]
        cur = con.execute(f"""UPDATE uso_download SET apagada=1, apagada_em=datetime('now'), anonimizada=1, recebida_em=NULL, nome=NULL, email=NULL, telefone=NULL,
                                 instituicao=NULL, uso=NULL, material_codigo=NULL, material_origem=NULL, projeto_codigo=NULL, fundo_codigo=NULL,
                                 pagina=NULL, resposta_json=NULL
                               WHERE apagada=0 AND id IN ({",".join("?" * len(parte))})""", parte)
        n += cur.rowcount
    con.commit()
    return n
