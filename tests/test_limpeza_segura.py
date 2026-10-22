"""A limpeza geral não pode fechar bloqueios reais, autoria, códigos e duplicatas."""
import sqlite3
import unittest
from unittest.mock import patch
from app.limpeza_segura import candidatos_seguros


class LimpezaSeguraTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("""CREATE TABLE erro (
            id INT, situacao TEXT, origem TEXT, gravidade TEXT,
            categoria TEXT, codigo TEXT, chave TEXT, descricao TEXT)""")
        self.con.executemany("INSERT INTO erro VALUES(?,?,?,?,?,?,?,?)", [
            (1,"aberto","campvision","aviso","metadado","F009-P0092","minor","Aviso menor"),
            (2,"aberto","campvision","bloqueia","metadado","F009-P0092","error","Original corrompido"),
            (3,"aberto","campvision","corrigir","autoria_divergente","F009-P0092","author","Autoria"),
            (4,"aberto","campvision","corrigir","duplicata","F009-P0092","dup","Cópia"),
            (5,"aberto","campvision","corrigir","codigo","F009-P0092","cod","Código incerto"),
            (6,"aberto","operador","aviso","metadado","F009-P0092",None,"Equipe"),
            (7,"aberto","campvision","corrigir","orientacao","F009-P0092","giro","Giro corrigido"),
        ])
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_so_informativo_com_prova(self):
        def explicar(e, ctx):
            if e["id"] in (1,2,3,4,5,7):
                return {"resolvido_sozinho":{"seguro":True,"motivo":"já conferido"}}
            return {"resolvido_sozinho":None}
        with patch("app.problemas.contexto",return_value={}),patch("app.problemas.explicar",side_effect=explicar):
            encontrados=candidatos_seguros(self.con)
        self.assertEqual([x["id"] for x in encontrados],[1,7])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM erro").fetchone()[0],7)

    def test_ambiguidade_nao_fecha(self):
        with patch("app.problemas.contexto",return_value={}),patch("app.problemas.explicar",return_value={"resolvido_sozinho":None}):
            self.assertEqual(candidatos_seguros(self.con),[])


if __name__=="__main__":
    unittest.main()
