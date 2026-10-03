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
    env = dict(os.environ, CAMP_DB_PATH=db, CAMP_COOKIE_SECURE="false", PYTHONPATH=str(RAIZ / "backend"))
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
    c.commit(); c.close()
    rc, out = rodar("antigo", db)
    ok(rc == 0, "migra sem erro" + ("" if rc == 0 else f" -> {out[-200:]}"))
    if rc == 0:
        c = sqlite3.connect(db)
        ok(c.execute("SELECT titulo FROM projeto WHERE codigo='F099-P0001'").fetchone()[0] == "Casa de teste", "dados existentes preservados")
        ok("identificacao_original" in [r[1] for r in c.execute("PRAGMA table_info(projeto)")], "coluna identificacao_original adicionada")
        ok(c.execute("SELECT valor FROM configuracao WHERE chave='qnap.ip'").fetchone()[0] == "192.168.15.30", "IP do QNAP preenchido pela migração 023")
        ok(c.execute("SELECT count(*) FROM configuracao WHERE chave='estacao.token'").fetchone()[0] == 1, "chave estacao.token criada")

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

print("\n" + ("TUDO OK" if not falhas else f"{len(falhas)} FALHA(S)"))
sys.exit(1 if falhas else 0)
