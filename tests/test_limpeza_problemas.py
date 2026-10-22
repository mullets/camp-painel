"""REF-041: limpeza conservadora de avisos automáticos sem apagar bloqueios."""
import sqlite3
import unittest
from app import problemas


class ProblemasAutomaticosTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE projeto(codigo TEXT PRIMARY KEY,titulo TEXT,fundo_codigo TEXT,
                               mesclado_em TEXT,descartado_em TEXT,status_site TEXT);
          CREATE TABLE fundo(codigo TEXT PRIMARY KEY,titulo TEXT);
          CREATE TABLE cv_resposta(projeto_codigo TEXT,chave TEXT,por TEXT,em TEXT,
                                  motivo TEXT,lote_id INT,tipo TEXT,acao TEXT);
          CREATE TABLE lista_processamento(id INTEGER PRIMARY KEY, projeto_codigo TEXT,
                                          resultado TEXT, descartado_em TEXT);
          CREATE TABLE item(codigo TEXT PRIMARY KEY,projeto_codigo TEXT,duplicata_de TEXT,
                            codigo_anterior TEXT,giro_manual INT,espelho_manual INT,
                            lote_id INT,revisao TEXT,revisado_em TEXT);
          CREATE TABLE erro(id INTEGER PRIMARY KEY, gravidade TEXT,categoria TEXT,origem TEXT,
                            codigo TEXT,descricao TEXT,relatado_por TEXT,chave TEXT,
                            criado_em TEXT,situacao TEXT DEFAULT 'aberto',resolvido_em TEXT,
                            resolucao TEXT);
          CREATE TABLE evento(id INTEGER PRIMARY KEY, entidade TEXT,codigo TEXT,tipo TEXT,
                              ator TEXT,detalhe TEXT,quando TEXT DEFAULT (datetime('now')));
          INSERT INTO fundo VALUES ('F026','Sami Bussab');
          INSERT INTO projeto VALUES ('F026-P0004','Escola','F026',NULL,NULL,'no_ar');
          INSERT INTO item VALUES ('F026-P0004-S01-D00001','F026-P0004',NULL,NULL,0,NULL,
                                   37,'conferida','2026-10-22 16:10:20');
          INSERT INTO erro(id,gravidade,categoria,origem,codigo,descricao,chave,criado_em)
          VALUES (1,'aviso','metadado','campvision','F026-P0004',
                  'IPTC:By-line exceeds length limit (truncated)',
                  'campvision:aviso-menor:hash','2026-10-22 16:10:00');
          INSERT INTO erro(id,gravidade,categoria,origem,codigo,descricao,chave,criado_em)
          VALUES (2,'corrigir','orientacao','campvision','F026-P0004-S01-D00001',
                  'orientacao incerta','campvision:erros:hash2','2026-10-22 16:00:00');
          INSERT INTO erro(id,gravidade,categoria,origem,codigo,descricao,chave,criado_em)
          VALUES (3,'bloqueia','arquivo_corrompido','campvision','F026-P0004-S01-D00001',
                  'TIF corrompido','campvision:erros:hash3','2026-10-22 16:00:00');
          INSERT INTO erro(id,gravidade,categoria,origem,codigo,descricao,chave,criado_em)
          VALUES (4,'corrigir','duplicata','campvision','F026-P0004-S01-D00001',
                  'possível duplicata','campvision:erros:hash4','2026-10-22 16:00:00');
        """)

    def tearDown(self):
        self.db.close()

    def test_so_informativos_e_alerta_conferido_fecham(self):
        ids = problemas.fechar_resolvidos(self.db)
        self.assertEqual(set(ids), {1, 2})
        statuses = dict(self.db.execute("SELECT id,situacao FROM erro"))
        self.assertEqual(statuses[3], "aberto")
        self.assertEqual(statuses[4], "aberto")
        self.assertEqual(statuses[1], "corrigido")
        self.assertEqual(statuses[2], "corrigido")

    def test_nao_repete_evento_e_mantem_proveniencia(self):
        problemas.fechar_resolvidos(self.db)
        self.assertEqual(problemas.fechar_resolvidos(self.db), [])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM evento WHERE tipo='fechado_automatico'").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM erro").fetchone()[0], 4)

if __name__ == "__main__":
    unittest.main()
