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
        k = connect(); ev = {r[0]: r[1] for r in k.execute("SELECT tipo, count(*) FROM evento WHERE entidade='usuario' AND tipo LIKE 'foto_%' GROUP BY tipo")}; k.close()
        ver("trocas e remoções ficam na auditoria", ev.get("foto_atualizada", 0) >= 5 and ev.get("foto_removida") == 1, str(ev))
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

print("\n" + ("TUDO OK" if not falhas else f"{len(falhas)} FALHA(S)"))
sys.exit(1 if falhas else 0)
