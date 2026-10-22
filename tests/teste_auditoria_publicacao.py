"""WP-AUD-05 — divergências são detectadas sem alterar os snapshots."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.auditoria_publicacao import diagnosticar

class AuditTest(unittest.TestCase):
 def test_site_missing_status_and_orphan(self):
  painel=[
   {"codigo":"F001-P0001","tainacan_item_id":10,"status_site":"no_ar","tipo":"projeto"},
   {"codigo":"F001-P0002","tainacan_item_id":20,"status_site":"rascunho","tipo":"projeto"},
   {"codigo":"F001-P0003","tainacan_item_id":30,"status_site":"no_ar","tipo":"projeto"}]
  site=[{"id":10,"status":"publish","tipo":"projeto"},
        {"id":20,"status":"private","tipo":"projeto"},
        {"id":40,"status":"publish","tipo":"projeto"}]
  x=diagnosticar(painel,site)
  self.assertEqual(x["corretos"],1)
  self.assertEqual(x["faltando_no_site"][0]["codigo"],"F001-P0003")
  self.assertEqual(x["status_divergente"][0]["codigo"],"F001-P0002")
  self.assertEqual(x["publicos_sem_vinculo_no_painel"][0]["id"],40)
  self.assertTrue(x["somente_leitura"])

if __name__=="__main__":
 unittest.main()
