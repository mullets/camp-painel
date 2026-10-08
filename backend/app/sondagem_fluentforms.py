"""Sondagem SOMENTE LEITURA do Fluent Forms do site (fase 0 do "Uso do acervo": quem baixou o quê).

Responde, sem adivinhar: o formulário de download registra QUAL material? O que a pessoa recebe depois de enviar? Quantas entradas existem?
Só faz GET. NUNCA imprime nome, e-mail, telefone nem texto livre digitado por pessoas (só contagens, nomes de campo e URLs de configuração).
"""
from __future__ import annotations

import collections
import json
import re

PADRAO_FORM = re.compile(r"download|material|cadastro", re.I)
PADRAO_MATERIAL = re.compile(r"codigo|código|item|material|ficha|url|link|arquivo|documento", re.I)
PADRAO_USO = re.compile(r"\buso\b|finalidade|pretendid", re.I)
PADRAO_CODIGO = re.compile(r"F\d{3}-P\d{4}", re.I)
ARQUIVO_PUBLICO = re.compile(r"\.(jpe?g|png|tiff?|pdf|zip|dng)(\?|$)|/wp-content/uploads/", re.I)
LISTAS = ("data", "entries", "submissions", "items", "forms", "results")


def _get(h, caminho: str, **params):
    try:
        r = h.get(caminho, params=params)
    except Exception as e:  # noqa: BLE001
        return None, f"sem resposta ({type(e).__name__})"
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, None


def _lista(dados) -> list:
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        for k in LISTAS:
            v = dados.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                r = _lista(v)
                if r:
                    return r
    return []


def _total(dados) -> int | None:
    if isinstance(dados, dict):
        if isinstance(dados.get("total"), int):
            return dados["total"]
        for k in LISTAS:
            if isinstance(dados.get(k), dict):
                t = _total(dados[k])
                if t is not None:
                    return t
    return None


def _json_ou_dict(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, (dict, list)) else {}


def _campos(no, saida: list) -> None:
    """Percorre os campos do formulário (inclusive colunas/contêineres) e junta (nome, rótulo, tipo, obrigatório)."""
    if isinstance(no, list):
        for x in no:
            _campos(x, saida)
    elif isinstance(no, dict):
        attrs, cfg = no.get("attributes") or {}, no.get("settings") or {}
        if attrs.get("name"):
            obrig = bool(((cfg.get("validation_rules") or {}).get("required") or {}).get("value"))
            saida.append((attrs["name"], cfg.get("label") or "", no.get("element") or attrs.get("type") or "", obrig))
        for k in ("fields", "columns"):
            if k in no:
                _campos(no[k], saida)


def _achar(no, chave: str):
    if isinstance(no, dict):
        if chave in no and no[chave] not in (None, ""):
            return no[chave]
        for v in no.values():
            r = _achar(v, chave)
            if r not in (None, ""):
                return r
    elif isinstance(no, list):
        for v in no:
            r = _achar(v, chave)
            if r not in (None, ""):
                return r
    return None


def sondar(h, form_id: int | None = None) -> list[str]:
    L: list[str] = []
    add = L.append
    add("== Fluent Forms na API do site (somente leitura; nenhum dado pessoal é impresso)")
    st, raiz = _get(h, "/wp-json/")
    if st != 200 or not isinstance(raiz, dict):
        add(f"  ✖ não consegui ler a API do site ({st or raiz}). Confira o endereço e as credenciais em Configurações.")
        return L
    rotas = [r for r in (raiz.get("routes") or {}) if "fluentform" in r]
    if "fluentform/v1" not in (raiz.get("namespaces") or []) and not rotas:
        add("  ✖ A API do Fluent Forms NÃO aparece neste site (o plugin não expõe REST, ou está desativado).")
        add("    Alternativas: ler as entradas direto do banco do WordPress, ou criar um webhook no plugin do site (hook fluentform/submission_inserted).")
        return L
    add(f"  ✔ namespace fluentform/v1 presente ({len(rotas)} rota(s) com 'fluentform')")

    st, dados = _get(h, "/wp-json/fluentform/v1/forms", per_page=100)
    if st in (401, 403):
        add(f"  ✖ a API respondeu {st} para os formulários: o usuário do painel no WordPress precisa ser administrador do Fluent Forms.")
        return L
    forms = _lista(dados)
    if st != 200 or not forms:
        add(f"  ✖ não consegui listar os formulários (HTTP {st}). Rotas de formulário vistas: {[r for r in rotas if 'form' in r][:6]}")
        return L
    add("\n== Formulários (id · título · status)")
    for f in forms:
        add(f"  {f.get('id')} · {f.get('title')} · {f.get('status')}")
    escolhidos = [f for f in forms if str(f.get("id")) == str(form_id)] if form_id else [f for f in forms if PADRAO_FORM.search(str(f.get("title", "")))]
    if not escolhidos:
        add("\n  Nenhum formulário parece ser o de download. Rode de novo com --form ID.")
        return L

    for f in escolhidos[:3]:
        fid = f.get("id")
        add(f"\n== Formulário de download: {f.get('title')} (id {fid})")
        st, det = _get(h, f"/wp-json/fluentform/v1/forms/{fid}")
        campos: list = []
        if st == 200:
            _campos(_json_ou_dict(_achar(det, "form_fields") or _achar(det, "formFields")), campos)
        if campos:
            add("  campos: " + "; ".join(f"{n} «{r}» ({t}{', obrigatório' if o else ''})" for n, r, t, o in campos))
        else:
            add(f"  – não consegui ler os campos (HTTP {st}). Veja em Fluent Forms → Editar formulário.")
        cand_material = [(n, r) for n, r, t, o in campos if PADRAO_MATERIAL.search(n) or PADRAO_MATERIAL.search(r) or t in ("input_hidden",)]
        add("  campos que podem identificar o MATERIAL: " + (", ".join(f"{n} «{r}»" for n, r in cand_material) if cand_material else "NENHUM"))

        conf = None
        for caminho in (f"/wp-json/fluentform/v1/forms/{fid}/settings", f"/wp-json/fluentform/v1/forms/{fid}/settings/general"):
            st, c = _get(h, caminho)
            if st == 200 and c:
                conf = c
                break
        destino = tipo = None
        if conf:
            tipo, destino = _achar(conf, "redirectTo"), _achar(conf, "customUrl") or _achar(conf, "redirectMessage")
            msg = _achar(conf, "messageToShow")
            add(f"  confirmação ao enviar: tipo={tipo or '?'}" + (f" · destino={destino}" if destino else "") + (" · mostra mensagem na tela" if msg else ""))
        else:
            add("  – não consegui ler a confirmação (o que a pessoa recebe). Veja em Fluent Forms → Configurações → Confirmações.")

        entradas: list = []
        total = None
        for caminho, params in (("/wp-json/fluentform/v1/submissions", {"form_id": fid, "per_page": 100, "page": 1}),
                                (f"/wp-json/fluentform/v1/forms/{fid}/submissions", {"per_page": 100})):
            st, d = _get(h, caminho, **params)
            if st == 200:
                entradas, total = _lista(d), _total(d)
                if entradas or total is not None:
                    break
        if not entradas and not total:
            add(f"  – não consegui ler as entradas (HTTP {st}).")
        else:
            datas = sorted(str(e.get("created_at") or e.get("date") or "")[:10] for e in entradas if e.get("created_at") or e.get("date"))
            add(f"  entradas: {total if total is not None else len(entradas)} no total; analisadas as {len(entradas)} mais recentes"
                + (f"; período {datas[0]} a {datas[-1]}" if datas else ""))
            resp = [_json_ou_dict(e.get("response") if "response" in e else e) for e in entradas]
            for n, r in cand_material:
                vals = [str(x.get(n)).strip() for x in resp if isinstance(x, dict) and x.get(n) not in (None, "", [])]
                if vals:
                    cods = sum(1 for v in vals if PADRAO_CODIGO.search(v))
                    add(f"  campo «{n}»: preenchido em {len(vals)} de {len(resp)} entradas; {cods} com código CAMP no formato Fxxx-Pxxxx")
                else:
                    add(f"  campo «{n}»: vazio em todas as {len(resp)} entradas analisadas")
            uso = [n for n, r, t, o in campos if PADRAO_USO.search(n) or PADRAO_USO.search(r)]
            for n in uso[:1]:
                vals = [str(x.get(n)).strip() for x in resp if isinstance(x, dict) and x.get(n) not in (None, "", [])]
                dist = collections.Counter(vals)
                if vals and len(dist) <= 12 and all(len(v) <= 40 for v in dist):
                    add(f"  «{n}» (lista de opções): " + ", ".join(f"{v}={c}" for v, c in dist.most_common()))
                elif vals:
                    add(f"  «{n}»: texto livre ({len(dist)} respostas diferentes em {len(vals)}): sem categorias para relatório")

        add("\n== CONCLUSÕES para o desenho")
        add("  " + ("✔ o formulário PARECE registrar o material (campo(s) acima): confira se é preenchido sempre" if cand_material
                    else "✖ o formulário NÃO registra qual material foi pedido: precisa de um campo oculto com o código"))
        if destino and ARQUIVO_PUBLICO.search(str(destino)):
            add("  ✖ depois do envio a pessoa é levada a um endereço PÚBLICO de arquivo: o painel só saberia quem PREENCHEU, não quem baixou. Precisa de link individual com validade.")
        elif tipo or destino:
            add("  – o destino da confirmação não parece um arquivo público; confira como a pessoa recebe o material.")
        else:
            add("  – não ficou claro como a pessoa recebe o arquivo: verificar a confirmação do formulário.")
    return L
