"""Edição dos textos de uma folha (item): catalogação no painel + textos públicos no Tainacan.

Regras:
- Salva SEMPRE primeiro no painel; o envio ao site é uma segunda etapa que nunca desfaz a primeira.
- Só oferece para edição os campos que existem de verdade na coleção do site e cujo tipo sabemos gravar
  (texto, texto longo e taxonomia). Taxonomia só aceita termo que já existe.
- Auditoria com antes/depois.
"""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import auth, dados_foto, parceiros
from .db import connect
from .publicador import _meta, atualizar_folha_no_site
from .rotas_projetos import _colecao_config

router = APIRouter(prefix="/api", tags=["itens"])

LIMITES_LOCAIS = {"titulo": 300, "tipo_documento": 120, "folha": 40, "escala": 60, "dimensoes": 120, "suporte": 160, "credito": 300,
                  "endereco_folha": 300, "cliente_folha": 200}   # endereço e cliente lidos no carimbo da folha (consenso do lote)
ROTULOS_LOCAIS = {"titulo": "Título", "tipo_documento": "Tipo", "folha": "Folha", "escala": "Escala", "dimensoes": "Dimensões", "suporte": "Suporte",
                  "credito": "Crédito", "endereco_folha": "Endereço da obra", "cliente_folha": "Cliente"}
SITE_METADADOS = ("Tipo de desenho", "Técnica", "Suporte", "Endereço", "Cliente", "Fotógrafo",
                  "Data do registro fotográfico", "Informação atribuída pela catalogação")
LIM_TEXTO_SITE = 5000
LIM_TITULO_SITE = 300


def _tipo_edicao(tipo: str | None) -> str | None:
    t = tipo or ""
    if "Taxonomy" in t:
        return "taxonomia"
    if "Textarea" in t:
        return "textarea"
    if t.endswith("\\Text") or t.endswith("Text"):
        return "texto"
    return None


def _item_e_site(con, codigo: str):
    i = con.execute("SELECT * FROM item WHERE codigo=?", (codigo,)).fetchone()
    if not i:
        raise HTTPException(404, "Folha não existe")
    cid = _colecao_config(con, "tainacan.itens_collection_id", 8013)
    w = con.execute("""SELECT id, colecao_id, status, titulo, metadados, json FROM wp_item
                        WHERE codigo_detectado=? AND colecao_id=? ORDER BY id DESC LIMIT 1""", (codigo, cid)).fetchone()
    return i, w


def _descricao_do_site(w) -> str:
    try:
        j = json.loads(w["json"] or "{}")
    except ValueError:
        j = {}
    d = j.get("description")
    if d is None:
        try:
            d = (json.loads(w["metadados"] or "{}")).get("Descrição")
        except ValueError:
            d = None
    return d or ""


def _campos_do_site(con, w) -> tuple[list[dict], list[dict]]:
    """(editaveis, somente_leitura) segundo os metadados que existem na coleção do item."""
    try:
        valores = json.loads(w["metadados"] or "{}")
    except ValueError:
        valores = {}
    editaveis, leitura = [], []
    for nome in SITE_METADADOS:
        mid, tipo = _meta(con, w["colecao_id"], nome)
        if not mid:
            continue
        kind = _tipo_edicao(tipo)
        atual = valores.get(nome) or (valores.get("Suporte original") if nome == "Suporte" else "") or ""   # CAMP-035: o site velho ainda pode chamar de "Suporte original"
        if not kind:
            if atual:
                leitura.append({"nome": nome, "valor": atual, "motivo": "tipo de campo não editável aqui"})
            continue
        campo = {"nome": nome, "tipo": kind, "valor": atual}
        if kind == "taxonomia":
            tax = con.execute("SELECT taxonomia_id FROM wp_metadado WHERE id=?", (mid,)).fetchone()
            tid = tax[0] if tax else None
            campo["opcoes"] = [r[0] for r in con.execute("SELECT nome FROM wp_termo WHERE taxonomia_id=? ORDER BY nome", (tid,))] if tid else []
        editaveis.append(campo)
    return editaveis, leitura


@router.get("/itens/{codigo}/edicao")
def dados_edicao(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        i, w = _item_e_site(con, codigo)
        d = {"codigo": codigo, "status_site": i["status_site"], "no_site": bool(w),
             "local": {**{k: i[k] for k in (*LIMITES_LOCAIS, "ano_folha")}, "tipo_documento": i["tipos_documento"] or i["tipo_documento"]},
             "tipos_documento": [r[0] for r in con.execute("SELECT nome FROM tipo_documento ORDER BY nome")],
             "site": None}
        d["local"]["parceiros"] = parceiros.ler(i["parceiros"])        # 19/10: escritórios parceiros / projetos complementares
        d["local"].update({k: i[k] for k in dados_foto.CAMPOS})      # 21/10: ano da foto, estágio, fotógrafo
        d["disciplinas"] = list(parceiros.DISCIPLINAS)
        d["fundo_codigo"] = codigo.split("-")[0]
        from .rotas_revisao import imagem_site_pendente
        d["imagem_site_pendente"] = imagem_site_pendente(con, codigo)      # 19/10: girada/espelhada no painel, o site ainda tem a antiga
        if w:
            editaveis, leitura = _campos_do_site(con, w)
            d["site"] = {"status": w["status"], "titulo": w["titulo"] or "", "descricao": _descricao_do_site(w),
                         "campos": editaveis, "somente_leitura": leitura}
        return d
    finally:
        con.close()


class EdicaoItem(BaseModel):
    titulo: str | None = None
    tipo_documento: str | None = None
    folha: str | None = None
    escala: str | None = None
    ano_folha: int | None = None
    dimensoes: str | None = None
    suporte: str | None = None
    credito: str | None = None
    endereco_folha: str | None = None
    cliente_folha: str | None = None
    titulo_site: str | None = None
    descricao_site: str | None = None
    metadados_site: dict[str, str] | None = None
    parceiros: list | None = None     # [{"escritorio", "disciplina", "outra"?}]; [] limpa; ausente = não mexe
    foto_ano: str | None = None       # 21/10 (opcional): ano da foto, estágio, fotógrafo; "" limpa; ausente = não mexe
    foto_estagio: str | None = None
    foto_fotografo: str | None = None
    vistos: dict | None = None        # CAMP-095 (opcional): o valor de cada campo mudado como a pessoa o VIU ao abrir a folha; se outra pessoa mudou antes, 409


@router.patch("/itens/{codigo}")
def editar_item(codigo: str, d: EdicaoItem, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        i, w = _item_e_site(con, codigo)
        # ---------- validação (nada é gravado se algo estiver inválido) ----------
        novos, antes = {}, {}
        for k, lim in LIMITES_LOCAIS.items():
            v = getattr(d, k)
            if v is None:
                continue
            v = v.strip()
            if k == "tipo_documento":   # 19/10: pode ter mais de um tipo ("Planta; Corte; Elevação/Fachada"); cada um tem de existir
                from .tipos_documento import separar, juntar
                atual = i["tipos_documento"] or i["tipo_documento"]
                ja_tem = {t.lower(): t for t in separar(atual)}
                lista = []
                for t in separar(v):     # sem limite de caracteres na lista inteira (Sírio, 19/10): cada tipo é conferido no vocabulário
                    r = con.execute("SELECT nome FROM tipo_documento WHERE nome=? OR lower(nome)=lower(?) ORDER BY nome=? DESC LIMIT 1", (t, t, t)).fetchone()
                    if not r and t.lower() not in ja_tem:   # o tipo que a folha JÁ tem não impede salvar o resto
                        raise HTTPException(400, f"Tipo de documento '{t}' não existe no vocabulário")
                    lista.append(r[0] if r else ja_tem[t.lower()])
                if (juntar(lista) or None) != (atual or None):   # tipo_documento = o primeiro (ligado ao vocabulário); a lista inteira em tipos_documento
                    novos["tipo_documento"], novos["tipos_documento"] = (lista[0] if lista else None), (juntar(lista) if len(lista) > 1 else None)
                    antes["tipo_documento"] = atual
                continue
            v = v or None
            if v == ((i[k] or "").strip() or None):
                continue                 # Sírio, 19/10: a revisão manda todos os campos; o que não mudou não é validado de novo (o CAMP Vision pode ter lido mais longo que o limite)
            if v and len(v) > lim:
                raise HTTPException(400, f"{ROTULOS_LOCAIS.get(k, k)}: máximo de {lim} caracteres (tem {len(v)})")
            novos[k], antes[k] = v, i[k]
        if d.ano_folha is not None:
            if d.ano_folha != 0 and not (1800 <= d.ano_folha <= 2100):
                raise HTTPException(400, "Ano da folha inválido (0 para limpar)")
            v = d.ano_folha or None
            if v != i["ano_folha"]:
                novos["ano_folha"], antes["ano_folha"] = v, i["ano_folha"]
        lista_parceiros = None
        if d.parceiros is not None:                       # 19/10: escritórios parceiros; só grava se mudou (a revisão manda só o que mudou)
            lista_parceiros = parceiros.normalizar(d.parceiros)
            atual = parceiros.ler(i["parceiros"])
            if lista_parceiros != atual:
                novos["parceiros"], antes["parceiros"] = parceiros.para_coluna(lista_parceiros), atual
        for k in dados_foto.CAMPOS:                       # 21/10: dados da foto
            v = getattr(d, k)
            if v is None:
                continue
            v = dados_foto.normalizar(k, v)
            if v != (i[k] or None):
                novos[k], antes[k] = v, i[k]

        titulo_site = descricao_site = None
        md_envio: dict = {}
        site_antes: dict = {}
        quer_site = d.titulo_site is not None or d.descricao_site is not None or bool(d.metadados_site)
        if quer_site and not w:
            raise HTTPException(400, "Esta folha ainda não existe no site: só a catalogação do painel pode ser editada")
        if w:
            if d.titulo_site is not None:
                t = d.titulo_site.strip()
                if not t:
                    raise HTTPException(400, "O título da página no site não pode ficar vazio")
                if len(t) > LIM_TITULO_SITE:
                    raise HTTPException(400, f"Título no site: máximo de {LIM_TITULO_SITE} caracteres")
                if t != (w["titulo"] or ""):
                    titulo_site = t; site_antes["título da página"] = w["titulo"]
            if d.descricao_site is not None:
                t = d.descricao_site.strip()
                if len(t) > LIM_TEXTO_SITE:
                    raise HTTPException(400, f"Descrição: máximo de {LIM_TEXTO_SITE} caracteres")
                atual = _descricao_do_site(w)
                if t != atual:
                    descricao_site = t; site_antes["descrição"] = atual
            if d.metadados_site:
                editaveis = {c["nome"]: c for c in _campos_do_site(con, w)[0]}
                try:
                    valores_atuais = json.loads(w["metadados"] or "{}")
                except ValueError:
                    valores_atuais = {}
                for nome, bruto in d.metadados_site.items():
                    c = editaveis.get(nome)
                    if not c:
                        raise HTTPException(400, f"O campo '{nome}' não pode ser editado aqui (não existe na coleção ou o tipo não é suportado)")
                    v = (bruto or "").strip()
                    if len(v) > LIM_TEXTO_SITE:
                        raise HTTPException(400, f"{nome}: máximo de {LIM_TEXTO_SITE} caracteres")
                    if v == (valores_atuais.get(nome) or ""):
                        continue
                    mid, _ = _meta(con, w["colecao_id"], nome)
                    if c["tipo"] == "taxonomia" and v:
                        tid = con.execute("SELECT taxonomia_id FROM wp_metadado WHERE id=?", (mid,)).fetchone()[0]
                        termo = con.execute("SELECT id, nome FROM wp_termo WHERE taxonomia_id=? AND lower(nome)=lower(?)", (tid, v)).fetchone()
                        if not termo:
                            raise HTTPException(400, f"'{v}' não existe na lista de {nome}. Escolha um termo existente.")
                        md_envio[nome] = (mid, termo["id"], termo["nome"])
                    else:
                        md_envio[nome] = (mid, v, v)
                    site_antes[nome] = valores_atuais.get(nome) or ""
        # ---------- CAMP-095: duas pessoas na mesma folha ----------
        # Quem abriu a folha antes de outra pessoa salvar não apaga a correção dela em silêncio: se o campo que esta pessoa mudou já não é o que
        # ela viu ao abrir, nada é gravado e a resposta diz o valor de agora. Campo não mudado por ela nem vai na requisição (a tela manda só o que mudou).
        if d.vistos and novos:
            conflitos = []
            for k in novos:
                if k not in d.vistos or k == "tipos_documento":
                    continue
                visto = d.vistos[k]
                try:
                    if k == "tipo_documento":
                        from .tipos_documento import separar, juntar
                        agora_v, visto_v = juntar(separar(i["tipos_documento"] or i["tipo_documento"])) or None, juntar(separar(str(visto or ""))) or None
                    elif k == "ano_folha":
                        agora_v, visto_v = i["ano_folha"] or None, (int(visto) if str(visto or "").strip() else None) or None
                    elif k == "parceiros":
                        agora_v, visto_v = parceiros.ler(i["parceiros"]), parceiros.normalizar(visto or [])
                    else:
                        agora_v, visto_v = (i[k] or "").strip() or None, str(visto or "").strip() or None
                except (TypeError, ValueError, HTTPException):
                    continue
                if agora_v != visto_v:
                    rot = ROTULOS_LOCAIS.get(k) or {"ano_folha": "Ano da folha", "parceiros": "Escritórios parceiros", **dados_foto.ROTULOS}.get(k, k)
                    conflitos.append(f"{rot} agora é “{agora_v if not isinstance(agora_v, list) else ', '.join(x.get('escritorio', '') for x in agora_v)}”" if agora_v else f"{rot} foi apagado")
            if conflitos:
                raise HTTPException(409, "Outra pessoa mudou esta folha enquanto você editava (" + "; ".join(conflitos) + "). Nada foi salvo: abra a folha de novo para ver e corrigir.")
        # ---------- grava no painel ----------
        if novos:
            sets = ", ".join(f"{k}=?" for k in novos)
            con.execute(f"UPDATE item SET {sets}, atualizado_em=datetime('now') WHERE codigo=?", (*novos.values(), codigo))
        if novos or site_antes:
            depois = dict(novos)
            if "parceiros" in depois:
                depois["parceiros"] = lista_parceiros     # no histórico, a lista (não o texto JSON da coluna)
            for k in site_antes:
                depois[f"site:{k}"] = (titulo_site if k == "título da página" else descricao_site if k == "descrição"
                                       else md_envio[k][2])
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (codigo, u["email"], json.dumps({"antes": {**antes, **{f"site:{k}": v for k, v in site_antes.items()}},
                                                         "depois": depois}, ensure_ascii=False)))
        con.commit()
        wid, cid = (w["id"], w["colecao_id"]) if w else (None, None)
    finally:
        con.close()
    # ---------- envia ao site (nunca desfaz o que já foi salvo) ----------
    site = None
    if any(k in novos for k in dados_foto.CAMPOS) and i["tainacan_item_id"]:   # 21/10: a folha no site recebe os dados da foto em seguida
        tarefas.add_task(dados_foto.enviar_varios, [codigo], u["email"])
    if wid and (titulo_site is not None or descricao_site is not None or md_envio):
        site = atualizar_folha_no_site(codigo, wid, cid, titulo_site, descricao_site, md_envio, u["email"])
    campos = list(novos) + [f"site:{k}" for k in site_antes]
    return {"ok": True, "campos": campos, "site": site}
