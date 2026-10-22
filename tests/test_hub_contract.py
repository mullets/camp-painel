"""WP-AUD-13: contrato WordPress↔painel para gravar hub de arquiteto."""
import unittest
from app.wp import WP


class Resposta:
    def __init__(self, status=200, dados=None, texto=""):
        self.status_code = status
        self.dados = dados
        self.text = texto

    def json(self):
        return self.dados


class HTTPFalso:
    def __init__(self, r):
        self.r = r
        self.posts = []

    def post(self, url, json):
        self.posts.append((url, json))
        return self.r


def cliente(resposta):
    wp = object.__new__(WP)
    wp.h = HTTPFalso(resposta)
    return wp


class TesteContratoHub(unittest.TestCase):
    def test_sucesso_integral(self):
        wp = cliente(Resposta(dados={"ok": True, "page_id": 92, "gravados": ["_camp_bio"], "retry": []}))
        self.assertEqual(wp.gravar_hub(7, {"_camp_bio": "História"})["page_id"], 92)
        self.assertEqual(wp.h.posts, [("/wp-json/camp/v1/painel/hub/7", {"meta": {"_camp_bio": "História"}})])

    def test_sucesso_parcial_nao_pode_parecer_completo(self):
        wp = cliente(Resposta(dados={
            "ok": False, "parcial": True, "page_id": 92,
            "gravados": ["_camp_bio"], "retry": ["_camp_acervo_acesso"],
        }))
        with self.assertRaisesRegex(RuntimeError, "1 campo"):
            wp.gravar_hub(7, {"_camp_bio": "Nova", "_camp_acervo_acesso": "Digital"})

    def test_falha_sem_parcial(self):
        wp = cliente(Resposta(dados={"ok": False, "retry": []}))
        with self.assertRaisesRegex(RuntimeError, "Atualização incompleta"):
            wp.gravar_hub(7, {})

    def test_retorno_legado(self):
        wp = cliente(Resposta(dados={"page_id": 93, "gravados": ["_camp_bio"]}))
        self.assertEqual(wp.gravar_hub(7, {"_camp_bio": "Bio"})["page_id"], 93)

    def test_retorno_invalido(self):
        wp = cliente(Resposta(dados=["dados inesperados"]))
        with self.assertRaisesRegex(RuntimeError, "formato inválido"):
            wp.gravar_hub(7, {})

    def test_erro_http(self):
        wp = cliente(Resposta(status=503, dados={"code": "indisponivel"}, texto="Falha temporária"))
        with self.assertRaisesRegex(RuntimeError, "503"):
            wp.gravar_hub(7, {})


if __name__ == "__main__":
    unittest.main()
