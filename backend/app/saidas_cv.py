"""Lê TUDO o que o CAMP Vision 2 grava em <pasta do projeto>/catalogacao/ (contrato 2.1) para a tela mostrar.
Só leitura: o painel nunca escreve em catalogacao/ nem no QNAP. Arquivo ausente ou fora do formato NÃO derruba nada:
vira None ('não veio do CAMP Vision') ou o texto cru com o aviso de formato mudado."""
from __future__ import annotations

import json
import re
from pathlib import Path

CAMPOS_PROJETO = ("titulo", "ano", "cidade", "uf", "cliente", "endereco")
_COLUNA = {"titulo": "titulo", "ano": "ano", "cidade": "cidade", "uf": "uf", "cliente": "cliente", "endereco": "endereco_obra"}


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return {"_ilegivel": True}


def _texto(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else None
    except OSError:
        return None


def ler_relatorio(texto: str | None) -> dict | None:
    """O relatório do lote tem 8 partes fixas: 'N. Título' e itens recuados ('nenhum' quando vazio) — nucleo/entrada.py relatorio_lote (CV2 f8c8a69)."""
    if texto is None:
        return None
    partes, atual = [], None
    for ln in texto.splitlines():
        m = re.match(r"^(\d+)\.\s+(.+?)\s*$", ln)
        if m:
            atual = {"n": int(m.group(1)), "titulo": m.group(2), "itens": []}
            partes.append(atual)
        elif atual is not None and ln.startswith("   ") and ln.strip() and ln.strip() != "nenhum":
            atual["itens"].append(ln.strip())
    out = {"texto": texto, "partes": partes, "formato_ok": len(partes) >= 6 and [p["n"] for p in partes][:6] == [1, 2, 3, 4, 5, 6], "alerta_origem": None}
    p1 = next((p for p in partes if p["n"] == 1), None)
    if p1 and p1["itens"]:
        m = re.search(r"(\d+) arquivo\(s\) na origem, (\d+) arquivado\(s\), (\d+) documento\(s\)", p1["itens"][0])
        if m:
            origem, arquivados, docs = (int(x) for x in m.groups())
            out["numeros"] = {"origem": origem, "arquivados": arquivados, "documentos": docs}
            if origem != arquivados:   # ALERTA, não bloqueio (decisão do Rafa em aberto; a troca para bloqueio fica concentrada aqui)
                out["alerta_origem"] = f"{origem} arquivo(s) na origem, mas {arquivados} arquivado(s): {origem - arquivados} não chegaram ao acervo."
    return out


def ler_orientacao(texto: str | None) -> dict | None:
    if texto is None:
        return None
    incertas: list[str] = []
    linhas = []
    for ln in texto.splitlines():
        if ":" in ln and not ln.lower().startswith("orientação aplicada"):
            rot, _, lista = ln.partition(":")
            ds = [d.strip() for d in lista.split(",") if re.fullmatch(r"D\d+", d.strip())]
            linhas.append({"rotulo": rot.strip(), "folhas": ds})
            if rot.strip().lower().startswith("incerta"):
                incertas.extend(ds)
    return {"texto": texto, "linhas": linhas, "incertas": incertas}


ROTULO_ACEITE = {"contagem_origem_igual_saida": "Contagem de origem igual à de saída", "sem_autoria_divergente": "Nenhuma folha com autoria divergente",
                 "duplicatas_marcadas": "Duplicatas marcadas (só a única vai ao site)", "orientacao_incerta_zerada": "Orientação incerta zerada ou revisada",
                 "serie_incerta_zerada": "Série incerta zerada", "sem_plausibilidade": "Nenhum campo preenchido por plausibilidade",
                 "documentacao_nao_e_obra": "Documentação não classificada como obra", "backtest_ok": "Back-test da regra ≥ 85%",
                 "exif_conferido": "EXIF conferido", "relatorio_gerado": "Relatório de fim de lote gerado"}


def ler_aceite(pasta: str | Path) -> dict | None:
    """CV2 §10 (contrato 9.4): o "aceite" do JSON de lote mais recente em catalogacao/lotes/. None = o CV2 não gravou."""
    d = Path(pasta) / "catalogacao" / "lotes"
    if not d.is_dir():
        return None
    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        j = _json(f)
        if isinstance(j, dict) and isinstance(j.get("aceite"), dict):
            return {**j["aceite"], "_arquivo": f.name}
    return None


def itens_aceite(aceite: dict | None) -> list[dict]:
    """Os itens do checklist como lista {chave, rotulo, ok, detalhe} (ok None = não informado)."""
    if not aceite:
        return []
    out = []
    for k, v in aceite.items():
        if k in ("publicavel", "pendencias") or k.startswith("_"):
            continue
        ok = v.get("ok") if isinstance(v, dict) else v if isinstance(v, bool) else None
        det = (v.get("contagem") if isinstance(v, dict) else None)
        out.append({"chave": k, "rotulo": ROTULO_ACEITE.get(k, k.replace("_", " ").capitalize()), "ok": ok, "detalhe": det})
    return out


def motivos_aceite(aceite: dict | None) -> list[str]:
    if not aceite:
        return []
    pend = aceite.get("pendencias")
    if isinstance(pend, list) and pend:
        return [str(x.get("mensagem") or x.get("item") or x) if isinstance(x, dict) else str(x) for x in pend]
    return [i["rotulo"] for i in itens_aceite(aceite) if i["ok"] is False]


def sugestoes_projeto(pacote: dict | None, projeto: dict) -> list[dict]:
    """Campos do bloco 'projeto' do pacote como SUGESTÃO. Só sugere onde o painel está vazio (ou com o título provisório 'P0001'):
    nunca propõe trocar o que uma pessoa já escreveu."""
    if not isinstance(pacote, dict) or not isinstance(pacote.get("projeto"), dict):
        return []
    bp, out = pacote["projeto"], []
    for campo in CAMPOS_PROJETO:
        sug = bp.get(campo)
        sug = str(sug).strip() if sug not in (None, "") else ""
        atual = projeto.get(_COLUNA[campo])
        atual_txt = "" if atual in (None, 0, "0") else str(atual).strip()
        provisorio = campo == "titulo" and bool(re.fullmatch(r"P\d{4}", atual_txt))
        if sug and (not atual_txt or provisorio) and sug != atual_txt:
            out.append({"campo": campo, "sugerido": sug, "atual": atual_txt or None, "fontes": (bp.get("fontes") or {}).get(campo)})
    return out


def ler_saidas(pasta: str | Path, projeto: dict, respostas: dict | None = None) -> dict:
    cat = Path(pasta) / "catalogacao"
    if not cat.is_dir():
        return {"existe": False, "motivo": "esta pasta não tem catalogacao/ (o CAMP Vision ainda não entregou)"}
    pacote = _json(cat / "pacote_tainacan.json")
    pac = pacote if isinstance(pacote, dict) and not pacote.get("_ilegivel") else None
    propostas = _json(cat / "propostas.json")
    if propostas is None and pac:
        propostas = pac.get("propostas")
    releituras = []
    rr = cat / "releituras"
    if rr.is_dir():
        for d in sorted((x for x in rr.iterdir() if x.is_dir()), reverse=True)[:10]:
            comp = _json(d / "comparacao.json")
            if comp is not None:
                releituras.append({"quando": d.name, "comparacao": comp})
    return {
        "existe": True,
        "pacote_ilegivel": bool(isinstance(pacote, dict) and pacote.get("_ilegivel")),
        "avisos": (pac or {}).get("avisos") if pac else None,
        "retirados": (pac or {}).get("retirados") if pac else None,
        "propostas": propostas,
        "sugestoes": [x for x in sugestoes_projeto(pac, projeto) if f"sugestao:{x['campo']}" not in (respostas or {})],
        "respostas": respostas or {},
        "capa_sugerida": ((pac or {}).get("projeto") or {}).get("capa_sugerida") if pac else None,
        "aceite": (lambda a: {"publicavel": a.get("publicavel"), "itens": itens_aceite(a), "motivos": motivos_aceite(a), "arquivo": a.get("_arquivo")} if a else None)(ler_aceite(pasta)),
        "execucao": (pac or {}).get("execucao") if pac else None,
        "relatorio": ler_relatorio(_texto(cat / "relatorio.txt")),
        "decisoes": _json(cat / "decisoes.json"),
        "orientacao": ler_orientacao(_texto(cat / "orientacao.txt")),
        "releituras": releituras,
    }
