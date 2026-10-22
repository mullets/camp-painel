"""Testa registro transacional da fila de correções publicada."""
import sqlite3
import unittest
from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / "db" / "migrations" / "150_fila_correcao_site.sql"

class FilaTriggerTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript("""CREATE TABLE item (
            codigo TEXT PRIMARY KEY, tainacan_item_id INT, status_site TEXT, titulo TEXT,
            tipo_documento TEXT, tipos_documento TEXT, folha TEXT, escala TEXT, ano_folha INT,
            endereco_folha TEXT, cliente_folha TEXT, suporte TEXT, giro_manual INT,
            espelho_manual INT, recorte TEXT, alinhamento REAL, imagem_corrigida TEXT);""")
        self.con.executescript(SQL.read_text(encoding="utf-8"))
        self.con.execute("INSERT INTO item(codigo,tainacan_item_id,status_site,titulo) VALUES('F001-P0001-S01-D00001',100,'no_ar','Planta')")
    def tearDown(self):
        self.con.close()
    def test_edicao_insere(self):
        self.con.execute("UPDATE item SET titulo='Planta nova' WHERE codigo='F001-P0001-S01-D00001'")
        self.assertEqual(self.con.execute("SELECT versao FROM fila_correcao_site").fetchone()[0], 1)
    def test_nova_edicao_substitui_versao(self):
        self.con.execute("UPDATE item SET titulo='Planta nova' WHERE codigo='F001-P0001-S01-D00001'")
        self.con.execute("UPDATE item SET escala='1:100' WHERE codigo='F001-P0001-S01-D00001'")
        self.assertEqual(self.con.execute("SELECT versao FROM fila_correcao_site").fetchone()[0], 2)
    def test_edicao_igual_nao_entra(self):
        self.con.execute("UPDATE item SET titulo='Planta' WHERE codigo='F001-P0001-S01-D00001'")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM fila_correcao_site").fetchone()[0], 0)
    def test_nao_publicada_nao_entra(self):
        self.con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo='F001-P0001-S01-D00001'")
        self.con.execute("UPDATE item SET titulo='Planta outra' WHERE codigo='F001-P0001-S01-D00001'")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM fila_correcao_site").fetchone()[0], 0)
    def test_rollback_nao_deixa_fila(self):
        self.con.commit()
        self.con.execute("BEGIN")
        self.con.execute("UPDATE item SET titulo='Mudou' WHERE codigo='F001-P0001-S01-D00001'")
        self.con.rollback()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM fila_correcao_site").fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
