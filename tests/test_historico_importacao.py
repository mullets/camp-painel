"""REF-040: reexecução do mesmo pacote não inventa uma atividade."""
import sqlite3
import unittest
from app.historico_importacao import registrar_importacao

class HistoricoImportacaoTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("""CREATE TABLE evento(
            id INTEGER PRIMARY KEY, entidade TEXT, codigo TEXT, tipo TEXT,
            ator TEXT, detalhe TEXT)""")
        self.p = "F026-P0004"
        self.d = [{"codigo": "F026-P0004-S01-D00001", "titulo": "Planta"}]

    def tearDown(self):
        self.con.close()

    def registrar(self, **contagens):
        return registrar_importacao(self.con, self.p, "operador", 37, contagens, self.d)

    def eventos(self):
        return self.con.execute("SELECT COUNT(*) FROM evento").fetchone()[0]

    def test_zero_folhas_zero_atividade(self):
        for _ in range(12):
            self.assertFalse(self.registrar(criadas=0, atualizadas=0, ignoradas=7, retirados=7, problemas=7))
        self.assertEqual(self.eventos(), 0)

    def test_primeira_importacao_e_reenvio(self):
        dados = dict(criadas=5, atualizadas=0, ignoradas=0, problemas=0)
        self.assertTrue(self.registrar(**dados))
        for _ in range(5):
            self.assertFalse(self.registrar(**dados))
        self.assertEqual(self.eventos(), 1)

    def test_nova_folha_e_novo_pacote(self):
        self.assertTrue(self.registrar(criadas=2))
        self.d.append({"codigo": "F026-P0004-S01-D00002", "titulo": "Corte"})
        self.assertTrue(self.registrar(criadas=1))
        self.assertEqual(self.eventos(), 2)

    def test_somente_novo_problema_e_evento_util(self):
        self.assertTrue(self.registrar(criadas=0, problemas_registrados=1))
        self.assertFalse(self.registrar(criadas=0, problemas_registrados=0))
        self.assertEqual(self.eventos(), 1)

if __name__ == "__main__":
    unittest.main()
