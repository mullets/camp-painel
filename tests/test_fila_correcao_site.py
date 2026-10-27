"""Fila de correções: teste isolado de SQLite e WordPress falso."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import fila_correcao_site as fila


class FilaCorrecaoSiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "acervo.db"
        con = self.con()
        con.executescript("""CREATE TABLE fila_correcao_site (
            item_codigo TEXT PRIMARY KEY, versao INT DEFAULT 1, estado TEXT DEFAULT 'pendente',
            tentativas INT DEFAULT 0, proxima_em TEXT DEFAULT (datetime('now')),
            reservado_ate TEXT, ultimo_erro TEXT, atualizado_em TEXT DEFAULT (datetime('now')));""")
        con.execute("INSERT INTO fila_correcao_site(item_codigo) VALUES('F001-P0001-S01-D00001')")
        con.commit()
        con.close()
        self.patch_connect = patch.object(fila, "connect", side_effect=self.con)
        self.patch_connect.start()
        self.patch_flag = patch("app.alteracoes_site.enviar_sozinho", return_value=True)
        self.patch_flag.start()
        self.patch_reenvio = patch.object(fila, "reenvio_ativo", return_value=True)
        self.patch_reenvio.start()

    def tearDown(self):
        self.patch_reenvio.stop()
        self.patch_flag.stop()
        self.patch_connect.stop()
        self.tmp.cleanup()

    def con(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def test_envio_confirmado_tira_fila(self):
        with patch("app.alteracoes_site.enviar", return_value={"ok": True, "falhas": [], "total": 1, "enviadas": ["F001-P0001-S01-D00001"]}) as send:
            res = fila.executar_pendentes()
        self.assertEqual(len(res["enviadas"]), 1)
        c = self.con()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM fila_correcao_site").fetchone()[0], 0)
        c.close()
        send.assert_called_once()

    def test_sucesso_sem_folha_confirmada_nao_pode_quitar(self):
        with patch("app.alteracoes_site.enviar", return_value={"ok": True, "enviadas": [], "total": 0}):
            r = fila.executar_pendentes(limite=1)
        self.assertEqual(len(r["falhas"]), 1)
        c = self.con()
        row = c.execute("SELECT estado, tentativas FROM fila_correcao_site").fetchone()
        c.close()
        self.assertEqual((row["estado"], row["tentativas"]), ("pendente", 1))

    def test_erro_mantem_pendente_e_backoff(self):
        with patch("app.alteracoes_site.enviar", side_effect=RuntimeError("WP 500")):
            r = fila.executar_pendentes()
        self.assertEqual(len(r["falhas"]), 1)
        c = self.con()
        row = c.execute("SELECT estado, tentativas, ultimo_erro FROM fila_correcao_site").fetchone()
        c.close()
        self.assertEqual(row["estado"], "pendente")
        self.assertEqual(row["tentativas"], 1)
        self.assertIn("WP 500", row["ultimo_erro"])

    def test_lease_vencido_pode_ser_retomado(self):
        c = self.con()
        c.execute("UPDATE fila_correcao_site SET estado='executando', reservado_ate='2020-01-01'")
        c.commit()
        c.close()
        with patch("app.alteracoes_site.enviar", return_value={"ok": True, "enviadas": ["F001-P0001-S01-D00001"], "total": 1}):
            res = fila.executar_pendentes()
        self.assertEqual(len(res["enviadas"]), 1)

    def test_atualizacao_concorrente_nao_e_apagada(self):
        def mudou(*args):
            c = self.con()
            c.execute("UPDATE fila_correcao_site SET versao=versao+1, estado='pendente' WHERE item_codigo=?", (args[2][0],))
            c.commit()
            c.close()
            return {"ok": True, "enviadas": [args[2][0]], "total": 1}
        with patch("app.alteracoes_site.enviar", side_effect=mudou):
            fila.executar_pendentes(limite=1)
        c = self.con()
        self.assertEqual(c.execute("SELECT versao FROM fila_correcao_site").fetchone()[0], 2)
        c.close()

    def test_ux40_manual_roda_com_flag_desligada_e_so_uma_rodada_por_vez(self):
        self.patch_reenvio.stop()
        try:
            with patch.object(fila, "reenvio_ativo", return_value=False), \
                 patch("app.alteracoes_site.enviar", return_value={"ok": True, "enviadas": ["F001-P0001-S01-D00001"], "total": 1}) as send:
                self.assertEqual(fila.executar_pendentes(), {"desligado": True})      # automático: parado
                send.assert_not_called()
                fila._RODADA.acquire()
                try:
                    self.assertEqual(fila.executar_pendentes(forcar_manual=True), {"ocupado": True})
                finally:
                    fila._RODADA.release()
                send.assert_not_called()
                vistos = []
                r = fila.executar_pendentes(forcar_manual=True, ator="adm@camp.arq.br", ao_terminar_item=lambda *a: vistos.append(a))
                self.assertEqual(r["enviadas"], ["F001-P0001-S01-D00001"])
                self.assertEqual(send.call_args[0][1], "adm@camp.arq.br")
                self.assertEqual(vistos, [("F001-P0001-S01-D00001", True, None)])
        finally:
            self.patch_reenvio.start()


if __name__ == "__main__":
    unittest.main()
