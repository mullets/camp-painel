"""WP-AUD-01: testar entrega exatamente uma vez e resistência a falhas de ACK/COMMIT.

Rodar: PYTHONPATH=backend python -m unittest discover -s tests -p 'teste_coleta_pedidos_ack.py'
Usa SQLite em memória e HTTP falso, não consulta WordPress/painel reais.
"""
import json
import logging
import sqlite3
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import coletor_pedidos_site as cp


def banco():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE pedido_site (site_id INTEGER PRIMARY KEY, tipo TEXT, codigo TEXT, criado_no_site TEXT,
          payload TEXT NOT NULL, destino TEXT, destino_id INTEGER, situacao TEXT NOT NULL DEFAULT 'pendente',
          erro TEXT, recebido_em TEXT DEFAULT (datetime('now')), importado_em TEXT);
      CREATE TABLE pedido_site_coleta (id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT DEFAULT (datetime('now')),
          lidas INTEGER DEFAULT 0, novas INTEGER DEFAULT 0, importadas INTEGER DEFAULT 0, erro TEXT);
      CREATE TABLE solicitacao (id INTEGER PRIMARY KEY AUTOINCREMENT, solicitante TEXT, email TEXT,
          instituicao TEXT, finalidade TEXT, detalhe TEXT, origem TEXT);
      CREATE TABLE solicitacao_item (solicitacao_id INTEGER, codigo TEXT, formato TEXT,
          UNIQUE(solicitacao_id,codigo,formato));
      CREATE TABLE evento (id INTEGER PRIMARY KEY AUTOINCREMENT, entidade TEXT, codigo TEXT, tipo TEXT,
          ator TEXT, detalhe TEXT);
      CREATE TABLE erro (id INTEGER PRIMARY KEY AUTOINCREMENT, gravidade TEXT, categoria TEXT, origem TEXT,
          codigo TEXT, descricao TEXT, relatado_por TEXT);
      CREATE TABLE projeto (codigo TEXT PRIMARY KEY);
      CREATE TABLE item (codigo TEXT PRIMARY KEY);
      CREATE TABLE fundo (codigo TEXT PRIMARY KEY);
      CREATE TABLE configuracao (chave TEXT, valor TEXT);
    """)
    return c


class Resposta:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self.data = data
    def json(self):
        return self.data


class HttpFalso:
    def __init__(self, dados):
        self.dados = dados
        self.confirmados = set()
        self.tentativas_ack = 0
        self.falhar_proximo_ack = False
        self.get_params = []

    def get(self, rota, params):
        self.get_params.append(params)
        assert rota == "/wp-json/camp/v1/solicitacoes"
        assert "marcar" not in params, "leitura jamais deve marcar"
        return Resposta(data=[x for x in self.dados if x["id"] not in self.confirmados][:params["limite"]])

    def post(self, rota, json):
        self.tentativas_ack += 1
        assert rota == "/wp-json/camp/v1/solicitacoes/confirmar"
        if self.falhar_proximo_ack:
            self.falhar_proximo_ack = False
            return Resposta(503, {})
        novos = [x for x in json["ids"] if x not in self.confirmados]
        antigos = [x for x in json["ids"] if x in self.confirmados]
        self.confirmados.update(json["ids"])
        return Resposta(data={"confirmados": novos, "ja_confirmados": antigos,
                              "nao_encontrados": [], "falhas": []})


class WPFalso:
    def __init__(self, http):
        self.h = http


def pedidos(n):
    return [{"id": i, "tipo": "consulta", "nome": f"Pessoa {i}", "email": "teste@example.org",
             "codigo": "F001", "finalidade": "pesquisa", "mensagem": "Visita ao acervo",
             "criado_em": "2026-10-22T12:00:00Z"} for i in range(1, n + 1)]


class FalhaCommit:
    """Simula queda do SQLite ANTES do commit do primeiro lote."""
    def __init__(self, real):
        self.real = real
        self.falha = True
    def execute(self, *a, **kw):
        return self.real.execute(*a, **kw)
    def commit(self):
        if self.falha:
            self.falha = False
            raise sqlite3.OperationalError("falha proposital antes do commit")
        return self.real.commit()
    def rollback(self):
        return self.real.rollback()


class TesteColetaACK(unittest.TestCase):
    def setUp(self):
        self.con = banco()
        self.p = patch.object(cp, "registrar")
        self.p.start()
    def tearDown(self):
        self.p.stop()
        self.con.close()

    def contar(self, tabela):
        return self.con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]

    def test_mais_de_200_pedidos_sem_pular_pagina(self):
        h = HttpFalso(pedidos(225))
        r = cp.coletar(con=self.con, wp=WPFalso(h), avisar=False)
        self.assertEqual((r["lidas"], r["novas"], r["confirmadas"], r["importadas"]),
                         (225, 225, 225, 225))
        self.assertEqual(self.contar("pedido_site"), 225)
        self.assertEqual(self.contar("solicitacao"), 225)
        self.assertEqual(len(h.confirmados), 225)
        self.assertTrue(all("marcar" not in q for q in h.get_params))

    def test_queda_de_rede_depois_do_commit_antes_do_ack(self):
        h = HttpFalso(pedidos(1))
        h.falhar_proximo_ack = True
        a = cp.coletar(con=self.con, wp=WPFalso(h), avisar=False)
        self.assertEqual((a["novas"], a["confirmadas"]), (1, 0))
        self.assertTrue(a["erro"])
        self.assertEqual(self.contar("pedido_site"), 1)
        self.assertEqual(self.contar("solicitacao"), 1)
        self.assertEqual(len(h.confirmados), 0)
        b = cp.coletar(con=self.con, wp=WPFalso(h), avisar=False)
        self.assertEqual((b["novas"], b["confirmadas"], b["importadas"]), (0, 1, 0))
        self.assertEqual(self.contar("solicitacao"), 1)
        self.assertEqual(len(h.confirmados), 1)

    def test_falha_de_commit_impede_ack(self):
        h = HttpFalso(pedidos(1))
        a = cp.coletar(con=FalhaCommit(self.con), wp=WPFalso(h), avisar=False)
        self.assertTrue(a["erro"])
        self.assertEqual(h.tentativas_ack, 0)
        self.assertEqual(self.contar("pedido_site"), 0)
        b = cp.coletar(con=self.con, wp=WPFalso(h), avisar=False)
        self.assertEqual((b["novas"], b["confirmadas"]), (1, 1))
        self.assertEqual(self.contar("solicitacao"), 1)

    def test_resposta_invalida_nao_confirma(self):
        h = HttpFalso([{"id": "invalido", "nome": "Teste"}])
        r = cp.coletar(con=self.con, wp=WPFalso(h), avisar=False)
        self.assertTrue(r["erro"])
        self.assertEqual(h.tentativas_ack, 0)
        self.assertEqual(self.contar("pedido_site"), 0)


if __name__ == "__main__":
    unittest.main()
