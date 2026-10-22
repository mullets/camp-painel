"""CAMP-145: CV2 sugere, painel e pessoas decidem.

Isolado: PYTHONPATH=backend python3 -m unittest tests.test_cv2_nao_decide
"""
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.saidas_cv import avaliar_aceite
from app.publicacao_guiada import lotes_para_aprovar
from app.rotas_revisao import _pode_importar


class ParecerNaoEVetoTest(unittest.TestCase):
    def test_reprovacao_cv_vira_aviso_sem_folhas_pendentes(self):
        itens = [{"ok": False, "chave": "contagem_exif", "rotulo": "Contagem",
                  "acao": None, "como": "CV2 encontrou inconsistência"}]
        with patch("app.saidas_cv.itens_aceite", return_value=itens), patch(
                "app.saidas_cv.motivos_aceite", return_value=["Contagem incerta"]):
            r = avaliar_aceite({"publicavel": False}, {"total": 0, "pendentes": 0})
        self.assertEqual(r["situacao"], "aviso")
        self.assertEqual(r["faltam"], [])
        self.assertEqual(r["motivos"], ["Contagem incerta"])

    def test_quarenta_e_uma_conferidas_superam_veto_automatico(self):
        itens = [{"ok": False, "chave": "orientacao_incerta_zerada", "rotulo": "Orientação"}]
        with patch("app.saidas_cv.itens_aceite", return_value=itens), patch(
                "app.saidas_cv.motivos_aceite", return_value=["Orientação incerta"]):
            r = avaliar_aceite({"publicavel": False}, {"total": 41, "pendentes": 0})
        self.assertEqual(r["situacao"], "resolvido")

    def test_avisos_ainda_exigem_revisar_folhas_pendentes(self):
        itens = [{"ok": False, "chave": "orientacao_incerta_zerada", "rotulo": "Orientação"}]
        with patch("app.saidas_cv.itens_aceite", return_value=itens), patch(
                "app.saidas_cv.motivos_aceite", return_value=["Orientação incerta"]):
            r = avaliar_aceite({"publicavel": False}, {"total": 41, "pendentes": 3})
        self.assertEqual(r["situacao"], "reprovado")
        self.assertEqual(r["faltam"][0]["acao"], "conferir")


class LotesSeparadosTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
            CREATE TABLE lista_processamento (
                id INTEGER PRIMARY KEY, projeto_codigo TEXT, etapa TEXT,
                aprovado_em TEXT, descartado_em TEXT
            );
            CREATE TABLE item (
                codigo TEXT, lote_id INTEGER, revisao TEXT, duplicata_de TEXT
            );
            INSERT INTO lista_processamento VALUES (43, 'F009-P0092', 'revisao', NULL, NULL);
            INSERT INTO lista_processamento VALUES (44, 'F009-P0092', 'revisao', NULL, NULL);
        """)
        self.con.executemany("INSERT INTO item VALUES (?,43,'conferida',NULL)",
                             [(f'F009-P0092-1981-S01-D{x:05}',) for x in range(1,42)])
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_publicacao_aprova_so_o_lote_que_tem_folhas(self):
        ids, total = lotes_para_aprovar(self.con, "F009-P0092")
        self.assertEqual((ids, total), ([43], 1))

    def test_importador_explica_pacote_so_com_retiradas(self):
        with TemporaryDirectory() as pasta:
            l = {"id": 44, "projeto_codigo": "F009-P0092",
                 "pasta_qnap": pasta, "descartado_em": None,
                 "aprovado_em": None, "etapa": "revisao"}
            with patch("app.rotas_revisao.ler_pacote", return_value={
                "projeto_codigo": "F009-P0092", "documentos": [],
                "retirados": [{"codigo":"F009-P0092-1981-S01-D00001"}]}):
                permitido, motivo = _pode_importar(self.con, l)
            self.assertFalse(permitido)
            self.assertIn("trazê-las para conferência", motivo)


if __name__ == "__main__":
    unittest.main()
