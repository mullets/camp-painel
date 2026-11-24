"""CAMP-FIN: pagamentos falsos de todas as fontes do Financeiro (novembro de 2026) e a conta do Mercado Pago FALSA (como o site devolve
em GET /wp-json/camp/v1/painel/mp/pagamentos, contrato 1.33). Usado pelo teste de backend (modo financeiro_receitas) e pelo de navegador.
Nada aqui fala com o site nem com o Mercado Pago de verdade.

Uso direto (navegador): python3 tests/semente_financeiro.py <banco.db>  → grava as fontes e a cópia da conta do Mercado Pago.
"""
import json
import sqlite3
import sys

TOKEN_FALSO = "APP_USR-SEGREDO-NAO-PODE-APARECER-123"


def semear(con) -> None:
    j = json.dumps
    am = [(11, "amigo", "anual", "Ana Amiga", "amigo"), (12, "amigo", "mensal", "Bruno Mensal", "amigo"), (13, "projeto", None, "Clara Adota", None)]
    ids = {}
    for sid, tipo, mod, nome, cat in am:
        ids[sid] = con.execute("INSERT INTO amigo (site_id, tipo, modalidade, nome, categoria, email) VALUES (?,?,?,?,?,?)",
                               (sid, tipo, mod, nome, cat, f"p{sid}@exemplo.com")).lastrowid
    pg = [(11, "mp-5000", "2026-10-20", 450, "credit_card", "approved"), (11, "mp-5001", "2026-11-05", 450, "credit_card", "approved"),
          (11, "painel-aa01", "2026-11-06", 200, "pix", "approved"), (12, "mp-5002", "2026-11-10", 45, "credit_card", "approved"),
          (12, "mp-5009", "2026-11-03", 45, "credit_card", "refunded"), (13, "mp-5003", "2026-11-07", 1000, "bank_transfer", "approved"),
          (12, "mp-5010", "2026-11-11", 45, "credit_card", "rejected")]
    for sid, ch, d, v, meio, st in pg:
        con.execute("INSERT INTO amigo_pagamento (amigo_id, chave, data, valor, meio, origem, status) VALUES (?,?,?,?,?,?,?)",
                    (ids[sid], ch, d, v, meio, "manual" if ch.startswith("painel-") else "mp", st))

    def cob(sid, fin, nome, valor, sit, pag, titulo=None, desc="Contribuição"):
        p = [pag] if pag else []
        con.execute("""INSERT INTO cobranca_avulsa (ref_painel, site_id, nome, email, valor, finalidade, descricao, situacao, external_reference, mp_titulo,
                       mp_pagamento_id, pago_em, valor_pago, valor_liquido, tarifa, meio, pagamentos) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"painel-cob-{sid}", sid, nome, f"c{sid}@exemplo.com", valor, fin, desc, sit, f"CAMP-COB-{sid}", titulo,
                     (pag or {}).get("id"), (pag or {}).get("pago_em"), (pag or {}).get("valor"), (pag or {}).get("liquido"), (pag or {}).get("tarifa"),
                     (pag or {}).get("meio"), j(p) if p else None))
    cob(801, "doacao", "Davi Doador", 300, "paga", {"id": "6001", "status": "approved", "valor": 300, "tarifa": 14.97, "liquido": 285.03, "meio": "bank_transfer", "pago_em": "2026-11-12T15:00:00Z"},
        "CAMP · Doação · apoio livre")
    cob(802, "doacao_acervo", "Eva Acervo", 2000, "paga", {"id": "6002", "status": "approved", "valor": 2000, "tarifa": 99.8, "liquido": 1900.2, "meio": "credit_card", "pago_em": "2026-11-13T14:00:00Z"},
        "CAMP · Doação de acervo — tratamento/digitalização · Acervo Eva")
    cob(803, "patrocinio", "Ana Diretora", 12000, "paga", {"id": "6003", "status": "approved", "valor": 12000, "meio": "bank_transfer", "pago_em": "2026-11-14T13:00:00Z"},
        "CAMP · Patrocínio · cota Parceiro")
    cob(804, "servico", "Gil Serviço", 500, "paga", {"id": "6004", "status": "approved", "valor": 500, "meio": "ticket", "pago_em": "2026-11-17T13:00:00Z"}, None, "Digitalização")
    cob(805, "outro", "=cmd|' /C calc'!A0", 100, "paga", {"id": "6005", "status": "approved", "valor": 100, "meio": "credit_card", "pago_em": "2026-11-19T13:00:00Z"}, None, "Outra")
    cob(806, "doacao", "Hugo Estorno", 250, "estornada", {"id": "6006", "status": "refunded", "valor": 250, "meio": "credit_card", "pago_em": "2026-11-08T13:00:00Z"}, "CAMP · Doação · estornada")
    cob(807, "doacao", "Iris Sem Pagamento", 90, "paga", None, "CAMP · Doação · sem pagamento")
    con.execute("INSERT INTO doacao_acervo (site_id, protocolo, nome, etapa, valor, dados) VALUES (901, 'CAMP-2026-000901', 'Eva Acervo', 'paga', 2000, ?)",
                (j({"cobranca": {"id": 802, "situacao": "paga"}, "documento": "12345678909", "documento_tipo": "cpf"}),))
    con.execute("INSERT INTO patrocinio (site_id, protocolo, cota, modalidade, empresa, cnpj, nome, etapa, valor_anual, valor_pago, dados) VALUES (701,'CAMP-2026-000701','parceiro','anual','Construtora Exemplo','11.222.333/0001-81','Ana Diretora','pago',12000,12000,?)",
                (j({"cota_nome": "Parceiro", "cobranca": {"id": 803, "situacao": "paga"}, "pagamentos": []}),))
    con.execute("INSERT INTO patrocinio (site_id, protocolo, cota, modalidade, empresa, cnpj, nome, etapa, valor_anual, valor_pago, dados) VALUES (702,'CAMP-2026-000702','mantenedor','mensal','Grande SA','22.333.444/0001-55','Beto','pago',24000,2000,?)",
                (j({"cota_nome": "Mantenedor", "cobranca": None, "pagamentos": [
                    {"id": "7001", "status": "approved", "valor": 2000, "meio": "credit_card", "pago_em": "2026-11-15T10:00:00-03:00"},
                    {"id": "6003", "status": "approved", "valor": 12000, "meio": "bank_transfer", "pago_em": "2026-11-14T10:00:00-03:00"}]}),))
    con.execute("INSERT INTO ingresso (site_id, ref, casa, visita, data, hora, nome, pessoas, total, situacao, pagamentos) VALUES (401,'CAMP-INGRESSO-JM-20261128-1000-1','JM','Visita guiada à Residência João Marino','2026-11-28','10:00','Fabio Visita',1,120,'pago',?)",
                (j([{"id": "8001", "valor": 120, "meio": "account_money", "data": "2026-11-16T10:00:00-03:00"}]),))
    con.commit()


def conta_mp() -> list[dict]:
    """Como o site devolve cada pagamento (contrato 1.33): só o nome de quem pagou, sem CPF nem e-mail."""
    def p(i, quando, valor, ref, st="approved", tarifa=None, liquido=None, meio="credit_card", metodo="visa", desc="", pagador="", refunds=None, est=0):
        return {"id": i, "date_approved": quando, "status": st, "transaction_amount": valor, "fee_details": [{"type": "mercadopago_fee", "amount": tarifa}] if tarifa is not None else [],
                "net_received_amount": liquido, "payment_type_id": meio, "payment_method_id": metodo, "external_reference": ref, "description": desc,
                "pagador": pagador, "refunds": refunds or [], "transaction_amount_refunded": est, "access_token": TOKEN_FALSO}
    return [
        p(5001, "2026-11-05T10:00:00.000-04:00", 450, "CAMP-AMIGO-11", tarifa=22.45, liquido=427.55, pagador="Ana Amiga"),
        p(5002, "2026-11-10T10:00:00.000-04:00", 45, "", tarifa=2.25, liquido=42.75, pagador="Bruno Mensal"),
        p(5009, "2026-11-03T10:00:00.000-04:00", 45, "CAMP-AMIGO-12", st="refunded", tarifa=2.25, liquido=0, refunds=[{"amount": 45, "date_created": "2026-11-20T12:00:00.000-04:00"}], est=45),
        p(6001, "2026-11-12T12:00:00.000-03:00", 300, "CAMP-COB-801", tarifa=14.97, liquido=285.03, meio="bank_transfer", metodo="pix"),
        p(6003, "2026-11-14T10:00:00.000-03:00", 12000, "CAMP-COB-803", tarifa=119.88, liquido=11880.12, meio="bank_transfer", metodo="pix"),
        p(6006, "2026-11-08T10:00:00.000-03:00", 250, "CAMP-COB-806", st="refunded", tarifa=12.48, liquido=0, refunds=[{"amount": 250, "date_created": "2026-11-21T09:00:00.000-03:00"}], est=250),
        p(8001, "2026-11-16T10:00:00.000-03:00", 120, "CAMP-INGRESSO-JM-20261128-1000-1", tarifa=5.99, liquido=114.01, meio="account_money", metodo="account_money"),
        p(9001, "2026-11-18T09:30:00.000-03:00", 150, "", tarifa=0, liquido=150, meio="bank_transfer", metodo="pix", desc="Pix recebido", pagador="Gabi Pix"),
        p(9002, "2026-11-18T11:00:00.000-03:00", 450, "CAMP-AMIGO-999", tarifa=22.45, liquido=427.55, pagador="Sem Cadastro"),
        p(9003, "2026-11-18T12:00:00.000-03:00", 70, "", st="cancelled", pagador="Cancelado"),
        p(9004, "2026-11-22T12:00:00.000-03:00", 80, "LOJA-XYZ", tarifa=3.99, liquido=76.01, desc="QR code da recepção", pagador="Joana QR"),
    ]


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "backend"))
    c = sqlite3.connect(sys.argv[1])
    c.row_factory = sqlite3.Row
    semear(c)
    from app import financeiro as f   # noqa: E402

    class _R:
        def __init__(s, d): s.status_code, s._d = 200, d
        def json(s): return s._d

    class _H:
        def get(s, path, params=None): return _R({"itens": conta_mp(), "mais": False, "agora": "2026-11-24T12:00:00Z"})

    class _W:
        h = _H()
    f.coletar_mp(c, _W(), de="2026-11-01", ate="2026-11-30")
    c.close()
