"""REF-041: agregação não destrutiva de centenas de registros."""
import sqlite3
import unittest
from app.diagnostico_erros import diagnosticar


class DiagnosticoErrosTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("""CREATE TABLE erro(
            id INTEGER PRIMARY KEY, situacao TEXT, gravidade TEXT, categoria TEXT,
            origem TEXT, codigo TEXT, descricao TEXT, chave TEXT)""")
        self.con.executemany("INSERT INTO erro(situacao,gravidade,categoria,origem,codigo,descricao,chave) VALUES(?,?,?,?,?,?,?)", [
            ("aberto", "aviso", "metadado", "campvision", "F009-P0092", "IPTC Minor", "campvision:aviso-menor:1"),
            ("aberto", "aviso", "metadado", "campvision", "F009-P0092", "IPTC Minor", "campvision:aviso-menor:2"),
            ("em_correcao", "bloqueia", "arquivo_corrompido", "campvision", "F026-P0004", "Arquivo ilegível", "erros:3"),
            ("corrigido", "bloqueia", "arquivo_corrompido", "campvision", "F026-P0004", "Antigo", "erros:4"),
            ("aberto", "corrigir", "outro", "equipe", "F026-P0006", "Revisar autoria", None)
        ])
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_resumo_e_repeticoes(self):
        r = diagnosticar(self.con)
        self.assertEqual(r["abertos"], 4)
        self.assertEqual(r["bloqueantes"], 1)
        self.assertEqual(r["avisos"], 2)
        self.assertEqual(r["avisos_menores_exiftool"], 2)
        self.assertEqual(r["automaticos"], 3)
        self.assertEqual(r["projetos_com_mais_alertas"][0]["projeto"], "F009-P0092")
        self.assertEqual(r["repeticoes_exatas"][0]["quantidade"], 2)

    def test_diagnostico_nao_altera_banco(self):
        before = self.con.execute("SELECT COUNT(*), SUM(id) FROM erro").fetchone()
        diagnosticar(self.con)
        after = self.con.execute("SELECT COUNT(*), SUM(id) FROM erro").fetchone()
        self.assertEqual(tuple(before), tuple(after))

    def test_fila_vazia(self):
        self.con.execute("DELETE FROM erro")
        r = diagnosticar(self.con)
        self.assertEqual(r["abertos"], 0)
        self.assertEqual(r["por_tipo"], [])


if __name__ == "__main__":
    unittest.main()
