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

print("\n" + ("TUDO OK" if not falhas else f"{len(falhas)} FALHA(S)"))
sys.exit(1 if falhas else 0)
