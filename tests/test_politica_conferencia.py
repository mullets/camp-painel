"""Regressões da classificação de folhas, sem dependências externas."""
import unittest
from app.revisao_politica import motivo_para_conferir

def folha(**kw):
    i = dict(codigo="F001-P0001-S01-D00001", titulo="Planta térrea", status_site="nao_publicado",
             pendencias="{}", duplicata_de=None, autoria_divergente=0, espelhado=0, espelho_manual=None)
    i.update(kw)
    return i

class PoliticaConferenciaTest(unittest.TestCase):
    def test_limpa(self):
        self.assertIsNone(motivo_para_conferir(folha()))
    def test_48_folhas_3_avisos(self):
        itens = [folha(codigo=f"D{i:05}") for i in range(48)]
        itens[3]["pendencias"] = '{"ressalvas":["giro incerto"]}'
        itens[20]["duplicata_de"] = "D00001"
        itens[35]["autoria_divergente"] = 1
        self.assertEqual(sum(motivo_para_conferir(i) is None for i in itens), 45)
    def test_sem_titulo(self):
        for valor in (None, "", "   "):
            self.assertEqual(motivo_para_conferir(folha(titulo=valor)), "sem título")
    def test_json_invalido(self):
        for valor in ("{", "[]", "null", '"incorreto"', 123):
            self.assertEqual(motivo_para_conferir(folha(pendencias=valor)), "pendências ilegíveis")
    def test_avisos(self):
        casos=[(folha(status_site="bloqueado"),"bloqueada"),
               (folha(pendencias='{"bloqueios":["corrompida"]}'),"bloqueada"),
               (folha(duplicata_de="D00001"),"duplicata"),
               (folha(autoria_divergente=1),"autoria"),
               (folha(espelhado=1),"espelhada?"),
               (folha(pendencias='{"sinais":["dúvida"]}'),"aviso do CAMP Vision")]
        for item, esperado in casos:
            self.assertEqual(motivo_para_conferir(item), esperado)
    def test_espelho_confirmado(self):
        self.assertIsNone(motivo_para_conferir(folha(espelhado=1, espelho_manual=0)))
    def test_problema_aberto(self):
        self.assertEqual(motivo_para_conferir(folha(), True), "problema aberto")

if __name__ == "__main__":
    unittest.main()
