"""WP-AUD-01: recuperar IDs já marcados, sem duplicar nem escrever em simular."""
import sys, sqlite3, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.recuperar_pedidos_site import recuperar

class R:
 def __init__(self,d):self.status_code=200;self.data=d
 def json(self):return self.data
class HTTP:
 def __init__(self,data):self.data=data
 def get(self,path,params):
  assert params.get('todas')==1
  pagina=params["pagina"];ini=(pagina-1)*200
  return R(self.data[ini:ini+200])
class WP:
 def __init__(self,data):self.h=HTTP(data)
class Tests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:')
  self.c.execute('CREATE TABLE pedido_site(site_id INTEGER PRIMARY KEY,tipo TEXT,codigo TEXT,criado_no_site TEXT,payload TEXT)')
 def tearDown(self):self.c.close()
 def test_simular_e_aplicar_idempotente(self):
  self.c.execute("INSERT INTO pedido_site VALUES (1,'consulta','F001','2026','{}')")
  site=[{"id":i,"tipo":"consulta","codigo":"F001","criado_em":"2026"} for i in range(1,226)]
  p=WP(site)
  a=recuperar(self.c,p,False)
  self.assertTrue(a['simulado'])
  self.assertTrue(a['varredura_completa'])
  self.assertEqual(a['faltantes_total'],224)
  self.assertEqual(self.c.execute('SELECT count(*) FROM pedido_site').fetchone()[0],1)
  b=recuperar(self.c,p,True)
  self.assertEqual(b["inseridos"],224)
  self.assertEqual(self.c.execute('SELECT count(*) FROM pedido_site').fetchone()[0],225)
  c=recuperar(self.c,p,True)
  self.assertEqual(c["inseridos"],0)
  self.assertEqual(c["faltantes_total"],0)

if __name__=="__main__": unittest.main()
