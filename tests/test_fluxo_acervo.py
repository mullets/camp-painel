"""CAMP-145: regressão da situação do lote. Só SQLite em memória, sem servidor/QNAP/site.

Rodar na raiz: python3 -m unittest tests/test_fluxo_acervo.py
"""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.filas_fase import (  # noqa: E402
    escolher_lote_ativo,
    fase_da_lista,
    lote_ativo_por_projeto,
)


class FaseDaListaTest(unittest.TestCase):
    def test_transicoes_existentes(self):
        casos = [
            ("erro", 48, 3, None, "erro"),
            ("publicado", 48, 0, "2026-10-22", "publicado"),
            ("enviado", 0, 0, None, "processando"),
            ("processando", 48, 3, None, "processando"),
            ("revisao", 0, 0, None, "importar"),
            ("rascunho", 0, 0, None, "publicar"),
            ("revisao", 48, 3, None, "conferir"),
            ("revisao", 48, 0, None, "aprovar"),
            ("revisao", 48, 0, "2026-10-22", "publicar"),
        ]
        for etapa, total, pendentes, aprovado, esperado in casos:
            with self.subTest(etapa=etapa, total=total, pendentes=pendentes):
                self.assertEqual(fase_da_lista(etapa, total, pendentes, aprovado), esperado)


class EscolhaLoteTest(unittest.TestCase):
    def test_vazio(self):
        self.assertIsNone(escolher_lote_ativo([]))

    def test_nenhum_pendente_retorna_mais_recente(self):
        lotes = [{"id": 22, "fase": "publicado"}, {"id": 21, "fase": "publicado"}]
        self.assertEqual(escolher_lote_ativo(lotes)["id"], 22)

    def test_publicado_mais_recente_nao_esconde_antigo_pendente(self):
        lotes = [
            {"id": 30, "fase": "publicado"},
            {"id": 29, "fase": "conferir"},
            {"id": 28, "fase": "erro"},
        ]
        self.assertEqual(escolher_lote_ativo(lotes)["id"], 29)

    def test_pendente_mais_recente_tem_prioridade(self):
        lotes = [{"id": 31, "fase": "importar"}, {"id": 30, "fase": "conferir"}]
        self.assertEqual(escolher_lote_ativo(lotes)["id"], 31)

    def test_f009_p0092_lote_44_vazio_nao_esconde_41_conferidas(self):
        # Captura real do caso: lote mais novo ainda não trouxe folhas;
        # lote anterior já contém as 41 folhas com revisão encerrada.
        lotes = [
            {"id": 44, "fase": "importar", "itens_total": 0, "itens_pendentes": 0},
            {"id": 43, "fase": "aprovar", "itens_total": 41, "itens_pendentes": 0},
        ]
        self.assertEqual(escolher_lote_ativo(lotes)["id"], 43)

    def test_lote_vazio_ainda_e_pendente_se_so_houver_publicados(self):
        lotes = [
            {"id": 44, "fase": "importar", "itens_total": 0},
            {"id": 43, "fase": "publicado", "itens_total": 41},
        ]
        self.assertEqual(escolher_lote_ativo(lotes)["id"], 44)

    def test_priorizar_lote_com_material_na_consulta_sql(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.executescript("""
                CREATE TABLE lista_processamento(
                    id INT, projeto_codigo TEXT, etapa TEXT, aprovado_em TEXT, descartado_em TEXT
                );
                CREATE TABLE item(lote_id INT, projeto_codigo TEXT, revisao TEXT);
                INSERT INTO lista_processamento VALUES(43,'F009-P0092','revisao',NULL,NULL);
                INSERT INTO lista_processamento VALUES(44,'F009-P0092','revisao',NULL,NULL);
            """)
            con.executemany("INSERT INTO item VALUES(43, 'F009-P0092', 'conferida')", [()] * 41)
            atual = lote_ativo_por_projeto(con)["F009-P0092"]
            self.assertEqual((atual["lote_id"], atual["fase"], atual["itens_total"]), (43, "aprovar", 41))
        finally:
            con.close()

    def test_folha_movida_nao_mantem_lote_antigo_com_trabalho_fantasma(self):
        # Mesmo lote_id preservado por proveniência, projeto_codigo mudou
        # depois da transferência. A tela não pode pedir revisão da folha antiga.
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.executescript("""
                CREATE TABLE lista_processamento(
                    id INT, projeto_codigo TEXT, etapa TEXT, aprovado_em TEXT, descartado_em TEXT
                );
                CREATE TABLE item(lote_id INT, projeto_codigo TEXT, revisao TEXT);
                INSERT INTO lista_processamento VALUES(1,'F099-P0001','revisao',NULL,NULL);
                INSERT INTO lista_processamento VALUES(2,'F099-P0001','revisao',NULL,NULL);
                INSERT INTO lista_processamento VALUES(3,'F099-P0001','revisao',NULL,NULL);
                INSERT INTO item VALUES(1,'F099-P0001','pendente');
                INSERT INTO item VALUES(1,'F099-P0001','pendente');
                INSERT INTO item VALUES(2,'F099-P0002','pendente');
            """)
            atual = lote_ativo_por_projeto(con)["F099-P0001"]
            self.assertEqual((atual["lote_id"], atual["fase"], atual["itens_total"],
                              atual["itens_pendentes"]), (1, "conferir", 2, 2))
            # O lote 2 permanece rastreável; a folha transferida não vira
            # tarefa fantasma do projeto original.
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM item WHERE lote_id=2").fetchone()[0], 1)
        finally:
            con.close()

    def test_consulta_sql_usa_a_mesma_regra(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.executescript("""
                CREATE TABLE lista_processamento (
                    id INTEGER PRIMARY KEY,
                    projeto_codigo TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    aprovado_em TEXT,
                    descartado_em TEXT
                );
                CREATE TABLE item (lote_id INTEGER NOT NULL, projeto_codigo TEXT NOT NULL, revisao TEXT NOT NULL);
            """)
            con.executemany(
                "INSERT INTO lista_processamento VALUES (?,?,?,?,?)",
                [
                    (1, "F001-P0001", "revisao", None, None),
                    (2, "F001-P0001", "publicado", "2026-10-22", None),
                    (3, "F001-P0002", "revisao", "2026-10-22", None),
                    (4, "F001-P0003", "erro", None, "2026-10-22"),
                ],
            )
            con.executemany("INSERT INTO item VALUES (?,?,?)", [
                (1, "F001-P0001", "pendente"), (3, "F001-P0002", "conferida")])
            atual = lote_ativo_por_projeto(con)
            self.assertEqual(atual["F001-P0001"]["lote_id"], 1)
            self.assertEqual(atual["F001-P0001"]["fase"], "conferir")
            self.assertEqual(atual["F001-P0002"]["lote_id"], 3)
            self.assertEqual(atual["F001-P0002"]["fase"], "publicar")
            self.assertNotIn("F001-P0003", atual)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
