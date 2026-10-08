#!/usr/bin/env python3
"""Testes de backend sem navegador: migrações (banco novo e banco antigo de produção) e guarda de rede.
Uso:  python tests/teste_backend.py        (sai com código 1 se algo falhar)"""
import os, subprocess, sys, tempfile, sqlite3, pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable
falhas = []

def ok(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond: falhas.append(msg)

def rodar(modo, db):
    env = dict(os.environ, CAMP_DB_PATH=db, CAMP_COOKIE_SECURE="false", PYTHONPATH=str(RAIZ / "backend"), CAMP_LOG_DIR=str(pathlib.Path(db).parent / "logs"), CAMP_BACKUP_DIR=str(pathlib.Path(db).parent / "backups"))
    r = subprocess.run([PY, __file__, "--filho", modo], env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def filho(modo):
    from app.db import init_db, aplicar_migracoes, connect
    if modo == "novo":
        init_db(); aplicar_migracoes(); aplicar_migracoes()   # 2x: idempotente
    elif modo == "antigo":
        aplicar_migracoes()
    elif modo == "rede":
        init_db(); aplicar_migracoes()
        from fastapi import HTTPException, Request
        from app.rede import exigir_estacao
        def req(ip, h=None):
            return Request({"type": "http", "client": (ip, 1), "method": "GET", "path": "/",
                            "headers": [(k.lower().encode(), v.encode()) for k, v in (h or {}).items()]})
        def tenta(ip, h=None):
            try: exigir_estacao(req(ip, h)); return 200
            except HTTPException as e: return e.status_code
        c = connect()
        casos = [
          ("LAN 192.168 sem token (legado)", tenta("192.168.15.43"), 200),
          ("LAN 10.x sem token", tenta("10.1.2.3"), 200),
          ("localhost sem proxy", tenta("127.0.0.1"), 200),
          ("IP público", tenta("8.8.8.8"), 403),
          ("TÚNEL: 127.0.0.1 + CF-Connecting-IP", tenta("127.0.0.1", {"CF-Connecting-IP": "8.8.8.8"}), 403),
          ("TÚNEL: 127.0.0.1 + X-Forwarded-For", tenta("127.0.0.1", {"X-Forwarded-For": "8.8.8.8"}), 403),
          ("LAN + cabeçalho de proxy sem token", tenta("192.168.15.43", {"X-Forwarded-For": "1.1.1.1"}), 403),
        ]
        c.execute("UPDATE configuracao SET valor='segredo-de-teste' WHERE chave='estacao.token'"); c.commit()
        casos += [
          ("token ligado: LAN sem cabeçalho", tenta("192.168.15.43"), 401),
          ("token ligado: token errado", tenta("192.168.15.43", {"X-Camp-Token": "errado"}), 401),
          ("token ligado: token certo na LAN", tenta("192.168.15.43", {"X-Camp-Token": "segredo-de-teste"}), 200),
          ("token ligado: token certo via túnel", tenta("127.0.0.1", {"X-Camp-Token": "segredo-de-teste", "CF-Connecting-IP": "8.8.8.8"}), 200),
        ]
        for nome, got, esp in casos:
            print(f"{'ok' if got == esp else 'FALHA'}|{nome}|esperado {esp} obtido {got}")
        import json as _j2
        from app.log_tecnico import LOG_FILE
        linhas = [_j2.loads(l) for l in open(LOG_FILE, encoding="utf-8")] if LOG_FILE.exists() else []
        neg = [l for l in linhas if l.get("evento") == "estacao_negada"]
        motivos = {l["motivo"] for l in neg}
        print(f"{'ok' if {'fora_da_lan', 'via_proxy_sem_token', 'token_ausente_ou_invalido'} <= motivos else 'FALHA'}|recusa registra o MOTIVO no log técnico|{sorted(motivos)}")
        print(f"{'ok' if all('segredo-de-teste' not in _j2.dumps(l) and 'errado' not in _j2.dumps(l) for l in neg) else 'FALHA'}|o log nunca grava o token enviado|")
        proxy = [l for l in neg if l["motivo"] == "via_proxy_sem_token"]
        print(f"{'ok' if proxy and 'cf-connecting-ip' in proxy[0]['cabecalhos_proxy'] or proxy and 'x-forwarded-for' in proxy[0]['cabecalhos_proxy'] else 'FALHA'}|log diz quais cabeçalhos de proxy vieram|{proxy[0]['cabecalhos_proxy'] if proxy else ''}")
    elif modo == "lock":
        import threading, time
        init_db(); aplicar_migracoes()
        from app import auth
        auth.criar_usuario("R", "r@camp.arq.br", "senha-bem-longa-123", "master", forcar_troca=False)
        from fastapi.testclient import TestClient
        from app.main import app
        cl = TestClient(app, raise_server_exceptions=False)
        def sync_longo():   # imita a sincronização: escrita longa segurando o lock
            c = sqlite3.connect(os.environ["CAMP_DB_PATH"], timeout=30); c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('x','x','x','sync')"); time.sleep(8); c.commit(); c.close()
        t = threading.Thread(target=sync_longo); t.start(); time.sleep(1)
        t0 = time.time(); r = cl.post("/api/auth/login", json={"email": "r@camp.arq.br", "senha": "senha-bem-longa-123"}); t.join()
        print(f"{'ok' if r.status_code == 200 else 'FALHA'}|login durante escrita longa do sincronizador|HTTP {r.status_code} em {time.time()-t0:.1f}s")
    elif modo == "edicao":
        init_db(); aplicar_migracoes()
        import json as _j
        from app import auth
        from fastapi.testclient import TestClient
        import app.publicador as pub
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo) VALUES ('F099','Fundo de teste')"); c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',1)")
        c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES ('F099-P0001','F099',1,'Casa de teste',1970)")
        for n in (1, 2):
            c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem) VALUES (?,?,?,?,?,?,?,'importado')",
                      (f"F099-P0001-1970-S01-D0000{n}", "F099-P0001", "S01", n, f"Planta {n}", "Planta", f"0{n}/02"))
        MT = "Tainacan\\Metadata_Types\\"
        for mid, nome, tipo, tax in ((501, "Técnica", "Text", None), (502, "Tipo de desenho", "Taxonomy", 77), (503, "Endereço", "Textarea", None), (504, "Data do registro fotográfico", "Date", None)):
            c.execute("INSERT INTO wp_metadado (id,colecao_id,nome,tipo,taxonomia_id) VALUES (?,?,?,?,?)", (mid, 8013, nome, MT + tipo, tax))
        c.execute("INSERT INTO wp_taxonomia (id,nome) VALUES (77,'Tipos de desenho')")
        c.execute("INSERT INTO wp_termo (id,taxonomia_id,nome) VALUES (9001,77,'Planta'),(9002,77,'Corte')")
        c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,fundo_detectado,projeto_detectado,metadados,json) VALUES (7001,8013,'draft','Planta 1 — P0001','F099-P0001-1970-S01-D00001','F099','F099-P0001',?,?)",
                  (_j.dumps({"Técnica": "nanquim", "Tipo de desenho": "Planta", "Data do registro fotográfico": "1972"}), _j.dumps({"description": "Descrição antiga"})))
        c.commit(); c.close()
        auth.criar_usuario("Op", "op@camp.arq.br", "senha-operador-123", "operador", forcar_troca=False)
        auth.criar_usuario("Leitor", "leitor@camp.arq.br", "senha-leitor-1234", "leitura", forcar_troca=False)
        def cli(email, senha):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": email, "senha": senha}); return x
        op, le = cli("op@camp.arq.br", "senha-operador-123"), cli("leitor@camp.arq.br", "senha-leitor-1234")
        I1, I2 = "F099-P0001-1970-S01-D00001", "F099-P0001-1970-S01-D00002"
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        class Fake:
            chamadas, falhar = [], set()
            def patch_item(self, cid, wid, **campos): Fake.chamadas.append(("patch", cid, wid, campos))
            def definir_metadado(self, wid, mid, valor):
                if mid in Fake.falhar: raise RuntimeError("Tainacan recusou (500)")
                Fake.chamadas.append(("meta", wid, mid, valor))
        pub.WP = Fake
        # permissões
        ver("leitura NÃO abre a edição (403)", le.get(f"/api/itens/{I1}/edicao").status_code == 403)
        ver("leitura NÃO edita (403)", le.patch(f"/api/itens/{I1}", json={"titulo": "x"}).status_code == 403)
        r = op.get(f"/api/itens/{I1}/edicao"); d = r.json()
        ver("operador abre a edição", r.status_code == 200 and d["no_site"], f"HTTP {r.status_code}")
        nomes = [x["nome"] for x in d["site"]["campos"]]
        ver("só oferece campos que existem na coleção", nomes == ["Tipo de desenho", "Técnica", "Endereço"] or sorted(nomes) == sorted(["Técnica", "Tipo de desenho", "Endereço"]), str(nomes))
        ver("campo Data (tipo não suportado) vira somente leitura", [x["nome"] for x in d["site"]["somente_leitura"]] == ["Data do registro fotográfico"])
        ver("taxonomia traz as opções existentes", next(x for x in d["site"]["campos"] if x["nome"] == "Tipo de desenho")["opcoes"] == ["Corte", "Planta"])
        ver("descrição atual vem do site", d["site"]["descricao"] == "Descrição antiga")
        d2 = op.get(f"/api/itens/{I2}/edicao").json(); ver("folha sem item no site: edição só local", d2["no_site"] is False and d2["site"] is None)
        # validação: nada é gravado se algo é inválido
        r = op.patch(f"/api/itens/{I1}", json={"titulo": "NÃO PODE GRAVAR", "metadados_site": {"Tipo de desenho": "Inexistente"}})
        ver("termo inexistente na taxonomia -> 400", r.status_code == 400, r.json().get("detail", "")[:60])
        ver("validação é tudo-ou-nada (título não gravou)", op.get(f"/api/itens/{I1}").json()["item"]["titulo"] == "Planta 1")
        for nome, corpo in (("tipo de documento fora do vocabulário", {"tipo_documento": "Pizza"}), ("ano 1700", {"ano_folha": 1700}),
                            ("campo não permitido", {"metadados_site": {"Fundo": "x"}}), ("título do site vazio", {"titulo_site": "  "}),
                            ("texto gigante", {"titulo": "x" * 400})):
            ver(f"recusa: {nome}", op.patch(f"/api/itens/{I1}", json=corpo).status_code == 400)
        ver("folha sem site + campo do site -> 400", op.patch(f"/api/itens/{I2}", json={"titulo_site": "x"}).status_code == 400)
        ver("folha inexistente -> 404", op.patch("/api/itens/F099-P0001-1970-S01-D99999", json={"titulo": "x"}).status_code == 404)
        # edição local
        Fake.chamadas.clear()
        r = op.patch(f"/api/itens/{I2}", json={"titulo": "  Planta baixa térrea  ", "folha": "02/02", "escala": "1:50", "ano_folha": 1971, "suporte": "papel vegetal"}); j = r.json()
        ver("edição local salva", r.status_code == 200 and sorted(j["campos"]) == ["ano_folha", "escala", "suporte", "titulo"], str(j)[:90])  # folha já era 02/02: igual não conta
        it = op.get(f"/api/itens/{I2}").json()["item"]
        ver("valores gravados (com trim)", it["titulo"] == "Planta baixa térrea" and it["escala"] == "1:50" and it["ano_folha"] == 1971)
        ver("edição local NÃO chama o site", Fake.chamadas == [] and j["site"] is None)
        ev = connect().execute("SELECT detalhe FROM evento WHERE entidade='item' AND codigo=? AND tipo='editado'", (I2,)).fetchone()
        dj = _j.loads(ev[0]); ver("auditoria com antes/depois", dj["antes"]["titulo"] == "Planta 2" and dj["depois"]["titulo"] == "Planta baixa térrea")
        r = op.patch(f"/api/itens/{I2}", json={"titulo": "Planta baixa térrea", "escala": "1:50"}); ver("nada mudou -> campos vazios", r.json()["campos"] == [])
        r = op.patch(f"/api/itens/{I2}", json={"escala": ""}); ver("texto vazio limpa o campo", op.get(f"/api/itens/{I2}").json()["item"]["escala"] is None)
        # envio ao site
        Fake.chamadas.clear()
        r = op.patch(f"/api/itens/{I1}", json={"titulo_site": "Planta térrea — P0001", "descricao_site": "Nova descrição", "metadados_site": {"Técnica": "grafite", "Tipo de desenho": "corte"}}); j = r.json()
        ver("envio ao site OK", r.status_code == 200 and j["site"]["falhas"] == [] and len(j["site"]["enviados"]) == 4, str(j["site"]))
        ver("título e descrição vão num único PATCH", ("patch", 8013, 7001, {"title": "Planta térrea — P0001", "description": "Nova descrição"}) in Fake.chamadas)
        ver("texto vai no metadado certo (501)", ("meta", 7001, 501, "grafite") in Fake.chamadas)
        ver("taxonomia vai como ID do termo (9002), não como nome", ("meta", 7001, 502, 9002) in Fake.chamadas)
        w = connect().execute("SELECT titulo, metadados, json FROM wp_item WHERE id=7001").fetchone()
        ver("espelho local atualizado sem esperar a sincronização", w["titulo"] == "Planta térrea — P0001" and _j.loads(w["metadados"])["Técnica"] == "grafite" and _j.loads(w["metadados"])["Tipo de desenho"] == "Corte" and _j.loads(w["json"])["description"] == "Nova descrição")
        # falha parcial
        Fake.chamadas.clear(); Fake.falhar = {501}
        r = op.patch(f"/api/itens/{I1}", json={"titulo": "Título local novo", "metadados_site": {"Técnica": "tinta", "Endereço": "Rua X, 10"}}); j = r.json()
        ver("falha de 1 campo não derruba o outro", [f["campo"] for f in j["site"]["falhas"]] == ["Técnica"] and "Endereço" in j["site"]["enviados"], str(j["site"])[:120])
        ver("o salvamento local sobrevive à falha do site", op.get(f"/api/itens/{I1}").json()["item"]["titulo"] == "Título local novo")
        ver("pendência registrada para revisão", connect().execute("SELECT count(*) FROM divergencia_site WHERE campo='pendente_Técnica_no_site'").fetchone()[0] == 1)
        ver("espelho NÃO muda para o campo que falhou", _j.loads(connect().execute("SELECT metadados FROM wp_item WHERE id=7001").fetchone()[0])["Técnica"] == "grafite")
        # site sem credencial
        Fake.falhar = set()
        def sem_wp(): raise RuntimeError("Application Password não configurada")
        pub.WP = sem_wp
        r = op.patch(f"/api/itens/{I1}", json={"descricao_site": "Outra"}); j = r.json()
        ver("sem credencial do WordPress: 200, salvo, aviso por campo", r.status_code == 200 and j["site"]["falhas"][0]["campo"] == "descrição", str(j["site"])[:100])
        for l in res: print(l)
    elif modo == "imagens":
        init_db(); aplicar_migracoes()
        import json as _j
        from app.imagens import thumb_do_item, documento_do_item, radical, e_imagem, resolver_anexos
        from app.sincronizador import _divergencia
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        # --- funções puras ---
        gen = {"thumbnail": {"large": ["https://camp.arq.br/wp-content/plugins/tainacan/assets/images/placeholder_square.png", 1, 1, False]}}
        ver("miniatura genérica do plugin é descartada", thumb_do_item(gen) == "")
        ver("thumbnail com valores false não quebra", thumb_do_item({"thumbnail": {"large": False, "full": False}}) == "" and thumb_do_item({}) == "")
        ver("miniatura real é aceita", thumb_do_item({"thumbnail": {"medium": ["https://s/up/a-300x200.jpg", 300, 200, True]}}) == "https://s/up/a-300x200.jpg")
        ver("documento: anexo vem como ID, nunca como URL", documento_do_item({"document_type": "attachment", "document": "321"}) == (None, 321))
        ver("documento: URL no src do HTML é usada como reserva", documento_do_item({"document_type": "attachment", "document": "321", "document_as_html": '<div><img src="https://s/up/a.jpg"></div>'}) == ("https://s/up/a.jpg", 321))
        ver("documento: tipo url", documento_do_item({"document_type": "url", "document": "https://s/y.png"}) == ("https://s/y.png", None))
        ver("documento: vazio", documento_do_item({"document_type": "empty", "document": ""}) == (None, None))
        ver("radical ignora -1024x768 e -scaled", radical("https://s/up/a-1024x768.jpg") == radical("https://s/up/a-scaled.jpg") == radical("https://s/up/a.JPG") == "a")
        ver("radical distingue arquivos diferentes", radical("https://s/up/a.jpg") != radical("https://s/up/b-300x200.jpg"))
        ver("TIFF/PDF não são imagem de navegador", not e_imagem("https://s/a.tif") and not e_imagem(None, "application/pdf") and e_imagem("https://s/a.jpg"))
        # --- passo da sincronização ---
        c = connect()
        def linha(i, cod, thumb, doc, mime_ok=True):
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,thumb_url,json) VALUES (?,8013,'draft','t',?,?,?)", (i, cod, thumb, _j.dumps(doc)))
        A = lambda n: {"document_type": "attachment", "document": str(n)}
        linha(1, "C1", "https://s/up/a-1024x768.jpg", A(11))                                  # miniatura certa
        linha(2, "C2", "", A(12))                                                           # sem miniatura, documento JPG
        linha(3, "C3", "https://s/up/zzz-300x200.jpg", A(13))                               # miniatura de OUTRO arquivo
        linha(4, "C4", "", A(14))                                                           # documento TIFF
        linha(5, "C5", "", {"document_type": "url", "document": "https://s/y.png"})        # url direta
        linha(6, "C6", "", {"document_type": "empty", "document": ""})                      # nada
        linha(7, "C7", "", {**A(99), "document_as_html": '<img src="https://s/up/h.jpg">'})  # anexo que a API não devolve
        c.commit()
        class Fake:
            def anexos(self, ids):
                return {11: {"url": "https://s/up/a.jpg", "mime": "image/jpeg", "large": None, "medium": None},
                        12: {"url": "https://s/up/b.jpg", "mime": "image/jpeg", "large": "https://s/up/b-1024x768.jpg", "medium": None},
                        13: {"url": "https://s/up/outro.jpg", "mime": "image/jpeg", "large": None, "medium": None},
                        14: {"url": "https://s/up/c.tif", "mime": "image/tiff", "large": None, "medium": None}}
        r = resolver_anexos(c, Fake(), 8013, _divergencia, log=lambda *a: None)
        L = {x["codigo_detectado"]: x for x in c.execute("SELECT * FROM wp_item")}
        ver("miniatura certa fica e é marcada 'miniatura'", L["C1"]["imagem_origem"] == "miniatura" and L["C1"]["documento_url"] == "https://s/up/a.jpg")
        ver("sem miniatura: usa o próprio documento (versão large)", L["C2"]["thumb_url"] == "https://s/up/b-1024x768.jpg" and L["C2"]["imagem_origem"] == "documento")
        ver("documento TIFF não vira imagem (sem imagem, sem inventar)", L["C4"]["thumb_url"] is None and L["C4"]["imagem_origem"] == "" and L["C4"]["documento_url"] == "https://s/up/c.tif")
        ver("url direta vira imagem", L["C5"]["thumb_url"] == "https://s/y.png" and L["C5"]["imagem_origem"] == "documento")
        ver("item sem documento: sem imagem", L["C6"]["thumb_url"] is None and L["C6"]["imagem_origem"] == "")
        ver("anexo ausente na API: usa o src do HTML", L["C7"]["thumb_url"] == "https://s/up/h.jpg" and L["C7"]["imagem_origem"] == "documento")
        dv = c.execute("SELECT codigo, valor_painel, valor_site FROM divergencia_site WHERE campo='miniatura_diferente_do_documento'").fetchall()
        ver("miniatura de outro arquivo vira divergência", len(dv) == 1 and dv[0][0] == "C3" and dv[0][1] == "outro" and dv[0][2] == "zzz", str([tuple(x) for x in dv]))
        ver("contagens", (r["com_miniatura"], r["via_documento"], r["sem_imagem"], r["divergentes"]) == (2, 3, 2, 1), str(r))
        # API fora do ar: não derruba a sincronização
        c.execute("UPDATE wp_item SET thumb_url=NULL, documento_url=NULL, imagem_origem=NULL"); c.commit()
        class Quebrado:
            def anexos(self, ids): raise RuntimeError("WordPress fora do ar")
        r = resolver_anexos(c, Quebrado(), 8013, _divergencia, log=lambda *a: None)
        L = {x["codigo_detectado"]: x for x in c.execute("SELECT * FROM wp_item")}
        ver("anexos indisponíveis: não quebra e usa o que o item já trazia", L["C7"]["imagem_origem"] == "documento" and L["C5"]["imagem_origem"] == "documento" and L["C2"]["imagem_origem"] == "", str(r))
        for l in res: print(l)
    elif modo == "importador":
        init_db(); aplicar_migracoes()
        import json as _j
        from app.importador_site import executar as importar
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo) VALUES ('F099','Fundo de teste')"); c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',1)")
        c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES ('F099-P0001','F099',1,'Casa de teste',1970)")
        for n, jpg in ((3, "16204"), (4, "/mnt/qnap/acervos/D00004.jpg"), (5, "https://velho/x5.jpg")):
            c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,arquivo_jpg,origem) VALUES (?,?,?,?,?,'importado')",
                      (f"F099-P0001-1970-S01-D0000{n}", "F099-P0001", "S01", n, jpg))
        docs = {1: "https://camp.arq.br/u/x1.jpg", 2: "16200", 3: "https://camp.arq.br/u/x3.jpg", 4: "https://camp.arq.br/u/x4.jpg", 5: "https://camp.arq.br/u/x5.jpg"}
        for n, doc in docs.items():
            cod = f"F099-P0001-1970-S01-D0000{n}"
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,documento_url,codigo_detectado,metadados) VALUES (?,8013,'private',?,?,?,?,?)",
                      (8000 + n, f"Folha {n}", f"folha-{n}", doc, cod, _j.dumps({"Código do documento": cod})))
        c.commit(); c.close()
        r = importar(log=lambda *a, **k: None)
        c = connect(); jpg = {r_[0][-1]: r_[1] for r_ in c.execute("SELECT codigo, arquivo_jpg FROM item")}
        def ver(nome, cond, det=""): print(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        ver("item novo recebe a URL real do documento", jpg.get("1") == "https://camp.arq.br/u/x1.jpg", str(jpg.get("1")))
        ver("item novo com ID de anexo NÃO grava o ID", jpg.get("2") is None, str(jpg.get("2")))
        ver("item existente com ID de anexo é corrigido para a URL", jpg.get("3") == "https://camp.arq.br/u/x3.jpg", str(jpg.get("3")))
        ver("caminho local existente é preservado", jpg.get("4") == "/mnt/qnap/acervos/D00004.jpg", str(jpg.get("4")))
        ver("URL existente é preservada", jpg.get("5") == "https://velho/x5.jpg", str(jpg.get("5")))
        ver("importador criou 2 e atualizou 3", r["itens_novos"] == 2 and r["itens_atualizados"] == 3, str({k: r[k] for k in ("itens_novos", "itens_atualizados")}))
    elif modo == "sync":
        init_db(); aplicar_migracoes()
        import json as _j, sqlite3 as _s, time as _t
        import app.sincronizador as sz
        from app.imagens import resolver_anexos  # noqa: F401
        db = os.environ["CAMP_DB_PATH"]
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        # ---- espelho ANTERIOR (rodada de ontem) ----
        c.execute("INSERT INTO wp_colecao (id,nome) VALUES (8007,'Projetos'),(8013,'Acervo')")
        c.execute("INSERT INTO wp_taxonomia (id,nome) VALUES (77,'Fundos'),(78,'Velha')")
        c.execute("INSERT INTO wp_termo (id,taxonomia_id,nome) VALUES (1,77,'Fundo teste'),(2,77,'Termo que sumiu'),(3,78,'Outro')")
        old = "2020-01-01 00:00:00"
        c.execute("UPDATE wp_colecao SET visto_em=?", (old,)); c.execute("UPDATE wp_taxonomia SET visto_em=?", (old,)); c.execute("UPDATE wp_termo SET visto_em=?", (old,))
        for i in (1, 2):
            cod = f"F099-P0001-1970-S01-D0000{i}"
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,fundo_detectado,projeto_detectado,thumb_url,documento_url,imagem_origem,visto_em) VALUES (?,8013,'publish',?,?,'F099','F099-P0001','https://velho/x.jpg','https://velho/x.jpg','documento',?)",
                      (i, f"Antigo {i}", cod, old))
        c.execute("INSERT INTO wp_metadado (id,colecao_id,nome,tipo,visto_em) VALUES (501,8013,'Técnica','Text',?)", (old,))
        # divergências: da sincronização (somem), pendência de escrita (fica) e uma já resolvida (fica)
        c.execute("INSERT INTO divergencia_site (entidade,codigo,campo,resolvida) VALUES ('item','X','sem_codigo',0),('item','D00001','pendente_Técnica_no_site',0),('item','Y','sem_codigo',1)")
        c.commit(); c.close()
        def mirror():
            k = _s.connect(db, timeout=5)
            r = {t: {x[0] for x in k.execute(f"SELECT id FROM {t}")} for t in ("wp_item", "wp_termo", "wp_taxonomia", "wp_colecao", "wp_metadado")}
            k.close(); return r
        def contem(depois, antes_):   # nada do que havia pode ter sumido (pode ter entrado coisa nova)
            return all(antes_[t] <= depois[t] for t in antes_)
        antes = mirror()
        def item(i, cod, titulo, anexo=None):
            return {"id": i, "title": titulo, "slug": titulo.lower().replace(" ", "-"), "url": f"https://fake/{i}/", "status": "publish", "modification_date": "2026-10-05",
                    "document_type": "attachment", "document": str(anexo or i), "document_mimetype": "image/jpeg", "thumbnail": {},
                    "metadata": {"1": {"name": "Código do documento", "value_as_string": cod}}}
        sonda = {"durante": [], "escrita_ms": []}
        class Fake:
            falha_na_2a = False
            def __init__(self, log=print): self.base = "https://fake"
            def quem_sou(self): return {"name": "teste", "roles": ["administrator"]}
            def taxonomias(self): return [{"id": 77, "name": "Fundos", "slug": "fundos"}]
            def termos(self, tid): return [{"id": 1, "name": "Fundo teste", "slug": "fundo-teste"}, {"id": 9, "name": "Termo novo", "slug": "termo-novo"}]
            def colecoes(self): return [{"id": 8007, "name": "Projetos", "slug": "p", "url": "u"}, {"id": 8013, "name": "Acervo", "slug": "a", "url": "u"}]
            def metadados_da_colecao(self, cid): return [{"id": 501, "name": "Técnica", "metadata_type": "Tainacan\\Metadata_Types\\Text", "metadata_type_options": {}}] if cid == 8013 else []
            def itens(self, cid):
                if cid == 8007:
                    yield {"id": 100, "title": "P0001 — Casa", "slug": "p0001-casa", "url": "u", "status": "publish", "metadata": {"1": {"name": "Código de Catalogação", "value_as_string": "F099-P0001"}}}
                    return
                yield item(1, "F099-P0001-1970-S01-D00001", "Planta atualizada")
                # ---- no MEIO da rede: o painel precisa continuar enxergando o espelho ANTIGO inteiro ----
                sonda["durante"].append(mirror())
                k = _s.connect(db, timeout=2); t0 = _t.time()
                try:
                    k.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('x','x','x','login')"); k.commit()
                    sonda["escrita_ms"].append(int((_t.time() - t0) * 1000))
                except _s.OperationalError:   # o painel ficaria travado (é o que o código antigo fazia)
                    sonda["escrita_ms"].append(99999)
                k.close()
                if Fake.falha_na_2a: raise RuntimeError("WordPress caiu no meio")
                yield item(3, "F099-P0001-1970-S01-D00003", "Planta nova")
                yield {"id": 4, "title": "Sem código nenhum", "slug": "sem-codigo", "url": "u", "status": "draft", "metadata": {}}
            def anexos(self, ids): return {i: {"url": f"https://fake/up/{i}.jpg", "mime": "image/jpeg", "large": f"https://fake/up/{i}-1024x768.jpg", "medium": None} for i in ids}
            def paginas(self): return []
        sz.WP = Fake
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        # ===== rodada que FALHA no meio: nada do espelho antigo pode ser perdido =====
        Fake.falha_na_2a = True
        r = sz.executar(True, lambda *a, **k: None)
        ver("rodada com falha devolve ok=False", r["ok"] is False, str(r)[:80])
        ver("falha no meio: NADA do espelho anterior foi apagado", contem(mirror(), antes), str({t: sorted(antes[t] - mirror()[t]) for t in antes}))
        k = connect(); ver("falha registrada na tabela de sincronizações", k.execute("SELECT ok FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()[0] == 0)
        ver("falha: divergências antigas intactas", k.execute("SELECT count(*) FROM divergencia_site WHERE resolvida=0").fetchone()[0] == 2); k.close()
        # ===== rodada completa =====
        Fake.falha_na_2a = False; sonda["durante"].clear()
        r = sz.executar(True, lambda *a, **k: None)
        ver("rodada completa ok=True", r["ok"] is True, str(r)[:100])
        ver("DURANTE a rede o espelho nunca ficou vazio/parcial (tudo o que havia continuava lá)", bool(sonda["durante"]) and all(contem(m, antes) for m in sonda["durante"]), str({t: sorted(antes[t] - sonda["durante"][0][t]) for t in antes}))
        ver("DURANTE a rede o painel consegue GRAVAR (nenhum lock longo)", max(sonda["escrita_ms"]) < 500, f"{sonda['escrita_ms']} ms")
        k = connect()
        ids = {x[0] for x in k.execute("SELECT id FROM wp_item WHERE colecao_id=8013")}
        ver("item que o site tem continua e foi atualizado", 1 in ids and k.execute("SELECT titulo FROM wp_item WHERE id=1").fetchone()[0] == "Planta atualizada")
        ver("item novo do site entrou", 3 in ids and 4 in ids)
        ver("item que sumiu do site saiu do espelho", 2 not in ids)
        ver("termo que sumiu saiu; termo novo entrou", {x[0] for x in k.execute("SELECT id FROM wp_termo")} == {1, 9})
        ver("taxonomia que sumiu saiu", {x[0] for x in k.execute("SELECT id FROM wp_taxonomia")} == {77})
        ver("imagem resolvida pelo anexo, na mesma gravação", k.execute("SELECT documento_url, thumb_url, imagem_origem FROM wp_item WHERE id=3").fetchone()[:] == ("https://fake/up/3.jpg", "https://fake/up/3-1024x768.jpg", "documento"), str(tuple(k.execute("SELECT documento_url, thumb_url, imagem_origem FROM wp_item WHERE id=3").fetchone())))
        ver("item sem imagem do site fica sem imagem (nunca herda a do antigo)", k.execute("SELECT imagem_origem FROM wp_item WHERE id=4").fetchone()[0] in ("", None))
        dv = {(x["codigo"], x["campo"], x["resolvida"]) for x in k.execute("SELECT codigo,campo,resolvida FROM divergencia_site")}
        ver("divergência antiga da sincronização foi substituída", ("X", "sem_codigo", 0) not in dv)
        ver("PENDÊNCIA de escrita no site é preservada", ("D00001", "pendente_Técnica_no_site", 0) in dv)
        ver("divergência já resolvida é preservada", ("Y", "sem_codigo", 1) in dv)
        ver("divergência nova (item sem código) foi registrada", ("4", "sem_codigo", 0) in dv)
        ver("metadados da coleção atualizados", k.execute("SELECT count(*) FROM wp_metadado WHERE visto_em > '2021'").fetchone()[0] == 1)
        ver("contagem do projeto reconciliada com o dossiê do site", k.execute("SELECT count(*) FROM wp_item WHERE colecao_id=8007").fetchone()[0] == 1)
        k.close()
        for l in res: print(l)
    elif modo == "backup":
        init_db(); aplicar_migracoes()
        import gzip as _gz, json as _j, threading, time as _t, tempfile as _tf
        from datetime import datetime, timedelta
        from pathlib import Path as _P
        from app import backup as bk, auth
        from app.config import settings as _cfg
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)"); c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',1)")
        c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES ('F099-P0001','F099',1,'Casa',1970)")
        for n in (1, 2, 3):
            c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem) VALUES (?,?,?,?,'importado')", (f"F099-P0001-1970-S01-D0000{n}", "F099-P0001", "S01", n))
        c.commit(); c.close()
        tmp = _P(_tf.mkdtemp()); res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        agora = datetime.now()
        # ---- backup básico + restauração verificada ----
        n_fundos = connect().execute("SELECT count(*) FROM fundo").fetchone()[0]   # inclui F031/F032 criados pela migração 007
        r = bk.fazer_backup(agora=agora)
        ver("backup cria arquivo compactado", (bk.PASTA / r["arquivo"]).is_file() and r["arquivo"].endswith(".db.gz"), r["arquivo"])
        ver("contagens da cópia batem com o banco", (r["contagens"]["fundo"], r["contagens"]["projeto"], r["contagens"]["item"]) == (n_fundos, 1, 3) and r["contagens"]["usuario"] == 0, str(r["contagens"]))
        ver("ULTIMO.json gravado com ok=True", bk.estado()["ok"] is True and bk.estado()["existe"])
        v = bk.restaurar_para(bk.PASTA / r["arquivo"], tmp / "rest.db")
        ver("restauração verificada: íntegra e com os mesmos dados", v["integridade"] == "ok" and v["item"] == 3 and v["projeto"] == 1, str(v))
        try:
            bk.restaurar_para(bk.PASTA / r["arquivo"], _P(_cfg.CAMP_DB_PATH)); ver("RECUSA restaurar por cima do banco em uso", False)
        except bk.BackupErro:
            ver("RECUSA restaurar por cima do banco em uso", True)
        # ---- consistência com o banco sendo gravado durante a cópia ----
        stop, n = threading.Event(), [0]
        def escreve():
            k = __import__("sqlite3").connect(_cfg.CAMP_DB_PATH, timeout=30)
            while not stop.is_set():
                k.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('x','x','x','escritor')"); k.commit(); n[0] += 1
            k.close()
        t = threading.Thread(target=escreve); t.start(); _t.sleep(0.3)
        r2 = bk.fazer_backup(agora=agora + timedelta(seconds=1)); stop.set(); t.join()
        ver("backup feito DURANTE gravações continua íntegro", r2["contagens"]["integridade"] == "ok" and n[0] > 0, f"{n[0]} gravações concorrentes")
        # ---- cópia extra ----
        ex = tmp / "qnap"; ex.mkdir()
        r3 = bk.fazer_backup(destino_extra=str(ex), agora=agora + timedelta(seconds=2))
        ver("cópia extra criada e conferida", r3["extra"]["ok"] and (ex / "camp-painel" / r3["arquivo"]).is_file())
        r4 = bk.fazer_backup(destino_extra="/pasta/que/nao/existe", agora=agora + timedelta(seconds=3))
        ver("cópia extra que falha NÃO invalida o backup local", r4["extra"]["ok"] is False and (bk.PASTA / r4["arquivo"]).is_file(), str(r4["extra"]))
        # ---- verificação reprovada: nada é aceito e o anterior continua ----
        antes = sorted(p.name for p in bk.PASTA.iterdir() if p.name.startswith("camp-"))
        original = bk._inspeciona
        bk._inspeciona = lambda p: {"integridade": "corrompido"}
        try:
            bk.fazer_backup(agora=agora + timedelta(seconds=4)); ver("cópia reprovada é recusada", False)
        except bk.BackupErro:
            ver("cópia reprovada é recusada", True)
        bk._inspeciona = original
        depois = sorted(p.name for p in bk.PASTA.iterdir() if p.name.startswith("camp-"))
        ver("falha não apaga nem cria backup e não deixa lixo (.tmp)", antes == depois and not list(bk.PASTA.glob(".camp-*.tmp")))
        e = bk.estado()
        ver("estado registra a falha mas mantém o último sucesso", e["ok"] is False and e["erro"] and e["existe"] and e["idade_horas"] is not None, f"ok={e['ok']} idade={e['idade_horas']}")
        # ---- retenção com datas simuladas ----
        ret = tmp / "ret"; ret.mkdir()
        agora_ret = datetime(2026, 10, 5, 12, 0, 0)
        d = datetime(2026, 8, 1, 3, 30)
        while d <= datetime(2026, 10, 5, 3, 30):
            (ret / f"camp-{d:%Y%m%d-%H%M%S}.db.gz").write_bytes(b"x"); d += timedelta(days=1)
        for nome in ("camp-20261005-100000.db", "camp-20261001-153000.db.gz", "leia-me.txt", "camp-manual.db", "ULTIMO.json"):
            (ret / nome).write_bytes(b"x")
        rem = bk.aplicar_retencao(ret, agora_ret)
        fica = {p.name for p in ret.iterdir()}
        ver("retenção: tudo das últimas 24 h fica", {"camp-20261005-033000.db.gz", "camp-20261005-100000.db"} <= fica)
        dias_ok = all(sum(1 for f in fica if f.startswith(f"camp-{(datetime(2026,10,5).date()-timedelta(days=k)):%Y%m%d}-")) == (2 if k == 0 else 1) for k in range(0, 14))
        ver("retenção: 1 por dia nos últimos 14 dias (2 hoje, pois ambos <24h)", dias_ok)
        ver("retenção: no dia com 2 backups fica o mais novo", "camp-20261001-153000.db.gz" in fica and "camp-20261001-033000.db.gz" not in fica)
        antigos = [f for f in fica if (lambda q: q and q < datetime(2026, 9, 22))(bk._quando(f))]
        semanas = [tuple(bk._quando(f).date().isocalendar())[:2] for f in antigos]
        ver("retenção: no máx. 1 por semana entre 14 dias e 8 semanas", len(semanas) == len(set(semanas)) and len(semanas) >= 5, f"{len(semanas)} semanas")
        ver("retenção: nada com mais de 8 semanas", not [f for f in fica if (lambda q: q and q.date() < datetime(2026, 8, 10).date())(bk._quando(f))])
        ver("retenção: arquivos que não são backup NÃO são tocados", {"leia-me.txt", "camp-manual.db", "ULTIMO.json"} <= fica)
        e2 = bk.estado(pasta=ret, agora=agora_ret)
        ver("estado sem ULTIMO.json usa o backup mais recente (do atualizar.sh)", e2["existe"] and e2["origem"] == "atualizar.sh" and e2["idade_horas"] == 2.0, f"{e2['arquivo']} {e2['idade_horas']}h")
        ver("estado sem nenhum backup", bk.estado(pasta=tmp / "vazio", agora=agora_ret)["existe"] is False)
        # ---- API e permissões ----
        auth.criar_usuario("Adm", "adm@camp.arq.br", "senha-admin-12345", "admin", forcar_troca=False)
        auth.criar_usuario("Op", "op@camp.arq.br", "senha-operador-123", "operador", forcar_troca=False)
        def cli(em, se):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": se}); return x
        adm, op = cli("adm@camp.arq.br", "senha-admin-12345"), cli("op@camp.arq.br", "senha-operador-123")
        ver("API: operador NÃO vê backup (403)", op.get("/api/backup").status_code == 403 and op.post("/api/backup/agora").status_code == 403)
        g = adm.get("/api/backup"); ver("API: admin vê o estado", g.status_code == 200 and g.json()["existe"], f"HTTP {g.status_code}")
        a = adm.post("/api/backup/agora"); ver("API: admin faz backup agora", a.status_code == 200 and a.json()["ok"] and (bk.PASTA / a.json()["arquivo"]).is_file(), f"HTTP {a.status_code} {a.text[:80]}")
        evs = connect().execute("SELECT count(*) FROM evento WHERE tipo='backup_manual'").fetchone()[0]
        ver("API: backup manual fica na auditoria", evs == 1)
        from app.rotas_gestao import _estado_qnap
        vazia, cheia = tmp / "qnap_vazia", tmp / "qnap_cheia"; vazia.mkdir(); cheia.mkdir(); (cheia / "lote1").mkdir()
        ver("QNAP: pasta que não existe = não conectado (nao_existe)", _estado_qnap(tmp / "nada") == (False, "nao_existe"))
        ver("QNAP: pasta VAZIA criada à mão NÃO conta como conectada (vazia)", _estado_qnap(vazia) == (False, "vazia"))
        ver("QNAP: pasta com conteúdo conta como conectada", _estado_qnap(cheia) == (True, None))
        est = op.get("/api/estacoes").json()["qnap"]
        ver("/api/estacoes devolve montado e o motivo", est["montado"] is False and est["motivo"] in ("nao_existe", "vazia"), str(est.get("motivo")))
        pub = op.get("/api/estacoes").json().get("backup", {})
        ver("estações: leitura recebe o estado do backup SEM caminhos", "existe" in pub and "idade_horas" in pub and "arquivo" not in pub and "extra" not in pub, str(sorted(pub)))
        for l in res: print(l)
    elif modo == "previa":
        init_db(); aplicar_migracoes()
        import json as _j, subprocess as _sp, sys as _sys
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        db = os.environ["CAMP_DB_PATH"]
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        def wp(i, col, status, titulo, md, doc=None, thumb=None, cod=None):
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,documento_url,thumb_url,codigo_detectado,metadados) VALUES (?,?,?,?,?,?,?,?,?)",
                      (i, col, status, titulo, f"s-{i}", doc, thumb, cod, _j.dumps(md)))
        wp(100, 8007, "publish", "P0001 — Casa de teste", {"Código de Catalogação": "F099-P0001", "Ano": "1970"})
        C = lambda n: f"F099-P0001-1970-S01-D0000{n}"
        wp(8001, 8013, "publish", "Planta 1", {"Código do documento": C(1)}, doc="https://s/1.jpg", cod=C(1))
        wp(8002, 8013, "draft", "Planta 2 sem imagem", {"Código do documento": C(2)}, cod=C(2))
        wp(8003, 8013, "publish", "Planta 3", {"Código do documento": C(3)}, doc="https://s/3.jpg", cod=C(3))
        wp(8010, 8013, "draft", "Teste sem código nenhum", {})
        wp(8011, 8013, "draft", "Orfã", {"Código do documento": "F099-P0009-1970-S01-D00001"}, doc="https://s/o.jpg", cod="F099-P0009-1970-S01-D00001")
        c.commit(); c.close()
        auth.criar_usuario("Adm", "adm@camp.arq.br", "senha-admin-12345", "admin", forcar_troca=False)
        auth.criar_usuario("Op", "op@camp.arq.br", "senha-operador-123", "operador", forcar_troca=False)
        def cli(em, se):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": se}); return x
        adm, op = cli("adm@camp.arq.br", "senha-admin-12345"), cli("op@camp.arq.br", "senha-operador-123")
        def estado():
            k = connect(); r = tuple(k.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("projeto", "item", "numero_p", "evento")); k.close(); return r
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        ver("operador NÃO vê a prévia nem importa (403)", op.get("/api/importacao/previa").status_code == 403 and op.post("/api/importacao/executar", json={"esperado_itens_novos": 3, "esperado_projetos_novos": 1}).status_code == 403)
        antes = estado()
        r = adm.get("/api/importacao/previa"); pv = r.json()
        ver("prévia calcula o que entraria", r.status_code == 200 and (pv["projetos_novos"], pv["itens_novos"]) == (1, 3), f"HTTP {r.status_code} {pv.get('projetos_novos')} {pv.get('itens_novos')}")
        ver("SIMULAR NÃO GRAVA NADA (projetos, itens, numero_p e eventos intactos)", estado() == antes, f"{antes} -> {estado()}")
        ver("prévia lista novos por fundo", pv["novos_por_fundo"] == [{"fundo": "F099", "itens": 3, "projetos": 1}], str(pv["novos_por_fundo"]))
        ver("prévia aponta os itens do site SEM imagem (inclusive o sem código)", pv["site_sem_imagem_total"] == 2 and {x["id"] for x in pv["site_sem_imagem"]} == {8002, 8010} and C(2) in {x["codigo"] for x in pv["site_sem_imagem"]}, str(pv["site_sem_imagem"]))
        ver("prévia aponta item sem código e folha sem projeto", pv["sem_codigo_total"] == 1 and len(pv["item_sem_projeto"]) == 1 and pv["item_sem_projeto"][0]["codigo"] == "F099-P0009-1970-S01-D00001")
        ver("prévia conta itens locais x site", pv["total_local"] == 0 and pv["total_site"] == 5 and pv["locais_sem_item_no_site"] == 0)
        out = _sp.run([_sys.executable, os.path.join(os.path.dirname(os.environ["PYTHONPATH"]), "scripts", "importar_site.py"), "--simular"], env=os.environ, capture_output=True, text=True)
        ver("CLI --simular mostra a prévia e não grava", "SIMULAÇÃO: nada foi gravado. Novos: 1 projetos, 3 itens" in out.stdout and estado() == antes, (out.stdout + out.stderr)[-120:])
        r = adm.post("/api/importacao/executar", json={"esperado_itens_novos": 0, "esperado_projetos_novos": 0})
        ver("execução com números diferentes da prévia é RECUSADA (409) e não grava", r.status_code == 409 and estado() == antes, f"HTTP {r.status_code}")
        r = adm.post("/api/importacao/executar", json={"esperado_itens_novos": 3, "esperado_projetos_novos": 1}); ex = r.json()
        ver("execução confirmada importa exatamente o que a prévia mostrou", r.status_code == 200 and (ex["projetos_novos"], ex["itens_novos"]) == (1, 3), str(ex))
        k = connect()
        ver("itens e projeto realmente criados", {x[0] for x in k.execute("SELECT codigo FROM item")} == {C(1), C(2), C(3)} and k.execute("SELECT count(*) FROM projeto WHERE codigo='F099-P0001'").fetchone()[0] == 1)
        ver("importação fica na auditoria", k.execute("SELECT count(*) FROM evento WHERE tipo='importacao_site'").fetchone()[0] == 1); k.close()
        pv2 = adm.get("/api/importacao/previa").json()
        ver("depois de importar, a prévia não tem mais nada novo (idempotente)", (pv2["projetos_novos"], pv2["itens_novos"]) == (0, 0) and pv2["itens_atualizados"] == 3 and pv2["total_local"] == 3, str((pv2["projetos_novos"], pv2["itens_novos"], pv2["itens_atualizados"])))
        for l in res: print(l)
    elif modo == "publicacao":
        init_db(); aplicar_migracoes()
        import json as _j, sqlite3 as _s, time as _t
        from app import auth
        import app.wp as wpmod, app.publicador as pubmod
        from fastapi.testclient import TestClient
        from app.main import app
        db = os.environ["CAMP_DB_PATH"]
        c = connect()
        for f in ("F099", "F098", "F097"):
            c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES (?,?,1)", (f, f"Fundo {f}"))
        def proj(f, n, wid, aut=0, teste=0):
            cod = f"{f}-P000{n}"
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (f, n))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,tainacan_item_id,autorizado_site,lote_teste) VALUES (?,?,?,?,1970,?,?,?)", (cod, f, n, f"Casa {cod}", wid, aut, teste))
            if wid: c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado) VALUES (?,8007,'draft',?,?)", (wid, f"Dossiê {cod}", cod))
            return cod
        P1 = proj("F099", 1, 100); P2 = proj("F099", 2, 101); P3 = proj("F099", 3, 102, aut=1, teste=1); P4 = proj("F099", 4, None)
        Q1 = proj("F098", 1, 200)
        def item(proj_cod, n, wid, dup=None):
            cod = f"{proj_cod}-1970-S01-D0000{n}"
            c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,tainacan_item_id,duplicata_de,tipo_duplicata,origem) VALUES (?,?,?,?,?,?,?,'importado')",
                      (cod, proj_cod, "S01", n, wid, dup, "exata" if dup else None))
            if wid: c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado) VALUES (?,8013,'draft',?,?)", (wid, f"Folha {n}", cod))
            return cod
        D1, D2, D3, D4 = item(P1, 1, 8001), item(P1, 2, 8002), item(P1, 3, 8003), item(P1, 4, None)
        D5 = item(P1, 5, 8005, dup=D1)       # duplicada: tem id no site mas NÃO entra na publicação
        c.commit(); c.close()
        for em, nome, papel in (("m@camp.arq.br", "M", "master"), ("adm@camp.arq.br", "A", "admin"), ("op@camp.arq.br", "O", "operador")):
            auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        mst, adm, op = cli("m@camp.arq.br"), cli("adm@camp.arq.br"), cli("op@camp.arq.br")
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        sonda = []
        class Fake:
            chamadas, falhar = [], set()
            def atualizar_status_item(self, cid, wid, status):
                k = _s.connect(db, timeout=1)   # o painel precisa conseguir GRAVAR durante a rede (nenhum lock longo)
                try: k.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('x','x','x','sonda')"); k.commit(); sonda.append(True)
                except _s.OperationalError: sonda.append(False)
                finally: k.close()
                if wid in Fake.falhar: raise RuntimeError(f"Tainacan recusou (403) item {wid}: rest_forbidden")
                Fake.chamadas.append((cid, wid, status)); return {}
        wpmod.WP = Fake; pubmod.WP = Fake
        def err(r):
            try: return r.json().get("erro") or ""
            except Exception: return r.text
        def st(tab, cod):
            k = connect(); r = k.execute(f"SELECT status_site FROM {tab} WHERE codigo=?", (cod,)).fetchone()[0]; k.close(); return r
        # ---- checklist ----
        r = op.get(f"/api/projetos/{P1}/publicacao"); g = r.json()
        ids_falta = {x["id"] for x in g["condicoes"] if x["bloqueia"] and not x["ok"]}
        ver("operador VÊ o checklist (leitura)", r.status_code == 200 and g["pode_agir"] is False, f"HTTP {r.status_code}")
        ver("checklist mostra o que falta: direitos e autorização (nada mais)", ids_falta == {"direitos", "autorizado"}, str(ids_falta))
        ver("cada pendência traz o botão que resolve", {x["acao"]["tipo"] for x in g["condicoes"] if x["bloqueia"] and not x["ok"]} == {"direitos", "autorizar"})
        ver("avisos: 1 folha fora do site e 1 duplicada excluída", {x["id"] for x in g["condicoes"] if not x["bloqueia"]} == {"folhas_fora", "folhas_excluidas"} and g["folhas_elegiveis"] == 3 and g["folhas_total"] == 5, f"elegíveis={g['folhas_elegiveis']} total={g['folhas_total']}")
        # ---- publicar bloqueado: TODAS as razões de uma vez ----
        r = adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "publicar"})
        ver("publicar bloqueado devolve TODAS as pendências (400)", r.status_code == 400 and "Direitos do fundo" in err(r) and "não foi autorizado" in err(r), err(r)[:140])
        ver("nada foi enviado ao site e nada mudou", Fake.chamadas == [] and st("projeto", P1) == "nao_publicado")
        # ---- satisfaz as condições pela própria API ----
        r = adm.put("/api/fundos/F099/direitos", json={"situacao": "autorizado", "titular": "Família X", "documento_autorizacao": "Termo 001"}); ver("direitos autorizados pela API", r.status_code == 200, f"HTTP {r.status_code} {r.text[:80]}")
        r = adm.patch(f"/api/projetos/{P1}", json={"autorizado_site": True}); ver("projeto autorizado pela API", r.status_code == 200, f"HTTP {r.status_code} {r.text[:80]}")
        g = op.get(f"/api/projetos/{P1}/publicacao").json(); ver("checklist libera a publicação", g["pode_publicar"] is True)
        # ---- publicar ----
        Fake.chamadas.clear(); sonda.clear()
        r = adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "publicar"}); j = r.json()
        ver("publicar OK: dossiê + 3 folhas (duplicada e sem vínculo ficam de fora)", r.status_code == 200 and j["ok"] and (j["alterados"], j["total"]) == (4, 4), str(j)[:140])
        ver("enviou ao Tainacan a coleção e o status certos", sorted(Fake.chamadas) == sorted([(8007, 100, "publish"), (8013, 8001, "publish"), (8013, 8002, "publish"), (8013, 8003, "publish")]), str(Fake.chamadas))
        ver("estado local atualizado só para o que foi publicado", st("projeto", P1) == "no_ar" and st("item", D1) == "no_ar" and st("item", D3) == "no_ar" and st("item", D5) == "nao_publicado" and st("item", D4) == "nao_publicado")
        ver("DURANTE a rede o painel consegue gravar (nenhum lock longo)", sonda and all(sonda), str(sonda))
        ver("resposta traz mensagem em português", "4 registro(s) publicados" in j["mensagem"], j["mensagem"])
        k = connect(); ver("publicação fica na auditoria", k.execute("SELECT count(*) FROM evento WHERE codigo=? AND tipo='site_publicar'", (P1,)).fetchone()[0] == 1); k.close()
        # ---- falha parcial do Tainacan: lista TODAS e salva o resto ----
        Fake.falhar = {8002}; Fake.chamadas.clear()
        r = adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "rascunho"})
        ver("admin comum NÃO volta para rascunho o que está publicado (403): tira do público como despublicar", r.status_code == 403 and "Despublicar" in err(r), err(r)[:90])
        r = mst.post(f"/api/projetos/{P1}/publicar", json={"acao": "rascunho"}); j = r.json()
        ver("falha parcial: ok=False, 3 de 4 voltaram a rascunho, 1 falha explicada", r.status_code == 200 and not j["ok"] and (j["alterados"], j["total"], len(j["falhas"])) == (3, 4, 1) and "Tainacan recusou (403)" in j["falhas"][0]["erro"] and j["falhas"][0]["codigo"] == D2, str(j)[:160])
        ver("falha parcial: o que falhou continua publicado, o resto mudou", st("item", D2) == "no_ar" and st("item", D1) == "rascunho" and st("projeto", P1) == "rascunho")
        ver("mensagem diz quantos falharam", "1 falharam" in j["mensagem"], j["mensagem"])
        Fake.falhar = set()
        # ---- WordPress inacessível: 503 claro, não 500 ----
        class SemWP:
            def __init__(self): raise RuntimeError("senha de aplicação não configurada")
        wpmod.WP = SemWP; pubmod.WP = SemWP
        r = adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "publicar"})
        ver("WordPress inacessível: 503 com explicação (não 500 genérico)", r.status_code == 503 and "WordPress" in err(r) and "Configurações" in err(r), f"HTTP {r.status_code} {r.text[:120]}")
        ver("o painel segue respondendo depois disso (conexão não vazou)", adm.get(f"/api/projetos/{P1}/publicacao").status_code == 200)
        wpmod.WP = Fake; pubmod.WP = Fake
        # ---- permissões de despublicar ----
        Fake.chamadas.clear(); adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "publicar"})
        r = adm.post(f"/api/projetos/{P1}/publicar", json={"acao": "tirar_do_ar"})
        ver("admin comum NÃO despublica o que está publicado (403, vocabulário novo)", r.status_code == 403 and "Despublicar" in err(r), r.text[:100])
        r = mst.post(f"/api/projetos/{P1}/publicar", json={"acao": "tirar_do_ar"})
        ver("master despublica: vai para 'fora_do_ar' (Despublicado)", r.status_code == 200 and r.json()["ok"] and st("projeto", P1) == "fora_do_ar", r.text[:100])
        # ---- projeto sem nenhum registro no site ----
        g = op.get(f"/api/projetos/{P4}/publicacao").json(); site = next(x for x in g["condicoes"] if x["id"] == "site")
        ver("projeto sem registros no site: o checklist diz e oferece 'Enviar folhas ao site'", not site["ok"] and site["acao"]["tipo"] == "subir_folhas")
        r = adm.post(f"/api/projetos/{P4}/publicar", json={"acao": "rascunho"}); j = r.json()
        ver("mudar publicação sem registros no site NÃO responde '0 atualizados' mudo", r.status_code == 200 and not j["ok"] and "ainda não tem registros no site" in j["mensagem"], str(j)[:120])
        # ---- lote ----
        Fake.chamadas.clear()
        r = adm.post("/api/projetos/lote", json={"codigos": [P1, P2], "acao": "publicar"}); j = r.json()
        ver("lote: um publica e o outro volta com o MOTIVO", r.status_code == 200 and [x["codigo"] for x in j["ok"]] == [P1] and len(j["falhas"]) == 1 and j["falhas"][0]["codigo"] == P2 and "não foi autorizado" in j["falhas"][0]["erro"], str(j)[:200])
        # ---- fundo inteiro: mesmas regras ----
        Fake.chamadas.clear()
        r = mst.post("/api/fundos/F099/status-site", json={"acao": "no_ar"}); j = r.json()
        feitos_cods = {(w, st_) for (_c, w, st_) in Fake.chamadas}
        ver("fundo inteiro: publica só o que está pronto (P1: dossiê + 3 folhas)", r.status_code == 200 and j["ok"] and j["alterados"] == 4 and feitos_cods == {(100, "publish"), (8001, "publish"), (8002, "publish"), (8003, "publish")}, str(j)[:160])
        ver("fundo inteiro NÃO publica a folha duplicada", all(w != 8005 for (_c, w, _s2) in Fake.chamadas))
        mot = {x["codigo"]: x["motivo"] for x in j["ignorados"]}
        ver("fundo inteiro explica quem ficou de fora e por quê (não autorizado, lote de teste, sem dossiê)", j["ignorados_total"] == 3 and "não foi autorizado" in mot[P2] and "teste" in mot[P3].lower() and "dossiê" in mot[P4], str(mot)[:200])
        k = connect(); ver("fundo ficou 'no_ar' (Publicado) e a ação ficou na auditoria", k.execute("SELECT status_site FROM fundo WHERE codigo='F099'").fetchone()[0] == "no_ar" and k.execute("SELECT count(*) FROM evento WHERE entidade='fundo' AND tipo='site_no_ar'").fetchone()[0] == 1); k.close()
        mst.put("/api/fundos/F098/direitos", json={"situacao": "autorizado", "titular": "Família Y", "documento_autorizacao": "Termo 002"})
        r = mst.post("/api/fundos/F097/status-site", json={"acao": "no_ar"})
        ver("fundo SEM direitos definidos: recusa com a explicação (400) em vez de '0 alterados'", r.status_code == 400 and "Direitos do fundo" in err(r) and "F097" in err(r), err(r)[:140])
        r = mst.post("/api/fundos/F098/status-site", json={"acao": "no_ar"}); j = r.json()
        ver("fundo sem NADA pronto: não diz '0 alterados' mudo, explica o motivo", r.status_code == 200 and not j["ok"] and "Nenhum projeto estava pronto" in (j["erro"] or "") and j["ignorados_total"] == 1, str(j)[:200])
        for l in res: print(l)
    elif modo == "adotar":
        init_db(); aplicar_migracoes()
        import json as _j
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        for n in (1, 2):
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',?)", (n,))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,status_site,tainacan_item_id) VALUES (?,?,?,?,1970,'nao_publicado',?)", (f"F099-P000{n}", "F099", n, f"Casa {n}", 100 + n))
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,metadados) VALUES (?,8007,'publish',?,?,?)", (100 + n, f"Dossiê {n}", f"F099-P000{n}", _j.dumps({"Código de Catalogação": f"F099-P000{n}"})))
        def wp(i, cod, titulo):
            c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,documento_url,codigo_detectado,metadados) VALUES (?,8013,'draft',?,?,?,?,?)",
                      (i, titulo, f"s-{i}", f"https://s/{i}.jpg", cod, _j.dumps({"Código do documento": cod, "Folha": "01"})))
        D = lambda p_, n: f"F099-P000{p_}-1970-S01-D0000{n}"
        c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,tainacan_item_id,origem) VALUES (?,?,?,?,?,'importado')", (D(1, 1), "F099-P0001", "S01", 1, 8001))
        wp(8001, D(1, 1), "Planta 1"); wp(8002, D(1, 2), "Planta 2 só no site"); wp(8003, D(1, 3), "Planta 3 só no site"); wp(8101, D(2, 1), "Outro projeto só no site")
        c.commit(); c.close()
        for em, nome, papel in (("op@camp.arq.br", "Op", "operador"), ("le@camp.arq.br", "Le", "leitura")):
            auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        op, le = cli("op@camp.arq.br"), cli("le@camp.arq.br")
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        def existe(cod):
            k = connect(); r = k.execute("SELECT origem FROM item WHERE codigo=?", (cod,)).fetchone(); k.close(); return r[0] if r else None
        ver("antes: a folha só no site NÃO existe no catálogo do painel (por isso dava 'não encontrado')", op.get(f"/api/itens/{D(1, 2)}").status_code == 404 and existe(D(1, 2)) is None)
        ver("leitura NÃO importa (403)", le.post("/api/projetos/F099-P0001/importar-folhas", json={"item": D(1, 2)}).status_code == 403)
        r = op.post("/api/projetos/F099-P0001/importar-folhas", json={"item": D(1, 2)}); j = r.json()
        ver("operador importa UMA folha só no site", r.status_code == 200 and (j["itens_novos"], j["itens_atualizados"]) == (1, 0), str(j))
        ver("a folha importada passa a existir e abre normalmente", existe(D(1, 2)) == "importado" and op.get(f"/api/itens/{D(1, 2)}").status_code == 200)
        ver("só aquela folha entrou (escopo certo): outra do projeto e a de outro projeto NÃO", existe(D(1, 3)) is None and existe(D(2, 1)) is None)
        k = connect(); pj = k.execute("SELECT status_site FROM projeto WHERE codigo='F099-P0001'").fetchone()[0]; k.close()
        ver("o projeto NÃO é alterado (o dossiê está publicado no site mas o painel segue 'nao_publicado')", pj == "nao_publicado", pj)
        r = op.patch(f"/api/itens/{D(1, 2)}", json={"titulo": "Planta baixa térrea", "escala": "1:50"})
        ver("depois de importada, EDITA como as outras (PATCH 200)", r.status_code == 200 and op.get(f"/api/itens/{D(1, 2)}").json()["item"]["titulo"] == "Planta baixa térrea", f"HTTP {r.status_code}")
        ver("folha de OUTRO projeto é recusada (400)", op.post("/api/projetos/F099-P0001/importar-folhas", json={"item": D(2, 1)}).status_code == 400)
        ver("folha que não está no site: 404 claro", op.post("/api/projetos/F099-P0001/importar-folhas", json={"item": D(1, 9)}).status_code == 404)
        ver("projeto que não existe: 404", op.post("/api/projetos/F099-P0077/importar-folhas", json={}).status_code == 404)
        r = op.post("/api/projetos/F099-P0001/importar-folhas", json={}); j = r.json()
        ver("projeto inteiro: traz as que faltam (só a D3) e atualiza as já existentes", r.status_code == 200 and j["itens_novos"] == 1 and existe(D(1, 3)) == "importado" and existe(D(2, 1)) is None, str(j))
        ver("a edição feita antes NÃO é sobrescrita pela reimportação", op.get(f"/api/itens/{D(1, 2)}").json()["item"]["titulo"] == "Planta baixa térrea")
        r = op.post("/api/projetos/F099-P0001/importar-folhas", json={}); ver("repetir é idempotente (0 novas)", r.json()["itens_novos"] == 0)
        k = connect(); ver("importações ficam na auditoria", k.execute("SELECT count(*) FROM evento WHERE tipo='importacao_folhas'").fetchone()[0] == 3); k.close()
        for l in res: print(l)
    elif modo == "urlpublica":
        init_db(); aplicar_migracoes()
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        for n, tit, cid in ((1, "Igreja Paróquia Mãe do Salvador, São Paulo/SP", "São Paulo"), (2, "Casa Dois", "Santos"), (3, "Casa Três", "Santos"), (4, "Casa Quatro", "Santos")):
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',?)", (n,))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES (?,?,?,?,1970,?)", (f"F099-P000{n}", "F099", n, tit, cid))
        pg = lambda i, slug, st, cod: c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status,codigo_detectado) VALUES (?,?,?,?,?,?)", (i, slug, slug, f"https://camp.arq.br/acervo/projetos/{slug}/", st, cod))
        pg(1, "f099-p0002-slug-do-plugin-publicado", "publish", "F099-P0002")
        pg(2, "f099-p0002-slug-antigo-rascunho", "draft", "F099-P0002")        # a PUBLICADA tem preferência
        pg(3, "f099-p0003-pagina-sem-codigo-detectado", "publish", None)       # achada pelo slug que começa com o código
        c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status,codigo_detectado) VALUES (9,'Outra','f099-p0004-fora','https://camp.arq.br/quem-somos/f099-p0004-fora/','publish','F099-P0004')")  # fora de /acervo/projetos/: ignorada
        c.commit(); c.close()
        auth.criar_usuario("Op", "op@camp.arq.br", "senha-longa-12345", "operador", forcar_troca=False)
        x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": "op@camp.arq.br", "senha": "senha-longa-12345"})
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        def det(cod): return x.get(f"/api/projetos/{cod}/detalhe").json()
        d1 = det("F099-P0001")
        ver("sem página no espelho: monta o endereço SEM cidade/UF (caso 'São Paulo/SP' com barra)", d1["site_url"] == "https://camp.arq.br/acervo/projetos/f099-p0001-igreja-paroquia-mae-do-salvador/" and d1["site_url_origem"] == "presumido" and d1["pagina_status"] is None, d1["site_url"])
        ver("o endereço montado NÃO tem '-sao-paulo-sp' (o defeito do link que não abria)", "sao-paulo" not in d1["site_url"])
        d2 = det("F099-P0002")
        ver("com página no espelho: usa o endereço REAL (não o montado)", d2["site_url"] == "https://camp.arq.br/acervo/projetos/f099-p0002-slug-do-plugin-publicado/" and d2["site_url_origem"] == "site", d2["site_url"])
        ver("duas páginas: a PUBLICADA tem preferência sobre o rascunho", d2["pagina_status"] == "publish")
        d3 = det("F099-P0003")
        ver("página sem código detectado é achada pelo slug que começa com o código", d3["site_url"].endswith("f099-p0003-pagina-sem-codigo-detectado/") and d3["site_url_origem"] == "site", d3["site_url"])
        d4 = det("F099-P0004")
        ver("página FORA de /acervo/projetos/ é ignorada (volta ao endereço montado)", d4["site_url_origem"] == "presumido" and "quem-somos" not in d4["site_url"], d4["site_url"])
        for l in res: print(l)
    elif modo == "foto":
        init_db(); aplicar_migracoes()
        import base64
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        JPG = base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDIooor5E+4P//Z")
        PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
        ids = {}
        for chave, em, papel in (("master", "m@camp.arq.br", "master"), ("admin", "adm@camp.arq.br", "admin"), ("admin2", "adm2@camp.arq.br", "admin"), ("operador", "op@camp.arq.br", "operador"), ("leitura", "le@camp.arq.br", "leitura")):
            ids[chave] = auth.criar_usuario(em.split("@")[0], em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        mst, adm, op, le, anon = cli("m@camp.arq.br"), cli("adm@camp.arq.br"), cli("op@camp.arq.br"), cli("le@camp.arq.br"), TestClient(app, raise_server_exceptions=False)
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        put = lambda cl, uid, corpo, tipo="image/jpeg": cl.put(f"/api/usuarios/{uid}/foto", content=corpo, headers={"Content-Type": tipo})
        ver("sem foto: GET dá 404 e /eu diz tem_foto=false", op.get(f"/api/usuarios/{ids['operador']}/foto").status_code == 404 and op.get("/api/auth/eu").json()["tem_foto"] is False)
        r = put(op, ids["operador"], JPG); ver("a pessoa troca a PRÓPRIA foto (operador)", r.status_code == 200, f"HTTP {r.status_code} {r.text[:60]}")
        r = op.get(f"/api/usuarios/{ids['operador']}/foto")
        ver("GET devolve a imagem com o tipo certo e nosniff", r.status_code == 200 and r.content == JPG and r.headers["content-type"] == "image/jpeg" and r.headers.get("x-content-type-options") == "nosniff", r.headers.get("content-type", ""))
        ver("colegas veem a foto (qualquer logado) e /eu traz id e tem_foto", le.get(f"/api/usuarios/{ids['operador']}/foto").status_code == 200 and op.get("/api/auth/eu").json()["tem_foto"] is True and op.get("/api/auth/eu").json()["id"] == ids["operador"])
        ver("sem login não vê foto (401)", anon.get(f"/api/usuarios/{ids['operador']}/foto").status_code == 401)
        ver("leitura NÃO troca a foto de outra pessoa (403)", put(le, ids["operador"], JPG).status_code == 403)
        ver("operador NÃO troca a foto de outra pessoa (403)", put(op, ids["leitura"], JPG).status_code == 403)
        ver("admin troca a foto de operador/leitura", put(adm, ids["leitura"], JPG).status_code == 200 and put(adm, ids["operador"], PNG, "image/png").status_code == 200)
        ver("PNG também vale e é servido como PNG", op.get(f"/api/usuarios/{ids['operador']}/foto").headers["content-type"] == "image/png")
        ver("admin NÃO troca a foto de outro admin nem do master (403)", put(adm, ids["admin2"], JPG).status_code == 403 and put(adm, ids["master"], JPG).status_code == 403)
        ver("admin troca a PRÓPRIA foto (é o caso da Beatriz)", put(adm, ids["admin"], JPG).status_code == 200)
        ver("master troca a foto de qualquer um", all(put(mst, i, JPG).status_code == 200 for i in ids.values()))
        ver("HTML disfarçado de JPEG é RECUSADO (valida o conteúdo, não o cabeçalho)", put(op, ids["operador"], b"<html><script>alert(1)</script></html>").status_code == 400)
        ver("SVG (com script) disfarçado de JPEG é RECUSADO", put(op, ids["operador"], b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "image/jpeg").status_code == 400)
        ver("arquivo enorme é recusado (413)", put(op, ids["operador"], JPG + b"0" * 310000).status_code == 413)
        ver("a recusa NÃO apagou a foto anterior", op.get(f"/api/usuarios/{ids['operador']}/foto").status_code == 200)
        ver("usuário inexistente: 404", put(mst, 99999, JPG).status_code == 404)
        lista = {u["id"]: u["tem_foto"] for u in adm.get("/api/usuarios").json()}
        ver("a lista de usuários traz tem_foto", lista[ids["operador"]] is True)
        ver("operador NÃO remove a foto de outro (403) mas remove a própria", op.delete(f"/api/usuarios/{ids['leitura']}/foto").status_code == 403 and op.delete(f"/api/usuarios/{ids['operador']}/foto").status_code == 200 and op.get(f"/api/usuarios/{ids['operador']}/foto").status_code == 404)
        # ---- troca obrigatória do primeiro acesso: não pode ser contornada ----
        auth.criar_usuario("Nova", "nova@camp.arq.br", "1234567812345678", "admin")   # senha temporária escolhida pelo administrador: aceita
        nv = TestClient(app, raise_server_exceptions=False); lr = nv.post("/api/auth/login", json={"email": "nova@camp.arq.br", "senha": "1234567812345678"})
        ver("a senha temporária escolhida pelo administrador é aceita e o login exige troca", lr.status_code == 200 and lr.json()["precisa_trocar_senha"] is True and nv.get("/api/estacoes").status_code == 428)
        troca = lambda nova: nv.post("/api/auth/trocar-senha", json={"senha_atual": "1234567812345678", "senha_nova": nova}).status_code
        ver("trocar pela MESMA senha é recusado (antes passava e liberava o painel)", troca("1234567812345678") == 400 and nv.get("/api/estacoes").status_code == 428)
        ver("sequência óbvia é recusada (12345678abcd)", troca("12345678abcd") == 400)
        ver("trecho repetido é recusado (abcabcabcabc)", troca("abcabcabcabc") == 400)
        ver("caractere repetido é recusado (aaaaaaaaaaaa)", troca("aaaaaaaaaaaa") == 400)
        ver("senha curta continua recusada", troca("Abc-123") == 400)
        ver("senha boa troca de verdade e libera o painel", troca("Rio-Azul-Verde-77") == 200 and nv.get("/api/estacoes").status_code == 200)
        ver("a senha temporária deixa de funcionar", TestClient(app, raise_server_exceptions=False).post("/api/auth/login", json={"email": "nova@camp.arq.br", "senha": "1234567812345678"}).status_code == 401)
        k = connect(); ev = {r[0]: r[1] for r in k.execute("SELECT tipo, count(*) FROM evento WHERE entidade='usuario' AND tipo LIKE 'foto_%' GROUP BY tipo")}; k.close()
        ver("trocas e remoções ficam na auditoria", ev.get("foto_atualizada", 0) >= 5 and ev.get("foto_removida") == 1, str(ev))
        for l in res: print(l)
    elif modo == "guia":
        init_db(); aplicar_migracoes()
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        for n, aut, wid in ((1, 1, 100), (2, 0, 101), (3, 0, None)):
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',?)", (n,))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,autorizado_site,tainacan_item_id) VALUES (?,?,?,?,1970,?,?)", (f"F099-P000{n}", "F099", n, f"Casa {n}", aut, wid))
        c.execute("INSERT INTO agente (forma_autorizada,tipo,historia,fonte_historia) VALUES ('Paulo Mendes da Rocha','pessoa',NULL,NULL)")
        aid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO agente (forma_autorizada,tipo) VALUES ('Sem Vinculo','pessoa')"); aid2 = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.commit(); c.close()
        for em, nome, papel in (("adm@camp.arq.br", "A", "admin"), ("le@camp.arq.br", "L", "leitura")):
            auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        adm, le, anon = cli("adm@camp.arq.br"), cli("le@camp.arq.br"), TestClient(app, raise_server_exceptions=False)
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        ids = lambda g, f: {x["id"] for x in g["condicoes"] if f(x)}
        # ---------- FUNDO ----------
        r = le.get("/api/fundos/F099/publicacao"); g = r.json()
        ver("leitura vê o checklist do fundo (200) e não pode agir", r.status_code == 200 and g["pode_agir"] is False, f"HTTP {r.status_code}")
        ver("fundo sem direitos: falta direitos e projeto pronto (bloqueiam)", ids(g, lambda x: x["bloqueia"] and not x["ok"]) == {"direitos", "projetos"}, str(ids(g, lambda x: x["bloqueia"] and not x["ok"])))
        ver("recomendações que não bloqueiam: agente, história e sigla", ids(g, lambda x: not x["bloqueia"] and not x["ok"]) == {"agente", "historia", "sigla"})
        ver("contagem: 3 projetos, 1 autorizado, 0 prontos, 0 publicados", g["contagem"] == {"projetos": 3, "autorizados": 1, "prontos": 0, "publicados": 0}, str(g["contagem"]))
        ver("próximo passo diz o que fazer primeiro (direitos)", g["proximo_passo"].startswith("Definir direitos do fundo"), g["proximo_passo"][:80])
        ver("cada pendência traz o botão que a resolve", all(x["acao"] for x in g["condicoes"] if not x["ok"]))
        adm.put("/api/fundos/F099/direitos", json={"situacao": "autorizado", "titular": "Família X", "documento_autorizacao": "Termo 001"})
        g = adm.get("/api/fundos/F099/publicacao").json()
        ver("com direitos autorizados e 1 projeto autorizado com dossiê: o fundo fica pronto", g["pode_publicar"] is True and g["contagem"]["prontos"] == 1 and g["pode_agir"] is True, str(g["contagem"]))
        ver("próximo passo agora orienta a publicar", "Tudo pronto" in g["proximo_passo"], g["proximo_passo"][:80])
        ver("fundo inexistente: 404 e sem login: 401", adm.get("/api/fundos/F000/publicacao").status_code == 404 and anon.get("/api/fundos/F099/publicacao").status_code == 401)
        # ---------- ARQUITETO ----------
        g = le.get(f"/api/agentes/{aid2}/publicacao").json()
        ver("arquiteto sem vínculo: falta vínculo e fundo publicado", ids(g, lambda x: x["bloqueia"] and not x["ok"]) == {"vinculo", "publicado"} and g["pode_publicar"] is False)
        c = connect(); c.execute("INSERT INTO fundo_agente (fundo_codigo,agente_id,papel) VALUES ('F099',?, 'produtor')", (aid,)); c.commit(); c.close()
        g = le.get(f"/api/agentes/{aid}/publicacao").json()
        ver("vinculado ao fundo: vínculo ok, mas AINDA não aparece (nenhum projeto publicado)", ids(g, lambda x: x["id"] == "vinculo" and x["ok"]) == {"vinculo"} and ids(g, lambda x: x["id"] == "publicado" and not x["ok"]) == {"publicado"})
        ver("o checklist diz que foto/bio/ativar são FEITOS NO WORDPRESS (o painel não publica arquiteto)", any(x["id"] == "wpadmin" and not x["ok"] and "wp-admin" in (x["detalhe"] or "") and not x["bloqueia"] for x in g["condicoes"]))
        ver("biografia ausente é apontada como recomendação (e que exige fonte)", any(x["id"] == "historia" and not x["ok"] and "fonte" in x["detalhe"] and not x["bloqueia"] for x in g["condicoes"]))
        c = connect(); c.execute("UPDATE agente SET historia='Biografia com fonte', fonte_historia='Dissertação X' WHERE id=?", (aid2,)); c.commit(); c.close()
        ver("com biografia e fonte a recomendação some", any(x["id"] == "historia" and x["ok"] for x in le.get(f"/api/agentes/{aid2}/publicacao").json()["condicoes"]))
        c = connect(); c.execute("UPDATE projeto SET status_site='no_ar' WHERE codigo='F099-P0001'")
        c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status) VALUES (1,'Paulo','paulo-mendes-da-rocha','https://camp.arq.br/acervo/arquitetos/paulo-mendes-da-rocha/','publish')")
        c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status) VALUES (2,'Outra','paulo-mendes-da-rocha','https://camp.arq.br/outra-area/paulo-mendes-da-rocha/','publish')")
        c.commit(); c.close()
        g = adm.get(f"/api/agentes/{aid}/publicacao").json()
        ver("com projeto publicado: o arquiteto passa a poder aparecer", g["pode_publicar"] is True and ids(g, lambda x: x["id"] == "publicado" and x["ok"]) == {"publicado"}, str(g["proximo_passo"])[:90])
        ver("acha a página REAL do arquiteto no espelho (só em /acervo/arquitetos/)", g["pagina_url"] == "https://camp.arq.br/acervo/arquitetos/paulo-mendes-da-rocha/" and g["pagina_status"] == "publish" and ids(g, lambda x: x["id"] == "pagina" and x["ok"]) == {"pagina"}, str(g["pagina_url"]))
        ver("próximo passo do arquiteto aponta o wp-admin", "wp-admin" in g["proximo_passo"], g["proximo_passo"][:100])
        ver("arquiteto inexistente: 404", adm.get("/api/agentes/99999/publicacao").status_code == 404)
        for l in res: print(l)
    elif modo == "paginacao":
        init_db(); aplicar_migracoes()
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,ativo) VALUES ('F099','Fundo de teste',1)")
        for n in range(1, 231):
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',?)", (n,))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,?,?,?,1970)", (f"F099-P{n:04d}", "F099", n, f"Casa {n}"))
        for n in range(250):
            c.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('teste',?, 'evento_teste','ator')", (f"E{n:04d}",))
        c.commit(); c.close()
        auth.criar_usuario("Adm", "adm@camp.arq.br", "senha-longa-12345", "admin", forcar_troca=False)
        x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": "adm@camp.arq.br", "senha": "senha-longa-12345"})
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        pg = lambda n, por=100: x.get(f"/api/projetos?pagina={n}&por_pagina={por}").json()
        p1, p2, p3, p4 = pg(1), pg(2), pg(3), pg(4)
        ver("projetos: 230 no total, páginas de 100 = 100 + 100 + 30 e a 4ª vazia", (p1["total"], len(p1["itens"]), len(p2["itens"]), len(p3["itens"]), len(p4["itens"])) == (230, 100, 100, 30, 0), str((p1["total"], len(p1["itens"]), len(p2["itens"]), len(p3["itens"]))))
        cods = [i["codigo"] for p in (p1, p2, p3) for i in p["itens"]]
        ver("projetos: as páginas não repetem nem perdem nenhum (230 códigos distintos, em ordem)", len(set(cods)) == 230 and cods == sorted(cods))
        ver("projetos: por_pagina enorme é limitado a 500", x.get("/api/projetos?por_pagina=99999").json()["por_pagina"] == 500)
        ver("projetos: a busca respeita a paginação (total do filtro, não do banco)", x.get("/api/projetos?q=Casa 22&por_pagina=5&pagina=1").json()["total"] == 11 and len(x.get("/api/projetos?q=Casa 22&por_pagina=5&pagina=3").json()["itens"]) == 1)
        e = lambda n, por=100: x.get(f"/api/eventos?pagina={n}&por_pagina={por}&tipo=evento_teste").json()
        e1, e2, e3 = e(1), e(2), e(3)
        ver("auditoria: 250 eventos = páginas de 100 + 100 + 50 (antes só os 200 mais recentes eram visíveis)", (e1["total"], len(e1["eventos"]), len(e2["eventos"]), len(e3["eventos"])) == (250, 100, 100, 50), str((e1["total"], len(e1["eventos"]), len(e2["eventos"]), len(e3["eventos"]))))
        ids = [ev["id"] for p in (e1, e2, e3) for ev in p["eventos"]]
        ver("auditoria: sem repetição e do mais novo para o mais antigo", len(set(ids)) == 250 and ids == sorted(ids, reverse=True))
        ver("auditoria: a resposta informa pagina e por_pagina", (e2["pagina"], e2["por_pagina"]) == (2, 100))
        ver("auditoria: o parâmetro antigo 'limite' continua funcionando", len(x.get("/api/eventos?limite=7&tipo=evento_teste").json()["eventos"]) == 7)
        ver("auditoria: por_pagina enorme é limitado a 1000", x.get("/api/eventos?por_pagina=99999").json()["por_pagina"] == 1000)
        for l in res: print(l)
    elif modo == "qnap":
        init_db(); aplicar_migracoes()
        import os as _os, time as _t, threading as _th
        from pathlib import Path as _P
        from app import auth
        import app.qnap_coletor as qc
        from fastapi.testclient import TestClient
        from app.main import app
        import shutil as _sh
        base = _P(os.environ["CAMP_DB_PATH"]).parent / "qnap_fake"; _sh.rmtree(base, ignore_errors=True); entrada = base / "99 - Entrada"; prontos = base / "100 - Scanners"
        for d in ("A", "B", "C", ".oculta", "@Recycle"): (entrada / d).mkdir(parents=True)
        agora = _t.time()
        _os.utime(entrada / "A", (agora - 3600, agora - 3600)); _os.utime(entrada / "B", (agora - 2 * 86400, agora - 2 * 86400)); _os.utime(entrada / "C", (agora - 5 * 86400, agora - 5 * 86400))
        (prontos / "lot1").mkdir(parents=True); (prontos / "lot1" / "info_projeto.json").write_text("{}")
        (prontos / "grp" / "lot2").mkdir(parents=True); (prontos / "grp" / "lot2" / "status.json").write_text("{}")
        (prontos / "grp" / "lot3" / "img").mkdir(parents=True); (prontos / "grp" / "lot3" / "info_projeto.json").write_text("{}"); (prontos / "grp" / "lot3" / "img" / "status.json").write_text("{}")  # dentro de lote: não conta
        (prontos / "vazio").mkdir(); (prontos / "@Recycle" / "lixo").mkdir(parents=True); (prontos / "@Recycle" / "lixo" / "status.json").write_text("{}")  # lixeira: ignorada
        _os.utime(prontos / "lot1" / "info_projeto.json", (agora - 86400, agora - 86400)); _os.utime(prontos / "grp" / "lot2" / "status.json", (agora - 7200, agora - 7200)); _os.utime(prontos / "grp" / "lot3" / "info_projeto.json", (agora - 1800, agora - 1800))
        c = connect()
        for k, v in (("qnap.raiz", str(base)), ("qnap.entrada_captura", str(entrada)), ("qnap.prontos_raiz", str(prontos))):
            c.execute("UPDATE configuracao SET valor=? WHERE chave=?", (v, k))
        c.commit(); c.close()
        for em, nome, papel in (("adm@camp.arq.br", "A", "admin"), ("le@camp.arq.br", "L", "leitura")):
            auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        adm, le, anon = cli("adm@camp.arq.br"), cli("le@camp.arq.br"), TestClient(app, raise_server_exceptions=False)
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        r = qc.coletar()
        ver("coleta mede o espaço (total e livre)", r.get("montado") == 1 and (r.get("total_gb") or 0) > 0 and r.get("livre_gb") is not None, str(r)[:140])
        ver("entrada bruta: 3 pastas (oculta e @Recycle ignoradas)", r.get("entrada_bruta") == 3, str(r.get("entrada_bruta")))
        ver("pastas PARADAS há mais de 3 dias: só a C", r.get("parados") == 1, str(r.get("parados")))
        ver("lotes prontos: 3 (não entra dentro de lote nem na lixeira)", r.get("prontos") == 3 and r.get("prontos_parcial") == 0, f"{r.get('prontos')} parcial={r.get('prontos_parcial')}")
        ver("último material = o lote mais recente ('grp/lot3'), com data", r.get("ultimo_material_nome") == "grp/lot3" and r.get("ultimo_material_em"), str(r.get("ultimo_material_nome")))
        ver("mede a latência (ms) e a duração, sem erro", isinstance(r.get("latencia_ms"), int) and r.get("duracao_ms") is not None and not r.get("erro"))
        ver("diagnóstico: a pasta de lotes existe e tem 3 pastas no topo (a lixeira não conta); a entrada existe", r.get("prontos_existe") == 1 and r.get("prontos_pastas") == 3 and r.get("entrada_existe") == 1, f"{r.get('prontos_existe')} {r.get('prontos_pastas')} {r.get('entrada_existe')}")
        # ---- QNAP não montado ----
        c = connect(); c.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.raiz'", (str(base / "nada"),)); c.execute("UPDATE configuracao SET valor='' WHERE chave IN ('qnap.entrada_captura','qnap.prontos_raiz')"); c.commit(); c.close()
        r2 = qc.coletar()
        ver("QNAP não montado: guarda montado=0 e o motivo, sem exceção", r2.get("montado") == 0 and r2.get("motivo") == "nao_existe" and "total_gb" not in r2, str(r2)[:120])
        # ---- montagem TRAVADA: nunca pendura ----
        qc.ORCAMENTO_S = 1
        orig = qc._medir
        qc._medir = lambda *a, **k: _t.sleep(3)
        t0 = _t.monotonic(); r3 = qc.coletar(); dt = _t.monotonic() - t0
        ver("montagem TRAVADA: a coleta volta no limite de tempo (não pendura) com o erro explicado", dt < 2.5 and "tempo esgotado" in (r3.get("erro") or ""), f"{dt:.1f}s {r3.get('erro')}")
        r4 = qc.coletar()
        ver("enquanto a coleta presa não termina, não empilha outra (sem vazar threads)", "ainda está presa" in (r4.get("erro") or ""), str(r4.get("erro")))
        _t.sleep(3.2); qc._medir = orig; qc.ORCAMENTO_S = 25
        c = connect(); c.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.raiz'", (str(base),)); c.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.entrada_captura'", (str(entrada),)); c.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(prontos),)); c.commit(); c.close()
        r5 = qc.coletar(); ver("depois de destravar, volta a coletar normalmente", r5.get("montado") == 1 and r5.get("prontos") == 3 and not r5.get("erro"), str(r5)[:100])
        # ---- retenção ----
        c = connect(); c.execute("INSERT INTO qnap_snapshot (coletado_em, montado) VALUES (datetime('now','-100 days'), 1)"); c.commit()
        qc.coletar(); ver("retenção: snapshot de 100 dias é apagado", c.execute("SELECT count(*) FROM qnap_snapshot WHERE coletado_em < datetime('now','-95 days')").fetchone()[0] == 0); c.close()
        # ---- tendência: 20 GB/dia ----
        c = connect(); c.execute("DELETE FROM qnap_snapshot")
        for i in range(8):
            c.execute("INSERT INTO qnap_snapshot (coletado_em, montado, total_gb, livre_gb) VALUES (datetime('now', ?), 1, 10000, ?)", (f"-{7 - i} days", 5000 - 20 * i))
        c.commit(); c.close()
        j = adm.get("/api/qnap").json()
        ver("tendência: ~20 GB/dia e ~240 dias até encher (livre 4.860 GB)", j["crescimento_gb_dia"] is not None and 18 <= j["crescimento_gb_dia"] <= 22 and 215 <= (j["dias_ate_encher"] or 0) <= 265, f"{j['crescimento_gb_dia']} GB/dia, {j['dias_ate_encher']} dias")
        ver("série dos últimos 7 dias para o gráfico (≤ 60 pontos, em ordem)", 2 <= len(j["serie"]) <= 60 and j["serie"][0]["livre_gb"] > j["serie"][-1]["livre_gb"])
        c = connect(); c.execute("DELETE FROM qnap_snapshot"); c.execute("INSERT INTO qnap_snapshot (coletado_em, montado, total_gb, livre_gb) VALUES (datetime('now'), 1, 10000, 5000)"); c.commit(); c.close()
        ver("com 1 ponto só não inventa tendência", adm.get("/api/qnap").json()["dias_ate_encher"] is None)
        c = connect(); c.execute("DELETE FROM qnap_snapshot")
        for i in range(6): c.execute("INSERT INTO qnap_snapshot (coletado_em, montado, total_gb, livre_gb) VALUES (datetime('now', ?), 1, 10000, ?)", (f"-{5 - i} days", 5000 + 30 * i))
        c.commit(); c.close()
        j = adm.get("/api/qnap").json(); ver("espaço sobrando (liberando): não há 'dias até encher'", j["dias_ate_encher"] is None and (j["crescimento_gb_dia"] or 0) < 0, str(j["crescimento_gb_dia"]))
        # ---- API e permissões ----
        ver("leitura vê as informações; sem login 401", le.get("/api/qnap").status_code == 200 and anon.get("/api/qnap").status_code == 401)
        ver("só admin pede coleta agora (leitura 403)", le.post("/api/qnap/coletar").status_code == 403)
        r = adm.post("/api/qnap/coletar"); ver("admin pede coleta e ela roda em segundo plano", r.status_code == 200 and (r.json().get("iniciada") or r.json().get("ja_em_andamento")), r.text[:80])
        for _ in range(40):
            if not qc.em_andamento(): break
            _t.sleep(0.25)
        _j2 = adm.get("/api/qnap").json(); ver("depois da coleta o snapshot novo aparece (idade pequena)", (_j2["idade_s"] if _j2["idade_s"] is not None else 999) < 30, f"idade={_j2['idade_s']} coleta={str(_j2['coleta'])[:150]}")
        # ---- /api/estacoes lê o guardado e NÃO varre o QNAP ----
        def proibido(*a, **k): raise AssertionError("varreu o QNAP dentro da requisição")
        qc._lotes = proibido
        e = adm.get("/api/estacoes")
        ver("/api/estacoes responde SEM varrer o QNAP (usa o guardado)", e.status_code == 200 and "pipeline" in e.json(), f"HTTP {e.status_code} {e.text[:80]}")
        for l in res: print(l)
    elif modo == "hoje":
        init_db(); aplicar_migracoes()
        import json as _j
        from app import auth
        import app.qnap_coletor as qc
        from fastapi.testclient import TestClient
        from app.main import app
        c = connect()
        for f in ("F091", "F092", "F093"): c.execute("INSERT INTO fundo (codigo,titulo,sigla,ativo) VALUES (?,?,?,1)", (f, f"Fundo {f}", "T" + f[-2:]))
        def proj(f, n, aut=0, teste=0, wid=None, st="nao_publicado"):
            cod = f"{f}-P000{n}"; c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (f, n))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,autorizado_site,lote_teste,tainacan_item_id,status_site) VALUES (?,?,?,?,1970,?,?,?,?)", (cod, f, n, f"Casa {cod}", aut, teste, wid, st)); return cod
        for n in (1, 2, 3): proj("F091", n)                       # F091: sem direitos, segura 3 projetos
        proj("F092", 1, aut=1, wid=700); proj("F092", 2)           # F092: direitos ok; P1 pronto, P2 sem autorização
        proj("F093", 1, aut=1, teste=1, wid=701)                   # F093: autorizado, mas é lote de teste -> NÃO está pronto
        proj("F093", 2, aut=1, wid=702, st="no_ar")                # já publicado: não conta
        for w in (700, 701, 702): c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo) VALUES (?,8007,'draft','x')", (w,))
        for f in ("F092", "F093"): c.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES (?, 'autorizado','Fam','Termo')", (f,))
        # eventos: 3 folhas hoje (uma com 2 eventos), 1 ontem; 1 publicação hoje
        for cod, q in (("F092-P0001-1970-S01-D00001", "now"), ("F092-P0001-1970-S01-D00001", "now"), ("F092-P0001-1970-S01-D00002", "now"), ("F092-P0001-1970-S01-D00003", "now"), ("F092-P0001-1970-S01-D00009", "-1 days")):
            c.execute("INSERT INTO evento (entidade,codigo,tipo,ator,quando) VALUES ('item',?,'editado','x',datetime('now',?))", (cod, "+0 days" if q == "now" else q))
        c.execute("INSERT INTO evento (entidade,codigo,tipo,ator) VALUES ('projeto','F093-P0002','site_publicar','x')")
        c.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,situacao) VALUES ('aviso','outro','operador','F092-P0001','erro de hoje','aberto')")
        for campo, ent, cod in (("sem_codigo", "item", "9001"), ("sem_codigo", "item", "9002"), ("sem_itens_no_site", "fundo", "F091"), ("publicado_em_fundo_fora_do_ar", "item", "F092-P0001-1970-S01-D00001"), ("campo_novo_desconhecido", "item", "X")):
            c.execute("INSERT INTO divergencia_site (entidade,codigo,campo,valor_painel,valor_site) VALUES (?,?,?,?,?)", (ent, cod, campo, "p", "s"))
        c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,documento_url,thumb_url) VALUES (8001,8013,'draft','sem imagem 1',NULL,NULL),(8002,8013,'draft','sem imagem 2','','')")
        c.execute("INSERT INTO qnap_snapshot (montado,total_gb,livre_gb,parados,entrada_bruta,prontos) VALUES (1, 1255, 28, 2, 5, 3)")
        c.commit(); c.close()
        for em, nome, papel in (("adm@camp.arq.br", "A", "admin"), ("le@camp.arq.br", "L", "leitura")): auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        adm, le, anon = cli("adm@camp.arq.br"), cli("le@camp.arq.br"), TestClient(app, raise_server_exceptions=False)
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        # ---- níveis de espaço: UMA regra ----
        k = connect(); nv = lambda t, l: qc.nivel_espaco(k, t, l)[0]
        ver("espaço: 28 GB de 1.255 (2,2%) = CRÍTICO (o caso real do painel)", nv(1255, 28) == "critico")
        ver("espaço: 150 GB de 1.255 (11,9%) = aviso", nv(1255, 150) == "aviso")
        ver("espaço: 700 GB de 1.255 = ok", nv(1255, 700) == "ok")
        ver("espaço: 49 GB livres é crítico mesmo num volume enorme (limite em GB)", nv(100000, 49) == "critico" and nv(100000, 10000) == "aviso" and nv(100000, 4000) == "critico")
        ver("espaço: sem medida não inventa nível", nv(None, None) is None and nv(0, 0) is None); k.close()
        j = adm.get("/api/qnap").json(); ver("/api/qnap traz o nível e o % livre", j["nivel_espaco"] == "critico" and j["livre_pct"] == 2.2, str((j["nivel_espaco"], j["livre_pct"])))
        ver("/api/estacoes também (é o que o banner lê)", adm.get("/api/estacoes").json()["qnap"]["nivel_espaco"] == "critico")
        # ---- /api/hoje ----
        r = le.get("/api/hoje"); h = r.json()
        ver("leitura vê o topo do painel (200); sem login 401", r.status_code == 200 and anon.get("/api/hoje").status_code == 401, f"HTTP {r.status_code}")
        ver("travados por direitos: 1 fundo (F091) que segura 3 projetos", h["kpis"]["travados"] == {"fundos": 1, "projetos": 3} and h["publicacao"]["fundos_travados"][0]["codigo"] == "F091", str(h["kpis"]["travados"]))
        ver("prontos para publicar: SÓ 1 (lote de teste e já publicado não contam), com 3 autorizados no total", h["kpis"]["prontos"] == {"valor": 1, "autorizados": 3}, str(h["kpis"]["prontos"]))
        ver("a ação 'autorizar' lista F092 com 1 projeto sem autorização", [(f["codigo"], f["nao_autorizados"]) for f in h["publicacao"]["fundos_para_autorizar"]] == [("F092", 1)], str(h["publicacao"]["fundos_para_autorizar"]))
        ver("folhas trabalhadas: 3 hoje (a mesma folha com 2 eventos conta UMA vez) e 1 ontem", h["hoje"]["folhas"] == {"hoje": 3, "ontem": 1}, str(h["hoje"]["folhas"]))
        ver("publicações hoje: 1; projetos novos hoje: os 7 criados agora", h["hoje"]["publicacoes"]["hoje"] == 1 and h["hoje"]["projetos_novos"]["hoje"] == 7, str(h["hoje"]))
        ver("pedidos e erros novos hoje: conta o erro de hoje (2 parâmetros no SQL)", h["hoje"]["pedidos_e_erros"]["hoje"] == 1, str(h["hoje"]["pedidos_e_erros"]))
        ids = [a["id"] for a in h["acoes"]]
        ver("ordem das ações: QNAP crítico, publicar pronto, direitos, autorizar, paradas, sem imagem, divergências", ids == ["qnap_espaco", "publicar", "direitos_F091", "autorizar_F092", "parados", "sem_imagem", "divergencias"], str(ids))
        ver("a ação do QNAP diz o espaço em GB e %", h["acoes"][0]["detalhe"] == "28 GB livres (2,2%)", h["acoes"][0]["detalhe"])
        ver("as ações de fundo levam à página do fundo", next(a for a in h["acoes"] if a["id"] == "direitos_F091")["rota"] == "fundo/F091" and next(a for a in h["acoes"] if a["id"] == "direitos_F091")["impacto"] == 3)
        ver("folhas do site sem imagem: 2 (NULL e vazio contam)", next(a for a in h["acoes"] if a["id"] == "sem_imagem")["impacto"] == 2)
        # ---- divergências em português ----
        d = le.get("/api/site/divergencias/resumo").json()
        titulos = {g["titulo"]: g["n"] for g in d["grupos"]}
        ver("divergências: total 5, agrupadas e com título em português", d["total"] == 5 and titulos.get("Item do site sem código CAMP") == 2 and titulos.get("Fundo sem nenhuma folha no site") == 1, str(titulos))
        ver("divergência 'publicado em fundo despublicado' explicada sem o código cru", "Público no site, mas o fundo está despublicado no painel" in titulos and not any("_" in t for t in titulos), str(list(titulos)))
        ver("tipo desconhecido não quebra: vira 'Outra divergência'", titulos.get("Outra divergência") == 1)
        ver("cada grupo traz a explicação e os itens (código e valores)", all(g["explicacao"] and g["itens"] for g in d["grupos"]))
        ver("o topo resume as divergências por tipo", h["divergencias"]["total"] == 5 and h["divergencias"]["tipos"][0]["n"] == 2)
        for l in res: print(l)
    elif modo == "campvision":
        init_db(); aplicar_migracoes()
        import json as _j, shutil as _sh
        from pathlib import Path as _P
        from app import auth
        from fastapi.testclient import TestClient
        from app.main import app
        base = _P(os.environ["CAMP_DB_PATH"]).parent / "cv_fake"; _sh.rmtree(base, ignore_errors=True)
        entrada = base / "Arquivos" / "100 - Scanners"; prontos = base / "Fundos e Escritorios" / "ACERVOS_CAMP"
        pd = prontos / "F099 - Fundo de teste" / "01 - Projetos"; entrada.mkdir(parents=True)
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F099','Fundo de teste','TST',1)")
        for n in (1, 2, 3, 4, 7):
            c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F099',?)", (n,))
            c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,?,?,?,1970)", (f"F099-P{n:04d}", "F099", n, f"Casa {n}"))
        for k, v in (("qnap.raiz", str(base)), ("qnap.entrada_captura", str(entrada)), ("qnap.prontos_raiz", str(prontos))): c.execute("UPDATE configuracao SET valor=? WHERE chave=?", (v, k))
        c.commit(); c.close()
        def lote(pasta, info=None, status=None, imgs=(), bruto_info=None):
            d = pd / pasta; d.mkdir(parents=True, exist_ok=True)
            if info is not None: (d / "info_projeto.json").write_text(_j.dumps(info))
            if bruto_info is not None: (d / "info_projeto.json").write_text(bruto_info)
            if status is not None: (d / "status.json").write_text(_j.dumps(status))
            for sub, nome in imgs: (d / sub).mkdir(exist_ok=True); (d / sub / nome).write_bytes(b"x")
            return d
        base_info = lambda cod, **k: {"codigo": cod, "nome": f"Casa {cod}", "folhas_esperadas": 3, "estacao": "contex1", "tipo_estacao": "contex", "operador": "Beatriz", "operador_email": "b@camp.arq.br", "fundo_codigo": "F099", **k}
        lote("F099-P0001 - Casa 1", base_info("F099-P0001"), {"status": "pronto", "codigo": "F099-P0001"}, [("Plantas", "a.jpg"), ("Plantas", "b.jpg"), ("Fotografias", "c.tif")])
        lote("F099-P0002 - Casa 2", base_info("F099-P0002"), {"status": "processando", "codigo": "F099-P0002"}, [("Plantas", "a.jpg")])
        lote("F099-P0003 - Casa 3", base_info("F099-P0003"), {"status": "erro", "codigo": "F099-P0003", "mensagem": "OCR falhou"}, [])
        lote("F099-P0004 - Casa 4", None, {"status": "campvision_concluido"}, [("Plantas", "a.jpg")])      # legado: sem info, código pelo NOME da pasta
        lote("F099-P0007 - Casa 7", base_info("F099-P0007"), {"status": "valor_estranho", "codigo": "F099-P0007"}, [("Plantas", "a.jpg")])
        lote("F099-P0001 - Teste", base_info("F099-P0001", teste=True), {"status": "pronto"}, [])
        lote("F099-P0096 - Fora do painel", base_info("F099-P0096"), {"status": "pronto"}, [])
        lote("Sem Codigo Nenhum", {"nome": "x"}, {"status": "pronto"}, [])
        lote("F099-P0005 - JSON quebrado", None, None, [], bruto_info="{nao e json")
        for em, nome, papel in (("op@camp.arq.br", "Op", "operador"), ("adm@camp.arq.br", "Adm", "admin")): auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        def com_ip(ip):   # fixa o IP de origem da requisição (a versão do Starlette instalada não aceita client=)
            async def asgi(scope, receive, send):
                if scope["type"] == "http": scope = {**scope, "client": (ip, 50000)}
                await app(scope, receive, send)
            return TestClient(asgi, raise_server_exceptions=False)
        op, adm = cli("op@camp.arq.br"), cli("adm@camp.arq.br")
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        def etapas():
            k = connect(); r = {x[0].rsplit("/", 1)[-1].split(" - ")[0]: (x[1], x[2], x[3]) for x in k.execute("SELECT pasta_qnap, etapa, folhas_encontradas, folhas_esperadas FROM lista_processamento")}; k.close(); return r
        r = op.post("/api/filas/varrer-qnap").json()
        ver("varredura: 5 lotes entram (pronto, processando, erro, legado e status desconhecido)", r["novas"] == 5, str({k: r[k] for k in ("novas", "processando", "com_erro")}))
        e = etapas()
        ver("status 'pronto' vai para REVISÃO, com as 3 imagens contadas nas subpastas e as 3 esperadas", e["F099-P0001"] == ("revisao", 3, 3), str(e.get("F099-P0001")))
        ver("status 'processando' fica em PROCESSANDO (não pede revisão)", e["F099-P0002"][0] == "processando" and r["processando"] == 1, str(e.get("F099-P0002")))
        ver("status 'erro' fica em ERRO", e["F099-P0003"][0] == "erro" and r["com_erro"] == 1, str(e.get("F099-P0003")))
        ver("legado: sem info_projeto.json e status 'campvision_concluido' = pronto; o código vem do NOME da pasta", e["F099-P0004"][0] == "revisao", str(e.get("F099-P0004")))
        ver("status desconhecido: entra como pronto e gera AVISO", e["F099-P0007"][0] == "revisao" and len(r["avisos"]) == 1 and "valor_estranho" in r["avisos"][0]["motivo"], str(r["avisos"]))
        motivos = " | ".join(i["motivo"] for i in r["ignoradas"])
        ver("ignorados com motivo: teste=true, código que o painel não conhece, sem código e JSON inválido", len(r["ignoradas"]) == 4 and "lote de teste" in motivos and "sem código de projeto reconhecido" in motivos and "manifesto inválido" in motivos, motivos[:200])
        k = connect(); ctx = _j.loads(k.execute("SELECT resultado FROM lista_processamento WHERE projeto_codigo='F099-P0001'").fetchone()[0]); evs = {x[0] for x in k.execute("SELECT tipo FROM evento WHERE ator='campvision2'")}; k.close()
        ver("o contexto do operador/estação é guardado (estacao, operador, e-mail, fundo)", ctx["estacao"] == "contex1" and ctx["operador"] == "Beatriz" and ctx["operador_email"] == "b@camp.arq.br" and ctx["fundo_codigo"] == "F099", str({k_: ctx.get(k_) for k_ in ("estacao", "operador", "fundo_codigo")}))
        ver("a auditoria registra pronto, processando e erro", {"material_pronto", "material_processando", "material_com_erro"} <= evs, str(evs))
        ver("varrer de novo é idempotente (0 novas)", op.post("/api/filas/varrer-qnap").json()["novas"] == 0)
        (pd / "F099-P0002 - Casa 2" / "status.json").write_text(_j.dumps({"status": "pronto", "codigo": "F099-P0002"}))
        r2 = op.post("/api/filas/varrer-qnap").json()
        ver("processando -> pronto: o lote passa para REVISÃO", r2["atualizadas"] == 1 and etapas()["F099-P0002"][0] == "revisao", str(r2["atualizadas"]))
        k = connect(); k.execute("UPDATE lista_processamento SET etapa='publicado' WHERE projeto_codigo='F099-P0001'"); k.commit(); k.close()
        (pd / "F099-P0001 - Casa 1" / "status.json").write_text(_j.dumps({"status": "processando", "codigo": "F099-P0001"})); op.post("/api/filas/varrer-qnap")
        ver("lote JÁ PUBLICADO nunca regride, mesmo que o CV2 mande 'processando' de novo", etapas()["F099-P0001"][0] == "publicado")
        # entrada bruta nunca vira lote, mesmo se a raiz final contiver a entrada
        k = connect(); k.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(base),)); k.commit(); k.close()
        (entrada / "F099-P0001 - Casa 1").mkdir(); (entrada / "F099-P0001 - Casa 1" / "status.json").write_text(_j.dumps({"status": "pronto", "codigo": "F099-P0001"}))
        op.post("/api/filas/varrer-qnap"); k = connect(); n_ent = k.execute("SELECT count(*) FROM lista_processamento WHERE pasta_qnap LIKE '%100 - Scanners%'").fetchone()[0]; k.close()
        ver("a ENTRADA bruta (100 - Scanners) nunca vira lote, mesmo dentro da raiz varrida", n_ent == 0, str(n_ent))
        # ---------------- HTTP das estações (rede local) ----------------
        lan = com_ip("192.168.15.40"); fora = com_ip("8.8.8.8")
        hb = {"estacao_id": "campvision2", "tipo_estacao": "campvision", "app": "campvision-new", "versao": "2.0.0", "hostname": "campvision", "ip_local": "192.168.15.40", "estado": "processando", "fundo_codigo": "F099", "projeto_codigo": "F099-P0002"}
        r = lan.post("/api/estacoes/heartbeat", json=hb); ver("heartbeat do CAMP Vision (tipo 'campvision', estado 'processando') é aceito", r.status_code == 200 and r.json()["estado"] == "processando", f"HTTP {r.status_code} {r.text[:80]}")
        ver("heartbeat com tipo ou estado inválido: 400", lan.post("/api/estacoes/heartbeat", json={**hb, "tipo_estacao": "xyz"}).status_code == 400 and lan.post("/api/estacoes/heartbeat", json={**hb, "estado": "dormindo"}).status_code == 400)
        ver("de fora da rede local: 403", fora.post("/api/estacoes/heartbeat", json=hb).status_code == 403)
        cv = next(m for m in adm.get("/api/estacoes").json()["maquinas"] if m["nome"] == "CAMP Vision 2")
        ver("em Estações o CAMP Vision 2 mostra o app online e o estado (estacao_id 'campvision2')", cv["estacao_id"] == "campvision2" and cv["app_online"] is True and cv["app_estado"] == "processando" and cv["app_projeto"] == "F099-P0002", str({k_: cv.get(k_) for k_ in ("estacao_id", "app_online", "app_estado")}))
        k = connect(); k.execute("UPDATE configuracao SET valor='segredo-cv' WHERE chave='estacao.token'"); k.commit(); k.close()
        ver("com token configurado: sem o cabeçalho = 401; com X-Camp-Token certo = 200", lan.post("/api/estacoes/heartbeat", json=hb).status_code == 401 and lan.post("/api/estacoes/heartbeat", json=hb, headers={"X-Camp-Token": "segredo-cv"}).status_code == 200 and lan.post("/api/estacoes/heartbeat", json=hb, headers={"X-Camp-Token": "errado"}).status_code == 401)
        T = {"X-Camp-Token": "segredo-cv"}
        ctx = lan.get("/api/estacoes/contexto", headers=T).json()
        f99 = next((f for f in ctx["fundos"] if f["codigo_fundo"] == "F099"), {})
        ver("/contexto: cada fundo traz codigo_fundo, prefixo, nome, ultimo_projeto, proximo_projeto (F099: último P0007, próximo P0008)", {"codigo_fundo", "prefixo", "nome", "ultimo_projeto", "proximo_projeto"} <= set(f99) and f99.get("ultimo_projeto") == "P0007" and f99.get("proximo_projeto") == "P0008", str(f99))
        cf = lan.get("/api/estacoes/contexto?fundo=F099", headers=T).json()
        ver("/contexto?fundo=: traz também os projetos (codigo, numero_projeto, projeto, ano, cidade, identificacao_original)", {"codigo", "numero_projeto", "projeto", "ano", "cidade", "identificacao_original"} <= set(cf["projetos"][0]) and len(cf["projetos"]) == 5, str(cf["projetos"][0]))
        chave = "a" * 32; corpo = {"fundo_codigo": "F099", "titulo": "Casa Nova", "ano": 1975, "cidade": "Campinas/SP", "operador": "Beatriz", "chave_reserva": chave}
        a = lan.post("/api/estacoes/projetos/reservar", json=corpo, headers=T); b = lan.post("/api/estacoes/projetos/reservar", json=corpo, headers=T)
        ver("/reservar devolve codigo, numero_projeto, fundo_codigo, titulo, ano, cidade, identificacao_original", a.status_code == 200 and {"codigo", "numero_projeto", "fundo_codigo", "titulo", "ano", "cidade", "identificacao_original"} <= set(a.json()) and a.json()["codigo"] == "F099-P0008", a.text[:160])
        ver("repetir a reserva com a MESMA chave devolve o MESMO projeto (não duplica)", b.json()["codigo"] == a.json()["codigo"])
        c3 = lan.post("/api/estacoes/projetos/reservar", json={**corpo, "chave_reserva": "b" * 32}, headers=T)
        ver("outra chave = próximo número (P0009)", c3.json()["codigo"] == "F099-P0009", c3.text[:100])
        ver("/reservar sem título: 400; fundo inexistente: 404", lan.post("/api/estacoes/projetos/reservar", json={**corpo, "titulo": " ", "chave_reserva": "c" * 32}, headers=T).status_code == 400 and lan.post("/api/estacoes/projetos/reservar", json={**corpo, "fundo_codigo": "F000", "chave_reserva": "d" * 32}, headers=T).status_code in (400, 404))
        for l in res: print(l)
    elif modo == "sondagem":
        import json as _j, threading as _th, httpx
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from app.sondagem_fluentforms import sondar
        CAMPOS = {"fields": [
            {"element": "input_name", "attributes": {"name": "names", "type": "text"}, "settings": {"label": "Nome completo", "validation_rules": {"required": {"value": True}}}},
            {"element": "input_email", "attributes": {"name": "email", "type": "email"}, "settings": {"label": "E-mail", "validation_rules": {"required": {"value": True}}}},
            {"element": "container", "columns": [{"fields": [
                {"element": "input_hidden", "attributes": {"name": "codigo_material", "type": "hidden"}, "settings": {"label": "Código do material"}},
                {"element": "select", "attributes": {"name": "uso_pretendido"}, "settings": {"label": "Uso pretendido"}}]}]}]}
        ENTRADAS = [{"id": i, "created_at": f"2026-09-{1 + i:02d} 10:00:00",
                     "response": _j.dumps({"names": "Ana Souza", "email": "ana.souza@exemplo.com", "telefone": "11999990000",
                                           "codigo_material": "F002-P0002-1977-S01-D0000%d" % i if i < 8 else "",
                                           "uso_pretendido": ["Pesquisa", "Publicação", "Exposição"][i % 3]})} for i in range(12)]
        def servidor(rotas):
            vistos = []
            class H(BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def do_GET(self):
                    vistos.append(("GET", self.path.split("?")[0]))
                    st, corpo = rotas.get(self.path.split("?")[0], (404, {"code": "rest_no_route"}))
                    self.send_response(st); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(_j.dumps(corpo).encode())
                def do_POST(self): vistos.append(("POST", self.path)); self.send_response(405); self.end_headers()
                do_PUT = do_DELETE = do_PATCH = do_POST
            srv = ThreadingHTTPServer(("127.0.0.1", 0), H); _th.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, vistos, httpx.Client(base_url=f"http://127.0.0.1:{srv.server_port}")
        base = {"/wp-json/": (200, {"namespaces": ["wp/v2", "fluentform/v1"], "routes": {"/fluentform/v1/forms": {}, "/fluentform/v1/submissions": {}}}),
                "/wp-json/fluentform/v1/forms": (200, {"data": [{"id": 7, "title": "Cadastro para download de material — CAMP", "status": "published"}, {"id": 5, "title": "Contato — CAMP", "status": "published"}]}),
                "/wp-json/fluentform/v1/forms/7": (200, {"id": 7, "form_fields": _j.dumps(CAMPOS)}),
                "/wp-json/fluentform/v1/forms/7/settings": (200, {"confirmation": {"redirectTo": "customUrl", "customUrl": "https://camp.arq.br/wp-content/uploads/2026/foto.jpg"}}),
                "/wp-json/fluentform/v1/submissions": (200, {"submissions": {"data": ENTRADAS, "total": 40}})}
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        srv, vistos, h = servidor(base); txt = "\n".join(sondar(h)); srv.shutdown()
        ver("acha o formulário de download pelo título e o id", "Cadastro para download de material" in txt and "id 7" in txt, txt[:200])
        ver("lê os campos, inclusive dentro de colunas, com rótulo, tipo e obrigatório", "names «Nome completo» (input_name, obrigatório)" in txt and "uso_pretendido" in txt, txt[200:500])
        ver("aponta o campo oculto do material como candidato a identificar o material", "codigo_material «Código do material»" in txt)
        ver("diz quantas entradas existem e o período", "40 no total; analisadas as 12 mais recentes" in txt and "2026-09-01 a 2026-09-12" in txt, txt[txt.find("entradas:"):][:140])
        ver("mede o preenchimento do campo do material (8 de 12, todos no formato Fxxx-Pxxxx)", "preenchido em 8 de 12 entradas; 8 com código CAMP" in txt)
        ver("agrega o 'uso pretendido' em categorias (lista de opções)", "Pesquisa=4" in txt and "Publicação=4" in txt and "Exposição=4" in txt)
        ver("detecta que a confirmação leva a um arquivo PÚBLICO (não dá para saber quem baixou)", "ENDEREÇO PÚBLICO" in txt.upper() or "endereço PÚBLICO" in txt, txt[-400:])
        ver("PRIVACIDADE: não imprime nome, e-mail nem telefone das pessoas", all(x not in txt for x in ("Ana", "Souza", "ana.souza", "@exemplo", "11999990000")))
        ver("só faz GET (nenhuma escrita no site)", vistos and all(m == "GET" for m, _ in vistos), str(set(m for m, _ in vistos)))
        sem = dict(base); sem["/wp-json/"] = (200, {"namespaces": ["wp/v2"], "routes": {}})
        srv, _, h = servidor(sem); t2 = "\n".join(sondar(h)); srv.shutdown()
        ver("plugin sem REST: diz com clareza e propõe alternativas", "NÃO aparece" in t2 and "webhook" in t2)
        proib = dict(base); proib["/wp-json/fluentform/v1/forms"] = (403, {"code": "rest_forbidden"})
        srv, _, h = servidor(proib); t3 = "\n".join(sondar(h)); srv.shutdown()
        ver("sem permissão (403): explica que o usuário precisa ser administrador do Fluent Forms", "403" in t3 and "administrador" in t3)
        sem_campo = dict(base); sem_campo["/wp-json/fluentform/v1/forms/7"] = (200, {"form_fields": _j.dumps({"fields": [CAMPOS["fields"][0]]})})
        srv, _, h = servidor(sem_campo); t4 = "\n".join(sondar(h)); srv.shutdown()
        ver("formulário SEM campo do material: a conclusão manda criar o campo oculto", "NENHUM" in t4 and "NÃO registra qual material" in t4)
        fora = httpx.Client(base_url="http://127.0.0.1:9", timeout=2); t5 = "\n".join(sondar(fora))
        ver("site fora do ar: mensagem clara, sem exceção", "não consegui ler a API" in t5, t5[:160])
        for l in res: print(l)
    elif modo == "uso":
        init_db(); aplicar_migracoes()
        import csv as _csv, io as _io, json as _j, threading as _th, httpx
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlparse, parse_qs
        from app import auth, rotas_uso, uso_formularios as uf
        from fastapi.testclient import TestClient
        from app.main import app
        res = []
        def ver(nome, cond, det=""): res.append(f"{'ok' if cond else 'FALHA'}|{nome}|{det}")
        # ---------- derivar ----------
        d = uf.derivar({"names": {"first_name": "Ana", "last_name": "Souza"}, "email": "Ana@Exemplo.COM", "phone": "11 99999-0000", "universidade_empresa": "USP",
                        "uso_pretendido": "Pesquisa", "codigo_material": "f002-p0002-1977-s01-d00001"})
        ver("derivar: nome composto, e-mail em minúsculas, telefone, instituição, uso e material pelo campo", (d["nome"], d["email"], d["telefone"], d["instituicao"], d["uso"]) == ("Ana Souza", "ana@exemplo.com", "11 99999-0000", "USP", "Pesquisa")
            and (d["material_codigo"], d["material_origem"], d["projeto_codigo"], d["fundo_codigo"]) == ("F002-P0002-1977-S01-D00001", "campo", "F002-P0002", "F002"), str(d))
        ver("derivar: sem campo do material, acha um código em qualquer valor", uf.derivar({"mensagem": "quero F002-P0002 por favor"})["material_origem"] == "valor")
        ver("derivar: sem nada, usa o endereço da ficha de onde o modal foi aberto", uf.derivar({}, "https://camp.arq.br/acervo/f003-p0005-1960-s01-d00002/")["material_codigo"] == "F003-P0005-1960-S01-D00002")
        ver("derivar: sem código em lugar nenhum = sem material (não inventa)", uf.derivar({"x": "y"}, "https://camp.arq.br/")["material_codigo"] is None)
        ver("derivar: e-mail em campo de outro nome é achado; texto inválido no campo e-mail não vira e-mail", uf.derivar({"contato": "b@x.org"})["email"] == "b@x.org" and uf.derivar({"email": "não sei"})["email"] is None)
        # ---------- WordPress de mentira ----------
        ESTADO = {"max": 250, "ignora_pagina": False, "forms": (200, None)}
        def entrada(i):
            n = i % 40
            return {"id": i, "created_at": f"2026-09-{(i % 28) + 1:02d} 10:00:00", "status": "trashed" if i == 7 else "spam" if i == 8 else "unread",
                    "source_url": f"https://camp.arq.br/acervo/f098-p0001-1977-s01-d0000{1 + i % 3}/" if i % 10 == 0 else None,
                    "response": _j.dumps({"names": f"Pessoa {n}", "email": f"Pessoa{n}@Exemplo.com", "phone": f"1190000{n:04d}", "universidade_empresa": f"Uni {n % 5}",
                                          "uso_pretendido": ["Pesquisa", "Publicação", "Exposição", "Família"][i % 4],
                                          "codigo_material": f"F098-P0001-1977-S01-D{(i % 6) + 1:05d}" if i % 5 else ""})}
        def ff(path, q):
            if path == "/wp-json/fluentform/v1/forms":
                return ESTADO["forms"] if ESTADO["forms"][1] else (200, {"data": [{"id": 3, "title": "Cadastro para download de material — CAMP"}, {"id": 5, "title": "Contato — CAMP"}]})
            if path == "/wp-json/fluentform/v1/submissions":
                pg = 1 if ESTADO["ignora_pagina"] else int(q.get("page", 1)); por = int(q.get("per_page", 10))
                ids = list(range(ESTADO["max"], 0, -1))[(pg - 1) * por: pg * por]
                return 200, {"submissions": {"data": [entrada(i) for i in ids], "total": ESTADO["max"]}}
            return 404, {"code": "rest_no_route"}
        def servidor(fn):
            vistos = []
            class H(BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def do_GET(self):
                    u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; vistos.append(("GET", u.path))
                    st, corpo = fn(u.path, q); self.send_response(st); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(_j.dumps(corpo).encode())
                def do_POST(self): vistos.append(("POST", self.path)); self.send_response(405); self.end_headers()
                do_PUT = do_DELETE = do_PATCH = do_POST
            srv = ThreadingHTTPServer(("127.0.0.1", 0), H); _th.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, vistos, httpx.Client(base_url=f"http://127.0.0.1:{srv.server_port}")
        srv, vistos, h = servidor(ff)
        c = connect()
        c.execute("INSERT INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F098','Fundo de teste','TST',1)"); c.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES ('F098',1)")
        c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES ('F098-P0001','F098',1,'Casa de teste',1977)"); c.commit()
        subm = lambda: sum(1 for m, p_ in vistos if p_.endswith("/submissions"))
        validas = [i for i in range(1, 251) if i not in (7, 8)]
        # ---------- coleta ----------
        r = uf.puxar(h, c, completo=True)
        ver("coleta COMPLETA: lê as 250 entradas em 3 páginas, grava 248 e pula a lixeira e o spam", (r["lidas"], r["novas"], r["puladas"], r["total_remoto"], subm()) == (250, 248, 2, 250, 3) and not r["erro"], str(r))
        ver("acha o formulário de download pelo título", r["form_id"] == 3 and "download" in (r["form_titulo"] or ""))
        n0 = subm(); r2 = uf.puxar(h, c)
        ver("coleta INCREMENTAL sem novidade: 0 novas e UMA só página lida", (r2["novas"], subm() - n0) == (0, 1), str((r2["novas"], subm() - n0)))
        ESTADO["max"] = 252; n0 = subm(); r3 = uf.puxar(h, c)
        ver("duas entradas novas: traz as 2 e para na página seguinte (já conhecida)", (r3["novas"], subm() - n0) == (2, 2), str((r3["novas"], subm() - n0)))
        c.execute("DELETE FROM uso_download"); c.commit(); ESTADO["ignora_pagina"] = True; n0 = subm(); r4 = uf.puxar(h, c, completo=True)
        ver("servidor que ignora o número da página: não entra em laço (para sem entradas novas)", subm() - n0 <= 3 and r4["novas"] == 100, str((subm() - n0, r4["novas"])))
        ESTADO["ignora_pagina"] = False; c.execute("DELETE FROM uso_download"); c.commit(); uf.puxar(h, c, completo=True)
        ESTADO["forms"] = (403, {"code": "rest_forbidden"}); r5 = uf.puxar(h, c)
        ver("sem permissão (403): o erro fica claro e registrado", "403" in (r5["erro"] or "") and "administrador" in r5["erro"], str(r5["erro"]))
        ESTADO["forms"] = (200, None); fora = httpx.Client(base_url="http://127.0.0.1:9", timeout=2); r6 = uf.puxar(fora, c)
        ver("site fora do ar: erro registrado, sem exceção", bool(r6["erro"]) and r6["novas"] == 0, str(r6["erro"]))
        ver("cada coleta fica registrada (diagnóstico), inclusive as com erro", c.execute("SELECT COUNT(*) FROM uso_coleta").fetchone()[0] >= 7 and c.execute("SELECT COUNT(*) FROM uso_coleta WHERE erro IS NOT NULL").fetchone()[0] >= 2)
        ver("só GET no site (nenhuma escrita)", all(m == "GET" for m, _ in vistos))
        ver("não guarda IP nem agente do navegador (minimização)", not any(k in [x[1] for x in c.execute("PRAGMA table_info(uso_download)")] for k in ("ip", "user_agent", "browser")))
        total = c.execute("SELECT COUNT(*) FROM uso_download").fetchone()[0]; sem_mat = c.execute("SELECT COUNT(*) FROM uso_download WHERE material_codigo IS NULL").fetchone()[0]
        c.close()
        # ---------- rotas (só admin) ----------
        rotas_uso._wp_http = lambda: h
        for em, nome, papel in (("adm@camp.arq.br", "Adm", "admin"), ("op@camp.arq.br", "Op", "operador")): auth.criar_usuario(nome, em, "senha-longa-12345", papel, forcar_troca=False)
        def cli(em):
            x = TestClient(app, raise_server_exceptions=False); x.post("/api/auth/login", json={"email": em, "senha": "senha-longa-12345"}); return x
        adm, op, anon = cli("adm@camp.arq.br"), cli("op@camp.arq.br"), TestClient(app, raise_server_exceptions=False)
        rotas = ["/api/uso", "/api/uso/pessoas", "/api/uso/materiais", "/api/uso/resumo", "/api/uso/exportar.csv", "/api/uso/1"]
        ver("sem login: 401 em todas; operador: 403 em todas (dados pessoais)", all(anon.get(r_).status_code == 401 for r_ in rotas) and all(op.get(r_).status_code == 403 for r_ in rotas) and op.post("/api/uso/puxar", json={}).status_code == 403 and op.post("/api/uso/anonimizar", json={"email": "a@b.co"}).status_code == 403)
        L = adm.get("/api/uso").json(); k = connect()
        sql = lambda q_, *a: k.execute(q_, a).fetchone()[0]
        ver("lista: total igual ao do banco, 50 por página, ordenada da mais recente; SEM telefone na lista", L["total"] == total and len(L["itens"]) == 50 and "telefone" not in L["itens"][0] and L["itens"][0]["recebida_em"] >= L["itens"][-1]["recebida_em"], str((L["total"], total)))
        ver("paginação: a página 2 traz outras 50; por_pagina é limitado a 200", adm.get("/api/uso?pagina=2").json()["itens"][0]["id"] != L["itens"][0]["id"] and len(adm.get("/api/uso?por_pagina=1000").json()["itens"]) == 200)
        ver("filtro por texto (e-mail, sem diferenciar maiúsculas) bate com o banco", adm.get("/api/uso?q=PESSOA3@").json()["total"] == sql("SELECT COUNT(*) FROM uso_download WHERE email LIKE '%pessoa3@%'"))
        ver("filtro por uso declarado bate com o banco", adm.get("/api/uso?uso=Publicação").json()["total"] == sql("SELECT COUNT(*) FROM uso_download WHERE uso='Publicação'"))
        ver("filtro por período bate com o banco", adm.get("/api/uso?de=2026-09-10&ate=2026-09-12").json()["total"] == sql("SELECT COUNT(*) FROM uso_download WHERE date(recebida_em) BETWEEN '2026-09-10' AND '2026-09-12'"))
        mat = sql("SELECT material_codigo FROM uso_download WHERE material_codigo IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1")
        ver("filtro por material bate com o banco e traz o título do projeto", adm.get(f"/api/uso?material={mat}").json()["total"] == sql("SELECT COUNT(*) FROM uso_download WHERE material_codigo=?", mat) and adm.get(f"/api/uso?material={mat}").json()["itens"][0]["material_titulo"] == "Casa de teste")
        P = adm.get("/api/uso/pessoas?por_pagina=200").json()
        ver("por pessoa: 40 pessoas (e-mail em minúsculas), a soma dos downloads fecha com o total", P["total"] == 40 and sum(x["downloads"] for x in P["itens"]) == total and all(x["email"] == x["email"].lower() for x in P["itens"]), str((P["total"], sum(x["downloads"] for x in P["itens"]), total)))
        M = adm.get("/api/uso/materiais?por_pagina=200").json()
        ver("por material: soma fecha com as entradas que têm material; o mais baixado vem primeiro, com título", sum(x["downloads"] for x in M["itens"]) == total - sem_mat and M["itens"][0]["downloads"] >= M["itens"][-1]["downloads"] and M["itens"][0]["titulo"] == "Casa de teste", str((sum(x["downloads"] for x in M["itens"]), total - sem_mat)))
        R = adm.get("/api/uso/resumo").json()
        ver("resumo: totais, pessoas, materiais, sem material e a última coleta", R["total"] == total and R["pessoas"] == 40 and R["sem_material"] == sem_mat and R["materiais"] == M["total"] and R["anonimizadas"] == 0 and R["ultima_coleta"] is not None and any(u_["uso"] == "Pesquisa" for u_ in R["usos"]), str({x: R[x] for x in ("total", "pessoas", "sem_material")}))
        D = adm.get(f"/api/uso/{L['itens'][0]['id']}").json()
        ver("detalhe: traz o telefone e as respostas completas; id inexistente = 404", D["telefone"] and "uso_pretendido" in D["resposta"] and adm.get("/api/uso/999999").status_code == 404)
        E = adm.get("/api/uso/exportar.csv?uso=Pesquisa"); linhas = list(_csv.reader(_io.StringIO(E.text.lstrip("\ufeff")), delimiter=";"))
        ver("CSV: abre no Excel (BOM), traz TODAS as linhas do filtro (não só a página) e o telefone", E.text.startswith("\ufeff") and len(linhas) - 1 == sql("SELECT COUNT(*) FROM uso_download WHERE uso='Pesquisa'") and linhas[0][3] == "telefone" and linhas[1][3] != "" and "csv" in E.headers["content-type"], str((len(linhas) - 1, E.headers["content-type"])))
        ev = k.execute("SELECT detalhe FROM evento WHERE tipo='uso_exportado'").fetchone()
        ver("a exportação fica na auditoria, com a contagem e SEM dados das pessoas", ev is not None and _j.loads(ev[0])["linhas"] == len(linhas) - 1 and "@" not in ev[0].replace("adm@camp.arq.br", ""))
        pu = adm.post("/api/uso/puxar", json={"completo": False}).json()
        ver("botão 'atualizar agora' (POST /puxar) devolve o resumo da coleta", pu["novas"] == 0 and pu["erro"] is None and pu["lidas"] > 0, str(pu))
        # ---------- apagar pessoa (LGPD) ----------
        alvo = "pessoa3@exemplo.com"; n_alvo = sql("SELECT COUNT(*) FROM uso_download WHERE email=?", alvo)
        ver("apagar pessoa: e-mail vazio = 400; e-mail desconhecido = 404", adm.post("/api/uso/anonimizar", json={"email": " "}).status_code == 400 and adm.post("/api/uso/anonimizar", json={"email": "ninguem@x.org"}).status_code == 404)
        a = adm.post("/api/uso/anonimizar", json={"email": "Pessoa3@EXEMPLO.com"}).json()
        ver("apagar pessoa: anonimiza TODAS as entradas dela (qualquer caixa de letra)", a["anonimizadas"] == n_alvo and n_alvo > 0, str(a))
        ver("depois: nome '(removido)', sem e-mail, telefone, instituição nem respostas; o uso e o material ficam", sql("SELECT COUNT(*) FROM uso_download WHERE anonimizada=1") == n_alvo and sql("SELECT COUNT(*) FROM uso_download WHERE anonimizada=1 AND nome='(removido)' AND email IS NULL AND telefone IS NULL AND instituicao IS NULL AND resposta_json IS NULL AND uso IS NOT NULL") == n_alvo)
        ver("a lista e as pessoas deixam de mostrar a pessoa; o total de downloads não muda", alvo not in adm.get("/api/uso?por_pagina=200").text and not any(x["email"] == alvo for x in adm.get("/api/uso/pessoas?por_pagina=200").json()["itens"]) and adm.get("/api/uso").json()["total"] == total)
        ev = k.execute("SELECT detalhe FROM evento WHERE tipo='uso_pessoa_anonimizada'").fetchone()
        ver("a auditoria guarda só uma impressão curta do e-mail, nunca o e-mail", ev is not None and "pessoa3" not in ev[0].lower() and "@" not in ev[0] and _j.loads(ev[0])["registros"] == n_alvo)
        pu = adm.post("/api/uso/puxar", json={"completo": True}).json()
        ver("uma coleta COMPLETA depois NÃO traz de volta a pessoa apagada", pu["novas"] == 0 and sql("SELECT COUNT(*) FROM uso_download WHERE email=?", alvo) == 0, str(pu["novas"]))
        ver("reprocessar refaz as colunas a partir das respostas guardadas, sem ir ao site", adm.post("/api/uso/reprocessar").json()["reprocessadas"] == total - n_alvo)
        k.close(); srv.shutdown()
        for l in res: print(l)
    return 0

if "--filho" in sys.argv:
    sys.exit(filho(sys.argv[2]))

tmp = tempfile.mkdtemp()

print("1) Banco NOVO (schema.sql + todas as migrações, rodando 2x)")
db = f"{tmp}/novo.db"
rc, out = rodar("novo", db)
ok(rc == 0, "sobe sem erro" + ("" if rc == 0 else f" -> {out[-200:]}"))
if rc == 0:
    c = sqlite3.connect(db)
    cols = [r[1] for r in c.execute("PRAGMA table_info(projeto)")]
    ok(cols.count("identificacao_original") == 1, "projeto.identificacao_original existe uma vez")
    nomes = {r[0] for r in c.execute("SELECT nome FROM migracao")}
    ok(len(list((RAIZ / "db/migrations").glob("*.sql"))) == len(nomes), f"todas as {len(nomes)} migrações registradas")
    ok(c.execute("SELECT count(*) FROM sqlite_master WHERE name='estacao_heartbeat'").fetchone()[0] == 1, "tabela estacao_heartbeat existe")

print("2) Banco ANTIGO de produção (b0149ab: schema + migrações 002-010, com dados)")
db = f"{tmp}/antigo.db"
def git(*a): return subprocess.run(["git", "-C", str(RAIZ), *a], capture_output=True, text=True).stdout
schema_antigo = git("show", "b0149ab:db/schema.sql")
if not schema_antigo:
    print("  (b0149ab indisponível neste clone; passo ignorado)")
else:
    c = sqlite3.connect(db); c.executescript(schema_antigo)
    c.execute("CREATE TABLE migracao (nome TEXT PRIMARY KEY, aplicada_em TEXT DEFAULT (datetime('now')))")
    for nome in sorted(l.split("/")[-1] for l in git("ls-tree", "--name-only", "b0149ab", "db/migrations/").split()):
        c.executescript(git("show", f"b0149ab:db/migrations/{nome}")); c.execute("INSERT INTO migracao (nome) VALUES (?)", (nome,))
    c.execute("INSERT INTO fundo (codigo, titulo) VALUES ('F099','Fundo de teste')")
    c.execute("INSERT INTO numero_p (fundo_codigo, numero) VALUES ('F099',1)")
    c.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano) VALUES ('F099-P0001','F099',1,'Casa de teste',1960)")
    for n, jpg in ((1, "16200"), (2, "16202"), (3, "<img src='x'>"), (4, "/mnt/qnap/acervos/a.jpg"), (5, "https://camp.arq.br/u/b.jpg")):
        c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,arquivo_jpg,tainacan_item_id,origem) VALUES (?,?,?,?,?,?,'importado')",
                  (f"F099-P0001-1960-S01-D0000{n}", "F099-P0001", "S01", n, jpg, 9000 + n))
    c.execute("INSERT INTO wp_item (id,colecao_id,documento_url) VALUES (9001,8013,'https://camp.arq.br/u/a-scaled.jpg')")   # só o item 1 tem URL real no espelho
    c.commit(); c.close()
    rc, out = rodar("antigo", db)
    ok(rc == 0, "migra sem erro" + ("" if rc == 0 else f" -> {out[-200:]}"))
    if rc == 0:
        c = sqlite3.connect(db)
        ok(c.execute("SELECT titulo FROM projeto WHERE codigo='F099-P0001'").fetchone()[0] == "Casa de teste", "dados existentes preservados")
        ok("identificacao_original" in [r[1] for r in c.execute("PRAGMA table_info(projeto)")], "coluna identificacao_original adicionada")
        ok(c.execute("SELECT valor FROM configuracao WHERE chave='qnap.ip'").fetchone()[0] == "192.168.15.30", "IP do QNAP preenchido pela migração 023")
        ok(c.execute("SELECT count(*) FROM configuracao WHERE chave='estacao.token'").fetchone()[0] == 1, "chave estacao.token criada")
        jpg = {r[0][-1]: r[1] for r in c.execute("SELECT codigo, arquivo_jpg FROM item ORDER BY codigo")}
        ok(jpg["1"] == "https://camp.arq.br/u/a-scaled.jpg", "migração 028: ID de anexo trocado pelo endereço real quando o espelho tem")
        ok(jpg["2"] is None and jpg["3"] is None, "migração 028: ID sem URL conhecida e HTML viram vazio (a tela usa o documento do site)")
        ok(jpg["4"] == "/mnt/qnap/acervos/a.jpg" and jpg["5"] == "https://camp.arq.br/u/b.jpg", "migração 028: caminho local e URL existentes NÃO são tocados")

print("3) Guarda de rede das rotas sem login")
rc, out = rodar("rede", f"{tmp}/rede.db")
if rc != 0: ok(False, f"teste de rede não rodou -> {out[-300:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = l.split("|"); ok(st == "ok", f"{nome} ({det})")

print("4) Login durante escrita longa do sincronizador (o erro 500 de 02/10)")
rc, out = rodar("lock", f"{tmp}/lock.db")
if rc != 0: ok(False, f"teste de lock não rodou -> {out[-300:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = l.split("|"); ok(st == "ok", f"{nome} ({det})")

print("5) Edição de textos da folha (rota nova, com Tainacan falso)")
rc, out = rodar("edicao", f"{tmp}/edicao.db")
if rc != 0: ok(False, f"teste de edição não rodou -> {out[-600:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("6) Imagens do site (miniatura x documento, sem planta falsa)")
rc, out = rodar("imagens", f"{tmp}/imagens.db")
if rc != 0: ok(False, f"teste de imagens não rodou -> {out[-600:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("7) Importador do site não grava mais ID de anexo como arquivo")
rc, out = rodar("importador", f"{tmp}/importador.db")
if rc != 0: ok(False, f"teste do importador não rodou -> {out[-500:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("8) Sincronização: espelho nunca vazio nem parcial; pendências preservadas")
rc, out = rodar("sync", f"{tmp}/sync.db")
if rc != 0: ok(False, f"teste de sincronização não rodou -> {out[-700:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("9) Backup do banco: consistente, verificado, com retenção e permissões")
rc, out = rodar("backup", f"{tmp}/backup.db")
if rc != 0: ok(False, f"teste de backup não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("10) Importador: prévia fiel (simulação não grava) e execução protegida")
rc, out = rodar("previa", f"{tmp}/previa.db")
if rc != 0: ok(False, f"teste da prévia não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st, nome, det = (l.split("|") + [""])[:3]; ok(st == "ok", f"{nome}" + (f" ({det})" if det and st != "ok" else ""))

print("11) Publicar: checklist, portões, falhas do WordPress, permissões, lote e fundo inteiro")
rc, out = rodar("publicacao", f"{tmp}/publicacao.db")
if rc != 0: ok(False, f"teste de publicação não rodou -> {out[-1100:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det})" if det and st_ != "ok" else ""))

print("12) Folhas só no site: importar no clique e editar como as demais")
rc, out = rodar("adotar", f"{tmp}/adotar.db")
if rc != 0: ok(False, f"teste de importar folhas não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det})" if det and st_ != "ok" else ""))

print("13) Endereço da página pública: o real do site, ou o montado sem cidade/UF")
rc, out = rodar("urlpublica", f"{tmp}/urlpublica.db")
if rc != 0: ok(False, f"teste do endereço público não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("14) Foto de perfil: permissões, validação pelo conteúdo, limite e auditoria")
rc, out = rodar("foto", f"{tmp}/foto.db")
if rc != 0: ok(False, f"teste de foto não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("15) Guia de publicação: checklist vivo do fundo e do arquiteto")
rc, out = rodar("guia", f"{tmp}/guia.db")
if rc != 0: ok(False, f"teste do guia não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("16) Paginação no servidor: projetos e auditoria (sem repetir nem perder linhas)")
rc, out = rodar("paginacao", f"{tmp}/paginacao.db")
if rc != 0: ok(False, f"teste de paginação não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("17) QNAP: coletor em segundo plano, limite de tempo, histórico e tendência")
rc, out = rodar("qnap", f"{tmp}/qnap.db")
if rc != 0: ok(False, f"teste do QNAP não rodou -> {out[-1000:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("18) Topo do painel: níveis de espaço, ações do dia, hoje x ontem e divergências explicadas")
rc, out = rodar("hoje", f"{tmp}/hoje.db")
if rc != 0: ok(False, f"teste do topo do painel não rodou -> {out[-1100:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("19) Contrato com o CAMP Vision 2: lotes, status, heartbeat, token e reserva de projeto")
rc, out = rodar("campvision", f"{tmp}/campvision.db")
if rc != 0: ok(False, f"teste do contrato do CAMP Vision não rodou -> {out[-1100:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("20) Sondagem do Fluent Forms (fase 0 do Uso do acervo): só leitura e sem dados pessoais")
rc, out = rodar("sondagem", f"{tmp}/sondagem.db")
if rc != 0: ok(False, f"teste da sondagem não rodou -> {out[-900:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("21) Uso do acervo: coleta do formulário do site, rotas só para admin, CSV e apagar pessoa (LGPD)")
rc, out = rodar("uso", f"{tmp}/uso.db")
if rc != 0: ok(False, f"teste do Uso do acervo não rodou -> {out[-1200:]}")
else:
    for l in out.splitlines():
        if "|" in l:
            st_, nome, det_ = (l.split("|") + [""])[:3]; ok(st_ == "ok", f"{nome}" + (f" ({det_})" if det_ and st_ != "ok" else ""))

print("\n" + ("TUDO OK" if not falhas else f"{len(falhas)} FALHA(S)"))
sys.exit(1 if falhas else 0)
