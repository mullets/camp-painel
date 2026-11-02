"""Aviso por e-mail da situação de uma inscrição em curso (02/11/2026).

Rafael: "quando coloco uma pessoa que se inscreveu no nosso painel, e mudo o status dela, devia mandar um e-mail para ela avisando
que status está". Só para inscrição (não para o "Avise-me") e só para em análise, selecionada e não selecionada; quem muda pode
desmarcar o aviso e escrever um recado. Canal: o e-mail transacional TR10 do Sender.net (sender.tr10_inscricao_situacao), se
preenchido; senão, o e-mail do site (a mesma rota da entrega de pedidos, wp_mail pelo SMTP do site). Nada configurado: não envia
e diz por quê. O status muda de qualquer jeito; o envio falho só vira aviso na tela.
"""
from __future__ import annotations

import json

from . import entrega
from .config import settings
from .email_envio import ENDERECO

AVISA = ("em_analise", "selecionada", "nao_selecionada")
ROTULO = {"em_analise": "Em análise", "selecionada": "Selecionada", "nao_selecionada": "Não selecionada"}
TEXTOS = {
    "em_analise": ("sua inscrição está em análise",
                   "Recebemos sua inscrição no curso {curso} e ela está em análise pela equipe da CAMP. Avisaremos o resultado por este e-mail."),
    "selecionada": ("você foi selecionado(a)",
                    "Boa notícia: sua inscrição no curso {curso} foi selecionada! Em breve mandaremos as próximas informações (datas, local e o que levar)."),
    "nao_selecionada": ("resultado da sua inscrição",
                        "Agradecemos muito o seu interesse no curso {curso}. Desta vez sua inscrição não foi selecionada. "
                        "Fique de olho nas próximas turmas em camp.arq.br."),
}


def canal(con) -> str:
    if entrega._cfg(con, "sender.token") and entrega._cfg(con, "sender.tr10_inscricao_situacao"):
        return "sender"
    if entrega._cfg(con, "wp.app_password", settings.WP_APP_PASSWORD):
        return "site"
    return ""


def _curso(r) -> str:
    c = (r["curso"] or "").strip() or "da CAMP"
    return f"{c} ({r['turma'].strip()})" if (r["turma"] or "").strip() else c


def montar(r, situacao: str, mensagem: str = "") -> dict:
    nome = (r["nome"] or "").strip()
    primeiro = nome.split()[0] if nome else "olá"
    titulo, corpo = TEXTOS[situacao]
    corpo = corpo.format(curso=_curso(r))
    mensagem = " ".join((mensagem or "").split())[:1000]
    texto = (f"Olá, {primeiro},\n\n{corpo}\n\n" + (f"{mensagem}\n\n" if mensagem else "")
             + "Se tiver alguma dúvida, é só responder este e-mail.\n\nEquipe CAMP\n")
    return {"assunto": f"CAMP · {(r['curso'] or 'Curso').strip()}: {titulo}", "texto": texto,
            "variaveis": {"nome": primeiro, "nome_completo": nome, "curso": (r["curso"] or "").strip(), "turma": (r["turma"] or "").strip(),
                          "situacao": ROTULO[situacao], "situacao_codigo": situacao, "texto": corpo, "mensagem": mensagem}}


def previa(con, r, situacao: str) -> dict:
    if r["tipo"] != "inscricao" or situacao not in AVISA:
        return {"avisa": False}
    m = montar(r, situacao)
    return {"avisa": True, "para": r["email"] or "", "email_valido": bool(ENDERECO.match(r["email"] or "")), "canal": canal(con),
            "rotulos": entrega.CANAIS, "assunto": m["assunto"], "texto": m["texto"]}


def enviar(con, r, situacao: str, mensagem: str, ator: dict) -> dict:
    """Manda o aviso. Devolve {enviado, canal?, para?, erro?}; registra o evento (com ou sem sucesso)."""
    para = (r["email"] or "").strip()
    if not ENDERECO.match(para):
        return {"enviado": False, "erro": "a inscrição não tem um e-mail válido"}
    c = canal(con)
    if not c:
        return {"enviado": False, "erro": "o envio de e-mail não está configurado (Sender.net ou a senha do site em Configurações)"}
    m = montar(r, situacao, mensagem)
    try:
        if c == "sender":
            entrega._enviar_sender(con, para, r["nome"] or "", m["variaveis"], chave_campanha="sender.tr10_inscricao_situacao")
        else:
            entrega._enviar_site(con, para, r["nome"] or "", m["assunto"], m["texto"], entrega._cfg(con, "entrega.responder_para"), None)
        res = {"enviado": True, "canal": c, "para": para}
    except entrega.EnvioErro as e:
        res = {"enviado": False, "canal": c, "erro": str(e)[:240]}
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao',?,?,?,?)",
                (str(r["site_id"]), "aviso_situacao" if res["enviado"] else "aviso_situacao_falhou", ator.get("email"),
                 json.dumps({"situacao": situacao, "canal": c, "para": para, "erro": res.get("erro")}, ensure_ascii=False)))
    con.commit()
    return res
