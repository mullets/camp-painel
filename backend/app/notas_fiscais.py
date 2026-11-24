"""Financeiro · Pedir nota fiscal ao fornecedor (CAMP-FIN, 24/11/2026). Rafael: "preparar para criar cobrança de nota fiscal para algum
fornecedor".

- Numa despesa SEM comprovante (e na fila "Precisa justificar"), o admin pede a nota fiscal ao fornecedor: e-mail do fornecedor (e, se quiser,
  WhatsApp, que vira um link wa.me com o texto pronto), descrição da nota (vem da justificativa), valor, data do pagamento e a referência do
  Mercado Pago. Prévia do texto antes de mandar.
- Despesa numa conta de projeto incentivado (ou com PRONAC no projeto/rubrica): a descrição da nota leva "Projeto PRONAC <número> · <nome do
  projeto>", e o texto diz "conforme orientação do projeto" (tom cauteloso: o painel não afirma regra da Lei Rouanet).
- Envio: pelo SMTP do painel (email_envio, o mesmo dos e-mails aos Downloads), que fala com quem está fora da CAMP sem passar pelo Sender do
  site (os modelos TR do Sender são do público do site). Sem SMTP, ou se preferir: "Copiar texto" e o link do WhatsApp; quem mandou por
  conta própria marca "Já mandei: marcar como pedida".
- A despesa fica "nota pedida em dd/mm" (despesa.nota_pedida_em) até o comprovante chegar (anexar o comprovante limpa); "Pedir de novo"
  reenvia. Depois de notas.lembrete_dias (padrão 7) sem nota, a Home do admin mostra "N notas fiscais pedidas ainda não chegaram" (baixa).
- Dados da CAMP para a nota (tomador): faturamento.* em Configurações, VAZIOS por padrão. Sem eles o pedido não sai (mensagem clara) e a tela
  pede uma vez. Nunca inventar valor.
- Memória do fornecedor: o e-mail/WhatsApp de cada contraparte fica guardado depois do 1º pedido (só admin) e volta preenchido. LGPD: apagar
  pessoa (pelo e-mail) apaga esse contato e tira o e-mail/WhatsApp/texto dos pedidos (apagar_por_email).
- Upload público para o fornecedor mandar a nota: NÃO existe (possível próximo passo).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, email_envio
from .db import connect

router = APIRouter(prefix="/api/financeiro/notas", tags=["notas_fiscais"])

DADOS = (("razao_social", "razão social", True), ("cnpj", "CNPJ", True), ("inscricao_municipal", "inscrição municipal", False),
         ("endereco", "endereço", True), ("email_notas", "e-mail que recebe as notas", True))
CANAIS = {"email": "e-mail (SMTP do painel)", "copiado": "texto copiado", "whatsapp": "WhatsApp"}
REMOVIDO = "(removido)"


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _ator(u: dict | None) -> str:
    return (u or {}).get("email") or "painel"


def _dmy(s: str) -> str:
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s and len(s) >= 10 else ""


def _brl(v) -> str:
    from .financeiro import brl
    return brl(v)


def cnpj_valido(v: str) -> bool:
    d = re.sub(r"\D", "", v or "")
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n in (12, 13):
        pesos = list(range(n - 7, 1, -1)) + list(range(9, 1, -1))
        s = sum(int(d[i]) * pesos[i] for i in range(n))
        dv = 0 if s % 11 < 2 else 11 - s % 11
        if int(d[n]) != dv:
            return False
    return True


def _fmt_cnpj(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else v


def dados_camp(con) -> dict:
    return {k: _cfg(con, "faturamento." + k) for k, _n, _o in DADOS}


def faltam(d: dict) -> list[str]:
    return [n for k, n, obrig in DADOS if obrig and not (d.get(k) or "").strip()]


def lembrete_dias(con) -> int:
    try:
        return max(1, min(90, int(_cfg(con, "notas.lembrete_dias", "7"))))
    except ValueError:
        return 7


def _chave(contraparte: str) -> str:
    return _txt(contraparte, 160).lower()


def contato(con, contraparte: str) -> dict:
    r = con.execute("SELECT email, whatsapp FROM fornecedor_contato WHERE chave=?", (_chave(contraparte),)).fetchone() if _chave(contraparte) else None
    return {"email": (r["email"] or "") if r else "", "whatsapp": (r["whatsapp"] or "") if r else ""}


def _despesa(con, did: int):
    r = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL", (did,)).fetchone()
    if not r:
        raise HTTPException(404, "Despesa não encontrada")
    return r


def pronac(con, r) -> str:
    """'Projeto PRONAC 2613864 · Livro Karazawa' quando a despesa é de conta de projeto incentivado ou o projeto/rubrica fala em PRONAC; senão ''."""
    c = con.execute("SELECT tipo, projeto, nome FROM financeiro_conta WHERE id=?", (r["conta_id"],)).fetchone()
    textos = [r["projeto"] or "", (c["projeto"] or "") if c else "", (c["nome"] or "") if c else ""]
    for t in textos:
        m = re.search(r"PRONAC\s*n?[ºo.]?\s*(\d{4,})\s*(?:[·\-–—:|]\s*)?(.*)", t, re.I)
        if m:
            nome = re.split(r"\s+[·|]\s+", m.group(2).strip())[0].strip(" ·-–—") if m.group(2) else ""
            return f"Projeto PRONAC {m.group(1)}" + (f" · {nome}" if nome else "")
    if c and c["tipo"] == "projeto_incentivado" and (c["projeto"] or "").strip():
        return f"Projeto {c['projeto'].strip()}"
    return ""


def montar(con, r, b: "Pedido | None" = None) -> dict:
    """O texto do pedido (assunto, corpo, link do WhatsApp) com os dados da CAMP; 'faltam' lista o que falta da CAMP."""
    b = b or Pedido()
    d = dados_camp(con)
    ident = pronac(con, r)
    desc = _txt(b.descricao if b.descricao is not None else (r["justificativa"] or ""), 500)
    if ident and not re.search(r"PRONAC\s*" + re.escape(re.sub(r"\D", "", ident.split("·")[0])), desc, re.I):
        desc = (desc + " · " if desc else "") + ident
    valor = b.valor if b.valor is not None else r["valor"]
    data = _txt(b.data, 10) if b.data else r["data"]
    ref = _txt(b.mp_ref if b.mp_ref is not None else (r["mp_ref"] or ""), 80)
    quem = _txt(r["contraparte"], 160)
    assunto = f"Pedido de nota fiscal · CAMP · pagamento de {_dmy(data)} ({_brl(valor)})"
    pag = [f"- Valor: {_brl(valor)}", f"- Data do pagamento: {_dmy(data)}"] + ([f"- Referência do Mercado Pago: {ref}"] if ref else [])
    tom = [f"- Razão social: {d['razao_social']}", f"- CNPJ: {_fmt_cnpj(d['cnpj'])}"] + \
          ([f"- Inscrição municipal: {d['inscricao_municipal']}"] if d["inscricao_municipal"].strip() else []) + [f"- Endereço: {d['endereco']}"]
    corpo = "\n".join([f"Olá{', ' + quem if quem else ''},", "",
                       "A CAMP pede, por gentileza, a emissão da nota fiscal referente ao pagamento abaixo.", "",
                       "Pagamento:", *pag, "",
                       "Dados para a nota fiscal (tomador):", *tom, "",
                       "Descrição para a nota:", desc or "(descreva o produto ou serviço)", ""]
                      + ([f"Conforme orientação do projeto, pedimos que a descrição da nota traga a identificação {ident}.", ""] if ident else [])
                      + [f"Por favor, envie a nota fiscal para {d['email_notas']}.", "", "Obrigado.", "CAMP"])
    wa = re.sub(r"\D", "", b.whatsapp or "")
    if wa and len(wa) <= 11:
        wa = "55" + wa
    return {"assunto": assunto, "texto": corpo, "descricao": desc, "pronac": ident, "valor": valor, "data": data, "mp_ref": ref, "contraparte": quem,
            "whatsapp_link": f"https://wa.me/{wa}?text={quote(assunto + chr(10) + chr(10) + corpo)}" if 12 <= len(wa) <= 15 else "",
            "faltam": faltam(d)}


def situacao(con, r) -> dict:
    """{pedida_em, n_pedidos, atrasada} da despesa (pedida = pedido feito e comprovante ainda não chegou)."""
    em = r["nota_pedida_em"] if "nota_pedida_em" in r.keys() else None
    n = con.execute("SELECT COUNT(*) FROM nota_pedido WHERE despesa_id=? AND situacao<>'falhou'", (r["id"],)).fetchone()[0]
    atras = bool(em and datetime.now(timezone.utc) - datetime.fromisoformat(em).replace(tzinfo=timezone.utc) >= timedelta(days=lembrete_dias(con)))
    return {"pedida_em": em, "n_pedidos": n, "atrasada": atras}


def atrasadas(con) -> int:
    """Notas pedidas há N dias ou mais que ainda não chegaram (tarefa baixa da Home do admin)."""
    corte = (datetime.now(timezone.utc) - timedelta(days=lembrete_dias(con))).strftime("%Y-%m-%d %H:%M:%S")
    return con.execute("SELECT COUNT(*) FROM despesa WHERE apagado_em IS NULL AND nota_pedida_em IS NOT NULL AND nota_pedida_em<=?", (corte,)).fetchone()[0]


def ao_anexar(con, did: int, ator: str) -> None:
    """O comprovante chegou: a despesa deixa de estar "nota pedida". Não faz commit."""
    if con.execute("UPDATE despesa SET nota_pedida_em=NULL WHERE id=? AND nota_pedida_em IS NOT NULL", (did,)).rowcount:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa',?,'nota_chegou',?,'{}')", (str(did), ator))


def apagar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): apaga o contato guardado do fornecedor e tira e-mail, WhatsApp e texto dos pedidos. Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    n = con.execute("DELETE FROM fornecedor_contato WHERE lower(email)=?", (em,)).rowcount
    n += con.execute("UPDATE nota_pedido SET para=?, whatsapp=NULL, texto=NULL WHERE lower(para)=?", (REMOVIDO, em)).rowcount
    return n


# ---------------------------------------------------------------- rotas (só admin e master)
class Pedido(BaseModel):
    email: str | None = None
    whatsapp: str | None = None
    descricao: str | None = None
    valor: float | None = None
    data: str | None = None
    mp_ref: str | None = None
    canal: str = "email"


class Dados(BaseModel):
    razao_social: str = ""
    cnpj: str = ""
    inscricao_municipal: str = ""
    endereco: str = ""
    email_notas: str = ""
    lembrete_dias: int | None = None


@router.get("/dados-camp")
def ver_dados(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        d = dados_camp(con)
        return {"dados": d, "faltam": faltam(d), "lembrete_dias": lembrete_dias(con), "smtp": email_envio.configurado(email_envio.configuracao(con))}
    finally:
        con.close()


@router.put("/dados-camp")
def salvar_dados(b: Dados, u: dict = Depends(auth.exige("admin"))) -> dict:
    v = {"razao_social": _txt(b.razao_social, 200), "cnpj": re.sub(r"\D", "", b.cnpj or ""), "inscricao_municipal": _txt(b.inscricao_municipal, 40),
         "endereco": _txt(b.endereco, 300), "email_notas": _txt(b.email_notas, 160).lower()}
    if v["cnpj"] and not cnpj_valido(v["cnpj"]):
        raise HTTPException(400, "CNPJ inválido: confira os 14 números")
    if v["email_notas"] and not email_envio.ENDERECO.match(v["email_notas"]):
        raise HTTPException(400, "O e-mail que recebe as notas não é válido")
    con = connect()
    try:
        for k, val in v.items():
            con.execute("""INSERT INTO configuracao (chave, valor, descricao, sensivel, atualizado_em, atualizado_por) VALUES (?,?,?,0,datetime('now'),?)
                           ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, atualizado_em=excluded.atualizado_em, atualizado_por=excluded.atualizado_por""",
                        ("faturamento." + k, val, f"Financeiro · nota fiscal: {k}", _ator(u)))
        if b.lembrete_dias is not None:
            if not 1 <= int(b.lembrete_dias) <= 90:
                raise HTTPException(400, "Lembrete: de 1 a 90 dias")
            con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave='notas.lembrete_dias'", (str(int(b.lembrete_dias)), _ator(u)))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro','faturamento','dados_camp_nota',?,?)",
                    (_ator(u), json.dumps({"campos": [k for k, val in v.items() if val]}, ensure_ascii=False)))
        con.commit()
        d = dados_camp(con)
        return {"dados": d, "faltam": faltam(d), "lembrete_dias": lembrete_dias(con)}
    finally:
        con.close()


@router.get("/pedidas")
def pedidas(u: dict = Depends(auth.exige("admin"))) -> dict:
    """As despesas com nota pedida que ainda não chegou (de qualquer mês), da mais antiga à mais nova."""
    con = connect()
    try:
        out = []
        for r in con.execute("SELECT * FROM despesa WHERE apagado_em IS NULL AND nota_pedida_em IS NOT NULL ORDER BY nota_pedida_em, id"):
            out.append({"id": r["id"], "data": r["data"], "valor": r["valor"], "contraparte": r["contraparte"] or "", **situacao(con, r)})
        return {"itens": out, "lembrete_dias": lembrete_dias(con), "atrasadas": sum(1 for x in out if x["atrasada"])}
    finally:
        con.close()


@router.get("/{did}")
def preparar(did: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """O formulário já preenchido: contato guardado do fornecedor, descrição (justificativa + PRONAC), valor, data, referência e a prévia."""
    con = connect()
    try:
        r = _despesa(con, did)
        ct = contato(con, r["contraparte"] or "")
        ult = con.execute("SELECT descricao FROM nota_pedido WHERE despesa_id=? AND descricao IS NOT NULL ORDER BY id DESC LIMIT 1", (did,)).fetchone()
        m = montar(con, r, Pedido(whatsapp=ct["whatsapp"], descricao=ult[0] if ult and not (r["justificativa"] or "").strip() else None))
        hist = [{"canal": h["canal"], "canal_nome": CANAIS.get(h["canal"], h["canal"]), "situacao": h["situacao"], "para": h["para"] or "", "erro": h["erro"] or "",
                 "quando": h["criado_em"], "por": h["criado_por"] or ""}
                for h in con.execute("SELECT * FROM nota_pedido WHERE despesa_id=? ORDER BY id DESC LIMIT 20", (did,))]
        tem_comp = bool(con.execute("SELECT 1 FROM despesa_anexo WHERE despesa_id=? AND apagado_em IS NULL", (did,)).fetchone())
        return {"despesa_id": did, "email": ct["email"], "whatsapp": ct["whatsapp"], "contato_guardado": bool(ct["email"] or ct["whatsapp"]), **m,
                "situacao": situacao(con, r), "historico": hist, "tem_comprovante": tem_comp,
                "smtp": email_envio.configurado(email_envio.configuracao(con)), "dados_camp": dados_camp(con)}
    finally:
        con.close()


@router.post("/{did}/previa")
def previa(did: int, b: Pedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return montar(con, _despesa(con, did), b)
    finally:
        con.close()


@router.post("/{did}/pedir")
def pedir(did: int, b: Pedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    """canal email: manda pelo SMTP do painel; canal copiado/whatsapp: registra que quem pediu mandou por conta própria. As duas marcam a
    despesa como "nota pedida" e guardam o contato do fornecedor. 'Pedir de novo' é a mesma chamada."""
    if b.canal not in CANAIS:
        raise HTTPException(400, "Canal inválido")
    if b.data:
        try:
            date.fromisoformat(b.data)
        except ValueError:
            raise HTTPException(400, "Data do pagamento inválida (AAAA-MM-DD)")
    if b.valor is not None and not 0 < float(b.valor) <= 10_000_000:
        raise HTTPException(400, "Valor inválido")
    para = _txt(b.email, 160).lower()
    if para and not email_envio.ENDERECO.match(para):
        raise HTTPException(400, "O e-mail do fornecedor não é válido")
    if b.canal == "email" and not para:
        raise HTTPException(400, "Escreva o e-mail do fornecedor (ou use Copiar texto ou o WhatsApp)")
    wa = re.sub(r"\D", "", b.whatsapp or "")
    if b.canal == "whatsapp" and not 10 <= len(wa) <= 15:
        raise HTTPException(400, "Escreva o WhatsApp do fornecedor com DDD")
    con = connect()
    try:
        r = _despesa(con, did)
        if con.execute("SELECT 1 FROM despesa_anexo WHERE despesa_id=? AND apagado_em IS NULL", (did,)).fetchone():
            raise HTTPException(409, "Esta despesa já tem comprovante: não é preciso pedir a nota")
        m = montar(con, r, b)
        if m["faltam"]:
            raise HTTPException(400, "Faltam os dados da CAMP para a nota fiscal: " + ", ".join(m["faltam"])
                                + ". Preencha em Dados da CAMP para a nota fiscal (uma vez só); o pedido não saiu.")
        ator = _ator(u)
        situ, erro = "registrado", None
        if b.canal == "email":
            smtp = email_envio.configuracao(con)
            if not email_envio.configurado(smtp):
                raise HTTPException(400, "O e-mail do painel (SMTP) não está configurado em Configurações: use Copiar texto ou o WhatsApp. O pedido não saiu.")
            try:
                email_envio.enviar(smtp, para, m["assunto"], m["texto"], responder_para=dados_camp(con)["email_notas"])
                situ = "enviado"
            except email_envio.EnvioErro as e:
                situ, erro = "falhou", str(e)[:200]
        con.execute("INSERT INTO nota_pedido (despesa_id, canal, situacao, para, whatsapp, assunto, descricao, texto, pronac, erro, criado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (did, b.canal, situ, para or None, wa or None, m["assunto"], m["descricao"] or None, m["texto"], 1 if m["pronac"] else 0, erro, ator))
        de_novo = bool(r["nota_pedida_em"])
        if situ != "falhou":
            con.execute("UPDATE despesa SET nota_pedida_em=datetime('now') WHERE id=?", (did,))
            if _chave(r["contraparte"] or "") and (para or wa):
                con.execute("""INSERT INTO fornecedor_contato (chave, contraparte, email, whatsapp, atualizado_por) VALUES (?,?,?,?,?)
                               ON CONFLICT(chave) DO UPDATE SET email=COALESCE(excluded.email, fornecedor_contato.email),
                               whatsapp=COALESCE(excluded.whatsapp, fornecedor_contato.whatsapp), atualizado_por=excluded.atualizado_por, atualizado_em=datetime('now')""",
                            (_chave(r["contraparte"]), _txt(r["contraparte"], 160), para or None, wa or None, ator))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa',?,?,?,?)",
                    (str(did), "nota_pedida" if situ != "falhou" else "nota_pedido_falhou", ator,
                     json.dumps({"canal": b.canal, "de_novo": de_novo, "pronac": bool(m["pronac"]), **({"erro": erro} if erro else {})}, ensure_ascii=False)))
        con.commit()
        if situ == "falhou":
            raise HTTPException(502, f"O e-mail não saiu ({erro}). Use Copiar texto ou o WhatsApp; a despesa não foi marcada como nota pedida.")
        r2 = _despesa(con, did)
        return {"ok": True, "situacao": situ, "de_novo": de_novo, **situacao(con, r2), "texto": m["texto"], "assunto": m["assunto"]}
    finally:
        con.close()
