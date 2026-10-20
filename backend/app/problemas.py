"""Problemas (tabela `erro`) explicados para quem vai resolver (pedido de 19/10: "a pasta de problemas tá confusa").

Para cada problema: de que projeto é (código e nome), o que aconteceu e o que fazer em português simples, e a AÇÃO do painel
que resolve de verdade (devolver à revisão, mover, marcar duplicata, girar...). Também descobre o que já se resolveu sozinho:
- seguro (fecha sozinho, com registro no histórico): a folha retirada foi devolvida à revisão por um admin; a folha retirada ou
  recusada entrou no painel quando o lote foi importado de novo; depois do relato, uma pessoa marcou a folha como duplicata
  (problema de duplicata) ou moveu a folha para outro projeto (problema de "folha de outro projeto").
- talvez (só mostra separado, a pessoa confirma): a folha não existe mais, mudou de código, já foi girada/espelhada, ou o
  projeto foi juntado a outro / descartado.
Só lê o banco (nunca o QNAP). `fechar_resolvidos` não faz commit: quem chama controla a transação."""
from __future__ import annotations

import json
import re

ABERTOS = ("aberto", "em_correcao")
ATOR_AUTOMATICO = "painel (automático)"
_FOLHA = re.compile(r"^F\d{3}-P\d{4}-.+-D\d+$")
_PROJ = re.compile(r"^F\d{3}-P\d{4}")

# categoria -> (o que aconteceu, o que fazer)
TEXTOS = {
    "orientacao": ("A folha está virada (de lado ou de cabeça para baixo).",
                   "Abra a folha e use Virar à esquerda ou Virar à direita até ela ficar em pé. A correção fica gravada."),
    "espelhado": ("A folha foi digitalizada pelo verso: o desenho e o texto aparecem ao contrário.",
                  "Abra a folha e use Espelhar. A correção fica gravada."),
    "duplicata": ("Esta folha parece repetida: igual a outra do projeto.",
                  "Marque de qual folha ela é cópia: nada é apagado e só a original vai ao site. Se não for repetida, feche como \"Não era problema\"."),
    "projeto_errado": ("Esta folha parece ser de outro projeto.",
                       "Mova a folha para o projeto certo (só projetos do mesmo fundo). Ela ganha o código do projeto certo e o código antigo fica guardado."),
    "autoria_divergente": ("A folha tem carimbo ou assinatura de outro autor. Isso não impede publicar: a folha sobe com o aviso.",
                           "Se o projeto é mesmo de outro autor (ou em coautoria), registre a autoria. Se não for, feche como \"Não era problema\"."),
    "metadado": ("Algum dado está errado ou faltando (título, ano, tipo, descrição).", "Abra e corrija o dado. Depois marque como corrigido."),
    "credito": ("O crédito (autoria, fotógrafo, escritório) está errado ou faltando.", "Abra e corrija o crédito. Depois marque como corrigido."),
    "codigo": ("O código está errado.", "Abra e confira o código. Se a folha for de outro projeto, mova a folha."),
    "arquivo_corrompido": ("O arquivo da imagem está danificado ou não abre.",
                           "Peça ao CAMP Vision para ler de novo ou digitalize a folha de novo. Depois marque como corrigido."),
    "outro": ("Problema relatado (veja o detalhe).", "Abra a folha ou o projeto e resolva. Depois marque como corrigido dizendo o que foi feito."),
}

ROTULO_ACAO = {
    "devolver": "Devolver à revisão", "abrir_lote": "Abrir o lote no projeto", "girar": "Abrir a folha para girar",
    "espelhar": "Abrir a folha para espelhar", "duplicata": "Marcar de qual folha é cópia", "mover": "Mover para o projeto certo",
    "autoria": "Registrar a autoria", "abrir_folha": "Abrir a folha", "abrir_projeto": "Abrir o projeto", "abrir_fundo": "Abrir o fundo",
}


def tipo_do_problema(e) -> str:
    ch = e["chave"] or ""
    if ch.startswith("campvision:retirado:"):
        return "retirada"
    if ch.startswith("campvision:recusada:"):
        return "recusada"
    return "comum"


def folha_da_chave(e) -> str | None:
    """A folha de que o problema automático fala (retirada: campvision:retirado:<folha>; recusada: campvision:recusada:<projeto>:<folha>)."""
    ch = e["chave"] or ""
    if ch.startswith("campvision:retirado:"):
        return ch[len("campvision:retirado:"):]
    if ch.startswith("campvision:recusada:"):
        partes = ch.split(":", 3)
        return partes[3] if len(partes) > 3 else None
    return None


def _em_lotes(xs, n=400):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def contexto(con, erros: list) -> dict:
    """Tudo o que `explicar` precisa, em poucas consultas (projetos, fundos, folhas, devoluções, lotes, eventos)."""
    cods = {e["codigo"] for e in erros}
    folhas = {c for c in cods if c.count("-") >= 4} | {f for e in erros if (f := folha_da_chave(e))}
    projs = {c[:10] for c in cods if _PROJ.match(c)}
    fundos = {c[:4] for c in cods if re.match(r"^F\d{3}", c)}
    ctx = {"projetos": {}, "fundos": {}, "itens": {}, "por_anterior": {}, "devolvidas": {}, "lotes": {}, "eventos": {}, "copias": {}, "retiradas": set()}
    for parte in _em_lotes(projs):
        q = ",".join("?" * len(parte))
        for r in con.execute(f"SELECT codigo, titulo, fundo_codigo, mesclado_em, descartado_em, status_site FROM projeto WHERE codigo IN ({q})", parte):
            ctx["projetos"][r["codigo"]] = dict(r)
        for r in con.execute(f"SELECT projeto_codigo, chave, por, em, motivo, lote_id FROM cv_resposta WHERE tipo='retirado' AND acao='devolver' AND projeto_codigo IN ({q})", parte):
            ctx["devolvidas"][r["chave"]] = dict(r)
        for r in con.execute(f"SELECT id, projeto_codigo, resultado FROM lista_processamento WHERE descartado_em IS NULL AND projeto_codigo IN ({q}) ORDER BY id", parte):
            ctx["lotes"].setdefault(r["projeto_codigo"], []).append((r["id"], r["resultado"] or ""))
    for parte in _em_lotes(fundos):
        q = ",".join("?" * len(parte))
        for r in con.execute(f"SELECT codigo, titulo FROM fundo WHERE codigo IN ({q})", parte):
            ctx["fundos"][r["codigo"]] = r["titulo"]
    for parte in _em_lotes(folhas):
        q = ",".join("?" * len(parte))
        for r in con.execute(f"SELECT codigo, projeto_codigo, duplicata_de, codigo_anterior, giro_manual, espelho_manual, lote_id FROM item WHERE codigo IN ({q})", parte):
            ctx["itens"][r["codigo"]] = dict(r)
        # CAMP-096 (exaustão, 20/10): folhas que o CAMP Vision RETIROU do lote (nunca entraram no painel). O problema "outra pasta" do erros.json
        # sobre elas não é "folha que sumiu": antes a tela dizia "Esta folha não existe mais no painel… Confira e feche" num problema que impede publicar.
        for r in con.execute(f"SELECT substr(chave, 21) FROM erro WHERE chave IN ({','.join('?' * len(parte))})", [f"campvision:retirado:{f}" for f in parte]):
            ctx["retiradas"].add(r[0])
        for r in con.execute(f"SELECT codigo, codigo_anterior FROM item WHERE codigo_anterior IN ({q})", parte):
            ctx["por_anterior"][r["codigo_anterior"]] = r["codigo"]
        for r in con.execute(f"SELECT codigo, tipo, max(quando) AS quando FROM evento WHERE entidade='item' AND tipo IN ('folha_movida','duplicata_marcada') AND codigo IN ({q}) GROUP BY codigo, tipo", parte):
            ctx["eventos"][(r["codigo"], r["tipo"])] = r["quando"]
        for r in con.execute(f"""SELECT i.codigo, i.duplicata_de, (SELECT max(quando) FROM evento v WHERE v.entidade='item' AND v.tipo='duplicata_marcada' AND v.codigo=i.codigo) AS quando
                                 FROM item i WHERE i.duplicata_de IN ({q})""", parte):
            if r["quando"]:
                ctx["copias"].setdefault(r["duplicata_de"], []).append((r["codigo"], r["quando"]))
    return ctx


def _lote_da_folha(ctx, proj: str, folha: str | None):
    """O lote em que o CAMP Vision retirou a folha (o resumo da importação guarda as retiradas); senão, o lote mais novo do projeto."""
    lotes = ctx["lotes"].get(proj) or []
    if folha:
        for lid, res in reversed(lotes):
            if f'"{folha}"' in res:
                return lid
    return lotes[-1][0] if lotes else None


def explicar(e, ctx: dict) -> dict:
    """Os campos que a tela usa: projeto (código e nome), o que aconteceu, o que fazer, a ação que resolve e se já se resolveu."""
    cod = e["codigo"] or ""
    tipo = tipo_do_problema(e)
    folha = folha_da_chave(e) if tipo != "comum" else (cod if cod.count("-") >= 4 else None)
    proj = cod[:10] if _PROJ.match(cod) else None
    pj = ctx["projetos"].get(proj) if proj else None
    fundo = cod[:4] if re.match(r"^F\d{3}", cod) else None
    it = ctx["itens"].get(folha) if folha else None
    alvo = "folha" if folha else ("projeto" if proj else ("fundo" if fundo else "outro"))
    out = {"tipo": tipo, "alvo": alvo, "folha": folha, "projeto_codigo": proj, "projeto_titulo": (pj or {}).get("titulo"),
           "fundo_codigo": fundo, "fundo_titulo": ctx["fundos"].get(fundo) if fundo else None,
           "folha_existe": bool(it) if folha else None, "folha_atual": None, "lote_id": None, "resolvido_sozinho": None}
    o_que, fazer = TEXTOS.get(e["categoria"], TEXTOS["outro"])
    if e["categoria"] == "outro" and (e["origem"] or "") == "campvision":      # 20/10: não foi "relatado" por ninguém; foi o CAMP Vision
        from .rotas_revisao import pede_so_olhar_a_folha
        o_que = "O CAMP Vision apontou (veja o detalhe)."
        if pede_so_olhar_a_folha(e["descricao"]):
            fazer = "Abra a folha e confira. Se estiver certa, \"Está certo\" resolve e o aviso sai daqui; se algo estiver errado, corrija e salve."
    acao = None
    sozinho = None
    criado = e["criado_em"] or ""
    if tipo == "retirada":
        out["lote_id"] = _lote_da_folha(ctx, proj, folha) if proj else None
        o_que = "O CAMP Vision tirou esta folha do lote antes da revisão. Ela não está no painel e não vai ao site."
        fazer = ("Se a folha está boa, devolva à revisão: ela entra na próxima importação, pendente de conferência. "
                 "Se a retirada está certa (folha repetida, em branco, de outro projeto), confirme e o problema fecha.")
        acao = "devolver" if out["lote_id"] else "abrir_lote"
        dv = ctx["devolvidas"].get(folha)
        if dv:
            sozinho = {"seguro": True, "motivo": f"Um admin devolveu a folha à revisão ({dv['por']}, {str(dv['em'])[:16]})" + (f": {dv['motivo']}" if dv.get("motivo") else "") + "."}
        elif it and it["projeto_codigo"] == proj:
            sozinho = {"seguro": True, "motivo": "A folha entrou no painel quando o lote foi importado de novo; agora ela passa pela revisão."}
    elif tipo == "recusada":
        out["lote_id"] = _lote_da_folha(ctx, proj, None) if proj else None
        o_que = "A folha veio no lote do CAMP Vision, mas o painel não aceitou ao importar (veja o motivo no detalhe)."
        fazer = ("Corrija no CAMP Vision e importe o lote de novo (página do projeto, \"Mais ações do lote\"). "
                 "Se a folha não deve entrar, marque como corrigido dizendo por quê.")
        acao = "abrir_lote"
        if it and it["projeto_codigo"] == proj:
            sozinho = {"seguro": True, "motivo": "A folha entrou no painel quando o lote foi importado de novo."}
    elif folha:
        if not it:
            novo = ctx["por_anterior"].get(folha)
            if novo:
                out["folha_atual"] = novo
                if e["categoria"] == "projeto_errado" and novo[:10] != folha[:10]:
                    sozinho = {"seguro": True, "motivo": f"A folha foi movida para o projeto {novo[:10]} (agora é {novo})."}
                else:
                    sozinho = {"seguro": False, "motivo": f"A folha mudou de código: agora é {novo}. Confira se o problema continua."}
            elif folha in ctx["retiradas"]:
                from .importador_lote import fala_de_projeto_divergente
                if e["categoria"] == "projeto_errado" or fala_de_projeto_divergente(e["descricao"]):
                    o_que = "O CAMP Vision tirou esta folha do lote por achar que é de outro projeto. Ela não está no painel e não vai ao site."
                    fazer = "Veja a folha. Se for deste projeto, \"É deste projeto\" a devolve ao lote; se não for, \"É de outro projeto…\" e ela fica fora."
                else:
                    o_que = "O CAMP Vision tirou esta folha do lote antes da revisão. Ela não está no painel e não vai ao site."
            else:
                sozinho = {"seguro": False, "motivo": "Esta folha não existe mais no painel (foi apagada ou mudou de código). Confira e feche."}
            acao = "abrir_projeto" if pj else None
        else:
            acao = {"orientacao": "girar", "espelhado": "espelhar", "duplicata": "duplicata", "projeto_errado": "mover",
                    "autoria_divergente": "autoria"}.get(e["categoria"], "abrir_folha")
            q_dup = ctx["eventos"].get((folha, "duplicata_marcada"))
            q_mov = ctx["eventos"].get((folha, "folha_movida"))
            copia = next((c for c, q in ctx["copias"].get(folha, []) if q >= criado), None)
            if e["categoria"] == "duplicata" and it["duplicata_de"] and q_dup and q_dup >= criado:
                sozinho = {"seguro": True, "motivo": f"Depois do relato, a folha foi marcada como cópia de {it['duplicata_de']} (só a original vai ao site)."}
            elif e["categoria"] == "duplicata" and copia:
                sozinho = {"seguro": True, "motivo": f"Depois do relato, a folha {copia} foi marcada como cópia desta (esta é a que vai ao site)."}
            elif e["categoria"] == "projeto_errado" and it["codigo_anterior"] and it["codigo_anterior"][:10] != folha[:10] and q_mov and q_mov >= criado:
                sozinho = {"seguro": True, "motivo": f"Depois do relato, a folha foi movida de {it['codigo_anterior'][:10]} para {folha[:10]}."}
            elif e["categoria"] == "orientacao" and it["giro_manual"]:
                sozinho = {"seguro": False, "motivo": f"A folha já foi girada no painel ({it['giro_manual']}°). Confira a imagem e feche."}
            elif e["categoria"] == "espelhado" and it["espelho_manual"]:
                sozinho = {"seguro": False, "motivo": "A folha já foi espelhada no painel. Confira a imagem e feche."}
    elif proj:
        acao = "autoria" if e["categoria"] == "autoria_divergente" else "abrir_projeto"
    elif fundo:
        acao = "abrir_fundo"
    if not sozinho and pj:
        if pj.get("mesclado_em"):
            sozinho = {"seguro": False, "motivo": f"O projeto foi juntado ao {pj['mesclado_em']}. Confira lá se o problema continua."}
        elif pj.get("descartado_em"):
            sozinho = {"seguro": False, "motivo": "O projeto foi descartado (era uma pasta, não uma obra). Confira e feche."}
    if proj and not pj and not sozinho:
        sozinho = {"seguro": False, "motivo": f"O projeto {proj} não existe mais no painel. Confira e feche."}
    out.update(o_que=o_que, fazer=fazer, acao=acao, acao_rotulo=ROTULO_ACAO.get(acao), resolvido_sozinho=sozinho)
    return out


def enriquecer(con, erros: list) -> list[dict]:
    ctx = contexto(con, erros)
    return [{**dict(e), **explicar(e, ctx)} for e in erros]


def fechar_resolvidos(con, ator: str = ATOR_AUTOMATICO) -> list[int]:
    """Fecha (situação 'corrigido') os problemas abertos que se resolveram sozinhos COM CERTEZA, gravando o porquê na resolução
    e um evento 'fechado_automatico' no histórico. Os "talvez" ficam abertos. Não faz commit. Devolve os ids fechados."""
    abertos = con.execute("SELECT * FROM erro WHERE situacao IN ('aberto','em_correcao')").fetchall()
    if not abertos:
        return []
    ctx = contexto(con, abertos)
    fechados = []
    for e in abertos:
        s = explicar(e, ctx)["resolvido_sozinho"]
        if not (s and s["seguro"]):
            continue
        n = con.execute("UPDATE erro SET situacao='corrigido', resolvido_em=datetime('now'), resolucao=? WHERE id=? AND situacao IN ('aberto','em_correcao')",
                        ("Resolvido sozinho: " + s["motivo"], e["id"])).rowcount
        if n:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('erro',?,'fechado_automatico',?,?)",
                        (str(e["id"]), ator, json.dumps({"codigo": e["codigo"], "motivo": s["motivo"]}, ensure_ascii=False)))
            fechados.append(e["id"])
    return fechados
